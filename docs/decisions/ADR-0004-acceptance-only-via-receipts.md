# ADR-0004: Acceptance only through verifier receipts; trust class and claim status are separate

Status: accepted (2026-10-26)

## Decision
A claim becomes `mechanically_verified` only when a receipt meets all of
these conditions:

- it comes from the verifier named in the sealed spec;
- it is bound to the spec digest and to an artifact already in the store;
- its verdict is `PASS`;
- its trust class is at or above the spec's requirement.

Self-reported confidence is stored for calibration studies and never read
by acceptance logic. Conflicting receipts make a claim `contested`. Each
task accepts at most one artifact. Claim statuses above
`mechanically_verified` require recorded human or external acts.

## Why
The dossier's v0.1 schema let V0 receipts pass. Model agreement and model
confidence are not independent evidence. arXiv 2610.08144 shows that even a
passing formal check can fail to cover the claim made in prose.

## Rejected
Majority vote across agents as verification; LLM-as-judge as a verifier for
primary endpoints.
