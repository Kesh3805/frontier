# ADR-0001: Rust control plane, Python execution layer, JSON interchange

Status: accepted (2026-10-26)

## Decision
Scheduling, budgets, task lifecycle, evidence and the event log live in a
Rust workspace (`frontier-core`, `frontier-sched`, `frontier-sim`,
`frontier-cli`). Model inference, verifiers that need Python tooling, and
statistical analysis live in `python/frontier_py`. The two exchange
versioned JSON documents (`schemas/`). A verifier is a subprocess that reads
one request on stdin and writes one receipt on stdout.

## Why
The control plane must be deterministic and replayable, and it must fail
loudly on invariant violations. Model and scientific tooling is
Python-native. A process boundary keeps untrusted generated code and heavy
ML dependencies out of the scheduler, and JSON keeps the contract
inspectable.

## Rejected
- *Single Python codebase*: simpler at first, but determinism and
  invariant enforcement are harder to guarantee, and the dossier asked for a
  Rust control plane.
- *PyO3 bindings / gRPC*: they couple build systems or add a service layer
  before any measured throughput need exists.
