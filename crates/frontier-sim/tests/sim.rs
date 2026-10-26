use frontier_core::EventLog;
use frontier_sched::PolicyConfig;
use frontier_sim::env::generate;
use frontier_sim::runner::SIM_CONFIG_VERSION;
use frontier_sim::{EnvConfig, RunConfig, SimConfig, run, summarize};

fn env() -> EnvConfig {
    EnvConfig {
        problems: 12,
        approaches_min: 1,
        approaches_max: 3,
        chain_min: 1,
        chain_max: 3,
        shared_lemma_prob: 0.5,
        dead_fraction: 0.3,
        p_alpha: 0.5,
        p_beta: 1.5,
        cost_log_mean: 0.0,
        cost_log_sd: 0.5,
        attempt_cost_sd: 0.3,
        failure_cost_mult: 1.5,
        hint_noise: 1.0,
        ..EnvConfig::default()
    }
}

fn config(policy: PolicyConfig, seed: u64) -> SimConfig {
    SimConfig {
        schema_version: SIM_CONFIG_VERSION.into(),
        name: "test".into(),
        env: env(),
        run: RunConfig {
            seed,
            workers: 4,
            budget_units: 150.0,
            attempt_cap_units: 6.0,
            verify_cost_units: 0.25,
            crash_prob: 0.05,
            max_attempts_per_task: 30,
            max_parallel_per_task: 2,
            prior_cost: 1.0,
            policy,
        },
    }
}

fn all_policies() -> Vec<PolicyConfig> {
    vec![
        PolicyConfig::Fifo,
        PolicyConfig::FixedSlice,
        PolicyConfig::RoundRobin,
        PolicyConfig::Random,
        PolicyConfig::GreedyPrior,
        PolicyConfig::HopelessElimination { min_attempts: 5, threshold: 0.05 },
        PolicyConfig::Ucb { prior_strength: 2.0, use_hints: true, beta: 1.0 },
        PolicyConfig::Thompson { prior_strength: 2.0, use_hints: true },
        PolicyConfig::OracleIndex,
    ]
}

#[test]
fn runs_are_bit_for_bit_reproducible() {
    for p in all_policies() {
        let a = run(&config(p.clone(), 7)).unwrap();
        let b = run(&config(p, 7)).unwrap();
        assert_eq!(a.log.head(), b.log.head());
        assert_eq!(a.log.records(), b.log.records());
    }
}

#[test]
fn budget_cap_and_audit_hold_for_every_policy_and_seed() {
    for p in all_policies() {
        for seed in 0..15 {
            let cfg = config(p.clone(), seed);
            let out = run(&cfg).unwrap();
            let s = summarize(&out.log).unwrap_or_else(|e| panic!("{p:?} seed {seed}: {e}"));
            assert!(s.committed_units <= cfg.run.budget_units + 1e-9);
            assert!(s.solved <= s.problems);
            assert!(s.utilization <= 1.0 + 1e-9, "utilization {}", s.utilization);
            assert_eq!(s.config_digest, cfg.digest());
        }
    }
}

#[test]
fn solved_problems_are_actually_solvable() {
    // Every verified terminal task must have nonzero true success probability:
    // the verifier never accepts a wrong answer.
    for seed in 0..10 {
        let cfg = config(PolicyConfig::RoundRobin, seed);
        let campaign = generate(&cfg.env, seed, cfg.run.budget_units).unwrap();
        let out = run(&cfg).unwrap();
        for r in out.log.records() {
            if let frontier_core::Event::TaskVerified { task_id, .. } = &r.event {
                assert!(campaign.truth[task_id].p_success > 0.0, "{task_id} accepted but impossible");
            }
        }
    }
}

#[test]
fn impossible_campaign_yields_nothing() {
    let mut cfg = config(PolicyConfig::Thompson { prior_strength: 2.0, use_hints: true }, 3);
    cfg.env.dead_fraction = 1.0;
    let s = summarize(&run(&cfg).unwrap().log).unwrap();
    assert_eq!(s.solved, 0);
    assert_eq!(s.accepted, 0);
    assert!(s.units_per_solved.is_none());
}

#[test]
fn total_crashes_charge_but_never_solve() {
    let mut cfg = config(PolicyConfig::RoundRobin, 4);
    cfg.run.crash_prob = 1.0;
    let s = summarize(&run(&cfg).unwrap().log).unwrap();
    assert_eq!(s.solved, 0);
    assert_eq!(s.crashes, s.attempts);
    assert!((s.crash_units - s.committed_units).abs() < 1e-9);
}

#[test]
fn log_roundtrip_and_tamper_detection() {
    let out = run(&config(PolicyConfig::RoundRobin, 5)).unwrap();
    let mut buf = Vec::new();
    out.log.write_jsonl(&mut buf).unwrap();
    let back = EventLog::read_jsonl(buf.as_slice()).unwrap();
    assert_eq!(summarize(&back).unwrap(), summarize(&out.log).unwrap());

    // Claim an extra solved problem without evidence: the hash chain breaks.
    let text = String::from_utf8(buf).unwrap();
    let forged = text.replacen("\"verdict\":\"FAIL\"", "\"verdict\":\"PASS\"", 1);
    assert_ne!(forged, text, "fixture must contain a failed verification");
    assert!(EventLog::read_jsonl(forged.as_bytes()).is_err());
}

