//! Scheduling policies: which runnable research task gets the next attempt.
//!
//! A policy sees a [`SchedView`] built only from past receipts and charges.
//! Ground-truth success rates (`TaskStats::oracle`) are populated only for
//! policies that declare `needs_oracle()`, and those are simulation-only
//! diagnostics. All tie-breaks are by lowest index, so given the same view
//! sequence and RNG stream a policy is deterministic.

use frontier_core::SplitMix64;
use serde::{Deserialize, Serialize};

pub type TaskIdx = usize;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct OracleInfo {
    pub p_success: f64,
    pub mean_cost: f64,
}

#[derive(Clone, Debug, Default)]
pub struct TaskStats {
    pub problem: usize,
    /// Finished attempts that were informative about success (passed,
    /// rejected or timed out). Infrastructure crashes are excluded.
    pub attempts: u32,
    pub failures: u32,
    pub in_flight: u32,
    pub verified: bool,
    pub cost_sum: f64,
    pub cost_n: u32,
    /// A-priori success estimate supplied with the task (e.g. a difficulty
    /// model). May be badly wrong.
    pub prior_hint: f64,
    pub oracle: Option<OracleInfo>,
}

/// One way of solving a problem: a terminal task plus all its unverified
/// prerequisites.
#[derive(Clone, Debug)]
pub struct Approach {
    pub problem: usize,
    pub tasks: Vec<TaskIdx>,
}

#[derive(Clone, Debug, Default)]
pub struct ProblemStats {
    pub solved: bool,
    pub closed: bool,
    /// Units committed or reserved on this problem so far.
    pub spent: f64,
    pub attempts: u32,
    pub verified_tasks: u32,
}

pub struct SchedView<'a> {
    pub tasks: &'a [TaskStats],
    pub approaches: &'a [Approach],
    pub problems: &'a [ProblemStats],
    /// Tasks that may receive an attempt now, sorted ascending.
    pub runnable: &'a [TaskIdx],
    pub total_budget: f64,
    /// Units the runner will reserve for one attempt (worst case).
    pub reservation: f64,
    /// Prior mean cost of one attempt, used before any cost is observed.
    pub prior_cost: f64,
}

impl SchedView<'_> {
    fn is_runnable(&self, t: TaskIdx) -> bool {
        self.runnable.binary_search(&t).is_ok()
    }

    /// Mean charged cost per finished attempt: task-level, else pooled, else prior.
    pub fn cost_estimate(&self, t: TaskIdx) -> f64 {
        let s = &self.tasks[t];
        if s.cost_n > 0 {
            return s.cost_sum / s.cost_n as f64;
        }
        let (sum, n) = self.tasks.iter().fold((0.0, 0u32), |(a, b), s| (a + s.cost_sum, b + s.cost_n));
        if n > 0 { sum / n as f64 } else { self.prior_cost }
    }
}

