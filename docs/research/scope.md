# Research scope and evidence boundaries

Status: **active**. Revised 2026-10-26 from dossier v0.1 after the
[source audit](source-audit.md).

## Question

> At a fixed end-to-end compute budget, does deciding *which research
> attempt runs next* from verifier feedback produce more independently
> verified results than strong fixed-allocation policies? Does a cheaper
> per-attempt generator, such as latent/text hybrid reasoning, add to that?

The unit of output is a **verified result**: a task whose acceptance
criterion, frozen before the run, has been met according to a verifier that
runs separately from the agent that produced the answer. Prose, agreement
between agents, and model confidence are not outputs.

## What is in scope now (phase 1, CPU-only, no spend)

1. **A research kernel** with typed immutable problem specs, a task DAG with a
   lifecycle, hard-cap budget accounting, content-addressed evidence,
   verifier receipts and a hash-chained event log with deterministic replay.
2. **Scheduling science in a synthetic environment.** The environment has
   known ground truth. It is used to find out *whether and where* adaptive
   allocation can beat strong fixed baselines at all. Every result from it
   is labelled **simulation**. It is a necessary-condition test for H1, not
   evidence about LLM research agents.
3. **Real verifiers on CPU** (algorithm tasks with property tests and
   reference implementations), together with adversarial fixtures that try
   to bypass them.
4. **Interface-only adapters** for hosted models and HybridAgent. They report
   honestly when the hardware or credentials needed are missing.

## Out of scope for phase 1

- Any paid inference, GPU rental or model training (these need an explicit
  budget authorisation).
- Any claim about Navier–Stokes, or about discovery "acceleration" in general.
- Lean tasks, until a pinned Lean/Mathlib verifier image exists.
- Distributed deployment: no message bus, Kubernetes, PostgreSQL or
  microservices.

## Hypotheses and their current status

| ID | Statement (operational) | Status |
|---|---|---|
| H1 | With text-only workers, adaptive allocation verifies more problems than the **stronger** of {strict fixed slice, work-conserving round-robin} at equal compute caps. It is also reported against a static-prior heuristic and a bandit baseline (Zuo et al. 2506.12721). | **Untested with LLM workers.** The non-LLM real-task pilot ([exp-004](../../results/exp-004/README.md)) is **inconclusive**, both on kernel 0.2 and on the corrected kernel 0.3 ([re-run](../../results/rerun-k0.3/README.md)): a clear gain only at the scarce budget (+1.86 [1.47, 2.26]). On dependency-structured real tasks ([exp-007](../../results/exp-007/README.md)), the pilot rule is **supported**: +4.44 [4.12, 4.76] at a scarce budget and +4.45 at a moderate one, still with a non-LLM worker. With fail-fast verification charging ([exp-008](../../results/exp-008/README.md)) it holds on dependency tasks (+5.07 at the scarce budget, +3.60 at the moderate one), while the single-step margin shrinks to +2.29 and vanishes at larger budgets. Its simulation precondition (H1-sim) failed in one regime, so any real-worker test must report results by budget regime and against round-robin. |
| H1-sim | In a synthetic environment where the scheduler sees only verifier receipts, posterior-based allocation beats work-conserving round-robin on verified yield when branch success rates are heterogeneous. It does not beat it by a material margin (≥ 0.5 problems) when they are homogeneous. | **Rejected** under the frozen rule (exp-000, simulation): positive in 5 of 6 primary cells, negative in R2-formal-plateau at moderate budget. Hints and learning both contributed to single-step gains, and the multi-step gain came mostly from structure awareness. See [`results/exp-000`](../../results/exp-000/README.md). The loss replicated in [exp-001](../../results/exp-001/README.md), and the advantage elsewhere survived correlated failures and verifier noise. [exp-002](../../results/exp-002/README.md) traced the loss to optimistic hints on dead problems the hints don't flag; with perfect (simulated) detection of dead problems, the loss became a gain. |
| H2 | Hybrid workers lower all-in cost per verified solution at non-inferior verified success, compared with matched text-only workers. | **Untested; blocked.** There is no GPU, and no matched text checkpoint is released (C5). |
| H3 | Hybrid × adaptive interaction on verified yield. | **Untested; blocked by H2.** |

### H2

The released HybridAgent checkpoints allow only two comparisons, and both
are confounded:

- **H2-ablation:** the same checkpoint with latent mode on and off. Running a
  hybrid-trained model with latent mode off is out of distribution, so this
  is biased against the text arm.
- **H2-base:** HybridAgent against its Qwen3-Base backbone with
  general-purpose instruction tuning. Training differences dominate this
  comparison.

Neither isolates the effect of the *mode*. A causal H2 needs a text-only
model trained with matched SFT and RL data (the released HybridSFT/HybridRL
datasets make this possible), and that costs GPU time. Until then H2 results
are **exploratory**, and if they are reported, both comparisons are reported
together as bounds.

## Cheaper tokens vs cheaper research

The cost of one verified result splits into generation (fraction *g*) and
everything else: prefill, tools, verification, retries, orchestration and
idle allocation. Suppose a generator cuts decode cost by a factor *k*, as the
HybridAgent paper models (k ≈ 2.7–3.7, decode only). The end-to-end saving is
then at most

    1 / ((1 − g) + g / k)

and only if success rates do not change. With g = 0.5 and k = 3.7, the
bound is ≈ 1.57×. Measuring *g* is therefore a prerequisite for H2: if
verification dominates, a cheaper generator cannot help much. The kernel
records generation and verification charges separately for this reason.

## Answers to the reassessment questions

1. *Scientifically meaningful?* Yes, if it is framed narrowly. Allocating
   compute across many verifiable attempts under a budget is a real problem
   with real costs. "Compressing discovery" in general is not measurable
   here.
2. *Novel?* The pieces have prior art: multi-agent Pareto scaling, budget-aware
   tool use (BATS/CATS), verifier-guided allocation, constrained-policy
   allocation, and bandit allocation across queries. Any contribution is a
   **tested combination** applied to dependency-structured evidence graphs,
   with full-system accounting. That contribution exists only if experiments
   support it.
3. *Measurable?* Yes: verified count at a fixed cap, with every cost
   recorded. In simulation, ground truth is known exactly.
4. *Strong baselines?* Required: work-conserving round-robin, a static-prior
   heuristic, random allocation, a bandit-elimination baseline after Zuo et
   al., and (simulation only) a labelled oracle-informed index.
5. *Buildable?* The kernel and the scheduling science are buildable on CPU.
   H2 is not, on current hardware.
6. *Main bottlenecks:* sparse and delayed verifier signal; correlated
   failures across branches; verification cost; for H2, the missing matched
   baseline.
7. *Falsification:* see each preregistration. For H1-sim (frozen exp-000
   rule), it is rejected if any of the six heterogeneous primary cells has a
   95% CI entirely below 0, or if four or more of those CIs include 0.
8. *Could something simpler match it?* Possibly. Work-conserving round-robin
   with deduplication is the default to beat, and losing to it is a
   publishable outcome.
9. *Proxy risk:* a synthetic environment is a proxy by construction. Results
   transfer only to the extent that its success-rate distributions resemble
   real attempt distributions. Those must be measured in Stage 2 before any
   transfer is claimed.
10. *Cheaper tokens vs cheaper research:* see the bound above.

## Claim vocabulary

`generated_hypothesis` < `plausible_candidate` < `mechanically_verified` <
`empirically_reproduced` < `independently_reviewed` < `scientifically_accepted`.
`rejected` and `contested` sit outside this order. Software can reach
`mechanically_verified` on its own. Every higher level needs a recorded
human or external act.
