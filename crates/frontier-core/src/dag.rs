//! Research task graph: dependency validation, deduplication and state.

use std::collections::{BTreeMap, BTreeSet};

use crate::task::{IllegalTransition, TaskDef, TaskState};

pub type TaskIdx = usize;

#[derive(Debug, PartialEq, thiserror::Error)]
pub enum GraphError {
    #[error("duplicate task id {0}")]
    DuplicateId(String),
    #[error("task {task} depends on unknown task {dep}")]
    UnknownDependency { task: String, dep: String },
    #[error("task {task} (problem {problem}) depends on {dep} from another problem")]
    CrossProblemDependency { task: String, problem: String, dep: String },
    #[error("tasks {a} and {b} share signature {signature:?} but have different prerequisites")]
    SignatureConflict { a: String, b: String, signature: String },
    #[error("dependency cycle through task {0}")]
    Cycle(String),
    #[error(transparent)]
    Transition(#[from] IllegalTransition<TaskState>),
}

#[derive(Clone, Debug)]
pub struct TaskNode {
    pub def: TaskDef,
    pub deps: Vec<TaskIdx>,
    pub dependents: Vec<TaskIdx>,
    state: TaskState,
}

impl TaskNode {
    pub fn state(&self) -> TaskState {
        self.state
    }
}

#[derive(Clone, Debug)]
pub struct TaskGraph {
    nodes: Vec<TaskNode>,
    by_id: BTreeMap<String, TaskIdx>,
    /// Task ids that were merged into an existing node by signature.
    merged: Vec<(String, TaskIdx)>,
}

impl TaskGraph {
    /// Validate and build. Tasks of one problem with equal signatures are
    /// merged (the first definition wins) provided their prerequisites agree.
    pub fn build(defs: Vec<TaskDef>) -> Result<Self, GraphError> {
        let mut seen = BTreeSet::new();
        for d in &defs {
            if !seen.insert(d.task_id.clone()) {
                return Err(GraphError::DuplicateId(d.task_id.clone()));
            }
        }
        // Map every id to the id of its canonical (first) definition.
        let mut canon_of_sig: BTreeMap<(String, String), String> = BTreeMap::new();
        let mut canon: BTreeMap<String, String> = BTreeMap::new();
        for d in &defs {
            let key = (d.problem_id.clone(), d.signature.clone());
            let c = canon_of_sig.entry(key).or_insert_with(|| d.task_id.clone()).clone();
            canon.insert(d.task_id.clone(), c);
        }
        let problem_of: BTreeMap<&str, &str> = defs.iter().map(|d| (d.task_id.as_str(), d.problem_id.as_str())).collect();
        let resolve = |d: &TaskDef| -> Result<BTreeSet<String>, GraphError> {
            d.depends_on
                .iter()
                .map(|dep| {
                    let c = canon.get(dep).ok_or_else(|| GraphError::UnknownDependency { task: d.task_id.clone(), dep: dep.clone() })?;
                    if problem_of[dep.as_str()] != d.problem_id {
                        return Err(GraphError::CrossProblemDependency {
                            task: d.task_id.clone(),
                            problem: d.problem_id.clone(),
                            dep: dep.clone(),
                        });
                    }
                    Ok(c.clone())
                })
                .collect()
        };

        let mut nodes: Vec<TaskNode> = Vec::new();
        let mut by_id = BTreeMap::new();
        let mut canon_deps: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        let mut merged = Vec::new();
        for d in &defs {
            let deps = resolve(d)?;
            let c = &canon[&d.task_id];
            if c != &d.task_id {
                if canon_deps[c] != deps {
                    return Err(GraphError::SignatureConflict { a: c.clone(), b: d.task_id.clone(), signature: d.signature.clone() });
                }
                merged.push((d.task_id.clone(), by_id[c]));
                continue;
            }
            canon_deps.insert(c.clone(), deps);
            by_id.insert(d.task_id.clone(), nodes.len());
            nodes.push(TaskNode { def: d.clone(), deps: vec![], dependents: vec![], state: TaskState::Pending });
        }
        for (alias, idx) in &merged {
            by_id.insert(alias.clone(), *idx);
        }
        for i in 0..nodes.len() {
            let deps: Vec<TaskIdx> = canon_deps[&nodes[i].def.task_id].iter().map(|c| by_id[c]).collect();
            for &d in &deps {
                nodes[d].dependents.push(i);
            }
            nodes[i].deps = deps;
        }
        let mut g = TaskGraph { nodes, by_id, merged };
        g.check_acyclic()?;
        for i in 0..g.nodes.len() {
            if g.nodes[i].deps.is_empty() {
                g.nodes[i].state = TaskState::Eligible;
            }
        }
        Ok(g)
    }

