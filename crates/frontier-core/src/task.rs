//! Research tasks and attempt lifecycles.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskKind {
    Hypothesis,
    Subproblem,
    ProofObligation,
    Experiment,
    /// Final obligation of one alternative approach; verifying it solves the problem.
    Goal,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TaskDef {
    pub task_id: String,
    pub problem_id: String,
    pub kind: TaskKind,
    #[serde(default)]
    pub depends_on: Vec<String>,
    /// Normalised description of the obligation. Two tasks of one problem with
    /// the same signature are the same obligation and are merged (dedup).
    pub signature: String,
    /// Verifying a terminal task solves the problem.
    pub terminal: bool,
}

/// Logical task state in the research graph.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    /// Waiting on unverified dependencies.
    Pending,
    /// All dependencies verified; attempts may be dispatched.
    Eligible,
    /// A verified artifact has been accepted for this task.
    Verified,
    /// Attempt cap reached without a verified artifact.
    Exhausted,
    /// No longer useful: problem solved elsewhere or a prerequisite failed.
    Abandoned,
}

impl TaskState {
    pub fn is_final(self) -> bool {
        matches!(self, TaskState::Verified | TaskState::Exhausted | TaskState::Abandoned)
    }

    pub fn can_transition_to(self, to: TaskState) -> bool {
        use TaskState::*;
        matches!(
            (self, to),
            (Pending, Eligible) | (Pending, Abandoned) | (Eligible, Verified) | (Eligible, Exhausted) | (Eligible, Abandoned)
        )
    }
}

/// Lifecycle of one execution attempt of a task by a worker.
///
/// `leased → running → artifact_submitted → verifying → accepted|rejected|inconclusive`,
/// with `crashed`, `timed_out`, `cancelled` and `quarantined` as exits.
/// Retries are new attempts; an attempt never re-enters `running`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttemptState {
    Leased,
    Running,
    ArtifactSubmitted,
    Verifying,
    Accepted,
    Rejected,
    Inconclusive,
    Crashed,
    TimedOut,
    Cancelled,
    Quarantined,
}

impl AttemptState {
    pub fn is_final(self) -> bool {
        use AttemptState::*;
        matches!(self, Accepted | Rejected | Inconclusive | Crashed | TimedOut | Cancelled | Quarantined)
    }

    pub fn can_transition_to(self, to: AttemptState) -> bool {
        use AttemptState::*;
        match self {
            Leased => matches!(to, Running | Cancelled),
            Running => matches!(to, ArtifactSubmitted | Crashed | TimedOut | Cancelled),
            // Rejected directly: identical content already holds a failing receipt.
            ArtifactSubmitted => matches!(to, Verifying | Rejected | Cancelled | Quarantined),
            Verifying => matches!(to, Accepted | Rejected | Inconclusive | Quarantined),
            _ => false,
        }
    }
}

#[derive(Debug, PartialEq, thiserror::Error)]
#[error("illegal transition {from:?} -> {to:?}")]
pub struct IllegalTransition<S: std::fmt::Debug> {
    pub from: S,
    pub to: S,
}

/// An attempt whose state can only move along legal edges.
#[derive(Clone, Debug)]
pub struct Attempt {
    pub attempt_id: u64,
    pub task: usize,
    pub worker: usize,
    state: AttemptState,
}

impl Attempt {
    pub fn lease(attempt_id: u64, task: usize, worker: usize) -> Self {
        Self { attempt_id, task, worker, state: AttemptState::Leased }
    }

    pub fn state(&self) -> AttemptState {
        self.state
    }

    pub fn advance(&mut self, to: AttemptState) -> Result<(), IllegalTransition<AttemptState>> {
        if self.state.can_transition_to(to) {
            self.state = to;
            Ok(())
        } else {
            Err(IllegalTransition { from: self.state, to })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use AttemptState::*;

    #[test]
    fn happy_path_and_illegal_edges() {
        let mut a = Attempt::lease(1, 0, 0);
        for s in [Running, ArtifactSubmitted, Verifying, Accepted] {
            a.advance(s).unwrap();
        }
        assert!(a.state().is_final());
        assert!(a.advance(Running).is_err(), "final attempts cannot be revived");

        let mut b = Attempt::lease(2, 0, 0);
        assert!(b.advance(Accepted).is_err(), "cannot accept without verification");
        b.advance(Running).unwrap();
        assert!(b.advance(Verifying).is_err(), "cannot verify without an artifact");
        b.advance(Crashed).unwrap();
    }

    #[test]
    fn every_final_state_is_absorbing() {
        let all =
            [Leased, Running, ArtifactSubmitted, Verifying, Accepted, Rejected, Inconclusive, Crashed, TimedOut, Cancelled, Quarantined];
        for from in all.into_iter().filter(|s| s.is_final()) {
            for to in all {
                assert!(!from.can_transition_to(to), "{from:?} -> {to:?}");
            }
        }
        let task_states = [TaskState::Pending, TaskState::Eligible, TaskState::Verified, TaskState::Exhausted, TaskState::Abandoned];
        for from in task_states.into_iter().filter(|s| s.is_final()) {
            for to in task_states {
                assert!(!from.can_transition_to(to), "{from:?} -> {to:?}");
            }
        }
    }
}
