"""A small list-processing DSL and a seeded program sampler.

Programs are single expressions over `xs` (a list of ints) returning an int
or a list of ints, rendered as Python source `def f(xs): return <expr>`.
The sampler is the search space of the deterministic worker: what it can
express decides which tasks are solvable for it.

Programs come from this trusted generator, so the worker may evaluate them
in-process against visible examples. The verifier still treats every
submitted program as untrusted and runs it in a separate interpreter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

Kind = Literal["int", "list"]

MAPS = ("x", "x*x", "x+1", "x-1", "-x", "abs(x)", "2*x", "x%2", "x//2")
PREDS = ("x>0", "x<0", "x%2==0", "x%2==1", "x!=0", "x>1")
CONSTS = ("0", "1", "2")


def gen_list(rng: random.Random, depth: int) -> str:
    if depth <= 0 or rng.random() < 0.3:
        return "xs"
    inner = gen_list(rng, depth - 1)
    r = rng.randrange(7)
    if r == 0:
        return f"sorted({inner})"
    if r == 1:
        return f"{inner}[::-1]"
    if r == 2:
        return f"[{rng.choice(MAPS)} for x in {inner}]"
    if r == 3:
        return f"[x for x in {inner} if {rng.choice(PREDS)}]"
    if r == 4:
        return f"[{rng.choice(MAPS)} for x in {inner} if {rng.choice(PREDS)}]"
    if r == 5:
        return f"{inner}[1:]"
    return f"{inner}[:-1]"


def gen_int(rng: random.Random, depth: int) -> str:
    if depth <= 0:
        return rng.choice(CONSTS)
    r = rng.randrange(9)
    lst = gen_list(rng, depth - 1)
    if r == 0:
        return f"sum({lst})"
    if r == 1:
        return f"len({lst})"
    if r == 2:
        return f"max({lst}, default=0)"
    if r == 3:
        return f"min({lst}, default=0)"
    if r == 4:
        return f"({lst}[0] if {lst} else 0)"
    if r == 5:
        return f"({gen_int(rng, depth - 1)} + {gen_int(rng, depth - 1)})"
    if r == 6:
        return f"({gen_int(rng, depth - 1)} - {gen_int(rng, depth - 1)})"
    if r == 7:
        return f"({gen_int(rng, depth - 1)} * {gen_int(rng, depth - 1)})"
    return rng.choice(CONSTS)


def sample_program(rng: random.Random, kind: Kind, depth: int = 3) -> str:
    expr = gen_int(rng, depth) if kind == "int" else gen_list(rng, depth)
    return f"def f(xs):\n    return {expr}\n"


def compile_program(source: str):
    """Compile a DSL program produced by `sample_program` (trusted input only).

    One namespace serves as globals and locals, so a composed program's
    candidate can call the library helpers defined before it."""
    scope: dict = {"__builtins__": {"sorted": sorted, "sum": sum, "len": len, "max": max, "min": min, "abs": abs}}
    exec(compile(source, "<dsl>", "exec"), scope)
    return scope["f"]


# --- Library helpers (catalog v3) -------------------------------------------
#
# A task that depends on verified lemmas receives them as a library of helper
# functions `h_<lemma>(xs)`. The sampler below extends the grammar with calls
# to them. It is used only when a library is present, so programs sampled for
# tasks without dependencies (catalog v1/v2) are unchanged.

HELPER_CALL_P = 0.5  # chance that an int node becomes a helper call
HELPER_ARG_XS_P = 0.6  # chance that a helper is applied to xs itself


@dataclass(frozen=True)
class Helpers:
    ints: tuple[str, ...] = ()
    lists: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.ints + self.lists))


def _helper_arg(rng: random.Random, depth: int, h: Helpers) -> str:
    return "xs" if depth <= 0 or rng.random() < HELPER_ARG_XS_P else gen_list_h(rng, depth - 1, h)


def gen_list_h(rng: random.Random, depth: int, h: Helpers) -> str:
    if h.lists and rng.random() < HELPER_CALL_P * (0.5 if depth > 0 else 1.0):
        return f"{rng.choice(h.lists)}({_helper_arg(rng, depth, h)})"
    if depth <= 0 or rng.random() < 0.3:
        return "xs"
    inner = gen_list_h(rng, depth - 1, h)
    r = rng.randrange(7)
    if r == 0:
        return f"sorted({inner})"
    if r == 1:
        return f"{inner}[::-1]"
    if r == 2:
        return f"[{rng.choice(MAPS)} for x in {inner}]"
    if r == 3:
        return f"[x for x in {inner} if {rng.choice(PREDS)}]"
    if r == 4:
        return f"[{rng.choice(MAPS)} for x in {inner} if {rng.choice(PREDS)}]"
    if r == 5:
        return f"{inner}[1:]"
    return f"{inner}[:-1]"


def gen_int_h(rng: random.Random, depth: int, h: Helpers) -> str:
    if h.ints and rng.random() < HELPER_CALL_P:
        return f"{rng.choice(h.ints)}({_helper_arg(rng, depth, h)})"
    if depth <= 0:
        return rng.choice(CONSTS)
    r = rng.randrange(9)
    lst = gen_list_h(rng, depth - 1, h)
    if r == 0:
        return f"sum({lst})"
    if r == 1:
        return f"len({lst})"
    if r == 2:
        return f"max({lst}, default=0)"
    if r == 3:
        return f"min({lst}, default=0)"
    if r == 4:
        return f"({lst}[0] if {lst} else 0)"
    if r == 5:
        return f"({gen_int_h(rng, depth - 1, h)} + {gen_int_h(rng, depth - 1, h)})"
    if r == 6:
        return f"({gen_int_h(rng, depth - 1, h)} - {gen_int_h(rng, depth - 1, h)})"
    if r == 7:
        return f"({gen_int_h(rng, depth - 1, h)} * {gen_int_h(rng, depth - 1, h)})"
    return rng.choice(CONSTS)


def sample_program_h(rng: random.Random, kind: Kind, h: Helpers, depth: int = 3) -> str:
    expr = gen_int_h(rng, depth, h) if kind == "int" else gen_list_h(rng, depth, h)
    return f"def f(xs):\n    return {expr}\n"


def uses_helper(source: str, h: Helpers) -> bool:
    return any(f"{n}(" in source for n in h.names)


def compose(library: list[tuple[str, str]] | tuple[tuple[str, str], ...], candidate: str) -> str:
    """The program the verifier runs: each verified helper's source (sorted by
    helper name), its `f` bound to the helper name, then the candidate.
    Mirrors `frontier_sim::real::compose_program` byte for byte."""
    out = []
    for name, src in sorted(library):
        out.append(src if src.endswith("\n") else src + "\n")
        out.append(f"{name} = f\n")
    out.append(candidate)
    return "".join(out)
