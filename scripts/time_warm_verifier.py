#!/usr/bin/env python3
"""Informal dev timing: per-call wall time of `verify` cold vs prespawned.

Runs a handful of candidates through the V1 verifier in three modes, with
modes interleaved per repetition: cold (the default, one child started per
call), and warm with `PrespawnPool(size=1)` and `PrespawnPool(size=4)`. Each
mode is timed back to back (`--gap-ms 0`) and with an idle gap between calls
that stands in for the worker's own time between verifications.

This is a development measurement, not a finding: nothing here is
preregistered, and the numbers depend on the host. Standard library and
frontier_py only; no network, no model calls.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from frontier_py.tasks import TASKS  # noqa: E402
from frontier_py.verifiers.property_tests import PrespawnPool, verify  # noqa: E402

SPEC = "0" * 64
CANDIDATES = [
    ("sort_ints", "pass", "def sort_ints(xs):\n    return sorted(xs)"),
    ("sort_ints", "fail", "def sort_ints(xs):\n    return xs"),
    ("gcd", "pass", "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a"),
    ("gcd", "fail", "def gcd(a, b):\n    return a"),
    ("lis_length", "pass", "def lis_length(xs):\n    best = [1] * len(xs)\n    for i in range(len(xs)):\n"
     "        for j in range(i):\n            if xs[j] < xs[i]:\n                best[i] = max(best[i], best[j] + 1)\n"
     "    return max(best, default=0)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reps", type=int, default=20, help="repetitions per (mode, gap); each covers every candidate")
    ap.add_argument("--gaps-ms", type=float, nargs="+", default=[0.0, 150.0], help="idle time between calls")
    args = ap.parse_args()

    pools = {"warm-1": PrespawnPool(size=1), "warm-4": PrespawnPool(size=4)}
    modes = ["cold", *pools]
    times: dict[tuple[str, float], list[float]] = {(m, g): [] for m in modes for g in args.gaps_ms}
    verdicts: dict[str, set[tuple[str, ...]]] = {}
    try:
        for m in modes:  # warm-up: fill the pools, load the reference code
            for name, _, src in CANDIDATES:
                verify(TASKS[name], {"source": src}, spec_digest=SPEC, seed=1, charge_per_case=0.005, prespawn=pools.get(m))
        for _ in range(args.reps):
            for gap in args.gaps_ms:
                for m in modes:
                    for name, _, src in CANDIDATES:
                        time.sleep(gap / 1000)
                        t0 = time.perf_counter()
                        r = verify(TASKS[name], {"source": src}, spec_digest=SPEC, seed=1, charge_per_case=0.005, prespawn=pools.get(m))
                        times[(m, gap)].append(time.perf_counter() - t0)
                        verdicts.setdefault(src, set()).add((r.verdict, str(r.cost_units)))
    finally:
        for p in pools.values():
            p.close()

    mismatched = [src for src, v in verdicts.items() if len(v) != 1]
    print(f"python {sys.version.split()[0]} on {sys.platform}; {args.reps} reps x {len(CANDIDATES)} candidates per cell")
    print(f"{'mode':<8} {'gap ms':>7} {'median ms':>10} {'mean ms':>9} {'p90 ms':>8} {'vs cold':>8}")
    for gap in args.gaps_ms:
        cold = statistics.median(times[("cold", gap)])
        for m in modes:
            xs = sorted(times[(m, gap)])
            med = statistics.median(xs)
            print(f"{m:<8} {gap:>7.0f} {med * 1e3:>10.1f} {statistics.fmean(xs) * 1e3:>9.1f} "
                  f"{xs[int(0.9 * (len(xs) - 1))] * 1e3:>8.1f} {med / cold:>8.2f}")
    print("verdicts and charges identical across modes:", "yes" if not mismatched else f"NO ({len(mismatched)} differ)")
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
