//! Catalog v3: dependency-structured real tasks, lemma libraries, audit.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use frontier_core::evidence::{RECEIPT_SCHEMA_VERSION, TrustClass};
use frontier_core::{
    Artifact, ArtifactKind, AttemptOutcome, Digest, Event, EventLog, TaskGraph, TaskState, Usage, Verdict, VerifierReceipt,
};
use frontier_sim::audit::AuditError;
use frontier_sim::external::{ExternalWorker, LibraryEntry};
use frontier_sim::real::{
    Catalog, RealExperimentConfig, campaign_from_catalog, cell_config, check_service_matches, compose_program, load_catalog,
    ordered_catalog,
};
use frontier_sim::runner::{LibraryUse, candidate_artifact, run_campaign_with};
use frontier_sim::summarize;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// The dev config pins the catalog digest; tests use the same pin.
fn dev_config() -> RealExperimentConfig {
    let text = std::fs::read_to_string(root().join("research/realtasks/dev-v3.json")).unwrap();
    serde_json::from_str(&text).unwrap()
}

fn catalog() -> Catalog {
    let cfg = dev_config();
    load_catalog(&root().join("research/realtasks").join(&cfg.catalog), cfg.catalog_sha256).unwrap()
}

#[test]
fn v3_catalog_builds_a_task_graph_with_alternative_approaches() {
    let cat = catalog();
    assert!(cat.is_dependency_structured());
    let campaign = campaign_from_catalog(&cat, 60.0).unwrap();
    assert!((20..=30).contains(&campaign.specs.len()));
    let graph = TaskGraph::build(campaign.tasks.clone()).unwrap();

    // Shared lemmas are merged by signature, and aliases share truth and helper.
    assert!(!graph.merged().is_empty(), "catalog must exercise lemma sharing");
    for (alias, idx) in graph.merged() {
        let canon = &graph.node(*idx).def.task_id;
        assert_eq!(campaign.truth[alias], campaign.truth[canon]);
        assert_eq!(campaign.helpers[alias], campaign.helpers[canon]);
    }
    for p in &cat.problems {
        let terminals = graph.nodes().iter().filter(|n| n.def.problem_id == p.problem_id && n.def.terminal).count();
        assert!(terminals >= 2, "{}: a direct and at least one lemma route", p.problem_id);
    }
    // Initially only tasks without prerequisites are eligible; every task
    // with prerequisites is pending, and every prerequisite has a helper name.
    for (i, n) in graph.nodes().iter().enumerate() {
        assert_eq!(n.state() == TaskState::Eligible, n.deps.is_empty(), "{}", n.def.task_id);
        for &d in &n.deps {
            assert!(campaign.helpers.contains_key(&graph.node(d).def.task_id));
        }
        assert_eq!(graph.eligible().any(|e| e == i), n.deps.is_empty());
    }
    // A chained route: lemma -> lemma -> goal.
    let chain = graph.index_of("dep.trimmed_pos_sum.a1.goal").unwrap();
    let mid = graph.node(chain).deps[0];
    assert_eq!(graph.node(mid).deps.len(), 1);

    // Dead problems: every terminal is dead or sits behind a dead lemma.
    let dead: BTreeSet<&str> = cat.problems.iter().filter(|p| p.label == "dead").map(|p| p.problem_id.as_str()).collect();
    assert!(dead.len() >= 3);

    // Shuffling permutes problems, never tasks within a problem.
    let shuffled = ordered_catalog(&cat, Some(7));
    assert_ne!(
        shuffled.problems.iter().map(|p| &p.problem_id).collect::<Vec<_>>(),
        cat.problems.iter().map(|p| &p.problem_id).collect::<Vec<_>>()
    );
    for p in &shuffled.problems {
        let orig = cat.problems.iter().find(|q| q.problem_id == p.problem_id).unwrap();
        assert_eq!(p.tasks.iter().map(|t| &t.id).collect::<Vec<_>>(), orig.tasks.iter().map(|t| &t.id).collect::<Vec<_>>());
    }
}

#[test]
fn dependent_tasks_become_eligible_only_once_every_lemma_is_verified() {
    let campaign = campaign_from_catalog(&catalog(), 60.0).unwrap();
    let mut g = TaskGraph::build(campaign.tasks).unwrap();
    let goal = g.index_of("dep.max_times_min.a1.goal").unwrap();
    let deps = g.node(goal).deps.clone();
    assert_eq!(deps.len(), 2);
    assert_eq!(g.node(goal).state(), TaskState::Pending);
    g.mark_verified(deps[0]).unwrap();
    assert_eq!(g.node(goal).state(), TaskState::Pending, "one lemma is not enough");
    assert_eq!(g.mark_verified(deps[1]).unwrap(), vec![goal]);
}

