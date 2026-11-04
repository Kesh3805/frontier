"""Score exp-012 (novel-candidate pricing and reuse evidence for hinted Thompson).

    python research/preregistration/exp-012/evaluate.py runs/exp-012

Pairing is by seed within a budget. Frozen with protocol.md before any
exp-012 output.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR = "round_robin"
OF = "thompson(k=2,hints=true)"  # observed cost, reuse is failure
OI = "thompson_novel(k=2,hints=true,cost=observed,reuse=ignored)"
NF = "thompson_novel(k=2,hints=true,cost=novel,reuse=failure)"
NI = "thompson_novel(k=2,hints=true,cost=novel,reuse=ignored)"
FL = "thompson_flat(k=2,hints=true)"
POLICIES = (RR, OF, OI, NF, NI, FL)
BUDGETS = (330, 1320, 2640)
METRICS = ("sim_true_solved", "dead_share", "sim_dead_attempts", "reused_rejections", "rejected", "attempts")


def rows(path):
    return {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


def diff(rs, a, b, metric="sim_true_solved"):
    recs = [Record(s, p, float(r[metric])) for (s, p), r in rs.items() if p in (a, b)]
    c = paired_bootstrap(recs, a, b)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def with_dead_share(rs):
    for r in rs.values():
        r["dead_share"] = r["sim_dead_attempts"] / r["attempts"] if r["attempts"] else 0.0
    return rs


def mean(rs, policy, metric):
    v = [r[metric] for (s, p), r in rs.items() if p == policy]
    return round(sum(v) / len(v), 4)


def main(root):
    root = Path(root)
    res = {}
    false_runs = 0
    for b in BUDGETS:
        rs = with_dead_share(rows(root / f"b{b}" / "results.jsonl"))
        false_runs += sum(r["sim_false_solved"] > 0 for r in rs.values())
        res[f"b{b}"] = {
            "means": {p: {m: mean(rs, p, m) for m in METRICS} for p in POLICIES},
            "vs_rr": {p: diff(rs, p, RR) for p in POLICIES if p != RR},
            "vs_thompson": {p: diff(rs, p, OF) for p in POLICIES if p not in (RR, OF)},
            "dead_share_vs_thompson": {p: diff(rs, p, OF, "dead_share") for p in POLICIES if p not in (RR, OF)},
            "dead_attempts_vs_thompson": {p: diff(rs, p, OF, "sim_dead_attempts") for p in POLICIES if p not in (RR, OF)},
            # Effect of per-novel pricing with reuse ignored, and with reuse as failure.
            "cost_effect": {"reuse_ignored": diff(rs, NI, OI), "reuse_failure": diff(rs, NF, OF)},
        }
    res["false_solve_runs"] = false_runs
    m, s = res["b1320"], res["b330"]
    v = {
        "N0 TH - RR at b1320: CI < 0 (the loss replicates)": m["vs_rr"][OF]["ci"][1] < 0,
        "N1 NF - TH at b1320: CI > 0": m["vs_thompson"][NF]["ci"][0] > 0,
        "N2 NF - RR at b1320 >= -0.3 (point)": m["vs_rr"][NF]["diff"] >= -0.3,
        "N3 NF - RR at b330: CI > 0": s["vs_rr"][NF]["ci"][0] > 0,
        "N4 OI - TH at b1320: CI < 0": m["vs_thompson"][OI]["ci"][1] < 0,
        "N5 cost effect larger with reuse ignored at b1320 (point)": m["cost_effect"]["reuse_ignored"]["diff"]
        > m["cost_effect"]["reuse_failure"]["diff"],
        "N6 dead-task share of attempts NF - TH at b1320: CI < 0": m["dead_share_vs_thompson"][NF]["ci"][1] < 0,
        "N7 no run with a false solve": false_runs == 0,
    }
    nf = m["vs_thompson"][NF]
    n0, n1, n2, n6 = (v[k] for k in v if k.startswith(("N0", "N1", "N2", "N6")))
    if not n0:
        v["Decision"] = "the moderate-budget loss did not replicate"
    elif n1 and n6 and n2:
        v["Decision"] = "pricing a novel candidate fixes hinted Thompson's moderate-budget loss"
    elif n1 and n6:
        v["Decision"] = "pricing a novel candidate improves on hinted Thompson but does not close the gap to round-robin"
    elif nf["ci"][1] <= 0:
        v["Decision"] = "pricing a novel candidate does not help"
    else:
        v["Decision"] = "unclear"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
