"""JSONL worker/verifier service for the Rust runner (protocol version 1).

    python -m frontier_py.realtasks.server [--suite-version 1|2] [--sandbox none|docker]

One JSON object per line on stdin, one reply per line on stdout:

    {"op": "hello"}
        -> {"ok": true, "protocol": 1, "suite_version": ..., "hidden_seed": ..., "sandbox": ...}
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

Sandbox modes (`--sandbox`, default `none`):

* `none`: the receipt comes from the V1 subprocess harness, and the extended
  ground-truth check runs IN THIS PROCESS via `catalog.correct_on`
  (`dsl.compile_program`, restricted builtins but no isolation). That is safe
  only because the programs are the project's own DSL output, which is
  trusted. Do not connect a model-backed worker in this mode.
* `docker`: both the receipt and the extended check execute the candidate in
  the V2 docker sandbox (`verifiers.property_tests`, `sandbox="docker"`); the
  extended inputs are run as one more suite through `verify`, and expected
  outputs are still computed here. No candidate code runs in this process.
  The service refuses to start if the sandbox is unusable, and a verify
  request whose extended check could not run in the sandbox gets an error
  reply rather than a guessed `extended_ok`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from ..tasks import TaskDef
from ..verifiers import property_tests
from ..verifiers.property_tests import SANDBOXES, verify
from .catalog import correct_on, extended_cases
from .suite import BY_NAME, HIDDEN_SEED, SUITE_VERSION, SUITE_VERSIONS
from .worker import attempt

PROTOCOL = 1
VERIFY_UNITS_PER_CASE = 0.005

_suite_version = SUITE_VERSION
_sandbox = "none"
_verify_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
_extended: dict[str, list] = {}


def handle(req: dict[str, Any]) -> dict[str, Any]:
    op = req.get("op")
    if op == "hello":
        return {"ok": True, "protocol": PROTOCOL, "suite_version": _suite_version, "hidden_seed": HIDDEN_SEED, "sandbox": _sandbox}
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
                             artifact_digest=req["artifact_digest"], charge_per_case=VERIFY_UNITS_PER_CASE, sandbox=_sandbox)
            wall = time.perf_counter() - t0
            if task.name not in _extended:
                _extended[task.name] = extended_cases(task)
            _verify_cache[key] = {"ok": True, "receipt": json.loads(receipt.to_json()),
                                  "extended_ok": extended_ok(task, req["source"], _extended[task.name]), "wall_seconds": round(wall, 6)}
            return _verify_cache[key]
        # Memoised: the receipt is identical, but no verification time was spent now.
        return {**_verify_cache[key], "wall_seconds": 0.0, "cached": True}
    return {"ok": False, "error": f"unknown op {op!r}"}


def extended_task(task: Any, cases: list[tuple[list[int], Any]]) -> TaskDef:
    """The extended ground-truth inputs as a TaskDef with no hidden part, for `verify`."""
    base = task.task_def(_suite_version)
    return TaskDef(
        name=f"{base.name}/extended",
        version=base.version,
        function_name=base.function_name,
        statement=base.statement,
        reference=base.reference,
        generate=lambda _rng: [],
        visible=tuple(([list(xs)], want) for xs, want in cases),
        per_call_timeout_s=base.per_call_timeout_s,
        wall_timeout_s=base.wall_timeout_s,
        memory_limit_mb=base.memory_limit_mb,
    )


def extended_ok(task: Any, source: str, cases: list[tuple[list[int], Any]]) -> bool:
    """Ground truth on the extended inputs.

    `--sandbox none`: in-process DSL check (trusted programs only).
    `--sandbox docker`: the candidate runs only inside the sandbox. A run
    that did not execute there raises, so the reply is an error instead of a
    guessed value; a candidate timeout or resource exhaustion counts as not
    correct.
    """
    if _sandbox == "none":
        return correct_on(source, cases)
    r = verify(extended_task(task, cases), {"source": source}, spec_digest="0" * 64, seed=0,
               artifact_digest="0" * 64, charge_per_case=0.0, sandbox=_sandbox)
    if r.trust_class != property_tests.TRUST_CLASS_SANDBOXED:
        raise RuntimeError(f"extended check did not run in the {_sandbox} sandbox: {r.reason}")
    return r.verdict == "PASS"


def configure(argv: list[str]) -> None:
    """Parse arguments and set the service mode; exit if the sandbox is unusable (fail closed)."""
    global _suite_version, _sandbox
    ap = argparse.ArgumentParser(prog="server")
    ap.add_argument("--suite-version", choices=SUITE_VERSIONS, default=SUITE_VERSION)
    ap.add_argument("--sandbox", choices=SANDBOXES, default="none")
    ns = ap.parse_args(argv)
    if ns.sandbox == "docker":
        ok, detail = property_tests.docker_status()
        if not ok:
            sys.exit(f"server: --sandbox docker requested but unusable: {detail}")
    _suite_version, _sandbox = ns.suite_version, ns.sandbox
    _verify_cache.clear()


def main(argv: list[str] | None = None) -> None:
    configure(sys.argv[1:] if argv is None else argv)
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
