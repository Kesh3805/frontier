"""Integration tests for the V2 docker sandbox (real containers).

Skipped unless a Linux docker engine is reachable and the pinned image is
present (`docker pull <SANDBOX_IMAGE>`). Set FRONTIER_REQUIRE_DOCKER=1 to
turn the skip into a failure; the `verifier-v2` CI job does, so these tests
cannot pass there by being skipped.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from frontier_py.tasks import TASKS
from frontier_py.verifiers import property_tests as pt

PYTHON_DIR = Path(__file__).resolve().parents[1]
SPEC = "5" * 64
SORT = TASKS["sort_ints"]
CANARY = "frontier-canary-7f3a9c"

_OK, _DETAIL = pt.docker_status()
if not _OK and os.environ.get("FRONTIER_REQUIRE_DOCKER") == "1":
    raise RuntimeError(f"FRONTIER_REQUIRE_DOCKER=1 but the docker sandbox is unusable: {_DETAIL}")
pytestmark = [pytest.mark.docker, pytest.mark.skipif(not _OK, reason=f"docker sandbox unavailable: {_DETAIL}")]


def probe(body: str):
    """Run `def f(): <body>` once in the sandbox and return its single output."""
    src = "def f():\n" + "".join(f"    {line}\n" for line in body.strip("\n").splitlines())
    out = pt.run_candidate(src, "f", [[]], per_call_timeout_s=10.0, wall_timeout_s=30.0, memory_limit_mb=256, sandbox="docker")
    assert out.kind == "ok", out
    return out.outputs[0]


def verify(source: str, task=SORT):
    return pt.verify(task, {"source": source}, spec_digest=SPEC, seed=7, sandbox="docker")


def test_correct_program_passes_with_v2():
    r = verify("def sort_ints(xs):\n    return sorted(xs)")
    assert r.verdict == "PASS" and r.trust_class == "V2", r.reason
    assert pt.SANDBOX_IMAGE in r.reason


def test_wrong_program_fails_with_v2():
    r = verify("def sort_ints(xs):\n    return list(xs)")
    assert r.verdict == "FAIL" and r.trust_class == "V2"


def test_network_is_unreachable():
    got = probe("""
import socket
res = []
for host, port in (("1.1.1.1", 53), ("8.8.8.8", 443)):
    try:
        socket.create_connection((host, port), timeout=3).close()
        res.append("connected")
    except OSError as e:
        res.append("blocked")
try:
    socket.getaddrinfo("example.com", 80)
    res.append("resolved")
except OSError:
    res.append("no-dns")
return res
""")
    assert got == ["blocked", "blocked", "no-dns"]


def test_only_tmp_is_writable():
    got = probe("""
res = {}
for path in ("/sandbox-escape", "/etc/escape", "/usr/local/lib/escape", "/home/escape", "/var/tmp/escape", "/root/escape",
             "/dev/shm/escape", "/dev/escape", "/run/escape"):
    try:
        with open(path, "w") as fh:
            fh.write("x")
        res[path] = "written"
    except OSError:
        res[path] = "denied"
with open("/tmp/ok", "w") as fh:
    fh.write("x")
res["/tmp/ok"] = "written"
return res
""")
    assert got.pop("/tmp/ok") == "written"
    assert set(got.values()) == {"denied"}, got


def test_tmp_is_size_limited_and_noexec():
    got = probe("""
import os
res = []
try:
    with open("/tmp/big", "wb") as fh:
        for _ in range(64):
            fh.write(b"x" * (1 << 20))
    res.append("wrote 64MiB")
except OSError:
    res.append("bounded")
os.remove("/tmp/big") if os.path.exists("/tmp/big") else None
with open("/tmp/run.sh", "w") as fh:
    fh.write("#!/bin/sh\\necho hi\\n")
os.chmod("/tmp/run.sh", 0o755)
res.append(os.access("/tmp/run.sh", os.X_OK))
return res
""")
    assert got == ["bounded", False]


def test_host_files_are_not_visible():
    got = probe(f"""
import os
res = {{}}
res["repo"] = os.path.exists({str(PYTHON_DIR)!r})
res["repo_posix"] = os.path.exists({PYTHON_DIR.as_posix()!r})
try:
    import frontier_py
    res["import"] = "imported"
except ImportError:
    res["import"] = "absent"
hits = []
for root, dirs, files in os.walk("/"):
    if root.startswith(("/proc", "/sys", "/dev")):
        dirs[:] = []
        continue
    if "frontier_py" in dirs or "property_tests.py" in files:
        hits.append(root)
