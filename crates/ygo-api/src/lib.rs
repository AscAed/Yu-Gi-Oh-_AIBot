use serde::{Deserialize, Serialize};
use ygo_domain::{Banlist, CardId, Deck, DeckValidationRules, EngineEvent, ValidationReport};
use ygo_search::{CandidateLine, SearchConfig, Searcher};
pub mod combo;

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct DeckRequest {
    pub archetypes: Vec<String>,
    pub deck: Option<Deck>,
    pub banlist_id: Option<String>,
    pub top_k: Option<usize>,
    pub search_budget: Option<usize>,
    pub opponent_scenarios: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ComboResult {
    pub verification: VerificationLevel,
    pub events: Vec<EngineEvent>,
    pub score: i32,
    pub rules: String,
    pub banlist: String,
    pub catalog: String,
    pub engine: Option<String>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum VerificationLevel {
    EngineVerified,
    Heuristic,
    Unsupported,
}

pub struct ApiService;

impl Default for ApiService {
    fn default() -> Self {
        Self::new()
    }
}

impl ApiService {
    pub const fn new() -> Self {
        Self
    }
    pub const fn ruleset(&self) -> &'static str {
        "ocg-mr5"
    }
    pub fn validate_deck(&self, deck: &Deck, banlist: &Banlist) -> ValidationReport {
        deck.validate(banlist, &DeckValidationRules::ocg())
    }
    pub fn rank_lines(&self, lines: Vec<CandidateLine>) -> Vec<CandidateLine> {
        Searcher::new(SearchConfig::default()).rank(lines)
    }

    pub fn validate_request(
        &self,
        request: &DeckRequest,
        banlist: &Banlist,
    ) -> Option<ValidationReport> {
        request
            .deck
            .as_ref()
            .map(|deck| self.validate_deck(deck, banlist))
    }

    pub fn placeholder_combo(&self, card: CardId, banlist: &Banlist) -> ComboResult {
        ComboResult {
            verification: VerificationLevel::Unsupported,
            events: vec![EngineEvent::Failure {
                reason: "external engine not connected".to_string(),
            }],
            score: 0,
            rules: self.ruleset().to_string(),
            banlist: banlist.version.clone(),
            catalog: "unavailable".to_string(),
            engine: Some(format!("requested-card:{}", card.0)),
        }
    }
}
