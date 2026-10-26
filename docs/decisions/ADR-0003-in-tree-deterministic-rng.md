# ADR-0003: In-tree SplitMix64 with labelled substreams

Status: accepted (2026-10-26)

## Decision
All randomness comes from `frontier_core::SplitMix64`. Independent streams
are derived from `(seed, label)`. Attempt outcomes use the label
`attempt/<task>/<k>`, so the k-th attempt on a task has the same outcome
under every policy (common random numbers).

## Why
Replays must not depend on the stream stability of an external crate
across versions. Common random numbers turn policy comparisons into paired
comparisons, which removes most environment noise.

## Rejected
`rand`/`rand_chacha`: high quality, but stream stability across major
versions is not a contract we control.
