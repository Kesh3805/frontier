"""Generate the exp-002 experiment configs (committed alongside their output)."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

R2 = dict(
    problems=50, approaches_min=1, approaches_max=1, chain_min=1, chain_max=1, shared_lemma_prob=0.0,
    dead_fraction=0.11, p_alpha=0.38, p_beta=0.17, cost_log_mean=0.0, cost_log_sd=0.5, attempt_cost_sd=0.3,
    failure_cost_mult=1.5, hint_noise=1.0,
)
R3 = dict(R2, dead_fraction=0.3, p_alpha=0.27, p_beta=0.91)
RUN = dict(seed=0, workers=8, budget_units=0.0, attempt_cap_units=8.0, verify_cost_units=0.25, crash_prob=0.02,
           max_attempts_per_task=64, max_parallel_per_task=1, prior_cost=1.0, policy={"kind": "round_robin"})
POLICIES = [
    {"kind": "round_robin"},
    {"kind": "greedy_prior"},
    {"kind": "thompson", "prior_strength": 0.5, "use_hints": True},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": True},
    {"kind": "thompson", "prior_strength": 8.0, "use_hints": True},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": False},
    {"kind": "oracle_index"},
]
LAMBDAS = (0.0, 0.5, 1.0)


def regimes(name, env):
    return [{"name": f"{name}-det{lam}", "env": dict(env, dead_hint_detection=lam)} for lam in LAMBDAS]


def write(name, regs, budget):
    cfg = {"schema_version": "0.1", "experiment_id": f"exp-002-{name}", "regimes": regs, "policies": POLICIES,
           "seed_start": 1, "seeds": 200, "run": dict(RUN, budget_units=budget)}
    with open(HERE / f"{name}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


write("b600", regimes("R2", R2) + regimes("R3", R3), 600.0)
write("b1200", regimes("R2", R2), 1200.0)
