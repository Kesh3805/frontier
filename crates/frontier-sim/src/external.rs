//! Client for the Python worker/verifier service (JSONL protocol versions 1
//! and 2, see `python/frontier_py/realtasks/server.py`).
//!
//! The service runs real candidate programs through the property-test
//! verifier. Its replies are trusted only as far as the receipt's trust class
//! says (V1: subprocess harness without OS isolation). Wall time it reports
//! is collected here and kept out of the deterministic event log.
//!
//! Protocol 2 adds an optional `library` to `attempt`: verified helper
//! sources for a dependent task. An attempt without a library is the same
//! request in both versions, so v1/v2 catalogs run unchanged against either.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

use frontier_core::{Digest, VerifierReceipt};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::runner::SimError;

/// Newest protocol this client speaks; it also accepts services speaking 1.
pub const PROTOCOL: u64 = 2;
/// First protocol version whose `attempt` accepts a `library`.
pub const LIBRARY_PROTOCOL: u64 = 2;

/// A verified helper passed to a dependent task's attempt: the call name and
/// the source of the artifact the evidence store accepted for the prerequisite.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LibraryEntry {
    pub name: String,
    pub source: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ServerCommand {
    pub program: String,
    pub args: Vec<String>,
    /// Working directory, relative to the experiment config's directory.
    pub cwd: String,
}

pub struct AttemptReply {
    pub source: String,
    pub gen_units: f64,
}

pub struct ExternalWorker {
    child: Child,
    /// The service's `hello` reply (protocol, suite version, hidden seed).
    pub hello: Value,
    /// Protocol version the service speaks (1 or 2).
    pub protocol: u64,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    /// Host wall-clock seconds the service spent verifying (not deterministic).
    pub verify_wall_seconds: f64,
}

fn protocol_error(msg: impl Into<String>) -> SimError {
    SimError::Invariant(format!("worker service: {}", msg.into()))
}

impl ExternalWorker {
    pub fn spawn(cmd: &ServerCommand, base: &std::path::Path) -> Result<Self, SimError> {
        let mut child = Command::new(&cmd.program)
            .args(&cmd.args)
            .current_dir(base.join(&cmd.cwd))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| protocol_error(format!("cannot start {:?}: {e}", cmd.program)))?;
        let stdin = child.stdin.take().expect("piped");
        let stdout = BufReader::new(child.stdout.take().expect("piped"));
        let mut w = Self { child, stdin, stdout, hello: Value::Null, protocol: 0, verify_wall_seconds: 0.0 };
        let hello = w.request(&json!({ "op": "hello" }))?;
        match hello.get("protocol").and_then(Value::as_u64) {
            Some(p @ 1..=PROTOCOL) => w.protocol = p,
            _ => return Err(protocol_error(format!("unsupported protocol in {hello}"))),
        }
        w.hello = hello;
        Ok(w)
    }

    fn request(&mut self, req: &Value) -> Result<Value, SimError> {
        let mut line = serde_json::to_string(req).map_err(|e| protocol_error(e.to_string()))?;
        line.push('\n');
        self.stdin.write_all(line.as_bytes()).and_then(|_| self.stdin.flush()).map_err(|e| protocol_error(e.to_string()))?;
        let mut reply = String::new();
        let n = self.stdout.read_line(&mut reply).map_err(|e| protocol_error(e.to_string()))?;
        if n == 0 {
            return Err(protocol_error("service closed its output"));
        }
        let v: Value = serde_json::from_str(&reply).map_err(|e| protocol_error(format!("bad reply {reply:?}: {e}")))?;
        if v.get("ok") != Some(&Value::Bool(true)) {
            return Err(protocol_error(format!("request {req} failed: {v}")));
        }
        Ok(v)
    }

    /// One worker attempt. `library` must be empty for tasks without
    /// prerequisites; the request is then identical to protocol 1.
    pub fn attempt(&mut self, task: &str, seed: u64, k: u32, library: &[LibraryEntry]) -> Result<AttemptReply, SimError> {
        let mut req = json!({ "op": "attempt", "task": task, "seed": seed, "k": k });
        if !library.is_empty() {
            if self.protocol < LIBRARY_PROTOCOL {
                return Err(protocol_error(format!("protocol {} service cannot take a library", self.protocol)));
            }
            req["library"] = serde_json::to_value(library).map_err(|e| protocol_error(e.to_string()))?;
        }
        let v = self.request(&req)?;
        let source = v.get("source").and_then(Value::as_str).ok_or_else(|| protocol_error("attempt reply lacks source"))?;
        let gen_units = v.get("gen_units").and_then(Value::as_f64).filter(|u| u.is_finite() && *u >= 0.0);
        Ok(AttemptReply { source: source.to_owned(), gen_units: gen_units.ok_or_else(|| protocol_error("bad gen_units"))? })
    }

    /// Returns the verifier's receipt and the extended ground-truth check.
    pub fn verify(&mut self, task: &str, source: &str, spec: Digest, artifact: Digest) -> Result<(VerifierReceipt, bool), SimError> {
        let v = self.request(&json!({
            "op": "verify", "task": task, "source": source,
            "spec_digest": spec.to_hex(), "artifact_digest": artifact.to_hex(),
        }))?;
        let receipt: VerifierReceipt = serde_json::from_value(v.get("receipt").cloned().unwrap_or(Value::Null))
            .map_err(|e| protocol_error(format!("receipt: {e}")))?;
        if receipt.spec_digest != spec || receipt.artifact_digest != artifact {
            return Err(protocol_error("receipt bound to a different spec or artifact"));
        }
        self.verify_wall_seconds += v.get("wall_seconds").and_then(Value::as_f64).unwrap_or(0.0);
        let extended_ok = v.get("extended_ok").and_then(Value::as_bool).ok_or_else(|| protocol_error("missing extended_ok"))?;
        Ok((receipt, extended_ok))
    }
}

impl Drop for ExternalWorker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