    fn check_acyclic(&self) -> Result<(), GraphError> {
        // Kahn's algorithm; anything left over sits on a cycle.
        let mut indeg: Vec<usize> = self.nodes.iter().map(|n| n.deps.len()).collect();
        let mut stack: Vec<TaskIdx> = (0..self.nodes.len()).filter(|&i| indeg[i] == 0).collect();
        let mut visited = 0;
        while let Some(i) = stack.pop() {
            visited += 1;
            for &j in &self.nodes[i].dependents {
                indeg[j] -= 1;
                if indeg[j] == 0 {
                    stack.push(j);
                }
            }
        }
        if visited == self.nodes.len() {
            Ok(())
        } else {
            let i = (0..self.nodes.len()).find(|&i| indeg[i] > 0).expect("cycle member");
            Err(GraphError::Cycle(self.nodes[i].def.task_id.clone()))
        }
    }

    pub fn len(&self) -> usize {
        self.nodes.len()
    }

    pub fn is_empty(&self) -> bool {
        self.nodes.is_empty()
    }

    pub fn node(&self, i: TaskIdx) -> &TaskNode {
        &self.nodes[i]
    }

    pub fn nodes(&self) -> &[TaskNode] {
        &self.nodes
    }

    pub fn index_of(&self, task_id: &str) -> Option<TaskIdx> {
        self.by_id.get(task_id).copied()
    }

    pub fn merged(&self) -> &[(String, TaskIdx)] {
        &self.merged
    }

    pub fn eligible(&self) -> impl Iterator<Item = TaskIdx> + '_ {
        (0..self.nodes.len()).filter(|&i| self.nodes[i].state == TaskState::Eligible)
    }

    fn set(&mut self, i: TaskIdx, to: TaskState) -> Result<(), GraphError> {
        let from = self.nodes[i].state;
        if !from.can_transition_to(to) {
            return Err(IllegalTransition { from, to }.into());
        }
        self.nodes[i].state = to;
        Ok(())
    }

    /// Mark a task verified. Returns dependents that became eligible.
    pub fn mark_verified(&mut self, i: TaskIdx) -> Result<Vec<TaskIdx>, GraphError> {
        self.set(i, TaskState::Verified)?;
        let mut unlocked = vec![];
        for j in self.nodes[i].dependents.clone() {
            if self.nodes[j].state == TaskState::Pending && self.nodes[j].deps.iter().all(|&d| self.nodes[d].state == TaskState::Verified) {
                self.set(j, TaskState::Eligible)?;
                unlocked.push(j);
            }
        }
        Ok(unlocked)
    }

    /// Mark a task exhausted and abandon everything that depended on it.
    /// Returns the abandoned tasks.
    pub fn mark_exhausted(&mut self, i: TaskIdx) -> Result<Vec<TaskIdx>, GraphError> {
        self.set(i, TaskState::Exhausted)?;
        let mut abandoned = vec![];
        let mut stack = self.nodes[i].dependents.clone();
        while let Some(j) = stack.pop() {
            if !self.nodes[j].state.is_final() {
                self.set(j, TaskState::Abandoned)?;
                abandoned.push(j);
                stack.extend(self.nodes[j].dependents.iter().copied());
            }
        }
        Ok(abandoned)
    }

