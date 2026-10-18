//! Resumable symbolic search. Forecasts do not grant native rule qualification.
use super::*;
use ygo_engine_adapter::{CallJournal, LedgerStats};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PersistedSearch {
    version: u16,
    search: SearchCheckpoint,
    budget: LedgerStats,
    charged_sequence: String,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchCheckpoint {
    version: u16,
    context: String,
    start: String,
    depth: usize,
    cursor: usize,
    frontier: Vec<Node>,
    next: Vec<Node>,
    output: PartialPlans,
    unknowns: BTreeSet<String>,
    gaps: BTreeSet<String>,
    plan_ids: BTreeSet<String>,
    finished: bool,
}

pub struct ResumableSearch<'a> {
    state: SearchCheckpoint,
    cat: &'a Catalog,
    pack: &'a FirstTurnKnowledge,
    goal: &'a Goal,
    sensitive: BTreeSet<String>,
}

impl<'a> ResumableSearch<'a> {
    pub fn begin(
        initial: &CausalState,
        cat: &'a Catalog,
        pack: &'a FirstTurnKnowledge,
        goal: &'a Goal,
        limits: &SearchLimits,
    ) -> Result<Self, String> {
        initial.validate(cat)?;
        pack.validate()?;
        goal.validate()?;
        if !(1..=8).contains(&limits.candidates)
            || !(1..=5000).contains(&limits.expansions)
            || !(1..=32).contains(&limits.frontier)
            || !(1..=64).contains(&limits.steps)
        {
            return Err("invalid bounded first-turn limits".into());
        }
        let start = hash(initial);
        Ok(Self {
            state: SearchCheckpoint {
                version: 1,
                context: hash(&(
                    "partial-search-checkpoint-v1",
                    &start,
                    hash(cat),
                    pack.id(),
                    goal.id(),
                    limits,
                )),
                start: start.clone(),
                depth: 0,
                cursor: 0,
                frontier: vec![Node {
                    state: initial.clone(),
                    steps: vec![],
                    seen: vec![start],
                    first: None,
                    score: 0,
                }],
                next: vec![],
                output: PartialPlans {
                    scope: "partial_integration_forecast".into(),
                    plans: vec![],
                    expanded: 0,
                    limits: limits.clone(),
                    termination: "exhausted_supported_model".into(),
                    unknowns: vec![],
                    coverage_gaps: vec![],
                },
                unknowns: BTreeSet::new(),
                gaps: BTreeSet::new(),
                plan_ids: BTreeSet::new(),
                finished: false,
            },
            cat,
            pack,
            goal,
            sensitive: pack
                .potential_ash_effects()
                .iter()
                .map(|r| r.id.clone())
                .collect(),
        })
    }

    /// Reconstruct the bounded symbolic prefix rather than trusting imported
    /// frontier order, counts, histories, scores or candidate membership.
    pub fn resume(
        saved: &SearchCheckpoint,
        initial: &CausalState,
        cat: &'a Catalog,
        pack: &'a FirstTurnKnowledge,
        goal: &'a Goal,
        limits: &SearchLimits,
    ) -> Result<Self, String> {
        let mut fresh = Self::begin(initial, cat, pack, goal, limits)?;
        if saved.version != 1
            || saved.context != fresh.state.context
            || saved.output.expanded > limits.expansions
        {
            return Err("search checkpoint version, context, or expansion balance differs".into());
        }
        fresh.advance(saved.output.expanded)?;
        if serde_json::to_value(saved).unwrap() != serde_json::to_value(&fresh.state).unwrap() {
            return Err("search checkpoint contradicts its deterministic symbolic prefix".into());
        }
        Ok(fresh)
    }

    pub fn snapshot(&self) -> &SearchCheckpoint {
        &self.state
    }

    /// Persist symbolic state and the current debit/reservation balance together.
    pub fn persist(&self, journal: &CallJournal) -> Result<String, String> {
        let saved = PersistedSearch {
            version: 1,
            search: self.state.clone(),
            budget: journal.stats().map_err(|e| e.message)?,
            charged_sequence: journal.charged_sequence_id().map_err(|e| e.message)?,
        };
        let key = format!("immutable/partial-search/{}", hash(&saved));
        journal
            .save_checkpoint(&key, &serde_json::to_value(saved).unwrap())
            .map_err(|e| e.message)?;
        if !journal
            .matches_checkpoint_state(&key)
            .map_err(|e| e.message)?
        {
            return Err("budget advanced while persisting symbolic search".into());
        }
        Ok(key)
    }

    /// Load only a safe checkpoint. Later/in-flight calls remain consumed and
    /// require explicit recovery; they can never be erased by an older frontier.
    #[allow(clippy::too_many_arguments)]
    pub fn load(
        journal: &CallJournal,
        key: &str,
        initial: &CausalState,
        cat: &'a Catalog,
        pack: &'a FirstTurnKnowledge,
        goal: &'a Goal,
        limits: &SearchLimits,
    ) -> Result<Self, String> {
        let value = journal
            .checkpoint(key)
            .map_err(|e| e.message)?
            .ok_or("missing symbolic checkpoint")?;
        let saved: PersistedSearch = serde_json::from_value(value).map_err(|e| e.to_string())?;
        if saved.version != 1
            || key != format!("immutable/partial-search/{}", hash(&saved))
            || !journal
                .matches_checkpoint_state(key)
                .map_err(|e| e.message)?
            || journal.checkpoint_budget(key).map_err(|e| e.message)? != Some(saved.budget.clone())
            || journal.charged_sequence_id().map_err(|e| e.message)? != saved.charged_sequence
        {
            return Err("search checkpoint or current debit/reservation state differs".into());
        }
        Self::resume(&saved.search, initial, cat, pack, goal, limits)
    }

