# frontier-py

Python layer of FRONTIER: independent verifiers, worker adapters and
analysis. Python >= 3.11; runtime deps `numpy`, `jsonschema`.

```sh
pip install -e python[test]       # or run from python/ without installing
python -m pytest python -q        # from the repo root
```

## Verifier CLI (request schema 0.2)

```sh
cd python
echo '{"schema_version":"0.2","task":"gcd","spec_digest":"<64 hex>",
       "candidate":{"source":"import math\ngcd = math.gcd"},"seed":1}' \
  | python -m frontier_py.verify_cli
```

- Input: one JSON object on stdin (UTF-8). Required: `schema_version`
  (`"0.2"`), `task` (`sort_ints` | `gcd` | `lis_length`), `spec_digest`,
  `candidate.source`, `seed` (non-negative int). Optional: `task_id`,
  `artifact_digest` (otherwise computed as the canonical digest of the
  frontier-core `Artifact` with kind `code`). Unknown top-level fields are
  rejected. Fields of `candidate` other than `source` are ignored.
- Output: one `VerifierReceipt` JSON line (same shape as the Rust struct).
- Exit status: 0 for any verdict, 2 for a malformed request.

Trust class is always **V1**. The harness runs the candidate with
`python -I -S` in a temporary directory with a scrubbed environment and
compares outputs in the parent. It applies rlimits on POSIX and timeouts
only on Windows. **It does not isolate the network or the filesystem.** See
the docstring of `frontier_py/verifiers/property_tests.py` for the full
threat model. V2 needs the isolated verifier image, which does not exist yet.

## Analysis

```sh
python -m frontier_py.analysis results.jsonl --baseline round_robin --metric solved
```

Paired cluster bootstrap (clusters = `(regime, seed)`, 10000 replicates,
seed 26102026) plus an exact sign test. It prints one Markdown table per
regime, comparing each policy with the baseline.

## Workers

`workers/base.py` defines the adapter protocol and `BudgetGuard`.
`hybrid_agent.py` pins the HybridAgent commit and checkpoint, and needs the
exit rule and the step and tool caps to be set explicitly. `hosted.py` reads
its key from a configured environment variable and will not run without a
`max_usd` budget. Neither adapter downloads anything or makes provider calls
on its own.
