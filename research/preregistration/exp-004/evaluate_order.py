"""Score exp-004's order-effect predictions against exp-003.

    python research/preregistration/exp-004/evaluate_order.py runs/exp-003 runs/exp-004

exp-003 and exp-004 share seeds and worker streams; they differ only in
problem order (catalog order vs per-seed shuffle). Pairing is by
(budget, policy, seed). Frozen with protocol.md before any exp-004 output.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR, FIFO, TH = "round_robin", "fifo", "thompson(k=2,hints=true)"
POLS = [RR, FIFO, "random", "greedy_prior", TH, "thompson(k=2,hints=false)", "oracle_index"]


def rows(path):
    return {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


def order_effect(old, new, policy, metric="sim_true_solved"):
    recs = []
    for (seed, pol), r in new.items():
        if pol == policy:
            recs.append(Record(seed, "shuffled", float(r[metric])))
            recs.append(Record(seed, "catalog", float(old[(seed, pol)][metric])))
    c = paired_bootstrap(recs, "shuffled", "catalog")
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def vs_rr(new, policy, metric="sim_true_solved"):
    recs = [Record(s, p, float(r[metric])) for (s, p), r in new.items() if p in (policy, RR)]
    c = paired_bootstrap(recs, policy, RR)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def main(old_root, new_root):
    res, v = {}, {}
    for b in (60, 240, 480):
        old, new = rows(Path(old_root) / f"b{b}" / "results.jsonl"), rows(Path(new_root) / f"b{b}" / "results.jsonl")
        res[f"b{b}"] = {"order_effect": {p: order_effect(old, new, p) for p in POLS},
                        "fifo_vs_rr_shuffled": vs_rr(new, FIFO)}
    v["O1 FIFO advantage disappears (FIFO-RR CI upper <= 0 at b60 and b240, shuffled)"] = all(
        res[f"b{b}"]["fifo_vs_rr_shuffled"]["ci"][1] <= 0 for b in (60, 240))
    v["O2 FIFO itself drops with shuffling at b60 (CI < 0)"] = res["b60"]["order_effect"][FIFO]["ci"][1] < 0
    v["O3 RR order-insensitive (|effect| < 0.5 at every budget)"] = all(
        abs(res[f"b{b}"]["order_effect"][RR]["diff"]) < 0.5 for b in (60, 240, 480))
    v["O4 thompson(hints) order-insensitive (|effect| < 0.5 at every budget)"] = all(
        abs(res[f"b{b}"]["order_effect"][TH]["diff"]) < 0.5 for b in (60, 240, 480))
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
