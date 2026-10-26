//! Grid experiments: regimes × policies × seeds, run in parallel.
//!
//! For a given (regime, seed) every policy faces the same generated campaign
//! and the same per-attempt outcome streams, so comparisons are paired.

use frontier_sched::PolicyConfig;
use serde::{Deserialize, Serialize};

use crate::audit::{RunSummary, summarize};
use crate::env::{EnvConfig, generate};
use crate::runner::{RunConfig, SIM_CONFIG_VERSION, SimConfig, SimError, run_campaign};

pub const EXPERIMENT_VERSION: &str = "0.1";

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Regime {
    pub name: String,
    pub env: EnvConfig,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExperimentConfig {
    pub schema_version: String,
    pub experiment_id: String,
    pub regimes: Vec<Regime>,
    pub policies: Vec<PolicyConfig>,
    pub seed_start: u64,
    pub seeds: u64,
    /// Run parameters shared by all cells; `seed` and `policy` are overridden.
    pub run: RunConfig,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResultRecord {
    pub experiment_id: String,
    pub regime: String,
    pub policy_index: usize,
    pub policy_config: PolicyConfig,
    #[serde(flatten)]
    pub summary: RunSummary,
    /// Host wall-clock time inside the policy; not deterministic.
    pub select_nanos: u128,
    pub decisions: u64,
}

impl ExperimentConfig {
    pub fn cell(&self, regime: &Regime, policy: &PolicyConfig, seed: u64) -> SimConfig {
        let mut run = self.run.clone();
        run.seed = seed;
        run.policy = policy.clone();
        SimConfig {
            schema_version: SIM_CONFIG_VERSION.into(),
            name: format!("{}/{}", self.experiment_id, regime.name),
            env: regime.env.clone(),
            run,
        }
    }
}

pub fn run_experiment(cfg: &ExperimentConfig, threads: usize) -> Result<Vec<ResultRecord>, SimError> {
    if cfg.schema_version != EXPERIMENT_VERSION {
        return Err(SimError::Config("unsupported experiment schema_version".into()));
    }
    let jobs: Vec<(usize, u64)> =
        (0..cfg.regimes.len()).flat_map(|r| (cfg.seed_start..cfg.seed_start + cfg.seeds).map(move |s| (r, s))).collect();
    let threads = threads.max(1).min(jobs.len().max(1));
    let chunks: Vec<Vec<(usize, u64)>> = (0..threads).map(|i| jobs.iter().copied().skip(i).step_by(threads).collect()).collect();
    let mut out: Vec<(usize, u64, Vec<ResultRecord>)> = Vec::new();
    std::thread::scope(|scope| -> Result<(), SimError> {
        let handles: Vec<_> = chunks
            .into_iter()
            .map(|chunk| {
                scope.spawn(move || -> Result<Vec<(usize, u64, Vec<ResultRecord>)>, SimError> {
                    let mut local = vec![];
                    for (ri, seed) in chunk {
                        let regime = &cfg.regimes[ri];
                        let campaign = generate(&regime.env, seed, cfg.run.budget_units).map_err(SimError::Config)?;
                        let mut recs = vec![];
                        for (pi, policy) in cfg.policies.iter().enumerate() {
                            let sim = cfg.cell(regime, policy, seed);
                            sim.validate()?;
                            let output = run_campaign(&sim, &campaign)?;
                            let summary = summarize(&output.log).map_err(|e| SimError::Invariant(e.to_string()))?;
                            recs.push(ResultRecord {
                                experiment_id: cfg.experiment_id.clone(),
                                regime: regime.name.clone(),
                                policy_index: pi,
                                policy_config: policy.clone(),
                                summary,
                                select_nanos: output.select_nanos,
                                decisions: output.decisions,
                            });
                        }
                        local.push((ri, seed, recs));
                    }
                    Ok(local)
                })
            })
            .collect();
        for h in handles {
            out.extend(h.join().expect("worker thread panicked")?);
        }
        Ok(())
    })?;
    out.sort_by_key(|(r, s, _)| (*r, *s));
    Ok(out.into_iter().flat_map(|(_, _, recs)| recs).collect())
}
