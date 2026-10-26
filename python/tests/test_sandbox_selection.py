"""Sandbox selection and fail-closed logic of the property-test verifier.

These run on every platform without docker. Where the docker code path has
to execute, `docker_command` is replaced by a stand-in that runs the harness
locally, so only the parent-side plumbing (protocol, exit-status mapping,
kill on timeout, receipt trust class) is exercised here. Real isolation is
tested in test_sandbox_docker.py.
"""

import re
import sys

import pytest

from frontier_py.realtasks import server
from frontier_py.tasks import TASKS
from frontier_py.verifiers import property_tests as pt

SPEC = "5" * 64
SORT = TASKS["sort_ints"]
GOOD = "def sort_ints(xs):\n    return sorted(xs)"
BAD = "def sort_ints(xs):\n    return list(xs)"
RUN = dict(per_call_timeout_s=2.0, wall_timeout_s=15.0, memory_limit_mb=512)


def _unavailable(monkeypatch, detail="docker engine not reachable"):
    monkeypatch.setattr(pt, "docker_status", lambda: (False, detail))


def _fake_docker(monkeypatch, argv=None):
    """Pretend docker is usable; run `argv` (default: the harness, locally) instead of `docker run`."""
    calls = {"argv": [], "killed": []}

    def command(name, memory_limit_mb, cpu_s):
        calls["argv"].append(name)
        return argv or [sys.executable, "-I", "-S", "-c", pt.HARNESS]

    monkeypatch.setattr(pt, "docker_status", lambda: (True, "ok"))
    monkeypatch.setattr(pt, "docker_command", command)
    monkeypatch.setattr(pt, "_docker_kill", lambda name: calls["killed"].append(name))
    return calls


def _verify(source, sandbox):
    return pt.verify(SORT, {"source": source}, spec_digest=SPEC, seed=7, sandbox=sandbox)


# --- selection ----------------------------------------------------------------


def test_unknown_sandbox_is_rejected():
    with pytest.raises(ValueError):
        pt.run_candidate(GOOD, "sort_ints", [[[1]]], sandbox="gvisor", **RUN)
    with pytest.raises(ValueError):
        _verify(GOOD, "nsjail")


def test_default_is_v1_and_says_so():
    r = pt.verify(SORT, {"source": GOOD}, spec_digest=SPEC, seed=7)
    assert r.verdict == "PASS" and r.trust_class == "V1"
    assert r.reason.startswith("[V1 harness")


# --- fail closed ----------------------------------------------------------------


def test_docker_unavailable_never_executes_or_claims_v2(monkeypatch):
    _unavailable(monkeypatch)
    ran = []
    monkeypatch.setattr(pt.subprocess, "Popen", lambda *a, **k: ran.append(a) or pytest.fail("candidate was started"))
    out = pt.run_candidate(GOOD, "sort_ints", [[[2, 1]]], sandbox="docker", **RUN)
    assert out.kind == "sandbox" and "docker engine not reachable" in out.detail
    r = _verify(GOOD, "docker")
    assert r.verdict == "INCONCLUSIVE" and r.trust_class == "V1"
    assert "NOT executed" in r.reason and "docker engine not reachable" in r.reason
    assert not ran


def test_docker_status_without_cli(monkeypatch):
    monkeypatch.setattr(pt, "DOCKER_BIN", "frontier-no-such-docker-binary")
    ok, detail = pt.docker_status()
    assert not ok and "not found" in detail


def test_docker_infra_failure_is_inconclusive_v1(monkeypatch):
    _fake_docker(monkeypatch, [sys.executable, "-c", "import sys; sys.exit(125)"])
    r = _verify(GOOD, "docker")
    assert r.verdict == "INCONCLUSIVE" and r.trust_class == "V1"
    assert "125" in r.reason and "NOT executed" in r.reason


def test_docker_oom_status_is_resource(monkeypatch):
    _fake_docker(monkeypatch, [sys.executable, "-c", "import sys; sys.exit(137)"])
    r = _verify(GOOD, "docker")
    assert r.verdict == "INCONCLUSIVE" and r.trust_class == "V2" and "resource exhaustion" in r.reason


