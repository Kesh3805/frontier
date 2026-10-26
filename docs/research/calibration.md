# FRONTIER calibration and prior-art review (2026-10-26)

Every number below has a URL and a locator. Fits are my own; the scripts are in
[`research/calibration/fit.py`](../../research/calibration/fit.py) and [`fit2.py`](../../research/calibration/fit2.py) (require scipy; not a project dependency) (scipy least squares or binned MLE).
UNVERIFIED marks claims I did not read in the source.

## 1. Zuo and Zhu, arXiv 2506.12721 (v2, 23 Apr 2026)
URL: https://arxiv.org/html/2506.12721

### Algorithm 1, "Elimination" (Sec. 4.2)
- **Arm:** a query x. One pull generates one response (one unit of compute).
- **Inputs:** query set S, budget B, reward oracle r, per-round per-query budget K, and threshold γ.
- **Loop:** initialise the active set A = S. While B > 0 and A is non-empty, give every x in A K new responses and set B -= K. Track the best reward r̂(x). If max_i r(x, y_i) ≥ γ, remove x from A.
- **What gets eliminated:** queries that are **solved**, not hopeless ones. Queries still active at the end count as unsolved.
- **Defaults:** K = 1, with an ablation over K ∈ {1, 2, 4, 8} (Sec. 5.4). γ is ablated over {0.97, 0.98, 0.99, 1.0}, and 1.0 is slightly best (App. C.2.1, Fig. 7). Temperature is 0.6 (C.1.1).

### Variants (App. A; hyperparameters in C.1.1)
- **UCB:** argmax r̂(x) + λN(x)^-1/2, with λ = 1.
- **Gap:** argmin (γ − r̂(x))N(x)^-1/2.
- **Entropy:** argmax H(x) + λN(x)^-1/2, with λ = 3. H is the entropy of the empirical answer distribution.
- **Per-query cap `max_sample`:** all three variants use one, set per scene and budget. Values range from 12 to 300 (Table 2). On the Hard sets the grid is {36, 48, 64}.
- **Other variants:** a streaming variant and a token-matched variant (Tables 3–5).

### Theory (Sec. 4.4)
- Thm 1: the method needs a budget of Θ̃(Σ_x 1/Δ_x), where Δ_x is the per-sample success probability. Uniform allocation needs Ω̃(max_x |S|/Δ_x).
- Prop. 1: explore-then-commit needs Ω̃(Σ max(m, 1/Δ_x)).

### Baselines (Sec. 5.1)
- **Uniform:** Best-of-N with budget B/n per query (Sec. 3). The excerpt I read does not say whether Uniform stops early on solved queries; the fixed B/n wording suggests it does not.
- **Two-Stage:** stage 1 spends 25%, 50% or 75% of the budget uniformly, and the best of the three is reported. Stage 2 allocates the rest "proportionally". What it is proportional to is UNVERIFIED.

### Headline results
Coverage gains over Uniform (Figs. 1–3):
- MATH-500: +2.4 to +11.1 pts.
- LiveCodeBench: +6.47 to +9.97 pts.
- AIME25: +10.82 pts at budget 16.
- Stated efficiency: 1.8–4× less compute.
- Table 5 (LiveCodeBench, R1-Distill-8B, budget 4): Uniform-GT 73.43 vs Elim-GT 84.66, a gain of +11.23. This is the abstract's headline.

**Token matching shrinks the gain.** Table 4 (MATH-500, Llama-3.2-1B, budget 16) gives Uniform 59.60, Elim 63.45 and Elim token-matched 60.90, so about two-thirds of the gain disappears. At budget 4 the same table gives 41.80 / 43.70 / 42.70. On LiveCodeBench (Table 5) the gain survives token matching (84.50 at budget 4).

**Dead share on the hard subsets** (Tables 6–7, 64 responses per query):
- MATH-500-Hard-8: 49 of 71 queries unsolvable (69%).
- MATH-500-Hard-16: 43 of 56 unsolvable (77%).

