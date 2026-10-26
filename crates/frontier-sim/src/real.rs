//! Real verifier-backed campaigns: a task catalog plus the external worker
//! service, run by the same scheduler, ledger, evidence store and audit as
//! simulations.
//!
//! The catalog (built by `python -m frontier_py.realtasks.catalog`) fixes the
//! problems, their statements, the probe hints shown to policies and the
//! ground-truth labels kept from them. The campaign is the same for every
//! seed; the seed selects the worker's search streams.

use std::collections::BTreeMap;
use std::path::Path;

use frontier_core::evidence::TrustClass;
use frontier_core::spec::{ProblemCategory, Provenance, SPEC_SCHEMA_VERSION, VerificationMethod, VerificationSpec};
use frontier_core::{Budget, Digest, ProblemSpec, SealedSpec, TaskDef, TaskKind};
use frontier_sched::PolicyConfig;
use serde::{Deserialize, Serialize};

use crate::audit::summarize;
use crate::env::{Campaign, EnvConfig, TaskTruth};
use crate::experiment::ResultRecord;
use crate::external::{ExternalWorker, LIBRARY_PROTOCOL, LibraryEntry, ServerCommand};
use crate::runner::{RunConfig, SIM_CONFIG_VERSION, SimConfig, SimError, run_campaign_with};

pub const REAL_EXPERIMENT_VERSION: &str = "0.1";
pub const PROPERTY_TESTS_ID: &str = "property-tests";
pub const PROPERTY_TESTS_VERSION: &str = "0.1.0";

#[derive(Clone, Debug, Deserialize)]
pub struct CatalogTask {
    pub name: String,
    pub problem_id: String,
    pub statement: String,
    pub status: String,
    pub dead: bool,
    pub hint: f64,
    pub criterion_sha256: Digest,
    pub p_hat: f64,
    pub mean_gen_units: f64,
}

/// One task of a catalog-v3 problem. `id` and `depends_on` are local to the
/// problem; a lemma shared by two approaches is listed once per approach
/// with the same `signature` and `name`, and the task graph merges it.
#[derive(Clone, Debug, Deserialize)]
pub struct CatalogDepTask {
    pub id: String,
    /// Task name understood by the worker service.
    pub name: String,
    pub signature: String,
    #[serde(default)]
    pub depends_on: Vec<String>,
    pub terminal: bool,
    /// Call name under which a verified artifact of this task is offered to
    /// its dependents (lemmas only).
    #[serde(default)]
    pub helper: Option<String>,
    pub status: String,
    pub dead: bool,
    pub hint: f64,
    /// Calibrated success rate, conditional on the task's lemmas being verified.
    pub p_hat: f64,
    pub mean_gen_units: f64,
}

#[derive(Clone, Debug, Deserialize)]
pub struct CatalogProblem {
    pub problem_id: String,
    pub statement: String,
    pub label: String,
    pub criterion_sha256: Digest,
    pub tasks: Vec<CatalogDepTask>,
}

/// Catalog v1/v2 (`tasks`: one single-task problem each) or v3 (`problems`:
/// dependency-structured problems with alternative approaches).
#[derive(Clone, Debug, Deserialize)]
pub struct Catalog {
    pub catalog_version: String,
    pub suite_version: String,
    pub hidden_seed: u64,
    #[serde(default)]
    pub tasks: Vec<CatalogTask>,
    #[serde(default)]
    pub problems: Vec<CatalogProblem>,
}

pub const DEPENDENCY_CATALOG_VERSION: &str = "3";

impl Catalog {
    pub fn is_dependency_structured(&self) -> bool {
        self.catalog_version == DEPENDENCY_CATALOG_VERSION
    }

    fn check_shape(&self) -> Result<(), SimError> {
        let ok = if self.is_dependency_structured() {
            self.tasks.is_empty() && !self.problems.is_empty()
        } else {
            self.problems.is_empty() && !self.tasks.is_empty()
        };
        if ok {
            Ok(())
        } else {
            Err(SimError::Config(format!(
                "catalog version {} must list {}",
                self.catalog_version,
                if self.is_dependency_structured() { "problems only" } else { "tasks only" }
            )))
        }
    }
}

