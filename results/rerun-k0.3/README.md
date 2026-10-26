# Corrected re-runs on kernel 0.3.0

**What and why.** An independent code review found two bugs in the runner
([errata E1/E2](../../docs/research/errata.md)):

- **E1:** dispatch stopped for good on a transient budget shortfall,
  stranding a policy-dependent share of the budget;
- **E2:** a repeat of an already-rejected program was not counted as a
  failure (real tasks only).

Kernel 0.3.0 fixes both. Every affected experiment was re-run under its
**unchanged frozen protocol, configs and scoring script**. The originals
stay in place, marked with an erratum banner.

**Execution.**

- 16 experiment arms, all from commit
  `4f68438f1827f2bd406f9afce95f48f7db693903`, with a clean tree in every
  manifest ([`manifests.json`](manifests.json)). Every run passed the log
  audit.
- Host: Windows, i5-1135G7, 8 threads.
- exp-003 is not re-run: exp-004 supersedes it.
- exp-005 is not affected: it is an offline verification study with no
  scheduler.

Per-run data and scored evaluations are in each subdirectory.

## Did any preregistered verdict change?

| Experiment | Verdict on kernel 0.1/0.2 | Verdict on kernel 0.3 | Changed? |
|---|---|---|---|
| exp-000 (simulation) | H1-sim **rejected** (5 of 6 primary cells positive, R2-moderate negative) | **rejected**, same pattern | No |
| exp-001 (simulation) | P-A0 ✔, P-A1–A3 ✘, M refuted; P-B1 ✔, B2/B3 ✘, robust ✔; P-C1/C3/C4 ✔, C2 ✘ | identical, prediction by prediction | No |
| exp-002 (simulation) | all predictions ✔, mechanism O **supported** | identical | No |
| exp-004 (real, shuffled) | P1, P2a ✔; P2b, P3, P4 ✘; H1 pilot **inconclusive** | P1, P2a, **P3, P4 ✔**; P2b ✘; H1 pilot **inconclusive** | P3 and P4 flip to ✔ |
| exp-006 (real, strong verifier) | stopped before completion on kernel 0.2 | W1, W2, W4 ✔; W3 ✘; "strong verification costs true yield" | First complete result ([report](../exp-006/README.md)) |

## Magnitudes that moved

**Simulation.**

- **exp-000, R2-formal-plateau, scarce budget:** Δ(Thompson − round-robin)
  fell from +1.46 to **+0.33** [0.13, 0.55]. Under E1 the old run had
  stranded round-robin budget, and correcting that shrinks the apparent
  gain.
- **exp-000, R0-homogeneous, scarce budget:** +0.41 [0.05, 0.76] became
  −0.13 [−0.49, +0.24]. The control cell now behaves as a null.
- **The losing cell is still there:** exp-000/001 R2-moderate is −0.34
  [−0.47, −0.21] (was −0.19 and −0.26).
- **Everything else is within a few tenths:**
  - exp-001 Part B scarce R5: +13.2 → +12.7;
  - exp-002 full-detection gain in R3: +3.85 → +3.94;
  - false-accept shares at fpr = 0.02: 12 / 24 / 9% for R2 / R3 / R5.

**Real tasks (exp-004).**

| Δ vs round-robin, true solves | Budget | Kernel 0.2 | Kernel 0.3 |
|---|---|---|---|
| thompson (hints) | 60 | +1.75 [1.36, 2.14] | **+1.86** [1.47, 2.26] |
| thompson (hints) | 240 | +0.25 | +0.19 [−0.11, 0.48] |
| thompson (hints) | 480 | +0.22 | +0.25 [0.09, 0.41] |
| thompson (no hints) | 60 | **−0.95** [−1.36, −0.55] | **−0.12** [−0.44, 0.20] |
| greedy_prior | 60 | +0.89 | +0.29 [−0.13, 0.70] |

Committed budget at 60 CU went from 43–52 CU (unequal across policies) to
57–58 CU for every policy.

## What this changes in the conclusions

1. **The scarce-budget gain on real tasks survives the fix**, and slightly
   grows (+1.86). Hinted Thompson is the only non-oracle policy with a
   clear gain at budget 60.
2. **"Hint-free adaptivity hurts at a scarce budget" was mostly a bug
   artifact** on real tasks: −0.95 becomes −0.12, not significant. In the
   simulator the comparable cell (exp-001 Part B, R3 scarce) is still
   negative, so this is a real-vs-simulated difference to keep in mind.
3. **Neither hints alone nor learning alone delivers the gain.** The static
   hint index (+0.29, not significant) and hint-free Thompson (−0.12) both
   fall short of hinted Thompson (+1.86). The combination is what works
   here.
4. **The simulator's headline numbers were partly inflated by E1** (R2
   scarce +1.46 → +0.33), but none of its frozen verdicts changed.