pub trait Policy {
    fn name(&self) -> String;
    fn needs_oracle(&self) -> bool {
        false
    }
    /// Pick a runnable task, or `None` to leave the free worker idle.
    fn select(&mut self, view: &SchedView, rng: &mut SplitMix64) -> Option<TaskIdx>;
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum PolicyConfig {
    /// Lowest-numbered problem first, work-conserving.
    Fifo,
    /// Strict equal per-problem budget slices; unused slices are not redistributed.
    FixedSlice,
    /// Work-conserving round-robin over problems, then over their runnable tasks.
    RoundRobin,
    Random,
    /// Expected-remaining-cost index from prior hints only; never learns.
    GreedyPrior,
    /// Successive elimination over problems (after Zuo et al., arXiv 2506.12721;
    /// an adaptation, not a reproduction).
    Elimination {
        min_attempts: u32,
        threshold: f64,
    },
    /// Optimistic expected-remaining-cost index with Beta posteriors.
    Ucb {
        prior_strength: f64,
        use_hints: bool,
        beta: f64,
    },
    /// Thompson-sampled expected-remaining-cost index with Beta posteriors.
    Thompson {
        prior_strength: f64,
        use_hints: bool,
    },
    /// Uses ground truth. Simulation-only diagnostic, not an upper bound.
    OracleIndex,
}

impl PolicyConfig {
    pub fn build(&self) -> Box<dyn Policy> {
        match *self {
            PolicyConfig::Fifo => Box::new(Fifo),
            PolicyConfig::FixedSlice => Box::new(RoundRobin { strict_slices: true, ..RoundRobin::default() }),
            PolicyConfig::RoundRobin => Box::new(RoundRobin::default()),
            PolicyConfig::Random => Box::new(RandomPolicy),
            PolicyConfig::GreedyPrior => Box::new(IndexPolicy { estimator: Estimator::Prior, label: "greedy_prior".into() }),
            PolicyConfig::Elimination { min_attempts, threshold } => Box::new(Elimination { min_attempts, threshold }),
            PolicyConfig::Ucb { prior_strength, use_hints, beta } => Box::new(IndexPolicy {
                estimator: Estimator::Ucb { prior_strength, use_hints, beta },
                label: format!("ucb(k={prior_strength},hints={use_hints},beta={beta})"),
            }),
            PolicyConfig::Thompson { prior_strength, use_hints } => Box::new(IndexPolicy {
                estimator: Estimator::Thompson { prior_strength, use_hints },
                label: format!("thompson(k={prior_strength},hints={use_hints})"),
            }),
            PolicyConfig::OracleIndex => Box::new(IndexPolicy { estimator: Estimator::Oracle, label: "oracle_index".into() }),
        }
    }
}

pub struct Fifo;

impl Policy for Fifo {
    fn name(&self) -> String {
        "fifo".into()
    }
    fn select(&mut self, view: &SchedView, _rng: &mut SplitMix64) -> Option<TaskIdx> {
        view.runnable.iter().copied().min_by_key(|&t| (view.tasks[t].problem, t))
    }
}

pub struct RandomPolicy;

impl Policy for RandomPolicy {
    fn name(&self) -> String {
        "random".into()
    }
    fn select(&mut self, view: &SchedView, rng: &mut SplitMix64) -> Option<TaskIdx> {
        if view.runnable.is_empty() {
            return None;
        }
        Some(view.runnable[rng.below(view.runnable.len() as u64) as usize])
    }
}

#[derive(Default)]
pub struct RoundRobin {
    strict_slices: bool,
    next_problem: usize,
    next_task: Vec<usize>,
}

impl Policy for RoundRobin {
    fn name(&self) -> String {
        if self.strict_slices { "fixed_slice".into() } else { "round_robin".into() }
    }

    fn select(&mut self, view: &SchedView, _rng: &mut SplitMix64) -> Option<TaskIdx> {
        let n = view.problems.len();
        if n == 0 {
            return None;
        }
        if self.next_task.len() < n {
            self.next_task.resize(n, 0);
        }
        let slice = view.total_budget / n as f64;
        for k in 0..n {
            let p = (self.next_problem + k) % n;
            if self.strict_slices && view.problems[p].spent + view.reservation > slice + 1e-9 {
                continue;
            }
            let mine: Vec<TaskIdx> = view.runnable.iter().copied().filter(|&t| view.tasks[t].problem == p).collect();
            if mine.is_empty() {
                continue;
            }
            let pick = mine[self.next_task[p] % mine.len()];
            self.next_task[p] = self.next_task[p].wrapping_add(1);
            self.next_problem = (p + 1) % n;
            return Some(pick);
        }
        None
    }
}

/// Successive elimination over problems: problems whose optimistic per-attempt
/// success bound drops below `threshold` after `min_attempts` stop receiving
/// compute; the rest share it evenly by fewest attempts first.
pub struct Elimination {
    min_attempts: u32,
    threshold: f64,
}

impl Policy for Elimination {
    fn name(&self) -> String {
        format!("elimination(n={},thr={})", self.min_attempts, self.threshold)
    }

