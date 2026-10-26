"""Score exp-007 predictions with the frozen frontier_py.analysis functions.

    python research/preregistration/exp-007/evaluate.py runs/exp-007

Frozen together with protocol.md, before any exp-007 output existed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR, TH, TN, GP = "round_robin", "thompson(k=2,hints=true)", "thompson(k=2,hints=false)", "greedy_prior"
POLS = [RR, "random", GP, TH, TN, "oracle_index"]
BUDGETS = (120, 480, 1920)


def load(path, metric):
    return [Record(r["seed"], r["policy"], float(r[metric])) for r in map(json.loads, open(path, encoding="utf-8"))]


def cmp(recs, a, b=RR):
    c = paired_bootstrap(recs, a, b)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)], "mean_a": round(c.mean_a, 4), "mean_b": round(c.mean_b, 4)}


def main(root):
    res, v = {}, {}
    for b in BUDGETS:
        p = Path(root) / f"b{b}" / "results.jsonl"
        res[f"b{b}"] = {m: {pol: cmp(load(p, m), pol) for pol in POLS if pol != RR}
                        for m in ("sim_true_solved", "solved", "sim_dead_attempts", "committed_units")}
    t = lambda b, pol: res[f"b{b}"]["sim_true_solved"][pol]  # noqa: E731
    v["D1 hinted Thompson beats RR at b120 (CI > 0)"] = t(120, TH)["ci"][0] > 0
    v["D2 hint-free Thompson beats RR at b120 (CI > 0)"] = t(120, TN)["ci"][0] > 0
    v["D3 |TH - RR| < 1 at b1920"] = abs(t(1920, TH)["diff"]) < 1
    v["D4 greedy_prior beats RR at b120 (CI > 0)"] = t(120, GP)["ci"][0] > 0
    v["D5 TH spends more dead attempts than RR at b480 (CI > 0)"] = res["b480"]["sim_dead_attempts"][TH]["ci"][0] > 0
    if t(120, TH)["ci"][0] > 0 and t(480, TH)["ci"][0] >= 0:
        v["H1-deps (pilot)"] = "supported"
    elif any(t(b, TH)["ci"][1] < 0 for b in BUDGETS):
        v["H1-deps (pilot)"] = "contradicted"
    else:
        v["H1-deps (pilot)"] = "inconclusive"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
