//! `frontier`: run, audit and replay research campaigns; run grid experiments.

use std::fs::{self, File};
use std::io::{BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

use frontier_core::{Digest, EventLog, KERNEL_VERSION};
use frontier_sim::{ExperimentConfig, SimConfig, run, run_experiment, summarize};
use serde::Serialize;

const USAGE: &str = "usage:
  frontier run --config SIM.json --out DIR
  frontier audit --events EVENTS.jsonl [--summary SUMMARY.json]
  frontier replay --config SIM.json --events EVENTS.jsonl
  frontier experiment --config EXP.json --out DIR [--threads N]";

type Result<T> = std::result::Result<T, String>;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let outcome = match args.first().map(String::as_str) {
        Some("run") => cmd_run(&args[1..]),
        Some("audit") => cmd_audit(&args[1..]),
        Some("replay") => cmd_replay(&args[1..]),
        Some("experiment") => cmd_experiment(&args[1..]),
        _ => Err(USAGE.into()),
    };
    match outcome {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("error: {e}");
            ExitCode::FAILURE
        }
    }
}

fn flag(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned()
}

fn required(args: &[String], name: &str) -> Result<String> {
    flag(args, name).ok_or_else(|| format!("missing {name}\n{USAGE}"))
}

fn read_json<T: serde::de::DeserializeOwned>(path: &str) -> Result<T> {
    let text = fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    serde_json::from_str(&text).map_err(|e| format!("{path}: {e}"))
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let mut text = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    text.push('\n');
    fs::write(path, text).map_err(|e| format!("{}: {e}", path.display()))
}

fn read_log(path: &str) -> Result<EventLog> {
    let f = File::open(path).map_err(|e| format!("{path}: {e}"))?;
    EventLog::read_jsonl(BufReader::new(f)).map_err(|e| format!("{path}: {e}"))
}

fn cmd_run(args: &[String]) -> Result<()> {
    let cfg: SimConfig = read_json(&required(args, "--config")?)?;
    let out = PathBuf::from(required(args, "--out")?);
    fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let result = run(&cfg).map_err(|e| e.to_string())?;
    let summary = summarize(&result.log).map_err(|e| e.to_string())?;
    let f = File::create(out.join("events.jsonl")).map_err(|e| e.to_string())?;
    result.log.write_jsonl(BufWriter::new(f)).map_err(|e| e.to_string())?;
    write_json(&out.join("config.json"), &cfg)?;
    write_json(&out.join("summary.json"), &summary)?;
    println!(
        "SIMULATION {} policy={} solved {}/{} committed {:.2}/{} CU, log head {}",
        cfg.name, summary.policy, summary.solved, summary.problems, summary.committed_units, cfg.run.budget_units, summary.log_head
    );
    Ok(())
}

fn cmd_audit(args: &[String]) -> Result<()> {
    let log = read_log(&required(args, "--events")?)?;
    let summary = summarize(&log).map_err(|e| format!("audit failed: {e}"))?;
    if let Some(path) = flag(args, "--summary") {
        let claimed: serde_json::Value = read_json(&path)?;
        let recomputed = serde_json::to_value(&summary).map_err(|e| e.to_string())?;
        if claimed != recomputed {
            return Err(format!("{path} does not match the summary recomputed from the log"));
        }
    }
    println!("audit ok: {} records, head {}, solved {}/{}", log.records().len(), summary.log_head, summary.solved, summary.problems);
    Ok(())
}

fn cmd_replay(args: &[String]) -> Result<()> {
    let cfg: SimConfig = read_json(&required(args, "--config")?)?;
    let recorded = read_log(&required(args, "--events")?)?;
    let rerun = run(&cfg).map_err(|e| e.to_string())?;
    if rerun.log.head() != recorded.head() {
        let diverge = recorded.records().iter().zip(rerun.log.records()).position(|(a, b)| a != b);
        return Err(format!(
            "replay diverged: recorded head {}, replay head {} (first differing record: {:?})",
            recorded.head(),
            rerun.log.head(),
            diverge
        ));
    }
    println!("replay ok: {} records reproduced, head {}", recorded.records().len(), recorded.head());
    Ok(())
}

#[derive(Serialize)]
struct Manifest {
    experiment_id: String,
    kind: &'static str,
    config_digest: Digest,
    results_sha256: Digest,
    records: usize,
    kernel_version: &'static str,
    source_commit: String,
    source_dirty: bool,
    host_os: &'static str,
    host_arch: &'static str,
    host_threads: usize,
    threads_used: usize,
    wall_seconds: f64,
}

fn git(args: &[&str]) -> Option<String> {
    let out = std::process::Command::new("git").args(args).output().ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).trim().to_owned())
}

fn cmd_experiment(args: &[String]) -> Result<()> {
    let cfg: ExperimentConfig = read_json(&required(args, "--config")?)?;
    let out = PathBuf::from(required(args, "--out")?);
    let host_threads = std::thread::available_parallelism().map_or(1, |n| n.get());
    let threads = match flag(args, "--threads") {
        Some(t) => t.parse::<usize>().map_err(|e| format!("--threads: {e}"))?,
        None => host_threads,
    };
    fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let t0 = Instant::now();
    let records = run_experiment(&cfg, threads).map_err(|e| e.to_string())?;
    let wall_seconds = t0.elapsed().as_secs_f64();

    let mut buf = Vec::new();
    for r in &records {
        serde_json::to_writer(&mut buf, r).map_err(|e| e.to_string())?;
        buf.push(b'\n');
    }
    let results = out.join("results.jsonl");
    File::create(&results).and_then(|mut f| f.write_all(&buf)).map_err(|e| format!("{}: {e}", results.display()))?;
    write_json(&out.join("experiment.json"), &cfg)?;
    let manifest = Manifest {
        experiment_id: cfg.experiment_id.clone(),
        kind: "simulation",
        config_digest: Digest::of_canonical(&cfg).map_err(|e| e.to_string())?,
        results_sha256: Digest::of_bytes(&buf),
        records: records.len(),
        kernel_version: KERNEL_VERSION,
        source_commit: git(&["rev-parse", "HEAD"]).unwrap_or_else(|| "unknown".into()),
        source_dirty: git(&["status", "--porcelain", "--untracked-files=no"]).is_none_or(|s| !s.is_empty()),
        host_os: std::env::consts::OS,
        host_arch: std::env::consts::ARCH,
        host_threads,
        threads_used: threads,
        wall_seconds,
    };
    write_json(&out.join("manifest.json"), &manifest)?;
    println!("SIMULATION experiment {}: {} runs in {:.1}s -> {}", cfg.experiment_id, records.len(), wall_seconds, results.display());
    Ok(())
}
