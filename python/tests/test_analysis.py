import json
import math

import numpy as np
import pytest

from frontier_py.analysis import Record, load_jsonl, main, paired_bootstrap, sign_test_p


def recs(pairs, a="A", b="B"):
    out = []
    for c, (va, vb) in enumerate(pairs):
        out += [Record(c, a, va), Record(c, b, vb)]
    return out


def test_constant_difference_collapses_ci():
    rng = np.random.default_rng(1)
    base = rng.normal(10, 3, 40)
    r = paired_bootstrap(recs([(x + 2.5, x) for x in base]), "A", "B")
    assert r.n_clusters == 40 and r.n_excluded == 0
    assert r.diff == pytest.approx(2.5)
    assert r.ci_low == pytest.approx(2.5) and r.ci_high == pytest.approx(2.5)
    assert (r.a_gt_b, r.a_lt_b, r.ties) == (40, 0, 0)
    assert r.sign_p == pytest.approx(2 / 2**40)
    assert r.rel_diff == pytest.approx(2.5 / base.mean())


def test_zero_difference_ci_contains_zero():
    rng = np.random.default_rng(2)
    noise = rng.normal(0, 1, 60)
    pairs = [(5 + e, 5 - e) for e in noise]  # symmetric differences around 0
    r = paired_bootstrap(recs(pairs), "A", "B")
    assert r.ci_low < 0 < r.ci_high
    assert r.sign_p > 0.05


def test_identical_arms_all_ties():
    r = paired_bootstrap(recs([(1.0, 1.0)] * 10), "A", "B")
    assert (r.diff, r.ci_low, r.ci_high, r.ties, r.sign_p) == (0.0, 0.0, 0.0, 10, 1.0)


def test_deterministic_given_seed_and_sensitive_to_it():
    rng = np.random.default_rng(3)
    data = recs([(x, y) for x, y in rng.normal(0, 1, (30, 2))])
    r1, r2 = paired_bootstrap(data, "A", "B"), paired_bootstrap(data, "A", "B")
    assert (r1.ci_low, r1.ci_high) == (r2.ci_low, r2.ci_high)
    assert r1.replicates == 10_000 and r1.seed == 26102026
    r3 = paired_bootstrap(data, "A", "B", seed=1)
    assert (r3.ci_low, r3.ci_high) != (r1.ci_low, r1.ci_high)


def test_missing_arm_clusters_excluded_and_counted():
    data = recs([(2.0, 1.0)] * 5) + [Record("only-a", "A", 100.0), Record("only-b", "B", -100.0), Record("other", "C", 0.0)]
    r = paired_bootstrap(data, "A", "B")
    assert r.n_clusters == 5 and r.n_excluded == 2 and r.diff == 1.0


def test_replicate_records_are_averaged_within_cluster():
    data = [Record(0, "A", 1.0), Record(0, "A", 3.0), Record(0, "B", 1.0), Record(1, "A", 2.0), Record(1, "B", 2.0)]
    r = paired_bootstrap(data, "A", "B")
    assert r.diff == pytest.approx(0.5) and r.mean_a == pytest.approx(2.0)


def test_no_overlap_raises():
    with pytest.raises(ValueError):
        paired_bootstrap([Record(0, "A", 1.0)], "A", "B")


@pytest.mark.parametrize(
    "pos,neg,expected",
    [(0, 0, 1.0), (5, 5, 1.0), (10, 0, 2 / 1024), (9, 1, 2 * 11 / 1024), (1, 9, 2 * 11 / 1024), (3, 1, 0.625), (2, 2, 1.0)],
)
def test_sign_test(pos, neg, expected):
    assert sign_test_p(pos, neg) == pytest.approx(expected)


def test_sign_test_matches_brute_force():
    n = 12
    for k in range(n + 1):
        brute = sum(math.comb(n, i) for i in range(n + 1) if math.comb(n, i) <= math.comb(n, k)) / 2**n
        assert sign_test_p(k, n - k) == pytest.approx(min(1.0, brute))


def write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def experiment_rows():
    rows = []
    for regime, effect in (("heterogeneous", 3), ("homogeneous", 0)):
        for seed in range(20):
            rows.append({"regime": regime, "policy": "round_robin", "seed": seed, "solved": 10 + seed % 3,
                         "committed_units": 100.0, "time_to_first_solve": None if seed == 0 else 5.0})
            rows.append({"regime": regime, "policy": "posterior", "seed": seed, "solved": 10 + seed % 3 + effect,
                         "committed_units": 100.0, "time_to_first_solve": 4.0})
    return rows


def test_loader_groups_by_regime_and_drops_nulls(tmp_path):
    p = tmp_path / "r.jsonl"
    write_jsonl(p, experiment_rows())
    groups, dropped = load_jsonl(p, "time_to_first_solve")
    assert dropped == 2 and set(groups) == {"heterogeneous", "homogeneous"}
    r = paired_bootstrap(groups["heterogeneous"], "posterior", "round_robin")
    assert r.n_clusters == 19 and r.n_excluded == 1 and r.diff == pytest.approx(-1.0)
    groups, _ = load_jsonl(p, "solved")
    assert {rec.cluster_id for rec in groups["homogeneous"]} == {("homogeneous", s) for s in range(20)}


def test_loader_rejects_non_numeric(tmp_path):
    p = tmp_path / "r.jsonl"
    write_jsonl(p, [{"regime": "x", "policy": "a", "seed": 0, "solved": "yes"}])
    with pytest.raises(ValueError):
        load_jsonl(p, "solved")


def test_loader_treats_bools_as_indicators(tmp_path):
    p = tmp_path / "r.jsonl"
    write_jsonl(p, [{"regime": "x", "policy": "a", "seed": 0, "solved": True}])
    groups, _ = load_jsonl(p, "solved")
    assert groups["x"][0].value == 1.0


def test_cli_markdown(tmp_path, capsys):
    p = tmp_path / "r.jsonl"
    write_jsonl(p, experiment_rows())
    assert main([str(p), "--baseline", "round_robin", "--metric", "solved", "--replicates", "2000"]) == 0
    out = capsys.readouterr().out
    assert "### heterogeneous" in out and "### homogeneous" in out
    het = next(line for line in out.splitlines() if line.startswith("| posterior") and "[3, 3]" in line)
    assert "| 20 | 0 |" in het
    hom = [line for line in out.splitlines() if line.startswith("| posterior") and "[0, 0]" in line]
    assert len(hom) == 1
