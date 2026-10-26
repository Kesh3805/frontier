# Literature review

Access date for all sources: 2026-10-26. A status of **verified** means the
primary source was read. Anything else says what was not accessible. Page
content is summarised in our own words.

## 1. Hybrid Reasoning Agents (HybridAgent)

**Zou, J., Qi, Y., Chen, S., Bianchi, F., Zhu, S., Lu, P., He, J., Zou, J.**
"Hybrid Reasoning Agents." arXiv:2610.18861v1, 13 Oct 2026. CC BY 4.0.
Code: `togethercomputer/HybridAgent`, MIT, inspected at
`1b41cebbd2388d083ee1820af421b7f9e24affb5`. Checkpoints:
`togethercomputer/HybridAgent-8B-Agentic` rev `13a5c61b1880d7bcc2fac2e28d478809722beb8f`
(16.46 GB, MIT, base Qwen3-8B-Base) and `-14B-Agentic` rev
`1b726e326a4bfd38dc3c2251451f6fe0106d0d1c` (29.65 GB, base Qwen3-14B-Base).

### Method, as implemented

- **HybridLink** is a small residual adapter, `R(h) = h + W2·σ(W1·h)` with
  LayerNorms. It maps the last-layer hidden state back into input-embedding
  space. During a latent span its output becomes the next `inputs_embeds`
  slot, in place of sampling a token and looking up its embedding.
- **Working memory:** text tokens, latent steps and tool observations all go
  into **one KV cache** per trajectory. Tool results are appended without
  re-prefilling. Latent steps are *not* free: each is a full forward pass
  through the backbone, plus the adapter.
- **Mode switching:** a latent span opens when the model emits `<latent>`
  (allowed only inside `<think>`). In the released engine it closes when the
  LM-head argmax equals `</latent>` after `min_latent_steps`, or when it
  reaches `max_latent_steps`. The paper describes the exit as a
  nearest-embedding readout instead. Engine defaults (4/200 steps, tool cap
  5) differ from the paper's settings (16/256, cap 10).
- **Pseudo-text readout:** the nearest vocabulary embedding under cosine
  similarity. The paper only scores it for geometric alignment and with a
  Jaccard proxy. It is not shown to be faithful and is not a proof.
- **Training:** HybridSFT runs in three stages on 54K hybrid trajectories.
  HybridRL uses GRPO-style RL on 12K reasoning plus 1K agentic examples.
  Both datasets are released.
- **Backend:** a custom Hugging Face `transformers` loop. The paper mentions
  extending vLLM/verl, but that code is not released.

### Reported results (authors' claims, not reproduced)

Across 11 benchmarks, the authors report 35.5–54.7% fewer tokens, 1.8–2.6×
faster inference, 2.7–3.7× lower *modelled* cost, and +10.4% average
performance. These come from 32 H100s and five seeds. The cost model
(App. G.2) assumes $2.50 per H100-hour at 10% of peak BF16 throughput, and
charges one forward pass per text or latent step. It **excludes prompt
prefill, context-dependent attention and tool execution**.

### Implications for FRONTIER

- **Reuse:** the MIT license allows reusing the code with attribution. We
  plan to *call* the upstream engine from a pinned checkout through an
  adapter rather than vendor it (ADR-0006).
- **Reproduction is only partial even with a GPU.** The evaluation loop
  depends on a closed judge and summarizer (GPT-5.6-Luna) and on live
  Tavily search. Math benchmarks that use deterministic answer checking
  (`math-verify`) are the reproducible subset.