def test_docker_wall_timeout_kills_container(monkeypatch):
    calls = _fake_docker(monkeypatch, [sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(pt, "DOCKER_STARTUP_GRACE_S", 0.0)
    out = pt.run_candidate(GOOD, "sort_ints", [[[1]]], sandbox="docker", per_call_timeout_s=0.5, wall_timeout_s=1.0, memory_limit_mb=64)
    assert out.kind == "timeout"
    assert calls["killed"] == calls["argv"] and len(calls["killed"]) == 1


# --- protocol over the docker code path (harness run locally) -------------------


def test_docker_path_protocol_and_v2_receipt(monkeypatch):
    _fake_docker(monkeypatch)
    r = _verify(GOOD, "docker")
    assert r.verdict == "PASS" and r.trust_class == "V2", r.reason
    assert r.reason.startswith("[V2 docker sandbox python@sha256:") and "--network none" in r.reason
    r = _verify(BAD, "docker")
    assert r.verdict == "FAIL" and r.trust_class == "V2"


# --- the docker command itself ----------------------------------------------------


def test_docker_command_is_locked_down():
    argv = pt.docker_command("frontier-verify-x", 512, 21)
    joined = " ".join(argv)
    assert re.fullmatch(r"python@sha256:[0-9a-f]{64}", pt.SANDBOX_IMAGE)
    assert argv[:4] == [pt.DOCKER_BIN, "run", "--rm", "-i"]
    for flag in ("--network none", "--ipc none", "--read-only", "--memory 512m", "--memory-swap 512m", "--pids-limit 64", "--cpus 1",
                 "--cap-drop ALL", "--security-opt no-new-privileges", "--user 65534:65534", "--pull never",
                 "--name frontier-verify-x", "--ulimit cpu=21:21"):
        assert flag in joined, flag
    assert any(a.startswith("/tmp:rw,noexec,nosuid,nodev,size=16m") for a in argv)
    for forbidden in ("-v", "--volume", "--mount", "-e", "--env", "--env-file", "--privileged", "--cap-add", "--network=host"):
        assert forbidden not in argv, forbidden
    i = argv.index(pt.SANDBOX_IMAGE)
    assert argv[i + 1:] == ["python", "-I", "-S", "-c", pt.HARNESS]


# --- server ---------------------------------------------------------------------


@pytest.fixture
def restore_server():
    yield
    server.configure([])


def _server_verify(task, source, digest):
    return server.handle({"op": "verify", "task": task, "source": source, "spec_digest": "0" * 64, "artifact_digest": digest})


def test_server_refuses_docker_mode_without_docker(monkeypatch, restore_server):
    _unavailable(monkeypatch, "pinned image not present locally")
    with pytest.raises(SystemExit) as e:
        server.configure(["--sandbox", "docker"])
    assert "pinned image" in str(e.value)


def test_server_docker_mode_runs_extended_check_through_sandbox(monkeypatch, restore_server):
    _fake_docker(monkeypatch)
    in_process = []
    monkeypatch.setattr(server, "correct_on", lambda *a: in_process.append(a) or pytest.fail("extended check ran in-process"))
    server.configure(["--sandbox", "docker"])
    assert server.handle({"op": "hello"})["sandbox"] == "docker"
    ok = _server_verify("sum", "def f(xs):\n    return sum(xs)\n", "1" * 64)
    assert ok["receipt"]["trust_class"] == "V2" and ok["receipt"]["verdict"] == "PASS" and ok["extended_ok"] is True
    bad = _server_verify("noisy_sum", "def f(xs):\n    return sum(xs)\n", "2" * 64)
    assert bad["receipt"]["verdict"] == "FAIL" and bad["extended_ok"] is False
    assert not in_process


def test_server_docker_mode_extended_check_fails_closed(monkeypatch, restore_server):
    _fake_docker(monkeypatch)
    server.configure(["--sandbox", "docker"])
    _unavailable(monkeypatch)
    with pytest.raises(RuntimeError, match="did not run in the docker sandbox"):
        _server_verify("sum", "def f(xs):\n    return sum(xs)\n", "3" * 64)


def test_server_default_mode_keeps_in_process_extended_check(restore_server):
    server.configure([])
    assert server.handle({"op": "hello"})["sandbox"] == "none"
    r = _server_verify("sum", "def f(xs):\n    return sum(xs)\n", "4" * 64)
    assert r["receipt"]["trust_class"] == "V1" and r["extended_ok"] is True
