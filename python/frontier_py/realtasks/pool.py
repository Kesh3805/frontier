"""Sample pools for model-backed workers: estimate, fill, screen, replay.

    python -m frontier_py.realtasks.pool estimate --rate-card RC.json --n N [task options]
    python -m frontier_py.realtasks.pool fill --pool POOL.jsonl --rate-card RC.json --n N \\
        --transport fake --execute --max-usd X --ledger LEDGER.json [task options]
    python -m frontier_py.realtasks.pool screen --pool POOL.jsonl --sandbox docker [--out REPORT.jsonl]

Record once, replay exactly (ADR-0008). `fill` draws N independent samples
per task from a model into an append-only `TranscriptStore` (the pool), and
experiments replay the pool through `server --worker llm-pool`. The k-th
attempt on a task for seed s is pool sample j = pi(task, s)(k), where pi is
a SHA-256-seeded permutation of the task's sample indices (`permutation`).
It does not depend on the policy, so policies compared on one seed see the
same sample sequence, and cost is bounded by tasks x N.

`estimate` makes no call: it counts calls and sums each call's worst case
(prompt UTF-8 bytes + `PROMPT_OVERHEAD_TOKENS` input tokens, the output
cap as output tokens) priced by the rate card. `fill` refuses to run
without `--execute`, and in this version refuses every transport except
`fake` (there is no real transport; see `workers/transport.py`). Every call
goes through a `BudgetGuard` backed by a crash-safe `CampaignLedger`, so it
is reserved at its worst case before it is made. The API key, if a
transport needs one, is read from the environment variable named by
`--api-key-env` at call time and never written anywhere.

`screen` runs every pool sample's visible examples and the extended
ground-truth inputs through the property-test verifier in the requested
sandbox. Model text is never executed in this process. `--sandbox none` is
refused for pools unless `--allow-unsandboxed-for-tests` is given and the
pool was filled by the fake transport (DSL programs, trusted).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..verifiers import property_tests
from ..verifiers.property_tests import SANDBOXES
from ..workers.base import (
    Availability,
    BudgetExceeded,
    BudgetGuard,
    Capabilities,
    Charge,
    GenerationRequest,
    GenerationResult,
    Limits,
    Usage,
    WorkerAdapter,
)
from ..workers.ledger import CampaignLedger
from ..workers.llm_codegen import DEFAULT_TEMPLATE, PROMPT_OVERHEAD_TOKENS, TEMPLATE_VERSIONS, build_prompt, parse_function, try_parse
from ..workers.rate_card import RateCard
from ..workers.transcripts import TranscriptKey, TranscriptRecord, TranscriptStore, prompt_sha256, utc_now
from . import deps
from .dsl import compose
from .suite import BY_NAME, SUITE, RealTask
from .worker import LibEntry

TRANSPORTS = ("fake",)  # a real transport is added only with authorisation (stage2-plan.md, phase 1)
FAKE_PROVIDER = "fake"
FAKE_DSL_SEED = 424_242  # stream of the DSL worker used as a fake model
TASK_SETS = ("pilot", "deps", "all")
UNSANDBOXED_REFUSAL = "model-written code may only run sandboxed (--sandbox docker)"


class PoolError(RuntimeError):
    pass


# --- tasks ------------------------------------------------------------------

def task_by_name(name: str) -> RealTask:
    t = BY_NAME.get(name) or deps.BY_NAME.get(name)
    if t is None:
        raise PoolError(f"unknown task {name!r}")
    return t


def select_tasks(task_set: str = "pilot", names: Sequence[str] | None = None) -> list[RealTask]:
    pool: list[RealTask] = []
    if task_set in ("pilot", "all"):
        pool += list(SUITE)
    if task_set in ("deps", "all"):
        pool += list(deps.TASKS)
    if names:
        wanted = set(names)
        unknown = wanted - {t.name for t in pool}
        if unknown:
            raise PoolError(f"tasks not in set {task_set!r}: {sorted(unknown)}")
        pool = [t for t in pool if t.name in wanted]
    return pool


def reference_library(task: RealTask) -> list[LibEntry]:
    """The library a dependent task would get if each prerequisite were accepted
    with its hand-written reference program (chains composed recursively)."""
    out = []
    for d in getattr(task, "deps", ()):
        t = deps.BY_NAME[d]
        lib = reference_library(t)
        src = t.ref_source or ""
        if lib:
            src = compose([(e.name, e.source) for e in lib], src)
        out.append(LibEntry(t.helper or "", t.kind, src))
    return sorted(out, key=lambda e: e.name)


# --- pricing ----------------------------------------------------------------

def worst_case_tokens(prompt: str, max_output_tokens: int) -> tuple[int, int]:
    return len(prompt.encode("utf-8")) + PROMPT_OVERHEAD_TOKENS, max_output_tokens


def worst_case_usd(rate: RateCard, prompt: str, max_output_tokens: int) -> float:
    tin, tout = worst_case_tokens(prompt, max_output_tokens)
    return rate.usd({"input_tokens": tin, "output_tokens": tout})


def estimate(tasks: Iterable[RealTask], n: int, rate: RateCard, template: str, max_output_tokens: int) -> dict[str, Any]:
    """Calls and worst-case cost of filling `n` samples per task. Makes no call."""
    calls = 0
    worst_usd = 0.0
    worst_tokens = 0
    per_task = []
    for t in tasks:
        p = build_prompt(t, template)
        tin, tout = worst_case_tokens(p, max_output_tokens)
        u = worst_case_usd(rate, p, max_output_tokens)
        calls += n
        worst_usd += n * u
        worst_tokens += n * (tin + tout)
        per_task.append({"task": t.name, "calls": n, "worst_usd_per_call": u, "worst_input_tokens": tin})
    return {"calls": calls, "worst_case_usd": worst_usd, "worst_case_tokens": worst_tokens, "rate_card": rate.version,
            "template_version": template, "max_output_tokens": max_output_tokens, "tasks": per_task}


# --- fill -------------------------------------------------------------------

def make_header(*, provider: str, model: str, model_revision: str, template_version: str, temperature: float, top_p: float,
                max_output_tokens: int, n: int, tasks: Sequence[str], rate: RateCard) -> dict[str, Any]:
    return {
        "provider": provider, "model": model, "model_revision": model_revision, "template_version": template_version,
        "temperature": float(temperature), "top_p": float(top_p), "max_output_tokens": max_output_tokens,
        "n": n, "tasks": list(tasks), "rate_card": rate.to_dict(),
    }


def key_for(header: Mapping[str, Any], task: str, j: int, prompt: str) -> TranscriptKey:
    return TranscriptKey(header["provider"], header["model"], header["model_revision"], header["template_version"],
                         prompt_sha256(prompt), header["temperature"], header["top_p"], header["max_output_tokens"], task, j)


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "[REDACTED]") if secret else text


class TransportFailed(RuntimeError):
    pass


class PoolAdapter(WorkerAdapter):
    """Adapts a `Transport` to `WorkerAdapter`, pricing usage with the rate card.

    The API key is read from `api_key_env` at call time, handed to the
    transport, and never stored; an exception from the transport is re-raised
    as `TransportFailed` with the key redacted and no chained original."""

    def __init__(self, header: Mapping[str, Any], transport: Any, rate: RateCard, api_key_env: str | None) -> None:
        self.header, self.transport, self.rate, self.api_key_env = header, transport, rate, api_key_env
        self.current: tuple[str, int] = ("", 0)
        self.last: Any = None

    def capabilities(self) -> Capabilities:
        h = self.header
        return Capabilities(f"pool:{h['provider']}", h["model"], h["model_revision"], False, False, 0)

    def probe(self) -> Availability:
        if self.api_key_env and not os.environ.get(self.api_key_env):
            return Availability(False, (f"environment variable {self.api_key_env} is not set",))
        return Availability(True)

    def max_charge(self, req: GenerationRequest) -> Charge:
        tin, tout = worst_case_tokens(req.prompt, req.limits.max_output_tokens)
        return Charge(tin + tout, self.rate.usd({"input_tokens": tin, "output_tokens": tout}))

    def generate(self, req: GenerationRequest) -> GenerationResult:
        from ..workers.transport import TransportRequest

        h = self.header
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        task, j = self.current
        treq = TransportRequest(h["provider"], h["model"], h["model_revision"], req.prompt, h["temperature"], h["top_p"],
                                req.limits.max_output_tokens, req.seed, task=task, j=j)
        failure: str | None = None
        try:
            resp = self.transport.complete(treq, key)
        except Exception as e:  # noqa: BLE001 - re-raised below without the original (it may hold the key)
            failure = _redact(f"{type(e).__name__}: {e}", key)
        if failure is not None:
            raise TransportFailed(f"transport call for {task} j={j} failed: {failure}")
        del key
        self.last = resp
        usage = {"input_tokens": int(resp.input_tokens), "output_tokens": int(resp.output_tokens)}
        usd = self.rate.usd(usage)
        if resp.provider_usd is not None:
            usd = max(usd, float(resp.provider_usd))  # charge the larger of the two
        finish = resp.finish_reason if resp.finish_reason in ("stop", "length", "timeout", "error") else "error"
        return GenerationResult(resp.text, None, Usage(input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"], usd=usd),
                                finish)  # type: ignore[arg-type]


def fill(store: TranscriptStore, tasks: Sequence[RealTask], transport: Any, rate: RateCard, ledger: CampaignLedger, *,
         max_usd: float, api_key_env: str | None = None, log=print, clock=utc_now) -> dict[str, Any]:
    """Draw every missing (task, j) sample through the guard and ledger; stop at the first refusal."""
    h = store.header
    n = int(h["n"])
    plan = [(t, j) for t in tasks for j in range(n)]
    prompts = {t.name: build_prompt(t, h["template_version"]) for t in tasks}
    todo = [(t, j) for t, j in plan if key_for(h, t.name, j, prompts[t.name]) not in store]
    worst_tokens = sum(sum(worst_case_tokens(prompts[t.name], h["max_output_tokens"])) for t, _ in todo)
    adapter = PoolAdapter(h, transport, rate, api_key_env)
    guard = BudgetGuard(adapter, max_tokens=max(worst_tokens, 1), max_usd=max_usd, ledger=ledger)
    limits = Limits(max_output_tokens=h["max_output_tokens"], max_latent_steps=0, max_tool_calls=0, wall_seconds=600.0)
    made, stopped = 0, None
    for t, j in todo:
        prompt = prompts[t.name]
        adapter.current = (t.name, j)
        try:
            result = guard.generate(GenerationRequest(prompt=prompt, limits=limits, seed=j, model_revision=h["model_revision"]))
        except BudgetExceeded as e:
            stopped = str(e)
            break
        r = adapter.last
        store.put(TranscriptRecord(
            key=key_for(h, t.name, j, prompt),
            request={"provider": h["provider"], "model": h["model"], "model_revision": h["model_revision"],
                     "template_version": h["template_version"], "prompt": prompt, "temperature": h["temperature"],
                     "top_p": h["top_p"], "max_output_tokens": h["max_output_tokens"], "seed": j},
            text=result.text, input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens,
            usd=rate.usd(result.usage), provider_usd=r.provider_usd, finish_reason=result.finish_reason,
            response_model_id=r.response_model_id, utc=clock(),
        ))
        made += 1
        if ledger.halted:
            stopped = f"ledger halted: {ledger.halted}"
            break
    summary = {"planned": len(plan), "already_stored": len(plan) - len(todo), "calls_made": made, "stopped": stopped,
               "ledger_spent_usd": ledger.spent_usd, "ledger_cap_usd": ledger.cap_usd, "overruns": guard.overruns,
               "pool_sha256": store.sha256(), "complete": len(store) >= len(plan) and stopped is None}
    log(json.dumps(summary, indent=1))
    return summary


def dsl_fake_responses(tasks: Sequence[RealTask]) -> Any:
    """A fake 'model' that answers with the DSL worker's program for (task, j), in a code fence."""
    from .worker import attempt

    by_name = {t.name: t for t in tasks}

    def reply(req: Any) -> str:
        t = by_name[req.task]
        src = attempt(t, FAKE_DSL_SEED, req.j, reference_library(t))["source"]
        return f"Here is the function.\n```python\n{src}```\n"

    return reply


