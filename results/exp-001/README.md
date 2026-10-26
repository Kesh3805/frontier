# exp-001 results: mechanism, correlated failures, imperfect verifiers (simulation)

**Kind: SIMULATION.** Synthetic environment, no models, no spend.

Protocol: [`research/preregistration/exp-001/protocol.md`](../../research/preregistration/exp-001/protocol.md),
frozen at `ffa74c9`. Configs were hashed at `667476f`.

Execution:

- 40,200 runs from source commit `ffa74c91f83dda5d52d6bb587dc16fcbfdb8a6d3`
  with a clean tree, kernel 0.2.0.
- Host: Windows x86_64, i5-1135G7, about 6 minutes in total.
- Every run passed the log audit.

Scoring:

- Predictions were scored mechanically by
  [`evaluate.py`](../../research/preregistration/exp-001/evaluate.py). That
  script was written after the freeze and before any output was inspected.
- It only applies the protocol's rules, using the frozen `analysis.py`.
- Full numbers are in [`evaluation.json`](evaluation.json); per-run rows in
  `runs.csv.gz`.

Δ = thompson(k=2, hints) − round_robin, measured in problems solved out of
50, with 95% paired bootstrap CIs over 200 seeds.

## Prediction scorecard

| Prediction | Result |
|---|---|
| P-A0: the exp-000 R2-moderate loss replicates | ✔ Δ = −0.26 [−0.38, −0.14] (exp-000: −0.19 [−0.30, −0.09]) |
| P-A1: no loss with noise-free hints | ✘ Δ = −0.165 [−0.26, −0.065] at B=600 and −0.085 [−0.155, −0.02] at B=1200 |
| P-A2: Δ decreases monotonically with hint noise | ✘ Holds at B=300 and B=600; fails at B=1200 (differences ≤ 0.03) |
| P-A3: Δ decreases with prior strength k | ✘ Holds at B=600 (both noise levels); fails at B=1200 (differences ≤ 0.03) |
| P-A4: hint-free Thompson does no harm at B=1200 | ✔ +0.05 [0.015, 0.09] |
| **Hypothesis M (misleading hints cause the loss)** | **Refuted under the frozen rule, but confounded. See below.** |
| P-B1: correlation lowers every policy's yield | ✔ All 30 policy × cell comparisons |
| P-B2: Δ shrinks as stickiness ρ rises | ✘ Holds at scarce budget (all 3 cells); reversed at moderate budget (all 3 cells) |
| P-B3: some cell turns negative at ρ = 0.9 | ✘ None |
| **Adaptive advantage robust to correlation** | **Yes, under the frozen rule:** every cell positive at ρ=0 stays positive at ρ=0.9 |
| P-C1: a 2% false-positive rate produces false solves for every policy | ✔ |
| P-C2: adaptive allocation produces fewer false solves | ✘ Not in R2 (+0.07, n.s.); more in R3 (+0.59 [0.30, 0.88]) |
| P-C3: a 20% false-negative rate lowers true yield for every policy | ✔ |
| P-C4: the sign of Δ on true solves is unchanged by verifier noise | ✔ (R2 −, R3 +, R5 +) |

## Findings

### 1. The R2-moderate loss is real, and noisy hints are not the explanation

The loss replicated with fresh random streams. It did not go away with
noise-free hints. Hint noise and prior strength did make it worse at B=600,
but not at B=1200, where all differences are within about 0.03 problems.
Because P-A1 failed, the frozen rule marks hypothesis M as **refuted**.

**Confound, found after the run:** "noise 0" does not make hints perfect.
By construction ([`env.rs`](../../crates/frontier-sim/src/env.rs)), a dead
problem (11% in R2) gets a hint drawn *as if it were alive*, at every noise
level. So no condition in Part A gives the scheduler correct hints about
dead problems. Two observations fit this:

- hint-free Thompson ties round-robin exactly at B=600 (0.00 [−0.065, 0.065]);
- the static hint index loses about one problem everywhere.

Our revised, **untested** hypothesis is optimistic priors on dead
problems. Pseudo-successes from a high hint make the posterior decay slowly
over repeated failures, so dead problems keep absorbing attempts. exp-002
should test it by varying how informative hints are about deadness. We do
not claim this mechanism from this experiment.

### 2. Correlated failures cut yield, and do not remove the adaptive advantage

With ρ = 0.9, every policy solves less: for example R3 moderate drops from
17.9 to 9.9 for round-robin. At the scarce budget, the advantage shrinks
sharply as ρ rises:

| Cell | Δ at ρ=0 | Δ at ρ=0.9 |
|---|---|---|
| R2 | +1.40 | +0.22 |
| R3 | +3.35 | +0.48 |
| R5 | +13.2 | +11.4 |

At the moderate budget it *grows*:

| Cell | Δ at ρ=0 | Δ at ρ=0.9 |
|---|---|---|
| R2 | −0.26 | **+0.80** |
| R3 | +1.02 | +1.76 |
| R5 | +1.52 | +2.15 |

One reading, untested: when failures persist, moving away from a failing
obligation is worth more once there is enough budget to act on it.

### 3. Verifier false positives are amplified by the number of attempts

With fpr = 0.02 per check, the share of *accepted* problems that are
actually wrong is about 12% in R2, 23–25% in R3 and 8–11% in R5. This is a
base-rate effect: every wrong attempt that gets checked is another chance
for a false acceptance. A verifier that is "98% specific" per check is far
from 98% trustworthy per accepted result. For real systems, the per-check
false-positive rate must be well below 1 / (expected checks per problem).
Adaptive allocation does **not** mitigate this: in R3 it produced
slightly more false solves than round-robin.

Separately, a 20% false-negative rate hurts round-robin more than Thompson
in R5 (Δ grows from +1.5 to +3.5). The sign of Δ on true solves never
flipped.

## Status of the program's hypotheses

- **H1-sim** is still **rejected** as stated. Adaptive allocation is not
  uniformly better. The failure regime (R2, moderate budget, i.i.d.
  attempts) replicates. Where the advantage exists, it survives correlated
  failures and imperfect verifiers in this simulator.
- **Practical implication:** neither Thompson variant dominates.
  - Hint-free Thompson was never worse than round-robin at moderate
    budgets (≥ −0.02), but lost at scarce budget in R3, by as much as −1.0.
  - Hint-using Thompson gained up to +3.3 in that same R3 cell, but lost in
    R2-moderate.
  - **Treat difficulty hints as a measured input: calibrate them, including
    on unsolvable problems, before relying on them.**
- **Verification quality matters as much as allocation.** At fpr = 0.02,
  false solves (≈5 per 50 problems) were several times larger than any
  allocation effect in R2.

## Reproducibility

This is the first experiment on kernel 0.2.0, which replaced
platform-library `ln`/`exp` with portable fdlibm ports. The smoke log head
is pinned in CI so that cross-platform identity is tested on Linux. If
that check passes, these results are platform-independent. exp-000 used
kernel 0.1.0 and reproduces exactly only with its own Windows release
binary; see the erratum in [`results/exp-000`](../exp-000/README.md).

## Limitations

These were accepted in advance in the protocol:

- correlation is lag-1 and within an obligation only;
- verifier errors are independent;
- the hint model treats dead problems as live (now identified as
  consequential);
- one problem count (50);
- the oracle index assumes independent attempts.