res["hits"] = hits
return res
""")
    assert got == {"repo": False, "repo_posix": False, "import": "absent", "hits": []}


def test_secret_env_var_is_not_visible(monkeypatch):
    monkeypatch.setenv("FRONTIER_SECRET_CANARY", CANARY)
    got = probe("""
import os
return sorted(os.environ.items())
""")
    assert CANARY not in json.dumps(got)
    assert "FRONTIER_SECRET_CANARY" not in dict(got)


def test_runs_unprivileged():
    got = probe("""
import os
caps = [l for l in open("/proc/self/status") if l.startswith(("CapEff", "NoNewPrivs"))]
return [os.getuid(), os.getgid(), caps]
""")
    uid, gid, caps = got
    assert (uid, gid) == (65534, 65534)
    assert "CapEff:\t0000000000000000\n" in caps and "NoNewPrivs:\t1\n" in caps


def test_fork_bomb_is_bounded():
    src = """
import os
def sort_ints(xs):
    pids = []
    while True:
        pids.append(os.fork())
"""
    t0 = time.monotonic()
    r = verify(src)
    assert r.verdict in ("FAIL", "INCONCLUSIVE") and r.trust_class == "V2", r.reason
    assert time.monotonic() - t0 < SORT.wall_timeout_s + pt.DOCKER_STARTUP_GRACE_S + 15


def test_thread_and_subprocess_spawning_is_bounded():
    got = probe("""
import subprocess, threading
res = []
try:
    subprocess.run(["true"])
    res.append("spawned")
except OSError:
    res.append("no-spawn")
started = 0
try:
    for _ in range(200):
        threading.Thread(target=lambda: __import__("time").sleep(5), daemon=True).start()
        started += 1
except RuntimeError:
    pass
res.append(started < 64)
return res
""")
    assert got == ["no-spawn", True]


def test_memory_hog_is_bounded():
    src = """
def sort_ints(xs):
    hog = []
    while True:
        hog.append(bytearray(32 << 20))
"""
    t0 = time.monotonic()
    r = verify(src)
    assert r.verdict == "INCONCLUSIVE" and r.trust_class == "V2", r.reason
    assert "resource exhaustion" in r.reason
    assert time.monotonic() - t0 < SORT.wall_timeout_s + pt.DOCKER_STARTUP_GRACE_S + 15


def _no_containers_left(within_s: float = 15.0) -> bool:
    deadline = time.monotonic() + within_s
    while True:
        left = subprocess.run(["docker", "ps", "-aq", "--filter", "name=frontier-verify-"], capture_output=True, text=True, check=False)
        if left.returncode == 0 and left.stdout.strip() == "":
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.5)


def test_infinite_loop_times_out_and_container_is_removed():
    r = verify("def sort_ints(xs):\n    while True:\n        pass")
    assert r.verdict == "INCONCLUSIVE" and r.trust_class == "V2" and "timeout" in r.reason
    assert _no_containers_left()


def test_gil_hog_is_killed_from_the_parent():
    # sum() over a huge range holds the GIL, starving the in-container watchdog;
    # the parent's wall timeout (docker kill) or the CPU ulimit must end it.
    src = "def f():\n    return sum(range(10 ** 13))\n"
    t0 = time.monotonic()
    out = pt.run_candidate(src, "f", [[]], per_call_timeout_s=1.0, wall_timeout_s=3.0, memory_limit_mb=256, sandbox="docker")
    assert out.kind in ("timeout", "resource"), out
    assert time.monotonic() - t0 < 3.0 + pt.DOCKER_STARTUP_GRACE_S + 15
    assert _no_containers_left()


def test_server_docker_mode_end_to_end():
    reqs = [
        {"op": "hello"},
        {"op": "verify", "task": "sum", "source": "def f(xs):\n    return sum(xs)\n", "spec_digest": "0" * 64, "artifact_digest": "1" * 64},
        {"op": "verify", "task": "noisy_sum", "source": "def f(xs):\n    return sum(xs)\n", "spec_digest": "0" * 64, "artifact_digest": "2" * 64},
    ]
    p = subprocess.run([sys.executable, "-m", "frontier_py.realtasks.server", "--sandbox", "docker"],
                       input="\n".join(map(json.dumps, reqs)) + "\n", capture_output=True, text=True, cwd=PYTHON_DIR, timeout=300)
    replies = [json.loads(line) for line in p.stdout.splitlines()]
    assert replies[0]["sandbox"] == "docker"
    assert replies[1]["receipt"]["trust_class"] == "V2" and replies[1]["receipt"]["verdict"] == "PASS" and replies[1]["extended_ok"]
    assert replies[2]["receipt"]["verdict"] == "FAIL" and not replies[2]["extended_ok"]