# --- replay -----------------------------------------------------------------

def permutation(task: str, seed: int, n: int) -> list[int]:
    """pi(task, seed): a Fisher-Yates permutation of range(n), each swap drawn from SHA-256."""
    out = list(range(n))
    for i in range(n - 1, 0, -1):
        h = hashlib.sha256(f"frontier-pool-perm|{task}|{seed}|{i}".encode()).digest()
        r = int.from_bytes(h, "little") % (i + 1)
        out[i], out[r] = out[r], out[i]
    return out


@dataclass(frozen=True)
class Sample:
    j: int
    source: str
    input_tokens: int
    output_tokens: int
    parsed: bool  # False: the reply had no usable def f(xs); `source` is the raising stub


class Pool:
    """A verified, read-only view of a transcript store for replay. Never executes anything."""

    def __init__(self, path: str | Path) -> None:
        self.store = TranscriptStore(path)
        problems = self.store.verify()
        if problems:
            raise PoolError(f"pool {path} failed its integrity check: {problems[:3]}")
        self.header = self.store.header
        self.rate = RateCard.from_dict(self.header["rate_card"])
        self.sha256 = self.store.sha256()
        self.samples: dict[str, list[Sample]] = {}
        for rec in sorted(self.store.records(), key=lambda r: (r.key.task, r.key.j)):
            self.samples.setdefault(rec.key.task, []).append(
                Sample(rec.key.j, parse_function(rec.text), rec.input_tokens, rec.output_tokens, try_parse(rec.text) is not None))
        for task, ss in self.samples.items():
            if [s.j for s in ss] != list(range(len(ss))):
                raise PoolError(f"pool {path}: task {task} has non-contiguous sample indices {[s.j for s in ss]}")

    @property
    def label(self) -> str:
        h = self.header
        return f"llm-pool:{h['provider']}/{h['model']}@{h['model_revision']}"

    @property
    def is_fake(self) -> bool:
        return self.header["provider"] == FAKE_PROVIDER

    def sample(self, task: str, seed: int, k: int) -> Sample:
        ss = self.samples.get(task)
        if not ss:
            raise PoolError(f"pool has no samples for task {task!r}")
        if not 0 <= k < len(ss):
            raise PoolError(f"attempt k={k} on {task!r} is beyond the pool's {len(ss)} samples")
        return ss[permutation(task, seed, len(ss))[k]]

    def attempt(self, task: str, seed: int, k: int) -> dict[str, Any]:
        s = self.sample(task, seed, k)
        usage = {"input_tokens": s.input_tokens, "output_tokens": s.output_tokens}
        # visible_pass is unknown: computing it would execute model code here.
        return {"source": s.source, "gen_units": self.rate.cu(usage), "samples": 1, "visible_pass": None, "j": s.j}


