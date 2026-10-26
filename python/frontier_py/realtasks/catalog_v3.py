"""Build catalog v3: dependency-structured problems (see `deps.py`).

    python -m frontier_py.realtasks.catalog --catalog-version 3 --out ../research/realtasks/catalog-v3.json

Per problem: the goal statement, the problem label, a commitment to every
task's frozen hidden suite, and the tasks of each approach (`direct`, then
`a1`, `a2`, ... for lemma routes). A lemma shared by two routes appears in
each route under its own id with the same signature and worker name; the
task graph merges the copies.

Per task, calibration on `CALIBRATION_SEED` (disjoint from experiment seeds):

* Tasks are calibrated prerequisites first. A dependent task is calibrated
  *conditional on its lemmas being verified*: its attempts receive a library
  built from each prerequisite's first calibration attempt that is correct
  on the hidden and extended suites (`library_source: "calibration"`). A
  prerequisite with no such attempt (a dead lemma) is replaced by its
  hand-written reference program (`"reference"`); that dependent task can
  never become eligible in a run, so its estimate is informational.
* `p_hat`: fraction of attempts whose composed program is correct on the
  frozen hidden suite and 1,000 extended inputs; `mean_gen_units` as v1.
* `hint`: the probe predictor, given the same library (it sees visible
  examples only), with `PROBE_SAMPLES` probes.
* `expressible`: exhaustive grammar check (`expressible.py`). `dead` is the
  ground-truth label (`inexpressible` or `misspecified`); the builder
  refuses to write a catalog whose labels disagree with the check.

Route summaries (`routes`) report, per approach, the expected generation
charge to verify every task once in sequence, sum(mean_gen_units / p_hat),
which is infinite when any task has p_hat = 0.
"""

from __future__ import annotations

import math
from typing import Any

from ..receipt import canonical_digest
from . import deps
from .catalog import CALIBRATION_ATTEMPTS, CALIBRATION_SEED, correct_on, extended_cases, hidden_cases
from .dsl import compose
from .expressible import expressible
from .suite import HIDDEN_SEED
from .worker import MAX_SAMPLES, LibEntry, attempt, probe_hint

CATALOG_VERSION = "3"
SUITE = deps.DEFAULT_SUITE
# Probe size for hints. v1/v2 used 200; with six visible examples a
# visible-passing sample is rarer, and 200 probes put most hints at the
# 0.001 floor regardless of difficulty.
PROBE_SAMPLES = 1000


def _order(p: deps.DepProblem) -> list[deps.DepTask]:
    """Prerequisites before dependents."""
    done: list[str] = []
    by = {t.name: t for t in p.tasks}

    def visit(n: str) -> None:
        if n in done:
            return
        for d in by[n].deps:
            visit(d)
        done.append(n)

    for t in p.tasks:
        visit(t.name)
    return [by[n] for n in done]


def calibrate_task(t: deps.DepTask, accepted: dict[str, tuple[str, str]], attempts: int = CALIBRATION_ATTEMPTS) -> dict[str, Any]:
    """`accepted`: worker name -> (source, how) of calibrated prerequisites.
    Returns the task's estimates and its own first correct program."""
    lib = [LibEntry(deps.BY_NAME[d].helper or "", deps.BY_NAME[d].kind, accepted[d][0]) for d in t.deps]
    pairs = [(e.name, e.source) for e in lib]
    hidden, extended = hidden_cases(t, SUITE), extended_cases(t)
    n_ok = n_hidden_ok = 0
    units = 0.0
    first_correct = None
    for k in range(attempts):
        a = attempt(t, CALIBRATION_SEED, k, lib)
        units += a["gen_units"]
        prog = compose(pairs, a["source"]) if pairs else a["source"]
        if correct_on(prog, hidden):
            n_hidden_ok += 1
            if correct_on(prog, extended):
                n_ok += 1
                first_correct = first_correct or prog
    helpers = {deps.BY_NAME[d].helper or "": (deps.BY_NAME[d].kind, deps.BY_NAME[d].reference) for d in t.deps}
    how = sorted({accepted[d][1] for d in t.deps})
    return {
        "hint": round(probe_hint(t, lib, PROBE_SAMPLES), 6),
        "p_hat": n_ok / attempts,
        "p_hat_hidden_only": n_hidden_ok / attempts,
        "mean_gen_units": round(units / attempts, 6),
        "expressible": expressible(t.kind, t.reference, helpers),
        "library_source": (how[0] if len(how) == 1 else "mixed") if how else None,
        "_first_correct": first_correct,
    }