    /// Expand at most this many nodes. No engine is invoked, and every path
    /// retains its own history; visible boards are never used for state merging.
    pub fn advance(&mut self, nodes: usize) -> Result<bool, String> {
        for _ in 0..nodes.min(self.state.output.limits.expansions) {
            if self.state.finished {
                break;
            }
            self.expand_one()?;
        }
        Ok(self.state.finished)
    }

    pub fn finish(mut self) -> Result<PartialPlans, String> {
        while !self.state.finished {
            self.advance(32)?;
        }
        Ok(self.state.output)
    }

    fn expand_one(&mut self) -> Result<(), String> {
        let node = self
            .state
            .frontier
            .get(self.state.cursor)
            .ok_or("invalid symbolic frontier cursor")?
            .clone();
        self.state.cursor += 1;
        self.state.output.expanded += 1;
        let limits = self.state.output.limits.clone();
        let evaluation = ygo_goal::evaluate(
            &self.goal.expr,
            &forecast_facts(&node.state),
            &Default::default(),
        );
        if evaluation.result == ygo_goal::Truth::Yes && node.state.pending.is_empty() {
            let candidate = plan(&node, self.goal, self.pack, &limits, &self.state.start);
            if self.state.plan_ids.insert(candidate.id.clone()) {
                self.state.output.plans.push(candidate);
            }
            self.prune_plans();
        } else if self.state.depth == limits.steps {
            self.state.output.termination = "symbolic_step_budget".into();
        } else {
            let expanded = successors(&node.state, self.cat, self.pack);
            self.state.unknowns.extend(expanded.unknowns);
            self.state.gaps.extend(expanded.coverage_gaps);
            for step in expanded.transitions {
                let id = hash(&step.after_resolution);
                if node.seen.contains(&id) {
                    continue;
                }
                let mut seen = node.seen.clone();
                seen.push(id);
                let first = node.first.clone().or_else(|| {
                    (step.kind != TransitionKind::DeclineTrigger
                        && self.sensitive.contains(&step.rule_id))
                    .then(|| step.rule_id.clone())
                });
                let state = step.after_resolution.clone();
                let score = crate::v3::goal_priority(&self.goal.expr, &forecast_facts(&state));
                let mut steps = node.steps.clone();
                steps.push(step);
                self.state.next.push(Node {
                    state,
                    steps,
                    seen,
                    first,
                    score,
                });
            }
        }
        if self.state.cursor == self.state.frontier.len() {
            if self.state.output.expanded >= limits.expansions || self.state.next.is_empty() {
                self.complete();
            } else {
                self.next_depth();
            }
        } else if self.state.output.expanded >= limits.expansions {
            self.state.output.termination = "symbolic_expansion_budget".into();
            self.complete();
        }
        Ok(())
    }

    fn complete(&mut self) {
        self.state.output.unknowns = self.state.unknowns.iter().cloned().collect();
        self.state.output.coverage_gaps = self.state.gaps.iter().cloned().collect();
        self.state.finished = true;
    }

    fn prune_plans(&mut self) {
        let limit = self.state.output.limits.candidates;
        self.state.output.plans.sort_by_key(|p| {
            (
                std::cmp::Reverse(p.predicted_resources),
                p.steps.len(),
                p.id.clone(),
            )
        });
        let mut keep = vec![];
        let mut classes = BTreeSet::new();
        for (i, p) in self.state.output.plans.iter().enumerate() {
            if classes.insert(p.first_sensitive.clone()) && keep.len() < limit {
                keep.push(i);
            }
        }
        for i in 0..self.state.output.plans.len() {
            if keep.len() == limit {
                break;
            }
            if !keep.contains(&i) {
                keep.push(i);
            }
        }
        keep.sort_unstable();
        self.state.output.plans = std::mem::take(&mut self.state.output.plans)
            .into_iter()
            .enumerate()
            .filter(|(i, _)| keep.contains(i))
            .map(|(_, p)| p)
            .collect();
    }

    fn next_depth(&mut self) {
        let limit = self.state.output.limits.frontier;
        self.state.next.sort_by_cached_key(|n| {
            (
                std::cmp::Reverse(n.score),
                std::cmp::Reverse(resources(&n.state)),
                n.steps.len(),
                hash(&n.steps),
            )
        });
        let mut classes = BTreeSet::new();
        let mut chosen = vec![];
        for (i, node) in self.state.next.iter().enumerate() {
            let last = node
                .steps
                .last()
                .and_then(|s| self.pack.rule(&s.rule_id))
                .map(|r| format!("{:?}", r.operation));
            if classes.insert((node.first.clone(), last)) && chosen.len() < limit {
                chosen.push(i);
            }
        }
        for i in 0..self.state.next.len() {
            if chosen.len() == limit {
                break;
            }
            if !chosen.contains(&i) {
                chosen.push(i);
            }
        }
        chosen.sort_unstable();
        self.state.frontier = std::mem::take(&mut self.state.next)
            .into_iter()
            .enumerate()
            .filter(|(i, _)| chosen.contains(i))
            .map(|(_, n)| n)
            .collect();
        self.state.cursor = 0;
        self.state.depth += 1;
    }
}
