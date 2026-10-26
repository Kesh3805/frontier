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
echo "qualification passed"