### Our `Elimination` (crates/frontier-sched/src/lib.rs) vs the paper: fixes needed for "faithful"
1. **The elimination rule is inverted.** Ours drops problems whose optimistic bound on `verified_tasks/attempts` falls below `threshold`, which is closer to racing. Zuo drops **solved** queries. The runner already closes solved problems (runner.rs:474–475), so Zuo-Elim in our sim is K-per-round round-robin over unsolved problems. Our `min_attempts`, `threshold` and `log_term = 2 ln(total)` have no counterpart in the paper.
2. **The statistic counts intermediate lemmas.** Ours includes non-terminal obligations. Zuo's per-arm signal is query solved or not (r ≥ γ). Use terminal success only.
3. **Rounds.** Zuo runs synchronous rounds: every active arm gets K samples, then B -= K. Ours is asynchronous fewest-first, counting in-flight attempts. Add an explicit round/K parameter, or prove and document the equivalence when workers equal 1.
4. **Budget unit.** Zuo counts samples, and token-matching is a secondary analysis. Ours charges lognormal cost units. Add a sample-count budget mode and report both.
5. **Per-arm cap.** Add `max_sample`, as the UCB, Gap and Entropy variants have.
6. **UCB variant.** Implement r̂ + λN^-1/2 with λ = 1. With a binary verifier, r̂ = 0 for every active arm, so it degenerates to fewest-samples-first. State this.
7. **Entropy variant.** It needs answer diversity, which the sim does not generate. Either add a synthetic entropy signal correlated with solvability (Tables 6–7) or declare it out of scope.
8. **Problem shape.** Zuo has one arm per query. Run the faithful replication with approaches = 1 and chain = 1, and label any within-problem task choice as our extension.
9. **Baselines.**
   - Uniform corresponds to our `FixedSlice` (no redistribution), **not** `RoundRobin`. Our work-conserving `RoundRobin` already is Zuo-Elim with K = 1.
   - Add Two-Stage with ratios {25, 50, 75}% and report the best.
10. **Reporting.** Use coverage (fraction solved) as the metric, averaged over ≥4 seeds as the paper does.

## 1b. BATS, arXiv 2511.17006 (Liu et al., v2, 17 Aug 2026)
URL: https://arxiv.org/html/2511.17006
- **Name:** "CATS" does not appear in the paper.
- **Budget Tracker (Sec. 3.1):** a prompt-level `<budget>` block showing used and remaining tool calls.
- **BATS (Sec. 4):** budget-aware planning plus self-verification with SUCCESS/CONTINUE/PIVOT decisions.
- **Scope:** budgets are per question, and the paper does no cross-task allocation (Sec. 2.1).
- **Results:**
  - BATS on Gemini-2.5-Pro, BrowseComp: 24.6 vs ReAct 12.6 (Table 3).
  - The tracker alone on SWE-bench Verified at budget 50: 55.4% vs 36.8% (Table 7).
  - The tracker alone on τ²-bench: Pass^4 of 27.2% at budget 10 vs 26.3% at budget 50 (Table 6).
- **Applicability to us:** the tracker transfers to non-search tasks such as coding (Tables 6–7). The CONTINUE/PIVOT rule is an **intra-problem approach-switching** policy. It is a natural baseline for our approach-level choice, not for cross-problem allocation.

## 2. Empirical per-problem success distributions

Model: pass@k = (1 − d)·[1 − B(α, β+k)/B(α, β)].

| Source (URL, locator) | Data | Fit |
|---|---|---|
| Brown et al. 2407.21787v3, Table 2 (GSM8K, Llama-3-8B, 10k samples) | pass@1 bins 0–10/10–25/25–75/75–100% contain 5/10/29/84 of 128 problems | binned MLE, d=0: α=0.81, β=0.26 |
| Su et al. 2505.00127, Table 4 (10 samples) | MATH R1-Distill: all correct 46.5%, none 11.9% | α=0.40, β=0.18 |
| same, Table 4 | MATH R1-Preview: all correct 71.4%, none 9.6% | α=0.25, β=0.055 |
| same, Table 4 | GSM8K R1-Distill / R1-Preview | α=0.94, β=0.47 / α=0.62, β=0.12 |
| DeepSeek-Prover-V2 2504.21801v2, Table 1 (miniF2F) | 671B CoT: k=1/32/1024/8192 gives 61.9/82.4/86.6/88.9% | d=0.11, α=0.38, β=0.17 (max residual 0.007) |
| same, Table 1 | 7B non-CoT: 55.5/68.0/73.2/75.0% | d=0.22, α=0.22, β=0.09 |
| Goedel-Prover-V2 2508.03613v1, Table 2 | 32B: k=32/1024/8192 gives 88.1/91.8/92.2% | d∈[0, 0.07], α 0.08–0.37 (d not identified) |
| Brown et al., abstract (SWE-bench Lite) | DeepSeek-Coder-V2: pass@1 15.9%, pass@250 56% | method of moments: d=0 gives α=0.12, β=0.65; d=0.3 gives α=0.27, β=0.91 |
| DeepSeek-Prover-V2, Table 4 (PutnamBench, 671B CoT) | 22/33/47 of 658 at k=32/128/1024 | d=0.8: α=0.08, β=3.6; d=0.9: α=0.26, β=9.0 |
| Brown et al. Sec. 2.2 (CodeContests, Gemma-2B) | pass@1 0.02%, pass@10k 7.1% | d=0.9: α=0.29, β=145 |

