"""Independent property-test verifier for algorithm tasks.

The candidate is untrusted source code. It runs in a separate interpreter
started as `sys.executable -I -S -c <harness>`:

* `-I -S`: no user site, no site-packages, no PYTHON* variables, script
  directory not on `sys.path`; the child's `sys.path` is the stdlib only, so
  `frontier_py` (and the reference implementations) cannot be imported.
* cwd is a fresh temporary directory, deleted afterwards.
* the environment is replaced by an allowlist: nothing on POSIX,
  `SYSTEMROOT` on Windows (CPython needs it to start). Parent secrets such
  as API keys are not inherited.
* inputs go in on stdin as JSON; outputs come back as one JSON line tagged
  with a per-run nonce on a duplicated descriptor. The child's fd 0/1/2 are
  pointed at the null device before candidate code runs, so `print` cannot
  reach the result channel by accident.
* expected outputs are computed by the reference implementation in THIS
  process, from hidden inputs generated fresh at verify time, and compared
  here. The child never receives them; nothing the child reports is taken
  as a verdict.

Resource limits:

* POSIX: `RLIMIT_AS` (task memory limit), `RLIMIT_CPU`, `RLIMIT_FSIZE`,
  `RLIMIT_NOFILE`, `RLIMIT_CORE` via `preexec_fn`, plus `RLIMIT_NPROC = 0`
  set inside the harness after its watchdog thread starts (ineffective when
  running as root). The child gets its own session and the whole process
  group is killed on timeout.
* Windows: only timeouts (per-call watchdog in the child, wall clock in the
  parent, process-tree kill with `taskkill /T`). There is NO memory, CPU,
  file-size or process-count limit. Receipts say so in `reason`.

Not provided on any platform: network isolation (sockets are NOT blocked),
filesystem isolation (the candidate can read any file the user can, by
absolute path, including the reference sources), and protection against
the candidate finding the nonce in its own process memory. The nonce only
prevents accidental or naive forgery; the real defence against forged
results is that the parent compares outputs against expected values the
child never sees. For these reasons every receipt is trust class V1, never
V2: V2 requires the isolated verifier image, which does not exist yet.

Verdicts: PASS iff every visible and hidden case matches exactly (canonical
JSON equality, so 1 != 1.0 != true). FAIL on mismatch, exception, missing
function, malformed or oversized output, or early exit. INCONCLUSIVE on
timeout or resource exhaustion. `cost_units` is verifier wall-clock seconds.
Only `body["source"]` of the artifact is read; any other field (e.g. a
self-reported confidence) has no effect on the verdict.
"""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..receipt import VerifierReceipt, canonical_digest, canonical_json
from ..tasks import Args, TaskDef

VERIFIER_ID = "property-tests"
VERIFIER_VERSION = "0.1.0"
TRUST_CLASS = "V1"
MAX_OUTPUT_BYTES = 8 << 20
POSIX = os.name == "posix"

ISOLATION_NOTE = (
    "[V1 harness: rlimits only; network and filesystem NOT isolated]"
    if POSIX
    else "[V1 harness, unsandboxed: timeouts only, no memory/CPU/process limits; network and filesystem NOT isolated]"
)

# Runs inside the child. Kept dependency-free (stdlib only, no site).
HARNESS = r"""
import json, os, sys, threading, time
def _main():
    dumps, loads, mono, write, exit_ = json.dumps, json.loads, time.monotonic, os.write, os._exit
    req = loads(sys.stdin.buffer.read().decode("utf-8"))
    nonce, limit = req["nonce"], float(req["per_call_timeout"])
    out = os.dup(1)
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    lock = threading.Lock()
    def emit(body):
        lock.acquire()
        data = ('{"nonce":' + dumps(nonce) + "," + body + "}\n").encode("utf-8")
        while data:
            data = data[write(out, data):]
        exit_(0)
    def name(e):
        n = type(e).__name__
        return n if n.isidentifier() and len(n) <= 64 else "Exception"
    state = {"deadline": mono() + limit, "case": -1}
    def watch():
        while True:
            time.sleep(0.02)
            if mono() > state["deadline"]:
                emit('"status":"timeout","case":' + str(state["case"]))
    threading.Thread(target=watch, daemon=True).start()
    if os.name == "posix":
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
        except (ImportError, ValueError, OSError, AttributeError):
            pass
    inputs, fname = req["inputs"], req["function"]
    ns = {"__name__": "candidate"}
    try:
        exec(compile(req["source"], "<candidate>", "exec"), ns)
    except MemoryError:
        emit('"status":"resource","case":-1,"error":"MemoryError"')
    except BaseException as e:
        emit('"status":"error","case":-1,"error":' + dumps(name(e)))
    fn = ns.get(fname)
    if not callable(fn):
        emit('"status":"error","case":-1,"error":"MissingFunction"')
    parts = []
    for i, args in enumerate(inputs):
        state["case"] = i
        state["deadline"] = mono() + limit
        try:
            parts.append(dumps(fn(*args), allow_nan=False))
        except MemoryError:
            emit('"status":"resource","case":' + str(i) + ',"error":"MemoryError"')
        except BaseException as e:
            emit('"status":"error","case":' + str(i) + ',"error":' + dumps(name(e)))
    state["deadline"] = float("inf")
    emit('"status":"ok","outputs":[' + ",".join(parts) + "]")
try:
    _main()
except MemoryError:
    os._exit(86)
"""

