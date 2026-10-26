import json
import subprocess
import sys
from pathlib import Path

from frontier_py.realtasks import worker
from frontier_py.realtasks.catalog import correct_on, hidden_cases
from frontier_py.realtasks.dsl import compile_program, sample_program
from frontier_py.realtasks.suite import BY_NAME, DEAD, SUITE

PYTHON_DIR = Path(__file__).resolve().parents[1]


def test_suite_shape_and_labels():
    assert len({t.name for t in SUITE}) == len(SUITE)
    assert {t.status for t in SUITE} == {"solvable", "inexpressible", "misspecified", "misleading"}
    assert DEAD == {"inexpressible", "misspecified"}


def test_visible_examples_agree_with_reference_except_misleading():
    for t in SUITE:
        agree = all(t.reference(list(xs)) == out for xs, out in t.visible)
        assert agree == (t.status != "misleading"), t.name


def test_sampler_and_worker_are_deterministic():
    import random

    a = [sample_program(random.Random(5), "int") for _ in range(20)]
    b = [sample_program(random.Random(5), "int") for _ in range(20)]
    assert a == b
    assert worker.attempt(BY_NAME["sum"], 3, 7) == worker.attempt(BY_NAME["sum"], 3, 7)


def test_dsl_expresses_every_solvable_reference_shape():
    # Hand-written DSL programs for a few deep solvable tasks pass the frozen suite.
    progs = {
        "twice_sum_minus_max": "def f(xs):\n    return ((sum(xs) + sum(xs)) - max(xs, default=0))\n",
        "count_nonzero_even": "def f(xs):\n    return len([x for x in [x for x in xs if x>0] if x%2==0])\n",
        "drop_first_sorted": "def f(xs):\n    return sorted(xs)[1:]\n",
    }
    for name, src in progs.items():
        compile_program(src)
        assert correct_on(src, hidden_cases(BY_NAME[name])), name


def test_misleading_task_is_alive_but_search_cannot_use_examples():
    t = BY_NAME["contradictory_sum"]
    assert correct_on("def f(xs):\n    return sum(xs)\n", hidden_cases(t))
    assert not worker.matches("def f(xs):\n    return sum(xs)\n", list(t.visible))


def test_misspecified_task_rejects_the_stated_function():
    t = BY_NAME["noisy_sum"]
    src = "def f(xs):\n    return sum(xs)\n"
    assert worker.matches(src, list(t.visible))
    assert not correct_on(src, hidden_cases(t))


def test_suite_v2_adds_exhaustive_small_inputs_and_rejects_boundary_bug():
    from frontier_py.realtasks.catalog import hidden_cases as hc

    t = BY_NAME["max0"]
    v1, v2 = hc(t, "1"), hc(t, "2")
    assert len(v2) == len(v1) + 156
    bug = "def f(xs):\n    return max([x for x in xs if x!=0], default=0)\n"
    assert correct_on(bug, v1) and not correct_on(bug, v2)


def test_server_protocol():
    reqs = [
        {"op": "hello"},
        {"op": "attempt", "task": "sum", "seed": 1, "k": 0},
        {"op": "verify", "task": "sum", "source": "def f(xs):\n    return sum(xs)\n", "spec_digest": "0" * 64, "artifact_digest": "1" * 64},
        {"op": "verify", "task": "noisy_sum", "source": "def f(xs):\n    return sum(xs)\n", "spec_digest": "0" * 64, "artifact_digest": "2" * 64},
        {"op": "attempt", "task": "nope", "seed": 1, "k": 0},
    ]
    p = subprocess.run([sys.executable, "-m", "frontier_py.realtasks.server"], input="\n".join(map(json.dumps, reqs)) + "\n",
                       capture_output=True, text=True, cwd=PYTHON_DIR, timeout=120)
    replies = [json.loads(line) for line in p.stdout.splitlines()]
    assert replies[0]["protocol"] == 2  # v2 adds libraries; requests without one are unchanged
    assert replies[1]["ok"] and replies[1]["gen_units"] > 0
    assert replies[2]["receipt"]["verdict"] == "PASS" and replies[2]["extended_ok"]
    assert replies[2]["receipt"]["cost_units"] == 0.215  # deterministic charge: 43 cases x 0.005
    assert replies[3]["receipt"]["verdict"] == "FAIL" and not replies[3]["extended_ok"]
    assert replies[4]["ok"] is False
