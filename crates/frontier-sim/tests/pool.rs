//! Stage 2 phase 0: replay of a recorded sample pool (ADR-0008).
//!
//! A pool is filled by the fake transport, which answers with DSL programs
//! (no provider call, no key), and a small real-task experiment is replayed
//! from it through `server --worker llm-pool`. The log heads must not depend
//! on the run or on the thread count. Skipped if Python is unavailable.

use std::path::{Path, PathBuf};
use std::process::Command;

use frontier_core::Digest;
use frontier_sim::external::ServerCommand;
use frontier_sim::real::{RealExperimentConfig, ServiceStats, run_real_experiment};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn scratch(name: &str) -> PathBuf {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("frontier-{name}-{}-{nanos}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Fill a 4-sample pool for every pilot task with the fake (DSL) transport.
fn fake_pool(dir: &Path) -> Option<PathBuf> {
    let rate = dir.join("rate-card.json");
    std::fs::write(
        &rate,
        r#"{"version":"test-1","cu_per_input_token":0.0005,"cu_per_output_token":0.002,"usd_per_input_token":1e-7,"usd_per_output_token":4e-7}"#,
    )
    .unwrap();
    let pool = dir.join("pool.jsonl");
    let out = Command::new("python")
        .args(["-m", "frontier_py.realtasks.pool", "fill", "--task-set", "pilot", "--n", "4", "--transport", "fake", "--execute"])
        .arg("--rate-card")
        .arg(&rate)
        .arg("--pool")
        .arg(&pool)
        .arg("--max-usd")
        .arg("1")
        .arg("--ledger")
        .arg(dir.join("ledger.json"))
        .current_dir(root().join("python"))
        .output();
    match out {
        Ok(o) if o.status.success() => Some(pool),
        Ok(o) => panic!("pool fill failed: {}", String::from_utf8_lossy(&o.stderr)),
        Err(e) => {
            eprintln!("python unavailable ({e}); skipping");
            None
        }
    }
}

fn config(pool: &Path) -> RealExperimentConfig {
    let v = serde_json::json!({
        "schema_version": "0.1",
        "experiment_id": "pool-replay-test",
        "catalog": "research/realtasks/catalog-v1.json",
        "catalog_sha256": "80bdd82bec3e249b17d7938dab3e28786989dae55edd0650875c0c6c440b9585",
        "server": { "program": "python", "args": [], "cwd": "python" },
        "policies": [
            { "kind": "round_robin" },
            { "kind": "thompson", "prior_strength": 2.0, "use_hints": true }
        ],
        "seed_start": 1,
        "seeds": 2,
        "run": {
            "seed": 0, "workers": 2, "budget_units": 5.0, "attempt_cap_units": 3.0, "verify_cost_units": 0.25,
            "crash_prob": 0.0, "max_attempts_per_task": 4, "max_parallel_per_task": 1, "prior_cost": 1.0,
            "policy": { "kind": "round_robin" }
        }
    });
    let mut cfg: RealExperimentConfig = serde_json::from_value(v).unwrap();
    cfg.server = ServerCommand {
        program: "python".into(),
        args: vec![
            "-m".into(),
            "frontier_py.realtasks.server".into(),
            "--worker".into(),
            "llm-pool".into(),
            "--pool".into(),
            pool.to_string_lossy().into_owned(),
            "--allow-unsandboxed-for-tests".into(),
        ],
        cwd: "python".into(),
    };
    cfg
}

fn heads(cfg: &RealExperimentConfig, threads: usize) -> (Vec<(usize, Digest, usize)>, ServiceStats) {
    let (recs, stats) = run_real_experiment(cfg, &root(), threads).unwrap();
    (recs.iter().map(|r| (r.policy_index, r.summary.log_head, r.summary.solved)).collect(), stats)
}

#[test]
fn pool_replay_log_heads_are_reproducible_across_runs_and_threads() {
    let dir = scratch("pool-replay");
    let Some(pool) = fake_pool(&dir) else { return };
    let pool_sha = {
        let bytes = std::fs::read(&pool).unwrap();
        Digest::of_bytes(&bytes).to_hex()
    };
    let cfg = config(&pool);
    let (a, sa) = heads(&cfg, 1);
    let (b, _) = heads(&cfg, 1);
    let (c, sc) = heads(&cfg, 2);
    assert_eq!(a.len(), 4);
    assert!(a.iter().map(|x| x.2).sum::<usize>() > 0, "replayed DSL programs should solve something");
    assert_eq!(a, b, "two runs differ");
    assert_eq!(a, c, "thread count changed the logs");
    assert_eq!(sa.worker, "llm-pool:fake/dsl-search@fake-1");
    assert_eq!(sa.pool_sha256.as_deref(), Some(pool_sha.as_str()));
    assert_eq!(sc.pool_sha256, sa.pool_sha256);
    assert!(sa.verify_calls > 0 && sa.verify_wall_seconds > 0.0);
    let _ = std::fs::remove_dir_all(&dir);
}