/// Same fixture as `test_compose_matches_rust_fixture` in python/tests/test_deps.py.
#[test]
fn compose_program_matches_python() {
    let lib = [
        LibraryEntry { name: "h_b".into(), source: "def f(xs):\n    return len(xs)\n".into() },
        LibraryEntry { name: "h_a".into(), source: "def f(xs):\n    return sum(xs)".into() },
    ];
    assert_eq!(
        compose_program(&lib, "def f(xs):\n    return (h_a(xs) - h_b(xs))\n"),
        "def f(xs):\n    return sum(xs)\nh_a = f\ndef f(xs):\n    return len(xs)\nh_b = f\ndef f(xs):\n    return (h_a(xs) - h_b(xs))\n"
    );
}

fn lib(source: &str, artifact: Digest) -> Vec<LibraryUse> {
    vec![LibraryUse { entry: LibraryEntry { name: "h_max0".into(), source: source.into() }, task_id: "dep.p.a1.max0".into(), artifact }]
}

fn digest_of(body: serde_json::Value, parents: Vec<Digest>) -> Digest {
    Artifact { kind: ArtifactKind::Candidate, spec_digest: Digest::ZERO, task_id: "dep.p.a1.goal".into(), parents, body }.digest().unwrap()
}

#[test]
fn library_contents_are_bound_into_the_artifact_digest() {
    let cand = "def f(xs):\n    return h_max0(xs)\n";
    let a = Digest::of_bytes(b"lemma artifact a");
    let (plain, no_parents) = candidate_artifact(cand, &[]);
    assert_eq!(plain, serde_json::json!({ "source": cand }), "no library: the v1 body exactly");
    assert!(no_parents.is_empty());

    let (b1, p1) = candidate_artifact(cand, &lib("def f(xs):\n    return max(xs, default=0)\n", a));
    assert_eq!(p1, vec![a]);
    assert!(b1["source"].as_str().unwrap().starts_with("def f(xs):\n    return max(xs, default=0)\nh_max0 = f\n"));
    let d1 = digest_of(b1.clone(), p1.clone());
    // Another helper source, or another parent, gives another artifact.
    let (b2, p2) = candidate_artifact(cand, &lib("def f(xs):\n    return 0\n", a));
    assert_ne!(d1, digest_of(b2, p2));
    let (b3, p3) = candidate_artifact(cand, &lib("def f(xs):\n    return max(xs, default=0)\n", Digest::of_bytes(b"other")));
    assert_ne!(d1, digest_of(b3, p3));
    assert_eq!(d1, digest_of(b1, p1), "deterministic");
}

fn receipt(artifact: Digest, verdict: Verdict) -> VerifierReceipt {
    VerifierReceipt {
        schema_version: RECEIPT_SCHEMA_VERSION.into(),
        spec_digest: Digest::ZERO,
        artifact_digest: artifact,
        verdict,
        trust_class: TrustClass::V1,
        verifier_id: "property-tests".into(),
        verifier_version: "0.1.0".into(),
        reason: String::new(),
        cost_units: 1.0,
    }
}

/// A hand-built, correctly chained log: lemma L verified, then goal G
/// attempted with `parents`. `goal_first` dispatches G before L is verified.
fn chain_log(parents: Vec<Digest>, goal_first: bool) -> EventLog {
    let (dl, dbad, dg) = (Digest::of_bytes(b"L"), Digest::of_bytes(b"bad"), Digest::of_bytes(b"G"));
    let usage = Usage { compute_units: 1.0, ..Usage::default() };
    let mut log = EventLog::new();
    log.append(Event::RunStarted {
        run_id: "t".into(),
        config_digest: Digest::ZERO,
        seed: 1,
        policy: "p".into(),
        kernel_version: "x".into(),
        budget_units: 100.0,
        workers: 1,
    });
    log.append(Event::ProblemRegistered { problem_id: "p".into(), spec_digest: Digest::ZERO });
    log.append(Event::TaskRegistered { task_id: "L".into(), problem_id: "p".into(), depends_on: vec![], terminal: false });
    log.append(Event::TaskRegistered { task_id: "G".into(), problem_id: "p".into(), depends_on: vec!["L".into()], terminal: true });
    let lemma = |log: &mut EventLog, id: u64, at: f64, d: Digest, v: Verdict| {
        log.append(Event::AttemptDispatched { attempt_id: id, task_id: "L".into(), worker: 0, at, reserved_units: 5.0 });
        log.append(Event::AttemptFinished {
            attempt_id: id,
            at: at + 1.0,
            outcome: AttemptOutcome::Artifact { digest: d, duplicate: false, parents: vec![] },
            usage: usage.clone(),
        });
        log.append(Event::VerificationFinished { attempt_id: id, at: at + 2.0, receipt: receipt(d, v) });
    };
    lemma(&mut log, 0, 0.0, dbad, Verdict::Fail);
    let goal_attempt = |log: &mut EventLog, at: f64| {
        log.append(Event::AttemptDispatched { attempt_id: 2, task_id: "G".into(), worker: 0, at, reserved_units: 5.0 });
        log.append(Event::AttemptFinished {
            attempt_id: 2,
            at: at + 1.0,
            outcome: AttemptOutcome::Artifact { digest: dg, duplicate: false, parents: parents.clone() },
            usage: usage.clone(),
        });
        log.append(Event::VerificationFinished { attempt_id: 2, at: at + 2.0, receipt: receipt(dg, Verdict::Fail) });
    };
    if goal_first {
        goal_attempt(&mut log, 2.0);
    }
    lemma(&mut log, 1, 5.0, dl, Verdict::Pass);
    log.append(Event::TaskVerified { task_id: "L".into(), artifact: dl, at: 7.0 });
    if !goal_first {
        goal_attempt(&mut log, 8.0);
    }
    log.append(Event::RunFinished { at: 20.0, committed_units: 6.0 });
    log
}

