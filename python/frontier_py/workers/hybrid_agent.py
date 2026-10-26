"""HybridAgent adapter (interface only in phase 1).

Pins the upstream engine and checkpoint. Nothing is ever downloaded: the
checkout and the checkpoint must already exist on local disk, and `probe()`
reports exactly what is missing.

The paper and the released engine disagree (source audit C6): the engine
leaves latent mode when the LM-head argmax equals `</latent>` after a
minimum step count, or at a step cap, while the paper describes a
nearest-token readout; engine defaults (min/max latent steps 4/200, tool cap
5) differ from the paper's (16/256, tool cap 10). These settings are
therefore required config with no defaults, so every run states which one
it used. `ENGINE_DEFAULTS` and `PAPER_SETTINGS` are given for reference only.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .base import Availability, Capabilities, Charge, GenerationRequest, GenerationResult, WorkerAdapter, WorkerUnavailable

UPSTREAM_REPO = "togethercomputer/HybridAgent"
UPSTREAM_COMMIT = "1b41cebbd2388d083ee1820af421b7f9e24affb5"
CHECKPOINT = "togethercomputer/HybridAgent-8B-Agentic"
CHECKPOINT_REVISION = "13a5c61b1880d7bcc2fac2e28d478809722beb8f"
MIN_VRAM_GB = 24.0

ExitRule = Literal["lm_head_argmax", "nearest_token"]
ENGINE_DEFAULTS = {"exit_rule": "lm_head_argmax", "min_latent_steps": 4, "max_latent_steps": 200, "max_tool_calls": 5}
PAPER_SETTINGS = {"exit_rule": "nearest_token", "min_latent_steps": 16, "max_latent_steps": 256, "max_tool_calls": 10}


@dataclass(frozen=True, kw_only=True)
class HybridAgentConfig:
    checkout_path: Path
    checkpoint_path: Path
    exit_rule: ExitRule
    min_latent_steps: int
    max_latent_steps: int
    max_tool_calls: int
    max_context_tokens: int

    def __post_init__(self) -> None:
        if self.exit_rule not in ("lm_head_argmax", "nearest_token"):
            raise ValueError(f"unknown exit_rule {self.exit_rule!r}")
        if not 0 <= self.min_latent_steps <= self.max_latent_steps:
            raise ValueError("need 0 <= min_latent_steps <= max_latent_steps")
        if self.max_tool_calls < 0 or self.max_context_tokens <= 0:
            raise ValueError("max_tool_calls must be >= 0 and max_context_tokens > 0")


def checkout_commit(path: Path) -> str | None:
    """HEAD commit of a git checkout, read from files (no git subprocess)."""
    git = path / ".git"
    try:
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head
        ref = head[5:]
        loose = git / ref
        if loose.is_file():
            return loose.read_text().strip()
        for line in (git / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    except OSError:
        return None
    return None


def gpu_status(torch: Any) -> list[str]:
    """Reasons the given torch module cannot host the model ([] if it can)."""
    if not torch.cuda.is_available():
        return ["CUDA is not available"]
    best = max(torch.cuda.get_device_properties(i).total_memory for i in range(torch.cuda.device_count())) / 2**30
    return [] if best >= MIN_VRAM_GB else [f"largest GPU has {best:.1f} GiB VRAM, need >= {MIN_VRAM_GB:g} GiB"]


class HybridAgentAdapter(WorkerAdapter):
    def __init__(self, config: HybridAgentConfig) -> None:
        self.config = config

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name="hybrid-agent",
            model=CHECKPOINT,
            model_revision=CHECKPOINT_REVISION,
            latent_reasoning=True,
            tool_use=self.config.max_tool_calls > 0,
            max_context_tokens=self.config.max_context_tokens,
        )

    def probe(self) -> Availability:
        reasons: list[str] = []
        c = self.config
        commit = checkout_commit(c.checkout_path)
        if commit is None:
            reasons.append(f"no git checkout of {UPSTREAM_REPO} at {c.checkout_path}")
        elif commit != UPSTREAM_COMMIT:
            reasons.append(f"checkout is at {commit}, pinned {UPSTREAM_COMMIT}")
        if not (c.checkpoint_path / "config.json").is_file():
            reasons.append(f"checkpoint {CHECKPOINT}@{CHECKPOINT_REVISION} not found at {c.checkpoint_path} (never auto-downloaded)")
        if importlib.util.find_spec("torch") is None:
            reasons.append("torch is not installed")
        else:
            import torch

            reasons += gpu_status(torch)
        return Availability(not reasons, tuple(reasons))

    def max_charge(self, req: GenerationRequest) -> Charge:
        return Charge(tokens=len(req.prompt.encode("utf-8")) + req.limits.max_output_tokens, usd=0.0)

    def generate(self, req: GenerationRequest) -> GenerationResult:
        if req.model_revision != CHECKPOINT_REVISION:
            raise ValueError(f"request pins revision {req.model_revision}, adapter pins {CHECKPOINT_REVISION}")
        if req.limits.max_latent_steps > self.config.max_latent_steps or req.limits.max_tool_calls > self.config.max_tool_calls:
            raise ValueError("request limits exceed the configured latent-step or tool caps")
        status = self.probe()
        if not status.available:
            raise WorkerUnavailable(status.reason)
        raise NotImplementedError("engine binding is not implemented in phase 1 (no GPU available to test it)")
