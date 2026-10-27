"""Frozen scoring for exp-009 (measured cost of fail-fast verification).

    python research/preregistration/exp-009/evaluate.py RUNS_DIR

RUNS_DIR holds M/ (measure.py output) and C-E1, C-F1, C-F2, C-E2 (frontier
real-experiment output). Prints one JSON object with every quantity the
protocol names, the prediction verdicts and the decision.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BOOT_REPS = 10_000
BOOT_SEED = 26102026
CASES = 199  # suite v2: 3 visible + 196 hidden
PER_CASE = 0.005
OUTCOME = ("solved", "sim_true_solved", "sim_false_solved", "sim_dead_attempts", "committed_units", "generation_units",
           "verification_units", "attempts", "accepted", "rejected", "reused_rejections")


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def per_candidate(rows: list[dict]) -> dict[int, dict]:
    by: dict[int, dict] = defaultdict(lambda: {"F": [], "E": []})
    for r in rows:
        by[r["id"]][r["mode"]].append(r)
    out = {}
    for i, m in by.items():
        f, e = m["F"], m["E"]
        out[i] = {
            "task": f[0]["task"],
            "verdict_f": f[0]["verdict"], "verdict_e": e[0]["verdict"],
            "agree": len({x["verdict"] for x in f + e}) == 1,
            "c_full": CASES * PER_CASE,  # full charge: every verdict pays for every case
            "c_ff": e[0]["charge"], "c_ff_f": f[0]["charge"],
            "t_f": statistics.median(x["wall_s"] for x in f), "t_e": statistics.median(x["wall_s"] for x in e),
            "cpu_f": statistics.median((x["child_cpu_s"] or 0.0) + x["parent_cpu_s"] for x in f),
            "cpu_e": statistics.median((x["child_cpu_s"] or 0.0) + x["parent_cpu_s"] for x in e),
        }
    return out


def saving(cs: list[dict], a: str, b: str) -> float:
    return 1.0 - sum(c[b] for c in cs) / sum(c[a] for c in cs)


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def fixed_share(cs: list[dict]) -> float:
    a, b = ols([c["c_ff"] / PER_CASE for c in cs], [c["t_e"] for c in cs])
    return a / (a + CASES * b)


def boot(cs: list[dict], stat) -> list[float]:
    """Percentile 95% CI, resampling tasks (clusters) with replacement."""
    by: dict[str, list[dict]] = defaultdict(list)
    for c in cs:
        by[c["task"]].append(c)
    keys = sorted(by)
    rng = random.Random(BOOT_SEED)
    vals = []
    for _ in range(BOOT_REPS):
        sample = [c for k in (rng.choice(keys) for _ in keys) for c in by[k]]
        try:
            vals.append(stat(sample))
        except ZeroDivisionError:
            continue
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)]


def campaign(runs: Path) -> dict:
    res = {n: {(r["policy"], r["seed"]): r for r in load_jsonl(runs / n / "results.jsonl")} for n in ("C-E1", "C-F1", "C-F2", "C-E2")}
    man = {n: json.loads((runs / n / "manifest.json").read_text(encoding="utf-8")) for n in res}
    ref = res["C-F1"]
    identical = {n: sum(all(r[k] == ref[key][k] for k in OUTCOME) for key, r in d.items()) for n, d in res.items()}
    wall = {n: m["verify_wall_seconds"] for n, m in man.items()}
    cpu = {n: m.get("verify_child_cpu_seconds") for n, m in man.items()}
    e, f = wall["C-E1"] + wall["C-E2"], wall["C-F1"] + wall["C-F2"]
    return {"runs": {n: len(d) for n, d in res.items()}, "identical_to_F1": identical, "verify_wall_s": wall, "verify_child_cpu_s": cpu,
            "measured_saving": round(1 - e / f, 4),
            "source": {n: (m["source_commit"], m["source_dirty"]) for n, m in man.items()}}


def main(runs: Path) -> None:
    rows = load_jsonl(runs / "M" / "measurements.jsonl")
    cands = per_candidate(rows)
    allc = list(cands.values())
    fail = [c for c in allc if c["verdict_f"] == "FAIL"]
    passed = [c for c in allc if c["verdict_f"] == "PASS"]
    m = {
        "candidates": len(allc), "fail": len(fail), "pass": len(passed),
        "inconclusive": sum(c["verdict_f"] == "INCONCLUSIVE" for c in allc),
        "verdict_disagreements": sum(not c["agree"] for c in allc),
        "charge_mismatches": sum(c["c_ff"] != c["c_ff_f"] for c in allc),
        "mean_wall_f_s": round(statistics.fmean(c["t_f"] for c in allc), 5),
        "mean_wall_e_s": round(statistics.fmean(c["t_e"] for c in allc), 5),
        "S_meas_fail": round(saving(fail, "t_f", "t_e"), 4), "S_meas_fail_ci": boot(fail, lambda s: saving(s, "t_f", "t_e")),
        "S_mod_fail": round(saving(fail, "c_full", "c_ff"), 4),
        "S_meas_all": round(saving(allc, "t_f", "t_e"), 4), "S_meas_all_ci": boot(allc, lambda s: saving(s, "t_f", "t_e")),
        "S_mod_all": round(saving(allc, "c_full", "c_ff"), 4),
        "S_cpu_fail": round(saving(fail, "cpu_f", "cpu_e"), 4),
        "fixed_share": round(fixed_share(allc), 4), "fixed_share_ci": boot(allc, fixed_share),
        "fit_seconds": dict(zip(("a", "b_per_case"), (round(v, 7) for v in ols([c["c_ff"] / PER_CASE for c in allc], [c["t_e"] for c in allc])))),
        "pass_ratio_median": round(statistics.median(c["t_e"] / c["t_f"] for c in passed), 4) if passed else None,
    }
    att = load_jsonl(runs / "M" / "attempts.jsonl")
    gen = sum(a["gen_wall_s"] for a in att) / len(att)
    m["descriptive"] = {"mean_attempt_wall_s": round(gen, 5),
                        "verification_share_measured_F": round(m["mean_wall_f_s"] / (m["mean_wall_f_s"] + gen), 4),
                        "verification_share_measured_E": round(m["mean_wall_e_s"] / (m["mean_wall_e_s"] + gen), 4)}
    c = campaign(runs)
    ident = all(v == c["runs"][n] for n, v in c["identical_to_F1"].items())
    v = {
        "M1 measured saving on FAIL candidates: CI upper bound < 0.25": m["S_meas_fail_ci"][1] < 0.25,
        "M2 modelled minus measured saving on FAIL candidates >= 0.40": m["S_mod_fail"] - m["S_meas_fail"] >= 0.40,
        "M3 fixed-overhead share of a full verification >= 0.75": m["fixed_share"] >= 0.75,
        "M4 early stop costs PASS candidates within 10% (median ratio in [0.9, 1.1])": m["pass_ratio_median"] is not None
        and 0.9 <= m["pass_ratio_median"] <= 1.1,
        "M5 same verdicts and charges for every candidate, and identical campaign outcomes": m["verdict_disagreements"] == 0
        and m["charge_mismatches"] == 0 and ident,
        "M6 campaign measured saving < 0.25": c["measured_saving"] < 0.25,
    }
    if v["M1 measured saving on FAIL candidates: CI upper bound < 0.25"] and v["M2 modelled minus measured saving on FAIL candidates >= 0.40"]:
        decision = "modelled fail-fast saving does not hold physically on this harness"
    elif m["S_meas_fail_ci"][0] >= 0.5 * m["S_mod_fail"]:
        decision = "modelled fail-fast saving holds physically"
    else:
        decision = "partial"
    print(json.dumps({"M": m, "C": c, "verdicts": {**v, "Decision": decision}}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
