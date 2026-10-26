"""Catalog v3: dependency-structured problems, libraries, labels."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from frontier_py.realtasks import deps, worker
from frontier_py.realtasks.catalog import correct_on, hidden_cases
from frontier_py.realtasks.dsl import compose
from frontier_py.realtasks.expressible import expressible
from frontier_py.realtasks.server import handle, library_for

PYTHON_DIR = Path(__file__).resolve().parents[1]

# In-grammar witnesses for live goal tasks (direct and via lemmas). Lemma
# witnesses live in `deps.WITNESS`.
GOAL_WITNESS = {
    "span_pos/direct": "(max([x for x in xs if x>0], default=0) - min([x for x in xs if x>0], default=0))",
    "span_pos/via_maxpos+minpos": "(h_maxpos(xs) - h_minpos(xs))",
    "span_pos/via_positives": "(max(h_positives(xs), default=0) - min(h_positives(xs), default=0))",
    "span_neg/direct": "(max([x for x in xs if x<0], default=0) - min([x for x in xs if x<0], default=0))",
    "span_neg/via_negatives": "(max(h_negatives(xs), default=0) - min(h_negatives(xs), default=0))",
    "span_abs/direct": "(max([abs(x) for x in xs], default=0) - min([abs(x) for x in xs], default=0))",
    "span_abs/via_abs_all": "(max(h_abs_all(xs), default=0) - min(h_abs_all(xs), default=0))",
    "trimmed_sum/via_trim": "sum(h_trim(xs))",
    "max_times_min/direct": "(max(xs, default=0) * min(xs, default=0))",
    "max_times_min/via_max0+min0": "(h_max0(xs) * h_min0(xs))",
    "sign_balance/direct": "(len([x for x in xs if x>0]) - len([x for x in xs if x<0]))",
    "sign_balance/via_count_neg+count_pos": "(h_count_pos(xs) - h_count_neg(xs))",
    "parity_gap/direct": "(sum([x for x in xs if x%2==0]) - sum([x for x in xs if x%2==1]))",
    "parity_gap/via_sum_even+sum_odd": "(h_sum_even(xs) - h_sum_odd(xs))",
    "energy_gap/direct": "(sum([x*x for x in xs]) - sum([abs(x) for x in xs]))",
    "energy_gap/via_sum_abs+sum_squares": "(h_sum_squares(xs) - h_sum_abs(xs))",
    "extremes_pos_neg/direct": "(max([x for x in xs if x>0], default=0) + min([x for x in xs if x<0], default=0))",
    "extremes_pos_neg/via_maxpos+minneg": "(h_maxpos(xs) + h_minneg(xs))",
    "top_two_sum/via_max0+second_max": "(h_max0(xs) + h_second_max(xs))",
    "top_two_sum/via_drop_max+max0": "(h_max0(xs) + max(h_drop_max(xs), default=0))",
    "trimmed_pos_sum/via_pos_drop_min": "sum(h_pos_drop_min(xs)[:-1])",
    "span_sq_pos/direct": "(max([x*x for x in xs if x>0], default=0) - min([x*x for x in xs if x>0], default=0))",
    "span_sq_pos/via_sq_pos": "(max(h_sq_pos(xs), default=0) - min(h_sq_pos(xs), default=0))",
    "sum_pos/direct": "sum([x for x in xs if x>0])",
    "sum_pos/via_positives": "sum(h_positives(xs))",
    "count_even/direct": "len([x for x in xs if x%2==0])",
    "count_even/via_evens": "len(h_evens(xs))",
    "second_smallest/direct": "(sorted(xs)[1:][0] if sorted(xs)[1:] else 0)",
    "second_smallest/via_drop_min": "(h_drop_min(xs)[0] if h_drop_min(xs) else 0)",
    "second_max/direct": "max(sorted(xs)[:-1], default=0)",
    "second_max/via_drop_max": "max(h_drop_max(xs), default=0)",
    "sum_even_trap/direct": "sum([x for x in xs if x%2==0])",
    "sum_even_trap/via_count_pos": "(sum([x for x in xs if x%2==0]) + (h_count_pos(xs) * 0))",
    "span_trap/direct": "(max(xs, default=0) - min(xs, default=0))",
    "span_trap/via_sum": "((max(xs, default=0) - min(xs, default=0)) + (h_sum(xs) * 0))",
    "sort_desc_trap/direct": "sorted(xs)[::-1]",
    # Live given its lemma, but the lemma (dedupe) is dead, so never eligible.
    "second_distinct/via_dedupe_sorted": "max(h_dedupe_sorted(xs)[:-1], default=0)",
}


def program(name: str) -> str:
    """A task's witness composed with its prerequisites' witnesses."""
    t = deps.BY_NAME[name]
    part = name.split("/", 1)[1]
    body = deps.WITNESS.get(part) if t.role == "lemma" else GOAL_WITNESS.get(name)
    src = (t.ref_source if t.role == "lemma" and body is None else f"def f(xs):\n    return {body}\n")
    assert src is not None, name
    lib = [(deps.BY_NAME[d].helper, program(d)) for d in t.deps]
    return compose(lib, src) if lib else src


def test_shape_and_labels():
    assert 20 <= len(deps.PROBLEMS) <= 30
    assert len(deps.BY_NAME) == len(deps.TASKS), "task names are unique"
    assert {p.label for p in deps.PROBLEMS} == {"lemma_useful", "direct_easy", "trap", "dead"}
    statuses = {"solvable", "trap", "inexpressible", "misspecified"}
    for p in deps.PROBLEMS:
        names = {t.name for t in p.tasks}
        assert deps.task_name(p.pid, "direct") in names
        assert p.routes, p.pid
        helpers = [t.helper for t in p.tasks if t.role == "lemma"]
        assert len(helpers) == len(set(helpers))
        for t in p.tasks:
            assert t.status in statuses, t.name
            assert all(d in names and deps.BY_NAME[d].role == "lemma" for d in t.deps), t.name
            assert (t.role == "lemma") == (t.helper is not None)
    assert sum(p.label == "trap" for p in deps.PROBLEMS) >= 3
    assert sum(p.label == "dead" for p in deps.PROBLEMS) >= 3


def test_live_tasks_have_witnesses_that_pass_their_hidden_suites():
    for t in deps.TASKS:
        if t.status in deps.DEAD_V3:
            continue
        assert correct_on(program(t.name), hidden_cases(t, "2")), t.name


def test_dead_labels():
    # Misspecified: the stated function fails the hidden suite.
    noisy = deps.BY_NAME["noisy_span/direct"]
    assert not correct_on(program("span_trap/direct"), hidden_cases(noisy, "2"))
    assert all(noisy.reference(list(xs)) == out for xs, out in noisy.visible), "examples agree with the statement"
    # Inexpressible (spot checks; the catalog builder checks every label).
    assert not expressible("int", deps.BY_NAME["trimmed_sum/direct"].reference)
    lib = {"h_count": ("int", len)}
    assert not expressible("list", deps.BY_NAME["sort_desc_trap/via_count"].reference, lib)
    assert expressible("int", deps.BY_NAME["trimmed_sum/via_trim"].reference, {"h_trim": ("list", lambda xs: sorted(xs)[1:][:-1])})


def test_compose_matches_rust_fixture():
    # Same fixture as `compose_program_matches_python` in crates/frontier-sim/tests/deps.rs.
    lib = [("h_b", "def f(xs):\n    return len(xs)\n"), ("h_a", "def f(xs):\n    return sum(xs)")]
    got = compose(lib, "def f(xs):\n    return (h_a(xs) - h_b(xs))\n")
    assert got == ("def f(xs):\n    return sum(xs)\nh_a = f\n"
                   "def f(xs):\n    return len(xs)\nh_b = f\n"
                   "def f(xs):\n    return (h_a(xs) - h_b(xs))\n")


def _lib(name: str) -> list[worker.LibEntry]:
    t = deps.BY_NAME[name]
    return [worker.LibEntry(deps.BY_NAME[d].helper, deps.BY_NAME[d].kind, program(d)) for d in t.deps]


def test_library_attempts_are_deterministic_and_call_helpers():
    t = deps.BY_NAME["max_times_min/via_max0+min0"]
    lib = _lib(t.name)
    a = worker.attempt(t, 5, 3, lib)
    assert a == worker.attempt(t, 5, 3, list(reversed(lib))), "order of library entries is irrelevant"
    assert "h_max0(" in a["source"] or "h_min0(" in a["source"]
    # Output depends on library contents: a wrong helper changes what matches.
    bad = [worker.LibEntry(e.name, e.kind, "def f(xs):\n    return 0\n") for e in lib]
    runs = [worker.attempt(t, 5, k, lib)["source"] for k in range(8)]
    assert runs != [worker.attempt(t, 5, k, bad)["source"] for k in range(8)]
    ok = sum(correct_on(compose([(e.name, e.source) for e in lib], s), hidden_cases(t, "2")) for s in runs)
    assert ok >= 4, "with verified lemmas the dependent goal is easy"


def test_tasks_without_library_use_the_v1_sampler():
    from frontier_py.realtasks.suite import BY_NAME

    t = BY_NAME["sum"]
    assert worker.attempt(t, 3, 7) == worker.attempt(t, 3, 7, ())
    d = deps.BY_NAME["sum_pos/direct"]
    assert all("h_" not in worker.attempt(d, 1, k)["source"] for k in range(5))


def test_server_validates_libraries():
    from frontier_py.realtasks.suite import BY_NAME

    via = deps.BY_NAME["sum_pos/via_positives"]
    good = [{"name": "h_positives", "source": program("sum_pos/positives")}]
    assert [e.name for e in library_for(via, good)] == ["h_positives"]
    for bad in ([], good + good, [{"name": "h_evens", "source": "x"}], [{"name": "h_positives"}], "nope"):
        with pytest.raises(ValueError):
            library_for(via, bad)
    with pytest.raises(ValueError):
        library_for(BY_NAME["sum"], good)  # v1 task: no library allowed
    with pytest.raises(ValueError):
        library_for(deps.BY_NAME["sum_pos/direct"], good)
    assert handle({"op": "attempt", "task": via.name, "seed": 1, "k": 0})["ok"] is False
    assert handle({"op": "attempt", "task": via.name, "seed": 1, "k": 0, "library": good})["ok"] is True


def test_server_protocol_v2_attempt_and_verify_composed_program():
    lemma_src = program("sum_pos/positives")
    goal = "def f(xs):\n    return sum(h_positives(xs))\n"
    composed = compose([("h_positives", lemma_src)], goal)
    reqs = [
        {"op": "hello"},
        {"op": "attempt", "task": "sum_pos/via_positives", "seed": 1, "k": 0, "library": [{"name": "h_positives", "source": lemma_src}]},
        {"op": "verify", "task": "sum_pos/via_positives", "source": composed, "spec_digest": "0" * 64, "artifact_digest": "1" * 64},
        {"op": "verify", "task": "sum_pos/via_positives", "source": goal, "spec_digest": "0" * 64, "artifact_digest": "2" * 64},
    ]
    p = subprocess.run([sys.executable, "-m", "frontier_py.realtasks.server", "--suite-version", "2"],
                       input="\n".join(map(json.dumps, reqs)) + "\n", capture_output=True, text=True, cwd=PYTHON_DIR, timeout=120)
    replies = [json.loads(line) for line in p.stdout.splitlines()]
    assert replies[0]["protocol"] == 2
    assert replies[1]["ok"] and "h_positives(" in replies[1]["source"]
    assert replies[2]["receipt"]["verdict"] == "PASS" and replies[2]["extended_ok"]
    assert replies[3]["receipt"]["verdict"] == "FAIL", "the goal alone cannot call an absent helper"
