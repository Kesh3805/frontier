//! Discrete-event execution of one campaign under one policy.
//!
//! Time is simulated: one compute unit (CU) of work occupies one worker for
//! one simulated second. Each attempt reserves its worst case (attempt cap
//! plus verification) before it starts, so the hard budget cap holds by
//! construction. Attempt outcomes come from a stream keyed by
//! (seed, task, per-task attempt index): different policies that make the
//! k-th attempt on a task see the same outcome (common random numbers),
//! which makes paired comparisons between policies far less noisy.

use std::cmp::Reverse;
use std::collections::{BTreeMap, BinaryHeap};
use std::time::Instant;

use frontier_core::evidence::{RECEIPT_SCHEMA_VERSION, TrustClass};
use frontier_core::{
    Artifact, ArtifactKind, Attempt, AttemptOutcome, AttemptState, BudgetLedger, ClaimStatus, Digest, Event, EventLog, EvidenceStore,
    KERNEL_VERSION, SealedSpec, SplitMix64, Submission, TaskGraph, TaskState, Usage, Verdict, VerifierReceipt,
};
use frontier_sched::{Approach, OracleInfo, Policy, PolicyConfig, ProblemStats, SchedView, TaskStats};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::env::{Campaign, EnvConfig, SIM_VERIFIER_ID, SIM_VERIFIER_VERSION, TaskTruth, generate};
use crate::external::{ExternalWorker, LibraryEntry};
use crate::real::compose_program;

pub const SIM_CONFIG_VERSION: &str = "0.1";

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunConfig {
    pub seed: u64,
    pub workers: usize,
    pub budget_units: f64,
    /// Attempts running longer are killed and charged this amount.
    pub attempt_cap_units: f64,
    pub verify_cost_units: f64,
    /// Probability that an attempt fails for infrastructure reasons.
    pub crash_prob: f64,
    pub max_attempts_per_task: u32,
    pub max_parallel_per_task: u32,
    /// Prior mean attempt cost given to policies before they observe any.
    pub prior_cost: f64,
    pub policy: PolicyConfig,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SimConfig {
    pub schema_version: String,
    pub name: String,
    pub env: EnvConfig,
    pub run: RunConfig,
}

impl SimConfig {
    pub fn validate(&self) -> Result<(), SimError> {
        let bad = |m: &str| Err(SimError::Config(m.into()));
        if self.schema_version != SIM_CONFIG_VERSION {
            return bad("unsupported schema_version");
        }
        self.env.validate().map_err(SimError::Config)?;
        let r = &self.run;
        if r.workers == 0 || r.max_parallel_per_task == 0 || r.max_attempts_per_task == 0 {
            return bad("workers, max_parallel_per_task and max_attempts_per_task must be > 0");
        }
        let positive = |x: f64| x.is_finite() && x > 0.0;
        if !positive(r.budget_units) || !positive(r.attempt_cap_units) || !positive(r.prior_cost) {
            return bad("budget_units, attempt_cap_units and prior_cost must be > 0");
        }
        if !(r.verify_cost_units.is_finite() && r.verify_cost_units >= 0.0) || !(0.0..=1.0).contains(&r.crash_prob) {
            return bad("verify_cost_units must be >= 0 and crash_prob in [0, 1]");
        }
        Ok(())
    }

    pub fn digest(&self) -> Digest {
        Digest::of_canonical(self).expect("config serialises")
    }
}

#[derive(Debug, thiserror::Error)]
pub enum SimError {
    #[error("invalid config: {0}")]
    Config(String),
    #[error("policy {policy} selected non-runnable task {task}")]
    PolicyViolation { policy: String, task: usize },
    #[error("kernel invariant violated: {0}")]
    Invariant(String),
}

/// Outcome of a run. `log` is the authoritative record; everything else can
/// be recomputed from it (see `audit`).
pub struct RunOutput {
    pub log: EventLog,
    pub policy_name: String,
    /// Wall-clock nanoseconds spent inside `Policy::select` (host-dependent,
    /// excluded from the deterministic log).
    pub select_nanos: u128,
    pub decisions: u64,
    /// Simulation ground truth about accepted results. Computed from hidden
    /// answers, so it is not part of the audited log.
    pub truth: SimTruth,
}

/// Soundness of what the run accepted, judged against hidden answers.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct SimTruth {
    /// Problems whose accepted terminal and every accepted prerequisite are correct.
    pub true_solved: usize,
    /// Problems closed as solved whose accepted chain contains a wrong artifact.
    pub false_solved: usize,
    /// Tasks accepted with an incorrect artifact (verifier false positives).
    pub false_accepted_tasks: usize,
    /// Attempts dispatched on obligations whose true success probability is 0.
    pub dead_attempts: usize,
}

