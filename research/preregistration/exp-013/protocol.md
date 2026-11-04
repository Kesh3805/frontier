# exp-013: Which tail of the hint prior costs hinted Thompson its moderate-budget yield?

Status: **DRAFT, under review.** It will be frozen before any exp-013
outcome on the preregistered seeds is generated. The scoring script
[`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM DSL worker; trust class V1). Not
confirmatory.

## Why

Under the measured verification charge, hinted Thompson has lost to
round-robin at 1,320 CU three times on fresh seeds:

| Experiment | TH − RR at 1,320 CU |
|---|---|
| [exp-010](../../../results/exp-010/README.md) | −0.93 |
| [exp-011](../../../results/exp-011/README.md) | −0.86 |
| [exp-012](../../../results/exp-012/README.md) | −0.70 |

No change to the cost index closed the gap:

- flat cost: +0.10 and −0.01;
- cost per novel candidate: +0.05;
- ignoring reused rejections: −0.12.

In exp-011, removing hints brought the dead-task excess down to
round-robin's level (descriptive).

The hints in catalog v2 are deliberately miscalibrated at both extremes:

| Stratum | Tasks | Examples |
|---|---|---|
| hint ≥ 0.9 and dead | 3 | count_above_7, noisy_sum, hashed_bucket (hint 0.999, ~0.2 CU to generate) |
| hint ≥ 0.9 and solvable | 11 | sum, sort, reverse, … |
| hint ≤ 0.1 and solvable | 8 | count_odd (p̂ 0.72), sum_squares, max_abs, … (hint 0.001) |
| hint ≤ 0.1 and dead | 5 | product, mode, … |
| between | 7 | |

With k = 2, the prior is Beta(2m, 2(1 − m)):

- A 0.999-hint dead task after f failures is Beta(≈2, f), which keeps a fat
  upper tail.
- A 0.001-hint task starts at Beta(0.002, ≈2), which almost never samples a
  usable success probability.

That suggests two mechanisms (named in review by ChatGPT):

- **H-high:** optimistic extreme hints keep dead tasks attractive.
- **H-low:** pessimistic extreme hints starve solvable tasks of attempts,
  so fresh evidence never corrects the prior.

## Design

**`thompson_tempered`** (harness commit `HARNESS`) is hinted,
observed-cost Thompson with each tail of the hint pulled towards 0.5
before it enters the prior:

- a hint m ≥ 0.9 becomes 0.5 + `high` · (m − 0.5);
- a hint m ≤ 0.1 becomes 0.5 + `low` · (m − 0.5);
- other hints are unchanged.

Details:

- k stays at 2. Only the prior mean changes, not its concentration.
- A factor of 1 leaves that tail bit-identical, and (1, 1) is exactly
  `thompson`; a unit test asserts identical choices.
- **No oracle information:** which tasks are tempered depends on the hint
  value only. The dead/solvable label is used only in analysis.
- With factor 0.5, 0.999 becomes 0.7495 and 0.001 becomes 0.2505.

The harness also records, for real-task runs, attempts per task and the
true-solved task ids (`sim_task_attempts`, `sim_true_solved_tasks`). These
are ground-truth diagnostics outside the audited log. A dev run of six
existing policies on three dev seeds was identical on every other field to
the previous binary.

Configs come from [`make_configs.py`](make_configs.py): the exp-010 S-v2
configs (catalog v2, hidden suite v2, `--charge-model measured`,
`verify_cost_units` 11.6, 8 workers). Budgets are 330, 1,320 and 2,640
CU, with **fresh seeds 9001–9100**. Six policies:

| Label | Policy | High tail | Low tail |
|---|---|---|---|
| RR | `round_robin` | | |
| TH | `thompson` (hints) | 1 | 1 |
| H | `thompson_tempered` | 0.5 | 1 |
| L | `thompson_tempered` | 1 | 0.5 |
| HL | `thompson_tempered` | 0.5 | 0.5 |
| NH | `thompson` (no hints), anchor | | |

That is 6 × 100 × 3 = 1,800 audited runs. The primary metric is
`sim_true_solved`.

TH, H, L and HL form a 2 × 2. Paired by seed with the frozen
`analysis.py` bootstrap (10,000 replicates, seed 26102026):

- **High-tail main effect:** mean(H, HL) − mean(TH, L).
- **Low-tail main effect:** mean(L, HL) − mean(TH, H).
- **Interaction:** (HL − L) − (H − TH).

**Mechanism metrics**, each a per-run share of attempts, so that fewer
total attempts cannot pass for better allocation:

- high-hint dead share: attempts on the 3 high-hint dead tasks;
- low-hint solvable share: attempts on the 8 low-hint solvable tasks.

Counts per stratum, low-hint solvable solves and the overall dead-task
share are also reported.

**Multiplicity.** Holm over the two primary solve contrasts (P3, P4):

- A contrast whose 97.5% CI lies above zero is significant.
- If either is, the other is tested with its 95% CI.
- The Holm-adjusted lower bound is the one used for "materially
  beneficial".

## Frozen inputs

Harness commit `HARNESS`. SHA-256 of each file with LF line endings:

HASHES

## Seen before freezing (disclosed)

- **All published data from exp-010, exp-011 and exp-012.**
- **The dev identity check** on dev seeds 1–3 at 1,320 CU also ran
  `thompson_tempered` (1, 1) and (0.5, 0.5). Their solve counts were seen:

  | Dev seed | TH | HL |
  |---|---|---|
  | 1 | 20 | 20 |
  | 2 | 17 | 18 |
  | 3 | 18 | 16 |

  (1, 1) matched TH in solves and attempts on every seed. Three seeds say
  nothing useful about a ±0.5 effect, and no prediction was set after
  seeing them.
- **A dev smoke** of all six policies on dev seeds 1–2 at each budget.
  It checked only that configs load and the diagnostics are present.
- **A scoring-script check.** The smoke data was scored with TH copied into
  every tempered cell; every contrast was exactly 0. Synthetic data with
  known effects gave the right main effects and interaction.
- **A unit-test fixture:** a cheap 0.999-hint task with 20 fresh failures
  against an untried 0.001-hint task. Tempering the low tail is what lets
  the untried task in.

## Predictions

All at 1,320 CU unless stated.

- **P0: the loss replicates.** TH − RR has CI < 0.
- **P1: high-tail tempering moves attempts off high-hint dead tasks.** The
  high-tail main effect on the high-hint dead share has CI < 0.
- **P2: low-tail tempering moves attempts onto low-hint solvable tasks.**
  The low-tail main effect on the low-hint solvable share has CI > 0.
- **P3: high-tail tempering raises solves.** The high-tail main effect on
  solves has a Holm-adjusted CI > 0.
- **P4: low-tail tempering raises solves.** The low-tail main effect on
  solves has a Holm-adjusted CI > 0.
- **P5: tempering both beats untempered.** HL − TH has CI > 0.
- **P6: the scarce-budget gain survives.** At 330 CU, H − TH, L − TH and
  HL − TH each have CI lower bound > −0.3.
- **P7: verdict quality is unchanged.** No run has a false solve.

## Decisions

If P0 fails: **"The moderate-budget loss did not replicate."** Otherwise,
one decision per tail. For the high tail:

- **"Supported and materially beneficial"** if P1 and P3 hold and the
  Holm-adjusted lower bound exceeds +0.3.
- **"Supported"** if P1 and P3 hold.
- **"Shifts allocation without a demonstrated yield gain"** if P1 holds
  and P3 fails.
- **"Not supported"** otherwise.

The low tail is decided the same way, with P2 and P4.

Also reported: **"tempering closes the gap"** if P5 holds and HL − RR ≥
−0.3 (point).

The interaction, results at 2,640 CU, NH, and all means are reported
descriptively. A factor of 0.5 is one point on a continuum, and the result
says nothing about other factors.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config or catalog hash mismatch;
- a service protocol error.

## Limits

- **One catalog:** the hint miscalibration is the catalog's, by design. A
  different hint source would have different tails.
- **Thresholds:** the 0.9 / 0.1 thresholds put 3 more solvable tasks (hints
  0.92–0.98) in the high tail. Tempering them also lowers their prior.
- **One host's cost:** the measured charge constants are this Windows
  host's (exp-009). Linux's fixed cost is about 4.8× smaller.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier (`--sandbox none`).
