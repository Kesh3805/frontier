"""Frozen scoring for exp-009L (exp-009 part M replicated on a Linux runner).

    python research/preregistration/exp-009L/score.py M_DIR [RUNNER_JSON]

M_DIR is measure.py's output (measurements.jsonl, corpus.jsonl,
attempts.jsonl, manifest.json); RUNNER_JSON is the runner description the
workflow writes. The part-M quantities come from exp-009's frozen
`evaluate.py`, imported unchanged, so they are computed exactly as on
Windows. The Windows baseline is read from `results/exp-009/`. Prints one
JSON object with every quantity the protocol names, the prediction verdicts,
the decision and the invalidation checks.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN_COMMIT = "bad09c9f497524c1ee6fc7146b4a541b4fbf9667"
REPS, MODES = 3, 2
WIN = ROOT / "results" / "exp-009"

_spec = importlib.util.spec_from_file_location("exp009_evaluate", ROOT / "research" / "preregistration" / "exp-009" / "evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)  # type: ignore[union-attr]


def load_gz(p: Path) -> list[dict]:
    return [json.loads(line) for line in gzip.decompress(p.read_bytes()).decode("utf-8").splitlines() if line.strip()]


def part_m(rows: list[dict], attempts: list[dict]) -> tuple[dict, dict]:
    """exp-009 evaluate.py's part-M block, verbatim in substance."""
    cands = ev.per_candidate(rows)
    allc = list(cands.values())
    fail = [c for c in allc if c["verdict_f"] == "FAIL"]
    passed = [c for c in allc if c["verdict_f"] == "PASS"]
    m = {
        "candidates": len(allc), "fail": len(fail), "pass": len(passed),
        "inconclusive": sum(c["verdict_f"] == "INCONCLUSIVE" for c in allc),
        "verdict_disagreements": sum(not c["agree"] for c in allc),
        "charge_mismatches": sum(c["c_ff"] != c["c_ff_f"] for c in allc),
        "mean_wall_f_s": round(statistics.fmean(c["t_f"] for c in allc), 5),
        "mean_wall_e_s": round(statistics.fmean(c["t_e"] for c in allc), 5),
        "S_meas_fail": round(ev.saving(fail, "t_f", "t_e"), 4),
        "S_meas_fail_ci": ev.boot(fail, lambda s: ev.saving(s, "t_f", "t_e")),
        "S_mod_fail": round(ev.saving(fail, "c_full", "c_ff"), 4),
        "S_meas_all": round(ev.saving(allc, "t_f", "t_e"), 4),
        "S_meas_all_ci": ev.boot(allc, lambda s: ev.saving(s, "t_f", "t_e")),
        "S_mod_all": round(ev.saving(allc, "c_full", "c_ff"), 4),
        "S_cpu_fail": round(ev.saving(fail, "cpu_f", "cpu_e"), 4),
        "fixed_share": round(ev.fixed_share(allc), 4), "fixed_share_ci": ev.boot(allc, ev.fixed_share),
        "fit_seconds": dict(zip(("a", "b_per_case"), (round(v, 7) for v in ev.ols(
            [c["c_ff"] / ev.PER_CASE for c in allc], [c["t_e"] for c in allc])))),
        "pass_ratio_median": round(statistics.median(c["t_e"] / c["t_f"] for c in passed), 4) if passed else None,
    }
    gen = sum(a["gen_wall_s"] for a in attempts) / len(attempts)
    m["descriptive"] = {"mean_attempt_wall_s": round(gen, 5),
                        "verification_share_measured_F": round(m["mean_wall_f_s"] / (m["mean_wall_f_s"] + gen), 4),
                        "verification_share_measured_E": round(m["mean_wall_e_s"] / (m["mean_wall_e_s"] + gen), 4)}
    return m, cands


def drift(rows: list[dict]) -> dict:
    """Median wall time per mode in the first and last quarter of measurement order (descriptive)."""
    q = len(rows) // 4
    return {part: {mode: round(statistics.median(r["wall_s"] for r in rs if r["mode"] == mode), 5) for mode in ("F", "E")}
            for part, rs in (("first_quarter", rows[:q]), ("last_quarter", rows[-q:]))}


