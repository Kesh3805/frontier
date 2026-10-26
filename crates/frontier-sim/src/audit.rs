//! Recompute run metrics from the event log alone and check integrity.
//!
//! The summary of a run is defined as the output of [`summarize`] on its
//! log. Nothing the runner holds in memory is trusted for reporting.

use std::collections::{BTreeMap, BTreeSet};

use frontier_core::{AttemptOutcome, Digest, Event, EventLog, Verdict};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RunSummary {
    pub run_id: String,
    pub policy: String,
    pub seed: u64,
    pub config_digest: Digest,
    pub log_head: Digest,
    pub workers: usize,
    pub budget_units: f64,
    pub problems: usize,
    pub solved: usize,
    pub committed_units: f64,
    pub generation_units: f64,
    pub verification_units: f64,
    /// Charges for attempts whose candidate was not verified because the
    /// task was already closed or the content was a duplicate.
    pub wasted_units: f64,
    pub crash_units: f64,
    pub timeout_units: f64,
    pub attempts: u64,
    pub crashes: u64,
    pub timeouts: u64,
    pub rejected: u64,
    pub accepted: u64,
    pub duplicates: u64,
    pub unverified_candidates: u64,
    pub time_to_first_solve: Option<f64>,
    pub makespan: f64,
    pub solve_times: Vec<f64>,
    pub busy_worker_seconds: f64,
    pub utilization: f64,
    pub units_per_solved: Option<f64>,
}

