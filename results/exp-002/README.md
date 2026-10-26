# exp-002 results: optimistic hints on undetected dead problems (simulation)

**Kind: SIMULATION.** Synthetic environment, no models, no spend.

Protocol and scoring script:
[`research/preregistration/exp-002/`](../../research/preregistration/exp-002/protocol.md),
both frozen at `4ff7d8a` (the scoring script was frozen this time too).

Execution:

- 12,600 runs from that commit with a clean tree, kernel 0.2.0, about 2
  minutes on the laptop CPU.
- Every run passed the log audit.
- CI passed on the freeze commit, including the cross-platform pinned
  smoke head.

Full numbers are in [`evaluation.json`](evaluation.json); per-run rows in
`runs.csv.gz`.

Notation:

- **λ** = probability that a dead problem's hint correctly reads
  near-zero.
- **Δ** = thompson(k=2, hints) − round_robin, in problems solved (of 50).
- **ΔD** = the same difference in attempts spent on dead problems.
- CIs are 95% paired bootstrap over 200 seeds.

## Prediction scorecard (primary cell: R2, budget 600)

| Prediction | Result |
|---|---|
| P1: Thompson over-spends on dead problems at λ=0 | ✔ ΔD = +46.9 attempts [42.3, 51.5] |
| P2: that over-spend falls as λ rises | ✔ 181 → 155 → 140 attempts |
| P3: Δ rises with λ | ✔ −0.26 → +0.29 → +0.56 |
| P4: no loss with full detection | ✔ Δ(1) = +0.56 [0.44, 0.69]; the strong version (CI above 0) also holds |
| P5: stronger priors over-spend more at λ=0 | ✔ k=0.5: 179, k=2: 181, k=8: 188 (the 0.5 → 2 step is small) |
| Secondary: P1 and P3 in R2 at budget 1200 and in R3 at budget 600 | ✔ all four |
| **Mechanism O** | **Supported under the frozen rule** |

## What this establishes

**The exp-000/exp-001 loss is explained, in this simulator, by optimistic
priors on dead problems the hints don't flag.** At λ=0 the λ=0 cell
reproduces exp-001 exactly (round-robin 40.14, Thompson 39.88). In that
cell, Thompson with hints spends about 47 more attempts than round-robin
on problems that can never be solved. The reason is that a live-looking
hint adds pseudo-successes to the prior, which then decays slowly with
repeated failures. Those attempts come out of solvable problems.

As λ increases, the over-spend shrinks and the loss turns into a gain. At
full detection (λ=1), Thompson reaches +0.56 against an oracle gap of
+0.73. Hint-free Thompson ignores hints and stays at Δ = 0.00 for every λ,
as expected.

The effect is largest where dead problems are common:

| Regime | Δ at λ=0 | Δ at λ=1 | Oracle |
|---|---|---|---|
| R3 (30% dead), budget 600 | +1.02 | **+3.85** | +5.02 |
| R2, budget 1200 | −0.08 | +0.13 | +0.17 |

**Even where Thompson already wins, it wastes attempts on dead problems.**
In R3 at λ=0 it leads by +1.0 problems, yet spends 87 more attempts on
dead problems than round-robin. The good allocation among live problems
and the waste on dead ones are separate effects that partly cancel.

## Implication for the program

What a hint says about *unsolvability* matters more than which allocation
algorithm is used. In R3, moving dead-problem detection from 0 to 1 is
worth +2.8 problems for the same scheduler, almost three times the gap
between that scheduler and round-robin at λ=0.

For real research tasks, this points to investing in signals that a
branch is impossible: counterexamples, refuted lemmas, failed
preconditions, and calibrated "unsolvable" predictions. It also means
treating difficulty predictors as untrusted until their calibration on
unsolvable problems has been measured. This is a hypothesis for real-task
work, not a result about LLM workers.

## Caveats

- **Detection here is perfect when it fires.** Live problems never get
  dead-looking hints, which favours hint use. A real predictor will also
  have false alarms, so the λ=1 gains are an upper bound for this
  mechanism.
- **"Dead" means p = 0 exactly.** Near-dead problems (p ≈ 0.001) would
  behave similarly, but were not tested.
- **Dead attempts are not all misallocation.** Non-idling policies spend
  leftover budget on dead problems once live ones are exhausted; the
  oracle spends 121 attempts this way in R2 at budget 600. Only the excess
  over round-robin (ΔD) measures misallocation.
- Single-step problems, 50 per campaign, i.i.d. attempts (exp-001 shows
  correlation changes magnitudes).

## Program status

H1-sim stays **rejected as originally stated**, because adaptive
allocation is not uniformly better. The failure mode now has a supported
mechanism and a remedy that has been tested in simulation: calibrated
detection of unsolvable problems, or not using hints at all. Both still
need confirmation on real verifier-backed tasks.
