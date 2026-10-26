import hashlib
import json

import pytest

from frontier_py.receipt import ReceiptError, VerifierReceipt, canonical_digest, canonical_json

D1, D2 = "a" * 64, "0123456789abcdef" * 4

# Output of serde_json 1.0.154 `to_string` on the same value (recorded from a
# scratch Rust build; Rust's canonical form is this compact sorted encoding).
SERDE_JSON_BYTES = (
    b'{"a":"caf\xc3\xa9 \\u001f q\\" b\\\\ n\\n","m":{"a":null,"b":true},'
    b'"z":[0.1,1.5,2.0,-3.25,1234.5678,0.25,100.0,1000000000000000.0,1e+16,1e+20,'
    b"0.001,0,-7,9007199254740993,9223372036854775807]}"
)


def make(**kw):
    base = dict(
        spec_digest=D1,
        artifact_digest=D2,
        verdict="PASS",
        trust_class="V1",
        verifier_id="property-tests",
        verifier_version="0.1.0",
        reason="ok",
        cost_units=1,
    )
    return VerifierReceipt(**{**base, **kw})


def test_canonical_matches_serde_json_for_fixture():
    value = {
        "z": [0.1, 1.5, 2.0, -3.25, 1234.5678, 0.25, 100.0, 1e15, 1e16, 1e20, 0.001, 0, -7, 2**53 + 1, 2**63 - 1],
        "a": "café \x1f q\" b\\ n\n",
        "m": {"b": True, "a": None},
    }
    assert canonical_json(value) == SERDE_JSON_BYTES
    assert canonical_digest(value) == hashlib.sha256(SERDE_JSON_BYTES).hexdigest()


def test_known_divergence_negative_exponent():
    # serde_json writes 1e-7; Python writes 1e-07. Documented, not papered over.
    assert canonical_json(1e-7) == b"1e-07"


def test_canonical_rejects_nan():
    with pytest.raises(ValueError):
        canonical_digest({"x": float("nan")})


def test_roundtrip_and_shape():
    r = make()
    d = json.loads(r.to_json())
    assert list(d) == sorted(d)
    assert d["schema_version"] == "0.2" and d["cost_units"] == 1.0 and isinstance(d["cost_units"], float)
    assert set(d) == {
        "schema_version", "spec_digest", "artifact_digest", "verdict", "trust_class",
        "verifier_id", "verifier_version", "reason", "cost_units",
    }
    assert VerifierReceipt.from_json(r.to_json()) == r
    assert '"cost_units":1.0' in r.to_json()


@pytest.mark.parametrize(
    "kw",
    [
        {"spec_digest": "A" * 64},
        {"artifact_digest": "a" * 63},
        {"verdict": "pass"},
        {"verdict": "OK"},
        {"trust_class": "V5"},
        {"cost_units": -1.0},
        {"cost_units": float("inf")},
        {"cost_units": True},
        {"schema_version": "0.1"},
        {"verifier_id": " "},
    ],
)
def test_validation(kw):
    with pytest.raises(ReceiptError):
        make(**kw)


def test_from_json_rejects_unknown_and_missing():
    d = make().to_dict()
    with pytest.raises(ReceiptError, match="unknown"):
        VerifierReceipt.from_dict({**d, "confidence": 1.0})
    del d["reason"]
    with pytest.raises(ReceiptError, match="missing"):
        VerifierReceipt.from_dict(d)
    with pytest.raises(ReceiptError):
        VerifierReceipt.from_json("{not json")