def main(mdir: Path, runner_json: Path | None) -> None:
    rows = ev.load_jsonl(mdir / "measurements.jsonl")
    corpus = ev.load_jsonl(mdir / "corpus.jsonl")
    attempts = ev.load_jsonl(mdir / "attempts.jsonl")
    man = json.loads((mdir / "manifest.json").read_text(encoding="utf-8"))
    runner = json.loads(runner_json.read_text(encoding="utf-8")) if runner_json else None
    m, cands = part_m(rows, attempts)

    win = json.loads((WIN / "evaluation.json").read_text(encoding="utf-8"))["M"]
    win_cands = ev.per_candidate(load_gz(WIN / "M-measurements.jsonl.gz"))
    win_corpus = load_gz(WIN / "M-corpus.jsonl.gz")
    same_corpus = corpus == win_corpus
    common = sorted(set(cands) & set(win_cands))
    keys = ("fixed_share", "S_meas_fail", "S_mod_fail", "S_meas_all", "S_mod_all", "mean_wall_f_s", "mean_wall_e_s",
            "pass_ratio_median")
    cmp = {
        "corpus_identical": same_corpus,
        "verdict_charge_identical_to_windows": sum(
            cands[i]["verdict_f"] == win_cands[i]["verdict_f"] and cands[i]["c_ff"] == win_cands[i]["c_ff"] for i in common),
        "compared": len(common),
        "table": {k: {"windows": win[k], "linux": m[k]} for k in keys},
        "fit_seconds": {"windows": win["fit_seconds"], "linux": m["fit_seconds"]},
        "fixed_cost_ratio_linux_over_windows": round(m["fit_seconds"]["a"] / win["fit_seconds"]["a"], 4),
        "per_case_ratio_linux_over_windows": round(m["fit_seconds"]["b_per_case"] / win["fit_seconds"]["b_per_case"], 4),
    }

    py = man["python"].split()[0]
    invalid = {
        "source_dirty": man["source_dirty"],
        "source_commit_not_run_commit": man["source_commit"] != RUN_COMMIT,
        "measurements_sha256_mismatch": hashlib.sha256((mdir / "measurements.jsonl").read_bytes()).hexdigest()
        != man["measurements_sha256"],
        "incomplete": len(rows) != len(corpus) * REPS * MODES or m["candidates"] != len(corpus),
        "not_linux_x86_64": not (man["platform"].startswith("Linux") and man["machine"] == "x86_64"),
        "not_python_3_12": not py.startswith("3.12."),
    }

    w_ci_hi = win["S_meas_fail_ci"][1]
    v = {
        # exp-009's frozen criteria, applied to the Linux data unchanged
        "M1 measured saving on FAIL candidates: CI upper bound < 0.25": m["S_meas_fail_ci"][1] < 0.25,
        "M2 modelled minus measured saving on FAIL candidates >= 0.40": m["S_mod_fail"] - m["S_meas_fail"] >= 0.40,
        "M3 fixed-overhead share of a full verification >= 0.75": m["fixed_share"] >= 0.75,
        "M4 early stop costs PASS candidates within 10% (median ratio in [0.9, 1.1])": m["pass_ratio_median"] is not None
        and 0.9 <= m["pass_ratio_median"] <= 1.1,
        "M5 same verdicts and charges for every candidate (F vs E)": m["verdict_disagreements"] == 0 and m["charge_mismatches"] == 0,
        # exp-009L predictions
        "L1 fixed cost a on Linux <= 0.06 s (at most half of Windows' 0.1205 s)": m["fit_seconds"]["a"] <= 0.06,
        "L2 fixed share on Linux: CI upper bound < Windows point estimate (0.9215)": m["fixed_share_ci"][1] < win["fixed_share"],
        "L3 measured saving on FAIL candidates: Linux CI lower bound > Windows CI upper bound (0.0779)": m["S_meas_fail_ci"][0] > w_ci_hi,
        "L4 same corpus as Windows, and every candidate's verdict and charge equal to Windows'": same_corpus
        and cmp["verdict_charge_identical_to_windows"] == len(win_cands) == len(cands),
    }
    m1 = v["M1 measured saving on FAIL candidates: CI upper bound < 0.25"]
    m2 = v["M2 modelled minus measured saving on FAIL candidates >= 0.40"]
    m3 = v["M3 fixed-overhead share of a full verification >= 0.75"]
    if m1 and m2 and m3:
        decision = "Windows result generalises"
    elif not m1 and not m3:
        decision = "host-specific"
    else:
        decision = "partial"
    if m1 and m2:
        exp009_rule = "modelled fail-fast saving does not hold physically on this harness"
    elif m["S_meas_fail_ci"][0] >= 0.5 * m["S_mod_fail"]:
        exp009_rule = "modelled fail-fast saving holds physically"
    else:
        exp009_rule = "partial"
    print(json.dumps({"M": m, "drift": drift(rows), "comparison": cmp, "manifest": man, "runner": runner,
                      "invalidation": {**invalid, "invalid": any(invalid.values())},
                      "verdicts": {**v, "exp-009 decision rule on Linux": exp009_rule, "Decision": decision}}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