#[derive(Clone, Debug)]
enum Planned {
    Crash { gen_units: f64 },
    Timeout,
    Candidate { gen_units: f64, body: serde_json::Value, confidence: Option<f64>, parents: Vec<Digest> },
}

/// A prerequisite's accepted artifact offered to a dependent task's attempt.
#[derive(Clone, Debug)]
pub struct LibraryUse {
    pub entry: LibraryEntry,
    pub task_id: String,
    pub artifact: Digest,
}

/// Artifact body and parents for an external candidate. Without a library
/// the body is `{"source": candidate}` exactly as before (catalog v1/v2).
/// With one, `source` is the composed program the verifier runs (library
/// sources, then the candidate), and `parents` lists the library's accepted
/// artifacts, so the artifact digest commits to every helper it calls.
pub fn candidate_artifact(candidate: &str, library: &[LibraryUse]) -> (serde_json::Value, Vec<Digest>) {
    if library.is_empty() {
        return (json!({ "source": candidate }), vec![]);
    }
    let entries: Vec<LibraryEntry> = library.iter().map(|l| l.entry.clone()).collect();
    let refs: Vec<serde_json::Value> =
        library.iter().map(|l| json!({ "helper": l.entry.name, "task_id": l.task_id, "artifact": l.artifact })).collect();
    let body = json!({ "source": compose_program(&entries, candidate), "candidate": candidate, "library": refs });
    (body, library.iter().map(|l| l.artifact).collect())
}

struct InFlight {
    attempt: Attempt,
    /// Per-task attempt index; keys the outcome and verifier streams.
    k: u32,
    plan: Planned,
    artifact: Option<Digest>,
    /// Receipt and ground-truth correctness, computed when generation ends
    /// and applied when the verification interval elapses.
    pending: Option<(VerifierReceipt, bool)>,
    gen_units: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Phase {
    GenerationDone,
    VerificationDone,
}

struct SimVerifier<'a> {
    truth: &'a BTreeMap<String, TaskTruth>,
    cost: f64,
    seed: u64,
    fnr: f64,
    fpr: f64,
}

fn answer_is_correct(truth: &BTreeMap<String, TaskTruth>, artifact: &Artifact) -> bool {
    artifact.body.get("answer").and_then(|v| v.as_str()) == Some(truth[&artifact.task_id].secret.as_str())
}

impl SimVerifier<'_> {
    /// Ground-truth check, then (if configured) a false-negative or
    /// false-positive flip drawn from a stream keyed by (task, attempt index).
    fn verify(&self, spec: &SealedSpec, artifact: &Artifact, digest: Digest, k: u32) -> VerifierReceipt {
        let correct = artifact.spec_digest == spec.digest() && answer_is_correct(self.truth, artifact);
        let pass = if self.fnr == 0.0 && self.fpr == 0.0 {
            correct
        } else {
            let u = SplitMix64::derive(self.seed, &format!("verify/{}/{k}", artifact.task_id)).next_f64();
            if correct { u >= self.fnr } else { u < self.fpr }
        };
        VerifierReceipt {
            schema_version: RECEIPT_SCHEMA_VERSION.into(),
            spec_digest: spec.digest(),
            artifact_digest: digest,
            verdict: if pass { Verdict::Pass } else { Verdict::Fail },
            trust_class: TrustClass::V2,
            verifier_id: SIM_VERIFIER_ID.into(),
            verifier_version: SIM_VERIFIER_VERSION.into(),
            reason: if pass { "answer matches commitment".into() } else { "answer does not match commitment".into() },
            cost_units: self.cost,
        }
    }
}

