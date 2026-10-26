"""Score exp-003 predictions with the frozen frontier_py.analysis functions.

    python research/preregistration/exp-003/evaluate.py runs/exp-003

Frozen together with protocol.md, before any exp-003 output existed.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR = "round_robin"
TH = "thompson(k=2,hints=true)"
TN = "thompson(k=2,hints=false)"
POLS = [RR, "fifo", "random", "greedy_prior", TH, TN, "oracle_index"]
METRICS = ("solved", "sim_true_solved", "sim_dead_attempts", "sim_false_solved", "committed_units", "attempts")


def load(path):
    out = {m: [] for m in METRICS}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        for m in METRICS:
            out[m].append(Record(r["seed"], r["policy"], float(r[m])))
    return out


def cmp(recs, a, b=RR):
    c = paired_bootstrap(recs, a, b)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)], "a_gt_b": c.a_gt_b, "a_lt_b": c.a_lt_b}


def mean(recs, arm):
    v = [r.value for r in recs if r.arm == arm]
    return round(sum(v) / len(v), 4)


def main(root):
    root = Path(root)
    res = {}
    for b in (60, 240, 480):
        d = load(root / f"b{b}" / "results.jsonl")
        res[f"b{b}"] = {
            "means": {m: {p: mean(d[m], p) for p in POLS} for m in METRICS},
            "vs_rr": {m: {p: cmp(d[m], p) for p in POLS if p != RR} for m in ("sim_true_solved", "solved", "sim_dead_attempts")},
            "runs_with_false_solve": {p: sum(1 for r in d["sim_false_solved"] if r.arm == p and r.value > 0) for p in POLS},
        }
    v = {}
    t = lambda b, p=TH, m="sim_true_solved": res[f"b{b}"]["vs_rr"][m][p]  # noqa: E731
    v["P1 dead over-spend at all budgets"] = all(t(b, TH, "sim_dead_attempts")["ci"][0] > 0 for b in (60, 240, 480))
    v["P2a scarce gain (b60)"] = t(60)["ci"][0] > 0
    v["P2b no gain at b480"] = t(480)["diff"] <= 0
    v["P3 hint-free ~ RR at b240 and b480"] = all(t(b, TN)["ci"][0] <= 0 <= t(b, TN)["ci"][1] for b in (240, 480))
    v["P4 hint-free spends fewer dead attempts than hinted (b240, b480)"] = all(
        res[f"b{b}"]["means"]["sim_dead_attempts"][TN] < res[f"b{b}"]["means"]["sim_dead_attempts"][TH] for b in (240, 480))
    if t(60)["ci"][0] > 0 and t(240)["ci"][0] > 0:
        v["H1-pilot"] = "supported"
    elif any(t(b)["ci"][1] < 0 for b in (60, 240, 480)):
        v["H1-pilot"] = "contradicted"
    else:
        v["H1-pilot"] = "inconclusive"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