def build(attempts: int = CALIBRATION_ATTEMPTS, only: set[str] | None = None) -> dict[str, Any]:
    problems = []
    for p in deps.PROBLEMS:
        if only is not None and p.pid not in only:
            continue
        accepted: dict[str, tuple[str, str]] = {}
        cal: dict[str, dict[str, Any]] = {}
        for t in _order(p):
            c = calibrate_task(t, accepted, attempts)
            cal[t.name] = c
            if t.role == "lemma":
                if c["_first_correct"] is not None:
                    accepted[t.name] = (c["_first_correct"], "calibration")
                elif t.ref_source is not None:
                    own = [(deps.BY_NAME[d].helper or "", accepted[d][0]) for d in t.deps]
                    accepted[t.name] = (compose(own, t.ref_source) if own else t.ref_source, "reference")
                else:
                    raise SystemExit(f"lemma {t.name}: no correct calibration attempt and no reference program")
            dead = t.status in deps.DEAD_V3
            if t.status != "misspecified" and c["expressible"] == dead:
                raise SystemExit(f"{t.name}: label {t.status!r} disagrees with the grammar check (expressible={c['expressible']})")
        tasks = []

        def entry(t: deps.DepTask, tid: str, depends_on: list[str], terminal: bool) -> dict[str, Any]:
            c = cal[t.name]
            part = t.name.split("/", 1)[1]
            return {
                "id": tid,
                "name": t.name,
                "role": t.role,
                "signature": f"lemma {part}" if t.role == "lemma" else f"goal {part}",
                "depends_on": depends_on,
                "terminal": terminal,
                "helper": t.helper,
                "kind": t.kind,
                "statement": t.statement,
                "status": t.status,
                "dead": t.status in deps.DEAD_V3,
                **{k: v for k, v in c.items() if not k.startswith("_")},
            }

        tasks.append(entry(deps.BY_NAME[deps.task_name(p.pid, "direct")], "direct", [], True))
        routes = [{"approach": "direct", "tasks": [deps.task_name(p.pid, "direct")]}]
        for i, r in enumerate(p.routes, 1):
            a = f"a{i}"
            chain = p.closure(r.uses)
            for lm in chain:
                t = deps.BY_NAME[deps.task_name(p.pid, lm)]
                tasks.append(entry(t, f"{a}.{lm}", [f"{a}.{d}" for d in p.lemma(lm).deps], False))
            goal = deps.BY_NAME[deps.task_name(p.pid, deps.via_part(r))]
            tasks.append(entry(goal, f"{a}.goal", [f"{a}.{u}" for u in sorted(r.uses)], True))
            routes.append({"approach": a, "tasks": [deps.task_name(p.pid, lm) for lm in chain] + [goal.name]})
        for rt in routes:
            costs = [cal[n]["mean_gen_units"] / cal[n]["p_hat"] if cal[n]["p_hat"] > 0 else math.inf for n in rt["tasks"]]
            rt["expected_gen_units"] = round(sum(costs), 4) if all(map(math.isfinite, costs)) else None
            rt["live"] = all(not deps.BY_NAME[n].status in deps.DEAD_V3 for n in rt["tasks"])
        unique = sorted({t["name"] for t in tasks})
        criterion = canonical_digest({
            "suite": SUITE, "catalog": CATALOG_VERSION, "problem": p.pid, "hidden_seed": HIDDEN_SEED,
            "tasks": [{"task": n, "cases": [[xs, want] for xs, want in hidden_cases(deps.BY_NAME[n], SUITE)]} for n in unique],
        })
        problems.append({
            "problem_id": f"dep.{p.pid}",
            "statement": p.statement,
            "label": p.label,
            "dead": not any(rt["live"] for rt in routes),
            "criterion_sha256": criterion,
            "routes": routes,
            "tasks": tasks,
        })
    return {
        "catalog_version": CATALOG_VERSION,
        "suite_version": SUITE,
        "hidden_seed": HIDDEN_SEED,
        "worker": {"max_samples": MAX_SAMPLES, "calibration_seed": CALIBRATION_SEED, "calibration_attempts": attempts},
        "problems": problems,
    }


def report(cat: dict[str, Any]) -> str:
    lines = []
    for p in cat["problems"]:
        lines.append(f"{p['problem_id']:24s} {p['label']:13s} {'DEAD' if p['dead'] else ''}")
        seen = set()
        for t in p["tasks"]:
            if t["name"] in seen:
                continue
            seen.add(t["name"])
            lines.append(f"    {t['name']:38s} {t['status']:14s} p_hat={t['p_hat']:.3f} hint={t['hint']:.3f} "
                         f"units={t['mean_gen_units']:.2f}{'  lib=' + t['library_source'] if t['library_source'] else ''}")
        for rt in p["routes"]:
            e = rt["expected_gen_units"]
            lines.append(f"      route {rt['approach']:6s} expected units {'inf' if e is None else f'{e:.2f}'}  {' -> '.join(rt['tasks'])}")
    return "\n".join(lines)
