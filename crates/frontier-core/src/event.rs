//! Append-only, hash-chained event log (JSON Lines).
//!
//! Each record carries `prev` (the previous record's hash) and `hash` =
//! SHA-256 of the canonical encoding of `(seq, prev, event)`. Editing,
//! deleting or reordering any record breaks the chain. The chain gives
//! tamper *evidence*, not authenticity: anyone can recompute it.

use std::io::{BufRead, Write};

use serde::{Deserialize, Serialize};

use crate::budget::Usage;
use crate::digest::Digest;
use crate::evidence::VerifierReceipt;

pub const EVENT_SCHEMA_VERSION: &str = "0.2";

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttemptOutcome {
    /// Worker produced an artifact. `parents` are the accepted artifacts of
    /// the task's prerequisites that the artifact builds on (the library of
    /// a dependent real task); the artifact digest commits to them. Omitted
    /// when empty, so logs without dependencies are unchanged.
    Artifact {
        digest: Digest,
        duplicate: bool,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        parents: Vec<Digest>,
    },
    /// Worker failed for infrastructure reasons; no artifact.
    Crashed,
    /// Attempt hit its compute limit and was killed; no artifact.
    TimedOut,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Event {
    RunStarted {
        run_id: String,
        config_digest: Digest,
        seed: u64,
        policy: String,
        kernel_version: String,
        budget_units: f64,
        workers: usize,
    },
    ProblemRegistered {
        problem_id: String,
        spec_digest: Digest,
    },
    TaskRegistered {
        task_id: String,
        problem_id: String,
        depends_on: Vec<String>,
        terminal: bool,
    },
    AttemptDispatched {
        attempt_id: u64,
        task_id: String,
        worker: usize,
        at: f64,
        reserved_units: f64,
    },
    AttemptFinished {
        attempt_id: u64,
        at: f64,
        outcome: AttemptOutcome,
        usage: Usage,
    },
    VerificationFinished {
        attempt_id: u64,
        at: f64,
        receipt: VerifierReceipt,
    },
    TaskVerified {
        task_id: String,
        artifact: Digest,
        at: f64,
    },
    TaskExhausted {
        task_id: String,
        at: f64,
    },
    ProblemSolved {
        problem_id: String,
        at: f64,
    },
    DispatchStopped {
        reason: String,
        at: f64,
    },
    RunFinished {
        at: f64,
        committed_units: f64,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Record {
    pub schema_version: String,
    pub seq: u64,
    pub prev: Digest,
    pub hash: Digest,
    pub event: Event,
}

fn record_hash(seq: u64, prev: &Digest, event: &Event) -> Digest {
    #[derive(Serialize)]
    struct Preimage<'a> {
        seq: u64,
        prev: &'a Digest,
        event: &'a Event,
    }
    Digest::of_canonical(&Preimage { seq, prev, event }).expect("events are always serialisable")
}

#[derive(Debug, thiserror::Error)]
pub enum LogError {
    #[error("record {seq}: expected sequence number {expected}")]
    Sequence { seq: u64, expected: u64 },
    #[error("record {seq}: prev hash does not match preceding record")]
    BrokenLink { seq: u64 },
    #[error("record {seq}: hash does not match contents")]
    BadHash { seq: u64 },
    #[error("record {seq}: unsupported schema_version {version:?}")]
    Version { seq: u64, version: String },
    #[error("line {line}: {source}")]
    Parse { line: usize, source: serde_json::Error },
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

#[derive(Clone, Debug, Default)]
pub struct EventLog {
    records: Vec<Record>,
}

impl EventLog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn append(&mut self, event: Event) -> &Record {
        let seq = self.records.len() as u64;
        let prev = self.head();
        let hash = record_hash(seq, &prev, &event);
        self.records.push(Record { schema_version: EVENT_SCHEMA_VERSION.into(), seq, prev, hash, event });
        self.records.last().expect("just pushed")
    }

    /// Hash of the last record, or zero for an empty log.
    pub fn head(&self) -> Digest {
        self.records.last().map_or(Digest::ZERO, |r| r.hash)
    }

    pub fn records(&self) -> &[Record] {
        &self.records
    }

    pub fn write_jsonl<W: Write>(&self, mut w: W) -> Result<(), LogError> {
        for r in &self.records {
            serde_json::to_writer(&mut w, r).map_err(std::io::Error::from)?;
            w.write_all(b"\n")?;
        }
        w.flush()?;
        Ok(())
    }

    /// Parse and fully verify a log. Any gap, edit or reordering is an error.
    pub fn read_jsonl<R: BufRead>(r: R) -> Result<Self, LogError> {
        let mut records = Vec::new();
        for (i, line) in r.lines().enumerate() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            let rec: Record = serde_json::from_str(&line).map_err(|source| LogError::Parse { line: i + 1, source })?;
            records.push(rec);
        }
        let log = Self { records };
        log.verify()?;
        Ok(log)
    }

    pub fn verify(&self) -> Result<Digest, LogError> {
        let mut prev = Digest::ZERO;
        for (i, r) in self.records.iter().enumerate() {
            if r.schema_version != EVENT_SCHEMA_VERSION {
                return Err(LogError::Version { seq: r.seq, version: r.schema_version.clone() });
            }
            if r.seq != i as u64 {
                return Err(LogError::Sequence { seq: r.seq, expected: i as u64 });
            }
            if r.prev != prev {
                return Err(LogError::BrokenLink { seq: r.seq });
            }
            if record_hash(r.seq, &r.prev, &r.event) != r.hash {
                return Err(LogError::BadHash { seq: r.seq });
            }
            prev = r.hash;
        }
        Ok(prev)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> EventLog {
        let mut log = EventLog::new();
        log.append(Event::DispatchStopped { reason: "a".into(), at: 1.0 });
        log.append(Event::ProblemSolved { problem_id: "p".into(), at: 2.0 });
        log.append(Event::RunFinished { at: 3.0, committed_units: 4.5 });
        log
    }

    #[test]
    fn roundtrip_preserves_chain() {
        let log = sample();
        let mut buf = Vec::new();
        log.write_jsonl(&mut buf).unwrap();
        let back = EventLog::read_jsonl(buf.as_slice()).unwrap();
        assert_eq!(back.head(), log.head());
        assert_eq!(back.records(), log.records());
    }

    /// Regression: without serde_json's `float_roundtrip`, some f64 values do
    /// not parse back bit-identically and genuine logs fail verification.
    #[test]
    fn arbitrary_floats_roundtrip_exactly() {
        let mut rng = crate::rng::SplitMix64::new(99);
        let mut log = EventLog::new();
        for _ in 0..2000 {
            let at = rng.next_f64() * 1e3 + rng.lognormal(0.0, 3.0);
            log.append(Event::DispatchStopped { reason: String::new(), at });
        }
        let mut buf = Vec::new();
        log.write_jsonl(&mut buf).unwrap();
        assert_eq!(EventLog::read_jsonl(buf.as_slice()).unwrap().head(), log.head());
    }

    #[test]
    fn tampering_is_detected() {
        let mut buf = Vec::new();
        sample().write_jsonl(&mut buf).unwrap();
        let text = String::from_utf8(buf).unwrap();

        let edited = text.replace("\"committed_units\":4.5", "\"committed_units\":1.0");
        assert!(matches!(EventLog::read_jsonl(edited.as_bytes()), Err(LogError::BadHash { seq: 2 })));

        let lines: Vec<&str> = text.lines().collect();
        let dropped = format!("{}\n{}\n", lines[0], lines[2]);
        assert!(matches!(EventLog::read_jsonl(dropped.as_bytes()), Err(LogError::Sequence { .. })));
    }
}
