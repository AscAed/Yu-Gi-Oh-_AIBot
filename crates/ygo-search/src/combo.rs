use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    time::Instant,
};
use ygo_engine_adapter::*;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct SearchBudget {
    pub top_k: usize,
    pub node_budget: usize,
    pub beam_width: usize,
    pub max_depth: usize,
    pub time_limit_ms: u64,
}
impl Default for SearchBudget {
    fn default() -> Self {
        Self {
            top_k: 5,
            node_budget: 10000,
            beam_width: 32,
            max_depth: 64,
            time_limit_ms: 60000,
        }
    }
}
impl SearchBudget {
    pub fn validate(&self) -> Result<(), String> {
        if self.top_k == 0
            || self.top_k > 100
            || self.node_budget == 0
            || self.node_budget > 1000000
            || self.beam_width == 0
            || self.beam_width > 1024
            || self.max_depth == 0
            || self.max_depth > 1024
            || self.time_limit_ms == 0
            || self.time_limit_ms > 3600000
        {
            Err("search budget out of range".into())
        } else {
            Ok(())
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ScoringConfig {
    pub board_interaction: f64,
    pub resource_advantage: f64,
    pub follow_up: f64,
    pub complexity: f64,
}
impl Default for ScoringConfig {
    fn default() -> Self {
        Self {
            board_interaction: 5.0,
            resource_advantage: 3.0,
            follow_up: 2.0,
            complexity: -0.25,
        }
    }
}
impl ScoringConfig {
    pub fn from_toml(text: &str) -> Result<Self, String> {
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct File {
            weights: ScoringConfig,
        }
        let config = toml::from_str::<File>(text)
            .map_err(|e| e.to_string())?
            .weights;
        if [
            config.board_interaction,
            config.resource_advantage,
            config.follow_up,
            config.complexity,
        ]
        .iter()
        .any(|n| !n.is_finite())
        {
            return Err("nonfinite scoring weight".into());
        }
        Ok(config)
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Evaluation {
    pub kind: String,
    pub profile_version: String,
    pub interaction: f64,
    pub resources: f64,
    pub follow_up: f64,
    pub decisions: usize,
    pub total: f64,
    pub coverage_gaps: Vec<String>,
    pub explanations: Vec<String>,
}
pub fn evaluate(state: &Checkpoint, decisions: usize, weights: &ScoringConfig) -> Evaluation {
    let mut e = Evaluation {
        kind: "heuristic".into(),
        profile_version: "rabbit-v1".into(),
        interaction: 0.0,
        resources: 0.0,
        follow_up: 0.0,
        decisions,
        total: 0.0,
        coverage_gaps: vec![],
        explanations: vec![],
    };
    for card in &state.cards {
        if matches!(card.location, 2 | 4 | 8) {
            e.resources += if card.player == 0 { 1.0 } else { -1.0 };
        }
        if card.player != 0 {
            continue;
        }
        match card.code {
            84013237 => {
                if card.location == 4 && card.position & 5 != 0 {
                    let n = card.overlay.len().min(2);
                    e.interaction += n as f64;
                    e.explanations.push(format!(
                        "84013237: 至多 {n} 次攻击无效估计；共用超量素材费用，未验证对手回合"
                    ));
                }
            }
            85138716 => {
                if card.location == 2 {
                    e.follow_up += 1.0;
                    e.explanations
                        .push("85138716: 手牌中保留展开点，续航为启发式估计".into());
                }
            }
            77637979 | 71594310 => (),
            _ => {
                if card.type_flags & 0x20 != 0 || card.type_flags & 6 != 0 {
                    e.coverage_gaps
                        .push(format!("未覆盖卡片 {} 的互动/续航", card.code));
                }
            }
        }
    }
    e.coverage_gaps.sort();
    e.coverage_gaps.dedup();
    e.total = e.interaction * weights.board_interaction
        + e.resources * weights.resource_advantage
        + e.follow_up * weights.follow_up
        + decisions as f64 * weights.complexity;
    e
}
pub fn prefix_key(request: &RunDuelRequest) -> String {
    if request.protocol_version == 6 {
        return digest(
            &serde_json::to_vec(&(
                "runtime-v6",
                &request.deck,
                &request.opening_hand,
                request.seed,
                &request.versions,
                &request.scenario,
                &request.interruption,
                &request.first_turn,
                &request.decisions,
            ))
            .expect("serializable v6 prefix"),
        );
    }
    if matches!(request.protocol_version, 4 | 5) {
        return digest(
            &serde_json::to_vec(&(
                if request.protocol_version == 5 {
                    "runtime-v5"
                } else {
                    "runtime-v4"
                },
                &request.deck,
                &request.opening_hand,
                request.seed,
                &request.versions,
                &request.scenario,
                &request.interruption,
                &request.decisions,
            ))
            .expect("runtime identity"),
        );
    }
    if request.protocol_version == 3 {
        return digest(
            &serde_json::to_vec(&(
                "runtime-v3",
                &request.deck,
                &request.opening_hand,
                request.seed,
                &request.versions,
                &request.scenario,
                &request.decisions,
            ))
            .expect("serializable v3 prefix"),
        );
    }
    digest(
        &serde_json::to_vec(&(
            request.protocol_version,
            &request.deck,
            &request.opening_hand,
            request.seed,
            &request.versions,
            &request.decisions,
        ))
        .expect("serializable prefix"),
    )
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ComboLine {
    pub id: String,
    pub decisions: Vec<Decision>,
    pub evaluation: Evaluation,
    pub result: DuelResult,
    pub replay_verified: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct SearchStats {
    pub nodes: usize,
    pub engine_calls: usize,
    pub cache_hits: usize,
    pub pruned: usize,
    pub failed_branches: usize,
    pub elapsed_ms: u64,
    pub replay_ms: u64,
    pub peak_frontier: usize,
    pub max_decision_depth: usize,
    pub completed_lines: usize,
    pub parent_peak_working_set_bytes: Option<u64>,
    pub worker_peak_working_set_bytes: Option<u64>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SearchReport {
    pub termination: String,
    pub lines: Vec<ComboLine>,
    pub stats: SearchStats,
    pub diagnostics: Vec<WorkerError>,
    pub scoring: ScoringConfig,
    pub budget: SearchBudget,
}
fn run<A: EngineAdapter>(
    adapter: &A,
    r: &RunDuelRequest,
    start: Instant,
    budget: &SearchBudget,
    stats: &mut SearchStats,
) -> Result<DuelResult, WorkerError> {
    let left = budget
        .time_limit_ms
        .saturating_sub(start.elapsed().as_millis() as u64);
    if left == 0 {
        return Err(WorkerError::new(
            "analysis_timeout",
            "search",
            "analysis deadline",
        ));
    }
    let mut r = r.clone();
    r.engine.timeout_ms = r.engine.timeout_ms.min(left);
    stats.engine_calls += 1;
    let result = adapter.run(&r)?;
    stats.worker_peak_working_set_bytes = stats
        .worker_peak_working_set_bytes
        .max(result.peak_working_set_bytes);
    Ok(result)
}
fn record_line(
    r: &RunDuelRequest,
    result: DuelResult,
    weights: &ScoringConfig,
    lines: &mut Vec<ComboLine>,
) {
    if matches!(
        result.status,
        DuelStatus::EngineVerified | DuelStatus::Partial
    ) {
        let id = prefix_key(r);
        if !lines.iter().any(|l| l.id == id) {
            lines.push(ComboLine {
                id,
                decisions: r.decisions.clone(),
                evaluation: evaluate(&result.checkpoint, r.decisions.len(), weights),
                result,
                replay_verified: false,
            });
        }
    }
}
fn passive(prompt: &Prompt) -> Option<Choice> {
    prompt
        .actions
        .iter()
        .find(|a| {
            matches!(
                a.choice,
                Choice::Command { command: 7, .. }
                    | Choice::Chain { index: None }
                    | Choice::YesNo { yes: false }
                    | Choice::Finish
            )
        })
        .or_else(|| prompt.actions.first())
        .map(|a| a.choice.clone())
}
pub fn search<A: EngineAdapter>(
    adapter: &A,
    request: &RunDuelRequest,
    budget: &SearchBudget,
    weights: &ScoringConfig,
) -> Result<SearchReport, String> {
    budget.validate()?;
    let start = Instant::now();
    let mut stats = SearchStats::default();
    let mut cache = BTreeMap::new();
    let mut diagnostics = vec![];
    let mut lines = vec![];
    let first = run(adapter, request, start, budget, &mut stats)
        .map_err(|e| format!("{}: {}", e.code, e.message))?;
    stats.nodes += 1;
    if first.status == DuelStatus::Failed {
        return Err(format!("{:?}", first.error));
    }
    cache.insert(prefix_key(request), first.clone());
    let mut root = request.clone();
    root.decisions = first.resolved_decisions.clone();
    let mut baseline = root.clone();
    let mut b = first.clone();
    while baseline.decisions.len() < budget.max_depth
        && b.prompt.is_some()
        && stats.nodes < budget.node_budget
    {
        let p = b.prompt.as_ref().unwrap();
        let choice = passive(p).ok_or("prompt has no actions")?;
        baseline.decisions.push(Decision {
            prompt_id: p.id,
            player: p.player,
            choice,
        });
        match run(adapter, &baseline, start, budget, &mut stats) {
            Ok(next) => {
                stats.nodes += 1;
                baseline.decisions = next.resolved_decisions.clone();
                stats.max_decision_depth = stats.max_decision_depth.max(baseline.decisions.len());
                cache.insert(prefix_key(&baseline), next.clone());
                b = next;
            }
            Err(e) => {
                diagnostics.push(e);
                break;
            }
        }
    }
    if baseline.decisions.len() <= budget.max_depth {
        record_line(&baseline, b, weights, &mut lines);
    }
    let mut frontier = vec![(root.clone(), first)];
    let mut termination = "exhausted".to_string();
    let mut seen = BTreeSet::new();
    seen.insert(prefix_key(&root));
    'depth: for depth in 0..budget.max_depth {
        let mut next = vec![];
        // Limit expensive prefix executions per layer. Rotate choice windows
        // across parents so identical zone variants do not all try one exit.
        let choices_per_parent = budget.beam_width.div_ceil(frontier.len().max(1));
        for (parent_index, (r, result)) in frontier.into_iter().enumerate() {
            if r.decisions.len() >= budget.max_depth {
                termination = "depth_budget".into();
                continue;
            }
            if let Some(p) = result.prompt {
                let mut actions = p.actions.clone();
                actions.sort_by_key(|a| match a.choice {
                    Choice::Command { command: 5, .. } => 0,
                    Choice::Command { command: 1, .. } => 1,
                    Choice::Command { command: 0, .. } => 2,
                    Choice::Command { command: 7, .. } => 9,
                    _ => 3,
                });
                if actions.len() > choices_per_parent {
                    let offset = (parent_index * choices_per_parent) % actions.len();
                    actions.rotate_left(offset);
                    stats.pruned += actions.len() - choices_per_parent;
                    actions.truncate(choices_per_parent);
                }
                for a in actions {
                    if stats.nodes >= budget.node_budget {
                        termination = "node_budget".into();
                        break 'depth;
                    }
                    // Leave time for independent verification of returned lines.
                    if start.elapsed().as_millis() as u64
                        >= budget.time_limit_ms.saturating_mul(9) / 10
                    {
                        termination = "time_budget".into();
                        break 'depth;
                    }
                    let mut child = r.clone();
                    child.decisions.push(Decision {
                        prompt_id: p.id,
                        player: p.player,
                        choice: a.choice,
                    });
                    let key = prefix_key(&child);
                    if !seen.insert(key.clone()) {
                        stats.cache_hits += 1;
                        continue;
                    }
                    let result = if let Some(cached) = cache.get(&key) {
                        stats.cache_hits += 1;
                        cached.clone()
                    } else {
                        stats.nodes += 1;
                        match run(adapter, &child, start, budget, &mut stats) {
                            Ok(v) => {
                                cache.insert(key, v.clone());
                                v
                            }
                            Err(e) => {
                                stats.failed_branches += 1;
                                if diagnostics.len() < 20 {
                                    diagnostics.push(e);
                                }
                                continue;
                            }
                        }
                    };
                    if result.status == DuelStatus::Failed {
                        stats.failed_branches += 1;
                        if diagnostics.len() < 20 {
                            if let Some(e) = result.error {
                                diagnostics.push(e);
                            }
                        }
                        continue;
                    }
                    child.decisions = result.resolved_decisions.clone();
                    stats.max_decision_depth = stats.max_decision_depth.max(child.decisions.len());
                    if child.decisions.len() > budget.max_depth {
                        termination = "depth_budget".into();
                        stats.pruned += 1;
                        continue;
                    }
                    record_line(&child, result.clone(), weights, &mut lines);
                    if result.prompt.is_some() {
                        next.push((child, result));
                    }
                }
            }
        }
        stats.peak_frontier = stats.peak_frontier.max(next.len());
        next.sort_by(|(a, ar), (b, br)| {
            evaluate(&br.checkpoint, b.decisions.len(), weights)
                .total
                .total_cmp(&evaluate(&ar.checkpoint, a.decisions.len(), weights).total)
                .then_with(|| prefix_key(a).cmp(&prefix_key(b)))
        });
        stats.pruned += next.len().saturating_sub(budget.beam_width);
        // Share the beam across distinct summon/activation histories. A setup
        // paying costs must survive alongside immediately higher-resource lines.
        // This is a pruning heuristic, never a state equivalence/cache key.
        let mut groups = BTreeMap::<Vec<(u8, u32)>, std::collections::VecDeque<_>>::new();
        let mut order = Vec::new();
        for node in next {
            let signature = node
                .0
                .decisions
                .iter()
                .filter_map(|d| match d.choice {
                    Choice::Command { command, index } if matches!(command, 0 | 1 | 3 | 4 | 5) => {
                        Some((command, index))
                    }
                    _ => None,
                })
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect::<Vec<_>>();
            if !groups.contains_key(&signature) {
                order.push(signature.clone());
            }
            groups.entry(signature).or_default().push_back(node);
        }
        let mut next = vec![];
        while next.len() < budget.beam_width {
            let mut added = false;
            for key in &order {
                if let Some(node) = groups.get_mut(key).unwrap().pop_front() {
                    next.push(node);
                    added = true;
                    if next.len() == budget.beam_width {
                        break;
                    }
                }
            }
            if !added {
                break;
            }
        }
        if next.is_empty() {
            break;
        }
        frontier = next;
        if depth + 1 == budget.max_depth {
            termination = "depth_budget".into();
        }
    }
    lines.sort_by(|a, b| {
        b.evaluation
            .total
            .total_cmp(&a.evaluation.total)
            .then_with(|| a.id.cmp(&b.id))
    });
    let replay_start = Instant::now();
    stats.completed_lines = lines.len();
    let mut verified = vec![];
    for mut line in lines {
        if verified.len() >= budget.top_k {
            break;
        }
        let mut replay = request.clone();
        replay.decisions = line.decisions.clone();
        match run(adapter, &replay, start, budget, &mut stats) {
            Ok(result)
                if result.status == line.result.status
                    && result.checkpoint == line.result.checkpoint
                    && result.events == line.result.events
                    && result.loaded_scripts == line.result.loaded_scripts
                    && result.resolved_decisions == line.decisions
                    && result.steps == line.result.steps =>
            {
                line.replay_verified = true;
                verified.push(line);
            }
            Ok(_) => diagnostics.push(WorkerError::new(
                "replay_mismatch",
                "verify",
                "trace/state changed",
            )),
            Err(e) => {
                diagnostics.push(e);
                break;
            }
        }
    }
    stats.replay_ms = replay_start.elapsed().as_millis() as u64;
    stats.elapsed_ms = start.elapsed().as_millis() as u64;
    stats.parent_peak_working_set_bytes = peak_working_set_bytes();
    if verified.is_empty() {
        termination = format!("{termination}:no_verified_lines");
    }
    Ok(SearchReport {
        termination,
        lines: verified,
        stats,
        diagnostics,
        scoring: weights.clone(),
        budget: budget.clone(),
    })
}
