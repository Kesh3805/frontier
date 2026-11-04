"""Score exp-013 (tempering the high and low tails of the hint prior).

    python research/preregistration/exp-013/evaluate.py runs/exp-013

Pairing is by seed within a budget. Factorial contrasts are paired
bootstraps between per-seed means of two pairs of arms, using the frozen
`analysis.paired_bootstrap`. Frozen with protocol.md before any exp-013
output.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

CATALOG = Path(__file__).resolve().parents[2] / "realtasks" / "catalog-v2.json"
HIGH, LOW = 0.9, 0.1  # tail thresholds, as in thompson_tempered

RR = "round_robin"
TH = "thompson(k=2,hints=true)"  # neither tail tempered
H = "thompson_tempered(k=2,high=0.5,low=1)"
L = "thompson_tempered(k=2,high=1,low=0.5)"
HL = "thompson_tempered(k=2,high=0.5,low=0.5)"
NH = "thompson(k=2,hints=false)"
POLICIES = (RR, TH, H, L, HL, NH)
BUDGETS = (330, 1320, 2640)
METRICS = (
    "sim_true_solved",
    "attempts",
    "dead_share",
    "high_dead_share",
    "low_solvable_share",
    "high_dead_attempts",
    "low_solvable_attempts",
    "low_dead_attempts",
    "high_solvable_attempts",
    "low_solvable_solved",
    "high_solvable_solved",
)


def strata():
    """Task id -> stratum, by hint tail and (for analysis only) dead flag."""
    out = {}
    for t in json.loads(CATALOG.read_text(encoding="utf-8"))["tasks"]:
        tail = "high" if t["hint"] >= HIGH else "low" if t["hint"] <= LOW else "mid"
        out[t["problem_id"] + ".goal"] = f"{tail}_{'dead' if t['dead'] else 'solvable'}"
    return out


def rows(path, st):
    rs = {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}
    for r in rs.values():
        n = r["attempts"]
        by = {}
        for task, k in r["sim_task_attempts"].items():
            by[st[task]] = by.get(st[task], 0) + k
        for s in ("high_dead", "high_solvable", "low_dead", "low_solvable"):
            r[f"{s}_attempts"] = by.get(s, 0)
        r["dead_share"] = r["sim_dead_attempts"] / n if n else 0.0
        r["high_dead_share"] = r["high_dead_attempts"] / n if n else 0.0
        r["low_solvable_share"] = r["low_solvable_attempts"] / n if n else 0.0
        solved = [st[t] for t in r["sim_true_solved_tasks"]]
        r["low_solvable_solved"] = solved.count("low_solvable")
        r["high_solvable_solved"] = solved.count("high_solvable")
    return rs


def ci(c, scale=1.0):
    return {"diff": round(scale * c.diff, 4), "ci": [round(scale * c.ci_low, 4), round(scale * c.ci_high, 4)]}


def diff(rs, a, b, metric="sim_true_solved", level=0.95):
    recs = [Record(s, p, float(r[metric])) for (s, p), r in rs.items() if p in (a, b)]
    return ci(paired_bootstrap(recs, a, b, level=level))


def contrast(rs, plus, minus, metric="sim_true_solved", level=0.95, scale=1.0):
    """Paired bootstrap of mean(plus arms) - mean(minus arms), per seed."""
    recs = [Record(s, "plus" if p in plus else "minus", float(r[metric])) for (s, p), r in rs.items() if p in plus + minus]
    return ci(paired_bootstrap(recs, "plus", "minus", level=level), scale)


def mean(rs, policy, metric):
    v = [r[metric] for (s, p), r in rs.items() if p == policy]
    return round(sum(v) / len(v), 4)


def factorial(rs, metric, level=0.95):
    return {
        "high_main": contrast(rs, (H, HL), (TH, L), metric, level),
        "low_main": contrast(rs, (L, HL), (TH, H), metric, level),
        # (HL - L) - (H - TH) = 2 * [mean(HL, TH) - mean(H, L)]
        "interaction": contrast(rs, (HL, TH), (H, L), metric, level, scale=2.0),
    }


def main(root):
    root = Path(root)
    st = strata()
    res = {}
    false_runs = 0
    for b in BUDGETS:
        rs = rows(root / f"b{b}" / "results.jsonl", st)
        false_runs += sum(r["sim_false_solved"] > 0 for r in rs.values())
        res[f"b{b}"] = {
            "means": {p: {m: mean(rs, p, m) for m in METRICS} for p in POLICIES},
            "vs_rr": {p: diff(rs, p, RR) for p in POLICIES if p != RR},
            "vs_thompson": {p: diff(rs, p, TH) for p in (H, L, HL, NH)},
            "factorial_solves": factorial(rs, "sim_true_solved"),
            "factorial_solves_97.5": factorial(rs, "sim_true_solved", level=0.975),
            "factorial_high_dead_share": factorial(rs, "high_dead_share"),
            "factorial_low_solvable_share": factorial(rs, "low_solvable_share"),
            "factorial_low_solvable_solved": factorial(rs, "low_solvable_solved"),
            "factorial_dead_share": factorial(rs, "dead_share"),
        }
    res["false_solve_runs"] = false_runs
    m, s = res["b1320"], res["b330"]

    # Holm over the two primary solve contrasts (positive direction): a
    # contrast whose 97.5% CI lies above 0 is significant; if either is, the
    # other is then tested with its 95% CI.
    strict = {k: m["factorial_solves_97.5"][k]["ci"][0] > 0 for k in ("high_main", "low_main")}
    holm = {k: strict[k] or (any(strict.values()) and m["factorial_solves"][k]["ci"][0] > 0) for k in strict}
    # A contrast's Holm-adjusted lower bound: the 97.5% bound unless the
    # other contrast was significant at 97.5%, then the 95% bound.
    def holm_low(k):
        other = "low_main" if k == "high_main" else "high_main"
        lvl = "factorial_solves" if strict[other] else "factorial_solves_97.5"
        return m[lvl][k]["ci"][0]

    v = {
        "P0 TH - RR at b1320: CI < 0 (the loss replicates)": m["vs_rr"][TH]["ci"][1] < 0,
        "P1 high-tail main effect on high-hint dead share at b1320: CI < 0": m["factorial_high_dead_share"]["high_main"]["ci"][1] < 0,
        "P2 low-tail main effect on low-hint solvable share at b1320: CI > 0": m["factorial_low_solvable_share"]["low_main"]["ci"][0] > 0,
        "P3 high-tail main effect on solves at b1320: Holm CI > 0": holm["high_main"],
        "P4 low-tail main effect on solves at b1320: Holm CI > 0": holm["low_main"],
        "P5 HL - TH at b1320: CI > 0": m["vs_thompson"][HL]["ci"][0] > 0,
        "P6 H, L, HL - TH at b330: CI lower > -0.3 (scarce-budget guardrail)": all(
            s["vs_thompson"][p]["ci"][0] > -0.3 for p in (H, L, HL)
        ),
        "P7 no run with a false solve": false_runs == 0,
    }
    vals = list(v.values())
    p0, p1, p2, p3, p4 = vals[:5]

    def verdict(alloc, solves, low_bound):
        if alloc and solves and low_bound > 0.3:
            return "supported and materially beneficial"
        if alloc and solves:
            return "supported"
        if alloc:
            return "shifts allocation without a demonstrated yield gain"
        return "not supported"

    if not p0:
        v["Decision"] = "the moderate-budget loss did not replicate"
    else:
        v["Decision (high tail: optimistic hints on dead tasks)"] = verdict(p1, p3, holm_low("high_main"))
        v["Decision (low tail: pessimistic hints on solvable tasks)"] = verdict(p2, p4, holm_low("low_main"))
        v["Closes the gap: HL - RR at b1320 >= -0.3 (point) and P5"] = vals[5] and m["vs_rr"][HL]["diff"] >= -0.3
    res["holm_lower_bounds_b1320"] = {k: round(holm_low(k), 4) for k in ("high_main", "low_main")}
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