#[derive(Debug, thiserror::Error)]
pub enum AuditError {
    #[error("log chain invalid: {0}")]
    Chain(#[from] frontier_core::event::LogError),
    #[error("log does not start with run_started")]
    NoStart,
    #[error("log does not end with run_finished")]
    NoFinish,
    #[error("attempt {0} referenced before dispatch")]
    UnknownAttempt(u64),
    #[error("committed units {logged} in run_finished, {recomputed} recomputed from charges")]
    ChargeMismatch { logged: f64, recomputed: f64 },
    #[error("committed {committed} exceeds budget {budget}")]
    OverBudget { committed: f64, budget: f64 },
    #[error("task {0} verified without a preceding PASS receipt for its artifact")]
    UnsupportedVerification(String),
    #[error("problem {0} solved more than once")]
    DoubleSolve(String),
    #[error("problem {0} solved without a verified terminal task")]
    UnsupportedSolve(String),
}

pub fn summarize(log: &EventLog) -> Result<RunSummary, AuditError> {
    let head = log.verify()?;
    let recs = log.records();
    let Some(Event::RunStarted { run_id, config_digest, seed, policy, budget_units, workers, .. }) = recs.first().map(|r| &r.event) else {
        return Err(AuditError::NoStart);
    };
    let Some(Event::RunFinished { at: end, committed_units }) = recs.last().map(|r| &r.event) else {
        return Err(AuditError::NoFinish);
    };

    let mut s = RunSummary {
        run_id: run_id.clone(),
        policy: policy.clone(),
        seed: *seed,
        config_digest: *config_digest,
        log_head: head,
        workers: *workers,
        budget_units: *budget_units,
        problems: 0,
        solved: 0,
        committed_units: 0.0,
        generation_units: 0.0,
        verification_units: 0.0,
        wasted_units: 0.0,
        crash_units: 0.0,
        timeout_units: 0.0,
        attempts: 0,
        crashes: 0,
        timeouts: 0,
        rejected: 0,
        accepted: 0,
        duplicates: 0,
        unverified_candidates: 0,
        time_to_first_solve: None,
        makespan: *end,
        solve_times: vec![],
        busy_worker_seconds: 0.0,
        utilization: 0.0,
        units_per_solved: None,
    };

    let mut start: BTreeMap<u64, f64> = BTreeMap::new();
    let mut task_of: BTreeMap<u64, String> = BTreeMap::new();
    let mut pending_candidate: BTreeMap<u64, (f64, f64)> = BTreeMap::new(); // gen units, finish time
    let mut passed: BTreeSet<(Digest, String)> = BTreeSet::new();
    let mut terminal: BTreeMap<String, (String, bool)> = BTreeMap::new();
    let mut verified_tasks: BTreeSet<String> = BTreeSet::new();
    let mut solved: BTreeSet<String> = BTreeSet::new();

    for r in recs {
        match &r.event {
            Event::ProblemRegistered { .. } => s.problems += 1,
            Event::TaskRegistered { task_id, problem_id, terminal: t, .. } => {
                terminal.insert(task_id.clone(), (problem_id.clone(), *t));
            }
            Event::AttemptDispatched { attempt_id, task_id, at, .. } => {
                start.insert(*attempt_id, *at);
                task_of.insert(*attempt_id, task_id.clone());
                s.attempts += 1;
            }
            Event::AttemptFinished { attempt_id, at, outcome, usage } => {
                let t0 = *start.get(attempt_id).ok_or(AuditError::UnknownAttempt(*attempt_id))?;
                let u = usage.compute_units;
                s.generation_units += u;
                match outcome {
                    AttemptOutcome::Crashed => {
                        s.crashes += 1;
                        s.crash_units += u;
                        s.busy_worker_seconds += at - t0;
                    }
                    AttemptOutcome::TimedOut => {
                        s.timeouts += 1;
                        s.timeout_units += u;
                        s.busy_worker_seconds += at - t0;
                    }
                    AttemptOutcome::Artifact { duplicate, .. } => {
                        if *duplicate {
                            s.duplicates += 1;
                        }
                        pending_candidate.insert(*attempt_id, (u, *at));
                    }
                }
            }
            Event::VerificationFinished { attempt_id, at, receipt } => {
                let t0 = *start.get(attempt_id).ok_or(AuditError::UnknownAttempt(*attempt_id))?;
                pending_candidate.remove(attempt_id).ok_or(AuditError::UnknownAttempt(*attempt_id))?;
                s.verification_units += receipt.cost_units;
                s.busy_worker_seconds += at - t0;
                if receipt.verdict == Verdict::Pass {
                    s.accepted += 1;
                    passed.insert((receipt.artifact_digest, task_of[attempt_id].clone()));
                } else {
                    s.rejected += 1;
                }
            }
            Event::TaskVerified { task_id, artifact, .. } => {
                if !passed.contains(&(*artifact, task_id.clone())) {
                    return Err(AuditError::UnsupportedVerification(task_id.clone()));
                }
                verified_tasks.insert(task_id.clone());
            }
            Event::ProblemSolved { problem_id, at } => {
                if !solved.insert(problem_id.clone()) {
                    return Err(AuditError::DoubleSolve(problem_id.clone()));
                }
                let supported = terminal.iter().any(|(t, (p, term))| *term && p == problem_id && verified_tasks.contains(t));
                if !supported {
                    return Err(AuditError::UnsupportedSolve(problem_id.clone()));
                }
                s.solve_times.push(*at);
            }
            _ => {}
        }
    }
    // Candidates that were never verified: duplicates of verified content or
    // results for tasks that closed while the attempt was running.
    for (id, (u, at)) in &pending_candidate {
        s.unverified_candidates += 1;
        s.wasted_units += u;
        s.busy_worker_seconds += at - start[id];
    }

    s.committed_units = s.generation_units + s.verification_units;
    if (s.committed_units - committed_units).abs() > 1e-6 * committed_units.max(1.0) {
        return Err(AuditError::ChargeMismatch { logged: *committed_units, recomputed: s.committed_units });
    }
    if s.committed_units > s.budget_units * (1.0 + 1e-9) {
        return Err(AuditError::OverBudget { committed: s.committed_units, budget: s.budget_units });
    }
    s.solved = solved.len();
    s.solve_times.sort_by(f64::total_cmp);
    s.time_to_first_solve = s.solve_times.first().copied();
    s.utilization = if s.makespan > 0.0 { s.busy_worker_seconds / (s.workers as f64 * s.makespan) } else { 0.0 };
    s.units_per_solved = (s.solved > 0).then(|| s.committed_units / s.solved as f64);
    Ok(s)
}
