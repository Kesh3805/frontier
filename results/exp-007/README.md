# exp-007 results: allocation on real dependency-structured tasks

**Kind: REAL TASKS, PILOT.** The worker is a non-LLM DSL search; the
verifier is trust class V1 with hidden suite v2. This is not a
confirmatory test.

**Protocol:** [`research/preregistration/exp-007/`](../../research/preregistration/exp-007/protocol.md),
frozen at `4f02843` and merged to `main` as `af2a78b`. The scoring script
was frozen with it.

**Runs.** 1,800 audited campaigns from `af2a78b` with a clean tree: 6
policies × 100 seeds × 3 budgets, on catalog v3 (24 problems, 19 live).
The audit includes the new checks that no attempt starts before its
prerequisites are verified and that every helper is an accepted artifact.
**No run had a false solve.** Wall time was about 2 hours.

Data: [`evaluation.json`](evaluation.json), `runs.csv.gz`,
[`manifests.json`](manifests.json).

The table shows true solves (of 19 live problems) and Δ against
round-robin, paired over 100 seeds, with 95% CIs.

| Policy | @120: solves | @120: Δ | @480: solves | @480: Δ | @1920: solves | @1920: Δ |
|---|---|---|---|---|---|---|
| round_robin | 3.35 | | 10.21 | | 17.65 | |
| thompson (hints) | 7.79 | **+4.44** [4.12, 4.76] | 14.66 | **+4.45** [4.13, 4.78] | 18.13 | +0.48 [0.29, 0.68] |
| greedy_prior | 7.61 | +4.26 [3.95, 4.57] | 14.24 | +4.03 [3.70, 4.36] | 15.73 | **−1.92** [−2.14, −1.70] |
| thompson (no hints) | 4.17 | +0.82 [0.64, 1.02] | 8.71 | **−1.50** [−1.76, −1.24] | 18.09 | +0.44 [0.31, 0.57] |
| random | 2.78 | −0.57 [−0.82, −0.31] | 10.47 | +0.26 [−0.02, 0.54] | 18.01 | +0.36 [0.22, 0.50] |
| oracle_index (estimated) | 10.37 | +7.02 [6.70, 7.35] | 17.06 | +6.85 [6.53, 7.18] | 18.79 | +1.14 [0.93, 1.35] |

## Scorecard

| Prediction | Result |
|---|---|
| D1: hinted Thompson beats round-robin at 120 | ✔ +4.44 |
| D2: hint-free Thompson beats round-robin at 120 | ✔ +0.82 |
| D3: \|TH − RR\| < 1 at 1920 | ✔ +0.48 |
| D4: greedy_prior beats round-robin at 120 | ✔ +4.26 |
| D5: TH spends more dead attempts than round-robin at 480 | ✔ +3.5 |
| **H1 on dependency tasks (pilot rule)** | **Supported** |

## What it shows, and what it doesn't

1. **The largest real-task scheduling effect so far.** With dependency
   structure, hinted Thompson more than doubles round-robin's verified
   yield at 120 CU (7.8 vs 3.4 problems). It still gains +4.45 at 480 CU.
   On single-step tasks (exp-004, corrected) the gain was +1.86 and only
   at the scarce budget. This matches the simulator, where the
   multi-approach regime R5 also gave the largest effects.
2. **Most of the gain is structure awareness plus hints, not learning
   alone.**
   - The static hint index (greedy_prior), which never learns, gets
     nearly all of it at 120 and 480 (+4.26, +4.03).
   - Hint-free Thompson gains a little at 120 (+0.82) and **loses** at 480
     (−1.50).
   - The expected-remaining-cost index favours short, cheap lemma routes,
     and the hints tell it which routes those are.
3. **Learning matters when budget is plentiful.** At 1,920 CU, the static
   index falls *behind* round-robin (−1.92): it keeps preferring routes
   that its fixed hints rate highly, including traps. Both Thompson
   variants recover from that (+0.48, +0.44).
4. **Headroom remains.** The estimated oracle reaches 10.4 and 17.1
   problems at 120 and 480 CU, against hinted Thompson's 7.8 and 14.7. The
   gap is in knowing which routes really work.
5. **Dead-task attempts at 1,920 CU** are high for both the oracle (+70)
   and hinted Thompson (+63). With most live problems solved, policies
   that never leave a worker idle spend leftover budget on what remains.
   This is the work-conservation effect noted in exp-003, not a
   misallocation of scarce budget.

## Limits

- **Worker and tasks:** the worker is DSL program search, not an LLM, and
  the 24 problems were designed by the project, including which routes
  are traps. Effect sizes depend on that design.
- **Hints:** probe-based hints. Their quality on lemma routes is part of
  what is being measured.
- **The oracle** uses calibration estimates.
- **Verifier:** trust class V1 (`--sandbox none`; the programs are the
  project's own).
- **Cost:** compute units are modelled charges, not measured CPU or cloud
  cost.

This is the first evidence in the program that adaptive allocation gives a
large, robust gain on real verified tasks, in the setting the review
pointed to. It still needs:

- a model-backed worker;
- held-out tasks the generator cannot see;
- a sandboxed (V2) run,

before it says anything about LLM research agents.
