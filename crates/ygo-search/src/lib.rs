use serde::{Deserialize, Serialize};
use ygo_domain::EngineEvent;
pub mod combo;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum Scenario {
    NoInterruption,
    MaxxC,
    Droll,
    Negate,
    BoardBreaker,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CandidateLine {
    pub id: String,
    pub scenario: Scenario,
    pub events: Vec<EngineEvent>,
    pub interaction_points: i32,
    pub resilience: i32,
    pub opponent_draws: i32,
    pub complexity: i32,
    pub score: i32,
}

impl CandidateLine {
    pub fn new(id: impl Into<String>, scenario: Scenario, events: Vec<EngineEvent>) -> Self {
        Self {
            id: id.into(),
            scenario,
            events,
            interaction_points: 0,
            resilience: 0,
            opponent_draws: 0,
            complexity: 0,
            score: 0,
        }
    }

    pub fn with_metrics(
        mut self,
        interaction_points: i32,
        resilience: i32,
        opponent_draws: i32,
        complexity: i32,
    ) -> Self {
        self.interaction_points = interaction_points;
        self.resilience = resilience;
        self.opponent_draws = opponent_draws;
        self.complexity = complexity;
        self.score = score_line(&self);
        self
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SearchConfig {
    pub interaction_weight: i32,
    pub resilience_weight: i32,
    pub opponent_draw_penalty: i32,
    pub complexity_penalty: i32,
}

impl Default for SearchConfig {
    fn default() -> Self {
        Self {
            interaction_weight: 10,
            resilience_weight: 4,
            opponent_draw_penalty: 8,
            complexity_penalty: 1,
        }
    }
}

pub struct Searcher {
    config: SearchConfig,
}

impl Searcher {
    pub fn new(config: SearchConfig) -> Self {
        Self { config }
    }

    pub fn rank(&self, mut candidates: Vec<CandidateLine>) -> Vec<CandidateLine> {
        for candidate in &mut candidates {
            candidate.score = self.score(candidate);
        }
        candidates.sort_by(|a, b| b.score.cmp(&a.score).then_with(|| a.id.cmp(&b.id)));
        candidates
    }

    fn score(&self, candidate: &CandidateLine) -> i32 {
        candidate.interaction_points * self.config.interaction_weight
            + candidate.resilience * self.config.resilience_weight
            - candidate.opponent_draws * self.config.opponent_draw_penalty
            - candidate.complexity * self.config.complexity_penalty
    }
}

fn score_line(candidate: &CandidateLine) -> i32 {
    SearchConfig::default().interaction_weight * candidate.interaction_points
        + SearchConfig::default().resilience_weight * candidate.resilience
        - SearchConfig::default().opponent_draw_penalty * candidate.opponent_draws
        - SearchConfig::default().complexity_penalty * candidate.complexity
}
