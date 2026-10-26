# FRONTIER

**Adaptive allocation of compute for verified research results.**
A research program of Ostrium Labs.

FRONTIER asks a narrow, falsifiable question. At a fixed end-to-end compute
budget, does choosing *which attempt runs next* from independent verifier
feedback yield more verified results than strong fixed-allocation policies?
And does a cheaper per-attempt generator, such as latent/text hybrid
reasoning, add to that?

## Status

| Area | State |
|---|---|
| Research scope, source audit, literature review | Written; see [`docs/research/`](docs/research/) |
| Rust research kernel | In progress |
| Experiments | None yet |
| H1 (adaptive allocation, real workers) | Untested |
| H2/H3 (hybrid reasoning) | Untested; blocked (no GPU, no matched text-only checkpoint) |

Nothing in this repository is a scientific discovery claim. Any result
produced in simulation is labelled as simulation.

## Layout

- `docs/research/`: [scope](docs/research/scope.md), [source audit](docs/research/source-audit.md), [literature review](docs/research/literature-review.md)
- `docs/archive/`: the original dossier v0.1, kept verbatim as a historical input

## License

No license has been granted yet. Licensing will be decided before any public
release. Third-party work is cited where it is used.