#[test]
fn fixed_slice_never_exceeds_its_per_problem_share() {
    let cfg = config(PolicyConfig::FixedSlice, 6);
    let out = run(&cfg).unwrap();
    let slice = cfg.run.budget_units / cfg.env.problems as f64;
    let mut spent: std::collections::BTreeMap<String, f64> = Default::default();
    let mut task_problem = std::collections::BTreeMap::new();
    let mut attempt_problem = std::collections::BTreeMap::new();
    for r in out.log.records() {
        match &r.event {
            frontier_core::Event::TaskRegistered { task_id, problem_id, .. } => {
                task_problem.insert(task_id.clone(), problem_id.clone());
            }
            frontier_core::Event::AttemptDispatched { attempt_id, task_id, .. } => {
                attempt_problem.insert(*attempt_id, task_problem[task_id].clone());
            }
            frontier_core::Event::AttemptFinished { attempt_id, usage, .. } => {
                *spent.entry(attempt_problem[attempt_id].clone()).or_default() += usage.compute_units;
            }
            frontier_core::Event::VerificationFinished { attempt_id, receipt, .. } => {
                *spent.entry(attempt_problem[attempt_id].clone()).or_default() += receipt.cost_units;
            }
            _ => {}
        }
    }
    for (p, u) in spent {
        assert!(u <= slice + 1e-9, "{p} spent {u} > slice {slice}");
    }
}

/// Pinned log head of the smoke campaign. The same value must come out of
/// every build profile and platform (CI checks Linux; it was pinned on
/// Windows). A change here means simulation outputs changed: re-pin only
/// together with a documented kernel change.
#[test]
fn smoke_config_log_head_is_pinned() {
    let cfg: SimConfig = serde_json::from_str(include_str!("../../../configs/smoke.json")).unwrap();
    let out = run(&cfg).unwrap();
    assert_eq!(out.log.head().to_hex(), "36b691cc3e6f8cf5faf3d9cc2038cc757d78d1a1d8e2358770e33dcdc983bbf7");
    // New environment fields default to off and are not serialised.
    let original: serde_json::Value = serde_json::from_str(include_str!("../../../configs/smoke.json")).unwrap();
    assert_eq!(serde_json::to_value(&cfg).unwrap(), original);
}

#[test]
fn perfect_verifier_accepts_only_sound_results() {
    for seed in 0..10 {
        let mut cfg = config(PolicyConfig::RoundRobin, seed);
        cfg.env.distinct_solutions = true;
        let out = run(&cfg).unwrap();
        let s = summarize(&out.log).unwrap();
        assert_eq!(out.truth.true_solved, s.solved);
        assert_eq!(out.truth.false_solved + out.truth.false_accepted_tasks, 0);
    }
}

#[test]
fn false_positives_produce_unsound_solves_and_false_negatives_block_them() {
    let mut cfg = config(PolicyConfig::RoundRobin, 2);
    cfg.env.distinct_solutions = true;
    cfg.env.verifier_fpr = 1.0;
    let out = run(&cfg).unwrap();
    let s = summarize(&out.log).unwrap();
    assert!(out.truth.false_solved > 0);
    assert_eq!(out.truth.true_solved + out.truth.false_solved, s.solved);

    cfg.env.verifier_fpr = 0.0;
    cfg.env.verifier_fnr = 1.0;
    let out = run(&cfg).unwrap();
    assert_eq!(summarize(&out.log).unwrap().solved, 0);
}

#[test]
fn dead_hint_detection_changes_only_dead_hints() {
    let mut cfg = config(PolicyConfig::RoundRobin, 4);
    cfg.env.dead_fraction = 0.5;
    let base = generate(&cfg.env, 4, 100.0).unwrap();
    cfg.env.dead_hint_detection = 1.0;
    let det = generate(&cfg.env, 4, 100.0).unwrap();
    assert_eq!(base.truth, det.truth);
    let mut dead_seen = 0;
    for (id, t) in &base.truth {
        if t.p_success == 0.0 {
            dead_seen += 1;
            assert!(det.hints[id] < 0.05, "detected dead hint {}", det.hints[id]);
        } else {
            assert_eq!(base.hints[id], det.hints[id]);
        }
    }
    assert!(dead_seen > 0);
}

#[test]
fn dead_attempts_are_counted() {
    let mut cfg = config(PolicyConfig::RoundRobin, 5);
    cfg.env.dead_fraction = 1.0;
    let out = run(&cfg).unwrap();
    assert_eq!(out.truth.dead_attempts as u64, summarize(&out.log).unwrap().attempts);
}

#[test]
fn sticky_runs_are_reproducible_and_audited() {
    let mut cfg = config(PolicyConfig::Thompson { prior_strength: 2.0, use_hints: true }, 8);
    cfg.env.failure_stickiness = 0.8;
    let a = run(&cfg).unwrap();
    assert_eq!(a.log.head(), run(&cfg).unwrap().log.head());
    summarize(&a.log).unwrap();
}

#[test]
fn real_catalog_builds_a_campaign_bound_to_its_digest() {
    use frontier_core::Digest;
    use frontier_sim::real::{campaign_from_catalog, load_catalog};
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../research/realtasks/catalog-v1.json");
    let digest = Digest::from_hex("80bdd82bec3e249b17d7938dab3e28786989dae55edd0650875c0c6c440b9585").unwrap();
    let cat = load_catalog(&path, digest).unwrap();
    assert!(load_catalog(&path, Digest::ZERO).is_err(), "digest mismatch must be refused");
    let c = campaign_from_catalog(&cat, 60.0).unwrap();
    assert_eq!(c.specs.len(), 34);
    assert_eq!(c.truth.values().filter(|t| t.dead).count(), 8);
    for s in &c.specs {
        assert_eq!(s.spec().verification.verifier_id, "property-tests");
        assert_eq!(s.spec().verification.required_trust, frontier_core::TrustClass::V1);
    }
    assert!(c.hints.values().all(|h| (0.0..=1.0).contains(h)));
}
