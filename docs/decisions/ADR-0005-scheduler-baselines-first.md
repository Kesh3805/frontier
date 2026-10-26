# ADR-0005: Deterministic baselines first; adaptive policies are posterior indices

Status: accepted (2026-10-26)

## Decision
Every adaptive policy is compared with:

- strict fixed slices (Zuo et al.'s "Uniform");
- work-conserving round-robin (Zuo et al. 2506.12721, Alg. 1, K=1, when
  each problem has one single-step approach);
- FIFO and random;
- a static prior-hint index;
- a hopeless-problem elimination heuristic;
- a simulation-only oracle index.

The first adaptive policies are Beta-posterior UCB and Thompson indices on
expected remaining cost to finish an approach. No learned (trained)
scheduler is built until these comparisons exist.

## Why
Gains over weak baselines are uninformative. Work-conserving round-robin
already captures the main published across-query allocation result, so it
is the bar to clear.

## Rejected
Calling the low-bound elimination heuristic an implementation of Zuo et
al.: it is not (see the calibration review in
`docs/research/calibration.md`).
