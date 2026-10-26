"""Verifier CLI, request schema 0.2.

    python -m frontier_py.verify_cli < request.json

Request (one JSON object on stdin, unknown fields rejected):
    {"schema_version": "0.2", "task": "<name>", "spec_digest": "<64 hex>",
     "candidate": {"source": "..."}, "seed": <int>,
     "task_id": "<optional>", "artifact_digest": "<optional 64 hex>"}

Writes one receipt JSON line to stdout. Exit 0 for every verdict, 2 for a
malformed request (message on stderr).
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any

import jsonschema

from .receipt import RECEIPT_SCHEMA_VERSION
from .tasks import TASKS
from .verifiers.property_tests import verify

DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
REQUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "task", "spec_digest", "candidate", "seed"],
    "properties": {
        "schema_version": {"const": RECEIPT_SCHEMA_VERSION},
        "task": {"enum": sorted(TASKS)},
        "spec_digest": DIGEST,
        "artifact_digest": DIGEST,
        "task_id": {"type": "string", "minLength": 1},
        "seed": {"type": "integer", "minimum": 0, "maximum": 2**64 - 1},
        "candidate": {"type": "object", "required": ["source"], "properties": {"source": {"type": "string"}}},
    },
}


def main(stdin: IO[bytes] | None = None, stdout: IO[bytes] | None = None) -> int:
    """Byte streams in and out: UTF-8 and LF regardless of platform locale."""
    stdin, stdout = stdin or sys.stdin.buffer, stdout or sys.stdout.buffer
    try:
        req = json.loads(stdin.read().decode("utf-8"))
        jsonschema.validate(req, REQUEST_SCHEMA)
    except (ValueError, jsonschema.ValidationError) as e:  # UnicodeDecodeError is a ValueError
        msg = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
        print(f"malformed request: {msg}", file=sys.stderr)
        return 2
    receipt = verify(
        TASKS[req["task"]],
        req["candidate"],
        spec_digest=req["spec_digest"],
        seed=req["seed"],
        artifact_digest=req.get("artifact_digest"),
        task_id=req.get("task_id"),
    )
    stdout.write(receipt.to_json().encode("utf-8") + b"\n")
    stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
