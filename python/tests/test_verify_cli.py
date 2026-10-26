import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from frontier_py.receipt import VerifierReceipt
from frontier_py.verify_cli import main

PY_ROOT = Path(__file__).resolve().parents[1]


def request(**kw):
    base = {
        "schema_version": "0.2",
        "task": "gcd",
        "spec_digest": "b" * 64,
        "candidate": {"source": "import math\ngcd = math.gcd"},
        "seed": 3,
    }
    return {**base, **kw}


def call(obj):
    out = io.BytesIO()
    rc = main(io.BytesIO((obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)).encode("utf-8")), out)
    return rc, out.getvalue().decode("utf-8")


def test_pass_and_fail_exit_zero():
    rc, out = call(request())
    assert rc == 0 and VerifierReceipt.from_json(out).verdict == "PASS"
    rc, out = call(request(candidate={"source": "def gcd(a, b):\n    return 1"}))
    assert rc == 0 and VerifierReceipt.from_json(out).verdict == "FAIL"


def test_non_ascii_source_survives():
    src = 'def gcd(a, b):\n    """größter gemeinsamer Teiler"""\n    import math\n    return math.gcd(a, b)'
    rc, out = call(request(candidate={"source": src}))
    assert rc == 0 and out.endswith("}\n") and VerifierReceipt.from_json(out).verdict == "PASS"


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        request(schema_version="0.1"),
        request(task="nope"),
        request(spec_digest="xyz"),
        request(seed=-1),
        request(seed="1"),
        request(candidate={}),
        request(extra=True),
    ],
)
def test_malformed_requests_exit_nonzero(bad):
    rc, out = call(bad)
    assert rc == 2 and out == ""


def test_module_entrypoint_end_to_end():
    p = subprocess.run(
        [sys.executable, "-m", "frontier_py.verify_cli"],
        input=json.dumps(request(task="sort_ints", candidate={"source": "def sort_ints(xs):\n    return sorted(xs)"})),
        capture_output=True,
        text=True,
        cwd=PY_ROOT,
        timeout=60,
    )
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    assert len(lines) == 1 and VerifierReceipt.from_json(lines[0]).verdict == "PASS"
