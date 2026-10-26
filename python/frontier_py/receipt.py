"""Verifier receipts and canonical digests, wire-compatible with frontier-core.

`VerifierReceipt` serializes to the same JSON object as the Rust
`frontier_core::evidence::VerifierReceipt` (same field names, enum spellings,
unknown fields rejected).

`canonical_digest` mirrors `frontier_core::digest::canonical_json`: compact
JSON with sorted object keys, UTF-8 without ASCII escaping, then SHA-256.
Byte equality was checked against serde_json 1.0.154 only for the fixture
in tests/test_receipt.py: strings (non-ASCII, control characters, quotes,
backslashes), integers up to i64::MAX, booleans, null, nested objects and
the floats listed there. Both sides emit shortest round-trip digits, but
they are known to DIFFER for negative exponents (Python `1e-07`, serde_json
`1e-7`); other float forms and integers outside i64/u64 (rejected by
serde_json) are untested. NaN and infinities are refused because serde_json
cannot encode them. Keep hashed payloads to integers and moderate floats.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, get_args

RECEIPT_SCHEMA_VERSION = "0.2"

Verdict = Literal["PASS", "FAIL", "INCONCLUSIVE", "REVIEW_REQUIRED"]
TrustClass = Literal["V0", "V1", "V2", "V3", "V4"]
VERDICTS: frozenset[str] = frozenset(get_args(Verdict))
TRUST_CLASSES: tuple[str, ...] = get_args(TrustClass)

_HEX64 = re.compile(r"[0-9a-f]{64}")


class ReceiptError(ValueError):
    pass


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def canonical_digest(obj: Any) -> str:
    """Lowercase hex SHA-256 of the canonical JSON encoding of `obj`."""
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def is_digest(s: object) -> bool:
    return isinstance(s, str) and _HEX64.fullmatch(s) is not None


@dataclass(frozen=True)
class VerifierReceipt:
    spec_digest: str
    artifact_digest: str
    verdict: Verdict
    trust_class: TrustClass
    verifier_id: str
    verifier_version: str
    reason: str
    cost_units: float
    schema_version: str = RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            raise ReceiptError(f"unsupported schema_version {self.schema_version!r}")
        for name in ("spec_digest", "artifact_digest"):
            if not is_digest(getattr(self, name)):
                raise ReceiptError(f"{name} must be 64 lowercase hex characters")
        if self.verdict not in VERDICTS:
            raise ReceiptError(f"unknown verdict {self.verdict!r}")
        if self.trust_class not in TRUST_CLASSES:
            raise ReceiptError(f"unknown trust_class {self.trust_class!r}")
        for name in ("verifier_id", "verifier_version", "reason"):
            if not isinstance(getattr(self, name), str):
                raise ReceiptError(f"{name} must be a string")
        if not self.verifier_id.strip() or not self.verifier_version.strip():
            raise ReceiptError("verifier_id and verifier_version must not be empty")
        c = self.cost_units
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or c < 0:
            raise ReceiptError("cost_units must be a finite number >= 0")
        # Rust holds an f64; normalise so that 1 encodes as 1.0 on both sides.
        object.__setattr__(self, "cost_units", float(c))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return canonical_json(self.to_dict()).decode("utf-8")

    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, d: Any) -> VerifierReceipt:
        if not isinstance(d, dict):
            raise ReceiptError("receipt must be a JSON object")
        fields = set(cls.__dataclass_fields__)
        unknown, missing = set(d) - fields, fields - set(d)
        if unknown:
            raise ReceiptError(f"unknown fields: {sorted(unknown)}")
        if missing:
            raise ReceiptError(f"missing fields: {sorted(missing)}")
        return cls(**d)

    @classmethod
    def from_json(cls, s: str | bytes) -> VerifierReceipt:
        try:
            d = json.loads(s)
        except json.JSONDecodeError as e:
            raise ReceiptError(f"invalid JSON: {e}") from e
        return cls.from_dict(d)
