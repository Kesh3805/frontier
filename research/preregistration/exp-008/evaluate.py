"""Score exp-008 (fail-fast charging) against its full-charge counterparts.

    python research/preregistration/exp-008/evaluate.py runs/exp-008 \
        runs/rerun-k03/exp-004 runs/rerun-k03/exp-006 runs/exp-007

Part S pairs with exp-006 (v2 suite, full charge) and exp-004 (v1 suite),
both kernel 0.3 re-runs; part D pairs with exp-007. Pairing is by
(budget, policy, seed). Frozen with protocol.md before any exp-008 output.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR, TH = "round_robin", "thompson(k=2,hints=true)"


def rows(path):
    return {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


def paired(a_rows, b_rows, policy, metric):
    recs = []
    for (seed, pol), r in a_rows.items():
        if pol == policy:
            recs += [Record(seed, "a", float(r[metric])), Record(seed, "b", float(b_rows[(seed, pol)][metric]))]
    c = paired_bootstrap(recs, "a", "b")
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)], "a": round(c.mean_a, 4), "b": round(c.mean_b, 4)}


def vs_rr(rs, policy):
    recs = [Record(s, p, float(r["sim_true_solved"])) for (s, p), r in rs.items() if p in (policy, RR)]
    c = paired_bootstrap(recs, policy, RR)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def share(rs, policy):
    v = [r["verification_units"] / r["committed_units"] for (s, p), r in rs.items() if p == policy and r["committed_units"] > 0]
    return round(sum(v) / len(v), 4)


def main(ff_root, v1_root, v2_root, deps_root):
    res, v = {"S": {}, "D": {}}, {}
    false_runs = 0
    for b in (60, 240, 480):
        ff = rows(Path(ff_root) / f"S-b{b}" / "results.jsonl")
        v2 = rows(Path(v2_root) / f"b{b}" / "results.jsonl")
        v1 = rows(Path(v1_root) / f"b{b}" / "results.jsonl")
        policies = sorted({p for _, p in ff})
        false_runs += sum(r["sim_false_solved"] > 0 for r in ff.values())
        cell = {"ff_minus_v2full": {p: paired(ff, v2, p, "sim_true_solved") for p in policies},
                "ff_minus_v1": {p: paired(ff, v1, p, "sim_true_solved") for p in policies},
                "verification_share_rr": {"v1": share(v1, RR), "v2_full": share(v2, RR), "v2_ff": share(ff, RR)},
                "vs_rr_ff": {p: vs_rr(ff, p) for p in policies if p != RR}}
        d = cell["ff_minus_v2full"][RR]
        lost = paired(v1, v2, RR, "sim_true_solved")["diff"]
        cell["recovery_fraction_rr"] = round(d["diff"] / lost, 4) if lost else None
        res["S"][f"b{b}"] = cell
    for b in (120, 480, 1920):
        ff, full = rows(Path(ff_root) / f"D-b{b}" / "results.jsonl"), rows(Path(deps_root) / f"b{b}" / "results.jsonl")
        pols = sorted({p for _, p in ff})
        false_runs += sum(r["sim_false_solved"] > 0 for r in ff.values())
        res["D"][f"b{b}"] = {"ff_minus_full": {p: paired(ff, full, p, "sim_true_solved") for p in pols},
                             "verification_share_rr": {"full": share(full, RR), "ff": share(ff, RR)},
                             "vs_rr_ff": {p: vs_rr(ff, p) for p in pols if p != RR}}
    S, D = res["S"], res["D"]
    v["F1 RR verification share at S-b240 falls by >= 40% relative"] = S["b240"]["verification_share_rr"]["v2_ff"] <= 0.6 * S["b240"]["verification_share_rr"]["v2_full"]
    v["F2 RR true solves rise with fail-fast at S-b60 (CI > 0)"] = S["b60"]["ff_minus_v2full"][RR]["ci"][0] > 0
    v["F3 RR recovers >= half of the v1->v2 loss at S-b60"] = (S["b60"]["recovery_fraction_rr"] or 0) >= 0.5
    v["F4 at most one fail-fast run with a false solve"] = false_runs <= 1
    v["F5 TH beats RR at D-b120 under fail-fast (CI > 0)"] = D["b120"]["vs_rr_ff"][TH]["ci"][0] > 0
    v["F6 RR true solves rise with fail-fast at D-b120 (CI > 0)"] = D["b120"]["ff_minus_full"][RR]["ci"][0] > 0
    res["false_solve_runs_ff"] = false_runs
    if v["F2 RR true solves rise with fail-fast at S-b60 (CI > 0)"] and v["F3 RR recovers >= half of the v1->v2 loss at S-b60"]:
        v["Decision"] = "fail-fast recovers yield"
    elif not v["F2 RR true solves rise with fail-fast at S-b60 (CI > 0)"]:
        v["Decision"] = "fail-fast does not recover yield"
    else:
        v["Decision"] = "partial recovery"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:5])
