"""Score exp-002 predictions with the frozen frontier_py.analysis functions.

    python research/preregistration/exp-002/evaluate.py runs/exp-002

Frozen together with protocol.md, before any exp-002 output existed.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR = "round_robin"
TH = "thompson(k=2,hints=true)"
KS = ["thompson(k=0.5,hints=true)", TH, "thompson(k=8,hints=true)"]
POLS = [RR, "greedy_prior", *KS, "thompson(k=2,hints=false)", "oracle_index"]
LAMS = ("0.0", "0.5", "1.0")


def load(path):
    out = {"solved": defaultdict(list), "sim_dead_attempts": defaultdict(list)}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        for m in out:
            out[m][r["regime"]].append(Record((r["regime"], r["seed"]), r["policy"], float(r[m])))
    return out


def cmp(recs, a, b=RR):
    c = paired_bootstrap(recs, a, b)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def mean(recs, arm):
    v = [r.value for r in recs if r.arm == arm]
    return sum(v) / len(v)


def cell(data, prefix):
    out = {}
    for lam in LAMS:
        reg = f"{prefix}-det{lam}"
        s, d = data["solved"][reg], data["sim_dead_attempts"][reg]
        out[lam] = {
            "solved_mean": {p: round(mean(s, p), 3) for p in POLS},
            "dead_attempts_mean": {p: round(mean(d, p), 3) for p in POLS},
            "delta": {p: cmp(s, p) for p in POLS if p != RR},
            "delta_dead": {p: cmp(d, p) for p in POLS if p != RR},
        }
    return out


def main(root):
    root = Path(root)
    b600, b1200 = load(root / "b600" / "results.jsonl"), load(root / "b1200" / "results.jsonl")
    res = {"R2-b600": cell(b600, "R2"), "R2-b1200": cell(b1200, "R2"), "R3-b600": cell(b600, "R3")}
    p = res["R2-b600"]
    v = {}
    v["P1"] = p["0.0"]["delta_dead"][TH]["ci"][0] > 0
    v["P2"] = p["0.0"]["dead_attempts_mean"][TH] > p["0.5"]["dead_attempts_mean"][TH] > p["1.0"]["dead_attempts_mean"][TH]
    v["P3"] = p["0.0"]["delta"][TH]["diff"] < p["0.5"]["delta"][TH]["diff"] < p["1.0"]["delta"][TH]["diff"]
    v["P4"] = not (p["1.0"]["delta"][TH]["ci"][1] < 0)
    v["P4-strong"] = p["1.0"]["delta"][TH]["ci"][0] > 0
    dk = [p["0.0"]["dead_attempts_mean"][k] for k in KS]
    v["P5"] = dk[0] < dk[1] < dk[2]
    for name in ("R2-b1200", "R3-b600"):
        q = res[name]
        v[f"secondary {name} P1"] = q["0.0"]["delta_dead"][TH]["ci"][0] > 0
        v[f"secondary {name} P3"] = q["0.0"]["delta"][TH]["diff"] < q["0.5"]["delta"][TH]["diff"] < q["1.0"]["delta"][TH]["diff"]
    if v["P1"] and v["P2"] and v["P3"] and v["P4"]:
        v["O"] = "supported"
    elif not v["P1"] or p["1.0"]["delta"][TH]["ci"][1] < 0:
        v["O"] = "refuted"
    else:
        v["O"] = "partially supported"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
