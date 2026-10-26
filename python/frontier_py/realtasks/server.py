"""JSONL worker/verifier service for the Rust runner (protocol version 2).

    python -m frontier_py.realtasks.server [--suite-version 1|2]

One JSON object per line on stdin, one reply per line on stdout:

    {"op": "hello"}
        -> {"ok": true, "protocol": 2, "suite_version": ..., "hidden_seed": ...}
    {"op": "attempt", "task": NAME, "seed": INT, "k": INT [, "library": [{"name": STR, "source": STR}, ...]]}
        -> {"ok": true, "source": STR, "gen_units": FLOAT, "samples": INT, "visible_pass": BOOL}
    {"op": "verify", "task": NAME, "source": STR, "spec_digest": HEX, "artifact_digest": HEX}
        -> {"ok": true, "receipt": {...}, "extended_ok": BOOL, "wall_seconds": FLOAT}

Protocol 2 adds the optional `library` of an attempt: the verified helpers
of a dependent (catalog v3) task, one per direct prerequisite, named
`h_<lemma>`, each with the source of the artifact the runner accepted for
that prerequisite. The names must be exactly the prerequisites' helpers: a
library on a task without prerequisites, or a missing, extra or duplicate
helper, is an error. The reply's `source` is the candidate alone; the
runner composes the program that is verified (`dsl.compose`) from the
library it sent. Requests without `library` are answered exactly as in
protocol 1, and v3 task names (`<problem>/<part>`) never collide with v1.

Errors reply {"ok": false, "error": STR}. `verify` runs the real
property-test verifier (a separate interpreter per candidate) against the
frozen hidden suite and charges a deterministic `VERIFY_UNITS_PER_CASE` per
case. `extended_ok` is simulation-style ground truth for measuring verifier
false acceptance: the program is also checked against 1,000 further inputs.
It is not part of the receipt and the runner keeps it out of the audited
log. Replies for identical verify requests are memoised: the verifier is
deterministic for these programs (they always terminate quickly), so this
saves time without changing results. A memoised reply carries
`"cached": true` and `wall_seconds` 0.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from ..verifiers.property_tests import verify
from . import deps
from .catalog import correct_on, extended_cases
from .suite import BY_NAME, HIDDEN_SEED, SUITE_VERSION, SUITE_VERSIONS, RealTask
from .worker import LibEntry, attempt

PROTOCOL = 2
VERIFY_UNITS_PER_CASE = 0.005

_suite_version = SUITE_VERSION
_verify_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
_extended: dict[str, list] = {}


def library_for(task: RealTask, raw: Any) -> list[LibEntry]:
    """Validate an attempt's library against the task's prerequisites."""
    entries = [] if raw is None else raw
    if not isinstance(entries, list) or not all(
        isinstance(e, dict) and isinstance(e.get("name"), str) and isinstance(e.get("source"), str) for e in entries
    ):
        raise ValueError("library must be a list of {name, source}")
    kinds = deps.library_kinds(task) if isinstance(task, deps.DepTask) else {}
    names = [e["name"] for e in entries]
    if sorted(names) != sorted(kinds) or len(set(names)) != len(names):
        raise ValueError(f"library {sorted(names)} does not match the prerequisites' helpers {sorted(kinds)}")
    return [LibEntry(e["name"], kinds[e["name"]], e["source"]) for e in entries]


def handle(req: dict[str, Any]) -> dict[str, Any]:
    op = req.get("op")
    if op == "hello":
        return {"ok": True, "protocol": PROTOCOL, "suite_version": _suite_version, "hidden_seed": HIDDEN_SEED}
    name = req.get("task", "")
    task: RealTask | None = BY_NAME.get(name) or deps.BY_NAME.get(name)
    if task is None:
        return {"ok": False, "error": f"unknown task {req.get('task')!r}"}
    if op == "attempt":
        try:
            lib = library_for(task, req.get("library"))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, **attempt(task, int(req["seed"]), int(req["k"]), lib)}
    if op == "verify":
        key = (task.name, req["source"], req["spec_digest"], req["artifact_digest"])
        if key not in _verify_cache:
            t0 = time.perf_counter()
            receipt = verify(task.task_def(_suite_version), {"source": req["source"]}, spec_digest=req["spec_digest"], seed=HIDDEN_SEED,
                             artifact_digest=req["artifact_digest"], charge_per_case=VERIFY_UNITS_PER_CASE)
            wall = time.perf_counter() - t0
            if task.name not in _extended:
                _extended[task.name] = extended_cases(task)
            _verify_cache[key] = {"ok": True, "receipt": json.loads(receipt.to_json()),
                                  "extended_ok": correct_on(req["source"], _extended[task.name]), "wall_seconds": round(wall, 6)}
            return _verify_cache[key]
        # Memoised: the receipt is identical, but no verification time was spent now.
        return {**_verify_cache[key], "wall_seconds": 0.0, "cached": True}
    return {"ok": False, "error": f"unknown op {op!r}"}


def main() -> None:
    global _suite_version
    args = sys.argv[1:]
    if args[:1] == ["--suite-version"] and len(args) == 2 and args[1] in SUITE_VERSIONS:
        _suite_version = args[1]
    elif args:
        sys.exit(f"usage: server [--suite-version {{{'|'.join(SUITE_VERSIONS)}}}]")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as e:  # noqa: BLE001 - report, never crash the session
            reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
