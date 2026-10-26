#!/usr/bin/env bash
# CPU-only engineering qualification: run a small simulated campaign, audit
# the log, replay it bit-for-bit, and confirm a forged verdict is rejected.
# Passing this is an engineering check, not scientific evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
BIN="${FRONTIER_BIN:-target/release/frontier}"
[ -x "$BIN" ] || BIN="$BIN.exe"
OUT=runs/qualify
rm -rf "$OUT"
"$BIN" run --config configs/smoke.json --out "$OUT"
"$BIN" audit --events "$OUT/events.jsonl" --summary "$OUT/summary.json"
"$BIN" replay --config configs/smoke.json --events "$OUT/events.jsonl"
python - "$OUT/events.jsonl" "$OUT/forged.jsonl" <<'PY'
import json, sys
lines = open(sys.argv[1]).read().splitlines()
for i, line in enumerate(lines):
    rec = json.loads(line)
    ev = rec["event"]
    if ev["type"] == "verification_finished" and ev["receipt"]["verdict"] == "FAIL":
        ev["receipt"]["verdict"] = "PASS"
        lines[i] = json.dumps(rec, separators=(",", ":"))
        break
else:
    sys.exit("no FAIL verdict to forge")
open(sys.argv[2], "w").write("\n".join(lines) + "\n")
PY
if "$BIN" audit --events "$OUT/forged.jsonl" 2>/dev/null; then
  echo "FAIL: forged verdict was accepted" >&2
  exit 1
fi
rm "$OUT/forged.jsonl"

# Real verifier-backed tasks: one campaign through the Python worker/verifier
# service, run twice to check determinism, then audited.
"$BIN" real-run --config research/realtasks/dev.json --seed 1 --policy-index 1 --out "$OUT/real-a"
"$BIN" real-run --config research/realtasks/dev.json --seed 1 --policy-index 1 --out "$OUT/real-b"
"$BIN" audit --events "$OUT/real-a/events.jsonl" --summary "$OUT/real-a/summary.json"
cmp "$OUT/real-a/events.jsonl" "$OUT/real-b/events.jsonl"

# Dependency-structured real tasks (catalog v3): lemmas are verified first and
# passed as libraries to dependent tasks. Same determinism and audit check.
"$BIN" real-run --config research/realtasks/dev-v3.json --seed 1 --policy-index 1 --out "$OUT/real3-a"
"$BIN" real-run --config research/realtasks/dev-v3.json --seed 1 --policy-index 1 --out "$OUT/real3-b"
"$BIN" audit --events "$OUT/real3-a/events.jsonl" --summary "$OUT/real3-a/summary.json"
cmp "$OUT/real3-a/events.jsonl" "$OUT/real3-b/events.jsonl"
grep -q '"parents":\[' "$OUT/real3-a/events.jsonl" || { echo "FAIL: v3 run never attempted a dependent task" >&2; exit 1; }
echo "qualification passed"
