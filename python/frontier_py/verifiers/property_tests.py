"""Independent property-test verifier for algorithm tasks.

Two sandbox backends share one protocol and one set of verdict semantics,
selected by `sandbox=` on `run_candidate` / `verify`:

* `"none"` (default, trust class V1): the harness runs in a local child
  interpreter with the guarantees and gaps listed under "V1" below.
* `"docker"` (trust class V2): the same harness runs as
  `python -I -S -c <harness>` inside a throwaway container of a Python
  image pinned by digest (`SANDBOX_IMAGE`), started with
  `docker run --rm -i --pull never --network none --ipc none --read-only
  --tmpfs /tmp --memory/--memory-swap <limit> --pids-limit 64 --cpus 1
  --cap-drop ALL --security-opt no-new-privileges --user 65534:65534`
  plus `--ulimit` core/nofile/fsize/cpu (see `docker_command`). No host
  path is mounted and no host environment variable is passed in, so the
  candidate cannot read the repository, the reference implementations or
  parent secrets, cannot reach the network, and can write only to a 16 MiB
  noexec tmpfs. Memory, process count and CPU are bounded by the cgroup.
  Inputs go in on the container's stdin; the result line comes back on the
  container's stdout, which the harness duplicates before pointing fd
  0/1/2 at /dev/null (the same nonce/result-channel protocol as V1).
  Expected outputs are still computed and compared in THIS process. The
  wall timeout is enforced by the parent: on expiry it runs `docker kill`
  on the container and kills the CLI.

V2 is claimed only for a run that actually executed in the container. If
docker is missing, the daemon is unreachable, the server is not a Linux
engine, the pinned image is not present locally, or `docker run` itself
fails (exit 125/126/127), the outcome is kind `"sandbox"` and the receipt is
INCONCLUSIVE with trust class V1 and a reason saying the candidate was not
executed. There is never a silent fallback to `"none"`. Caveats of V2: the
isolation is a Linux container sharing the host kernel (not a VM); the image
must be pulled ahead of time (`docker pull <SANDBOX_IMAGE>`); a candidate
that itself exits with status 125-127 is reported INCONCLUSIVE rather than
FAIL (never PASS); and the container user is not remapped (no user
namespace), so a kernel escape would land as uid 65534 on the host.

V1 (`sandbox="none"`): the candidate is untrusted source code. It runs in a
separate interpreter started as `sys.executable -I -S -c <harness>`:

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
child never sees. For these reasons every `sandbox="none"` receipt is
trust class V1, never V2. (The nonce caveat also applies inside the docker
sandbox; the parent-side comparison is the defence there too.)

Verdicts (both backends): PASS iff every visible and hidden case matches
exactly (canonical JSON equality, so 1 != 1.0 != true). FAIL on mismatch,
exception, missing function, malformed or oversized output, or early exit.
INCONCLUSIVE on timeout, resource exhaustion, or (docker) sandbox failure.
`cost_units` is verifier wall-clock seconds. `VERIFIER_VERSION` is the same
for both backends because the verification semantics are identical; the
backend is recorded in `trust_class` and in the receipt `reason`.
Only `body["source"]` of the artifact is read; any other field (e.g. a
self-reported confidence) has no effect on the verdict.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..receipt import VerifierReceipt, canonical_digest, canonical_json
from ..tasks import Args, TaskDef

VERIFIER_ID = "property-tests"
VERIFIER_VERSION = "0.1.0"
TRUST_CLASS = "V1"  # sandbox="none", and any run where the docker sandbox did not execute
TRUST_CLASS_SANDBOXED = "V2"  # only for runs that actually executed inside the docker sandbox
MAX_OUTPUT_BYTES = 8 << 20
POSIX = os.name == "posix"

Sandbox = Literal["none", "docker"]
SANDBOXES: tuple[str, ...] = ("none", "docker")

# Official `python:3.12-slim` (Python 3.12.15, linux/amd64 + linux/arm64),
# pinned by its multi-arch OCI index digest. Obtained 2026-10-27 from the
# Docker Hub registry HTTP API (anonymous pull token from auth.docker.io,
# then `HEAD /v2/library/python/manifests/3.12-slim` with an OCI index
# Accept header; the `docker-content-digest` response header). Refresh the
# same way, or with `docker buildx imagetools inspect python:3.12-slim`.
SANDBOX_IMAGE = "python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"
DOCKER_BIN = "docker"
DOCKER_STARTUP_GRACE_S = 10.0  # container start/teardown allowance added to the wall timeout
SANDBOX_TMPFS_MB = 16
SANDBOX_PIDS = 64

ISOLATION_NOTE = (
    "[V1 harness: rlimits only; network and filesystem NOT isolated]"
    if POSIX
    else "[V1 harness, unsandboxed: timeouts only, no memory/CPU/process limits; network and filesystem NOT isolated]"
)
DOCKER_ISOLATION_NOTE = (
    f"[V2 docker sandbox {SANDBOX_IMAGE}: --network none, --ipc none, read-only rootfs, {SANDBOX_TMPFS_MB}m noexec tmpfs /tmp only, "
    f"no host mounts or env, memory+swap {{memory}}m, pids {SANDBOX_PIDS}, 1 cpu, cap-drop ALL, no-new-privileges, uid 65534]"
)
DOCKER_NOT_RUN_NOTE = "[docker sandbox requested; candidate NOT executed, no sandbox claimed]"

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
        try:
            put(body)
        finally:
            exit_(0)
    def put(body):
        data = ('{"nonce":' + dumps(nonce) + "," + body + "}\n").encode("utf-8")
        while data:
            data = data[write(out, data):]
    def send(body):
        lock.acquire()
        try:
            put(body)
        except OSError:
            exit_(0)  # the parent stopped reading: it has seen a failing case
        lock.release()
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
    inputs, fname, stream = req["inputs"], req["function"], req.get("stream", False)
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
            part = dumps(fn(*args), allow_nan=False)
        except MemoryError:
            emit('"status":"resource","case":' + str(i) + ',"error":"MemoryError"')
        except BaseException as e:
            emit('"status":"error","case":' + str(i) + ',"error":' + dumps(name(e)))
        if stream:
            state["deadline"] = float("inf")
            send('"status":"case","case":' + str(i) + ',"output":' + part)
        else:
            parts.append(part)
    state["deadline"] = float("inf")
    emit('"status":"ok","outputs":[' + ",".join(parts) + "]")
try:
    _main()
except MemoryError:
    os._exit(86)
"""

