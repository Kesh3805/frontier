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
| H1 (real workers) | Untested: needs real verifier-backed tasks and inference |
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
