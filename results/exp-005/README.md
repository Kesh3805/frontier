# exp-005 results: which hidden test suites reject wrong programs?

**Kind: offline verification study** on real worker programs. No
scheduler, no spend. Protocol and code are frozen at `63ade8f`
([protocol](../../research/preregistration/exp-005/protocol.md)); the study
code hash is `addfc524…`. Full output: [`study.json`](study.json).

**Pool.** 26 live tasks × 400 worker attempts on seed 424242. This gives
**491 distinct truth-wrong programs** that still reproduce the visible
examples (2,048 submissions in total).

**Truth.** Agreement with the reference on 7,801 inputs: an exhaustive set
of small lists plus a large random set.

| Hidden suite | Cases | False acceptance (distinct) | False acceptance (weighted) |
|---|---|---|---|
| random, ±20 (generated like **v1**, not v1's exact inputs) | 40 | **1.83%** (9 programs) | 0.83% |
| random, ±20 | 160 | 0 | 0 |
| random, ±20 | 640 | 0 | 0 |
| random, ±3 | 40 | 0 | 0 |
| random, ±3 | 160 | 0 | 0 |
| exhaustive {−2..2}, length ≤ 3 | 156 | 0 | 0 |
| exhaustive + random ±20 | 196 | 0 | 0 |
| exp-003/004 extended check (random ±50) | 1,000 | 0 | 0 |

The 9 programs the current suite accepts are all boundary bugs:

| Task | Accepted wrong programs | Bug |
|---|---|---|
| max0 | 7 | `max` over non-zero elements: wrong when the true maximum is exactly 0 |
| span | 1 | Same `max` bug |
| max_abs | 1 | Filter on \|x\| > 1: wrong when the largest \|x\| is 1 |

## Scorecard

| Prediction | Result |
|---|---|
| V1: exhaustive-156 beats random-160 | ✘ Tie at 0 (floor effect) |
| V2: false acceptance falls strictly 40 > 160 > 640 | ✘ 160 and 640 tie at 0 |
| V3: random-40 in ±3 beats random-40 in ±20 | ✔ 0 vs 1.83% |
| V4: exhaustive + random is lowest | ✔ (tied) |
| V5: the exp-003/004 extended check has false acceptances > 0 | ✘ 0, which is good news for those results |
| **Small-scope hypothesis (frozen rule: V1 decides)** | **"Refuted" by the rule. Read it as "not testable here":** this pool contains too few hard-to-catch bugs to separate any suite larger than 40 cases. |

## What it means

1. **The current hidden suite is the weak link.** It is the only one that
   lets wrong programs through. Across exp-003/004 (4,200 runs, 78,510
   accepted solves), 163 runs (3.9%) contained at least one false solve.
   For context: AlphaCode (arXiv:2203.07814, Table 2) reports 30–62% of
   wrong programs accepted by benchmark test suites of 8–21 tests, and 4%
   with about 200 generated tests.
2. **Value range matters more than size at equal cost.** With 40 cases,
   values in ±3 caught every bug that ±20 missed. Boundary values such as
   "max is exactly 0" are common when values are small.
3. **The extended check used as ground truth in exp-003/004 accepted no
   wrong program in this pool.** Their "true solve" counts are not
   inflated relative to this stronger truth (within the pool's coverage).
4. **Action taken:** catalog v2 adds exhaustive small inputs to every
   hidden suite. Future runs use it.

## Limits

- The pool comes from one DSL worker; LLM-written bugs may differ.
- There was one seed per suite.
- Truth is finite.
- The floor effect limits what this pool can distinguish. A harder pool
  (deeper programs, more tasks) is needed to rank suites larger than 40.