Kind = Literal["ok", "timeout", "resource", "error", "malformed"]
_RESOURCE_SIGNALS = {getattr(signal, s) for s in ("SIGXCPU", "SIGXFSZ", "SIGKILL") if hasattr(signal, s)}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


@dataclass(frozen=True)
class ChildOutcome:
    kind: Kind
    detail: str
    outputs: list[Any] | None = None
    case: int | None = None


def child_env() -> dict[str, str]:
    """Minimal environment for the child; nothing secret is inherited."""
    if os.name == "nt":
        return {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}
    return {}


def _posix_limits(memory_mb: int, cpu_s: int) -> Any:
    def apply() -> None:
        import resource

        mem = memory_mb << 20
        for lim, val in (
            (resource.RLIMIT_AS, mem),
            (resource.RLIMIT_CPU, cpu_s),
            (resource.RLIMIT_FSIZE, 1 << 20),
            (resource.RLIMIT_NOFILE, 64),
            (resource.RLIMIT_CORE, 0),
        ):
            hard = resource.getrlimit(lim)[1]
            if hard != resource.RLIM_INFINITY:
                val = min(val, hard)
            resource.setrlimit(lim, (val, val))

    return apply


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if POSIX:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    else:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    proc.kill()


def run_candidate(
    source: str,
    function_name: str,
    inputs: list[Args],
    *,
    per_call_timeout_s: float,
    wall_timeout_s: float,
    memory_limit_mb: int,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> ChildOutcome:
    """Run untrusted `source` on `inputs` in an isolated child; return raw outputs."""
    nonce = secrets.token_hex(16)
    payload = json.dumps(
        {"nonce": nonce, "source": source, "function": function_name, "inputs": inputs, "per_call_timeout": per_call_timeout_s}
    ).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="frontier-verify-") as cwd:
        kwargs: dict[str, Any] = {}
        if POSIX:
            kwargs = {"preexec_fn": _posix_limits(memory_limit_mb, int(wall_timeout_s) + 1), "start_new_session": True}
        else:
            kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        proc = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", HARNESS],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            env=child_env(),
            close_fds=True,
            **kwargs,
        )
        assert proc.stdin is not None and proc.stdout is not None
        buf = bytearray()
        overflow = threading.Event()

        def feed() -> None:
            try:
                proc.stdin.write(payload)  # type: ignore[union-attr]
                proc.stdin.close()  # type: ignore[union-attr]
            except OSError:
                pass

        def drain() -> None:
            while chunk := proc.stdout.read1(65536):  # type: ignore[union-attr]
                if len(buf) + len(chunk) > max_output_bytes:
                    overflow.set()
                    _kill_tree(proc)
                    return
                buf.extend(chunk)

        threads = [threading.Thread(target=feed, daemon=True), threading.Thread(target=drain, daemon=True)]
        for t in threads:
            t.start()
        try:
            rc = proc.wait(timeout=wall_timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.wait()
            return ChildOutcome("timeout", f"wall timeout {wall_timeout_s:g}s exceeded")
        finally:
            for t in threads:
                t.join(timeout=2.0)
            proc.stdout.close()
    if overflow.is_set():
        return ChildOutcome("malformed", f"output exceeded {max_output_bytes} bytes")
    if rc != 0:
        if POSIX and -rc in _RESOURCE_SIGNALS:
            return ChildOutcome("resource", f"killed by signal {signal.Signals(-rc).name}")
        if rc == 86:
            return ChildOutcome("resource", "MemoryError in harness")
        return ChildOutcome("malformed", f"child exited with status {rc} without a result")
    return _parse(bytes(buf), nonce)


def _parse(raw: bytes, nonce: str) -> ChildOutcome:
    lines = raw.split(b"\n")
    if len(lines) != 2 or lines[1] != b"":
        return ChildOutcome("malformed", "result channel did not contain exactly one line")
    try:
        msg = json.loads(lines[0])
    except (ValueError, RecursionError):
        return ChildOutcome("malformed", "result line is not valid JSON")
    if not isinstance(msg, dict) or msg.get("nonce") != nonce:
        return ChildOutcome("malformed", "result not tagged with this run's nonce")
    status, case = msg.get("status"), msg.get("case")
    case = case if isinstance(case, int) and not isinstance(case, bool) else None
    err = msg.get("error")
    err = err if isinstance(err, str) and _NAME.fullmatch(err) else "Exception"
    if status == "ok" and isinstance(msg.get("outputs"), list):
        return ChildOutcome("ok", "", outputs=msg["outputs"])
    if status == "timeout":
        return ChildOutcome("timeout", "per-call timeout", case=case)
    if status == "resource":
        return ChildOutcome("resource", err, case=case)
    if status == "error":
        return ChildOutcome("error", err, case=case)
    return ChildOutcome("malformed", "unrecognised result status")


def artifact_digest_for(spec_digest: str, task_id: str, body: Mapping[str, Any]) -> str:
    """Digest of the artifact as frontier-core encodes `Artifact` (kind=code, no parents)."""
    return canonical_digest({"kind": "code", "spec_digest": spec_digest, "task_id": task_id, "parents": [], "body": dict(body)})


def _canon(x: Any) -> bytes | None:
    try:
        return canonical_json(x)
    except (ValueError, RecursionError):
        return None


def _where(case: int | None, n_visible: int) -> str:
    if case is None or case < 0:
        return "while loading the candidate"
    return f"on visible case {case}" if case < n_visible else f"on hidden case {case - n_visible}"


def verify(
    task: TaskDef,
    body: Mapping[str, Any],
    *,
    spec_digest: str,
    seed: int,
    artifact_digest: str | None = None,
    task_id: str | None = None,
    charge_per_case: float | None = None,
) -> VerifierReceipt:
    """Verify an artifact body {"source": str, ...} against `task`; return a receipt.

    `cost_units` is verifier wall-clock seconds by default. For replayable
    runs pass `charge_per_case`: the receipt then charges a deterministic
    `charge_per_case * number_of_cases` and the caller reports wall time
    separately.
    """
    start = time.perf_counter()
    if artifact_digest is None:
        artifact_digest = artifact_digest_for(spec_digest, task_id or task.name, body)

    def receipt(verdict: str, reason: str) -> VerifierReceipt:
        return VerifierReceipt(
            spec_digest=spec_digest,
            artifact_digest=artifact_digest,
            verdict=verdict,  # type: ignore[arg-type]
            trust_class=TRUST_CLASS,
            verifier_id=VERIFIER_ID,
            verifier_version=VERIFIER_VERSION,
            reason=f"{ISOLATION_NOTE} {task.name} v{task.version}: {reason}",
            cost_units=round(time.perf_counter() - start, 6) if charge_per_case is None else charge,
        )

    n_cases = len(task.visible) + len(task.hidden_inputs(seed))
    charge = round((charge_per_case or 0.0) * n_cases, 9)
    source = body.get("source")
    if not isinstance(source, str):
        return receipt("FAIL", "artifact body has no string 'source'")
    inputs = [list(a) for a, _ in task.visible] + task.hidden_inputs(seed)
    n_vis = len(task.visible)
    expected = [json.loads(canonical_json(task.reference(*copy.deepcopy(a)))) for a in inputs]
    out = run_candidate(
        source,
        task.function_name,
        inputs,
        per_call_timeout_s=task.per_call_timeout_s,
        wall_timeout_s=task.wall_timeout_s,
        memory_limit_mb=task.memory_limit_mb,
    )
    if out.kind == "timeout":
        return receipt("INCONCLUSIVE", f"timeout ({out.detail}) {_where(out.case, n_vis)}".rstrip())
    if out.kind == "resource":
        return receipt("INCONCLUSIVE", f"resource exhaustion ({out.detail}) {_where(out.case, n_vis)}")
    if out.kind == "error":
        return receipt("FAIL", f"candidate raised {out.detail} {_where(out.case, n_vis)}")
    if out.kind == "malformed" or out.outputs is None:
        return receipt("FAIL", f"malformed result: {out.detail}")
    if len(out.outputs) != len(expected):
        return receipt("FAIL", f"malformed result: {len(out.outputs)} outputs for {len(expected)} cases")
    bad = [i for i, (got, want) in enumerate(zip(out.outputs, expected)) if _canon(got) != canonical_json(want)]
    if bad:
        return receipt("FAIL", f"output mismatch on {len(bad)} of {len(expected)} cases (first {_where(bad[0], n_vis)})")
    return receipt("PASS", f"all {len(expected)} cases match ({n_vis} visible, {len(expected) - n_vis} hidden, seed {seed})")