struct Sim<'a> {
    cfg: &'a SimConfig,
    campaign: &'a Campaign,
    graph: TaskGraph,
    approaches: Vec<Approach>,
    stats: Vec<TaskStats>,
    problems: Vec<ProblemStats>,
    started_per_task: Vec<u32>,
    ledger: BudgetLedger,
    store: EvidenceStore,
    log: EventLog,
    queue: BinaryHeap<Reverse<(u64, u64, Phase, u64)>>,
    inflight: BTreeMap<u64, InFlight>,
    free_workers: Vec<usize>,
    next_attempt: u64,
    next_seq: u64,
    now: f64,
    stopped: bool,
    policy: Box<dyn Policy>,
    policy_rng: SplitMix64,
    select_nanos: u128,
    decisions: u64,
    /// Ground-truth soundness of each accepted task (None = not accepted).
    sound: Vec<Option<bool>>,
    /// Real worker/verifier service; `None` = simulated backend.
    external: Option<&'a mut ExternalWorker>,
    truth: SimTruth,
}

pub fn run(cfg: &SimConfig) -> Result<RunOutput, SimError> {
    cfg.validate()?;
    let campaign = generate(&cfg.env, cfg.run.seed, cfg.run.budget_units).map_err(SimError::Config)?;
    run_campaign(cfg, &campaign)
}

pub fn run_campaign(cfg: &SimConfig, campaign: &Campaign) -> Result<RunOutput, SimError> {
    run_campaign_with(cfg, campaign, None)
}

/// Run with an optional external worker/verifier service in place of the
/// simulated outcome streams and simulated verifier.
pub fn run_campaign_with(cfg: &SimConfig, campaign: &Campaign, external: Option<&mut ExternalWorker>) -> Result<RunOutput, SimError> {
    let mut sim = Sim::new(cfg, campaign, external)?;
    sim.execute()?;
    Ok(RunOutput {
        policy_name: sim.policy.name(),
        select_nanos: sim.select_nanos,
        decisions: sim.decisions,
        truth: sim.truth,
        log: sim.log,
    })
}

impl<'a> Sim<'a> {
    fn new(cfg: &'a SimConfig, campaign: &'a Campaign, external: Option<&'a mut ExternalWorker>) -> Result<Self, SimError> {
        let graph = TaskGraph::build(campaign.tasks.clone()).map_err(|e| SimError::Config(e.to_string()))?;
        let problem_index: BTreeMap<String, usize> = campaign.specs.iter().enumerate().map(|(i, s)| (s.id().to_owned(), i)).collect();
        let policy = cfg.run.policy.build();
        let oracle = policy.needs_oracle();
        let stats = graph
            .nodes()
            .iter()
            .map(|n| {
                let id = &n.def.task_id;
                let t = &campaign.truth[id];
                TaskStats {
                    problem: problem_index[&n.def.problem_id],
                    prior_hint: campaign.hints[id],
                    oracle: oracle.then(|| OracleInfo { p_success: t.p_success, mean_cost: expected_charge(cfg, t) }),
                    ..TaskStats::default()
                }
            })
            .collect();
        let approaches = graph
            .nodes()
            .iter()
            .enumerate()
            .filter(|(_, n)| n.def.terminal)
            .map(|(i, n)| {
                let mut tasks = vec![];
                let mut stack = vec![i];
                while let Some(j) = stack.pop() {
                    if !tasks.contains(&j) {
                        tasks.push(j);
                        stack.extend(graph.node(j).deps.iter().copied());
                    }
                }
                tasks.sort_unstable();
                Approach { problem: problem_index[&n.def.problem_id], tasks }
            })
            .collect();
        let n = graph.len();
        Ok(Self {
            cfg,
            campaign,
            graph,
            approaches,
            problems: vec![ProblemStats::default(); campaign.specs.len()],
            stats,
            started_per_task: vec![0; n],
            ledger: BudgetLedger::new(cfg.run.budget_units),
            store: EvidenceStore::new(),
            log: EventLog::new(),
            queue: BinaryHeap::new(),
            inflight: BTreeMap::new(),
            free_workers: (0..cfg.run.workers).rev().collect(),
            next_attempt: 0,
            next_seq: 0,
            now: 0.0,
            stopped: false,
            policy,
            policy_rng: SplitMix64::derive(cfg.run.seed, "policy"),
            select_nanos: 0,
            decisions: 0,
            sound: vec![None; n],
            external,
            truth: SimTruth::default(),
        })
    }

