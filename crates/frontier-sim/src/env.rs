//! Synthetic research environment with known ground truth.
//!
//! Each problem has several alternative approaches. An approach is a chain of
//! obligations ending in a terminal goal; approaches of one problem may share
//! their first obligation (a common lemma), which the task graph deduplicates.
//! Every obligation has a hidden per-attempt success probability and a mean
//! attempt cost. Policies never see these; they see only an a-priori hint
//! with configurable noise.
//!
//! This environment is a model of research attempts, not a measurement of
//! them. Its parameter regimes must be calibrated against real attempt data
//! before results are read as statements about LLM workers.

use std::collections::BTreeMap;

use frontier_core::evidence::TrustClass;
use frontier_core::spec::{ProblemCategory, Provenance, SPEC_SCHEMA_VERSION, VerificationMethod, VerificationSpec};
use frontier_core::{Budget, Digest, ProblemSpec, SealedSpec, SplitMix64, TaskDef, TaskKind};
use serde::{Deserialize, Serialize};

pub const SIM_VERIFIER_ID: &str = "sim-oracle";
pub const SIM_VERIFIER_VERSION: &str = "0.1.0";

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EnvConfig {
    pub problems: usize,
    pub approaches_min: u32,
    pub approaches_max: u32,
    /// Obligations per approach, including the terminal goal.
    pub chain_min: u32,
    pub chain_max: u32,
    /// Probability that approach j > 0 reuses approach 0's first obligation.
    pub shared_lemma_prob: f64,
    /// Fraction of obligations that can never succeed.
    pub dead_fraction: f64,
    /// Beta(alpha, beta) per-attempt success probability of live obligations.
    pub p_alpha: f64,
    pub p_beta: f64,
    /// Per-obligation mean attempt cost ~ LogNormal(cost_log_mean, cost_log_sd).
    pub cost_log_mean: f64,
    pub cost_log_sd: f64,
    /// Attempt-to-attempt cost variation (log-sd, mean-preserving).
    pub attempt_cost_sd: f64,
    /// Cost multiplier for unsuccessful attempts (failed reasoning tends to
    /// run longer; 2.2-2.5x on MATH per Su et al., arXiv 2505.00127, Table 1).
    pub failure_cost_mult: f64,
    /// Noise of the prior hint in logit space; dead obligations get a hint
    /// drawn as if they were live.
    pub hint_noise: f64,
    /// Lag-1 correlation of attempt outcomes on one obligation: attempt k
    /// repeats attempt k-1's outcome with this probability, otherwise draws
    /// fresh. The per-attempt marginal stays p. 0 = i.i.d. attempts.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub failure_stickiness: f64,
    /// Probability that the verifier rejects a correct artifact.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub verifier_fnr: f64,
    /// Probability that the verifier accepts an incorrect artifact.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub verifier_fpr: f64,
    /// Each attempt yields distinct artifact content even when correct
    /// (different proofs or programs for the same obligation). When false,
    /// correct answers are canonical and deduplicate.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub distinct_solutions: bool,
    /// Probability that the hint predictor recognises a dead obligation and
    /// reports a near-zero success estimate (logit(0.001) plus the usual
    /// noise). Undetected dead obligations keep a live-looking hint. Drawn
    /// from a separate stream, so the campaign's ground truth and live hints
    /// are identical across values. 0 = dead obligations always look live.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub dead_hint_detection: f64,
}

fn is_zero(x: &f64) -> bool {
    *x == 0.0
}

