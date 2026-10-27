# ADR-0008: Model workers are recorded once and replayed exactly

Status: accepted (2026-10-27)

## Decision
A model-backed worker never runs inside an experiment. Model calls happen
only in a separate, budgeted `pool fill` step
(`python/frontier_py/realtasks/pool.py`), which draws N independent samples
per task into an append-only transcript store
(`python/frontier_py/workers/transcripts.py`). Experiments then replay the
store through the existing Rust runner and the worker service in
`--worker llm-pool` mode, which has no transport and needs no API key.

- **Store.** One JSONL file: a header (provider, model, revision, prompt
  template version, sampling parameters, samples per task, task list, rate
  card), then one record per call. A record is keyed by the SHA-256 of
  {provider, model, model_revision, template_version, prompt_sha256,
  temperature, top_p, max_output_tokens, task, j}, and carries the request
  (an allowlist of fields; no headers, no credentials), the response text,
  token usage, USD, finish reason, the provider's response model id, UTC
  time, the header's digest and its own SHA-256. A key is stored at most
  once. `verify()` detects any edited, reordered, duplicated or truncated
  line. The file's SHA-256 identifies the pool and is recorded in the
  experiment manifest (`pool_sha256`).
- **Replay.** The k-th attempt on a task for seed s returns sample
  j = π(task, s)(k), a Fisher-Yates permutation of the task's sample
  indices whose swaps are drawn from SHA-256. It does not depend on the
  policy, so every policy on one seed sees the same sample sequence. k
  beyond the pool is an error, never a fresh call. `gen_units` is a
  versioned rate card applied to the recorded token usage, so replay is
  deterministic. The submission model label comes from the service's
  `hello` (`worker`), defaulting to `dsl-search`, so every existing log head
  is unchanged.
- **Sandbox.** Model-written code runs only through the V2 docker sandbox
  ([ADR-0007](ADR-0007-v2-sandboxed-verifier.md)), both for `pool screen`
  and in the replay service. `--sandbox none` is refused for a pool, except
  with `--allow-unsandboxed-for-tests` on a pool written by the fake
  transport (DSL programs, which the project already trusts; the extended
  check then runs in-process, as in DSL mode). The host parses model output
  with `ast` only; it never executes it.
- **Budget.** `fill` only estimates unless `--execute` is given. Every call
  is reserved at its worst case (prompt bytes plus a fixed overhead as input
  tokens, the output cap as output tokens) in a crash-safe, fsync'd
  campaign ledger (`workers/ledger.py`) before it is made, through the
  existing `BudgetGuard`. Unsettled reservations count as spent. A call
  that settles above its own reservation halts the ledger.
- **Keys.** An API key is read from an environment variable at call time,
  handed to the transport, and never written to the store, the ledger, logs
  or exception messages (transport errors are re-raised redacted, without
  the original chained). The verifier child never inherits it.
- **No real transport yet.** Only `FakeTransport` exists. `HttpTransport`
  is a marked interface that refuses to run, and `fill` refuses every
  transport except `fake`, until the project owner authorises a provider
  ([stage 2 plan](../research/stage2-plan.md), phases 1 and 2).

## Why
Live model calls inside an experiment would make runs non-reproducible:
the same seed would draw different programs, and different policies would
be compared on different samples. Cost would also grow with seeds ×
budgets × policies. Recording once bounds the spend at tasks × N, keeps
paired comparisons across policies, and lets anyone re-run an experiment
from the published pool without a key or any spend. Keeping calls out of
the experiment also keeps the network and secrets out of the process that
verifies untrusted code.

## Rejected
- **Live calls with response caching.** A cache keyed by (task, seed, k)
  still spends in proportion to seeds × budgets and makes the sample a
  policy sees depend on which calls happened to be cached first.
- **Using the provider's `seed` parameter for reproducibility.** Providers
  do not guarantee determinism across time or backends, and a silent model
  update would change results without any visible trace.
- **A per-seed pool.** Independent pools per seed would multiply cost by
  the seed count. Seeds share the pool instead, and confidence intervals
  use a two-level bootstrap (pool samples, then seeds).
- **Computing `visible_pass` in the replay service.** It needs executing
  model code; the reply carries `null` instead, and `pool screen` computes
  it through the sandbox.

## Consequences and caveats
- Seeds share one pool, so between-seed variation understates sampling
  variation; analyses must resample pool samples as well as seeds.
- A pool's results are tied to the recorded model revision. Re-recording
  produces a different pool (and digest), not a rerun.
- The ledger bounds what is authorised. A provider that reports more usage
  than the per-call bound allows (for example more output tokens than the
  requested cap) is settled as reported, so it can exceed the cap by at
  most that one call's excess; the ledger then halts. Honest reporting
  within the request's limits cannot exceed the cap.
- Child CPU time is measured with `getrusage` on POSIX only. With the
  docker sandbox it covers the docker CLI, not the container.
