"""Stage 2 phase 0: record-once pools, replay, budget safety. No provider is ever called."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from frontier_py.realtasks import deps
from frontier_py.realtasks.catalog import hidden_cases
from frontier_py.realtasks.pool import (
    FAKE_PROVIDER,
    Pool,
    PoolError,
    TransportFailed,
    dsl_fake_responses,
    estimate,
    fill,
    key_for,
    make_header,
    permutation,
    sandbox_policy,
    select_tasks,
    worst_case_usd,
)
from frontier_py.realtasks.suite import BY_NAME, SUITE
from frontier_py.verifiers import property_tests
from frontier_py.workers.base import BudgetExceeded, BudgetGuard
from frontier_py.workers.ledger import CampaignLedger, LedgerError
from frontier_py.workers.llm_codegen import PARSE_FAILURE_STUB, build_prompt, parse_function, prompt_sha256, try_parse
from frontier_py.workers.rate_card import RateCard
from frontier_py.workers.transcripts import (
    DuplicateTranscript,
    TranscriptError,
    TranscriptKey,
    TranscriptRecord,
    TranscriptStore,
)
from frontier_py.workers.transport import FakeTransport, HttpTransport, TransportResponse

PYTHON_DIR = Path(__file__).resolve().parents[1]
RATE = RateCard("test-1", cu_per_input_token=0.0005, cu_per_output_token=0.002, usd_per_input_token=1e-6, usd_per_output_token=4e-6)
CANARY = "sk-canary-0123456789abcdef-DO-NOT-LEAK"
FIXED_UTC = lambda: "2026-01-01T00:00:00Z"  # noqa: E731


def header(tasks, n=3, **kw):
    base = dict(provider=FAKE_PROVIDER, model="dsl-search", model_revision="fake-1", template_version="codegen-v1", temperature=1.0,
                top_p=1.0, max_output_tokens=256, n=n, tasks=[t.name for t in tasks], rate=RATE)
    base.update(kw)
    return make_header(**base)


def filled_pool(tmp_path, names=("sum", "count", "reverse"), n=3, task_set="pilot", name="pool.jsonl", cap=1.0):
    tasks = select_tasks(task_set, list(names))
    store = TranscriptStore(tmp_path / name, header(tasks, n))
    ledger = CampaignLedger(tmp_path / f"{name}.ledger.json", cap)
    summary = fill(store, tasks, FakeTransport(dsl_fake_responses(tasks)), RATE, ledger, max_usd=cap, log=lambda _s: None, clock=FIXED_UTC)
    return store, ledger, summary


# --- prompt -------------------------------------------------------------------

PROMPT_SUM = (
    "Write a Python function `f(xs)` that takes a list of integers `xs` and returns an integer. "
    "Use only the Python standard library; do not read input or print.\n"
    "\n"
    "Task: Sum of the elements.\n"
    "\n"
    "Examples:\n"
    "f([3, -1, 2]) == 4\n"
    "f([4, 4, -6, 1]) == 3\n"
    "f([0, 7]) == 7\n"
    "\n"
    "Reply with only the function in one ```python code block, starting with:\n"
    "def f(xs):\n"
)
GOLDEN_SUM_SHA256 = "e2f0d6c545ad1d043908e86988cfdc60303912a46a0c9dea5df55140d40b1506"


def test_prompt_golden():
    p = build_prompt(BY_NAME["sum"])
    assert p == PROMPT_SUM
    assert prompt_sha256(p) == GOLDEN_SUM_SHA256
    with pytest.raises(ValueError):
        build_prompt(BY_NAME["sum"], "codegen-v0")


def test_dependent_prompt_lists_helpers_by_statement_only():
    t = deps.BY_NAME["span_pos/via_positives"]
    p = build_prompt(t)
    assert "- h_positives(xs) returns a list of integers: The positive elements, in order." in p
    assert "def f(xs):\n    return [x for x in xs if x>0]" not in p  # the lemma's reference program is not shown


@pytest.mark.parametrize("task", list(SUITE) + list(deps.TASKS), ids=lambda t: t.name)
def test_prompt_leaks_no_hidden_data_or_labels(task):
    p = build_prompt(task)
    visible = {repr(list(xs)) for xs, _ in task.visible}
    shown = {line.split(") == ")[0][2:] for line in p.splitlines() if line.startswith("f([")}
    assert shown == visible
    for suite in ("1", "2"):
        for xs, want in hidden_cases(task, suite):
            if repr(xs) not in visible:
                assert f"f({xs!r})" not in p
    for args in task.task_def().hidden_inputs(20261026):
        if repr(args[0]) not in visible:
            assert f"f({args[0]!r})" not in p
    lowered = p.lower()
    for word in ("hidden", "solvable", "inexpressible", "misspecified", "misleading", "trap", "hint", "p_hat", "status", "label"):
        assert word not in lowered, word
    assert "lambda" not in p and "reference" not in lowered


# --- parser -------------------------------------------------------------------

GOOD = "def f(xs):\n    return sum(xs)\n"


@pytest.mark.parametrize("text", [
    GOOD,
    "```python\n" + GOOD + "```",
    "Sure! Here you go:\n```py\n" + GOOD + "```\nThis sums the list.",
    "```\n" + GOOD + "```",
    "```python\nimport math\n\ndef f(xs: list[int]) -> int:\n    def g(x):\n        return x\n    return sum(map(g, xs))\n```",
    "```text\nnot code\n```\n```python\n" + GOOD + "```",
    '"""Doc."""\nfrom itertools import accumulate\ndef f(xs):\n    return sum(xs)\n',
    "    def f(xs):\n        return sum(xs)\n",  # indented as a whole
    "~~~python\n" + GOOD + "~~~",
])
def test_parse_accepts(text):
    src = try_parse(text)
    assert src is not None and src.endswith("\n") and "def f(" in src
    assert parse_function(text) == src


@pytest.mark.parametrize("text", [
    "",
    "I cannot help with that.",
    "def g(xs):\n    return 0\n",
    "def f(xs, ys):\n    return 0\n",
    "def f(xs=[]):\n    return 0\n",
    "def f(*xs):\n    return 0\n",
    "def f(ys):\n    return 0\n",
    "async def f(xs):\n    return 0\n",
    "@cache\ndef f(xs):\n    return 0\n",
    "f = lambda xs: sum(xs)\n",
    "def f(xs):\n    return 0\ndef f(xs):\n    return 1\n",
    "def f(xs):\n    return 0\ndef helper(x):\n    return x\n",
    "def f(xs):\n    return 0\nprint(f([1]))\n",
    "import os\nos.system('echo hi')\ndef f(xs):\n    return 0\n",
    "def f(xs):\n    return (\n",
    "```python\ndef f(xs):\n    retur sum(xs)\n```",
    "def f(xs):\n    return 0\n\x00",
    "class f:\n    pass\n",
])
def test_parse_rejects_to_raising_stub(text):
    assert try_parse(text) is None
    assert parse_function(text) == PARSE_FAILURE_STUB


def test_parse_rejects_oversized_reply():
    assert try_parse("def f(xs):\n    return 0\n" + "#" * (70 << 10)) is None


def test_parse_failure_stub_fails_verification_cleanly():
    r = property_tests.verify(BY_NAME["sum"].task_def(), {"source": PARSE_FAILURE_STUB}, spec_digest="0" * 64, seed=1)
    assert r.verdict == "FAIL" and "ValueError" in r.reason


# --- transcripts store --------------------------------------------------------

def _record(store, task="sum", j=0, text=GOOD, **kw):
    prompt = build_prompt(BY_NAME[task])
    h = store.header
    req = {"provider": h["provider"], "model": h["model"], "model_revision": h["model_revision"], "template_version": h["template_version"],
           "prompt": prompt, "temperature": h["temperature"], "top_p": h["top_p"], "max_output_tokens": h["max_output_tokens"], "seed": j}
    req.update(kw.pop("request", {}))
    return TranscriptRecord(key_for(h, task, j, prompt), req, text, 50, 10, 0.0001, "stop", "fake-x", "2026-01-01T00:00:00Z", **kw)


def test_store_put_get_and_refuses_duplicates(tmp_path):
    store = TranscriptStore(tmp_path / "s.jsonl", header([BY_NAME["sum"]]))
    rec = _record(store)
    store.put(rec)
    with pytest.raises(DuplicateTranscript):
        store.put(_record(store, text="def f(xs):\n    return 0\n"))
    reopened = TranscriptStore(tmp_path / "s.jsonl")
    assert reopened.get(rec.key) == rec and len(reopened) == 1
    with pytest.raises(DuplicateTranscript):
        reopened.put(rec)
    assert reopened.verify() == []
    with pytest.raises(TranscriptError):  # header must match when reopening with one
        TranscriptStore(tmp_path / "s.jsonl", header([BY_NAME["sum"]], n=9))
    with pytest.raises(TranscriptError):  # no header, no store
        TranscriptStore(tmp_path / "missing.jsonl")


def test_store_refuses_keys_off_header_and_requests_with_secrets(tmp_path):
    store = TranscriptStore(tmp_path / "s.jsonl", header([BY_NAME["sum"]]))
    with pytest.raises(TranscriptError, match="allowlist"):
        store.put(_record(store, request={"api_key": CANARY}))
    with pytest.raises(TranscriptError, match="allowlist"):
        store.put(_record(store, request={"headers": {"authorization": "Bearer x"}}))
    rec = _record(store)
    other = TranscriptRecord(TranscriptKey(**{**rec.key.canonical(), "model": "other"}), rec.request, rec.text, 1, 1, 0.0, "stop", "", "")
    with pytest.raises(TranscriptError, match="header"):
        store.put(other)
    with pytest.raises(TranscriptError, match="prompt"):
        store.put(_record(store, request={"prompt": "something else"}))
    assert len(store) == 0 and store.verify() == []


@pytest.mark.parametrize("edit", [
    lambda s: s.replace('"text":"Here is', '"text":"Hare is', 1),
    lambda s: s.replace('"output_tokens":', '"output_tokens":1', 1),
    lambda s: s.replace('"n":3', '"n":4', 1),
    lambda s: s + s.splitlines(keepends=True)[1],
    lambda s: s[:-5],
])
def test_store_verify_detects_tampering(tmp_path, edit):
    store, _, _ = filled_pool(tmp_path)
    assert store.verify() == []
    before = store.sha256()
    p = store.path
    p.write_bytes(edit(p.read_text(encoding="utf-8")).encode("utf-8"))
    assert store.verify() != []
    assert store.sha256() != before
    with pytest.raises((PoolError, TranscriptError, ValueError, KeyError)):
        Pool(p)


def test_fill_is_deterministic_and_resumable(tmp_path):
    a, _, sa = filled_pool(tmp_path, name="a.jsonl")
    b, _, sb = filled_pool(tmp_path, name="b.jsonl")
    assert a.path.read_bytes() == b.path.read_bytes() and a.sha256() == b.sha256() == sa["pool_sha256"]
    assert sa["calls_made"] == 9 and sa["complete"]
    tasks = select_tasks("pilot", ["sum", "count", "reverse"])
    again = fill(TranscriptStore(a.path), tasks, FakeTransport(dsl_fake_responses(tasks)), RATE, CampaignLedger(tmp_path / "a.jsonl.ledger.json", 1.0),
                 max_usd=1.0, log=lambda _s: None, clock=FIXED_UTC)
    assert again["calls_made"] == 0 and again["already_stored"] == 9 and again["pool_sha256"] == sa["pool_sha256"]


# --- replay -------------------------------------------------------------------

def test_permutation_is_a_deterministic_bijection():
    for n in (1, 2, 7, 32):
        for seed in (0, 1, 99):
            p = permutation("sum", seed, n)
            assert sorted(p) == list(range(n))
            assert p == permutation("sum", seed, n)
    assert permutation("sum", 1, 32) != permutation("sum", 2, 32)
    assert permutation("sum", 1, 32) != permutation("count", 1, 32)
    assert permutation("sum", 5, 0) == []


def test_pool_replay_is_policy_independent_and_bounded(tmp_path):
    store, _, _ = filled_pool(tmp_path)
    pool = Pool(store.path)
    # The k-th attempt depends only on (task, seed, k): any policy reaching attempt k sees the same sample.
    seq = [pool.sample("sum", 7, k).j for k in range(3)]
    assert seq == permutation("sum", 7, 3)
    assert [pool.sample("sum", 7, k).j for k in (2, 0, 1)] == [seq[2], seq[0], seq[1]]
    a = pool.attempt("sum", 7, 1)
    assert a == Pool(store.path).attempt("sum", 7, 1)
    assert a["visible_pass"] is None and a["samples"] == 1
    rec = next(r for r in store.records() if r.key.task == "sum" and r.key.j == a["j"])
    assert a["gen_units"] == RATE.cu({"input_tokens": rec.input_tokens, "output_tokens": rec.output_tokens})
    with pytest.raises(PoolError, match="beyond"):
        pool.sample("sum", 7, 3)
    with pytest.raises(PoolError):
        pool.sample("max0", 7, 0)
    assert pool.label == "llm-pool:fake/dsl-search@fake-1" and pool.sha256 == store.sha256()


def test_sandbox_policy_refuses_unsandboxed_model_code(tmp_path):
    store, _, _ = filled_pool(tmp_path)
    pool = Pool(store.path)
    with pytest.raises(PoolError, match="sandboxed"):
        sandbox_policy(pool, "none", False)
    sandbox_policy(pool, "none", True)  # fake (DSL) pool, explicit test flag
    # A pool recorded from any real provider may never run unsandboxed, flag or not.
    real = TranscriptStore(tmp_path / "real.jsonl", header([BY_NAME["sum"]], provider="someprovider"))
    with pytest.raises(PoolError, match="only for pools from the fake"):
        sandbox_policy(Pool(real.path), "none", True)


def _server(args, reqs, env=None):
    return subprocess.run([sys.executable, "-m", "frontier_py.realtasks.server", *args], input="".join(json.dumps(r) + "\n" for r in reqs),
                          capture_output=True, text=True, cwd=PYTHON_DIR, timeout=120, env=env)


def test_server_llm_pool_mode_replays_byte_identically_without_a_key(tmp_path):
    store, _, _ = filled_pool(tmp_path, names=("sum", "span_pos/positives", "span_pos/via_positives"), task_set="all")
    lib = [{"name": "h_positives", "source": "def f(xs):\n    return [x for x in xs if x>0]\n"}]
    reqs = [
        {"op": "hello"},
        {"op": "attempt", "task": "sum", "seed": 1, "k": 0},
        {"op": "attempt", "task": "sum", "seed": 1, "k": 2},
        {"op": "attempt", "task": "span_pos/via_positives", "seed": 4, "k": 1, "library": lib},
        {"op": "attempt", "task": "span_pos/via_positives", "seed": 4, "k": 1},  # library missing: refused
        {"op": "attempt", "task": "sum", "seed": 1, "k": 3},  # beyond the pool
        {"op": "attempt", "task": "count", "seed": 1, "k": 0},  # not in the pool
    ]
    env = {k: v for k, v in os.environ.items() if "KEY" not in k.upper() and "TOKEN" not in k.upper()}
    args = ["--worker", "llm-pool", "--pool", str(store.path), "--allow-unsandboxed-for-tests"]
    a, b = _server(args, reqs, env), _server(args, reqs, env)
    assert a.returncode == 0, a.stderr
    assert a.stdout == b.stdout  # byte-identical replay
    r = [json.loads(line) for line in a.stdout.splitlines()]
    assert r[0]["worker"] == "llm-pool:fake/dsl-search@fake-1" and r[0]["pool_sha256"] == store.sha256()
    assert r[1]["ok"] and r[1]["j"] == permutation("sum", 1, 3)[0] and r[1]["gen_units"] > 0
    assert r[3]["ok"] and "h_positives(" in r[3]["source"]
    assert [x["ok"] for x in r[4:]] == [False, False, False]
    assert "beyond" in r[5]["error"]


def test_server_llm_pool_refuses_sandbox_none_and_dsl_hello_is_unchanged(tmp_path):
    store, _, _ = filled_pool(tmp_path)
    p = _server(["--worker", "llm-pool", "--pool", str(store.path)], [{"op": "hello"}])
    assert p.returncode != 0 and "sandboxed" in p.stderr and p.stdout == ""
    p = _server(["--allow-unsandboxed-for-tests"], [{"op": "hello"}])
    assert p.returncode != 0
    p = _server([], [{"op": "hello"}])
    hello = json.loads(p.stdout)
    assert hello["worker"] == "dsl-search" and hello["pool_sha256"] is None


def test_replay_service_never_imports_a_transport():
    code = ("import sys; import frontier_py.realtasks.server as s; s.configure([]); "
            "print(any(m.endswith('workers.transport') for m in sys.modules))")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PYTHON_DIR, timeout=60)
    assert p.stdout.strip() == "False", p.stderr


def test_verify_reply_reports_measured_cost():
    reqs = [{"op": "verify", "task": "sum", "source": GOOD, "spec_digest": "0" * 64, "artifact_digest": "1" * 64}] * 2
    r = [json.loads(line) for line in _server([], reqs).stdout.splitlines()]
    assert r[0]["wall_seconds"] > 0 and "cached" not in r[0]
    assert r[0]["child_cpu_seconds"] is not None and r[0]["child_cpu_seconds"] >= 0
    assert r[1]["cached"] and r[1]["wall_seconds"] == 0.0 and r[1]["child_cpu_seconds"] in (0.0, None)
    assert r[0]["receipt"] == r[1]["receipt"]


def test_screen_runs_every_sample_through_the_verifier(tmp_path):
    store, _, _ = filled_pool(tmp_path, names=("sum", "noisy_sum"), n=2)
    out = tmp_path / "screen.jsonl"
    p = subprocess.run([sys.executable, "-m", "frontier_py.realtasks.pool", "screen", "--pool", str(store.path), "--sandbox", "none",
                        "--allow-unsandboxed-for-tests", "--out", str(out)], capture_output=True, text=True, cwd=PYTHON_DIR, timeout=300)
    assert p.returncode == 0, p.stderr
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 4 and all(r["parsed"] for r in rows)
    assert all(r["visible_pass"] for r in rows if r["task"] == "sum")
    p = subprocess.run([sys.executable, "-m", "frontier_py.realtasks.pool", "screen", "--pool", str(store.path), "--sandbox", "none"],
                       capture_output=True, text=True, cwd=PYTHON_DIR, timeout=60)
    assert p.returncode == 2 and "sandboxed" in p.stderr


# --- budget safety ------------------------------------------------------------

def test_rate_card():
    u = {"input_tokens": 1000, "output_tokens": 100}
    assert RATE.cu(u) == 0.7 and RATE.usd(u) == pytest.approx(0.0014)
    assert RateCard.from_dict(RATE.to_dict()) == RATE and RATE.sha256() == RateCard.from_dict(RATE.to_dict()).sha256()
    for bad in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            RateCard("v", bad, 0, 0, 0)
    with pytest.raises(ValueError):
        RATE.cu({"input_tokens": -1, "output_tokens": 0})


def test_ledger_reserves_before_calls_and_unsettled_reservations_count(tmp_path):
    path = tmp_path / "ledger.json"
    led = CampaignLedger(path, 1.0)
    r0 = led.reserve(0.4)
    r1 = led.reserve(0.4)
    with pytest.raises(BudgetExceeded):
        led.reserve(0.3)  # 0.8 reserved, unsettled, counts as spent
    led.settle(r0, 0.1)
    assert led.spent_usd == pytest.approx(0.5)
    # A crash: a new process reopens the ledger; the unsettled r1 still counts at its worst case.
    again = CampaignLedger(path, 1.0)
    assert again.unsettled == [r1] and again.spent_usd == pytest.approx(0.5)
    again.reserve(0.5)
    with pytest.raises(BudgetExceeded):
        again.reserve(0.01)
    with pytest.raises(LedgerError):
        again.settle(r0, 0.1)  # already settled
    with pytest.raises(LedgerError):
        CampaignLedger(path, 2.0)  # a campaign's cap cannot be raised by reopening
    with pytest.raises(ValueError):
        CampaignLedger(tmp_path / "zero.json", 0.0)


def test_fill_refuses_before_any_call_when_the_cap_is_too_small(tmp_path):
    tasks = select_tasks("pilot", ["sum"])
    store = TranscriptStore(tmp_path / "p.jsonl", header(tasks, n=2))
    worst = worst_case_usd(RATE, build_prompt(tasks[0]), 256)
    transport = FakeTransport(dsl_fake_responses(tasks))
    s = fill(store, tasks, transport, RATE, CampaignLedger(tmp_path / "l.json", worst * 0.99), max_usd=worst * 0.99, log=lambda _s: None)
    assert transport.calls == [] and s["calls_made"] == 0 and s["stopped"] and len(store) == 0


def test_over_reporting_transport_cannot_breach_the_cap(tmp_path):
    tasks = select_tasks("pilot", ["sum", "count", "reverse", "sort"])
    worst = max(worst_case_usd(RATE, build_prompt(t), 256) for t in tasks)
    cap = worst * 2.0
    store = TranscriptStore(tmp_path / "p.jsonl", header(tasks, n=4))
    ledger = CampaignLedger(tmp_path / "l.json", cap)
    # Reports 1.5x the honest usage, still within the per-call worst case: reservations bound
    # the spend and the campaign stops before the cap, with calls left undone.
    transport = FakeTransport(dsl_fake_responses(tasks), usage_scale=1.5)
    s = fill(store, tasks, transport, RATE, ledger, max_usd=cap, log=lambda _s: None)
    assert s["stopped"] and not s["complete"]
    assert ledger.spent_usd <= cap + 1e-12 and 0 < s["calls_made"] < 16
    assert len(transport.calls) == s["calls_made"] == len(store)
    # A grossly over-reporting transport (beyond the per-call bound) halts the ledger after that call.
    store2 = TranscriptStore(tmp_path / "p2.jsonl", header(tasks, n=4))
    ledger2 = CampaignLedger(tmp_path / "l2.json", cap)
    t2 = FakeTransport(lambda r: TransportResponse("```python\n" + GOOD + "```", 10_000, 10_000))
    s2 = fill(store2, tasks, t2, RATE, ledger2, max_usd=cap, log=lambda _s: None)
    assert len(t2.calls) == 1 and ledger2.halted and "halted" in s2["stopped"]
    with pytest.raises(BudgetExceeded):
        ledger2.reserve(0.0)
    # The guard also flags the overrun for the operator.
    assert s2["overruns"]


def test_guard_with_ledger_leaves_failed_calls_reserved(tmp_path):
    from frontier_py.realtasks.pool import PoolAdapter
    from frontier_py.workers.base import GenerationRequest, Limits

    tasks = select_tasks("pilot", ["sum"])
    h = header(tasks)
    ledger = CampaignLedger(tmp_path / "l.json", 1.0)
    adapter = PoolAdapter(h, FakeTransport({}, fail=RuntimeError("boom")), RATE, None)
    guard = BudgetGuard(adapter, max_tokens=10**6, max_usd=1.0, ledger=ledger)
    req = GenerationRequest(prompt=build_prompt(tasks[0]), limits=Limits(256, 0, 0, 10.0), seed=0, model_revision="fake-1")
    with pytest.raises(TransportFailed):
        guard.generate(req)
    assert ledger.unsettled == [0] and ledger.spent_usd == pytest.approx(adapter.max_charge(req).usd)


def test_estimate_counts_calls_and_worst_case_without_calling():
    tasks = select_tasks("pilot", ["sum", "count"])
    e = estimate(tasks, 32, RATE, "codegen-v1", 256)
    assert e["calls"] == 64
    assert e["worst_case_usd"] == pytest.approx(32 * sum(worst_case_usd(RATE, build_prompt(t), 256) for t in tasks))


def test_http_transport_is_not_implemented():
    with pytest.raises(NotImplementedError):
        HttpTransport()


def test_fill_cli_refusals(tmp_path):
    rc = tmp_path / "rc.json"
    rc.write_text(json.dumps(RATE.to_dict()))
    base = [sys.executable, "-m", "frontier_py.realtasks.pool", "fill", "--rate-card", str(rc), "--n", "1", "--tasks", "sum",
            "--pool", str(tmp_path / "p.jsonl")]

    def run(*extra):
        return subprocess.run([*base, *extra], capture_output=True, text=True, cwd=PYTHON_DIR, timeout=60)

    p = run("--transport", "fake")
    assert p.returncode == 2 and "--execute" in p.stderr and not (tmp_path / "p.jsonl").exists()
    p = run("--transport", "http", "--execute", "--max-usd", "1", "--ledger", str(tmp_path / "l.json"))
    assert p.returncode == 2 and "refusing transport" in p.stderr
    p = run("--transport", "fake", "--execute")
    assert p.returncode == 2 and "--max-usd" in p.stderr
    p = run("--transport", "fake", "--execute", "--max-usd", "1", "--ledger", str(tmp_path / "l.json"))
    assert p.returncode == 0, p.stderr
    assert Pool(tmp_path / "p.jsonl").samples["sum"][0].parsed


# --- secrets ------------------------------------------------------------------

def test_canary_api_key_never_leaks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_CANARY_KEY", CANARY)
    tasks = select_tasks("pilot", ["sum", "count"])
    store = TranscriptStore(tmp_path / "p.jsonl", header(tasks, n=2))
    ledger = CampaignLedger(tmp_path / "l.json", 1.0)
    seen = []

    def reply(req):
        seen.append(req)
        return "```python\n" + GOOD + "```"

    transport = FakeTransport(reply)
    fill(store, tasks, transport, RATE, ledger, max_usd=1.0, api_key_env="FRONTIER_CANARY_KEY")
    assert transport.keyed_calls == 4  # the key was handed to the transport ...
    assert all(CANARY not in repr(r) for r in seen)  # ... but not inside the request
    for f in tmp_path.iterdir():
        assert CANARY.encode() not in f.read_bytes(), f.name  # nor written anywhere
    out = capsys.readouterr()
    assert CANARY not in out.out + out.err

    # Exceptions from a transport are redacted and do not chain the original.
    bad = FakeTransport({}, fail=RuntimeError(f"401 for key {CANARY}"))
    store2 = TranscriptStore(tmp_path / "p2.jsonl", header(tasks, n=1))
    with pytest.raises(TransportFailed) as ei:
        fill(store2, tasks, bad, RATE, CampaignLedger(tmp_path / "l2.json", 1.0), max_usd=1.0, api_key_env="FRONTIER_CANARY_KEY",
             log=lambda _s: None)
    e = ei.value
    assert CANARY not in str(e) and "[REDACTED]" in str(e)
    assert e.__cause__ is None and e.__context__ is None
    for f in tmp_path.iterdir():
        assert CANARY.encode() not in f.read_bytes(), f.name

    # The verifier's child environment never carries it.
    assert CANARY not in json.dumps(property_tests.child_env())
    probe = "def f(xs):\n    import os\n    return sorted(os.environ)\n"
    out = property_tests.run_candidate(probe, "f", [[[]]], per_call_timeout_s=5, wall_timeout_s=20, memory_limit_mb=256)
    assert out.kind == "ok" and "FRONTIER_CANARY_KEY" not in out.outputs[0]
    leak = "def f(xs):\n    import os\n    return [v for v in os.environ.values() if 'canary' in v]\n"
    out = property_tests.run_candidate(leak, "f", [[[]]], per_call_timeout_s=5, wall_timeout_s=20, memory_limit_mb=256)
    assert out.kind == "ok" and out.outputs == [[]]
