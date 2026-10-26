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
    """Compile a DSL program produced by `sample_program` (trusted input only)."""
    scope: dict = {}
    exec(compile(source, "<dsl>", "exec"), {"__builtins__": {"sorted": sorted, "sum": sum, "len": len, "max": max, "min": min, "abs": abs}}, scope)
    return scope["f"]
