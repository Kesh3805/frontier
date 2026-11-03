"""Score exp-010 (allocation under the measured verification charge).

    python research/preregistration/exp-010/evaluate.py runs/exp-010

Pairing is by (policy, seed) within a budget. Frozen with protocol.md before
any exp-010 output.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR, TH = "round_robin", "thompson(k=2,hints=true)"
S_BUDGETS, D_BUDGETS = (330, 1320, 2640), (660, 2640)


def rows(path):
    return {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


def summary(c):
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)], "a": round(c.mean_a, 4), "b": round(c.mean_b, 4)}


def paired(a_rows, b_rows, policy, metric="sim_true_solved"):
    recs = []
    for (seed, pol), r in a_rows.items():
        if pol == policy:
            recs += [Record(seed, "a", float(r[metric])), Record(seed, "b", float(b_rows[(seed, pol)][metric]))]
    return summary(paired_bootstrap(recs, "a", "b"))


def vs_rr(rs, policy, metric="sim_true_solved"):
    recs = [Record(s, p, float(r[metric])) for (s, p), r in rs.items() if p in (policy, RR)]
    return summary(paired_bootstrap(recs, policy, RR))


def share(rs, policy):
    v = [r["verification_units"] / r["committed_units"] for (s, p), r in rs.items() if p == policy and r["committed_units"] > 0]
    return round(sum(v) / len(v), 4)


def false_runs(rs):
    return sum(r["sim_false_solved"] > 0 for r in rs.values())


def main(root):
    root = Path(root)
    res = {"S": {}, "D": {}}
    false = {"S-v1": 0, "S-v2": 0, "S-v2ff": 0, "D-v2": 0}
    for b in S_BUDGETS:
        arms = {a: rows(root / f"{a}-b{b}" / "results.jsonl") for a in ("S-v1", "S-v2", "S-v2ff")}
        for a, rs in arms.items():
            false[a] += false_runs(rs)
        pols = sorted({p for _, p in arms["S-v2"]})
        res["S"][f"b{b}"] = {
            "v2_minus_v1": {p: paired(arms["S-v2"], arms["S-v1"], p) for p in pols},
            "v2ff_minus_v2": {p: paired(arms["S-v2ff"], arms["S-v2"], p) for p in pols},
            "vs_rr": {a: {p: vs_rr(rs, p) for p in pols if p != RR} for a, rs in arms.items()},
            "dead_attempts_vs_rr_v2": {p: vs_rr(arms["S-v2"], p, "sim_dead_attempts") for p in pols if p != RR},
            "verification_share_rr": {a: share(rs, RR) for a, rs in arms.items()},
            "mean_true_solved": {a: {p: round(sum(r["sim_true_solved"] for (s, q), r in rs.items() if q == p) / 100, 4) for p in pols}
                                 for a, rs in arms.items()},
        }
    for b in D_BUDGETS:
        rs = rows(root / f"D-v2-b{b}" / "results.jsonl")
        false["D-v2"] += false_runs(rs)
        pols = sorted({p for _, p in rs})
        res["D"][f"b{b}"] = {"vs_rr": {p: vs_rr(rs, p) for p in pols if p != RR}, "verification_share_rr": share(rs, RR),
                             "mean_true_solved": {p: round(sum(r["sim_true_solved"] for (s, q), r in rs.items() if q == p) / 100, 4)
                                                  for p in pols}}
    res["false_solve_runs"] = false
    S, D = res["S"], res["D"]
    s330 = S["b330"]
    v = {
        "G1 RR v2 - v1 at S-b330 > -1.0 (point)": s330["v2_minus_v1"][RR]["diff"] > -1.0,
        "G2 |RR v2ff - v2| at S-b330 < 0.75 (point)": abs(s330["v2ff_minus_v2"][RR]["diff"]) < 0.75,
        "G3 TH - RR at S-b330 (v2): CI > 0 and point > 1.86": s330["vs_rr"]["S-v2"][TH]["ci"][0] > 0
        and s330["vs_rr"]["S-v2"][TH]["diff"] > 1.86,
        "G4 TH - RR at D-b660: CI > 0": D["b660"]["vs_rr"][TH]["ci"][0] > 0,
        "G5 no false solve with suite v2; at least one with suite v1": false["S-v2"] == false["S-v2ff"] == false["D-v2"] == 0
        and false["S-v1"] >= 1,
        "G6 RR verification share at S-b330 (v2) >= 0.80": s330["verification_share_rr"]["S-v2"] >= 0.80,
    }
    d1 = s330["v2_minus_v1"][RR]
    if v["G1 RR v2 - v1 at S-b330 > -1.0 (point)"]:
        v["Decision (suite cost)"] = "the stronger suite no longer costs yield under measured cost"
    elif d1["ci"][1] < -1.0:
        v["Decision (suite cost)"] = "the stronger suite still costs yield under measured cost"
    else:
        v["Decision (suite cost)"] = "unclear"
    th_s, th_d = s330["vs_rr"]["S-v2"][TH], D["b660"]["vs_rr"][TH]
    if th_s["ci"][0] > 0 and th_d["ci"][0] > 0:
        v["Decision (allocation)"] = "adaptive allocation's scarce-budget gain is robust to measured cost"
    elif th_s["ci"][1] < 0 or th_d["ci"][1] < 0:
        v["Decision (allocation)"] = "adaptive allocation's scarce-budget gain is not robust to measured cost"
    else:
        v["Decision (allocation)"] = "mixed"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