    fn execute(&mut self) -> Result<(), SimError> {
        let r = &self.cfg.run;
        self.log.append(Event::RunStarted {
            run_id: format!("{}-{}", self.cfg.name, r.seed),
            config_digest: self.cfg.digest(),
            seed: r.seed,
            policy: self.policy.name(),
            kernel_version: KERNEL_VERSION.into(),
            budget_units: r.budget_units,
            workers: r.workers,
        });
        for s in &self.campaign.specs {
            self.log.append(Event::ProblemRegistered { problem_id: s.id().into(), spec_digest: s.digest() });
        }
        for n in self.graph.nodes() {
            let deps = n.deps.iter().map(|&d| self.graph.node(d).def.task_id.clone()).collect();
            self.log.append(Event::TaskRegistered {
                task_id: n.def.task_id.clone(),
                problem_id: n.def.problem_id.clone(),
                depends_on: deps,
                terminal: n.def.terminal,
            });
        }
        self.dispatch()?;
        while let Some(Reverse((t_bits, _, phase, id))) = self.queue.pop() {
            self.now = f64::from_bits(t_bits);
            match phase {
                Phase::GenerationDone => self.on_generation_done(id)?,
                Phase::VerificationDone => self.on_verification_done(id)?,
            }
            self.dispatch()?;
        }
        if self.ledger.open_reservations() != 0 {
            return Err(SimError::Invariant("reservations left open at end of run".into()));
        }
        self.log.append(Event::RunFinished { at: self.now, committed_units: self.ledger.committed() });
        Ok(())
    }

    fn schedule(&mut self, at: f64, phase: Phase, attempt: u64) {
        debug_assert!(at >= 0.0);
        self.queue.push(Reverse((at.to_bits(), self.next_seq, phase, attempt)));
        self.next_seq += 1;
    }

    fn runnable(&self) -> Vec<usize> {
        let r = &self.cfg.run;
        self.graph
            .eligible()
            .filter(|&t| {
                let s = &self.stats[t];
                !self.problems[s.problem].closed
                    && s.in_flight < r.max_parallel_per_task
                    && self.started_per_task[t] < r.max_attempts_per_task
            })
            .collect()
    }

    fn dispatch(&mut self) -> Result<(), SimError> {
        let reservation = self.cfg.run.attempt_cap_units + self.cfg.run.verify_cost_units;
        while !self.stopped && !self.free_workers.is_empty() {
            let runnable = self.runnable();
            if runnable.is_empty() {
                return Ok(());
            }
            if self.ledger.available() < reservation {
                // Outstanding reservations may be blocking: in-flight attempts
                // usually settle below their worst case and release the rest.
                // Wait for them; stop only when nothing is left to release.
                if self.inflight.is_empty() {
                    self.stopped = true;
                    self.log.append(Event::DispatchStopped { reason: "budget".into(), at: self.now });
                }
                return Ok(());
            }
            let view = SchedView {
                tasks: &self.stats,
                approaches: &self.approaches,
                problems: &self.problems,
                runnable: &runnable,
                total_budget: self.cfg.run.budget_units,
                reservation,
                prior_cost: self.cfg.run.prior_cost,
            };
            let t0 = Instant::now();
            let choice = self.policy.select(&view, &mut self.policy_rng);
            self.select_nanos += t0.elapsed().as_nanos();
            self.decisions += 1;
            let Some(task) = choice else { return Ok(()) };
            if runnable.binary_search(&task).is_err() {
                return Err(SimError::PolicyViolation { policy: self.policy.name(), task });
            }
            self.launch(task, reservation)?;
        }
        Ok(())
    }

