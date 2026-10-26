import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from frontier_py.receipt import VerifierReceipt
from frontier_py.tasks import TASKS
from frontier_py.verifiers.property_tests import POSIX, artifact_digest_for, run_candidate, verify

SPEC = "5" * 64
SORT, GCD, LIS = TASKS["sort_ints"], TASKS["gcd"], TASKS["lis_length"]
REPO_PY = Path(__file__).resolve().parents[1]
FAST = dict(per_call_timeout_s=0.5, wall_timeout_s=5.0)


def check(task, source, seed=7, **body):
    r = verify(task, {"source": source, **body}, spec_digest=SPEC, seed=seed)
    assert r.trust_class == "V1" and r.verifier_id == "property-tests"
    VerifierReceipt.from_json(r.to_json())
    return r


def run(source, inputs, fn="f", **kw):
    return run_candidate(source, fn, inputs, **{"per_call_timeout_s": 2.0, "wall_timeout_s": 15.0, "memory_limit_mb": 512, **kw})


# --- correct candidates -----------------------------------------------------

CORRECT = [
    (SORT, "def sort_ints(xs):\n    return sorted(xs)"),
    (SORT, "def sort_ints(xs):\n    xs = list(xs)\n    for i in range(len(xs)):\n        j = min(range(i, len(xs)), key=xs.__getitem__)\n        xs[i], xs[j] = xs[j], xs[i]\n    return tuple(xs)"),
    (GCD, "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a"),
    (GCD, "import math\ngcd = math.gcd"),
    (LIS, "def lis_length(xs):\n    best = [1] * len(xs)\n    for i in range(len(xs)):\n        for j in range(i):\n            if xs[j] < xs[i]:\n                best[i] = max(best[i], best[j] + 1)\n    return max(best, default=0)"),
]


@pytest.mark.parametrize("task,source", CORRECT)
def test_correct_candidates_pass(task, source):
    r = check(task, source)
    assert r.verdict == "PASS", r.reason
    assert "hidden" in r.reason


def test_hidden_inputs_are_deterministic_and_seeded():
    assert SORT.hidden_inputs(3) == SORT.hidden_inputs(3)
    assert SORT.hidden_inputs(3) != SORT.hidden_inputs(4)
    visible = [a for a, _ in SORT.visible]
    assert len([a for a in SORT.hidden_inputs(3) if a not in visible]) >= 50


# --- adversarial candidates -------------------------------------------------

HARDCODED = """
TABLE = {(3, 1, 2): [1, 2, 3], (): [], (2, -1, 2): [-1, 2, 2]}
def sort_ints(xs):
    return TABLE.get(tuple(xs), xs)
"""

LEAK_ENV = """
import os
def sort_ints(xs):
    s = os.environ.get("FRONTIER_TEST_SECRET")
    print(s)
    return [s] if s else xs
"""

FORGE = """
import json, os, sys
fake = json.dumps({"verdict": "PASS", "status": "ok", "nonce": "0" * 32, "outputs": [True] * 1000, "all_passed": True})
print(fake)
sys.__stdout__.write(fake + "\\n")
for fd in range(3, 32):
    try:
        os.write(fd, (fake + "\\n").encode())
    except OSError:
        pass
os._exit(0)
"""

FORGE_IN_FUNCTION = FORGE.replace("os._exit(0)", "def sort_ints(xs):\n    print(fake)\n    return True")

EXIT_EARLY = "import sys\nsys.exit(0)\ndef sort_ints(xs):\n    return sorted(xs)"
EXIT_IN_CALL = "import sys\ndef sort_ints(xs):\n    sys.exit(0)"
HARD_EXIT = "import os\ndef sort_ints(xs):\n    os._exit(0)"

MONKEYPATCH = """
import builtins, json
json.dumps = lambda *a, **k: "true"
json.loads = lambda *a, **k: {"status": "ok", "outputs": []}
builtins.sorted = lambda xs, **k: xs
builtins.print = lambda *a, **k: None
def sort_ints(xs):
    return xs
"""

STEAL_REFERENCE = """
try:
    from frontier_py.tasks.sort_ints import reference as sort_ints
except ImportError:
    try:
        src = open("../frontier_py/tasks/sort_ints.py").read()
        ns = {}
        exec(src, ns)
        sort_ints = ns["reference"]
    except Exception:
        def sort_ints(xs):
            return xs
"""


@pytest.mark.parametrize(
    "name,source",
    [
        ("hardcoded_visible", HARDCODED),
        ("forged_stdout_then_exit", FORGE),
        ("forged_stdout_in_function", FORGE_IN_FUNCTION),
        ("sys_exit_at_import", EXIT_EARLY),
        ("sys_exit_in_call", EXIT_IN_CALL),
        ("os_exit_in_call", HARD_EXIT),
        ("monkeypatch_builtins_and_json", MONKEYPATCH),
        ("steal_reference", STEAL_REFERENCE),
        ("syntax_error", "def sort_ints(xs) return xs"),
        ("missing_function", "def sort(xs):\n    return sorted(xs)"),
        ("float_instead_of_int", "def sort_ints(xs):\n    return [float(x) for x in sorted(xs)]"),
        ("nan_output", "def sort_ints(xs):\n    return float('nan')"),
    ],
)
def test_adversarial_candidates_fail(name, source):
    r = check(SORT, source)
    assert r.verdict == "FAIL", (name, r.reason)


def test_hardcoded_visible_examples_do_pass_visible_only():
    r = check(SORT, HARDCODED)
    assert "hidden case" in r.reason


