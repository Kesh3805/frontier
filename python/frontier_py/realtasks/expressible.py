"""Exhaustive expressibility check for the worker's grammar (labels for v3).

A task is dead for the DSL worker if no program the sampler can produce
reproduces the reference on the frozen hidden suite. Every suite-v2 hidden
suite contains all 156 lists over {-2..2} of length <= 3, so it suffices to
show that no program matches the reference on those inputs.

Programs are enumerated by *semantic class*: two expressions that agree on
every probe input are interchangeable inside any larger expression, so each
grammar level keeps one representative per fingerprint (the vector of its
outputs on the probe inputs). The levels mirror `dsl.gen_list`/`gen_int`
(depth 3) and, with a library, `dsl.gen_list_h`/`gen_int_h`, including the
rule that a lemma-route program must call at least one helper. Helpers are
evaluated with their *reference* semantics, i.e. assuming the verified
lemma is correct on the derived lists it is applied to.

A True result is not a proof of solvability on the full hidden suite (the
probe set is a subset); tests hold explicit witnesses for live labels.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from .dsl import CONSTS, MAPS, PREDS

SMALL: tuple[tuple[int, ...], ...] = tuple(t for n in range(4) for t in itertools.product(range(-2, 3), repeat=n))

_MAP: dict[str, Callable[[int], int]] = {
    "x": lambda x: x, "x*x": lambda x: x * x, "x+1": lambda x: x + 1, "x-1": lambda x: x - 1, "-x": lambda x: -x,
    "abs(x)": abs, "2*x": lambda x: 2 * x, "x%2": lambda x: x % 2, "x//2": lambda x: x // 2,
}
_PRED: dict[str, Callable[[int], bool]] = {
    "x>0": lambda x: x > 0, "x<0": lambda x: x < 0, "x%2==0": lambda x: x % 2 == 0, "x%2==1": lambda x: x % 2 == 1,
    "x!=0": lambda x: x != 0, "x>1": lambda x: x > 1,
}
assert tuple(_MAP) == MAPS and tuple(_PRED) == PREDS

LFP = tuple[tuple[int, ...], ...]  # list output per probe input
IFP = tuple[int, ...]  # int output per probe input
Classes = dict[Any, set[bool]]  # fingerprint -> helper-use flags seen


def _list_ops() -> list[Callable[[tuple[int, ...]], tuple[int, ...]]]:
    ops: list[Callable[[tuple[int, ...]], tuple[int, ...]]] = [lambda v: tuple(sorted(v)), lambda v: v[::-1]]
    for m in _MAP.values():
        ops.append(lambda v, m=m: tuple(m(x) for x in v))
    for p in _PRED.values():
        ops.append(lambda v, p=p: tuple(x for x in v if p(x)))
    for m in _MAP.values():
        for p in _PRED.values():
            ops.append(lambda v, m=m, p=p: tuple(m(x) for x in v if p(x)))
    ops += [lambda v: v[1:], lambda v: v[:-1]]
    return ops


LIST_OPS = _list_ops()
AGGS: list[Callable[[tuple[int, ...]], int]] = [sum, len, lambda v: max(v, default=0), lambda v: min(v, default=0),
                                                lambda v: v[0] if v else 0]


def _add(cs: Classes, fp: Any, used: bool) -> None:
    cs.setdefault(fp, set()).add(used)


def _items(cs: Classes) -> Iterable[tuple[Any, bool]]:
    for fp, flags in cs.items():
        for u in flags:
            yield fp, u


class Grammar:
    def __init__(self, list_helpers: dict[str, Callable] | None = None, int_helpers: dict[str, Callable] | None = None):
        self.lh = list(list_helpers.values()) if list_helpers else []
        self.ih = list(int_helpers.values()) if int_helpers else []
        self._lists: dict[int, Classes] = {}
        self._ints: dict[int, Classes] = {}

    def _hl(self, h: Callable, fp: LFP) -> LFP:
        return tuple(tuple(h(list(v))) for v in fp)

    def _hi(self, h: Callable, fp: LFP) -> IFP:
        return tuple(int(h(list(v))) for v in fp)

    def lists(self, d: int) -> Classes:
        if d in self._lists:
            return self._lists[d]
        xs: LFP = SMALL
        cs: Classes = {}
        _add(cs, xs, False)
        for h in self.lh:
            _add(cs, self._hl(h, xs), True)
        if d > 0:
            for fp, u in list(_items(self.lists(d - 1))):
                for op in LIST_OPS:
                    _add(cs, tuple(op(v) for v in fp), u)
                for h in self.lh:
                    _add(cs, self._hl(h, fp), True)
        self._lists[d] = cs
        return cs

    def ints(self, d: int) -> Classes:
        if d in self._ints:
            return self._ints[d]
        cs: Classes = {}
        for c in CONSTS:
            _add(cs, (int(c),) * len(SMALL), False)
        for h in self.ih:
            _add(cs, self._hi(h, SMALL), True)
        if d > 0:
            for fp, u in _items(self.lists(d - 1)):
                for agg in AGGS:
                    _add(cs, tuple(agg(v) for v in fp), u)
                for h in self.ih:
                    _add(cs, self._hi(h, fp), True)
            prev = list(_items(self.ints(d - 1)))
            for (a, ua), (b, ub) in itertools.product(prev, prev):
                _add(cs, tuple(x + y for x, y in zip(a, b)), ua or ub)
                _add(cs, tuple(x - y for x, y in zip(a, b)), ua or ub)
                _add(cs, tuple(x * y for x, y in zip(a, b)), ua or ub)
        self._ints[d] = cs
        return cs

    def int_reachable(self, target: IFP, need_helper: bool, depth: int = 3) -> bool:
        """Is `target` produced by some depth-`depth` int program (calling a
        helper if `need_helper`)? The top-level binary operations are checked
        without materialising all pairs."""
        ok = (lambda u: u) if need_helper else (lambda u: True)
        t = tuple(target)
        if any(t == (int(c),) * len(SMALL) for c in CONSTS) and not need_helper:
            return True
        if self.ih and t in {self._hi(h, SMALL) for h in self.ih}:
            return True
        for fp, u in _items(self.lists(depth - 1)):
            if any(tuple(agg(v) for v in fp) == t for agg in AGGS) and ok(u):
                return True
            if any(self._hi(h, fp) == t for h in self.ih):
                return True
        prev = self.ints(depth - 1)
        tv = np.array(t, dtype=np.int64)
        for a, flags in prev.items():
            for ua in flags:
                av = np.array(a, dtype=np.int64)
                for b in (tuple((tv - av).tolist()), tuple((av - tv).tolist())):  # a + b = t, a - b = t
                    if b in prev and any(ok(ua or ub) for ub in prev[b]):
                        return True
        keys = list(prev)
        mat = np.array(keys, dtype=np.int64)
        used_any = np.array([True in prev[k] for k in keys])
        free_any = np.array([False in prev[k] for k in keys])
        for i, a in enumerate(keys):
            hit = np.all(mat * mat[i] == tv, axis=1)
            if not hit.any():
                continue
            if not need_helper:
                return True
            if used_any[i] and (used_any[hit].any() or free_any[hit].any()):
                return True
            if used_any[hit].any():
                return True
        return False

    def list_reachable(self, target: LFP, need_helper: bool, depth: int = 3) -> bool:
        t = tuple(tuple(v) for v in target)
        cs = self.lists(depth - 1)
        if t == SMALL and not need_helper:
            return True
        if any(self._hl(h, SMALL) == t for h in self.lh):
            return True
        for fp, u in _items(cs):
            if not need_helper or u:
                for op in LIST_OPS:
                    if tuple(op(v) for v in fp) == t:
                        return True
            for h in self.lh:
                if self._hl(h, fp) == t:
                    return True
        return False


def fingerprint(ref: Callable[[list[int]], Any]) -> tuple[Any, ...]:
    out = []
    for v in SMALL:
        r = ref(list(v))
        out.append(tuple(r) if isinstance(r, list) else int(r))
    return tuple(out)


def expressible(kind: str, ref: Callable[[list[int]], Any], helpers: dict[str, tuple[str, Callable]] | None = None) -> bool:
    """`helpers`: name -> (kind, reference). With helpers, a program must call one."""
    helpers = helpers or {}
    g = Grammar({n: f for n, (k, f) in helpers.items() if k == "list"}, {n: f for n, (k, f) in helpers.items() if k == "int"})
    fp = fingerprint(ref)
    need = bool(helpers)
    return g.list_reachable(fp, need) if kind == "list" else g.int_reachable(fp, need)
