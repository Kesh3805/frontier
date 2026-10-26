"""Score exp-001 predictions using the frozen frontier_py.analysis functions.

    python research/preregistration/exp-001/evaluate.py runs/exp-001

Written after the protocol was frozen, before results were inspected; it
only applies the protocol's rules mechanically.
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


def load(path, metric):
    by_regime = defaultdict(list)
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        by_regime[r["regime"]].append(Record((r["regime"], r["seed"]), r["policy"], float(r[metric])))
    return by_regime


def cmp(recs, a, b=RR):
    c = paired_bootstrap(recs, a, b)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)], "mean_a": round(c.mean_a, 3), "mean_b": round(c.mean_b, 3)}


def means(recs):
    acc = defaultdict(list)
    for r in recs:
        acc[r.arm].append(r.value)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def main(root):
    root = Path(root)
    out = {}
    verdicts = {}

    # Part A
    A = {b: load(root / f"A-b{b}" / "results.jsonl", "solved") for b in (300, 600, 1200)}
    a = {f"B{b}/noise{n}": {pol: cmp(A[b][f"A-noise{n}"], pol) for pol in
                            ["thompson(k=0.5,hints=true)", TH, "thompson(k=8,hints=true)", TN, "greedy_prior", "oracle_index"]}
         for b in A for n in (0, 1, 2)}
    out["A"] = a
    rep = a["B600/noise1"][TH]
    verdicts["P-A0"] = rep["ci"][1] < 0
    verdicts["P-A1"] = all(a[f"B{b}/noise0"][TH]["ci"][0] >= 0 for b in (300, 600, 1200)) and a["B300/noise0"][TH]["ci"][0] > 0
    verdicts["P-A2"] = all(a[f"B{b}/noise0"][TH]["diff"] > a[f"B{b}/noise1"][TH]["diff"] > a[f"B{b}/noise2"][TH]["diff"] for b in (300, 600, 1200))
    verdicts["P-A3"] = all(
        a[f"B{b}/noise{n}"]["thompson(k=0.5,hints=true)"]["diff"] > a[f"B{b}/noise{n}"][TH]["diff"] > a[f"B{b}/noise{n}"]["thompson(k=8,hints=true)"]["diff"]
        for b in (600, 1200) for n in (1, 2))
    verdicts["P-A4"] = a["B1200/noise1"][TN]["ci"][1] >= 0
    verdicts["M"] = ("supported" if verdicts["P-A1"] and verdicts["P-A2"] and verdicts["P-A3"]
                     else "refuted" if not verdicts["P-A1"] else "partially supported")

    # Part B
    B = {lab: load(root / f"B-{lab}" / "results.jsonl", "solved") for lab in ("scarce", "moderate")}
    b_out, p1, p2, p3_cells, robust = {}, True, True, [], True
    for lab, regs in B.items():
        for rn in ("R2", "R3", "R5"):
            cell = {}
            for rho in ("0.0", "0.5", "0.9"):
                recs = regs[f"B-{rn}-rho{rho}"]
                cell[rho] = {"means": {k: round(v, 3) for k, v in means(recs).items()}, "delta": cmp(recs, TH), "delta_nohints": cmp(recs, TN)}
            b_out[f"{lab}/{rn}"] = cell
            p1 &= all(cell["0.0"]["means"][pol] > cell["0.9"]["means"][pol] for pol in cell["0.0"]["means"])
            p2 &= cell["0.0"]["delta"]["diff"] > cell["0.9"]["delta"]["diff"]
            if cell["0.9"]["delta"]["ci"][1] < 0:
                p3_cells.append(f"{lab}/{rn}")
            if cell["0.0"]["delta"]["ci"][0] > 0 and not cell["0.9"]["delta"]["ci"][0] > 0:
                robust = False
    out["B"] = b_out
    verdicts["P-B1"], verdicts["P-B2"], verdicts["P-B3"] = p1, p2, bool(p3_cells)
    verdicts["P-B3 cells"] = p3_cells
    verdicts["B robust to correlation"] = robust

    # Part C
    Ct = load(root / "C-moderate" / "results.jsonl", "sim_true_solved")
    Cf = load(root / "C-moderate" / "results.jsonl", "sim_false_solved")
    Cs = load(root / "C-moderate" / "results.jsonl", "solved")
    c_out, p1, p2, p3, p4 = {}, True, True, True, True
    for rn in ("R2", "R3", "R5"):
        cell = {}
        for fnr in ("0.0", "0.2"):
            for fpr in ("0.0", "0.02"):
                k = f"C-{rn}-fnr{fnr}-fpr{fpr}"
                cell[f"fnr{fnr}/fpr{fpr}"] = {
                    "true_solved_means": {p: round(v, 3) for p, v in means(Ct[k]).items()},
                    "false_solved_means": {p: round(v, 3) for p, v in means(Cf[k]).items()},
                    "accepted_means": {p: round(v, 3) for p, v in means(Cs[k]).items()},
                    "delta_true": cmp(Ct[k], TH),
                    "delta_false": cmp(Cf[k], TH),
                }
        c_out[rn] = cell
        for fnr in ("0.0", "0.2"):
            p1 &= all(v > 0 for v in cell[f"fnr{fnr}/fpr0.02"]["false_solved_means"].values())
        if rn in ("R2", "R3"):
            p2 &= cell["fnr0.0/fpr0.02"]["delta_false"]["ci"][1] < 0
        for fpr in ("0.0", "0.02"):
            base, noisy = cell[f"fnr0.0/fpr{fpr}"]["true_solved_means"], cell[f"fnr0.2/fpr{fpr}"]["true_solved_means"]
            p3 &= all(noisy[p] < base[p] for p in base)
        sgn = lambda x: (x > 0) - (x < 0)  # noqa: E731
        p4 &= sgn(cell["fnr0.2/fpr0.02"]["delta_true"]["diff"]) == sgn(cell["fnr0.0/fpr0.0"]["delta_true"]["diff"])
    out["C"] = c_out
    verdicts.update({"P-C1": p1, "P-C2": p2, "P-C3": p3, "P-C4": p4})
    out["verdicts"] = verdicts
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
