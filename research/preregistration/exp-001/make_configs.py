"""Generate the exp-001 experiment configs (committed alongside their output)."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

BASE_ENV = dict(
    problems=50, approaches_min=1, approaches_max=1, chain_min=1, chain_max=1, shared_lemma_prob=0.0,
    dead_fraction=0.11, p_alpha=0.38, p_beta=0.17, cost_log_mean=0.0, cost_log_sd=0.5, attempt_cost_sd=0.3,
    failure_cost_mult=1.5, hint_noise=1.0,
)
R2 = dict(BASE_ENV)
R3 = dict(BASE_ENV, dead_fraction=0.3, p_alpha=0.27, p_beta=0.91)
R5 = dict(BASE_ENV, approaches_min=1, approaches_max=3, chain_min=1, chain_max=4, shared_lemma_prob=0.5)

RUN = dict(seed=0, workers=8, budget_units=0.0, attempt_cap_units=8.0, verify_cost_units=0.25, crash_prob=0.02,
           max_attempts_per_task=64, max_parallel_per_task=1, prior_cost=1.0, policy={"kind": "round_robin"})


def thompson(k, hints=True):
    return {"kind": "thompson", "prior_strength": k, "use_hints": hints}


RR, GREEDY, ORACLE = {"kind": "round_robin"}, {"kind": "greedy_prior"}, {"kind": "oracle_index"}


def write(name, regimes, policies, budget):
    cfg = {"schema_version": "0.1", "experiment_id": f"exp-001-{name}", "regimes": regimes, "policies": policies,
           "seed_start": 1, "seeds": 200, "run": dict(RUN, budget_units=budget)}
    with open(HERE / f"{name}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


# Part A: mechanism of the R2-moderate loss.
a_regimes = [{"name": f"A-noise{n}", "env": dict(R2, hint_noise=float(n))} for n in (0, 1, 2)]
a_policies = [RR, GREEDY, thompson(0.5), thompson(2.0), thompson(8.0), thompson(2.0, False), ORACLE]
for b in (300, 600, 1200):
    write(f"A-b{b}", a_regimes, a_policies, float(b))

# Part B: correlated attempt failures.
b_regimes = [{"name": f"B-{rn}-rho{r}", "env": dict(env, failure_stickiness=r)}
             for rn, env in (("R2", R2), ("R3", R3), ("R5", R5)) for r in (0.0, 0.5, 0.9)]
b_policies = [RR, GREEDY, thompson(2.0), thompson(2.0, False), ORACLE]
for label, b in (("scarce", 150.0), ("moderate", 600.0)):
    write(f"B-{label}", b_regimes, b_policies, b)

# Part C: imperfect verifiers (distinct solution content in every cell).
c_regimes = [{"name": f"C-{rn}-fnr{fnr}-fpr{fpr}",
              "env": dict(env, verifier_fnr=fnr, verifier_fpr=fpr, distinct_solutions=True)}
             for rn, env in (("R2", R2), ("R3", R3), ("R5", R5)) for fnr in (0.0, 0.2) for fpr in (0.0, 0.02)]
c_policies = [RR, GREEDY, thompson(2.0), thompson(2.0, False)]
write("C-moderate", c_regimes, c_policies, 600.0)
