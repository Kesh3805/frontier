# Source audit

Audit date: 2026-10-26. This records what FRONTIER started from, how much
each source is trusted, and where the starting material is wrong or
inconsistent.

## Source-of-truth hierarchy

When sources disagree, the higher level wins:

1. Independently checked primary sources: published papers, specifications
   and upstream code inspected at a pinned revision.
2. Frozen protocols and validated experiment artifacts in this repository
   (`research/preregistration/`, `results/`), tied to commit SHAs.
3. Canonical project documentation (`docs/`).
4. The original dossier and anything else that is proposed but unverified.

## Inventory of supplied materials

| Material | SHA-256 | Disposition |
|---|---|---|
| `FRONTIER-Complete-Research-Documentation.md` (dossier v0.1, 870 lines) | `5a63d4fe7c19b6d5f0209394d9e727711f7e29fa1c37348dfdcf506191fb594d` | Archived verbatim as [`docs/archive/dossier-v0.1.md`](../archive/dossier-v0.1.md). Treated as level 4. |
| `FRONTIER-Research-Dossier.pdf` (42 pages) | `967b3755a16884ecf31080980189bcb5896d19ea83073e2d89861a5559a09c7f` | Not committed. Its text extraction has the same 14 chapters as the Markdown, so it adds nothing but layout. |
| `frontier-research/docs/01..14-*.md` | not individually recorded | The same chapters as the combined Markdown, split into files. Not committed; the archive copy supersedes them. |
| `frontier-research/schemas/*.json` (v0.1) | `7043…886f`, `37a8…2f0c`, `10a9…98c8` | Replaced by v0.2 schemas in `schemas/`, generated from the Rust types (see "Defects" below). |
| `frontier-research/config/experiment-proposed.yaml` | `5fa7…6bcc` | Kept as a planning input. Most of its fields are `TO_BE_PINNED`. |
| `frontier-research/templates/*` | — | The preregistration checklist was adopted into `research/preregistration/README.md`. The benchmark workflow template is **not** enabled. |
| `frontier-research/.github/workflows/documentation-check.yml` | `52fb…c3ff` | Superseded by `.github/workflows/ci.yml`. |

The supplied materials did not include a code starter package, benchmark
tasks, a bibliography file beyond chapter 13, or any experimental results.

## Corrections to the dossier

These come from the literature check in
[`literature-review.md`](literature-review.md). Each one corrects a specific
dossier statement.

| # | Dossier statement | Correction |
|---|---|---|
| C1 | §02-A: a "proposed resolution" of Navier–Stokes, with no theorem stated. | OpenAI claims **finite-time blowup for the forced equations**: smooth external force, fluid starting at rest, finite energy. This is Clay statements **C (ℝ³) and D (𝕋³)**. The **unforced** existence-and-smoothness problem (Clay A/B, f ≡ 0) is not addressed. OpenAI's own word is "resolves"; "proposed" is the dossier's hedge. |
| C2 | "~88 hours to the result; 17 additional hours for Lean formalization." | The 88 h runs from the first agent launch (1 Sept), before agents were reassigned to N–S. The 17 h covers formalization **and** verification, and it was done by a different, publicly named model (GPT-6 Astra). The production model was also upgraded mid-run. |
| C3 | "Formal verification" is treated as closing the question. | A Lean repository is public (`openai/NavierStokesAndEuler`, Apache-2.0). arXiv 2610.08144 argues that a passing Lean build does not certify that the natural-language proof says the same thing. As of 13 Oct 2026, no independent review had been completed, and Clay still lists the problem as Active. |
| C4 | HybridAgent: "Qwen3-derived 8B and ~14B variants." | Three scales were trained (4B/8B/14B on Qwen3-**Base**); only 8B and 14B are released. Training and inference used 32 H100s. The evaluation depends on a closed LLM judge/summarizer (GPT-5.6-Luna) and live Tavily search, so it cannot be reproduced exactly. |
| C5 | Implicitly, that matched text-only checkpoints can be assembled. | The paper trains matched text baselines but **does not release them**. Loading the HybridAgent checkpoint without HybridLink gives a hybrid-trained model with its latent mode switched off, which is not a matched text arm. **H2 cannot be tested causally without training our own baseline** (see [`scope.md`](scope.md#h2)). |
| C6 | Latent exit is described as a nearest-token readout. | Paper and code disagree. The released engine exits when the **LM-head argmax equals `</latent>`** (after a minimum step count) or when a step cap is reached. Nearest-embedding readout is used only for the optional pseudo-text. Engine defaults also differ from the paper (min/max latent steps 4/200 vs 16/256; tool caps 5 vs 10). |
| C7 | "Released code provides batch inference" (implying a comparable serving stack). | The repo is a custom HF `transformers` decode loop. The paper's vLLM/verl extensions are not released. Throughput we measure will not be comparable to the paper's. |
| C8 | Liu et al. 2026 called "CATS". | The arXiv version (2511.17006) calls the method **BATS** plus a "Budget Tracker". Cite both names. |
| C9 | The prior-art list omits across-query bandit allocation. | Zuo et al., arXiv 2506.12721, already treats per-query compute allocation as a bandit problem under a fixed budget. This is the closest prior work to the FRONTIER scheduler and is now a required baseline. |
| C10 | GitHub runner sizes given in "GiB". | GitHub documents GB. The figures themselves are correct: public 4 CPU/16 GB, private 2 CPU/8 GB, T4 runner 16 GB VRAM. |

## Internal inconsistencies and defects in the dossier

| # | Issue | Resolution |
|---|---|---|
| D1 | The v0.1 receipt schema lets a `PASS` receipt carry trust class `V0`, while §06 says V0 "never counts as solved". | The kernel enforces `verdict == PASS && trust_class >= spec.required_trust` (`crates/frontier-core/src/evidence.rs`). |
| D2 | The ledger-event schema has no hash chain, so it cannot show tampering. Its event types also miss lifecycle exits (`crashed`, `timed_out`, `quarantined`) that §04 defines. | The v0.2 event log is hash-chained and covers the full attempt lifecycle. |
| D3 | "Verified" is used both for maturity ("meets independent checker *and human-review* requirements") and for trust class V2 (machine re-run). | Two separate vocabularies: `TrustClass` (V0–V4) for the checking behind a result, and `ClaimStatus` for the epistemic state. A machine check reaches `mechanically_verified` at most. |
| D4 | H2 requires "no material loss in solved-task rate", but "material" is never defined. | Any future H2 preregistration must state a non-inferiority margin. |
| D5 | H1 compares against "fixed uniform allocation", which is a weak baseline when it does not redistribute budget left over by solved problems. | Both a strict fixed-slice baseline and a work-conserving round-robin baseline are implemented. Claims are made against the stronger one. |
| D6 | The primary budget is in dollars, but Stage 1 has no billed resources. | Budgets are in compute units (CU) plus the underlying physical quantities. A rate card converts to USD once paid resources exist. |
| D7 | Stage P plans 10 Lean tasks, but no Lean toolchain is pinned or available on the development host. | Formal tasks are deferred until a pinned Lean + Mathlib verifier image exists. |
| D8 | The dossier never bounds how much a cheaper generator can save end to end. | An Amdahl-style bound is added in [`scope.md`](scope.md#cheaper-tokens-vs-cheaper-research). |
