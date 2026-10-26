//! Simulation harness for scheduling research. Every result produced here is
//! a simulation result about a synthetic environment.

pub mod audit;
pub mod env;
pub mod experiment;
pub mod runner;

pub use audit::{RunSummary, summarize};
pub use env::EnvConfig;
pub use experiment::{ExperimentConfig, ResultRecord, run_experiment};
pub use runner::{RunConfig, SimConfig, SimError, run};
