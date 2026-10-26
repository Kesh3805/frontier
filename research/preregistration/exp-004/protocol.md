# exp-004: Real-task pilot with problem order shuffled per seed

Status: **FROZEN** before any exp-004 outcome was generated. The scoring
scripts `evaluate_primary.py` (a byte-identical copy of exp-003's) and
`evaluate_order.py` are frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM worker). Not confirmatory.

## Why

In exp-003, FIFO gained +3.41 at budget 60. The catalog listed easy tasks
first and dead tasks last, so iterating in index order leaked difficulty
information. Round-robin also iterates in catalog order. exp-004 repeats
exp-003 exactly, except that problem order is shuffled per seed (stream
`problem-order`). Seeds 1001–1100 and the worker streams are the same, so
pairing (budget, policy, seed) across the two experiments isolates the
effect of order.

## Frozen inputs

Config commit `bf263c8eb89ae3e426f1aff8093501b4d861b78f`. Everything is
identical to exp-003, except:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-004/b60.json` | `dec8dc9b04079c29d2955f443de5b90a42c9b6a9010212500f86f8b5d0038093` |
| `research/preregistration/exp-004/b240.json` | `89bc83fd822749dc4050bce9a292701311f1b9373bfdcfefedaa8141a6f9f452` |
| `research/preregistration/exp-004/b480.json` | `da6ca52e84b42ffed594b2125eee3ed9f066e10bffdaebe44a6bd81630e24849` |
| `research/preregistration/exp-004/evaluate_primary.py` | `5afba1f19f9d1cbaea9ccf594789f28e7b1a6906868538cc270b697d2c7988ae` |
| `crates/frontier-sim/src/real.rs` | `f1ec8d77969ed5cb3277a4009f044982082a39e7aaa903e6cb04d3f190d44c1c` |
| `python/frontier_py/realtasks/server.py` | `b8a2f46eae7680fdf3df5dabde923ef8a15cf02ccefa2272841b9478421492f5` |

The only change to `server.py` is the wall-time bookkeeping fix. Receipts
and results do not depend on it.

## Predictions

**Order effects** (`evaluate_order.py`), on `sim_true_solved`:

- **O1:** with shuffling, FIFO − round-robin has a CI upper bound ≤ 0 at
  budgets 60 and 240. FIFO's advantage was the order artifact.
- **O2:** FIFO's own result drops when order is shuffled at budget 60
  (paired CI entirely below 0).
- **O3:** round-robin is order-insensitive: |shuffled − catalog| < 0.5 at
  every budget.
- **O4:** thompson(k=2, hints) is order-insensitive in the same sense. Its
  index ignores order, except for tie-breaks.

**Replication of exp-003** (`evaluate_primary.py`, unchanged rules): P1,
P2a, P2b, P3, P4, and the pilot H1 rule.

The prediction for P2b is unchanged from exp-003, where it failed. It is
kept unchanged deliberately, so it is not revised after seeing results.

## Invalidation

As exp-003: audit failure, a dirty tree, a hash mismatch, or a protocol
error.