- **No matched text baseline is released.** See [`scope.md`](scope.md#h2).
- **Hardware:** a BF16 8B checkpoint needs about 16.4 GB for weights alone,
  before KV cache and activations. Our development host has no GPU.

## 2. OpenAI Navier–Stokes case study

**OpenAI** (8 Sept 2026). "On the Navier–Stokes Millennium Prize Problem."
https://openai.com/index/navier-stokes-solution/. Direct fetch returned 403,
so the page was read through a text proxy. Lean code:
`openai/NavierStokesAndEuler`, Apache-2.0, HEAD `f9e8bc5b38b6e212696e8a30e3e91517af887bbd`,
Lean `v4.34.0-rc2`.

- **What is claimed:** finite-time blowup for the **forced**
  incompressible Navier–Stokes equations, starting from rest, with a smooth
  force and finite energy, on ℝ³ (Clay statement C) and on the torus (D).
  The **unforced** existence-and-smoothness question (Clay A/B) is **not**
  addressed. A separate result on unforced **Euler** blowup came first.
- **Organisation reported:** about 10,000 concurrent agents; 2.7M messages
  and about 130B output tokens for N–S; 4.9M messages and about 300B tokens
  across all problems attempted. The result arrived about 88 h after the
  first agents were launched. Before that, about 100 agents spent about 50 h
  on Euler, and agents were then moved over with the Euler result as
  context. Groups were "cross-pollinated" through consolidation. The model
  was upgraded mid-run. Lean formalization and verification took about 17 h
  and was done by GPT-6 Astra. No compute cost was published.
- **Status:** Clay still lists the problem as **Active**. As of 13 Oct 2026,
  expert review was ongoing and incomplete (*Scientific American*). arXiv
  **2610.08144** (Bastounis, Circelli, Hansen) argues that a Lean build does
  not certify that the natural-language proof is faithful to it, and uses
  this case as an example. We could not access the *Science* news article
  (it sits behind a bot check). A Clay remark that the problem was
  "apparently settled" appears only secondhand and is **unverified**.

**For FRONTIER** the transferable ideas are organisational and are
**hypotheses**, not findings: formulations explored in parallel, resources
reallocated on intermediate results, shared consolidated evidence, and a
formal checker separate from the generator. The case gives no compute
ledger and no controlled comparison, so it says nothing about efficiency.
arXiv 2610.08144 also supports our separation between `mechanically_verified`
and `independently_reviewed`.

## 3. Budget-aware and adaptive test-time compute

| Work | Verified reference | What it already shows | How FRONTIER differs (to be tested, not assumed) |
|---|---|---|---|
| Snell et al. 2024 | arXiv 2408.03314 | Compute-optimal allocation by prompt difficulty beats best-of-N at equal compute. | Allocation over *dependency graphs* of sub-results with external verifiers. |
| Manvi et al. 2024 | arXiv 2410.02725 | The model predicts mid-generation whether more samples will help. | We use only receipt-based signals, never self-assessment. |
| Raman et al. (AdaBoN) | arXiv 2505.12050 | Explore-then-allocate best-of-N budget across prompts. | Similar allocation layer; adds DAG structure and full cost accounting. |
| **Zuo et al. 2025** | arXiv 2506.12721 | **Allocating compute across queries is a bandit problem:** elimination with confidence bounds maximises the fraction solved under a fixed budget. | **Closest prior art for the scheduler. Required baseline.** |
| Zhai et al. 2026 | arXiv 2604.14853 | Lagrangian "solve" oracle plus imitation policy for allocation under an average-compute constraint. | Their per-instance oracle has no counterpart in delayed DAG rewards; we may adopt their constrained formulation. |
| Bilal et al. 2026 (ICML) | PMLR 306:8277–8301 | PRM-guided adaptive trajectory generation and pruning within a problem. | We do not count PRM scores as verification. |
| Liu et al. 2026 (COLM), BATS / CATS | arXiv 2511.17006 | Budget tracking over joint token and tool cost; adaptive serial vs parallel exploration for search agents. | A cost-aware comparator for tool-heavy tasks. |
| Wunderlich et al. 2026 (ACL SRW) | doi:10.18653/v1/2026.acl-srw.1 | Pareto fronts of multi-agent schemes against compute; multi-agent can be compute-efficient. | **Novelty cannot rest on "cost-aware multi-agent reasoning".** |

## 4. Routing and cascades

FrugalGPT (arXiv 2305.05176) and RouteLLM (arXiv 2406.18665) route queries
to cheaper or stronger models by predicted difficulty. FRONTIER's "escalate
to a stronger model" is an instance of this. It is not a new contribution.

## 5. Verifier-backed search in formal mathematics

DeepSeek-Prover-V2 (arXiv 2504.21801), Kimina-Prover (2504.11354),
Goedel-Prover-V2 (2508.03613) and Seed-Prover (2507.23726) all rely on Lean
as an independent checker, and they spend most of their compute on large
numbers of parallel or iterative attempts. Their pass@k-versus-compute
curves are the natural real-world calibration for our synthetic
success-rate distributions. AlphaProof (Nature, 2025) is relevant, but we
did not verify its citation details in this review.

## 6. Agent systems for discovery

The AI Scientist (arXiv 2408.06292), AlphaEvolve (arXiv 2506.13131) and
Google's AI co-scientist (arXiv 2502.18864) show end-to-end automated
pipelines. AlphaEvolve is the most relevant: an evolutionary loop gated by
automated evaluators. None of them reports a controlled
verified-yield-per-compute comparison of allocation policies. That gap is
the one FRONTIER targets, and it is narrow.

## 7. Gaps and bounded contributions

What is **not** established in the literature we found:

1. Whether allocation that adapts to verifier receipts helps when results
   have **dependencies** (lemma → theorem), so that rewards are delayed and
   partial results unlock further work.
2. How allocation gains change once **all** costs are counted: verification,
   duplicated attempts, crashes, scheduler overhead.
3. How large hybrid-reasoning savings are **end to end** in a multi-attempt
   research loop (see the bound in [`scope.md`](scope.md)).

FRONTIER's candidate contributions are limited to (a) a reproducible
harness with receipts, (b) controlled evidence on questions 1–2, with
negative results reported, and later (c) matched measurements for question 3.
None of these is claimed yet.

## 8. Open questions and limits of this review

- This is not a systematic review. The search was targeted, and on 2026-10-26.
- We did not read the BATS/CATS and Zuo et al. papers in full beyond the
  abstract and method level. Each must be read closely before we implement
  it as a baseline.
- The details of the arXiv 2610.08144 critique (specific lemma mismatches)
  were not checked in the paper itself.
