"""Score exp-006 (strong verifier) against exp-004 (v1 verifier).

    python research/preregistration/exp-006/evaluate.py runs/exp-004 runs/exp-006

Same seeds, worker streams and shuffled order; only the hidden suite (and
hence verification cost) differs. Pairing is by (budget, policy, seed).
Frozen with protocol.md before any exp-006 output existed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from frontier_py.analysis import Record, paired_bootstrap  # noqa: E402

RR, TH = "round_robin", "thompson(k=2,hints=true)"
POLS = [RR, "fifo", "random", "greedy_prior", TH, "thompson(k=2,hints=false)", "oracle_index"]


def rows(path):
    return {(r["seed"], r["policy"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


def strong_minus_weak(old, new, policy, metric):
    recs = []
    for (seed, pol), r in new.items():
        if pol == policy:
            recs.append(Record(seed, "v2", float(r[metric])))
            recs.append(Record(seed, "v1", float(old[(seed, pol)][metric])))
    c = paired_bootstrap(recs, "v2", "v1")
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)], "v2": round(c.mean_a, 4), "v1": round(c.mean_b, 4)}


def vs_rr(new, policy, metric="sim_true_solved"):
    recs = [Record(s, p, float(r[metric])) for (s, p), r in new.items() if p in (policy, RR)]
    c = paired_bootstrap(recs, policy, RR)
    return {"diff": round(c.diff, 4), "ci": [round(c.ci_low, 4), round(c.ci_high, 4)]}


def share(rows_, policy):
    v = [r["verification_units"] / r["committed_units"] for (s, p), r in rows_.items() if p == policy and r["committed_units"] > 0]
    return round(sum(v) / len(v), 4)


def main(old_root, new_root):
    res, v = {}, {}
    total_false_v2 = 0
    for b in (60, 240, 480):
        old, new = rows(Path(old_root) / f"b{b}" / "results.jsonl"), rows(Path(new_root) / f"b{b}" / "results.jsonl")
        total_false_v2 += sum(1 for r in new.values() if r["sim_false_solved"] > 0)
        res[f"b{b}"] = {
            "true_solved_v2_minus_v1": {p: strong_minus_weak(old, new, p, "sim_true_solved") for p in POLS},
            "accepted_v2_minus_v1": {p: strong_minus_weak(old, new, p, "solved") for p in POLS},
            "false_solved_v2_minus_v1": {p: strong_minus_weak(old, new, p, "sim_false_solved") for p in POLS},
            "verification_share": {"v1": share(old, RR), "v2": share(new, RR)},
            "vs_rr_v2": {p: vs_rr(new, p) for p in POLS if p != RR},
        }
    res["runs_with_false_solve_v2"] = total_false_v2
    v["W1 at most one v2 run with a false solve (all budgets, all policies)"] = total_false_v2 <= 1
    v["W2 RR true solves drop with v2 at b60 (CI < 0)"] = res["b60"]["true_solved_v2_minus_v1"][RR]["ci"][1] < 0
    v["W3 RR true solves change by < 0.3 at b480"] = abs(res["b480"]["true_solved_v2_minus_v1"][RR]["diff"]) < 0.3
    v["W4 RR verification share more than doubles at b240"] = res["b240"]["verification_share"]["v2"] > 2 * res["b240"]["verification_share"]["v1"]
    d = [res[f"b{b}"]["true_solved_v2_minus_v1"][RR] for b in (60, 240, 480)]
    if all(x["ci"][0] >= 0 for x in d):
        v["Decision (RR)"] = "strong verification does not cost true yield"
    elif any(x["ci"][1] < 0 for x in d):
        v["Decision (RR)"] = "strong verification costs true yield at some budget"
    else:
        v["Decision (RR)"] = "inconclusive"
    res["verdicts"] = v
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