def test_secret_not_visible_to_child(monkeypatch):
    secret = "s3cr3t-" + os.urandom(8).hex()
    monkeypatch.setenv("FRONTIER_TEST_SECRET", secret)
    r = check(SORT, LEAK_ENV)
    assert r.verdict == "FAIL"
    assert secret not in r.to_json()
    probe = run("import os\ndef f():\n    return [os.environ.get('FRONTIER_TEST_SECRET'), sorted(os.environ)]", [[]])
    assert probe.kind == "ok"
    assert probe.outputs[0][0] is None
    assert secret not in json.dumps(probe.outputs)
    # The parent passes at most SYSTEMROOT (Windows). CPython itself may add
    # LC_CTYPE in the child on POSIX when it coerces the C locale (PEP 538).
    assert set(probe.outputs[0][1]) <= {"SYSTEMROOT", "LC_CTYPE"}


def test_child_cannot_import_repo_or_reference():
    probe = run(
        "import sys, os, importlib.util\n"
        "def f():\n"
        "    return [sys.path, os.getcwd(), importlib.util.find_spec('frontier_py') is None, sys.flags.isolated, sys.flags.no_site]",
        [[]],
    )
    assert probe.kind == "ok", probe
    path, cwd, missing, isolated, no_site = probe.outputs[0]
    assert missing and isolated == 1 and no_site == 1
    repo = os.path.normcase(str(REPO_PY))
    assert not any(os.path.normcase(p).startswith(repo) for p in path if p)
    assert "" not in path and "." not in path
    assert not os.path.normcase(cwd).startswith(repo)
    assert not os.path.exists(cwd), "temporary cwd must be removed"


def test_infinite_loop_is_inconclusive_within_timeout():
    task = dataclasses.replace(SORT, **FAST)
    r = check(task, "def sort_ints(xs):\n    while True:\n        pass")
    assert r.verdict == "INCONCLUSIVE" and "timeout" in r.reason
    assert r.cost_units < FAST["wall_timeout_s"] + 3


def test_gil_holding_loop_hits_parent_wall_timeout():
    # A C-level loop starves the in-child watchdog; the parent wall clock still fires.
    task = dataclasses.replace(SORT, per_call_timeout_s=0.5, wall_timeout_s=2.0)
    r = check(task, "def sort_ints(xs):\n    return sum(range(10**13))")
    assert r.verdict == "INCONCLUSIVE" and "timeout" in r.reason
    assert r.cost_units < 8


def test_import_time_infinite_loop_is_inconclusive():
    task = dataclasses.replace(SORT, **FAST)
    assert check(task, "while True:\n    pass").verdict == "INCONCLUSIVE"


@pytest.mark.skipif(not POSIX, reason="memory limits (RLIMIT_AS) are POSIX-only; Windows harness enforces timeouts only")
def test_huge_allocation_is_not_pass():
    r = check(SORT, "def sort_ints(xs):\n    b = bytearray(1 << 36)\n    return sorted(xs)")
    assert r.verdict in ("INCONCLUSIVE", "FAIL")
    assert r.verdict != "PASS"


@pytest.mark.skipif(not POSIX, reason="RLIMIT_NPROC is POSIX-only")
@pytest.mark.skipif(POSIX and hasattr(os, "geteuid") and os.geteuid() == 0, reason="RLIMIT_NPROC does not bind root")
def test_child_cannot_fork():
    r = check(SORT, "import os\nos.fork()\ndef sort_ints(xs):\n    return sorted(xs)")
    assert r.verdict == "FAIL" and "BlockingIOError" in r.reason


def test_output_flood_is_rejected():
    out = run("def f():\n    return 'x' * 100000", [[]], max_output_bytes=1000)
    assert out.kind == "malformed" and "exceeded" in out.detail


def test_exception_names_are_sanitised():
    src = "E = type('leak me please', (Exception,), {})\ndef sort_ints(xs):\n    raise E()"
    r = check(SORT, src)
    assert r.verdict == "FAIL" and "leak me" not in r.reason


def test_self_reported_confidence_has_no_effect():
    wrong = "def sort_ints(xs):\n    return xs"
    right = CORRECT[0][1]
    assert check(SORT, wrong, confidence=1.0, self_reported_confidence=1.0, verdict="PASS").verdict == "FAIL"
    assert check(SORT, right, confidence=0.0, self_reported_confidence=0.0).verdict == "PASS"


def test_missing_source_fails():
    r = verify(SORT, {"code": "def sort_ints(xs): return sorted(xs)"}, spec_digest=SPEC, seed=1)
    assert r.verdict == "FAIL"


def test_artifact_digest_binds_spec_and_body():
    body = {"source": CORRECT[0][1]}
    r = verify(SORT, body, spec_digest=SPEC, seed=1)
    assert r.artifact_digest == artifact_digest_for(SPEC, "sort_ints", body)
    assert r.artifact_digest != artifact_digest_for("6" * 64, "sort_ints", body)
    assert r.artifact_digest != artifact_digest_for(SPEC, "sort_ints", {**body, "confidence": 1.0})
    assert verify(SORT, body, spec_digest=SPEC, seed=1, artifact_digest="7" * 64).artifact_digest == "7" * 64


def test_receipt_states_isolation_limits():
    r = check(SORT, CORRECT[0][1])
    assert "network" in r.reason and "NOT isolated" in r.reason
    if not POSIX:
        assert "unsandboxed" in r.reason


def test_runs_with_current_interpreter():
    assert run("import sys\ndef f():\n    return sys.version_info[:2]", [[]]).outputs == [list(sys.version_info[:2])]