def sandbox_policy(pool: Pool, sandbox: str, allow_unsandboxed_for_tests: bool) -> None:
    """Raise unless model code from this pool may run under `sandbox`."""
    if sandbox not in SANDBOXES:
        raise PoolError(f"unknown sandbox {sandbox!r}")
    if sandbox == "none":
        if not allow_unsandboxed_for_tests:
            raise PoolError(UNSANDBOXED_REFUSAL)
        if not pool.is_fake:
            raise PoolError(f"--allow-unsandboxed-for-tests is only for pools from the fake transport, not {pool.header['provider']!r}")


# --- screen -----------------------------------------------------------------

def cases_task(task: RealTask, suffix: str, cases: Sequence[tuple[list[int], Any]]) -> Any:
    from ..tasks import TaskDef

    base = task.task_def()
    return TaskDef(name=f"{base.name}/{suffix}", version=base.version, function_name=base.function_name, statement=base.statement,
                   reference=base.reference, generate=lambda _rng: [], visible=tuple(([list(xs)], want) for xs, want in cases),
                   per_call_timeout_s=base.per_call_timeout_s, wall_timeout_s=base.wall_timeout_s, memory_limit_mb=base.memory_limit_mb)


def screen(pool: Pool, sandbox: str) -> list[dict[str, Any]]:
    """Visible-example and extended checks for every sample, all through the verifier."""
    from .catalog import extended_cases

    rows = []
    for name in sorted(pool.samples):
        task = task_by_name(name)
        lib = [(e.name, e.source) for e in reference_library(task)]
        vis = cases_task(task, "visible", [(list(xs), want) for xs, want in task.visible])
        ext = cases_task(task, "extended", extended_cases(task))
        for s in pool.samples[name]:
            program = compose(lib, s.source) if lib else s.source
            row: dict[str, Any] = {"task": name, "j": s.j, "parsed": s.parsed}
            for what, td in (("visible", vis), ("extended", ext)):
                r = property_tests.verify(td, {"source": program}, spec_digest="0" * 64, seed=0, artifact_digest="0" * 64,
                                          charge_per_case=0.0, sandbox=sandbox)  # type: ignore[arg-type]
                if sandbox == "docker" and r.trust_class != property_tests.TRUST_CLASS_SANDBOXED:
                    raise PoolError(f"{name} j={s.j}: {what} check did not run in the sandbox: {r.reason}")
                row[f"{what}_pass"] = r.verdict == "PASS"
                row[f"{what}_verdict"] = r.verdict
            rows.append(row)
    return rows


