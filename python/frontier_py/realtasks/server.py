"""JSONL worker/verifier service for the Rust runner (protocol version 2).

    python -m frontier_py.realtasks.server [--suite-version 1|2] [--sandbox none|docker] [--fail-fast | --early-stop]
        [--worker dsl|llm-pool --pool POOL.jsonl]

One JSON object per line on stdin, one reply per line on stdout:

    {"op": "hello"}
        -> {"ok": true, "protocol": 2, "suite_version": ..., "hidden_seed": ..., "sandbox": ...,
            "worker": STR, "pool_sha256": HEX|null}
    {"op": "attempt", "task": NAME, "seed": INT, "k": INT [, "library": [{"name": STR, "source": STR}, ...]]}
        -> {"ok": true, "source": STR, "gen_units": FLOAT, "samples": INT, "visible_pass": BOOL|null [, "j": INT]}
    {"op": "verify", "task": NAME, "source": STR, "spec_digest": HEX, "artifact_digest": HEX}
        -> {"ok": true, "receipt": {...}, "extended_ok": BOOL, "wall_seconds": FLOAT,
            "child_cpu_seconds": FLOAT|null}

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

Workers (`--worker`, default `dsl`):

* `dsl`: the deterministic DSL search (`worker.attempt`). `hello` reports
  `"worker": "dsl-search"` and `"pool_sha256": null`.
* `llm-pool`: replay of a recorded sample pool (`pool.Pool`, ADR-0008).
  `attempt(task, seed, k)` returns pool sample j = pi(task, seed)(k), a
  SHA-256-seeded permutation of the task's sample indices that does not
  depend on the policy; k beyond the pool is an error. `gen_units` is the
  pool's rate card applied to the call's recorded token usage, so replay is
  deterministic. `visible_pass` is null (computing it would execute model
  code here) and `j` is the sample used. The pool's integrity is checked at
  start-up. This mode has no transport and needs no API key. It refuses
  `--sandbox none`, because model-written code may only run sandboxed,
  unless `--allow-unsandboxed-for-tests` is given AND the pool came from
  the fake transport (DSL programs, trusted). `hello` reports
  `"worker": "llm-pool:<provider>/<model>@<revision>"` and the pool's
  SHA-256; the Rust runner records that label on every submission.

Fail-fast (`--fail-fast`) only changes the charge: a FAIL is charged up to
its first failing case, but the candidate still runs on every case.
`--early-stop` makes it physical: the candidate's run is streamed and
stopped at the first mismatch (`verify(early_stop=True)`), with the same
charges. PASS verdicts and every charge are the same as with `--fail-fast`;
only FAIL reasons differ (they no longer count every mismatching case), as
would a candidate that fails a case and later times out (FAIL, not
INCONCLUSIVE; not seen with DSL programs).

Measured cost: each fresh `verify` reply carries its wall time and the CPU
time of the verifier's child process (POSIX: `getrusage` children delta;
Windows: GetProcessTimes, in 15.6 ms ticks; a candidate that never started
reports null). With `--sandbox docker` the child is the
docker CLI, so container CPU is not included. Memoised replies report 0
for both. The runner keeps both out of the deterministic log.
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
from . import deps
from .pool import Pool, PoolError, sandbox_policy
from .catalog import correct_on, extended_cases
from .suite import BY_NAME, HIDDEN_SEED, SUITE_VERSION, SUITE_VERSIONS, RealTask
from .worker import LibEntry, attempt

PROTOCOL = 2
VERIFY_UNITS_PER_CASE = 0.005

_suite_version = SUITE_VERSION
_sandbox = "none"
_fail_fast = False  # charge FAILs only up to the first failing case
_early_stop = False  # also stop the candidate's run at the first failing case
_pool: Pool | None = None  # --worker llm-pool
DSL_WORKER_LABEL = "dsl-search"
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
        return {"ok": True, "protocol": PROTOCOL, "suite_version": _suite_version, "hidden_seed": HIDDEN_SEED, "sandbox": _sandbox,
                "fail_fast": _fail_fast, "early_stop": _early_stop, "worker": DSL_WORKER_LABEL if _pool is None else _pool.label,
                "pool_sha256": None if _pool is None else _pool.sha256}
    name = req.get("task", "")
    task: RealTask | None = BY_NAME.get(name) or deps.BY_NAME.get(name)
    if task is None:
        return {"ok": False, "error": f"unknown task {req.get('task')!r}"}
    if op == "attempt":
        try:
            lib = library_for(task, req.get("library"))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if _pool is not None:
            try:
                return {"ok": True, **_pool.attempt(task.name, int(req["seed"]), int(req["k"]))}
            except PoolError as e:
                return {"ok": False, "error": str(e)}
        return {"ok": True, **attempt(task, int(req["seed"]), int(req["k"]), lib)}
    if op == "verify":
        key = (task.name, req["source"], req["spec_digest"], req["artifact_digest"])
        if key not in _verify_cache:
            t0, stats = time.perf_counter(), {}
            receipt = verify(task.task_def(_suite_version), {"source": req["source"]}, spec_digest=req["spec_digest"], seed=HIDDEN_SEED,
                             artifact_digest=req["artifact_digest"], charge_per_case=VERIFY_UNITS_PER_CASE, sandbox=_sandbox,
                             fail_fast=_fail_fast, early_stop=_early_stop, stats=stats)
            wall, cpu = time.perf_counter() - t0, stats.get("child_cpu_seconds")
            if task.name not in _extended:
                _extended[task.name] = extended_cases(task)
            _verify_cache[key] = {"ok": True, "receipt": json.loads(receipt.to_json()),
                                  "extended_ok": extended_ok(task, req["source"], _extended[task.name]), "wall_seconds": round(wall, 6),
                                  "child_cpu_seconds": None if cpu is None else round(cpu, 6)}
            return _verify_cache[key]
        # Memoised: the receipt is identical, but no verification time was spent now.
        cached = _verify_cache[key]
        return {**cached, "wall_seconds": 0.0, "child_cpu_seconds": None if cached["child_cpu_seconds"] is None else 0.0, "cached": True}
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
    global _suite_version, _sandbox, _fail_fast, _early_stop, _pool
    ap = argparse.ArgumentParser(prog="server")
    ap.add_argument("--suite-version", choices=SUITE_VERSIONS, default=SUITE_VERSION)
    ap.add_argument("--sandbox", choices=SANDBOXES, default="none")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fail-fast", action="store_true", help="charge a failing verification only up to its first failing case")
    mode.add_argument("--early-stop", action="store_true", help="as --fail-fast, and stop the candidate's run at that case")
    ap.add_argument("--worker", choices=("dsl", "llm-pool"), default="dsl")
    ap.add_argument("--pool", help="transcript store to replay (--worker llm-pool)")
    ap.add_argument("--allow-unsandboxed-for-tests", action="store_true", help=argparse.SUPPRESS)
    ns = ap.parse_args(argv)
    pool = None
    if ns.worker == "llm-pool":
        if not ns.pool:
            sys.exit("server: --worker llm-pool needs --pool PATH")
        try:
            pool = Pool(ns.pool)
            sandbox_policy(pool, ns.sandbox, ns.allow_unsandboxed_for_tests)
        except (PoolError, OSError, ValueError) as e:
            sys.exit(f"server: refusing --worker llm-pool: {e}")
    elif ns.pool or ns.allow_unsandboxed_for_tests:
        sys.exit("server: --pool and --allow-unsandboxed-for-tests need --worker llm-pool")
    if ns.sandbox == "docker":
        ok, detail = property_tests.docker_status()
        if not ok:
            sys.exit(f"server: --sandbox docker requested but unusable: {detail}")
    _suite_version, _sandbox, _fail_fast, _early_stop, _pool = ns.suite_version, ns.sandbox, ns.fail_fast, ns.early_stop, pool
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