    fn select(&mut self, view: &SchedView, _rng: &mut SplitMix64) -> Option<TaskIdx> {
        let total_attempts: u32 = view.problems.iter().map(|p| p.attempts).sum();
        let log_term = (2.0 * (total_attempts.max(2) as f64).ln()).max(0.0);
        let active = |p: usize| {
            let s = &view.problems[p];
            if s.attempts < self.min_attempts {
                return true;
            }
            let n = s.attempts as f64;
            let mean = s.verified_tasks as f64 / n;
            mean + (log_term / n).sqrt() >= self.threshold
        };
        let mut best: Option<(u32, TaskIdx)> = None;
        for &t in view.runnable {
            let p = view.tasks[t].problem;
            if !active(p) {
                continue;
            }
            let key = view.problems[p].attempts + view.tasks.iter().filter(|s| s.problem == p).map(|s| s.in_flight).sum::<u32>();
            if best.is_none_or(|(k, _)| key < k) {
                best = Some((key, t));
            }
        }
        best.map(|(_, t)| t)
    }
}

#[derive(Clone, Debug)]
enum Estimator {
    Prior,
    Ucb { prior_strength: f64, use_hints: bool, beta: f64 },
    Thompson { prior_strength: f64, use_hints: bool },
    Oracle,
}

fn beta_params(s: &TaskStats, prior_strength: f64, use_hints: bool) -> (f64, f64) {
    let m = if use_hints { s.prior_hint.clamp(1e-3, 1.0 - 1e-3) } else { 0.5 };
    let a = prior_strength * m + if s.verified { 1.0 } else { 0.0 };
    let b = prior_strength * (1.0 - m) + s.failures as f64;
    (a, b)
}

/// Chooses the approach with the smallest estimated expected cost to finish
/// (sum over remaining tasks of cost / p-success, i.e. geometric retries) and
/// dispatches its lowest-numbered runnable task.
pub struct IndexPolicy {
    estimator: Estimator,
    label: String,
}

impl IndexPolicy {
    fn estimates(&self, view: &SchedView, rng: &mut SplitMix64) -> Vec<(f64, f64)> {
        view.tasks
            .iter()
            .enumerate()
            .map(|(t, s)| match &self.estimator {
                Estimator::Prior => (s.prior_hint, view.prior_cost),
                Estimator::Oracle => {
                    let o = s.oracle.expect("oracle policy run without oracle data");
                    (o.p_success, o.mean_cost)
                }
                Estimator::Ucb { prior_strength, use_hints, beta } => {
                    let (a, b) = beta_params(s, *prior_strength, *use_hints);
                    let mean = a / (a + b);
                    let sd = (a * b / ((a + b).powi(2) * (a + b + 1.0))).sqrt();
                    ((mean + beta * sd).min(1.0), view.cost_estimate(t))
                }
                Estimator::Thompson { prior_strength, use_hints } => {
                    let (a, b) = beta_params(s, *prior_strength, *use_hints);
                    (rng.beta(a, b), view.cost_estimate(t))
                }
            })
            .collect()
    }
}

impl Policy for IndexPolicy {
    fn name(&self) -> String {
        self.label.clone()
    }

    fn needs_oracle(&self) -> bool {
        matches!(self.estimator, Estimator::Oracle)
    }