    /// The library for an attempt on `task`: for each direct prerequisite,
    /// the source of the artifact the evidence store accepted for it, sorted
    /// by helper name. Nothing else can enter: a prerequisite without an
    /// accepted artifact is an invariant violation (the task would not be
    /// eligible), and the service only ever receives what this returns.
    pub(crate) fn library_for(&self, task: usize) -> Result<Vec<LibraryUse>, SimError> {
        let mut lib = Vec::new();
        for &d in &self.graph.node(task).deps {
            let dep = &self.graph.node(d).def.task_id;
            let missing = |what: &str| SimError::Invariant(format!("prerequisite {dep} of {}: {what}", self.graph.node(task).def.task_id));
            let artifact = self.store.accepted_for(dep).ok_or_else(|| missing("no accepted artifact"))?;
            let stored = self.store.get(&artifact).ok_or_else(|| missing("accepted artifact not stored"))?;
            let source = stored.artifact.body.get("source").and_then(|v| v.as_str()).ok_or_else(|| missing("artifact has no source"))?;
            let name = self.campaign.helpers.get(dep).ok_or_else(|| missing("no helper name"))?;
            lib.push(LibraryUse { entry: LibraryEntry { name: name.clone(), source: source.to_owned() }, task_id: dep.clone(), artifact });
        }
        lib.sort_by(|a, b| a.entry.name.cmp(&b.entry.name));
        Ok(lib)
    }

    fn plan_attempt(&mut self, task: usize, k: u32) -> Result<Planned, SimError> {
        let r = &self.cfg.run;
        let id = self.graph.node(task).def.task_id.clone();
        if self.external.is_some() {
            let library = self.library_for(task)?;
            let entries: Vec<LibraryEntry> = library.iter().map(|l| l.entry.clone()).collect();
            let ext = self.external.as_deref_mut().expect("checked");
            let a = ext.attempt(&self.campaign.truth[&id].name, r.seed, k, &entries)?;
            return Ok(if a.gen_units > r.attempt_cap_units {
                Planned::Timeout
            } else {
                let (body, parents) = candidate_artifact(&a.source, &library);
                Planned::Candidate { gen_units: a.gen_units, body, confidence: None, parents }
            });
        }
        let env = &self.cfg.env;
        let truth = &self.campaign.truth[&id];
        let d = fresh_draws(r.seed, &id, truth.p_success, truth.mean_cost, env.attempt_cost_sd, r.crash_prob, k);
        let success =
            if env.failure_stickiness > 0.0 { sticky_success(r.seed, &id, truth.p_success, env.failure_stickiness, k) } else { d.success };
        let cost = if success { d.base_cost } else { d.base_cost * env.failure_cost_mult };
        let answer = if success { truth.secret.clone() } else { d.wrong };
        let body = if env.distinct_solutions {
            let variant = SplitMix64::derive(r.seed, &format!("variant/{id}/{k}")).next_u64();
            json!({ "answer": answer, "variant": format!("{variant:016x}") })
        } else {
            json!({ "answer": answer })
        };
        Ok(if d.crash {
            Planned::Crash { gen_units: (cost * d.crash_frac).min(r.attempt_cap_units) }
        } else if cost > r.attempt_cap_units {
            Planned::Timeout
        } else {
            Planned::Candidate { gen_units: cost, body, confidence: Some(d.confidence), parents: vec![] }
        })
    }

    fn launch(&mut self, task: usize, reservation: f64) -> Result<(), SimError> {
        let worker = self.free_workers.pop().expect("checked non-empty");
        let attempt_id = self.next_attempt;
        self.next_attempt += 1;
        self.ledger.reserve(attempt_id, reservation).map_err(|e| SimError::Invariant(e.to_string()))?;
        let k = self.started_per_task[task];
        self.started_per_task[task] += 1;
        if self.campaign.truth[&self.graph.node(task).def.task_id].dead {
            self.truth.dead_attempts += 1;
        }
        let plan = self.plan_attempt(task, k)?;
        let gen_units = match plan {
            Planned::Crash { gen_units } | Planned::Candidate { gen_units, .. } => gen_units,
            Planned::Timeout => self.cfg.run.attempt_cap_units,
        };
        let mut attempt = Attempt::lease(attempt_id, task, worker);
        attempt.advance(AttemptState::Running).map_err(|e| SimError::Invariant(e.to_string()))?;
        self.stats[task].in_flight += 1;
        let p = self.stats[task].problem;
        self.problems[p].spent += reservation;
        self.log.append(Event::AttemptDispatched {
            attempt_id,
            task_id: self.graph.node(task).def.task_id.clone(),
            worker,
            at: self.now,
            reserved_units: reservation,
        });
        self.schedule(self.now + gen_units, Phase::GenerationDone, attempt_id);
        self.inflight.insert(attempt_id, InFlight { attempt, k, plan, artifact: None, pending: None, gen_units });
        Ok(())
    }

