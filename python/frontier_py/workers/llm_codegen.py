"""Prompt construction and output parsing for model-written programs.

`build_prompt(task, template_version)` renders what a code-writing model is
shown for one real task: an instruction, the task statement, the visible
examples as `f([..]) == ..` lines, the helper functions a dependent task may
call (name, return type and statement of each verified prerequisite) and
the required signature. It reads only public, visible fields of the task.
Hidden inputs, expected hidden outputs, ground-truth status labels,
difficulty hints and reference implementations never enter a prompt.

`parse_function(text)` turns a model reply into candidate source without
executing anything: the code is taken from the first fenced block that
defines `f` (or the whole reply when there is no fence), parsed with `ast`,
and accepted only if its top level is an optional docstring, imports, and
exactly one plain `def f(xs)` with a single positional parameter. Anything
else becomes `PARSE_FAILURE_STUB`, a program that raises when called, so a
malformed reply is an ordinary failing attempt rather than a crash.
"""

from __future__ import annotations

import ast
import re
import textwrap
from typing import Any

from .transcripts import prompt_sha256  # noqa: F401 - re-exported for pool tooling

DEFAULT_TEMPLATE = "codegen-v1"
TEMPLATE_VERSIONS = (DEFAULT_TEMPLATE,)
MAX_SOURCE_BYTES = 64 << 10
PARSE_FAILURE_STUB = 'def f(xs):\n    raise ValueError("model output did not contain a usable def f(xs)")\n'
# Upper bound on tokens a chat wrapper adds around the prompt (role markers,
# system scaffolding). Worst-case input tokens = prompt UTF-8 bytes + this.
PROMPT_OVERHEAD_TOKENS = 64

_KIND_TEXT = {"int": "an integer", "list": "a list of integers"}
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+-]*)[ \t]*$", re.MULTILINE)


def _fmt(x: Any) -> str:
    return repr(x)


def _helpers(task: Any) -> list[tuple[str, str, str]]:
    """(helper name, return kind, statement) of a dependent task's direct prerequisites."""
    deps = getattr(task, "deps", ())
    if not deps:
        return []
    from ..realtasks import deps as dep_tasks

    out = []
    for d in deps:
        t = dep_tasks.BY_NAME[d]
        out.append((t.helper or "", t.kind, t.statement))
    return sorted(out)


def build_prompt(task: Any, template_version: str = DEFAULT_TEMPLATE) -> str:
    if template_version != DEFAULT_TEMPLATE:
        raise ValueError(f"unknown prompt template {template_version!r}; known: {TEMPLATE_VERSIONS}")
    lines = [
        "Write a Python function `f(xs)` that takes a list of integers `xs` and returns "
        f"{_KIND_TEXT[task.kind]}. Use only the Python standard library; do not read input or print.",
        "",
        f"Task: {task.statement}",
        "",
        "Examples:",
    ]
    lines += [f"f({_fmt(list(xs))}) == {_fmt(want)}" for xs, want in task.visible]
    helpers = _helpers(task)
    if helpers:
        lines += ["", "These verified helper functions are already defined; build on them:"]
        lines += [f"- {name}(xs) returns {_KIND_TEXT[kind]}: {stmt}" for name, kind, stmt in helpers]
    lines += [
        "",
        "Reply with only the function in one ```python code block, starting with:",
        "def f(xs):",
    ]
    return "\n".join(lines) + "\n"


def _code_of(text: str) -> str:
    """The first fenced block defining `f`, else the first fenced block, else the whole text."""
    blocks: list[str] = []
    pos = 0
    while (m := _FENCE.search(text, pos)) is not None:
        fence = m.group(1)
        close = re.compile(rf"^[ \t]*{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", re.MULTILINE)
        end = close.search(text, m.end())
        if end is None:
            blocks.append(text[m.end():])
            break
        blocks.append(text[m.end():end.start()])
        pos = end.end()
    if not blocks:
        return text
    for b in blocks:
        if re.search(r"^\s*def\s+f\s*\(", b, re.MULTILINE):
            return b
    return blocks[0]


def _plain_single_arg(fn: ast.FunctionDef) -> bool:
    a = fn.args
    return (
        not a.posonlyargs and len(a.args) == 1 and a.args[0].arg == "xs"
        and a.vararg is None and a.kwarg is None and not a.kwonlyargs and not a.defaults and not a.kw_defaults
    )


def try_parse(text: str) -> str | None:
    """Candidate source, or None if the reply has no acceptable `def f(xs)`. Never executes code."""
    if not isinstance(text, str) or "\x00" in text or len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        return None
    code = _code_of(text).strip("\n")
    if not code.strip():
        return None
    code = textwrap.dedent(code).rstrip() + "\n"
    try:
        tree = ast.parse(code, mode="exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]  # module docstring
    defs = [n for n in body if isinstance(n, ast.FunctionDef)]
    others = [n for n in body if not isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom))]
    if others or len(defs) != 1:
        return None
    fn = defs[0]
    if fn.name != "f" or fn.decorator_list or not _plain_single_arg(fn):
        return None
    return code


def parse_function(text: str) -> str:
    """Candidate source for a model reply, or `PARSE_FAILURE_STUB` if it has none."""
    src = try_parse(text)
    return PARSE_FAILURE_STUB if src is None else src
