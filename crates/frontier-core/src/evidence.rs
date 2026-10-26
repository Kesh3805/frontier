//! Content-addressed evidence: artifacts, verifier receipts and claim status.
//!
//! Acceptance rules enforced here:
//! * Only a verifier receipt can promote a claim; a worker's self-reported
//!   confidence is stored but never consulted.
//! * A receipt must reference the exact sealed spec digest and an artifact
//!   already in the store.
//! * A PASS below the spec's required trust class does not verify.
//! * Conflicting receipts mark the claim `Contested`; nothing is silently
//!   overwritten.
//! * At most one artifact is accepted per task (exactly-once acceptance).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::digest::{Digest, DigestError};
use crate::spec::SealedSpec;

/// Strength of the checking behind a result (see docs/architecture/evidence.md).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum TrustClass {
    /// Narrative claim only.
    V0,
    /// Tool-checked locally; checker/spec equivalence not audited.
    V1,
    /// Independently re-run by an isolated verifier against a frozen spec.
    V2,
    /// Expert-reviewed independent reproduction.
    V3,
    /// Accepted by the field.
    V4,
}

/// Epistemic status of a claim. These are deliberately distinct levels.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimStatus {
    GeneratedHypothesis,
    PlausibleCandidate,
    Rejected,
    Contested,
    MechanicallyVerified,
    EmpiricallyReproduced,
    IndependentlyReviewed,
    ScientificallyAccepted,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    Hypothesis,
    Candidate,
    Proof,
    Code,
    SimulationOutput,
    Counterexample,
}

/// The content-addressed part of an artifact. Who produced it is recorded
/// separately so that identical content from two workers deduplicates.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub kind: ArtifactKind,
    pub spec_digest: Digest,
    pub task_id: String,
    #[serde(default)]
    pub parents: Vec<Digest>,
    pub body: serde_json::Value,
}

