import importlib.util, statistics as st, sys, gzip, json
from pathlib import Path
spec = importlib.util.spec_from_file_location("ev", "research/preregistration/exp-009/evaluate.py"); ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
def rows_of(p):
    t = gzip.decompress(Path(p).read_bytes()).decode() if p.endswith(".gz") else Path(p).read_text()
    return [json.loads(l) for l in t.splitlines() if l.strip()]
for name, p in (("windows", "results/exp-009/M-measurements.jsonl.gz"), ("linux", sys.argv[1])):
    rows = rows_of(p); c = list(ev.per_candidate(rows).values())
    fail = [x for x in c if x["verdict_f"] == "FAIL"]; pas = [x for x in c if x["verdict_f"] == "PASS"]
    m = lambda xs, k: round(1000 * st.fmean(x[k] for x in xs), 2)
    pr = st.median(x["t_e"] / x["t_f"] for x in pas)
    first = [x for x in fail if x["c_ff"] == ev.PER_CASE]
    aF, bF = ev.ols([x["c_ff"] / ev.PER_CASE for x in fail], [x["t_f"] for x in fail])
    pc = {mo: round(1000 * st.median(r["parent_cpu_s"] for r in rows if r["mode"] == mo), 2) for mo in "FE"}
    print(name, {"F_pass_ms": m(pas, "t_f"), "E_pass_ms": m(pas, "t_e"), "F_fail_ms": m(fail, "t_f"), "E_fail_ms": m(fail, "t_e"),
                 "E_fail_first_case_ms": m(first, "t_e"), "n_first": len(first),
                 "pass_mean_diff_ms": round(m(pas, "t_f") - m(pas, "t_e"), 2),
                 "fail_saving_beyond_pass_ratio": round(1 - sum(x["t_e"] for x in fail) / (pr * sum(x["t_f"] for x in fail)), 4),
                 "median_parent_cpu_ms": pc})