    /// Abandon all unfinished tasks of a problem (e.g. once it is solved).
    pub fn abandon_problem(&mut self, problem_id: &str) -> Result<Vec<TaskIdx>, GraphError> {
        let mut out = vec![];
        for i in 0..self.nodes.len() {
            if self.nodes[i].def.problem_id == problem_id && !self.nodes[i].state.is_final() {
                self.set(i, TaskState::Abandoned)?;
                out.push(i);
            }
        }
        Ok(out)
    }

    /// Whether every terminal task of the problem is final and none verified.
    pub fn problem_dead(&self, problem_id: &str) -> bool {
        let mut terminals = self.nodes.iter().filter(|n| n.def.problem_id == problem_id && n.def.terminal).peekable();
        terminals.peek().is_some() && terminals.all(|n| matches!(n.state, TaskState::Exhausted | TaskState::Abandoned))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::task::TaskKind;

    fn t(id: &str, deps: &[&str], sig: &str, terminal: bool) -> TaskDef {
        TaskDef {
            task_id: id.into(),
            problem_id: "p".into(),
            kind: if terminal { TaskKind::Goal } else { TaskKind::ProofObligation },
            depends_on: deps.iter().map(|s| s.to_string()).collect(),
            signature: sig.into(),
            terminal,
        }
    }

    #[test]
    fn eligibility_follows_verification() {
        let mut g = TaskGraph::build(vec![t("a", &[], "a", false), t("b", &["a"], "b", false), t("c", &["a", "b"], "c", true)]).unwrap();
        assert_eq!(g.eligible().collect::<Vec<_>>(), vec![0]);
        assert_eq!(g.mark_verified(0).unwrap(), vec![1]);
        assert_eq!(g.node(2).state(), TaskState::Pending);
        assert_eq!(g.mark_verified(1).unwrap(), vec![2]);
        assert!(g.mark_verified(0).is_err(), "double verification is illegal");
    }

    #[test]
    fn rejects_cycles_unknown_and_duplicates() {
        assert!(matches!(TaskGraph::build(vec![t("a", &["b"], "a", false), t("b", &["a"], "b", true)]), Err(GraphError::Cycle(_))));
        assert!(matches!(TaskGraph::build(vec![t("a", &["zz"], "a", true)]), Err(GraphError::UnknownDependency { .. })));
        assert!(matches!(TaskGraph::build(vec![t("a", &[], "a", true), t("a", &[], "b", true)]), Err(GraphError::DuplicateId(_))));
        let mut other = t("x", &[], "x", false);
        other.problem_id = "q".into();
        assert!(matches!(TaskGraph::build(vec![other, t("a", &["x"], "a", true)]), Err(GraphError::CrossProblemDependency { .. })));
    }

    #[test]
    fn signature_dedup_shares_lemmas() {
        // Two approaches both need lemma L; they are merged into one node.
        let g = TaskGraph::build(vec![
            t("A.L", &[], "lemma L", false),
            t("A.goal", &["A.L"], "goal via A", true),
            t("B.L", &[], "lemma L", false),
            t("B.goal", &["B.L"], "goal via B", true),
        ])
        .unwrap();
        assert_eq!(g.len(), 3);
        assert_eq!(g.index_of("B.L"), g.index_of("A.L"));
        assert_eq!(g.node(g.index_of("A.L").unwrap()).dependents.len(), 2);
        assert!(matches!(
            TaskGraph::build(vec![t("x", &[], "x", false), t("a", &[], "s", false), t("b", &["x"], "s", true)]),
            Err(GraphError::SignatureConflict { .. })
        ));
    }

    #[test]
    fn exhaustion_prunes_dependents() {
        let mut g = TaskGraph::build(vec![t("a", &[], "a", false), t("b", &["a"], "b", true), t("c", &[], "c", true)]).unwrap();
        assert_eq!(g.mark_exhausted(0).unwrap(), vec![1]);
        assert!(!g.problem_dead("p"));
        g.mark_exhausted(2).unwrap();
        assert!(g.problem_dead("p"));
    }
}
