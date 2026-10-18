use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
mod catalog;
pub use catalog::*;

#[derive(
    Clone, Copy, Debug, Default, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize,
)]
pub struct CardId(pub u32);

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct Card {
    pub id: CardId,
    pub name: String,
    pub archetypes: Vec<String>,
    pub kind: CardKind,
    #[serde(default)]
    pub alias: u32,
    #[serde(default)]
    pub type_flags: u32,
    #[serde(default)]
    pub setcodes: Vec<u16>,
    #[serde(default)]
    pub level: u32,
    #[serde(default)]
    pub attribute: u32,
    #[serde(default)]
    pub race: u64,
    #[serde(default)]
    pub attack: i32,
    #[serde(default)]
    pub defense: i32,
    #[serde(default)]
    pub lscale: u32,
    #[serde(default)]
    pub rscale: u32,
    #[serde(default)]
    pub link_marker: u32,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CardKind {
    #[default]
    Monster,
    Spell,
    Trap,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum Limit {
    Forbidden,
    Limited,
    SemiLimited,
    Unlimited,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Banlist {
    pub region: String,
    pub version: String,
    pub limits: BTreeMap<CardId, Limit>,
}

impl Banlist {
    pub fn ocg<I>(version: impl Into<String>, limits: I) -> Self
    where
        I: IntoIterator<Item = (CardId, Limit)>,
    {
        Self {
            region: "OCG".to_string(),
            version: version.into(),
            limits: limits.into_iter().collect(),
        }
    }

    pub fn limit_for(&self, card: CardId) -> Limit {
        self.limits.get(&card).copied().unwrap_or(Limit::Unlimited)
    }
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct Deck {
    pub main: Vec<CardId>,
    pub extra: Vec<CardId>,
    pub side: Vec<CardId>,
}

impl Deck {
    pub fn new(main: Vec<CardId>, extra: Vec<CardId>, side: Vec<CardId>) -> Self {
        Self { main, extra, side }
    }

    pub fn validate(&self, banlist: &Banlist, rules: &DeckValidationRules) -> ValidationReport {
        let mut violations = Vec::new();
        if self.main.len() < rules.main_min || self.main.len() > rules.main_max {
            violations.push(Violation::new(
                "main_size",
                format!(
                    "main deck must contain {}-{} cards",
                    rules.main_min, rules.main_max
                ),
            ));
        }
        if self.extra.len() > rules.extra_max {
            violations.push(Violation::new(
                "extra_size",
                format!(
                    "extra deck cannot contain more than {} cards",
                    rules.extra_max
                ),
            ));
        }
        if self.side.len() > rules.side_max {
            violations.push(Violation::new(
                "side_size",
                format!(
                    "side deck cannot contain more than {} cards",
                    rules.side_max
                ),
            ));
        }

        let mut counts = BTreeMap::new();
        for card in self
            .main
            .iter()
            .chain(self.extra.iter())
            .chain(self.side.iter())
        {
            *counts.entry(*card).or_insert(0usize) += 1;
        }
        for (card, count) in counts {
            let allowed = match banlist.limit_for(card) {
                Limit::Forbidden => 0,
                Limit::Limited => 1,
                Limit::SemiLimited => 2,
                Limit::Unlimited => rules.max_copies,
            };
            if count > allowed {
                violations.push(Violation::new(
                    "copy_limit",
                    format!(
                        "card {} appears {} times; maximum is {}",
                        card.0, count, allowed
                    ),
                ));
            }
        }

        ValidationReport { violations }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct DeckValidationRules {
    pub main_min: usize,
    pub main_max: usize,
    pub extra_max: usize,
    pub side_max: usize,
    pub max_copies: usize,
}

impl DeckValidationRules {
    pub const fn ocg() -> Self {
        Self {
            main_min: 40,
            main_max: 60,
            extra_max: 15,
            side_max: 15,
            max_copies: 3,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Violation {
    pub code: String,
    pub message: String,
}

impl Violation {
    fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ValidationReport {
    pub violations: Vec<Violation>,
}

impl ValidationReport {
    pub fn is_legal(&self) -> bool {
        self.violations.is_empty()
    }
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct VersionSet {
    pub rules: String,
    pub banlist: String,
    pub catalog: String,
    pub engine: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum EngineEvent {
    Draw {
        card: CardId,
    },
    NormalSummon {
        card: CardId,
    },
    SpecialSummon {
        card: CardId,
    },
    Activate {
        card: CardId,
    },
    ChainLink {
        index: u8,
        card: CardId,
    },
    Resolve {
        card: CardId,
    },
    Search {
        card: CardId,
    },
    MoveZone {
        card: CardId,
        from: String,
        to: String,
    },
    Negate {
        card: CardId,
    },
    Destroy {
        card: CardId,
    },
    Banish {
        card: CardId,
    },
    EndPhase,
    Failure {
        reason: String,
    },
}
