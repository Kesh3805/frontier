# ADR-0002: Single process with an append-only hash-chained JSONL log

Status: accepted (2026-10-26)

## Decision
A campaign runs in one process. Its authoritative record is an append-only
JSONL event log in which each record commits to the previous record's hash.
All reported metrics are recomputed from the log (`frontier audit`), and a
run is replayed by re-executing its config and comparing log heads
(`frontier replay`).

## Why
This is the simplest durable store that supports every phase-1 requirement:
immutability, tamper evidence, replay and integrity audit. A database adds
no capability we currently need.

## Rejected
- *SQLite now*: useful for queries across many runs. Revisit when crash
  recovery of live (non-simulated) workers requires a durable queue.
- *PostgreSQL, message bus, Kubernetes*: no requirement justifies them yet.

## Consequences
The hash chain shows tampering but does not prove authorship. Signing or
CI attestation is deferred until results are published.