impl EnvConfig {
    pub fn validate(&self) -> Result<(), String> {
        let prob = |x: f64| (0.0..=1.0).contains(&x);
        if self.problems == 0 {
            return Err("problems must be > 0".into());
        }
        if self.approaches_min == 0 || self.approaches_min > self.approaches_max {
            return Err("need 1 <= approaches_min <= approaches_max".into());
        }
        if self.chain_min == 0 || self.chain_min > self.chain_max {
            return Err("need 1 <= chain_min <= chain_max".into());
        }
        if !prob(self.shared_lemma_prob) || !prob(self.dead_fraction) {
            return Err("probabilities must lie in [0, 1]".into());
        }
        if self.p_alpha <= 0.0 || self.p_beta <= 0.0 {
            return Err("p_alpha and p_beta must be > 0".into());
        }
        if !(self.failure_cost_mult.is_finite() && self.failure_cost_mult >= 1.0) {
            return Err("failure_cost_mult must be >= 1".into());
        }
        if !(0.0..1.0).contains(&self.failure_stickiness) {
            return Err("failure_stickiness must lie in [0, 1)".into());
        }
        if !prob(self.dead_hint_detection) {
            return Err("dead_hint_detection must lie in [0, 1]".into());
        }
        if !prob(self.verifier_fnr) || !prob(self.verifier_fpr) {
            return Err("verifier error rates must lie in [0, 1]".into());
        }
        if self.cost_log_sd < 0.0 || self.attempt_cost_sd < 0.0 || self.hint_noise < 0.0 {
            return Err("standard deviations must be >= 0".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct TaskTruth {
    /// Task name understood by the worker backend (equal to the id in simulation).
    pub name: String,
    /// True when no attempt can ever succeed (ground truth, never shown to policies).
    pub dead: bool,
    pub p_success: f64,
    pub mean_cost: f64,
    /// The answer a correct attempt produces; held only by the verifier.
    pub secret: String,
}

#[derive(Clone, Debug)]
pub struct Campaign {
    pub specs: Vec<SealedSpec>,
    pub tasks: Vec<TaskDef>,
    /// Keyed by task id (aliases of merged tasks map to the same truth).
    pub truth: BTreeMap<String, TaskTruth>,
    pub hints: BTreeMap<String, f64>,
}

fn logit(p: f64) -> f64 {
    let p = p.clamp(1e-6, 1.0 - 1e-6);
    frontier_core::detmath::ln(p / (1.0 - p))
}

fn sigmoid(x: f64) -> f64 {
    1.0 / (1.0 + frontier_core::detmath::exp(-x))
}

fn between(rng: &mut SplitMix64, lo: u32, hi: u32) -> u32 {
    lo + rng.below((hi - lo + 1) as u64) as u32
}

pub fn generate(cfg: &EnvConfig, seed: u64, budget_hint: f64) -> Result<Campaign, String> {
    cfg.validate()?;
    let mut rng = SplitMix64::derive(seed, "env");
    let mut specs = Vec::new();
    let mut tasks = Vec::new();
    let mut truth_by_sig: BTreeMap<(String, String), TaskTruth> = BTreeMap::new();
    let mut hint_by_sig: BTreeMap<(String, String), f64> = BTreeMap::new();
    let mut truth = BTreeMap::new();
    let mut hints = BTreeMap::new();

    for pi in 0..cfg.problems {
        let pid = format!("P{pi:04}");
        let n_app = between(&mut rng, cfg.approaches_min, cfg.approaches_max);
        let mut first_sig_of_a0 = None;
        let mut secrets = Vec::new();
        for a in 0..n_app {
            let len = between(&mut rng, cfg.chain_min, cfg.chain_max);
            let mut prev: Option<String> = None;
            for k in 0..len {
                let terminal = k + 1 == len;
                let mut sig = format!("{pid}/A{a}/O{k}");
                if k == 0 && !terminal {
                    match &first_sig_of_a0 {
                        None => first_sig_of_a0 = Some(sig.clone()),
                        Some(s) if rng.bernoulli(cfg.shared_lemma_prob) => sig = s.clone(),
                        Some(_) => {}
                    }
                }
                let task_id = format!("{pid}.A{a}.O{k}");
                let key = (pid.clone(), sig.clone());
                if !truth_by_sig.contains_key(&key) {
                    let dead = rng.bernoulli(cfg.dead_fraction);
                    let live_p = rng.beta(cfg.p_alpha, cfg.p_beta);
                    let p = if dead { 0.0 } else { live_p };
                    let mean_cost = rng.lognormal(cfg.cost_log_mean, cfg.cost_log_sd);
                    let mut hint = sigmoid(logit(live_p) + cfg.hint_noise * rng.standard_normal());
                    if dead && cfg.dead_hint_detection > 0.0 {
                        let mut r = SplitMix64::derive(seed, &format!("deadhint/{sig}"));
                        if r.bernoulli(cfg.dead_hint_detection) {
                            hint = sigmoid(logit(1e-3) + cfg.hint_noise * r.standard_normal());
                        }
                    }
                    let secret = format!("{:016x}", rng.next_u64());
                    truth_by_sig.insert(key.clone(), TaskTruth { name: sig.clone(), dead: p == 0.0, p_success: p, mean_cost, secret });
                    hint_by_sig.insert(key.clone(), hint);
                }
                let t = truth_by_sig[&key].clone();
                secrets.push((task_id.clone(), t.secret.clone()));
                truth.insert(task_id.clone(), t);
                hints.insert(task_id.clone(), hint_by_sig[&key]);
                tasks.push(TaskDef {
                    task_id: task_id.clone(),
                    problem_id: pid.clone(),
                    kind: if terminal { TaskKind::Goal } else { TaskKind::ProofObligation },
                    depends_on: prev.iter().cloned().collect(),
                    signature: sig,
                    terminal,
                });
                prev = Some(task_id);
            }
        }
        // The criterion digest commits to the hidden answers without revealing them.
        let criterion = Digest::of_canonical(&secrets).map_err(|e| e.to_string())?;
        let spec = ProblemSpec {
            schema_version: SPEC_SCHEMA_VERSION.into(),
            problem_id: pid.clone(),
            objective: format!("Synthetic research problem {pid}: verify any approach's goal obligation"),
            category: ProblemCategory::Synthetic,
            inputs: vec![],
            allowed_tools: vec![],
            budget: Budget { compute_units: budget_hint, ..Budget::default() },
            verification: VerificationSpec {
                method: VerificationMethod::SimulatedOracle,
                verifier_id: SIM_VERIFIER_ID.into(),
                verifier_version: SIM_VERIFIER_VERSION.into(),
                criterion_sha256: criterion,
                required_trust: TrustClass::V2,
            },
            success_criteria: "A terminal obligation's artifact matches the committed hidden answer".into(),
            depends_on: vec![],
            provenance: Provenance { source: format!("frontier-sim env seed {seed}"), created_by: "frontier-sim".into(), license: None },
            difficulty: None,
        };
        specs.push(SealedSpec::seal(spec).map_err(|e| e.to_string())?);
    }
    Ok(Campaign { specs, tasks, truth, hints })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub(crate) fn small_env() -> EnvConfig {
        EnvConfig {
            problems: 6,
            approaches_min: 1,
            approaches_max: 3,
            chain_min: 1,
            chain_max: 3,
            shared_lemma_prob: 0.5,
            dead_fraction: 0.3,
            p_alpha: 1.0,
            p_beta: 3.0,
            cost_log_mean: 0.0,
            cost_log_sd: 0.5,
            attempt_cost_sd: 0.3,
            failure_cost_mult: 1.5,
            hint_noise: 0.5,
            ..EnvConfig::default()
        }
    }

    #[test]
    fn generation_is_deterministic_and_seed_dependent() {
        let a = generate(&small_env(), 1, 100.0).unwrap();
        let b = generate(&small_env(), 1, 100.0).unwrap();
        let c = generate(&small_env(), 2, 100.0).unwrap();
        assert_eq!(a.tasks, b.tasks);
        assert_eq!(a.truth, b.truth);
        assert_eq!(a.specs.iter().map(|s| s.digest()).collect::<Vec<_>>(), b.specs.iter().map(|s| s.digest()).collect::<Vec<_>>());
        assert_ne!(a.truth, c.truth);
    }

    #[test]
    fn shared_lemmas_share_truth() {
        let mut cfg = small_env();
        cfg.shared_lemma_prob = 1.0;
        cfg.chain_min = 2;
        cfg.approaches_min = 2;
        let c = generate(&cfg, 3, 100.0).unwrap();
        let g = frontier_core::TaskGraph::build(c.tasks.clone()).unwrap();
        assert!(!g.merged().is_empty());
        for (alias, idx) in g.merged() {
            assert_eq!(c.truth[alias], c.truth[&g.node(*idx).def.task_id]);
        }
    }
}