### Worked example: method of moments
Mean per-attempt success is pass@1 = α/(α+β) = m. Solve the pass@k equation for s = α+β.
- SWE-bench Lite, d = 0: m = 0.159 and 1 − B(0.159s, 0.841s + 250)/B(0.159s, 0.841s) = 0.56, which gives s = 0.767, so α = 0.122 and β = 0.645.

### Robust finding: α < 1 in every fit
All fits give α between 0.01 and 0.9, a U- or J-shaped distribution with a heavy tail of near-zero-p solvable problems. The repo's test value Beta(1, 3) has α = 1 and understates that tail.

### d and α are confounded
With only two or three points, d trades off against α. Use datasets with a visible plateau, such as the four-point DeepSeek-Prover-V2 series, to pin d.

### Cost dispersion
- Within-problem token dispersion per attempt: no published value found. attempt_cost_sd is UNVERIFIED.
- **Failed attempts cost more** (Su et al. Table 1). Correct vs incorrect mean tokens:

  | Model | Dataset | Correct | Incorrect | Ratio |
  |---|---|---|---|---|
  | R1-Distill | MATH | 2907 | 6521 | 2.2× |
  | R1-Preview | MATH | 2460 | 6106 | 2.5× |
  | R1-Distill | GSM8K | 667 | 842 | 1.26× |

  The sim currently draws cost independently of outcome. Add a failure-cost multiplier of 1.3–2.5.
- Zuo Table 4 is indirect evidence that cost correlates with difficulty: token matching erases about two-thirds of the gain.

### Mapping to the sim
`dead_fraction` is per obligation. The problem-level dead share is about Π_approaches [1 − (1−d)^L], ignoring shared lemmas. For example, A = 2, L = 3 and d = 0.3 give 0.43. To use the fits above directly, set approaches = chain = 1. Otherwise invert this formula.

- **Problem-level heterogeneity:** Beta(α, β) plus d.
- **Attempt-level heterogeneity:** iid Bernoulli(p), plus lognormal cost with attempt_cost_sd. Real attempts may be correlated (UNVERIFIED).

### Proposed regimes (approaches = chain = 1 for calibration)

| Regime | d | α | β | Cost | Basis |
|---|---|---|---|---|---|
| R1 saturated-easy | 0–0.05 | 0.4–0.9 | 0.1–0.5 | fail ×1.3–2.5 | Brown Table 2; Su Table 4 |
| R2 formal-plateau | 0.1–0.2 | 0.2–0.4 | 0.1–0.2 | UNVERIFIED | DeepSeek-Prover-V2 Table 1 fits |
| R3 agentic-SWE | 0.2–0.4 | 0.2–0.5 | 0.8–1.4 | UNVERIFIED | Brown abstract (2 points only) |
| R4 frontier-hard | 0.8–0.9 | 0.1–0.3 | 4–9 | UNVERIFIED | PutnamBench Table 4; Zuo Tables 6–7 (69–77% unsolvable) |

## 3. Adaptive vs uniform allocation across problems at fixed budget
- **Zuo 2506.12721:** +1.3 to +11.2 pts coverage, or 2–4× efficiency. The gain shrinks to +1–1.3 pts when token-matched on MATH (Table 4).
- **Zuo, Zhou, Zhu 2604.21018:** warm-up, then nearest-neighbour demonstrations for unresolved queries.
  - Gains over Unif of 1.8–16.1 pts (Table 5) and 0.3–10.3 pts (Table 6).
  - Elim vs DA on MATH500, GPT-4.1-mini: 92.4 vs 92.2 (Table 3). Elim vs Unif is not tabulated.
- **Snell et al. 2408.03314:** ">4×" efficiency over best-of-N (abstract). This is per-prompt strategy selection, not cross-problem reallocation.

**What this means for H1:** the published gains are measured against non-redistributing Uniform. Against work-conserving RoundRobin, which already equals Zuo-Elim, expect much smaller effects, likely a few points. The size is UNVERIFIED.

Sources: https://arxiv.org/html/2506.12721 · https://arxiv.org/html/2511.17006 · https://arxiv.org/html/2407.21787v3 · https://arxiv.org/html/2504.21801 · https://arxiv.org/html/2508.03613 · https://arxiv.org/html/2505.00127 · https://arxiv.org/abs/2408.03314 · https://arxiv.org/html/2604.21018
