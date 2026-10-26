# exp-004 results: real-task pilot with problem order shuffled per seed

> **Erratum E1 and E2 (2026-10-27).** These results were produced on kernel
> 0.2.0, which had a bug that stranded budget unevenly across policies (E1) and one that did not count repeated rejected programs as failures (E2). See [`docs/research/errata.md`](../../docs/research/errata.md).
> Re-run on kernel 0.3.0: H1 pilot **still inconclusive**; P3 and P4 now hold; scarce-budget gain +1.86 [1.47, 2.26]; the hint-free loss at budget 60 (−0.95) shrinks to −0.12, not significant. See [`results/rerun-k0.3/`](../rerun-k0.3/README.md).

**Kind: REAL TASKS, PILOT** (non-LLM worker). Protocol:
[`research/preregistration/exp-004/`](../../research/preregistration/exp-004/protocol.md),
frozen at `a7e1528`.

**Runs.** 2,100 audited campaigns from that commit with a clean tree, 37
minutes. Seeds and worker streams are identical to exp-003; only problem
order differs. Pairing (budget, policy, seed) across the two experiments
therefore measures the **order effect** directly.

Data: [`order.json`](order.json), [`evaluation.json`](evaluation.json),
`runs.csv.gz`.

## Order effects

The order effect is the change from catalog order (exp-003) to shuffled
order (exp-004), on true solves.

| Policy | Effect @60 | Effect @240 | Effect @480 |
|---|---|---|---|
| fifo | **−9.03** [−9.50, −8.57] | **−6.67** [−7.39, −5.96] | −2.35 [−2.98, −1.75] |
| round_robin | **−0.79** [−1.00, −0.58] | −0.07 [−0.16, 0.02] | +0.01 [−0.05, 0.07] |
| greedy_prior | **−0.82** [−1.04, −0.60] | **−1.21** [−1.48, −0.96] | −0.16 [−0.35, 0.02] |
| thompson (hints) | −0.06 [−0.21, 0.09] | **−0.44** [−0.59, −0.29] | −0.05 [−0.17, 0.07] |
| thompson (no hints) | +0.04 | +0.06 | +0.03 |
| random | **+0.52** [0.06, 1.00] | −0.01 [−0.22, 0.20] | −0.01 [−0.11, 0.08] |
| oracle_index | 0 | 0 | 0 |

| Prediction | Result |
|---|---|
| O1: FIFO no longer beats round-robin once shuffled | ✔ It is now far worse: −4.83 [−5.39, −4.27] at 60 |
| O2: FIFO drops when shuffled | ✔ −9.03 |
| O3: round-robin is order-insensitive | ✘ −0.79 at budget 60 |
| O4: thompson (hints) is order-insensitive (\|effect\| < 0.5) | ✔ but −0.44 at 240, with a CI excluding 0 |

**Why order leaked into the results:**

- **FIFO** exhausts tasks in catalog order.
- **Round-robin**'s first pass at a scarce budget reaches the
  first-listed (easy) tasks first.
- **greedy_prior** breaks its many tied hints (0.999 or 0.001) by lowest
  index.

Thompson sampling breaks ties at random and is affected less, but not
immune: −0.44 [−0.59, −0.29] at budget 240, larger than round-robin's
effect there. It passed O4 only through the |effect| < 0.5 threshold.
Random allocation also moved (+0.52 at 60), perhaps through its own
order-dependent indexing. **The lesson
for the harness:** any deterministic lowest-index tie-break turns catalog
order into a hidden feature. Real-task runs must shuffle order, and future
policies should break ties at random.

## The pilot question, re-scored on shuffled order

| Δ vs round_robin (true solves) | @60 | @240 | @480 |
|---|---|---|---|
| thompson (hints) | **+1.75** [1.36, 2.14] | +0.25 [−0.04, 0.54] | +0.22 [0.04, 0.39] |
| greedy_prior | +0.89 [0.44, 1.33] | −0.16 [−0.48, 0.15] | +0.05 [−0.16, 0.25] |
| thompson (no hints) | −0.95 [−1.36, −0.55] | −0.12 [−0.42, 0.17] | +0.16 [0.02, 0.30] |
| fifo | −4.83 | −5.28 | −2.54 |
| random | −1.08 | +0.13 | +0.12 |
| oracle_index (estimated) | +4.70 | +1.93 | +0.78 |

| exp-003 prediction, re-checked | Result |
|---|---|
| P1: thompson (hints) over-spends on dead tasks | ✔ |
| P2a: gain at budget 60 | ✔ +1.75 |
| P2b: no gain at budget 480 | ✘ +0.22 |
| P3: hint-free thompson ≈ round-robin at 240 and 480 | ✘ +0.16 [0.02, 0.30] at 480 |
| P4: hint-free thompson wastes fewer dead attempts than hinted | ✘ 279 vs 279 at 480 (holds at 240: 163 vs 214) |
| **H1 (pilot rule)** | **Inconclusive** (exp-003 said supported) |

## What we now believe (real tasks, DSL worker)

- **Adaptive allocation with hints helps when the budget is scarce:**
  +1.75 true solves out of 26 live tasks, and the result holds up under
  shuffling.
- **At moderate and generous budgets the advantage is small or absent.**
  exp-003's significant +0.62 at budget 240 was partly a task-order
  artifact.
- **Without hints, adaptivity hurts at a scarce budget**, in both orders.
- **The estimated oracle shows large headroom** (+4.7 at 60). That
  headroom is in *knowing p*, which no tested policy approximates well.
- **exp-003's conclusions are corrected here.** Its README links to this
  correction.
