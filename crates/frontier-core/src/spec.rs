//! Immutable research problem specifications.
//!
//! A `ProblemSpec` is plain data; a `SealedSpec` is a validated spec bound to
//! its content digest. Every downstream object (tasks, receipts, events)
//! refers to the digest, so a changed goal or acceptance criterion is a
//! different problem rather than a silent edit.

use serde::{Deserialize, Serialize};

use crate::budget::Budget;
use crate::digest::{Digest, DigestError};
use crate::evidence::TrustClass;

pub const SPEC_SCHEMA_VERSION: &str = "0.2";

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProblemCategory {
    FormalProof,
    Algorithm,
    Numerical,
    /// Synthetic environment with known ground truth; never a scientific result.
    Synthetic,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerificationMethod {
    Lean,
    Smt,
    PropertyTests,
    ReferenceImplementation,
    NumericalTolerance,
    /// Ground-truth oracle inside a simulation.
    SimulatedOracle,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InputArtifact {
    pub name: String,
    pub sha256: Digest,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerificationSpec {
    pub method: VerificationMethod,
    pub verifier_id: String,
    pub verifier_version: String,
    /// Hash of the frozen acceptance criterion (hidden tests, theorem
    /// statement, tolerance table). The criterion itself is held by the verifier.
    pub criterion_sha256: Digest,
    pub required_trust: TrustClass,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub source: String,
    pub created_by: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub license: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProblemSpec {
    pub schema_version: String,
    pub problem_id: String,
    pub objective: String,
    pub category: ProblemCategory,
    #[serde(default)]
    pub inputs: Vec<InputArtifact>,
    #[serde(default)]
    pub allowed_tools: Vec<String>,
    pub budget: Budget,
    pub verification: VerificationSpec,
    pub success_criteria: String,
    #[serde(default)]
    pub depends_on: Vec<String>,
    pub provenance: Provenance,
    /// Difficulty estimate where available (0 = trivial, 1 = hardest in corpus).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub difficulty: Option<f64>,
}

#[derive(Debug, thiserror::Error)]
pub enum SpecError {
    #[error("unsupported schema_version {0:?} (expected {SPEC_SCHEMA_VERSION})")]
    SchemaVersion(String),
    #[error("invalid identifier {0:?}: use 1-128 chars of [A-Za-z0-9._-]")]
    BadId(String),
    #[error("field {0} must not be empty")]
    Empty(&'static str),
    #[error("invalid budget: {0}")]
    Budget(String),
    #[error("difficulty must be within [0, 1]")]
    Difficulty,
    #[error("problem {0} depends on itself")]
    SelfDependency(String),
    #[error("digest mismatch: expected {expected}, computed {actual}")]
    DigestMismatch { expected: Digest, actual: Digest },
    #[error(transparent)]
    Digest(#[from] DigestError),
}

pub fn valid_id(s: &str) -> bool {
    !s.is_empty() && s.len() <= 128 && s.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
}

impl ProblemSpec {
    pub fn validate(&self) -> Result<(), SpecError> {
        if self.schema_version != SPEC_SCHEMA_VERSION {
            return Err(SpecError::SchemaVersion(self.schema_version.clone()));
        }
        if !valid_id(&self.problem_id) {
            return Err(SpecError::BadId(self.problem_id.clone()));
        }
        if self.objective.trim().is_empty() {
            return Err(SpecError::Empty("objective"));
        }
        if self.success_criteria.trim().is_empty() {
            return Err(SpecError::Empty("success_criteria"));
        }
        if self.verification.verifier_id.trim().is_empty() {
            return Err(SpecError::Empty("verification.verifier_id"));
        }
        self.budget.validate().map_err(SpecError::Budget)?;
        if let Some(d) = self.difficulty {
            if !(0.0..=1.0).contains(&d) {
                return Err(SpecError::Difficulty);
            }
        }
        for dep in &self.depends_on {
            if !valid_id(dep) {
                return Err(SpecError::BadId(dep.clone()));
            }
            if dep == &self.problem_id {
                return Err(SpecError::SelfDependency(dep.clone()));
            }
        }
        Ok(())
    }
}

/// A validated, digest-bound specification. Fields are private: there is no
/// way to mutate the spec after sealing.
#[derive(Clone, Debug, PartialEq)]
pub struct SealedSpec {
    spec: ProblemSpec,
    digest: Digest,
}

impl SealedSpec {
    pub fn seal(spec: ProblemSpec) -> Result<Self, SpecError> {
        spec.validate()?;
        let digest = Digest::of_canonical(&spec)?;
        Ok(Self { spec, digest })
    }

    /// Seal and check against a digest recorded elsewhere (e.g. a frozen
    /// preregistration manifest).
    pub fn seal_expecting(spec: ProblemSpec, expected: Digest) -> Result<Self, SpecError> {
        let sealed = Self::seal(spec)?;
        if sealed.digest != expected {
            return Err(SpecError::DigestMismatch { expected, actual: sealed.digest });
        }
        Ok(sealed)
    }

    pub fn spec(&self) -> &ProblemSpec {
        &self.spec
    }

    pub fn digest(&self) -> Digest {
        self.digest
    }

    pub fn id(&self) -> &str {
        &self.spec.problem_id
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub fn example_spec(id: &str) -> ProblemSpec {
        ProblemSpec {
            schema_version: SPEC_SCHEMA_VERSION.into(),
            problem_id: id.into(),
            objective: "Return the sorted permutation of an integer list".into(),
            category: ProblemCategory::Algorithm,
            inputs: vec![],
            allowed_tools: vec!["python".into()],
            budget: Budget { compute_units: 100.0, ..Budget::default() },
            verification: VerificationSpec {
                method: VerificationMethod::PropertyTests,
                verifier_id: "property-tests".into(),
                verifier_version: "0.1.0".into(),
                criterion_sha256: Digest::of_bytes(b"hidden tests v1"),
                required_trust: TrustClass::V2,
            },
            success_criteria: "All hidden and property tests pass".into(),
            depends_on: vec![],
            provenance: Provenance { source: "unit-test".into(), created_by: "test".into(), license: None },
            difficulty: Some(0.1),
        }
    }

    #[test]
    fn sealing_binds_digest_to_content() {
        let a = SealedSpec::seal(example_spec("p1")).unwrap();
        let mut changed = example_spec("p1");
        changed.success_criteria = "Visible tests pass".into();
        let b = SealedSpec::seal(changed.clone()).unwrap();
        assert_ne!(a.digest(), b.digest(), "editing acceptance criteria must change identity");
        assert!(SealedSpec::seal_expecting(changed, a.digest()).is_err());
        assert!(SealedSpec::seal_expecting(example_spec("p1"), a.digest()).is_ok());
    }

    #[test]
    fn rejects_invalid_specs() {
        let mut s = example_spec("bad id");
        assert!(matches!(SealedSpec::seal(s.clone()), Err(SpecError::BadId(_))));
        s.problem_id = "ok".into();
        s.budget.compute_units = 0.0;
        assert!(matches!(SealedSpec::seal(s.clone()), Err(SpecError::Budget(_))));
        s.budget.compute_units = 1.0;
        s.depends_on = vec!["ok".into()];
        assert!(matches!(SealedSpec::seal(s), Err(SpecError::SelfDependency(_))));
    }

    #[test]
    fn unknown_fields_are_rejected() {
        let mut v = serde_json::to_value(example_spec("p1")).unwrap();
        v["accept_anything"] = serde_json::Value::Bool(true);
        assert!(serde_json::from_value::<ProblemSpec>(v).is_err());
    }
}