#[test]
fn audit_rejects_libraries_built_from_unverified_artifacts() {
    let (dl, dbad) = (Digest::of_bytes(b"L"), Digest::of_bytes(b"bad"));
    summarize(&chain_log(vec![dl], false)).expect("library from the accepted lemma artifact is fine");
    // A rejected lemma artifact, or a made-up one, cannot be injected even
    // in a log whose hash chain is intact.
    for bad in [dbad, Digest::of_bytes(b"never seen")] {
        assert!(matches!(summarize(&chain_log(vec![bad], false)), Err(AuditError::UnverifiedParent { .. })));
    }
    assert!(matches!(summarize(&chain_log(vec![], true)), Err(AuditError::IneligibleDispatch { .. })));
}

fn server_or_skip() -> Option<(RealExperimentConfig, ExternalWorker)> {
    let cfg = dev_config();
    match ExternalWorker::spawn(&cfg.server, &root().join("research/realtasks")) {
        Ok(w) => Some((cfg, w)),
        Err(e) => {
            eprintln!("python worker service unavailable ({e}); skipping");
            None
        }
    }
}

/// End to end through the Python service: a small v3 campaign is
/// deterministic, passes the audit, and every attempt on a dependent task
/// carried exactly the accepted artifacts of its prerequisites.
#[test]
fn real_v3_run_is_deterministic_and_libraries_are_the_accepted_lemmas() {
    let Some((cfg, mut worker)) = server_or_skip() else { return };
    let cat = catalog();
    check_service_matches(&worker, &cat).unwrap();
    let campaign = campaign_from_catalog(&ordered_catalog(&cat, Some(1)), cfg.run.budget_units).unwrap();
    let oracle = cfg.policies.iter().position(|p| *p == frontier_sched::PolicyConfig::OracleIndex).unwrap();
    let sim = cell_config(&cfg, &cfg.policies[oracle], 1, campaign.specs.len());
    let a = run_campaign_with(&sim, &campaign, Some(&mut worker)).unwrap();
    let b = run_campaign_with(&sim, &campaign, Some(&mut worker)).unwrap();
    assert_eq!(a.log.head(), b.log.head());
    let s = summarize(&a.log).unwrap();
    assert!(s.committed_units <= cfg.run.budget_units + 1e-9);

    let mut deps: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut accepted: BTreeMap<String, Digest> = BTreeMap::new();
    let mut task_of: BTreeMap<u64, String> = BTreeMap::new();
    let mut with_library = 0;
    let mut dependent_verified = 0;
    for r in a.log.records() {
        match &r.event {
            Event::TaskRegistered { task_id, depends_on, .. } => {
                deps.insert(task_id.clone(), depends_on.clone());
            }
            Event::AttemptDispatched { attempt_id, task_id, .. } => {
                task_of.insert(*attempt_id, task_id.clone());
            }
            Event::AttemptFinished { attempt_id, outcome: AttemptOutcome::Artifact { parents, .. }, .. } => {
                let task = &task_of[attempt_id];
                let want: BTreeSet<Digest> = deps[task].iter().map(|d| accepted[d]).collect();
                assert_eq!(parents.iter().copied().collect::<BTreeSet<_>>(), want, "{task}");
                assert_eq!(parents.len(), deps[task].len());
                with_library += usize::from(!parents.is_empty());
            }
            Event::TaskVerified { task_id, artifact, .. } => {
                accepted.insert(task_id.clone(), *artifact);
                dependent_verified += usize::from(!deps[task_id].is_empty());
            }
            _ => {}
        }
    }
    assert!(with_library > 0, "the run must reach a dependent task");
    assert!(dependent_verified > 0, "and verify one through its lemmas");
}
