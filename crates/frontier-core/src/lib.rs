//! FRONTIER research kernel: typed problems, tasks, budgets, evidence and an
//! append-only event log. No I/O beyond JSONL (de)serialisation; no clocks.

pub mod budget;
pub mod dag;
pub mod detmath;
pub mod digest;
pub mod event;
pub mod evidence;
pub mod rng;
pub mod spec;
pub mod task;

pub use budget::{Budget, BudgetLedger, LedgerError, Usage};
pub use dag::{GraphError, TaskGraph, TaskIdx};
pub use digest::Digest;
pub use event::{AttemptOutcome, Event, EventLog, Record};
pub use evidence::{Artifact, ArtifactKind, ClaimStatus, EvidenceStore, Submission, TrustClass, Verdict, VerifierReceipt};
pub use rng::SplitMix64;
pub use spec::{ProblemSpec, SealedSpec};
pub use task::{Attempt, AttemptState, TaskDef, TaskKind, TaskState};

pub const KERNEL_VERSION: &str = env!("CARGO_PKG_VERSION");
