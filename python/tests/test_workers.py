import dataclasses
import socket
import types
from pathlib import Path

import pytest

from frontier_py.workers import hybrid_agent as ha
from frontier_py.workers.base import (
    Availability,
    BudgetExceeded,
    BudgetGuard,
    Capabilities,
    Charge,
    GenerationRequest,
    GenerationResult,
    Limits,
    Usage,
    WorkerAdapter,
    WorkerUnavailable,
)
from frontier_py.workers.hosted import HostedAdapter, HostedConfig

LIMITS = Limits(max_output_tokens=100, max_latent_steps=0, max_tool_calls=0, wall_seconds=10)


def req(prompt="x" * 50, revision="r1", **lim):
    return GenerationRequest(prompt=prompt, limits=dataclasses.replace(LIMITS, **lim), seed=0, model_revision=revision)


class Fake(WorkerAdapter):
    def __init__(self, used_tokens=120, used_usd=0.01, bound=Charge(150, 0.02)):
        self.used, self.bound, self.calls = Usage(input_tokens=used_tokens - 20, output_tokens=20, usd=used_usd), bound, 0

    def capabilities(self):
        return Capabilities("fake", "m", "r1", False, False, 1000)

    def probe(self):
        return Availability(True)

    def max_charge(self, r):
        return self.bound

    def generate(self, r):
        self.calls += 1
        return GenerationResult("ok", {"source": "", "confidence": 1.0}, self.used, "stop")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_budget_guard_refuses_before_calling():
    fake = Fake()
    g = BudgetGuard(fake, max_tokens=400, max_usd=1.0)
    g.generate(req())
    g.generate(req())
    assert (g.spent_tokens, g.remaining_tokens, fake.calls) == (240, 160, 2)
    g.generate(req())  # worst case 150 <= 160
    with pytest.raises(BudgetExceeded):
        g.generate(req())  # 40 left < 150
    assert fake.calls == 3 and g.refused == 1


def test_budget_guard_usd_cap():
    fake = Fake(used_usd=0.5, bound=Charge(10, 0.6))
    g = BudgetGuard(fake, max_tokens=10**6, max_usd=1.0)
    g.generate(req())
    with pytest.raises(BudgetExceeded):
        g.generate(req())
    assert fake.calls == 1


def test_budget_guard_records_overrun_and_charges_actual():
    fake = Fake(used_tokens=500, bound=Charge(100, 0.02))
    g = BudgetGuard(fake, max_tokens=1000, max_usd=1.0)
    g.generate(req())
    assert g.spent_tokens == 500 and len(g.overruns) == 1


def test_budget_guard_zero_budget_refuses_everything():
    fake = Fake(bound=Charge(1, 0.0))
    with pytest.raises(BudgetExceeded):
        BudgetGuard(fake, max_tokens=0, max_usd=0.0).generate(req())
    assert fake.calls == 0
    with pytest.raises(ValueError):
        BudgetGuard(fake, max_tokens=1, max_usd=float("nan"))


# --- HybridAgent ------------------------------------------------------------


def hybrid_config(tmp_path, **kw):
    base = dict(
        checkout_path=tmp_path / "HybridAgent",
        checkpoint_path=tmp_path / "ckpt",
        exit_rule="lm_head_argmax",
        min_latent_steps=4,
        max_latent_steps=200,
        max_tool_calls=5,
        max_context_tokens=32768,
    )
    return ha.HybridAgentConfig(**{**base, **kw})


def test_hybrid_pins():
    assert ha.UPSTREAM_COMMIT == "1b41cebbd2388d083ee1820af421b7f9e24affb5"
    assert ha.CHECKPOINT == "togethercomputer/HybridAgent-8B-Agentic"
    assert ha.CHECKPOINT_REVISION == "13a5c61b1880d7bcc2fac2e28d478809722beb8f"


def test_hybrid_config_has_no_implicit_defaults(tmp_path):
    with pytest.raises(TypeError):
        ha.HybridAgentConfig(checkout_path=tmp_path, checkpoint_path=tmp_path)
    with pytest.raises(ValueError):
        hybrid_config(tmp_path, min_latent_steps=10, max_latent_steps=5)
    with pytest.raises(ValueError):
        hybrid_config(tmp_path, exit_rule="whatever")


