"""JSONL worker/verifier service for the Rust runner (protocol version 1).

    python -m frontier_py.realtasks.server [--suite-version 1|2]

One JSON object per line on stdin, one reply per line on stdout:

    {"op": "hello"}
        -> {"ok": true, "protocol": 1, "suite_version": ..., "hidden_seed": ...}
    {"op": "attempt", "task": NAME, "seed": INT, "k": INT}
        -> {"ok": true, "source": STR, "gen_units": FLOAT, "samples": INT, "visible_pass": BOOL}
    {"op": "verify", "task": NAME, "source": STR, "spec_digest": HEX, "artifact_digest": HEX}
        -> {"ok": true, "receipt": {...}, "extended_ok": BOOL, "wall_seconds": FLOAT}

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
from .catalog import correct_on, extended_cases
from .suite import BY_NAME, HIDDEN_SEED, SUITE_VERSION, SUITE_VERSIONS
from .worker import attempt

PROTOCOL = 1
VERIFY_UNITS_PER_CASE = 0.005

_suite_version = SUITE_VERSION
_verify_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
_extended: dict[str, list] = {}


def handle(req: dict[str, Any]) -> dict[str, Any]:
    op = req.get("op")
    if op == "hello":
        return {"ok": True, "protocol": PROTOCOL, "suite_version": _suite_version, "hidden_seed": HIDDEN_SEED}
    task = BY_NAME.get(req.get("task", ""))
    if task is None:
        return {"ok": False, "error": f"unknown task {req.get('task')!r}"}
    if op == "attempt":
        return {"ok": True, **attempt(task, int(req["seed"]), int(req["k"]))}
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