/// The program the verifier runs for a dependent task's candidate: every
/// library helper's source (sorted by name), with its `f` bound to the
/// helper name, then the candidate. Mirrors `frontier_py.realtasks.dsl.compose`.
pub fn compose_program(library: &[LibraryEntry], candidate: &str) -> String {
    let mut lib: Vec<&LibraryEntry> = library.iter().collect();
    lib.sort_by(|a, b| a.name.cmp(&b.name).then_with(|| a.source.cmp(&b.source)));
    let mut out = String::new();
    for e in lib {
        out.push_str(&e.source);
        if !e.source.ends_with('\n') {
            out.push('\n');
        }
        out.push_str(&e.name);
        out.push_str(" = f\n");
    }
    out.push_str(candidate);
    out
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RealExperimentConfig {
    pub schema_version: String,
    pub experiment_id: String,
    /// Catalog path relative to this config file, and its frozen SHA-256.
    pub catalog: String,
    pub catalog_sha256: Digest,
    pub server: ServerCommand,
    pub policies: Vec<PolicyConfig>,
    pub seed_start: u64,
    pub seeds: u64,
    /// `seed` and `policy` are overridden per cell; `crash_prob` must be 0.
    pub run: RunConfig,
    /// Permute problem order per seed (stream "problem-order"), so that no
    /// policy can exploit the order in which the catalog lists tasks.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub shuffle_problem_order: bool,
}

/// The catalog's problems, optionally permuted by a stream keyed only by
/// seed (v1/v2: its tasks; v3: its problems, each keeping its task order).
pub fn ordered_catalog(cat: &Catalog, shuffle_seed: Option<u64>) -> Catalog {
    fn shuffle<T>(xs: &mut [T], seed: u64) {
        let mut rng = frontier_core::SplitMix64::derive(seed, "problem-order");
        for i in (1..xs.len()).rev() {
            let j = rng.below(i as u64 + 1) as usize;
            xs.swap(i, j);
        }
    }
    let mut out = cat.clone();
    if let Some(seed) = shuffle_seed {
        shuffle(&mut out.tasks, seed);
        shuffle(&mut out.problems, seed);
    }
    out
}

pub fn load_catalog(path: &Path, expected: Digest) -> Result<Catalog, SimError> {
    let bytes = std::fs::read(path).map_err(|e| SimError::Config(format!("{}: {e}", path.display())))?;
    let actual = Digest::of_bytes(&bytes);
    if actual != expected {
        return Err(SimError::Config(format!("catalog digest {actual} does not match frozen {expected}")));
    }
    let cat: Catalog = serde_json::from_slice(&bytes).map_err(|e| SimError::Config(format!("catalog: {e}")))?;
    cat.check_shape()?;
    Ok(cat)
}

fn problem_spec(problem_id: &str, statement: &str, criterion: Digest, cat: &Catalog, budget_hint: f64) -> Result<SealedSpec, SimError> {
    let spec = ProblemSpec {
        schema_version: SPEC_SCHEMA_VERSION.into(),
        problem_id: problem_id.to_owned(),
        objective: statement.to_owned(),
        category: ProblemCategory::Algorithm,
        inputs: vec![],
        allowed_tools: vec![],
        budget: Budget { compute_units: budget_hint, ..Budget::default() },
        verification: VerificationSpec {
            method: VerificationMethod::PropertyTests,
            verifier_id: PROPERTY_TESTS_ID.into(),
            verifier_version: PROPERTY_TESTS_VERSION.into(),
            criterion_sha256: criterion,
            required_trust: TrustClass::V1,
        },
        success_criteria: "Every visible and frozen hidden case matches the reference output exactly".into(),
        depends_on: vec![],
        provenance: Provenance {
            source: format!("frontier_py.realtasks suite v{} (catalog v{})", cat.suite_version, cat.catalog_version),
            created_by: "frontier".into(),
            license: None,
        },
        difficulty: None,
    };
    SealedSpec::seal(spec).map_err(|e| SimError::Config(e.to_string()))
}

/// Dependency-structured problems (catalog v3). Task ids are
/// `<problem_id>.<local id>`; each lemma task gets a helper name; truth and
/// hints are per task (aliases of merged lemmas get the same values). The
/// criterion digest of a problem commits to the hidden suites of all its
/// tasks. `p_hat` is calibrated with the task's lemmas verified.
fn dependency_campaign(cat: &Catalog, budget_hint: f64) -> Result<Campaign, SimError> {
    let mut campaign = Campaign { specs: vec![], tasks: vec![], truth: BTreeMap::new(), hints: BTreeMap::new(), helpers: BTreeMap::new() };
    for p in &cat.problems {
        campaign.specs.push(problem_spec(&p.problem_id, &p.statement, p.criterion_sha256, cat, budget_hint)?);
        let local: BTreeMap<&str, &CatalogDepTask> = p.tasks.iter().map(|t| (t.id.as_str(), t)).collect();
        let tid = |id: &str| format!("{}.{id}", p.problem_id);
        for t in &p.tasks {
            for d in &t.depends_on {
                let dep = local
                    .get(d.as_str())
                    .ok_or_else(|| SimError::Config(format!("{}: task {} depends on unknown {d}", p.problem_id, t.id)))?;
                if dep.helper.is_none() {
                    return Err(SimError::Config(format!("{}: prerequisite {d} of {} has no helper name", p.problem_id, t.id)));
                }
            }
            campaign.tasks.push(TaskDef {
                task_id: tid(&t.id),
                problem_id: p.problem_id.clone(),
                kind: if t.terminal { TaskKind::Goal } else { TaskKind::ProofObligation },
                depends_on: t.depends_on.iter().map(|d| tid(d)).collect(),
                signature: t.signature.clone(),
                terminal: t.terminal,
            });
            let p_success = if t.dead { 0.0 } else { t.p_hat };
            campaign.truth.insert(
                tid(&t.id),
                TaskTruth { name: t.name.clone(), dead: t.dead, p_success, mean_cost: t.mean_gen_units, secret: String::new() },
            );
            campaign.hints.insert(tid(&t.id), t.hint);
            if let Some(h) = &t.helper {
                campaign.helpers.insert(tid(&t.id), h.clone());
            }
        }
    }
    Ok(campaign)
}

/// Problems, task graphs, hints and ground truth from a catalog: single-task
/// problems for v1/v2, dependency-structured problems for v3.
/// `p_hat` and `mean_gen_units` are calibration estimates used only by the
/// diagnostic oracle; dead-by-construction tasks get p = 0.
pub fn campaign_from_catalog(cat: &Catalog, budget_hint: f64) -> Result<Campaign, SimError> {
    cat.check_shape()?;
    if cat.is_dependency_structured() {
        return dependency_campaign(cat, budget_hint);
    }
    let mut specs = Vec::new();
    let mut tasks = Vec::new();
    let mut truth = BTreeMap::new();
    let mut hints = BTreeMap::new();
    for t in &cat.tasks {
        specs.push(problem_spec(&t.problem_id, &t.statement, t.criterion_sha256, cat, budget_hint)?);
        let task_id = format!("{}.goal", t.problem_id);
        tasks.push(TaskDef {
            task_id: task_id.clone(),
            problem_id: t.problem_id.clone(),
            kind: TaskKind::Goal,
            depends_on: vec![],
            signature: t.name.clone(),
            terminal: true,
        });
        let p = if t.dead { 0.0 } else { t.p_hat };
        truth.insert(
            task_id.clone(),
            TaskTruth { name: t.name.clone(), dead: t.dead, p_success: p, mean_cost: t.mean_gen_units, secret: String::new() },
        );
        hints.insert(task_id, t.hint);
    }
    Ok(Campaign { specs, tasks, truth, hints, helpers: BTreeMap::new() })
}

/// A neutral environment block for external-backend runs: nothing in it is
/// sampled; it makes the oracle's expected charge equal to the calibrated
/// mean generation charge plus verification.
pub fn neutral_env(problems: usize) -> EnvConfig {
    EnvConfig {
        problems,
        approaches_min: 1,
        approaches_max: 1,
        chain_min: 1,
        chain_max: 1,
        shared_lemma_prob: 0.0,
        dead_fraction: 0.0,
        p_alpha: 1.0,
        p_beta: 1.0,
        cost_log_mean: 0.0,
        cost_log_sd: 0.0,
        attempt_cost_sd: 0.0,
        failure_cost_mult: 1.0,
        hint_noise: 0.0,
        ..EnvConfig::default()
    }
}

pub fn cell_config(cfg: &RealExperimentConfig, policy: &PolicyConfig, seed: u64, problems: usize) -> SimConfig {
    let mut run = cfg.run.clone();
    run.seed = seed;
    run.policy = policy.clone();
    SimConfig {
        schema_version: SIM_CONFIG_VERSION.into(),
        name: format!("{}/catalog-{}", cfg.experiment_id, &cfg.catalog_sha256.to_hex()[..16]),
        env: neutral_env(problems),
        run,
    }
}

/// Refuse to run if the service verifies against a different hidden suite
/// than the one the catalog's criterion digests commit to.
pub fn check_service_matches(worker: &ExternalWorker, cat: &Catalog) -> Result<(), SimError> {
    let suite = worker.hello.get("suite_version").and_then(serde_json::Value::as_str);
    let seed = worker.hello.get("hidden_seed").and_then(serde_json::Value::as_u64);
    if suite != Some(cat.suite_version.as_str()) || seed != Some(cat.hidden_seed) {
        return Err(SimError::Config(format!(
            "worker service serves suite {suite:?} seed {seed:?}, catalog needs suite {:?} seed {}",
            cat.suite_version, cat.hidden_seed
        )));
    }
    if cat.is_dependency_structured() && worker.protocol < LIBRARY_PROTOCOL {
        return Err(SimError::Config(format!(
            "catalog v{} needs worker protocol {LIBRARY_PROTOCOL} (libraries), service speaks {}",
            cat.catalog_version, worker.protocol
        )));
    }
    Ok(())
}

/// Per-thread output: records grouped by seed, plus verifier wall seconds.
type ThreadOutput = (Vec<(u64, Vec<ResultRecord>)>, f64);

/// Run every (seed, policy) cell. Each thread owns one service process.
pub fn run_real_experiment(cfg: &RealExperimentConfig, base: &Path, threads: usize) -> Result<(Vec<ResultRecord>, f64), SimError> {
    if cfg.schema_version != REAL_EXPERIMENT_VERSION {
        return Err(SimError::Config("unsupported real experiment schema_version".into()));
    }
    if cfg.run.crash_prob != 0.0 {
        return Err(SimError::Config("crash_prob must be 0 for real campaigns".into()));
    }
    let catalog = load_catalog(&base.join(&cfg.catalog), cfg.catalog_sha256)?;
    let fixed_campaign = campaign_from_catalog(&catalog, cfg.run.budget_units)?;
    let seeds: Vec<u64> = (cfg.seed_start..cfg.seed_start + cfg.seeds).collect();
    let threads = threads.max(1).min(seeds.len().max(1));
    let chunks: Vec<Vec<u64>> = (0..threads).map(|i| seeds.iter().copied().skip(i).step_by(threads).collect()).collect();
    let mut out: Vec<(u64, Vec<ResultRecord>)> = Vec::new();
    let mut wall = 0.0;
    std::thread::scope(|scope| -> Result<(), SimError> {
        let handles: Vec<_> = chunks
            .into_iter()
            .map(|chunk| {
                let (fixed_campaign, catalog) = (&fixed_campaign, &catalog);
                scope.spawn(move || -> Result<ThreadOutput, SimError> {
                    let mut worker = ExternalWorker::spawn(&cfg.server, base)?;
                    check_service_matches(&worker, catalog)?;
                    let mut local = vec![];
                    for seed in chunk {
                        let shuffled;
                        let campaign = if cfg.shuffle_problem_order {
                            shuffled = campaign_from_catalog(&ordered_catalog(catalog, Some(seed)), cfg.run.budget_units)?;
                            &shuffled
                        } else {
                            fixed_campaign
                        };
                        let mut recs = vec![];
                        for (pi, policy) in cfg.policies.iter().enumerate() {
                            let sim = cell_config(cfg, policy, seed, campaign.specs.len());
                            sim.validate()?;
                            let output = run_campaign_with(&sim, campaign, Some(&mut worker))?;
                            let summary = summarize(&output.log).map_err(|e| SimError::Invariant(e.to_string()))?;
                            recs.push(ResultRecord {
                                experiment_id: cfg.experiment_id.clone(),
                                regime: "pilot".into(),
                                policy_index: pi,
                                policy_config: policy.clone(),
                                summary,
                                select_nanos: output.select_nanos,
                                decisions: output.decisions,
                                sim_true_solved: output.truth.true_solved,
                                sim_false_solved: output.truth.false_solved,
                                sim_false_accepted_tasks: output.truth.false_accepted_tasks,
                                sim_dead_attempts: output.truth.dead_attempts,
                            });
                        }
                        local.push((seed, recs));
                    }
                    Ok((local, worker.verify_wall_seconds))
                })
            })
            .collect();
        for h in handles {
            let (recs, w) = h.join().expect("worker thread panicked")?;
            out.extend(recs);
            wall += w;
        }
        Ok(())
    })?;
    out.sort_by_key(|(s, _)| *s);
    Ok((out.into_iter().flat_map(|(_, r)| r).collect(), wall))
}