Kind = Literal["ok", "timeout", "resource", "error", "malformed", "sandbox", "mismatch"]
EARLY_STOP_GRACE_S = 1.0  # after a failing streamed case: time for the child to exit before it is killed
_RESOURCE_SIGNALS = {getattr(signal, s) for s in ("SIGXCPU", "SIGXFSZ", "SIGKILL") if hasattr(signal, s)}
# `docker run` exit statuses: 125 = docker/daemon error, 126 = command cannot be
# invoked, 127 = command not found. 128+N = container process killed by signal N
# (9 SIGKILL, e.g. the cgroup OOM killer; 24 SIGXCPU; 25 SIGXFSZ on Linux).
_DOCKER_INFRA_STATUSES = {125: "docker/daemon error", 126: "command not invocable", 127: "command not found"}
_DOCKER_RESOURCE_STATUSES = {137: "SIGKILL (cgroup memory/pids limit)", 152: "SIGXCPU", 153: "SIGXFSZ"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


@dataclass(frozen=True)
class ChildOutcome:
    kind: Kind
    detail: str
    outputs: list[Any] | None = None
    case: int | None = None
    matched: int | None = None  # streamed runs: cases received and matched before the outcome


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


def _process_cpu_seconds(proc: subprocess.Popen[bytes]) -> float | None:
    """User + kernel CPU seconds of an exited child on Windows (GetProcessTimes), else None."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    times = [wintypes.FILETIME() for _ in range(4)]  # creation, exit, kernel, user
    handle = wintypes.HANDLE(int(proc._handle))  # type: ignore[attr-defined]
    if not ctypes.windll.kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):  # type: ignore[attr-defined]
        return None
    return sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:]) / 1e7


def _children_cpu() -> float | None:
    """User + system CPU seconds of reaped child processes (POSIX), else None."""
    try:
        import resource
    except ImportError:
        return None
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


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


def _check_sandbox(sandbox: str) -> None:
    if sandbox not in SANDBOXES:
        raise ValueError(f"unknown sandbox {sandbox!r}; expected one of {SANDBOXES}")


def _docker(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run([DOCKER_BIN, *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def docker_status() -> tuple[bool, str]:
    """Whether the docker sandbox can run here: (usable, human-readable detail).

    Requires the docker CLI, a reachable Linux engine, and `SANDBOX_IMAGE`
    already present locally (runs use `--pull never`). Not cached: the
    daemon can come and go.
    """
    if shutil.which(DOCKER_BIN) is None:
        return False, f"{DOCKER_BIN!r} CLI not found on PATH"
    v = _docker("version", "--format", "{{.Server.Os}}")
    if v is None or v.returncode != 0:
        return False, "docker engine not reachable"
    if v.stdout.strip() != "linux":
        return False, f"docker engine OS is {v.stdout.strip()!r}, need 'linux'"
    i = _docker("image", "inspect", "--format", "{{.Id}}", SANDBOX_IMAGE)
    if i is None or i.returncode != 0:
        return False, f"pinned image not present locally; run: docker pull {SANDBOX_IMAGE}"
    return True, "ok"


def docker_command(name: str, memory_limit_mb: int, cpu_s: int) -> list[str]:
    """argv that runs HARNESS in a fresh, locked-down container (stdin/stdout attached)."""
    return [
        DOCKER_BIN, "run", "--rm", "-i", "--pull", "never", "--name", name,
        "--network", "none",
        "--ipc", "none",  # private IPC namespace and no world-writable /dev/shm
        "--read-only",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={SANDBOX_TMPFS_MB}m",
        "--workdir", "/tmp",
        "--memory", f"{memory_limit_mb}m", "--memory-swap", f"{memory_limit_mb}m",
        "--pids-limit", str(SANDBOX_PIDS),
        "--cpus", "1",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--ulimit", "core=0:0",
        "--ulimit", "nofile=64:64",
        "--ulimit", "fsize=1048576:1048576",
        "--ulimit", f"cpu={cpu_s}:{cpu_s}",
        SANDBOX_IMAGE,
        "python", "-I", "-S", "-c", HARNESS,
    ]


def _docker_kill(name: str) -> None:
    _docker("kill", name, timeout=30.0)


def run_candidate(
    source: str,
    function_name: str,
    inputs: list[Args],
    *,
    per_call_timeout_s: float,
    wall_timeout_s: float,
    memory_limit_mb: int,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
    sandbox: Sandbox = "none",
    expected: Callable[[int], bytes] | None = None,
    stats: dict[str, Any] | None = None,
) -> ChildOutcome:
    """Run untrusted `source` on `inputs` in an isolated child; return raw outputs.

    `sandbox="docker"` runs the child in the pinned container image; if that
    is not possible the outcome is kind "sandbox" and nothing was executed.

    With `expected` (canonical expected output of case i, computed on demand
    by the caller), the run is streamed and stops early: the child reports
    each output as it is computed, the parent compares it at once, and at
    the first mismatch it stops reading, so the child exits at its next
    write (or is killed after `EARLY_STOP_GRACE_S`). The outcome is then
    kind "mismatch" at that case. A run that completes is kind "ok" with
    `outputs=None` and `matched` = the number of cases that matched; error,
    timeout and resource outcomes are as without streaming, with `matched`.
    The child still never sees an expected value.

    `stats`, if given, receives `child_cpu_seconds`: the child's CPU time
    (Windows: GetProcessTimes; POSIX: RUSAGE_CHILDREN delta, so not safe
    with concurrent calls; with docker, the CLI's CPU, not the container's).
    """
    _check_sandbox(sandbox)
    if sandbox == "docker":
        ok, detail = docker_status()
        if not ok:
            return ChildOutcome("sandbox", f"docker sandbox unavailable: {detail}")
    nonce = secrets.token_hex(16)
    req: dict[str, Any] = {"nonce": nonce, "source": source, "function": function_name, "inputs": inputs, "per_call_timeout": per_call_timeout_s}
    if expected is not None:
        req["stream"] = True
    payload = json.dumps(req).encode("utf-8")
    cpu0 = _children_cpu() if POSIX else None
    container = f"frontier-verify-{secrets.token_hex(8)}"
    with tempfile.TemporaryDirectory(prefix="frontier-verify-") as cwd:
        kwargs: dict[str, Any] = {}
        if sandbox == "docker":
            # The docker CLI is trusted and needs the parent's DOCKER_*/PATH/HOME;
            # none of it reaches the container. Limits are applied by the engine,
            # not by rlimits on the CLI process.
            argv = docker_command(container, memory_limit_mb, int(wall_timeout_s) + 1)
            env: dict[str, str] | None = None
            wall = wall_timeout_s + DOCKER_STARTUP_GRACE_S
            kwargs = {"start_new_session": True} if POSIX else {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        else:
            argv = [sys.executable, "-I", "-S", "-c", HARNESS]
            env = child_env()
            wall = wall_timeout_s
            if POSIX:
                kwargs = {"preexec_fn": _posix_limits(memory_limit_mb, int(wall_timeout_s) + 1), "start_new_session": True}
            else:
                kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=cwd,
                env=env,
                close_fds=True,
                **kwargs,
            )
        except OSError as e:
            if sandbox == "docker":
                return ChildOutcome("sandbox", f"cannot start docker: {type(e).__name__}")
            raise

        def stop() -> None:
            if sandbox == "docker":
                _docker_kill(container)
            _kill_tree(proc)

        assert proc.stdin is not None and proc.stdout is not None
        buf = bytearray()
        overflow = threading.Event()
        drained = threading.Event()
        failed: list[int] = []  # streamed: the first mismatching case
        received = [0]  # streamed: cases received and matched

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
                    stop()
                    return
                buf.extend(chunk)

        def drain_stream() -> None:
            # Consume leading case lines as they arrive; whatever follows the
            # last one (the terminal line, or anything malformed) stays in buf.
            total = 0
            try:
                while chunk := proc.stdout.read1(65536):  # type: ignore[union-attr]
                    total += len(chunk)
                    if total > max_output_bytes:
                        overflow.set()
                        stop()
                        return
                    buf.extend(chunk)
                    while (j := buf.find(b"\n")) >= 0:
                        out = _stream_case(bytes(buf[:j]), nonce, received[0])
                        if out is None:
                            break
                        del buf[: j + 1]
                        if _canon(out[0]) != expected(received[0]):  # type: ignore[misc]
                            failed.append(received[0])
                            proc.stdout.close()  # type: ignore[union-attr]
                            return
                        received[0] += 1
            finally:
                drained.set()

        threads = [threading.Thread(target=feed, daemon=True),
                   threading.Thread(target=drain if expected is None else drain_stream, daemon=True)]
        for t in threads:
            t.start()
        try:
            if expected is None:
                rc = proc.wait(timeout=wall)
            else:
                deadline = time.monotonic() + wall
                drained.wait(wall)
                if failed:
                    try:
                        proc.wait(timeout=EARLY_STOP_GRACE_S)
                    except subprocess.TimeoutExpired:
                        stop()
                        proc.wait()
                    return ChildOutcome("mismatch", "output mismatch", case=failed[0], matched=received[0])
                rc = proc.wait(timeout=max(deadline - time.monotonic(), 0.0))
        except subprocess.TimeoutExpired:
            stop()
            proc.wait()
            return ChildOutcome("timeout", f"wall timeout {wall:g}s exceeded", matched=None if expected is None else received[0])
        finally:
            for t in threads:
                t.join(timeout=2.0)
            proc.stdout.close()
            if stats is not None:
                if POSIX:
                    cpu1 = _children_cpu()
                    stats["child_cpu_seconds"] = None if cpu0 is None or cpu1 is None else cpu1 - cpu0
                else:
                    stats["child_cpu_seconds"] = _process_cpu_seconds(proc)
    if overflow.is_set():
        return ChildOutcome("malformed", f"output exceeded {max_output_bytes} bytes")
    if expected is not None:
        return _with_matched(_finish(rc, bytes(buf), nonce, sandbox), received[0], len(inputs))
    return _finish(rc, bytes(buf), nonce, sandbox)


def _finish(rc: int, raw: bytes, nonce: str, sandbox: str) -> ChildOutcome:
    if sandbox == "docker" and rc in _DOCKER_INFRA_STATUSES:
        return ChildOutcome("sandbox", f"docker run exited {rc} ({_DOCKER_INFRA_STATUSES[rc]}) without a result")
    if sandbox == "docker" and rc in _DOCKER_RESOURCE_STATUSES:
        return ChildOutcome("resource", f"container process killed by {_DOCKER_RESOURCE_STATUSES[rc]}")
    if rc != 0:
        if POSIX and -rc in _RESOURCE_SIGNALS:
            return ChildOutcome("resource", f"killed by signal {signal.Signals(-rc).name}")
        if rc == 86:
            return ChildOutcome("resource", "MemoryError in harness")
        return ChildOutcome("malformed", f"child exited with status {rc} without a result")
    return _parse(raw, nonce)


def _stream_case(line: bytes, nonce: str, index: int) -> list[Any] | None:
    """[output] of a streamed case line for case `index`, else None (the list
    keeps a JSON null output distinct from 'not a case line')."""
    try:
        msg = json.loads(line)
    except (ValueError, RecursionError):
        return None
    if (isinstance(msg, dict) and len(msg) == 4 and msg.get("nonce") == nonce and msg.get("status") == "case"
            and type(msg.get("case")) is int and msg["case"] == index and "output" in msg):
        return [msg["output"]]
    return None


def _with_matched(out: ChildOutcome, matched: int, n: int) -> ChildOutcome:
    """A streamed run's terminal outcome: "ok" only if every case was streamed and
    matched and the terminal line carries no outputs of its own."""
    if out.kind == "ok":
        if matched != n or out.outputs != []:
            return ChildOutcome("malformed", f"streamed {matched} of {n} cases before the end", matched=matched)
        return ChildOutcome("ok", "", outputs=None, matched=matched)
    return dataclasses.replace(out, matched=matched)


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
    sandbox: Sandbox = "none",
    fail_fast: bool = False,
    early_stop: bool = False,
    stats: dict[str, Any] | None = None,
) -> VerifierReceipt:
    """Verify an artifact body {"source": str, ...} against `task`; return a receipt.

    `cost_units` is verifier wall-clock seconds by default. For replayable
    runs pass `charge_per_case`: the receipt then charges a deterministic
    `charge_per_case * number_of_cases` and the caller reports wall time
    separately. With `fail_fast`, a FAIL caused by a specific case (an output
    mismatch or an exception) is charged only for the cases up to and
    including the first failing one, in suite order (visible, then hidden),
    as a test runner that stops at the first failure would be. Verdicts are
    unchanged; PASS and INCONCLUSIVE are always charged in full.

    `early_stop` makes that physical: expected outputs are computed one case
    at a time and the candidate's run is streamed and stopped at the first
    mismatch (`run_candidate(expected=...)`). It implies `fail_fast`
    charging. PASS verdicts are unchanged. A FAIL's reason no longer counts
    all mismatching cases, and a candidate that fails one case and would
    later time out or exhaust a resource is FAIL instead of INCONCLUSIVE.
    `stats`, if given, receives `child_cpu_seconds` (see `run_candidate`).

    `sandbox="docker"` executes the candidate in the pinned container and
    yields trust class V2, but only if it actually ran there; otherwise the
    receipt is INCONCLUSIVE, trust class V1, and says the candidate was not
    executed. It never falls back to `sandbox="none"`.
    """
    _check_sandbox(sandbox)
    start = time.perf_counter()
    if artifact_digest is None:
        artifact_digest = artifact_digest_for(spec_digest, task_id or task.name, body)
    executed_in_sandbox = False

    def receipt(verdict: str, reason: str) -> VerifierReceipt:
        if sandbox == "none":
            trust, note = TRUST_CLASS, ISOLATION_NOTE
        elif executed_in_sandbox:
            trust, note = TRUST_CLASS_SANDBOXED, DOCKER_ISOLATION_NOTE.format(memory=task.memory_limit_mb)
        else:
            trust, note = TRUST_CLASS, DOCKER_NOT_RUN_NOTE
        return VerifierReceipt(
            spec_digest=spec_digest,
            artifact_digest=artifact_digest,
            verdict=verdict,  # type: ignore[arg-type]
            trust_class=trust,  # type: ignore[arg-type]
            verifier_id=VERIFIER_ID,
            verifier_version=VERIFIER_VERSION,
            reason=f"{note} {task.name} v{task.version}: {reason}",
            cost_units=round(time.perf_counter() - start, 6) if charge_per_case is None else charge,
        )

    n_cases = len(task.visible) + len(task.hidden_inputs(seed))
    charge = round((charge_per_case or 0.0) * n_cases, 9)
    source = body.get("source")
    if not isinstance(source, str):
        return receipt("FAIL", "artifact body has no string 'source'")
    inputs = [list(a) for a, _ in task.visible] + task.hidden_inputs(seed)
    n_vis = len(task.visible)
    fail_fast = fail_fast or early_stop

    def expected_at(i: int) -> Any:
        return json.loads(canonical_json(task.reference(*copy.deepcopy(inputs[i]))))

    expected = None if early_stop else [expected_at(i) for i in range(len(inputs))]
    out = run_candidate(
        source,
        task.function_name,
        inputs,
        per_call_timeout_s=task.per_call_timeout_s,
        wall_timeout_s=task.wall_timeout_s,
        memory_limit_mb=task.memory_limit_mb,
        sandbox=sandbox,
        expected=(lambda i: canonical_json(expected_at(i))) if early_stop else None,
        stats=stats,
    )
    if out.kind == "sandbox":
        return receipt("INCONCLUSIVE", f"sandbox failure ({out.detail})")
    executed_in_sandbox = sandbox == "docker"
    if out.kind == "timeout":
        return receipt("INCONCLUSIVE", f"timeout ({out.detail}) {_where(out.case, n_vis)}".rstrip())
    if out.kind == "resource":
        return receipt("INCONCLUSIVE", f"resource exhaustion ({out.detail}) {_where(out.case, n_vis)}")
    if out.kind == "error":
        if fail_fast and charge_per_case is not None and out.case is not None:
            charge = round(charge_per_case * (out.case + 1), 9)
        return receipt("FAIL", f"candidate raised {out.detail} {_where(out.case, n_vis)}")
    if out.kind == "mismatch" and out.case is not None:
        if charge_per_case is not None:
            charge = round(charge_per_case * (out.case + 1), 9)
        return receipt("FAIL", f"output mismatch (first {_where(out.case, n_vis)}; stopped early)")
    if early_stop and out.kind == "ok":
        return receipt("PASS", f"all {len(inputs)} cases match ({n_vis} visible, {len(inputs) - n_vis} hidden, seed {seed})")
    if out.kind != "ok" or out.outputs is None or expected is None:
        return receipt("FAIL", f"malformed result: {out.detail}")
    if len(out.outputs) != len(expected):
        return receipt("FAIL", f"malformed result: {len(out.outputs)} outputs for {len(expected)} cases")
    bad = [i for i, (got, want) in enumerate(zip(out.outputs, expected)) if _canon(got) != canonical_json(want)]
    if bad and fail_fast and charge_per_case is not None:
        charge = round(charge_per_case * (bad[0] + 1), 9)
    if bad:
        return receipt("FAIL", f"output mismatch on {len(bad)} of {len(expected)} cases (first {_where(bad[0], n_vis)})")
    return receipt("PASS", f"all {len(expected)} cases match ({n_vis} visible, {len(expected) - n_vis} hidden, seed {seed})")
