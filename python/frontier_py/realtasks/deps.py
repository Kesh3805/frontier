"""Dependency-structured real tasks (catalog v3).

Each problem asks for one goal function `f(xs)` over a list of ints and can
be solved by any of its alternative approaches:

* **direct**: one terminal task, searched with the plain DSL;
* **via lemmas**: one or more lemma tasks, each a verifiable helper function
  with its own reference and frozen hidden suite, then a terminal task whose
  programs must call the verified helpers (`h_<lemma>(...)`). A lemma may
  itself depend on another lemma (a chain), and approaches of one problem
  may share a lemma (the task graph merges it by signature).

Every task is verified on its own frozen hidden suite (suite v2 style:
every list over {-2..2} of length <= 3, then 40 random cases). Visible
examples are six inputs (`VISIBLE`), more than v1's three, so that search
on lemmas is not dominated by programs that overfit the examples. Labels
are ground truth kept from policies:

* `solvable`: a program in the worker's grammar passes the suite (tests hold
  a witness). How hard it is to find is what calibration measures.
* `trap`: a lemma-route goal whose helper is useless for the goal; only a
  degenerate program that cancels the helper out can pass. Live, near zero.
* `inexpressible`: no program in the worker's grammar (with the route's
  helpers, assumed correct) reproduces the reference on the suite's
  exhaustive inputs; checked by `expressible.py`. Dead for this worker.
* `misspecified`: hidden tests check a different function than the
  statement and visible examples describe. Dead for every worker.

Problem labels: `lemma_useful` (direct route hard or dead, lemma route
easy), `direct_easy` (both routes live, the lemmas cost extra),
`trap` (a lemma that verifies but does not help), `dead` (no route can
succeed, sometimes behind verifiable lemmas).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..tasks import TaskDef
from .dsl import Kind
from .suite import GENERATORS, RealTask, _mode, _prefix, _product, _second_largest, _stable_hash

DEAD_V3: frozenset[str] = frozenset({"inexpressible", "misspecified"})
DEFAULT_SUITE = "2"
VISIBLE: tuple[list[int], ...] = ([3, -1, 2], [4, 4, -6, 1], [0, 7], [-5, 2, -2, 0, 9], [8, 3, -1, 5, 2], [])


@dataclass(frozen=True)
class DepTask(RealTask):
    """A task of a v3 problem. `deps` are worker names of direct prerequisites."""

    problem: str = ""
    role: str = "direct"  # "direct" | "lemma" | "via"
    deps: tuple[str, ...] = ()
    helper: str | None = None  # call name when this task is a lemma
    # Hand-written lemma program: the in-grammar witness of a live lemma, or a
    # plain reference for a dead one. Used by tests, and by calibration as the
    # library entry when no calibration attempt was correct; never by runs.
    ref_source: str | None = None

    def task_def(self, version: str = DEFAULT_SUITE) -> TaskDef:
        return TaskDef(
            name=f"deps/{self.name}",
            version=version,
            function_name="f",
            statement=self.statement,
            reference=self.reference,
            generate=GENERATORS[version],
            visible=tuple(([xs], out) for xs, out in self.visible),
            per_call_timeout_s=2.0,
            wall_timeout_s=20.0,
        )


@dataclass(frozen=True)
class Lemma:
    name: str
    kind: Kind
    statement: str
    ref: Callable[[list[int]], Any]
    status: str = "solvable"
    deps: tuple[str, ...] = ()  # other lemmas of the same problem
    ref_source: str | None = None


@dataclass(frozen=True)
class Route:
    uses: tuple[str, ...]  # lemmas the goal calls directly
    status: str


@dataclass(frozen=True)
class DepProblem:
    pid: str
    label: str
    kind: Kind
    statement: str
    ref: Callable[[list[int]], Any]
    direct: str  # status of the direct route
    lemmas: tuple[Lemma, ...] = ()
    routes: tuple[Route, ...] = ()
    visible_ref: Callable[[list[int]], Any] | None = None  # misspecified: what the examples show
    tasks: tuple[DepTask, ...] = field(default=(), compare=False)

    def lemma(self, name: str) -> Lemma:
        return next(lm for lm in self.lemmas if lm.name == name)

    def closure(self, uses: tuple[str, ...]) -> list[str]:
        """Lemmas a route needs, prerequisites first."""
        out: list[str] = []

        def visit(n: str) -> None:
            if n in out:
                return
            for d in self.lemma(n).deps:
                visit(d)
            out.append(n)

        for u in uses:
            visit(u)
        return out


def task_name(pid: str, part: str) -> str:
    return f"{pid}/{part}"


def via_part(route: Route) -> str:
    return "via_" + "+".join(sorted(route.uses))


def helper_name(lemma: str) -> str:
    return f"h_{lemma}"


def _vis(ref: Callable[[list[int]], Any]) -> tuple[tuple[list[int], Any], ...]:
    return tuple((list(xs), ref(list(xs))) for xs in VISIBLE)


def _make_tasks(p: DepProblem) -> tuple[DepTask, ...]:
    vref = p.visible_ref or p.ref
    out = [DepTask(task_name(p.pid, "direct"), p.direct, p.kind, p.statement, p.ref, _vis(vref), problem=p.pid, role="direct")]
    for lm in p.lemmas:
        out.append(DepTask(task_name(p.pid, lm.name), lm.status, lm.kind, lm.statement, lm.ref, _vis(lm.ref), problem=p.pid,
                           role="lemma", deps=tuple(task_name(p.pid, d) for d in lm.deps), helper=helper_name(lm.name),
                           ref_source=lm.ref_source))
    for r in p.routes:
        out.append(DepTask(task_name(p.pid, via_part(r)), r.status, p.kind, p.statement, p.ref, _vis(vref), problem=p.pid, role="via",
                           deps=tuple(task_name(p.pid, u) for u in sorted(r.uses))))
    return tuple(out)


# --- lemma vocabulary --------------------------------------------------------

def _max0(xs: list[int]) -> int:
    return max(xs, default=0)


def _min0(xs: list[int]) -> int:
    return min(xs, default=0)


def _pos(xs: list[int]) -> list[int]:
    return [x for x in xs if x > 0]


def _neg(xs: list[int]) -> list[int]:
    return [x for x in xs if x < 0]


def _dedupe(xs: list[int]) -> list[int]:
    return sorted(set(xs))


DEDUPE_SOURCE = (
    "def f(xs):\n"
    "    out = []\n"
    "    for x in sorted(xs):\n"
    "        if not out or out[-1] != x:\n"
    "            out.append(x)\n"
    "    return out\n"
)


# In-grammar programs for every live lemma (tests check them against the
# hidden suites). A lemma-dependent witness calls its prerequisites' helpers.
WITNESS: dict[str, str] = {
    "positives": "[x for x in xs if x>0]",
    "negatives": "[x for x in xs if x<0]",
    "evens": "[x for x in xs if x%2==0]",
    "abs_all": "[abs(x) for x in xs]",
    "sort": "sorted(xs)",
    "maxpos": "max([x for x in xs if x>0], default=0)",
    "minpos": "min([x for x in xs if x>0], default=0)",
    "minneg": "min([x for x in xs if x<0], default=0)",
    "max0": "max(xs, default=0)",
    "min0": "min(xs, default=0)",
    "count": "len(xs)",
    "sum": "sum(xs)",
    "count_pos": "len([x for x in xs if x>0])",
    "count_neg": "len([x for x in xs if x<0])",
    "sum_even": "sum([x for x in xs if x%2==0])",
    "sum_odd": "sum([x for x in xs if x%2==1])",
    "sum_squares": "sum([x*x for x in xs])",
    "sum_abs": "sum([abs(x) for x in xs])",
    "trim": "sorted(xs)[1:][:-1]",
    "drop_min": "sorted(xs)[1:]",
    "drop_max": "sorted(xs)[:-1]",
    "second_max": "max(sorted(xs)[:-1], default=0)",
    "sq_pos": "[x*x for x in h_positives(xs)]",
    "pos_drop_min": "sorted(h_positives(xs))[1:]",
}


def L(name: str, kind: Kind, statement: str, ref: Callable[[list[int]], Any], **kw: Any) -> Lemma:
    if name in WITNESS:
        kw.setdefault("ref_source", f"def f(xs):\n    return {WITNESS[name]}\n")
    return Lemma(name, kind, statement, ref, **kw)


POSITIVES = L("positives", "list", "The positive elements, in order.", _pos)
NEGATIVES = L("negatives", "list", "The negative elements, in order.", _neg)
EVENS = L("evens", "list", "The even elements, in order.", lambda xs: [x for x in xs if x % 2 == 0])
ABS_ALL = L("abs_all", "list", "Absolute value of every element.", lambda xs: [abs(x) for x in xs])
SORT = L("sort", "list", "The list sorted ascending.", sorted)
MAXPOS = L("maxpos", "int", "Largest positive element, or 0 if none.", lambda xs: _max0(_pos(xs)))
MINPOS = L("minpos", "int", "Smallest positive element, or 0 if none.", lambda xs: _min0(_pos(xs)))
MINNEG = L("minneg", "int", "Smallest negative element, or 0 if none.", lambda xs: _min0(_neg(xs)))
MAX0 = L("max0", "int", "Largest element, or 0 if empty.", _max0)
MIN0 = L("min0", "int", "Smallest element, or 0 if empty.", _min0)
COUNT = L("count", "int", "Number of elements.", len)
SUM = L("sum", "int", "Sum of the elements.", sum)
COUNT_POS = L("count_pos", "int", "Number of positive elements.", lambda xs: len(_pos(xs)))
COUNT_NEG = L("count_neg", "int", "Number of negative elements.", lambda xs: len(_neg(xs)))
SUM_EVEN = L("sum_even", "int", "Sum of the even elements.", lambda xs: sum(x for x in xs if x % 2 == 0))
SUM_ODD = L("sum_odd", "int", "Sum of the odd elements.", lambda xs: sum(x for x in xs if x % 2 == 1))
SUM_SQUARES = L("sum_squares", "int", "Sum of squares.", lambda xs: sum(x * x for x in xs))
SUM_ABS = L("sum_abs", "int", "Sum of absolute values.", lambda xs: sum(abs(x) for x in xs))
TRIM = L("trim", "list", "The sorted list without its smallest and largest element.", lambda xs: sorted(xs)[1:][:-1])
DROP_MIN = L("drop_min", "list", "The sorted list without its smallest element.", lambda xs: sorted(xs)[1:])
DROP_MAX = L("drop_max", "list", "The sorted list without its largest element.", lambda xs: sorted(xs)[:-1])
SECOND_MAX = L("second_max", "int", "Largest element after removing one copy of the maximum (0 if fewer than 2).",
               lambda xs: _max0(sorted(xs)[:-1]))
SQ_POS = L("sq_pos", "list", "Squares of the positive elements, in order.", lambda xs: [x * x for x in _pos(xs)], deps=("positives",))
POS_DROP_MIN = L("pos_drop_min", "list", "The positive elements sorted ascending, without the smallest.",
                 lambda xs: sorted(_pos(xs))[1:], deps=("positives",))
DEDUPE = L("dedupe_sorted", "list", "Distinct elements, ascending.", _dedupe, status="inexpressible", ref_source=DEDUPE_SOURCE)


def _span(xs: list[int]) -> int:
    return _max0(xs) - _min0(xs)


def _noisy_span(xs: list[int]) -> int:
    return _span(xs) + (_stable_hash(xs) % 3 if len(xs) > 6 else 0)


def P(pid: str, label: str, kind: Kind, statement: str, ref: Callable[[list[int]], Any], direct: str,
      lemmas: tuple[Lemma, ...] = (), routes: tuple[Route, ...] = (), visible_ref: Callable[[list[int]], Any] | None = None) -> DepProblem:
    p = DepProblem(pid, label, kind, statement, ref, direct, lemmas, routes, visible_ref)
    return DepProblem(pid, label, kind, statement, ref, direct, lemmas, routes, visible_ref, _make_tasks(p))


R = Route

PROBLEMS: tuple[DepProblem, ...] = (
    # Lemma route useful: the direct program is deep (rare or out of reach),
    # the goal is a one-line combination of verified helpers.
    P("span_pos", "lemma_useful", "int", "Largest minus smallest positive element (0 if none).",
      lambda xs: _max0(_pos(xs)) - _min0(_pos(xs)), "solvable",
      (MAXPOS, MINPOS, POSITIVES), (R(("maxpos", "minpos"), "solvable"), R(("positives",), "solvable"))),
    P("span_neg", "lemma_useful", "int", "Largest minus smallest negative element (0 if none).",
      lambda xs: _max0(_neg(xs)) - _min0(_neg(xs)), "solvable", (NEGATIVES,), (R(("negatives",), "solvable"),)),
    P("span_abs", "lemma_useful", "int", "Largest minus smallest absolute value (0 if empty).",
      lambda xs: _max0([abs(x) for x in xs]) - _min0([abs(x) for x in xs]), "solvable", (ABS_ALL,), (R(("abs_all",), "solvable"),)),
    P("trimmed_sum", "lemma_useful", "int", "Sum of the elements without one smallest and one largest (0 if fewer than 3).",
      lambda xs: sum(sorted(xs)[1:][:-1]), "inexpressible", (TRIM,), (R(("trim",), "solvable"),)),
    P("max_times_min", "lemma_useful", "int", "Largest element times smallest element (0 if empty).",
      lambda xs: _max0(xs) * _min0(xs), "solvable", (MAX0, MIN0), (R(("max0", "min0"), "solvable"),)),
    P("sign_balance", "lemma_useful", "int", "Number of positive minus number of negative elements.",
      lambda xs: len(_pos(xs)) - len(_neg(xs)), "solvable", (COUNT_POS, COUNT_NEG), (R(("count_neg", "count_pos"), "solvable"),)),
    P("parity_gap", "lemma_useful", "int", "Sum of the even elements minus sum of the odd elements.",
      lambda xs: sum(x for x in xs if x % 2 == 0) - sum(x for x in xs if x % 2 == 1), "solvable",
      (SUM_EVEN, SUM_ODD), (R(("sum_even", "sum_odd"), "solvable"),)),
    P("energy_gap", "lemma_useful", "int", "Sum of squares minus sum of absolute values.",
      lambda xs: sum(x * x for x in xs) - sum(abs(x) for x in xs), "solvable", (SUM_SQUARES, SUM_ABS), (R(("sum_abs", "sum_squares"), "solvable"),)),
    P("extremes_pos_neg", "lemma_useful", "int", "Largest positive plus smallest negative element (each 0 if none).",
      lambda xs: _max0(_pos(xs)) + _min0(_neg(xs)), "solvable", (MAXPOS, MINNEG), (R(("maxpos", "minneg"), "solvable"),)),
    # Two routes sharing the lemma max0 (merged by signature in the task graph).
    P("top_two_sum", "lemma_useful", "int", "Largest element plus the largest of the rest (0 for missing ones).",
      lambda xs: _max0(xs) + _max0(sorted(xs)[:-1]), "inexpressible",
      (MAX0, SECOND_MAX, DROP_MAX), (R(("max0", "second_max"), "solvable"), R(("drop_max", "max0"), "solvable"))),
    # Chains: lemma -> lemma -> goal.
    P("trimmed_pos_sum", "lemma_useful", "int", "Sum of the positive elements without the smallest and largest positive.",
      lambda xs: sum(sorted(_pos(xs))[1:][:-1]), "inexpressible",
      (POSITIVES, POS_DROP_MIN), (R(("pos_drop_min",), "solvable"), R(("positives",), "inexpressible"))),
    P("span_sq_pos", "lemma_useful", "int", "Largest minus smallest square of a positive element (0 if none).",
      lambda xs: _max0([x * x for x in _pos(xs)]) - _min0([x * x for x in _pos(xs)]), "solvable",
      (POSITIVES, SQ_POS), (R(("sq_pos",), "solvable"),)),
    # Direct route easy; the lemma route works too but costs an extra task.
    P("sum_pos", "direct_easy", "int", "Sum of the positive elements.", lambda xs: sum(_pos(xs)), "solvable",
      (POSITIVES,), (R(("positives",), "solvable"),)),
    P("count_even", "direct_easy", "int", "Number of even elements.", lambda xs: sum(1 for x in xs if x % 2 == 0), "solvable",
      (EVENS,), (R(("evens",), "solvable"),)),
    P("second_smallest", "direct_easy", "int", "Smallest element after removing one copy of the minimum (0 if fewer than 2).",
      lambda xs: (sorted(xs)[1:] or [0])[0], "solvable", (DROP_MIN,), (R(("drop_min",), "solvable"),)),
    P("second_max", "direct_easy", "int", "Largest element after removing one copy of the maximum (0 if fewer than 2).",
      lambda xs: _max0(sorted(xs)[:-1]), "solvable", (DROP_MAX,), (R(("drop_max",), "solvable"),)),
    # Traps: the lemma verifies but does not help with the goal.
    P("sum_even_trap", "trap", "int", "Sum of the even elements.", lambda xs: sum(x for x in xs if x % 2 == 0), "solvable",
      (COUNT_POS,), (R(("count_pos",), "trap"),)),
    P("span_trap", "trap", "int", "Largest minus smallest element (0 if empty).", _span, "solvable", (SUM,), (R(("sum",), "trap"),)),
    P("sort_desc_trap", "trap", "list", "The list sorted descending.", lambda xs: sorted(xs)[::-1], "solvable",
      (COUNT,), (R(("count",), "inexpressible"),)),
    # Dead goals, some behind lemmas that do verify.
    P("product_abs", "dead", "int", "Product of the elements (1 if empty).", _product, "inexpressible",
      (ABS_ALL,), (R(("abs_all",), "inexpressible"),)),
    P("second_distinct", "dead", "int", "Second largest distinct element, or 0.", _second_largest, "inexpressible",
      (DEDUPE,), (R(("dedupe_sorted",), "solvable"),)),
    P("mode_sorted", "dead", "int", "Most frequent element (smallest on ties), or 0.", _mode, "inexpressible",
      (SORT,), (R(("sort",), "inexpressible"),)),
    P("prefix_pos", "dead", "list", "Running sums.", _prefix, "inexpressible", (POSITIVES,), (R(("positives",), "inexpressible"),)),
    P("noisy_span", "dead", "int", "Largest minus smallest element (0 if empty).", _noisy_span, "misspecified",
      (MAX0, MIN0), (R(("max0", "min0"), "misspecified"),), visible_ref=_span),
)

TASKS: tuple[DepTask, ...] = tuple(t for p in PROBLEMS for t in p.tasks)
BY_NAME: dict[str, DepTask] = {t.name: t for t in TASKS}
PROBLEM_OF: dict[str, DepProblem] = {p.pid: p for p in PROBLEMS}


def library_kinds(task: DepTask) -> dict[str, Kind]:
    """Helper name -> return kind for the task's direct prerequisites."""
    return {BY_NAME[d].helper or "": BY_NAME[d].kind for d in task.deps}