    fn task_closed(&self, task: usize) -> bool {
        self.graph.node(task).state() != TaskState::Eligible || self.problems[self.stats[task].problem].closed
    }

    fn on_generation_done(&mut self, id: u64) -> Result<(), SimError> {
        let fl = self.inflight.get_mut(&id).expect("scheduled attempt exists");
        let task = fl.attempt.task;
        let gen_units = fl.gen_units;
        let usage = Usage { compute_units: gen_units, cpu_seconds: gen_units, ..Usage::default() };
        let outcome = match fl.plan.clone() {
            Planned::Crash { .. } => {
                fl.attempt.advance(AttemptState::Crashed).map_err(|e| SimError::Invariant(e.to_string()))?;
                AttemptOutcome::Crashed
            }
            Planned::Timeout => {
                fl.attempt.advance(AttemptState::TimedOut).map_err(|e| SimError::Invariant(e.to_string()))?;
                AttemptOutcome::TimedOut
            }
            Planned::Candidate { body, confidence, parents, .. } => {
                fl.attempt.advance(AttemptState::ArtifactSubmitted).map_err(|e| SimError::Invariant(e.to_string()))?;
                let node = self.graph.node(task);
                let spec = &self.campaign.specs[self.stats[task].problem];
                let artifact = Artifact {
                    kind: ArtifactKind::Candidate,
                    spec_digest: spec.digest(),
                    task_id: node.def.task_id.clone(),
                    parents: parents.clone(),
                    body,
                };
                let sub = Submission {
                    attempt_id: id,
                    worker_id: format!("worker-{}", fl.attempt.worker),
                    model: self.external.as_ref().map_or_else(|| "synthetic".into(), |w| w.model_label.clone()),
                    self_reported_confidence: confidence,
                };
                let out = self.store.submit(artifact, sub).map_err(|e| SimError::Invariant(e.to_string()))?;
                fl.artifact = Some(out.digest);
                AttemptOutcome::Artifact { digest: out.digest, duplicate: out.duplicate, parents }
            }
        };
        self.log.append(Event::AttemptFinished { attempt_id: id, at: self.now, outcome: outcome.clone(), usage });

        // Verify only fresh, still-useful candidates. Content that already has a
        // receipt is reused rather than re-verified.
        let needs_verification = match &outcome {
            AttemptOutcome::Artifact { digest, .. } => {
                self.store.get(digest).is_some_and(|s| s.receipts.is_empty()) && !self.task_closed(task)
            }
            _ => false,
        };
        if needs_verification {
            let (receipt, correct) = self.run_verifier(id)?;
            let duration = receipt.cost_units;
            let fl = self.inflight.get_mut(&id).expect("present");
            fl.attempt.advance(AttemptState::Verifying).map_err(|e| SimError::Invariant(e.to_string()))?;
            fl.pending = Some((receipt, correct));
            self.schedule(self.now + duration, Phase::VerificationDone, id);
            return Ok(());
        }
        // Identical content that already carries a non-verifying receipt is
        // rejected by reusing that receipt: the attempt failed and counts as
        // evidence about the task, without paying for verification again.
        let reused_rejection = match &outcome {
            AttemptOutcome::Artifact { digest, .. } => {
                !self.task_closed(task)
                    && self.store.get(digest).is_some_and(|s| !s.receipts.is_empty() && s.status != ClaimStatus::MechanicallyVerified)
            }
            _ => false,
        };
        let informative = matches!(outcome, AttemptOutcome::TimedOut) || reused_rejection;
        let fl = self.inflight.get_mut(&id).expect("present");
        if fl.attempt.state() == AttemptState::ArtifactSubmitted {
            let to = if reused_rejection { AttemptState::Rejected } else { AttemptState::Cancelled };
            fl.attempt.advance(to).map_err(|e| SimError::Invariant(e.to_string()))?;
        }
        self.finish(id, gen_units, informative, false)
    }

