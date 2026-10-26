# FRONTIER

**Adaptive allocation of compute for verified research results.**
A research program of Ostrium Labs.

FRONTIER asks a narrow, falsifiable question. At a fixed end-to-end compute
budget, does choosing *which attempt runs next* from independent verifier
feedback yield more verified results than strong fixed-allocation policies?
And does a cheaper per-attempt generator, such as latent/text hybrid
reasoning, add to that?

## Status (2026-10-26)

| Area | State |
|---|---|
| Research scope, source audit, literature review, calibration | Written; see [`docs/research/`](docs/research/) |
| Architecture decisions | [`docs/decisions/`](docs/decisions/) (ADR-0001 to ADR-0006) |
| Rust kernel: specs, task DAG, budget ledger, evidence, hash-chained log | Implemented and tested |
| Scheduling policies (9) and synthetic simulator with audit and replay | Implemented and tested |
| Python property-test verifier (V1, not sandboxed), analysis, adapters | Implemented and tested; HybridAgent and hosted adapters are interface-only |
| **exp-000** (simulation, preregistered) | **Done. H1-sim rejected under the frozen rule**: adaptive allocation beat round-robin in 5 of 6 primary cells but was worse in one. See [`results/exp-000/`](results/exp-000/README.md) |
| **exp-001** (simulation, preregistered) | **Done.** The R2-moderate loss replicates; the misleading-hints explanation is refuted under the frozen rule (with a disclosed confound). Where the adaptive advantage exists, it survives correlated failures and verifier noise. A 2% per-check false-positive rate makes 8–25% of accepted results false. See [`results/exp-001/`](results/exp-001/README.md) |
| **exp-002** (simulation, preregistered) | **Done. Mechanism supported:** the loss comes from optimistic hints on dead problems the hints don't flag (+47 wasted attempts). With full detection of dead problems the loss becomes a gain (+0.56; +3.85 in R3). See [`results/exp-002/`](results/exp-002/README.md) |
| **exp-003** (real tasks, non-LLM worker, pilot) | **Done.** 34 real algorithm tasks, real subprocess verifier. Thompson with hints beat round-robin at budgets 60 and 240 (pilot rule: supported), but most of the gain comes from hints. The predicted waste on dead tasks was reproduced, and real verifier false acceptances were measured. FIFO's lead is a task-order confound. See [`results/exp-003/`](results/exp-003/README.md) |
| **exp-004** (real tasks, shuffled order) | **Done.** Task order leaked into FIFO, round-robin and tie-breaking index policies. With order shuffled, hinted Thompson wins clearly only at the scarce budget (+1.75 [1.36, 2.14]); the pilot H1 verdict is **inconclusive**. See [`results/exp-004/`](results/exp-004/README.md) |
| **exp-005** (verification study) | **Done.** The current 40-case hidden suite accepts 1.8% of wrong programs (boundary bugs); every larger or narrower-range suite accepts none, so the small-scope hypothesis can't be tested at this floor. See [`results/exp-005/`](results/exp-005/README.md) |
| H1 (LLM workers) | Untested: needs an LLM worker and a spending authorisation |
| H2/H3 (hybrid reasoning) | Untested and blocked: no GPU, and no released matched text-only checkpoint |

Nothing in this repository is a scientific discovery claim. Simulation
results are labelled as simulations.

## Quick start

```bash
cargo test --workspace                       # Rust kernel, policies, simulator
python -m pytest python -q                   # verifiers, analysis, adapters
cargo build --release -p frontier-cli
bash scripts/qualify.sh                      # smoke run + audit + replay + forgery check
target/release/frontier experiment --config research/preregistration/exp-000/scarce.json --out runs/exp-000/scarce
(cd python && python -m frontier_py.analysis ../runs/exp-000/scarce/results.jsonl --baseline round_robin --metric solved)
```

## Layout

- `crates/frontier-core`: problem specs, task DAG and lifecycle, budget ledger, evidence store, event log
- `crates/frontier-sched`: allocation policies
- `crates/frontier-sim`: synthetic environment, discrete-event runner, log audit, experiment grid
- `crates/frontier-cli`: the `frontier` binary (`run`, `audit`, `replay`, `experiment`)
- `python/frontier_py`: verifiers, statistics, worker adapters
- `schemas/`: versioned JSON data contracts
- `research/preregistration/`: frozen protocols; `results/`: executed results
- `docs/`: research, decisions, archive of the original dossier

## License

Apache License 2.0; see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Third-party
papers, code and models are cited where used and keep their own licenses
(HybridAgent: MIT; HybridAgent checkpoints: MIT; Qwen3 base models and
benchmark datasets: their respective terms).
