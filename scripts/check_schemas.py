#!/usr/bin/env python3
"""Validate FRONTIER data-contract schemas and, optionally, data files.

Always checks that every schemas/*.schema.json is a valid JSON Schema
(draft 2020-12), that cross-schema references resolve, and that every
schemas/examples/<name>.example.json validates against <name>.schema.json.

Optional data checks:
  --events FILE.jsonl   each non-blank line against event-record.schema.json
  --config FILE.json    against sim-config.schema.json
  --receipt FILE.json   against verifier-receipt.schema.json
  --spec FILE.json      against problem-spec.schema.json
  --artifact FILE.json  against artifact.schema.json
Each option may be repeated. Exit status is 1 if anything fails.

Requires only the standard library and jsonschema (>= 4.18).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
except ImportError as exc:  # pragma: no cover - environment problem
    sys.exit(f"error: {exc}. Install with: pip install 'jsonschema>=4.18'")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"
EXAMPLE_DIR = SCHEMA_DIR / "examples"
MAX_ERRORS_PER_DOC = 20


class Checker:
    def __init__(self) -> None:
        self.failures = 0
        self.schemas: dict[str, dict] = {}
        self.validators: dict[str, Draft202012Validator] = {}

    def fail(self, msg: str) -> None:
        self.failures += 1
        print(f"FAIL {msg}")

    def load_schemas(self) -> None:
        paths = sorted(SCHEMA_DIR.glob("*.schema.json"))
        if not paths:
            self.fail(f"no schemas found in {SCHEMA_DIR}")
            return
        resources = []
        for path in paths:
            name = path.name.removesuffix(".schema.json")
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.fail(f"{rel(path)}: cannot parse: {exc}")
                continue
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                self.fail(f"{rel(path)}: not a valid 2020-12 schema: {exc.message} (at {pointer(exc.path)})")
                continue
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                self.fail(f"{rel(path)}: $schema must be the 2020-12 meta-schema")
                continue
            expected_id = f"https://github.com/Kesh3805/frontier/schemas/{path.name}"
            if schema.get("$id") != expected_id:
                self.fail(f"{rel(path)}: $id must be {expected_id!r}, got {schema.get('$id')!r}")
                continue
            self.schemas[name] = schema
            resources.append((expected_id, Resource.from_contents(schema, default_specification=DRAFT202012)))
            print(f"ok   {rel(path)}: valid 2020-12 schema")
        registry = Registry().with_resources(resources)
        for name, schema in self.schemas.items():
            validator = Draft202012Validator(schema, registry=registry)
            try:
                resolve_all_refs(schema, registry.resolver(base_uri=schema["$id"]))
            except Exception as exc:  # referencing raises several types
                self.fail(f"schemas/{name}.schema.json: unresolvable $ref: {exc}")
                continue
            self.validators[name] = validator

    def validate(self, schema_name: str, instance: object, label: str) -> bool:
        validator = self.validators.get(schema_name)
        if validator is None:
            self.fail(f"{label}: schema {schema_name!r} unavailable")
            return False
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if not errors:
            return True
        for err in errors[:MAX_ERRORS_PER_DOC]:
            self.fail(f"{label}: {pointer(err.absolute_path)}: {describe(err)}")
        if len(errors) > MAX_ERRORS_PER_DOC:
            print(f"     ... {len(errors) - MAX_ERRORS_PER_DOC} more errors in {label}")
        return False

    def check_json_file(self, schema_name: str, path: Path) -> None:
        try:
            instance = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.fail(f"{path}: cannot parse JSON: {exc}")
            return
        if self.validate(schema_name, instance, str(path)):
            print(f"ok   {path}: valid {schema_name}")

    def check_jsonl_file(self, schema_name: str, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            self.fail(f"{path}: cannot read: {exc}")
            return
        records = bad = 0
        for lineno, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            records += 1
            label = f"{path}:{lineno}"
            try:
                instance = json.loads(line)
            except json.JSONDecodeError as exc:
                self.fail(f"{label}: cannot parse JSON: {exc}")
                bad += 1
                continue
            if not self.validate(schema_name, instance, label):
                bad += 1
        if records == 0:
            self.fail(f"{path}: no records")
        elif bad == 0:
            print(f"ok   {path}: {records} records valid {schema_name}")

    def check_examples(self) -> None:
        if not EXAMPLE_DIR.is_dir():
            return
        for path in sorted(EXAMPLE_DIR.glob("*.example.json")):
            name = path.name.removesuffix(".example.json")
            if name not in self.schemas:
                self.fail(f"{rel(path)}: no matching schemas/{name}.schema.json")
                continue
            try:
                instance = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.fail(f"{rel(path)}: cannot parse JSON: {exc}")
                continue
            if self.validate(name, instance, rel(path)):
                print(f"ok   {rel(path)}: valid {name}")


def resolve_all_refs(node: object, resolver) -> None:
    """Resolve every $ref once so dangling references fail up front."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            ref = cur.get("$ref")
            if isinstance(ref, str):
                try:
                    resolver.lookup(ref)
                except Exception as exc:  # referencing raises several types
                    raise ValueError(f"{ref!r} ({type(exc).__name__})") from None
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def describe(err) -> str:
    # For if/then and oneOf failures the leaf errors are far more useful.
    leaves = list(err.context or [])
    if leaves:
        best = max(leaves, key=lambda e: len(list(e.absolute_path)))
        return f"{err.message} [{pointer(best.absolute_path)}: {best.message}]"
    return err.message


def pointer(path) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in path]
    return "/" + "/".join(parts) if parts else "(root)"


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--events", type=Path, action="append", default=[], metavar="FILE.jsonl")
    ap.add_argument("--config", type=Path, action="append", default=[], metavar="FILE.json")
    ap.add_argument("--receipt", type=Path, action="append", default=[], metavar="FILE.json")
    ap.add_argument("--spec", type=Path, action="append", default=[], metavar="FILE.json")
    ap.add_argument("--artifact", type=Path, action="append", default=[], metavar="FILE.json")
    args = ap.parse_args(argv)

    c = Checker()
    c.load_schemas()
    c.check_examples()
    for p in args.events:
        c.check_jsonl_file("event-record", p)
    for p in args.config:
        c.check_json_file("sim-config", p)
    for p in args.receipt:
        c.check_json_file("verifier-receipt", p)
    for p in args.spec:
        c.check_json_file("problem-spec", p)
    for p in args.artifact:
        c.check_json_file("artifact", p)

    if c.failures:
        print(f"check_schemas: {c.failures} failure(s)")
        return 1
    print("check_schemas: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