    /// Produce the receipt for an attempt's artifact: simulated verifier, or
    /// the external service (real verifier plus extended ground-truth check).
    fn run_verifier(&mut self, id: u64) -> Result<(VerifierReceipt, bool), SimError> {
        let (task, digest, k) = {
            let fl = &self.inflight[&id];
            (fl.attempt.task, fl.artifact.expect("verified attempts have artifacts"), fl.k)
        };
        let spec = &self.campaign.specs[self.stats[task].problem];
        let artifact = self.store.get(&digest).expect("submitted").artifact.clone();
        if let Some(ext) = self.external.as_deref_mut() {
            let source = artifact.body.get("source").and_then(|v| v.as_str()).unwrap_or_default();
            let name = &self.campaign.truth[&artifact.task_id].name;
            return ext.verify(name, source, spec.digest(), digest);
        }
        let env = &self.cfg.env;
        let verifier = SimVerifier {
            truth: &self.campaign.truth,
            cost: self.cfg.run.verify_cost_units,
            seed: self.cfg.run.seed,
            fnr: env.verifier_fnr,
            fpr: env.verifier_fpr,
        };
        let correct = artifact.spec_digest == spec.digest() && answer_is_correct(&self.campaign.truth, &artifact);
        Ok((verifier.verify(spec, &artifact, digest, k), correct))
    }

    fn on_verification_done(&mut self, id: u64) -> Result<(), SimError> {
        let (task, digest, gen_units, (receipt, correct)) = {
            let fl = self.inflight.get_mut(&id).expect("present");
            (
                fl.attempt.task,
                fl.artifact.expect("verified attempts have artifacts"),
                fl.gen_units,
                fl.pending.take().expect("pending receipt"),
            )
        };
        let p = self.stats[task].problem;
        let spec = &self.campaign.specs[p];
        let verify_units = receipt.cost_units;
        let status = self.store.record_receipt(spec, receipt.clone()).map_err(|e| SimError::Invariant(e.to_string()))?;
        self.log.append(Event::VerificationFinished { attempt_id: id, at: self.now, receipt });
        let verified = status == ClaimStatus::MechanicallyVerified;
        let to = if verified { AttemptState::Accepted } else { AttemptState::Rejected };
        self.inflight.get_mut(&id).expect("present").attempt.advance(to).map_err(|e| SimError::Invariant(e.to_string()))?;
        if verified && !self.task_closed(task) {
            self.store.accept(digest).map_err(|e| SimError::Invariant(e.to_string()))?;
            self.graph.mark_verified(task).map_err(|e| SimError::Invariant(e.to_string()))?;
            self.stats[task].verified = true;
            self.problems[p].verified_tasks += 1;
            self.log.append(Event::TaskVerified { task_id: self.graph.node(task).def.task_id.clone(), artifact: digest, at: self.now });
            let sound = correct && self.graph.node(task).deps.iter().all(|&d| self.sound[d] == Some(true));
            self.sound[task] = Some(sound);
            if !correct {
                self.truth.false_accepted_tasks += 1;
            }
            if self.graph.node(task).def.terminal {
                if sound {
                    self.truth.true_solved += 1;
                } else {
                    self.truth.false_solved += 1;
                }
                self.problems[p].solved = true;
                self.problems[p].closed = true;
                self.graph.abandon_problem(spec.id()).map_err(|e| SimError::Invariant(e.to_string()))?;
                self.log.append(Event::ProblemSolved { problem_id: spec.id().into(), at: self.now });
            }
        }
        self.finish(id, gen_units + verify_units, true, verified)
    }

    /// Settle the ledger, update statistics, free the worker.
    fn finish(&mut self, id: u64, charged: f64, informative: bool, success: bool) -> Result<(), SimError> {
        let fl = self.inflight.remove(&id).expect("present");
        debug_assert!(fl.attempt.state().is_final());
        let task = fl.attempt.task;
        let reservation = self.cfg.run.attempt_cap_units + self.cfg.run.verify_cost_units;
        self.ledger.settle(id, charged).map_err(|e| SimError::Invariant(e.to_string()))?;
        let p = self.stats[task].problem;
        self.problems[p].spent += charged - reservation;
        let s = &mut self.stats[task];
        s.in_flight -= 1;
        s.cost_sum += charged;
        s.cost_n += 1;
        if informative {
            s.attempts += 1;
            self.problems[p].attempts += 1;
            if !success {
                s.failures += 1;
            }
        }
        self.free_workers.push(fl.attempt.worker);
        // Exhaust a task once its attempt allowance is used up and nothing is in flight.
        if self.graph.node(task).state() == TaskState::Eligible
            && self.started_per_task[task] >= self.cfg.run.max_attempts_per_task
            && self.stats[task].in_flight == 0
            && !self.problems[p].closed
        {
            self.graph.mark_exhausted(task).map_err(|e| SimError::Invariant(e.to_string()))?;
            self.log.append(Event::TaskExhausted { task_id: self.graph.node(task).def.task_id.clone(), at: self.now });
            let pid = self.campaign.specs[p].id().to_owned();
            if self.graph.problem_dead(&pid) {
                self.problems[p].closed = true;
            }
        }
        Ok(())
    }
}

