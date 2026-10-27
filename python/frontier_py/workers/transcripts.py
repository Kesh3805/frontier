"""Append-only store of recorded model calls (record once, replay exactly).

A transcript store is one JSONL file. The first line is a header that fixes
what the pool is: provider, model, revision, prompt template, sampling
parameters, rate card and suite. Every further line is one recorded call:

    {"kind": "call", "key": {...}, "key_sha256": HEX, "request": {...},
     "text": STR, "usage": {"input_tokens": INT, "output_tokens": INT},
     "usd": FLOAT, "provider_usd": FLOAT|null, "finish_reason": STR,
     "response_model_id": STR, "utc": STR, "header_sha256": HEX, "record_sha256": HEX}

`key` is a `TranscriptKey`: everything that decides what the model was
asked (provider, model, revision, template version, prompt hash, sampling
parameters, task, sample index j). `key_sha256` is the SHA-256 of its
canonical JSON. `header_sha256` binds the call to the store's header, and
`record_sha256` is the SHA-256 of the whole record without itself, so
editing any byte of a stored call, or of the header once a call is stored,
is detected by `verify()`.

`put` refuses a second record for a key that is already stored: a sample,
once drawn, is never redrawn or replaced. The request stored with a call is
built from an allowlist of fields; anything else (headers, keys, tokens)
is refused, so credentials cannot reach the file by accident.

The file is only ever appended to, one fsync'd line per call. `sha256()` is
the SHA-256 of the file bytes, which identifies the pool in experiment
manifests.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..receipt import canonical_digest, canonical_json, is_digest

STORE_SCHEMA = "frontier.transcripts/1"
REQUEST_FIELDS = frozenset(
    {"provider", "model", "model_revision", "template_version", "prompt", "temperature", "top_p", "max_output_tokens", "seed"}
)
HEADER_FIELDS = frozenset(
    {"provider", "model", "model_revision", "template_version", "temperature", "top_p", "max_output_tokens"}
)


class TranscriptError(RuntimeError):
    pass


class DuplicateTranscript(TranscriptError):
    pass


class TamperedStore(TranscriptError):
    pass


@dataclass(frozen=True)
class TranscriptKey:
    provider: str
    model: str
    model_revision: str
    template_version: str
    prompt_sha256: str
    temperature: float
    top_p: float
    max_output_tokens: int
    task: str
    j: int

    def __post_init__(self) -> None:
        if not is_digest(self.prompt_sha256):
            raise ValueError("prompt_sha256 must be a lowercase hex SHA-256")
        if isinstance(self.j, bool) or not isinstance(self.j, int) or self.j < 0:
            raise ValueError("sample index j must be a non-negative integer")
        if isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int) or self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")

    def canonical(self) -> dict[str, Any]:
        d = asdict(self)
        d["temperature"], d["top_p"] = float(self.temperature), float(self.top_p)
        return d

    @property
    def sha256(self) -> str:
        return canonical_digest(self.canonical())

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TranscriptKey:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TranscriptRecord:
    key: TranscriptKey
    request: Mapping[str, Any]
    text: str
    input_tokens: int
    output_tokens: int
    usd: float
    finish_reason: str
    response_model_id: str
    utc: str
    provider_usd: float | None = None

    def body(self, header_sha256: str) -> dict[str, Any]:
        return {
            "kind": "call",
            "key": self.key.canonical(),
            "key_sha256": self.key.sha256,
            "request": dict(self.request),
            "text": self.text,
            "usage": {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens},
            "usd": float(self.usd),
            "provider_usd": None if self.provider_usd is None else float(self.provider_usd),
            "finish_reason": self.finish_reason,
            "response_model_id": self.response_model_id,
            "utc": self.utc,
            "header_sha256": header_sha256,
        }

    def to_dict(self, header_sha256: str) -> dict[str, Any]:
        b = self.body(header_sha256)
        return {**b, "record_sha256": canonical_digest(b)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TranscriptRecord:
        u = d["usage"]
        return cls(TranscriptKey.from_dict(d["key"]), d["request"], d["text"], u["input_tokens"], u["output_tokens"], d["usd"],
                   d["finish_reason"], d["response_model_id"], d["utc"], d.get("provider_usd"))


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _check_request(request: Mapping[str, Any], key: TranscriptKey) -> None:
    extra = set(request) - REQUEST_FIELDS
    if extra:
        raise TranscriptError(f"request carries fields outside the allowlist: {sorted(extra)}")
    prompt = request.get("prompt")
    if not isinstance(prompt, str) or prompt_sha256(prompt) != key.prompt_sha256:
        raise TranscriptError("stored request prompt does not hash to the key's prompt_sha256")


class TranscriptStore:
    """Open (or, with `header`, create) the store at `path`."""

    def __init__(self, path: str | Path, header: Mapping[str, Any] | None = None) -> None:
        self.path = Path(path)
        self._records: dict[str, TranscriptRecord] = {}
        if self.path.exists() and self.path.stat().st_size > 0:
            self.header = self._load()
            if header is not None and self._header_body(header) != self.header:
                raise TranscriptError(f"{self.path}: existing header differs from the requested one")
        else:
            if header is None:
                raise TranscriptError(f"{self.path}: no such store (pass a header to create one)")
            self.header = self._header_body(header)
            self._append(self.header)

    @staticmethod
    def _header_body(header: Mapping[str, Any]) -> dict[str, Any]:
        missing = HEADER_FIELDS - set(header)
        if missing:
            raise TranscriptError(f"header lacks {sorted(missing)}")
        return json.loads(canonical_json({**header, "kind": "header", "schema": STORE_SCHEMA}))

    def _load(self) -> dict[str, Any]:
        lines = self.path.read_bytes().split(b"\n")
        if lines[-1] != b"":
            raise TamperedStore(f"{self.path}: last line is incomplete")
        header = json.loads(lines[0])
        if header.get("kind") != "header" or header.get("schema") != STORE_SCHEMA:
            raise TamperedStore(f"{self.path}: first line is not a {STORE_SCHEMA} header")
        for n, line in enumerate(lines[1:-1], start=2):
            d = json.loads(line)
            rec = TranscriptRecord.from_dict(d)
            if rec.key.sha256 in self._records:
                raise TamperedStore(f"{self.path}:{n}: duplicate key {rec.key.sha256}")
            self._records[rec.key.sha256] = rec
        return header

    def _append(self, obj: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "ab") as f:
            f.write(canonical_json(dict(obj)) + b"\n")
            f.flush()
            os.fsync(f.fileno())

    def _check_key_matches_header(self, key: TranscriptKey) -> None:
        for field in HEADER_FIELDS:
            want = self.header[field]
            got = getattr(key, field)
            if (float(got) != float(want)) if field in ("temperature", "top_p") else got != want:
                raise TranscriptError(f"key {field}={got!r} does not match the store header {want!r}")

    # --- public API -------------------------------------------------------

    def __contains__(self, key: TranscriptKey) -> bool:
        return key.sha256 in self._records

    def __len__(self) -> int:
        return len(self._records)

    def get(self, key: TranscriptKey) -> TranscriptRecord | None:
        return self._records.get(key.sha256)

    def records(self) -> Iterator[TranscriptRecord]:
        return iter(self._records.values())

    def put(self, record: TranscriptRecord) -> None:
        """Append one call. Refuses a key that is already stored."""
        if record.key.sha256 in self._records:
            raise DuplicateTranscript(f"transcript for {record.key.task} j={record.key.j} is already stored")
        self._check_key_matches_header(record.key)
        _check_request(record.request, record.key)
        self._append(record.to_dict(canonical_digest(self.header)))
        self._records[record.key.sha256] = record

    def verify(self) -> list[str]:
        """Re-read the file and return every integrity problem found (empty = intact)."""
        problems: list[str] = []
        try:
            lines = self.path.read_bytes().split(b"\n")
        except OSError as e:
            return [f"cannot read store: {e}"]
        if lines[-1] != b"":
            problems.append("last line is incomplete")
        seen: set[str] = set()
        header_sha = None
        for n, line in enumerate(lines[:-1] if lines[-1] == b"" else lines, start=1):
            try:
                d = json.loads(line)
            except ValueError:
                problems.append(f"line {n}: not JSON")
                continue
            if n == 1:
                if d != self.header:
                    problems.append("line 1: header changed")
                header_sha = canonical_digest(d)
                continue
            if not isinstance(d, dict) or d.get("kind") != "call":
                problems.append(f"line {n}: not a call record")
                continue
            body = {k: v for k, v in d.items() if k != "record_sha256"}
            if canonical_digest(body) != d.get("record_sha256"):
                problems.append(f"line {n}: record_sha256 mismatch")
            if d.get("header_sha256") != header_sha:
                problems.append(f"line {n}: not bound to this store's header")
            try:
                key = TranscriptKey.from_dict(d["key"])
                if key.sha256 != d.get("key_sha256"):
                    problems.append(f"line {n}: key_sha256 mismatch")
                if key.sha256 in seen:
                    problems.append(f"line {n}: duplicate key")
                seen.add(key.sha256)
                _check_request(d["request"], key)
            except (KeyError, TypeError, ValueError, TranscriptError) as e:
                problems.append(f"line {n}: {type(e).__name__}: {e}")
            if canonical_json(d) != line:
                problems.append(f"line {n}: not in canonical encoding")
        return problems

    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()
