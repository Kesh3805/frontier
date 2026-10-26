# exp-005: Which hidden test suites reject wrong programs? (verification study)

Status: **FROZEN** before any exp-005 outcome was generated. The study code
[`python/frontier_py/realtasks/suite_study.py`](../../../python/frontier_py/realtasks/suite_study.py)
is frozen with this protocol; its hash is recorded in the freezing commit.
Kind: **real programs, offline verification study**. No scheduler, no spend.

## Why

exp-003 measured real false acceptances: wrong programs passed the frozen
hidden suite (40 random lists with values in ±20, plus the visible
examples). Before the freeze, I inspected those programs; they were found
while designing this study. They are boundary bugs:

- `max` over non-zero elements, which is wrong only when the true maximum
  is exactly 0;
- a filter on |x| > 1, which is wrong only when the largest |x| is 1.

Random inputs rarely produce these cases. The software-testing "small
scope hypothesis" suggests that exhaustively testing small inputs catches
more such bugs than random testing of the same size. This matters for
FRONTIER because, by exp-001's base-rate argument, verifier false
acceptances grow with the number of attempts.

## Design

**Program pool.** For each of the 26 live tasks, the worker makes 400
attempts on pool seed 424242, which is disjoint from every earlier seed.
The pool keeps the distinct programs that reproduce the visible examples,
weighted by how often each was produced.

**Truth.** A program is wrong if it disagrees with the reference on
either:

- every list over {−3..3} of length ≤ 4 (2,801 inputs); or
- 5,000 random lists (length 0–20, values in ±100).

**Suites compared:**

- random 40 / 160 / 640 lists, values in ±20 (the first is the current
  suite's generator);
- random 40 / 160 lists, values in ±3;
- exhaustive: every list over {−2..2} of length ≤ 3 (156 inputs);
- exhaustive 156 plus random 40 in ±20;
- the exp-003/004 extended check: 1,000 random lists in ±50. Its inputs
  are verified identical to those used there.

**Metric.** False-acceptance rate: the share of truth-wrong programs that
pass the suite, counted per distinct program and weighted by production
frequency.

## Predictions (both counts unless stated)

- **V1:** exhaustive-156 has a lower false-acceptance rate than random-160
  in ±20, at a similar number of cases.
- **V2:** false acceptance falls as random suite size grows in ±20:
  40 > 160 > 640 (distinct count).
- **V3:** random-40 in ±3 has a lower rate than random-40 in ±20.
- **V4:** exhaustive-156 plus random-40 has the lowest rate of all suites
  (ties allowed).
- **V5:** the exp-003/004 extended check has a rate above 0. If so, the
  "true solves" reported there are upper bounds.

**Decision:**

- the small-scope hypothesis is **supported** in this setting if V1 and V4
  hold;
- it is **refuted** if V1 fails;
- otherwise it is **mixed**.

## Limits

- Truth is a finite test, so the study measures disagreement with a strong
  finite suite rather than proven correctness.
- The program pool comes from one DSL and one worker; LLM-written bugs may
  differ.
- Suites are seeded once each, so their sampling variance is not
  estimated.