# --- CLI --------------------------------------------------------------------

def _task_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--task-set", choices=TASK_SETS, default="pilot")
    ap.add_argument("--tasks", default="", help="comma-separated task names (default: every task in the set)")
    ap.add_argument("--n", type=int, required=True, help="samples per task")
    ap.add_argument("--rate-card", type=Path, required=True)
    ap.add_argument("--template", choices=TEMPLATE_VERSIONS, default=DEFAULT_TEMPLATE)
    ap.add_argument("--max-output-tokens", type=int, default=256)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pool", description=__doc__.split("\n\n")[0] if __doc__ else None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    est = sub.add_parser("estimate", help="count calls and worst-case USD; makes no call")
    _task_args(est)
    fl = sub.add_parser("fill", help="draw samples into the pool (needs --execute)")
    _task_args(fl)
    fl.add_argument("--pool", type=Path, required=True)
    fl.add_argument("--transport", required=True)
    fl.add_argument("--execute", action="store_true")
    fl.add_argument("--max-usd", type=float)
    fl.add_argument("--ledger", type=Path)
    fl.add_argument("--api-key-env", default=None, help="environment variable holding the API key (read at call time)")
    fl.add_argument("--provider", default=FAKE_PROVIDER)
    fl.add_argument("--model", default="dsl-search")
    fl.add_argument("--model-revision", default="fake-1")
    fl.add_argument("--temperature", type=float, default=1.0)
    fl.add_argument("--top-p", type=float, default=1.0)
    sc = sub.add_parser("screen", help="verify every pool sample's visible and extended checks in a sandbox")
    sc.add_argument("--pool", type=Path, required=True)
    sc.add_argument("--sandbox", choices=SANDBOXES, required=True)
    sc.add_argument("--allow-unsandboxed-for-tests", action="store_true", help=argparse.SUPPRESS)
    sc.add_argument("--out", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "screen":
        pool = Pool(a.pool)
        try:
            sandbox_policy(pool, a.sandbox, a.allow_unsandboxed_for_tests)
        except PoolError as e:
            print(f"pool screen: refusing: {e}", file=sys.stderr)
            return 2
        if a.sandbox == "docker":
            ok, detail = property_tests.docker_status()
            if not ok:
                print(f"pool screen: --sandbox docker requested but unusable: {detail}", file=sys.stderr)
                return 2
        rows = screen(pool, a.sandbox)
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(text)
        n = len(rows)
        print(f"screened {n} samples: visible pass {sum(r['visible_pass'] for r in rows)}, "
              f"extended pass {sum(r['extended_pass'] for r in rows)}", file=sys.stderr)
        return 0

    rate = RateCard.load(a.rate_card)
    tasks = select_tasks(a.task_set, [s for s in a.tasks.split(",") if s])
    if a.n <= 0:
        print("pool: --n must be > 0", file=sys.stderr)
        return 2
    est_ = estimate(tasks, a.n, rate, a.template, a.max_output_tokens)
    if a.cmd == "estimate":
        print(json.dumps(est_, indent=1))
        return 0

    # fill
    if a.transport not in TRANSPORTS:
        print(f"pool fill: refusing transport {a.transport!r}: only {TRANSPORTS} exist in this version "
              "(a real transport needs an authorised provider)", file=sys.stderr)
        return 2
    if not a.execute:
        print(json.dumps({k: v for k, v in est_.items() if k != "tasks"}, indent=1))
        print("pool fill: refusing to call without --execute (the estimate above was made with no call)", file=sys.stderr)
        return 2
    if a.max_usd is None or not a.max_usd > 0 or a.ledger is None:
        print("pool fill: --execute needs --max-usd > 0 and --ledger PATH", file=sys.stderr)
        return 2
    if a.transport == "fake" and a.provider != FAKE_PROVIDER:
        print(f"pool fill: the fake transport records provider {FAKE_PROVIDER!r} only", file=sys.stderr)
        return 2
    header = make_header(provider=a.provider, model=a.model, model_revision=a.model_revision, template_version=a.template,
                         temperature=a.temperature, top_p=a.top_p, max_output_tokens=a.max_output_tokens, n=a.n,
                         tasks=[t.name for t in tasks], rate=rate)
    store = TranscriptStore(a.pool, header)
    ledger = CampaignLedger(a.ledger, a.max_usd)
    from ..workers.transport import FakeTransport

    transport = FakeTransport(dsl_fake_responses(tasks))
    summary = fill(store, tasks, transport, rate, ledger, max_usd=a.max_usd, api_key_env=a.api_key_env)
    return 0 if summary["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