/// Expected charge of one attempt on a task, as the oracle would know it.
fn expected_charge(cfg: &SimConfig, t: &TaskTruth) -> f64 {
    let mean = t.mean_cost * (t.p_success + (1.0 - t.p_success) * cfg.env.failure_cost_mult);
    mean.min(cfg.run.attempt_cap_units) + cfg.run.verify_cost_units * (1.0 - cfg.run.crash_prob)
}

/// Draws from attempt k's own stream, in a fixed order. How many uniforms
/// each draw consumes depends only on the stream, never on the cost or crash
/// parameters, so the success draw is the same for any parameter values.
struct FreshDraws {
    base_cost: f64,
    crash: bool,
    crash_frac: f64,
    success: bool,
    wrong: String,
    confidence: f64,
}

fn fresh_draws(seed: u64, task_id: &str, p: f64, mean_cost: f64, cost_sd: f64, crash_prob: f64, k: u32) -> FreshDraws {
    let mut rng = SplitMix64::derive(seed, &format!("attempt/{task_id}/{k}"));
    let base_cost = mean_cost * rng.lognormal(-0.5 * cost_sd * cost_sd, cost_sd);
    let crash = rng.bernoulli(crash_prob);
    let crash_frac = rng.next_f64();
    let success = rng.bernoulli(p);
    let wrong = format!("{:016x}", rng.next_u64());
    let confidence = 0.5 + 0.5 * rng.next_f64();
    FreshDraws { base_cost, crash, crash_frac, success, wrong, confidence }
}

/// Success of attempt k when attempt k repeats attempt k-1's outcome with
/// probability `rho` and otherwise draws fresh. Attempt 0 is fresh, so every
/// attempt has marginal success `p` and lag-1 correlation `rho`. Depends only
/// on (seed, task, k), never on scheduling, so policies stay paired.
pub fn sticky_success(seed: u64, task_id: &str, p: f64, rho: f64, k: u32) -> bool {
    let fresh = |j: u32| fresh_draws(seed, task_id, p, 1.0, 0.0, 0.0, j).success;
    let mut outcome = fresh(0);
    for j in 1..=k {
        if !SplitMix64::derive(seed, &format!("stick/{task_id}/{j}")).bernoulli(rho) {
            outcome = fresh(j);
        }
    }
    outcome
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sticky_chain_keeps_marginal_and_sets_lag_one_correlation() {
        let (p, rho, n, len) = (0.3, 0.6, 4000, 12u32);
        let (mut sum, mut xy, mut pairs) = (0.0, 0.0, 0.0);
        for t in 0..n {
            let id = format!("t{t}");
            let xs: Vec<f64> = (0..len).map(|k| sticky_success(9, &id, p, rho, k) as u8 as f64).collect();
            sum += xs.iter().sum::<f64>();
            for w in xs.windows(2) {
                xy += w[0] * w[1];
                pairs += 1.0;
            }
        }
        let mean = sum / (n as f64 * len as f64);
        let corr = (xy / pairs - mean * mean) / (mean * (1.0 - mean));
        assert!((mean - p).abs() < 0.01, "marginal {mean}");
        assert!((corr - rho).abs() < 0.03, "lag-1 correlation {corr}");
    }

    #[test]
    fn zero_stickiness_matches_fresh_draws() {
        for k in 0..50 {
            assert_eq!(sticky_success(3, "x", 0.4, 0.0, k), fresh_draws(3, "x", 0.4, 2.0, 0.3, 0.1, k).success);
        }
    }
}
