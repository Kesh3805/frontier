# Errata

Errors found in the code behind published results, the results they
affect, and how each was handled. Original results stay in place, marked,
and corrected re-runs are added next to them.

## E1: dispatch stopped permanently on a transient budget shortfall (kernels 0.1–0.2)

**Found by:** independent code review, 2026-10-27.

**What happened.** `runner.rs` set `stopped` the first time the available
budget fell below one attempt's worst-case reservation. In-flight attempts
normally settle well below their reservation, but once `stopped` was set
the budget they released was never used. How much budget was stranded
depended on the policy: at budget 60 in exp-004, round-robin committed 52.3
CU and hinted Thompson 43.3 CU.

**Affected:** every experiment, exp-000 to exp-006, both simulated and real.

**Fix (kernel 0.3.0).** When reservations block a dispatch, the runner waits
for in-flight attempts to settle. It stops only when nothing is in flight
and the budget still cannot cover a reservation. A regression test checks
that every non-idling policy ends with less than one reservation unspent.

## E2: repeated rejected programs were not counted as failures (kernels 0.1–0.2)

**Found by:** independent code review, 2026-10-27.

**What happened.** When an attempt produced content identical to an
already-rejected artifact, the old receipt was reused, which is correct.
But the attempt was then recorded as uninformative, so the task's failure
count did not increase. With the DSL worker, repeats are common: about half
of hinted Thompson's attempts at budget 240 in exp-004 were repeats.
Posteriors on dead tasks with confident hints therefore barely moved.

**Affected:** the real-task experiments exp-003, exp-004 and exp-006. In the
simulator, wrong answers are always unique, so this case could not arise in
exp-000 to exp-002.

**Fix (kernel 0.3.0).** A repeat of content with a failing receipt is
rejected by reusing that receipt, and counts as an informative failure. The
audit reports these as `reused_rejections`.

## E3: no check that the worker service serves the catalog's hidden suite

A catalog-v2 run against a service started without `--suite-version 2`
would have verified against v1 without any error. The exp-006 configs were
correct, so no published result is affected. Fixed in kernel 0.3.0: the
service's suite version and hidden seed must match the catalog.

## Handling

- exp-006 on kernel 0.2 was **stopped before completion** (budgets 60 and
  240 had finished) once E1 and E2 were confirmed. Its data were not
  analysed.
- exp-000 to exp-004 and exp-006 are **re-run on kernel 0.3.0** under their
  unchanged frozen protocols and scoring scripts. Each results page reports
  whether its preregistered verdicts change.

## Known limitation, not yet fixed

The worker service runs the extended ground-truth check in its own process,
which is only safe for the project's own DSL programs. Model-written code
must be checked inside the sandboxed verifier child before any LLM worker
is connected.