def test_hybrid_probe_reports_everything_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ha.importlib.util, "find_spec", lambda name: None)
    a = ha.HybridAgentAdapter(hybrid_config(tmp_path))
    st = a.probe()
    assert not st.available
    assert any("no git checkout" in r for r in st.reasons)
    assert any("never auto-downloaded" in r for r in st.reasons)
    assert any("torch is not installed" in r for r in st.reasons)
    assert not (tmp_path / "ckpt").exists(), "probe must not create or fetch the checkpoint"
    with pytest.raises(WorkerUnavailable):
        a.generate(req(revision=ha.CHECKPOINT_REVISION))


def test_hybrid_probe_on_this_machine_never_downloads(tmp_path):
    # Real find_spec; with or without torch the probe must stay offline and report unavailable here.
    st = ha.HybridAgentAdapter(hybrid_config(tmp_path)).probe()
    assert not st.available and st.reason


def write_checkout(root: Path, commit: str, packed: bool):
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    if packed:
        (git / "packed-refs").write_text(f"# pack-refs\n{commit} refs/heads/main\n")
    else:
        (git / "refs" / "heads" / "main").write_text(commit + "\n")


@pytest.mark.parametrize("packed", [False, True])
def test_hybrid_checkout_commit_check(tmp_path, monkeypatch, packed):
    monkeypatch.setattr(ha.importlib.util, "find_spec", lambda name: None)
    write_checkout(tmp_path / "HybridAgent", "0" * 40, packed)
    (tmp_path / "ckpt").mkdir()
    (tmp_path / "ckpt" / "config.json").write_text("{}")
    st = ha.HybridAgentAdapter(hybrid_config(tmp_path)).probe()
    assert st.reasons == (f"checkout is at {'0' * 40}, pinned {ha.UPSTREAM_COMMIT}", "torch is not installed")


def fake_torch(available, gib):
    props = types.SimpleNamespace(total_memory=int(gib * 2**30))
    cuda = types.SimpleNamespace(is_available=lambda: available, device_count=lambda: 1, get_device_properties=lambda i: props)
    return types.SimpleNamespace(cuda=cuda)


def test_gpu_status():
    assert ha.gpu_status(fake_torch(False, 80)) == ["CUDA is not available"]
    assert "need >= 24" in ha.gpu_status(fake_torch(True, 16))[0]
    assert ha.gpu_status(fake_torch(True, 24)) == []


def test_hybrid_rejects_requests_beyond_config(tmp_path):
    a = ha.HybridAgentAdapter(hybrid_config(tmp_path))
    with pytest.raises(ValueError):
        a.generate(req(revision="other"))
    with pytest.raises(ValueError):
        a.generate(req(revision=ha.CHECKPOINT_REVISION, max_latent_steps=500))


# --- hosted -----------------------------------------------------------------

KEY_ENV = "FRONTIER_TEST_HOSTED_KEY"


def hosted_config(**kw):
    base = dict(
        provider="fake",
        model="m",
        model_revision="r1",
        api_key_env=KEY_ENV,
        max_usd=0.01,
        max_tokens=10_000,
        usd_per_input_token=1e-5,
        usd_per_output_token=2e-5,
        max_context_tokens=8192,
    )
    return HostedConfig(**{**base, **kw})


class Transport:
    def __init__(self):
        self.calls = []

    def __call__(self, payload, key):
        self.calls.append((payload, key))
        return {"text": "hi", "input_tokens": 10, "output_tokens": 5, "artifact_body": {"source": "x"}}


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan")])
def test_hosted_requires_positive_budget(bad):
    with pytest.raises(ValueError):
        hosted_config(max_usd=bad)


def test_hosted_reads_key_from_named_env_only(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    t = Transport()
    a = HostedAdapter(hosted_config(), t)
    assert not a.probe().available
    with pytest.raises(WorkerUnavailable):
        a.generate(req())
    assert t.calls == []
    monkeypatch.setenv(KEY_ENV, "k-test")
    r = a.generate(req())
    assert t.calls[0][1] == "k-test" and "k-test" not in repr(t.calls[0][0])
    assert r.usage.usd == pytest.approx(10 * 1e-5 + 5 * 2e-5)
    assert a.guard.spent_usd == pytest.approx(r.usage.usd)


def test_hosted_budget_refuses_before_transport(monkeypatch):
    monkeypatch.setenv(KEY_ENV, "k")
    t = Transport()
    a = HostedAdapter(hosted_config(max_usd=0.001), t)
    # worst case: 50 bytes * 1e-5 + 100 * 2e-5 = 0.0025 > 0.001
    with pytest.raises(BudgetExceeded):
        a.generate(req())
    assert t.calls == []
