# ADR-0006: HybridAgent through a pinned external checkout, not vendored code

Status: accepted (2026-10-26)

## Decision
FRONTIER does not copy `togethercomputer/HybridAgent` into this repository.
The adapter (`python/frontier_py/workers/hybrid_agent.py`) pins upstream
commit `1b41ceb…` and checkpoint revisions. It requires explicit latent-step
and tool-cap settings, because code and paper defaults differ. It reports
itself unavailable when there is no suitable GPU or checkout, and it never
downloads anything automatically.

## Why
Upstream is MIT-licensed and actively changing. Vendoring would fork it
silently. The development host has no GPU, so H2 is blocked anyway (see
`docs/research/scope.md`).

## Rejected
Re-implementing HybridLink in-tree: a reimplementation would be our own
method, not a reproduction of theirs.
