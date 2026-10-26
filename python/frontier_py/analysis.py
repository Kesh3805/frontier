"""Paired cluster bootstrap and exact sign test for arm comparisons.

    python -m frontier_py.analysis results.jsonl --baseline round_robin --metric solved

A cluster is the unit of pairing (for experiment JSONL: one (regime, seed)
pair, i.e. one environment draw run under every policy). Several records for
the same (cluster, arm) are averaged first. Clusters missing either arm are
excluded and counted; records whose metric is null are dropped and counted,
which makes conditional metrics such as `time_to_first_solve` comparisons
among clusters where both arms produced a value, not unconditional ones.

CI: percentile bootstrap over clusters (resampled with replacement) of the
mean paired difference A - B, default 10000 replicates and
`numpy.random.default_rng(26102026)`.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_SEED = 26102026
DEFAULT_REPLICATES = 10_000


@dataclass(frozen=True)
class Record:
    cluster_id: Hashable
    arm: str
    value: float


@dataclass(frozen=True)
class PairedComparison:
    arm_a: str
    arm_b: str
    n_clusters: int
    n_excluded: int
    mean_a: float
    mean_b: float
    diff: float
    ci_low: float
    ci_high: float
    rel_diff: float | None
    a_gt_b: int
    a_lt_b: int
    ties: int
    sign_p: float
    replicates: int
    seed: int


def sign_test_p(pos: int, neg: int) -> float:
    """Two-sided exact binomial sign test (ties already removed)."""
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(math.comb(n, i) for i in range(k + 1))
    return min(1.0, 2 * tail / 2**n)


def _cluster_means(records: Iterable[Record | Mapping[str, Any]]) -> dict[Hashable, dict[str, float]]:
    acc: dict[Hashable, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        c, arm, v = (r.cluster_id, r.arm, r.value) if isinstance(r, Record) else (r["cluster_id"], r["arm"], r["value"])
        acc[c][arm].append(float(v))
    return {c: {a: float(np.mean(vs)) for a, vs in arms.items()} for c, arms in acc.items()}


def paired_bootstrap(
    records: Iterable[Record | Mapping[str, Any]],
    arm_a: str,
    arm_b: str,
    *,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
    level: float = 0.95,
) -> PairedComparison:
    """Compare arm A against arm B over clusters that contain both."""
    means = _cluster_means(records)
    keys = sorted((c for c, arms in means.items() if arm_a in arms and arm_b in arms), key=repr)
    excluded = sum(1 for arms in means.values() if arm_a in arms or arm_b in arms) - len(keys)
    if not keys:
        raise ValueError(f"no cluster has both {arm_a!r} and {arm_b!r}")
    a = np.array([means[c][arm_a] for c in keys])
    b = np.array([means[c][arm_b] for c in keys])
    d = a - b
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(replicates, len(d)))
    boot = d[idx].mean(axis=1)
    alpha = (1 - level) / 2
    lo, hi = np.quantile(boot, [alpha, 1 - alpha])
    mean_b = float(b.mean())
    diff = float(d.mean())
    pos, neg = int((d > 0).sum()), int((d < 0).sum())
    return PairedComparison(
        arm_a=arm_a,
        arm_b=arm_b,
        n_clusters=len(keys),
        n_excluded=excluded,
        mean_a=float(a.mean()),
        mean_b=mean_b,
        diff=diff,
        ci_low=float(lo),
        ci_high=float(hi),
        rel_diff=diff / mean_b if mean_b != 0 else None,
        a_gt_b=pos,
        a_lt_b=neg,
        ties=len(d) - pos - neg,
        sign_p=sign_test_p(pos, neg),
        replicates=replicates,
        seed=seed,
    )


def load_jsonl(
    path: str | Path,
    metric: str,
    *,
    arm_field: str = "policy",
    cluster_fields: Sequence[str] = ("regime", "seed"),
    group_field: str | None = "regime",
) -> tuple[dict[Any, list[Record]], int]:
    """Read experiment JSONL into Records grouped by `group_field`.

    Booleans become 0/1. Returns (groups, number of records dropped for a
    null/missing metric). Non-numeric metric values raise ValueError.
    """
    groups: dict[Any, list[Record]] = defaultdict(list)
    dropped = 0
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            v = row.get(metric)
            if v is None:
                dropped += 1
                continue
            if not isinstance(v, (int, float)):
                raise ValueError(f"line {lineno}: metric {metric!r} is not numeric: {v!r}")
            cluster = tuple(row[k] for k in cluster_fields)
            groups[row[group_field] if group_field else None].append(Record(cluster, str(row[arm_field]), float(v)))
    return dict(groups), dropped


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.4g}"


def markdown_report(groups: Mapping[Any, list[Record]], baseline: str, metric: str, **kw: Any) -> str:
    out: list[str] = []
    for group in sorted(groups, key=repr):
        recs = groups[group]
        arms = sorted({r.arm for r in recs} - {baseline})
        out += [
            f"### {group}: {metric}, policy vs {baseline}",
            "",
            "| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        if not any(r.arm == baseline for r in recs):
            out += [f"| (baseline {baseline!r} absent) | | | | | | | | | |", ""]
            continue
        for arm in arms:
            try:
                c = paired_bootstrap(recs, arm, baseline, **kw)
            except ValueError:
                out.append(f"| {arm} | 0 | | | | | | | | |")
                continue
            out.append(
                f"| {arm} | {c.n_clusters} | {c.n_excluded} | {_fmt(c.mean_a)} | {_fmt(c.mean_b)} | {_fmt(c.diff)} "
                f"| [{_fmt(c.ci_low)}, {_fmt(c.ci_high)}] | {_fmt(c.rel_diff)} | {c.a_gt_b} / {c.a_lt_b} / {c.ties} | {c.sign_p:.4g} |"
            )
        out.append("")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m frontier_py.analysis", description=__doc__.split("\n\n")[0])
    p.add_argument("results", type=Path)
    p.add_argument("--baseline", required=True)
    p.add_argument("--metric", required=True)
    p.add_argument("--arm-field", default="policy")
    p.add_argument("--cluster-by", default="regime,seed", help="comma-separated fields")
    p.add_argument("--group-by", default="regime")
    p.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    a = p.parse_args(argv)
    groups, dropped = load_jsonl(
        a.results, a.metric, arm_field=a.arm_field, cluster_fields=a.cluster_by.split(","), group_field=a.group_by or None
    )
    print(markdown_report(groups, a.baseline, a.metric, replicates=a.replicates, seed=a.seed))
    print(f"Paired cluster bootstrap, {a.replicates} replicates, seed {a.seed}; clusters = ({a.cluster_by}).")
    if dropped:
        print(f"{dropped} record(s) with null {a.metric!r} dropped before pairing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
