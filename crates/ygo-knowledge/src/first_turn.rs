//! Source-bound first-turn hypotheses. Classification and native verification
//! are deliberately separate; deserializing a status cannot certify a rule.
use crate::{hash, Filter};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, path::Path};
pub mod certification;
pub mod verification;

const DATA: &str = include_str!("../../../knowledge/tournament-2026.knowledge.json");
const COVERAGE: &str = include_str!("../../../knowledge/tournament-2026.coverage.json");
const SOURCE: &str = include_str!("../../../configs/tournament-2026.source.json");

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ImplementationStatus {
    Curated,
    Implemented,
    Verified,
    Excluded,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    NormalSummonSet,
    EmptyFieldSpecial,
    DeckSet,
    RaiseLevelRank,
    DiscardMill,
    DeckMillSet,
    ReviveOnBanish,
    RevealSpecial,
    SearchMonster,
    RankAsLevel,
    PositionBoost,
    PhantomFieldSpecial,
    SearchSpellTrap,
    GrantedXyzAttack,
    Mill,
    SpecialOnPhantomSummon,
    GraveHandSpecial,
    Identity,
    DetachSelfSpecial,
    GrantedOpponentProtection,
    DangerReveal,
    DangerDiscardSpecial,
    ExactDarkGraveSpecial,
    BanishDestroy,
    DestroyDraw,
    ReturnOnGraveSpecial,
    SearchWarrior,
    MillMonster,
    RequiemRankUp,
    ForceRankUp,
    TrapSameTurn,
    TrapMonster,
    ImmediateXyz,
    GraveRevive,
    AshNegate,
    DrawObserver,
    MulcharmyObserver,
    EndPhaseHandReduce,
    MulcharmyLimit,
    LinkProcedure,
    LinkMaterialProhibition,
    LinkedXyzDestroy,
    LinkedDestroyProtection,
    CostMillBoost,
    LinkSummonBanish,
    TemporaryBanishReturn,
    XyzProcedure,
    DestroyedXyzRevive,
    RankShift,
    OphionLock,
    DelayedExosisterSet,
    RewriteOpponent,
    RequiemNegateRevive,
    ArcProtection,
    ArcAttackNegate,
    OpponentOverlay,
    DeckSpecial,
    SearchRankUp,
    ReturnBanishedOnDestruction,
    Outside,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DeckInteraction {
    None,
    Search,
    EffectMill,
    EffectSpecial,
    Draw,
    CostMill,
    Set,
}
impl DeckInteraction {
    pub fn is_ash_candidate(self) -> bool {
        matches!(
            self,
            Self::Search | Self::EffectMill | Self::EffectSpecial | Self::Draw
        )
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Usage {
    pub scope: String,
    pub key: Option<String>,
    pub limit: Option<usize>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub role: String,
    pub stage: String,
    pub controller: u8,
    pub locations: Vec<u8>,
    pub min: usize,
    pub max: usize,
    pub filter: Filter,
    pub relation: Option<String>,
    pub actual_level: Option<u32>,
    pub actual_rank: Option<u32>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FirstTurnRule {
    pub id: String,
    pub card_id: u32,
    pub applicable: bool,
    pub operation: Operation,
    pub description: Option<u64>,
    pub source_locations: u8,
    pub usage: Usage,
    pub selections: Vec<Selection>,
    pub conditions: Vec<String>,
    pub costs: Vec<String>,
    pub restrictions: Vec<String>,
    pub deck_interaction: DeckInteraction,
    pub status: ImplementationStatus,
    pub evidence_cases: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FirstTurnCard {
    pub card_id: u32,
    pub name: String,
    pub text_sha256: String,
    pub script: String,
    pub script_sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FirstTurnKnowledge {
    pub schema_version: u16,
    pub profile: String,
    pub asset_group_id: String,
    pub source_id: String,
    pub coverage_id: String,
    pub cards: Vec<FirstTurnCard>,
    pub rules: Vec<FirstTurnRule>,
    // Only the native case verifier may add certificates. JSON has no such field.
    #[serde(skip)]
    certified: BTreeSet<String>,
}

impl FirstTurnKnowledge {
    pub fn builtin() -> Result<Self, String> {
        let pack: Self = serde_json::from_str(DATA).map_err(|e| e.to_string())?;
        pack.validate()?;
        Ok(pack)
    }
    pub fn read(path: &Path) -> Result<Self, String> {
        let pack: Self = serde_json::from_slice(&std::fs::read(path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        pack.validate()?;
        Ok(pack)
    }
    pub fn id(&self) -> String {
        format!(
            "first-turn-knowledge-{}",
            hash(&serde_json::to_vec(self).unwrap())
        )
    }
    pub fn rule(&self, id: &str) -> Option<&FirstTurnRule> {
        self.rules.iter().find(|r| r.id == id)
    }
    pub fn validate(&self) -> Result<(), String> {
        let expected: Self = serde_json::from_str(DATA).map_err(|e| e.to_string())?;
        let coverage: serde_json::Value =
            serde_json::from_str(COVERAGE).map_err(|e| e.to_string())?;
        if self.schema_version != 1
            || self.profile != "tournament-first-turn-v1"
            || self.asset_group_id != coverage["asset_group_id"]
            || self.source_id != format!("tournament-source-{}", hash(SOURCE.as_bytes()))
            || self.coverage_id != format!("coverage-{}", hash(COVERAGE.as_bytes()))
            || serde_json::to_value(&self.cards).unwrap()
                != serde_json::to_value(&expected.cards).unwrap()
            || self.rules.len() != expected.rules.len()
        {
            return Err("first-turn knowledge source/coverage identity mismatch".into());
        }
        let mut ids = BTreeSet::new();
        for card in &self.cards {
            let original = coverage["cards"]
                .as_array()
                .and_then(|cards| cards.iter().find(|c| c["card_id"] == card.card_id))
                .ok_or("card missing from coverage")?;
            for (key, value) in serde_json::to_value(card).unwrap().as_object().unwrap() {
                if original[key] != *value {
                    return Err("card provenance differs from coverage".into());
                }
            }
        }
        for rule in &self.rules {
            let canonical = expected.rule(&rule.id).ok_or("unknown curated rule")?;
            let mut actual = serde_json::to_value(rule).unwrap();
            let mut frozen = serde_json::to_value(canonical).unwrap();
            for value in [&mut actual, &mut frozen] {
                let obj = value.as_object_mut().unwrap();
                obj.remove("status");
                obj.remove("evidence_cases");
            }
            if !ids.insert(&rule.id) || actual != frozen {
                return Err(format!(
                    "curated rule binding/semantics differs: {}",
                    rule.id
                ));
            }
            if rule.status == ImplementationStatus::Verified
                && (!self.certified.contains(&rule.id) || rule.evidence_cases.is_empty())
            {
                return Err(format!(
                    "missing native verification certificate: {}",
                    rule.id
                ));
            }
            if rule.applicable == (rule.status == ImplementationStatus::Excluded)
                || rule.conditions.is_empty()
            {
                return Err("invalid first-turn rule classification".into());
            }
        }
        Ok(())
    }
    /// Structure/source checks do not execute or certify any card effect.
    pub fn validate_sources(&self, root: &Path) -> Result<(), String> {
        self.validate()?;
        let mut manifest: serde_json::Value = serde_json::from_slice(
            &std::fs::read(root.join("manifest.json")).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        if manifest["asset_group_id"] != self.asset_group_id {
            return Err("wrong knowledge asset group".into());
        }
        manifest
            .as_object_mut()
            .ok_or("invalid asset group manifest")?
            .remove("asset_group_id");
        if format!(
            "asset-group-{}",
            hash(&serde_json::to_vec(&manifest).unwrap())
        ) != self.asset_group_id
        {
            return Err("knowledge asset group identity mismatch".into());
        }
        for name in ["cards.cdb", "scripts.json"] {
            let actual = hash(&std::fs::read(root.join(name)).map_err(|e| e.to_string())?);
            if manifest["files"][name] != actual {
                return Err(format!("knowledge asset hash mismatch: {name}"));
            }
        }
        let db = rusqlite::Connection::open_with_flags(
            root.join("cards.cdb"),
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
        )
        .map_err(|e| e.to_string())?;
        let script_root = root
            .join("script")
            .canonicalize()
            .map_err(|e| e.to_string())?;
        for card in &self.cards {
            let text: String = db
                .query_row("SELECT desc FROM texts WHERE id=?1", [card.card_id], |r| {
                    r.get(0)
                })
                .map_err(|e| e.to_string())?;
            let path = script_root
                .join(&card.script)
                .canonicalize()
                .map_err(|e| e.to_string())?;
            if !path.starts_with(&script_root)
                || hash(text.as_bytes()) != card.text_sha256
                || hash(&std::fs::read(path).map_err(|e| e.to_string())?) != card.script_sha256
                || manifest["files"][format!("script/{}", card.script)] != card.script_sha256
            {
                return Err(format!("knowledge source mismatch: {}", card.card_id));
            }
        }
        Ok(())
    }
    pub fn potential_ash_effects(&self) -> Vec<&FirstTurnRule> {
        self.rules
            .iter()
            .filter(|r| {
                r.applicable && r.description.is_some() && r.deck_interaction.is_ash_candidate()
            })
            .collect()
    }
    pub fn verified_ash_effects(&self) -> Vec<&FirstTurnRule> {
        self.potential_ash_effects()
            .into_iter()
            .filter(|r| {
                r.status == ImplementationStatus::Verified && self.certified.contains(&r.id)
            })
            .collect()
    }
    pub fn require_verified_coverage(&self) -> Result<(), String> {
        self.validate()?;
        let missing: Vec<_> = self
            .rules
            .iter()
            .filter(|r| {
                r.applicable
                    && (r.status != ImplementationStatus::Verified
                        || !self.certified.contains(&r.id))
            })
            .map(|r| r.id.as_str())
            .collect();
        if missing.is_empty() {
            Ok(())
        } else {
            Err(format!(
                "unverified first-turn rules: {}",
                missing.join(",")
            ))
        }
    }
}
