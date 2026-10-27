# Stage 2 plan: the first model-backed study

Status: **phase 0 implemented; phases 1–3 await spending authorisation.**
No provider call has been made and no API key has been used. All prices
below are **assumptions to verify** against the provider before anything
is spent.

## Goal

Test H1 with real model attempts. The question is whether adaptive
allocation (the exp-007 setting: dependency-structured problems,
verifier-gated) still beats round-robin when each attempt is an LLM
writing a program, rather than a DSL search. Measure physical cost as
well as modelled compute units.

H2/H3 (hybrid latent reasoning) are **not** part of Stage 2. They need a
GPU and a matched text-only baseline (see [`scope.md`](scope.md#h2)).

## Design decisions

1. **Record once, replay exactly.** A separate `pool fill` step draws N
   independent samples per task from the model into an append-only
   transcript store, keyed by:
   - provider, model, revision and prompt hash;
   - sampling parameters;
   - task and sample index.

   The experiment then runs the existing Rust runner against the store in
   **replay-only** mode. The replay service has no network access and no
   API key. The k-th attempt on a task for a given seed is pool sample
   π(task, seed)(k), a seeded permutation. This keeps paired comparisons
   across policies, and cost is bounded by tasks × N instead of growing
   with seeds × budgets. Because seeds share the pool, confidence
   intervals use a two-level bootstrap (pool samples, then seeds).
2. **The V2 sandbox is mandatory.** Model-written code runs only through
   `--sandbox docker` ([ADR-0007](../decisions/ADR-0007-v2-sandboxed-verifier.md)).
   That covers the visible-example screen, the hidden suite and the
   extended truth check. The host runs no in-process `exec` of model code.
3. **A held-out suite the generator cannot see.** The current task
   definitions and hidden-suite generators are public in this repository,
   so they are not sealed. Stage 2 needs a new suite, *llm-v1*:
   - **Anchor stratum:** the existing tasks, reported separately. They are
     expected to saturate.
   - **Hard stratum:** about 24 new tasks whose edge rules are fixed only by
     the examples, checked by exhaustive small-input suites.
   - **Dead and misspecified stratum:** 10–15% of tasks.
   - **Dependency stratum:** lemma routes, as in catalog v3.

   The hidden suites are committed **by hash only** until the run, and are
   stored outside the repository until then.
4. **Model selection rule**, fixed before calibration: choose the cheapest
   non-reasoning model for which at least 40% of hard-stratum live tasks
   have a calibration success rate p̂ between 0.05 and 0.8. That keeps the
   tasks neither trivial nor hopeless for it.
5. **Measured cost.** Record input and output tokens and USD from provider
   usage per call, plus verifier CPU and wall time. A versioned rate card
   converts tokens to compute units, so replay stays deterministic. USD is
   reconciled against the provider's reported cost.
6. **Budget safety.**
   - A per-call guard refuses any call whose worst-case cost exceeds what
     remains.
   - A per-campaign ledger (fsync'd, outside the repo) counts unsettled
     reservations as spent, so a crash cannot exceed the cap.
   - `fill` only estimates unless `--execute` is given.
   - The API key is read only from an environment variable, and never
     reaches logs, transcripts or the verifier child's environment.

## Size and cost (assumptions)

About 2,550 calls in total:

| Phase | Calls |
|---|---|
| Calibration | 58 tasks × 8 samples = 464 |
| Experiment pool | 58 × 32 = 1,856 |
| Retries (about 10%) | about 230 |

Per call, the assumption is 300 input and 100 output tokens (worst case
450 and 256). The model must not be a reasoning model.

| Assumed price, USD per 1M tokens (in / out) | Expected | Worst case |
|---|---|---|
| A, small model: 0.10 / 0.40 | $0.18 | $0.38 |
| B, mid model: 1 / 5 | $2.04 | $4.41 |
| C, frontier model: 3 / 15 | $6.12 | $13.23 |

**Recommended cap: $10 for the whole campaign**, using a model at price
point A or B.

## Phases

| Phase | Spend | Work |
|---|---|---|
| 0 | none | Implement the pool store, replay service, guard, ledger and prompt/parser. Test with a fake transport and a pool built by the DSL worker; check that log heads are reproducible. |
| 1 | authorisation 1 | Calibration calls. Freeze the model, rate card, catalog and budgets. Preregister exp-009. |
| 2 | authorisation 2 | Experiment-pool calls. |
| 3 | none | Run exp-009 offline from the pool, with frozen scoring, then publish. |

## Phase 0 status (no spend)

Done, tested only with a fake transport; recorded in
[ADR-0008](../decisions/ADR-0008-record-once-replay-for-model-workers.md):

| Piece | Where |
|---|---|
| Append-only transcript store (keyed, tamper-evident, duplicate-refusing) | `python/frontier_py/workers/transcripts.py` |
| Versioned rate card (tokens to CU and USD) | `python/frontier_py/workers/rate_card.py` |
| Crash-safe campaign ledger, wired into `BudgetGuard` | `python/frontier_py/workers/ledger.py`, `workers/base.py` |
| Prompt template `codegen-v1` and `ast`-only parser | `python/frontier_py/workers/llm_codegen.py` |
| `Transport` protocol and `FakeTransport`; real transport left as a refusing TODO | `python/frontier_py/workers/transport.py` |
| `pool estimate` / `fill` / `screen` CLI | `python/frontier_py/realtasks/pool.py` |
| Replay service `server --worker llm-pool --pool PATH` | `python/frontier_py/realtasks/server.py` |
| Model label from the service `hello`; pool digest, verify calls and child CPU in the manifest | `crates/frontier-sim/src/{external,real,runner}.rs`, `crates/frontier-cli` |

Checks: `python/tests/test_pool.py` (prompt golden hash and leakage, parser,
store, permutation, ledger, canary key) and
`crates/frontier-sim/tests/pool.rs` (a replayed mini-experiment from a
fake DSL pool has identical log heads across runs and thread counts).
Existing log heads are unchanged.

Not done in phase 0, and needed before phase 1:

- the *llm-v1* held-out suite (design decision 3);
- a real transport for the chosen provider, added only with authorisation;
- a run of `pool screen` and of the replay service under
  `--sandbox docker` on a host with the pinned image (CI `verifier-v2`
  covers the sandbox itself, not these two entry points);
- the frozen rate card for the chosen model.

## What the project owner must decide

- the provider and model (or approve the selection rule);
- a campaign cap for each authorised phase;
- whether transcripts may be committed (check the provider's terms).

Until then, only phase 0 (no spend) proceeds.