impl Artifact {
    pub fn digest(&self) -> Result<Digest, DigestError> {
        Digest::of_canonical(self)
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Submission {
    pub attempt_id: u64,
    pub worker_id: String,
    pub model: String,
    /// Self-reported confidence. Recorded for calibration analysis only.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub self_reported_confidence: Option<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Verdict {
    Pass,
    Fail,
    Inconclusive,
    ReviewRequired,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerifierReceipt {
    pub schema_version: String,
    pub spec_digest: Digest,
    pub artifact_digest: Digest,
    pub verdict: Verdict,
    pub trust_class: TrustClass,
    pub verifier_id: String,
    pub verifier_version: String,
    pub reason: String,
    pub cost_units: f64,
}

pub const RECEIPT_SCHEMA_VERSION: &str = "0.2";

#[derive(Debug, PartialEq, thiserror::Error)]
pub enum EvidenceError {
    #[error("receipt is for spec {receipt}, expected {expected}")]
    SpecMismatch { receipt: Digest, expected: Digest },
    #[error("receipt references unknown artifact {0}")]
    UnknownArtifact(Digest),
    #[error("artifact belongs to spec {artifact}, not {expected}")]
    ArtifactSpecMismatch { artifact: Digest, expected: Digest },
    #[error("receipt from verifier {got:?}, spec requires {want:?}")]
    WrongVerifier { got: String, want: String },
    #[error("task {task} already has accepted artifact {existing}")]
    AlreadyAccepted { task: String, existing: Digest },
    #[error("artifact {0} is not mechanically verified")]
    NotVerified(Digest),
    #[error("artifact encoding: {0}")]
    Encoding(String),
}

#[derive(Clone, Debug)]
pub struct StoredArtifact {
    pub artifact: Artifact,
    pub submissions: Vec<Submission>,
    pub status: ClaimStatus,
    pub receipts: Vec<VerifierReceipt>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SubmitOutcome {
    pub digest: Digest,
    /// True if identical content was already in the store.
    pub duplicate: bool,
}

#[derive(Clone, Debug, Default)]
pub struct EvidenceStore {
    artifacts: BTreeMap<Digest, StoredArtifact>,
    accepted: BTreeMap<String, Digest>,
}

impl EvidenceStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn submit(&mut self, artifact: Artifact, submission: Submission) -> Result<SubmitOutcome, EvidenceError> {
        let digest = artifact.digest().map_err(|e| EvidenceError::Encoding(e.to_string()))?;
        if let Some(existing) = self.artifacts.get_mut(&digest) {
            existing.submissions.push(submission);
            return Ok(SubmitOutcome { digest, duplicate: true });
        }
        let status = match artifact.kind {
            ArtifactKind::Hypothesis => ClaimStatus::GeneratedHypothesis,
            _ => ClaimStatus::PlausibleCandidate,
        };
        self.artifacts.insert(digest, StoredArtifact { artifact, submissions: vec![submission], status, receipts: vec![] });
        Ok(SubmitOutcome { digest, duplicate: false })
    }

    pub fn get(&self, d: &Digest) -> Option<&StoredArtifact> {
        self.artifacts.get(d)
    }

    pub fn len(&self) -> usize {
        self.artifacts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.artifacts.is_empty()
    }

    /// Apply a verifier receipt and return the resulting claim status.
    pub fn record_receipt(&mut self, spec: &SealedSpec, receipt: VerifierReceipt) -> Result<ClaimStatus, EvidenceError> {
        if receipt.spec_digest != spec.digest() {
            return Err(EvidenceError::SpecMismatch { receipt: receipt.spec_digest, expected: spec.digest() });
        }
        let want = &spec.spec().verification.verifier_id;
        if &receipt.verifier_id != want {
            return Err(EvidenceError::WrongVerifier { got: receipt.verifier_id.clone(), want: want.clone() });
        }
        let stored = self.artifacts.get_mut(&receipt.artifact_digest).ok_or(EvidenceError::UnknownArtifact(receipt.artifact_digest))?;
        if stored.artifact.spec_digest != spec.digest() {
            return Err(EvidenceError::ArtifactSpecMismatch { artifact: stored.artifact.spec_digest, expected: spec.digest() });
        }
        let required = spec.spec().verification.required_trust;
        let verifies = receipt.verdict == Verdict::Pass && receipt.trust_class >= required;
        let refutes = receipt.verdict == Verdict::Fail;
        let prior = stored.status;
        stored.status = match prior {
            ClaimStatus::Contested => ClaimStatus::Contested,
            ClaimStatus::MechanicallyVerified if refutes => ClaimStatus::Contested,
            ClaimStatus::Rejected if verifies => ClaimStatus::Contested,
            ClaimStatus::GeneratedHypothesis | ClaimStatus::PlausibleCandidate if verifies => ClaimStatus::MechanicallyVerified,
            ClaimStatus::GeneratedHypothesis | ClaimStatus::PlausibleCandidate if refutes => ClaimStatus::Rejected,
            other => other,
        };
        stored.receipts.push(receipt);
        Ok(stored.status)
    }

    /// Accept a verified artifact as the solution of its task, exactly once.
    pub fn accept(&mut self, digest: Digest) -> Result<(), EvidenceError> {
        let stored = self.artifacts.get(&digest).ok_or(EvidenceError::UnknownArtifact(digest))?;
        if stored.status != ClaimStatus::MechanicallyVerified {
            return Err(EvidenceError::NotVerified(digest));
        }
        let task = stored.artifact.task_id.clone();
        if let Some(existing) = self.accepted.get(&task) {
            return Err(EvidenceError::AlreadyAccepted { task, existing: *existing });
        }
        self.accepted.insert(task, digest);
        Ok(())
    }

    pub fn accepted_for(&self, task_id: &str) -> Option<Digest> {
        self.accepted.get(task_id).copied()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::tests::example_spec;
    use serde_json::json;

    fn setup() -> (SealedSpec, EvidenceStore, Artifact) {
        let spec = SealedSpec::seal(example_spec("p1")).unwrap();
        let art = Artifact {
            kind: ArtifactKind::Code,
            spec_digest: spec.digest(),
            task_id: "t1".into(),
            parents: vec![],
            body: json!({"source": "def f(x): return sorted(x)"}),
        };
        (spec, EvidenceStore::new(), art)
    }

    fn sub(attempt: u64, conf: f64) -> Submission {
        Submission { attempt_id: attempt, worker_id: "w".into(), model: "m".into(), self_reported_confidence: Some(conf) }
    }

    fn receipt(spec: &SealedSpec, d: Digest, verdict: Verdict, trust: TrustClass) -> VerifierReceipt {
        VerifierReceipt {
            schema_version: RECEIPT_SCHEMA_VERSION.into(),
            spec_digest: spec.digest(),
            artifact_digest: d,
            verdict,
            trust_class: trust,
            verifier_id: "property-tests".into(),
            verifier_version: "0.1.0".into(),
            reason: String::new(),
            cost_units: 1.0,
        }
    }

    #[test]
    fn confidence_never_verifies() {
        let (_spec, mut store, art) = setup();
        let d = store.submit(art, sub(1, 1.0)).unwrap().digest;
        assert_eq!(store.get(&d).unwrap().status, ClaimStatus::PlausibleCandidate);
        assert_eq!(store.accept(d), Err(EvidenceError::NotVerified(d)));
    }

    #[test]
    fn duplicates_are_detected_regardless_of_producer() {
        let (_spec, mut store, art) = setup();
        let a = store.submit(art.clone(), sub(1, 0.2)).unwrap();
        let b = store.submit(art, sub(2, 0.9)).unwrap();
        assert!(!a.duplicate && b.duplicate && a.digest == b.digest);
        assert_eq!(store.get(&a.digest).unwrap().submissions.len(), 2);
    }

    #[test]
    fn receipts_must_match_spec_verifier_and_trust() {
        let (spec, mut store, art) = setup();
        let d = store.submit(art, sub(1, 0.5)).unwrap().digest;
        let other = SealedSpec::seal(example_spec("p2")).unwrap();
        assert!(matches!(
            store.record_receipt(&other, receipt(&spec, d, Verdict::Pass, TrustClass::V2)),
            Err(EvidenceError::SpecMismatch { .. })
        ));
        let mut wrong = receipt(&spec, d, Verdict::Pass, TrustClass::V2);
        wrong.verifier_id = "self-assessment".into();
        assert!(matches!(store.record_receipt(&spec, wrong), Err(EvidenceError::WrongVerifier { .. })));
        assert_eq!(store.record_receipt(&spec, receipt(&spec, d, Verdict::Pass, TrustClass::V1)).unwrap(), ClaimStatus::PlausibleCandidate);
        assert_eq!(
            store.record_receipt(&spec, receipt(&spec, d, Verdict::Pass, TrustClass::V2)).unwrap(),
            ClaimStatus::MechanicallyVerified
        );
        store.accept(d).unwrap();
        assert!(matches!(store.accept(d), Err(EvidenceError::AlreadyAccepted { .. })));
    }

    #[test]
    fn contradictions_are_preserved() {
        let (spec, mut store, art) = setup();
        let d = store.submit(art, sub(1, 0.5)).unwrap().digest;
        store.record_receipt(&spec, receipt(&spec, d, Verdict::Pass, TrustClass::V2)).unwrap();
        assert_eq!(store.record_receipt(&spec, receipt(&spec, d, Verdict::Fail, TrustClass::V2)).unwrap(), ClaimStatus::Contested);
        assert_eq!(store.record_receipt(&spec, receipt(&spec, d, Verdict::Pass, TrustClass::V2)).unwrap(), ClaimStatus::Contested);
        assert_eq!(store.get(&d).unwrap().receipts.len(), 3);
    }
}
