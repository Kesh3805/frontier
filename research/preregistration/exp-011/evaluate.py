"""Score exp-011 (cost-blind Thompson under the measured verification charge).

    python research/preregistration/exp-011/evaluate.py runs/exp-011

Pairing is by seed within a budget. Frozen with protocol.md before any
exp-011 output.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR = "round_robin"
TH, THF = "thompson(k=2,hints=true)", "thompson_flat(k=2,hints=true)"
TN, TNF = "thompson(k=2,hints=false)", "thompson_flat(k=2,hints=false)"
POLICIES = (RR, TH, THF, TN, TNF)
BUDGETS = {"M": (330, 1320, 2640), "P": (60, 240, 480)}
METRICS = ("sim_true_solved", "sim_dead_attempts", "reused_rejections", "rejected")


def rows(path):
    return {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


def diff(rs, a, b, metric="sim_true_solved"):
    recs = [Record(s, p, float(r[metric])) for (s, p), r in rs.items() if p in (a, b)]
    c = paired_bootstrap(recs, a, b)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def mean(rs, policy, metric):
    v = [r[metric] for (s, p), r in rs.items() if p == policy]
    return round(sum(v) / len(v), 4)


def main(root):
    root = Path(root)
    res = {}
    false_runs = 0
    for part, budgets in BUDGETS.items():
        for b in budgets:
            rs = rows(root / f"{part}-b{b}" / "results.jsonl")
            false_runs += sum(r["sim_false_solved"] > 0 for r in rs.values())
            res[f"{part}-b{b}"] = {
                "means": {p: {m: mean(rs, p, m) for m in METRICS} for p in POLICIES},
                "vs_rr": {p: diff(rs, p, RR) for p in POLICIES if p != RR},
                "flat_minus_observed": {"hints": diff(rs, THF, TH), "no_hints": diff(rs, TNF, TN)},
                "flat_minus_observed_dead_attempts": {"hints": diff(rs, THF, TH, "sim_dead_attempts"),
                                                      "no_hints": diff(rs, TNF, TN, "sim_dead_attempts")},
            }
    res["false_solve_runs"] = false_runs
    m, p = res["M-b1320"], res["P-b240"]
    v = {
        "R1 TH - RR at M-b1320: CI < 0": m["vs_rr"][TH]["ci"][1] < 0,
        "R2 THflat - TH at M-b1320: CI > 0": m["flat_minus_observed"]["hints"]["ci"][0] > 0,
        "R3 dead attempts THflat - TH at M-b1320: CI < 0": m["flat_minus_observed_dead_attempts"]["hints"]["ci"][1] < 0,
        "R4 THflat - RR at M-b1320 >= -0.3 (point)": m["vs_rr"][THF]["diff"] >= -0.3,
        "R5 THflat - RR at M-b330: CI > 0": res["M-b330"]["vs_rr"][THF]["ci"][0] > 0,
        "R6 THflat - TH larger at M-b1320 than at P-b240 (point)": m["flat_minus_observed"]["hints"]["diff"]
        > p["flat_minus_observed"]["hints"]["diff"],
        "R7 no run with a false solve": false_runs == 0,
    }
    r1, r2, r3 = (v[k] for k in list(v)[:3])
    if not r1:
        v["Decision"] = "the moderate-budget loss did not replicate"
    elif r2 and r3:
        v["Decision"] = "the observed-cost index's bias towards cheaply failing tasks explains the loss"
    elif m["flat_minus_observed"]["hints"]["ci"][1] <= 0:
        v["Decision"] = "the loss replicated but has another cause"
    else:
        v["Decision"] = "the loss replicated; the cost-bias explanation is unclear"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
