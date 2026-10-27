"""Per-campaign spending ledger that survives crashes.

A `CampaignLedger` is one JSON file, kept outside the repository, holding
the campaign's USD cap and every reservation made against it. Before a paid
call the caller reserves the call's worst-case cost; after the call it
settles the reservation with the actual cost. Spent is

    sum(actual for settled reservations) + sum(worst for unsettled ones)

so a reservation whose call crashed, timed out or was killed before
settling counts at its worst case forever: a crash can never let a later
process spend past the cap. A reservation that would take spent above the
cap is refused before any call is made.

Every update rewrites the file atomically (write to a temporary sibling,
fsync, rename, fsync the directory where the platform allows it), so a
reader sees either the old or the new state, never a torn one.

A settled cost above its own reservation means the worst-case bound was
wrong (or a provider over-reported). The ledger records the overrun and
halts: every later reservation is refused until a human looks at it.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .base import BudgetExceeded

LEDGER_SCHEMA = "frontier.campaign-ledger/1"
_EPS = 1e-12


class LedgerError(RuntimeError):
    pass


def _finite_nonneg(x: float, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
        raise ValueError(f"{what} must be finite and non-negative, got {x!r}")
    return float(x)


def _fsync_dir(path: Path) -> None:
    if os.name != "posix":
        return  # directories cannot be opened for fsync on Windows; os.replace is still atomic
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class CampaignLedger:
    def __init__(self, path: str | Path, cap_usd: float) -> None:
        self.path = Path(path)
        cap = _finite_nonneg(cap_usd, "cap_usd")
        if cap <= 0:
            raise ValueError("an explicit cap_usd > 0 is required")
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state.get("schema") != LEDGER_SCHEMA:
                raise LedgerError(f"{self.path}: not a campaign ledger")
            if state.get("cap_usd") != cap:
                raise LedgerError(f"{self.path}: ledger cap is ${state.get('cap_usd')}, requested ${cap}; refusing to change a campaign's cap")
            self._state: dict[str, Any] = state
        else:
            self._state = {"schema": LEDGER_SCHEMA, "cap_usd": cap, "halted": None, "reservations": []}
            self._write()

    # --- state ------------------------------------------------------------

    @property
    def cap_usd(self) -> float:
        return float(self._state["cap_usd"])

    @property
    def halted(self) -> str | None:
        return self._state["halted"]

    @property
    def reservations(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._state["reservations"]]

    @property
    def spent_usd(self) -> float:
        """Settled actuals plus unsettled worst cases."""
        return sum(r["worst_usd"] if r["actual_usd"] is None else r["actual_usd"] for r in self._state["reservations"])

    @property
    def settled_usd(self) -> float:
        return sum(r["actual_usd"] for r in self._state["reservations"] if r["actual_usd"] is not None)

    @property
    def unsettled(self) -> list[int]:
        return [r["id"] for r in self._state["reservations"] if r["actual_usd"] is None]

    @property
    def remaining_usd(self) -> float:
        return self.cap_usd - self.spent_usd

    # --- operations ---------------------------------------------------------

    def reserve(self, worst_usd: float, label: str = "") -> int:
        """Reserve `worst_usd` before a call; returns the reservation id. Refuses past the cap."""
        worst = _finite_nonneg(worst_usd, "worst_usd")
        if self.halted:
            raise BudgetExceeded(f"ledger {self.path.name} is halted: {self.halted}")
        if self.spent_usd + worst > self.cap_usd + _EPS:
            raise BudgetExceeded(
                f"reservation of ${worst:.6f} refused: spent ${self.spent_usd:.6f} (unsettled counted at worst case) "
                f"of cap ${self.cap_usd:.6f}"
            )
        rid = len(self._state["reservations"])
        self._state["reservations"].append(
            {"id": rid, "label": label, "worst_usd": worst, "actual_usd": None, "reserved_utc": time.time(), "settled_utc": None}
        )
        self._write()
        return rid

    def settle(self, rid: int, actual_usd: float) -> None:
        """Record what a reserved call actually cost. An overrun halts the ledger."""
        actual = _finite_nonneg(actual_usd, "actual_usd")
        try:
            r = self._state["reservations"][rid]
        except (IndexError, TypeError):
            raise LedgerError(f"unknown reservation {rid!r}") from None
        if r["actual_usd"] is not None:
            raise LedgerError(f"reservation {rid} is already settled")
        r["actual_usd"], r["settled_utc"] = actual, time.time()
        if actual > r["worst_usd"] + _EPS:
            self._state["halted"] = f"reservation {rid} settled at ${actual:.6f} above its worst case ${r['worst_usd']:.6f}"
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self._state, indent=1, sort_keys=True).encode("utf-8") + b"\n"
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        _fsync_dir(self.path.parent)