    fn select(&mut self, view: &SchedView, rng: &mut SplitMix64) -> Option<TaskIdx> {
        if view.runnable.is_empty() {
            return None;
        }
        let est = self.estimates(view, rng);
        let mut best: Option<(f64, TaskIdx)> = None;
        for a in view.approaches {
            if view.problems[a.problem].closed {
                continue;
            }
            let remaining = a.tasks.iter().filter(|&&t| !view.tasks[t].verified);
            let Some(next) = a.tasks.iter().copied().find(|&t| view.is_runnable(t)) else { continue };
            let erc: f64 = remaining.map(|&t| est[t].1 / est[t].0.max(1e-9)).sum();
            if best.is_none_or(|(b, bt)| erc < b || (erc == b && next < bt)) {
                best = Some((erc, next));
            }
        }
        best.map(|(_, t)| t)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn view_fixture() -> (Vec<TaskStats>, Vec<Approach>, Vec<ProblemStats>) {
        // Problem 0: one task with poor hint. Problem 1: two-task chain, good hints.
        let tasks = vec![
            TaskStats { problem: 0, prior_hint: 0.05, oracle: Some(OracleInfo { p_success: 0.9, mean_cost: 1.0 }), ..Default::default() },
            TaskStats { problem: 1, prior_hint: 0.8, oracle: Some(OracleInfo { p_success: 0.01, mean_cost: 1.0 }), ..Default::default() },
            TaskStats { problem: 1, prior_hint: 0.8, oracle: Some(OracleInfo { p_success: 0.01, mean_cost: 1.0 }), ..Default::default() },
        ];
        let approaches = vec![Approach { problem: 0, tasks: vec![0] }, Approach { problem: 1, tasks: vec![1, 2] }];
        let problems = vec![ProblemStats::default(), ProblemStats::default()];
        (tasks, approaches, problems)
    }

    fn view<'a>(t: &'a [TaskStats], a: &'a [Approach], p: &'a [ProblemStats], r: &'a [TaskIdx]) -> SchedView<'a> {
        SchedView { tasks: t, approaches: a, problems: p, runnable: r, total_budget: 100.0, reservation: 5.0, prior_cost: 1.0 }
    }

    #[test]
    fn index_policies_follow_their_estimates() {
        let (t, a, p) = view_fixture();
        let r = [0, 1];
        let mut rng = SplitMix64::new(1);
        // Prior hints favour problem 1 (2/0.8 = 2.5 < 1/0.05 = 20).
        assert_eq!(PolicyConfig::GreedyPrior.build().select(&view(&t, &a, &p, &r), &mut rng), Some(1));
        // Ground truth favours problem 0.
        let mut oracle = PolicyConfig::OracleIndex.build();
        assert!(oracle.needs_oracle());
        assert_eq!(oracle.select(&view(&t, &a, &p, &r), &mut rng), Some(0));
    }

    #[test]
    fn learning_overrides_misleading_hints() {
        let (mut t, a, p) = view_fixture();
        t[1].failures = 40;
        t[1].attempts = 40;
        t[1].cost_n = 40;
        t[1].cost_sum = 40.0;
        let r = [0, 1];
        let mut ucb = PolicyConfig::Ucb { prior_strength: 2.0, use_hints: true, beta: 1.0 }.build();
        assert_eq!(ucb.select(&view(&t, &a, &p, &r), &mut SplitMix64::new(3)), Some(0));
    }

    #[test]
    fn round_robin_rotates_and_fixed_slice_caps() {
        let (t, a, mut p) = view_fixture();
        let r = [0, 1];
        let mut rr = PolicyConfig::RoundRobin.build();
        let mut rng = SplitMix64::new(0);
        let picks: Vec<_> = (0..4).map(|_| rr.select(&view(&t, &a, &p, &r), &mut rng).unwrap()).collect();
        assert_eq!(picks, vec![0, 1, 0, 1]);
        p[0].spent = 48.0; // slice = 50, reservation 5 => problem 0 is out of slice
        let mut fixed = PolicyConfig::FixedSlice.build();
        assert_eq!(fixed.select(&view(&t, &a, &p, &r), &mut rng), Some(1));
        assert_eq!(fixed.select(&view(&t, &a, &p, &r), &mut rng), Some(1));
        p[1].spent = 48.0;
        assert_eq!(fixed.select(&view(&t, &a, &p, &r), &mut rng), None, "fixed slices do not redistribute");
    }

    #[test]
    fn elimination_drops_hopeless_problems() {
        let (t, a, mut p) = view_fixture();
        p[0].attempts = 200;
        p[1].attempts = 5;
        p[1].verified_tasks = 1;
        let r = [0, 1];
        let mut e = PolicyConfig::Elimination { min_attempts: 10, threshold: 0.2 }.build();
        assert_eq!(e.select(&view(&t, &a, &p, &r), &mut SplitMix64::new(0)), Some(1));
    }

    #[test]
    fn policies_only_return_runnable_tasks() {
        let (t, a, p) = view_fixture();
        let r = [1];
        let configs = [
            PolicyConfig::Fifo,
            PolicyConfig::RoundRobin,
            PolicyConfig::Random,
            PolicyConfig::GreedyPrior,
            PolicyConfig::Thompson { prior_strength: 2.0, use_hints: true },
            PolicyConfig::OracleIndex,
        ];
        for c in configs {
            let mut pol = c.build();
            for s in 0..20 {
                let got = pol.select(&view(&t, &a, &p, &r), &mut SplitMix64::new(s));
                assert_eq!(got, Some(1), "{}", pol.name());
            }
        }
    }
}
