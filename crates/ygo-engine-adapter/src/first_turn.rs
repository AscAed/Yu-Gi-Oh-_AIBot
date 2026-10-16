//! Protocol v6 identities and an explicit, knowledge-derived Ash strategy set.
use crate::{InterruptionConfig, RunDuelRequest};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const FIRST_TURN_INITIALIZER: &str = "fixed-ash-first-turn-v1";

/// The planner receives only observable cards and unordered remaining counts.
/// Complete query checkpoints remain separate execution evidence.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FirstTurnPublicState {
    pub visible: crate::Checkpoint,
    pub own_deck_counts: BTreeMap<u32, usize>,
    pub opponent_deck_count: usize,
    pub opponent_hand_count: usize,
}

pub fn first_turn_public_state(checkpoint: &crate::Checkpoint) -> FirstTurnPublicState {
    let mut state = FirstTurnPublicState {
        visible: checkpoint.clone(),
        own_deck_counts: BTreeMap::new(),
        opponent_deck_count: 0,
        opponent_hand_count: 0,
    };
    state.visible.cards.retain(|card| {
        if card.location == 1 {
            if card.player == 0 {
                *state.own_deck_counts.entry(card.code).or_default() += 1;
            } else {
                state.opponent_deck_count += 1;
            }
            return false;
        }
        if card.player == 1 && card.location == 2 {
            state.opponent_hand_count += 1;
            return false;
        }
        card.player == 0 || (card.location != 64 && card.position & 5 != 0)
    });
    state
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AshEffectDescriptor {
    pub effect_id: String,
    pub card_id: u32,
    pub description: u64,
    /// Original activation range, not the source's location after paying costs.
    pub source_locations: u8,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FirstTurnConfig {
    pub asset_group_id: String,
    pub source_id: String,
    pub coverage_id: String,
    pub knowledge_id: String,
    pub ash_effects: Vec<AshEffectDescriptor>,
}

impl FirstTurnConfig {
    pub fn validate(&self) -> Result<(), String> {
        for (id, prefix) in [
            (&self.asset_group_id, "asset-group-"),
            (&self.source_id, "tournament-source-"),
            (&self.coverage_id, "coverage-"),
            (&self.knowledge_id, "first-turn-knowledge-"),
        ] {
            if !id.strip_prefix(prefix).is_some_and(|s| {
                s.len() == 64
                    && s.bytes()
                        .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
            }) {
                return Err("invalid frozen first-turn identity".into());
            }
        }
        let mut ids = BTreeSet::new();
        let mut descriptors: BTreeMap<(u32, u64), u8> = BTreeMap::new();
        for e in &self.ash_effects {
            let prefix = format!("{}:", e.card_id);
            let valid_description = e.description == 0
                || ((e.card_id as u64) << 20..=((e.card_id as u64) << 20) + 31)
                    .contains(&e.description);
            let zones = descriptors.entry((e.card_id, e.description)).or_default();
            if !e.effect_id.starts_with(&prefix)
                || e.effect_id.len() == prefix.len()
                || !valid_description
                || e.source_locations == 0
                || e.source_locations & !(2 | 4 | 8 | 16 | 32) != 0
                || *zones & e.source_locations != 0
                || !ids.insert(&e.effect_id)
            {
                return Err("invalid or ambiguous Ash effect descriptor".into());
            }
            *zones |= e.source_locations;
        }
        Ok(())
    }
    pub fn descriptor(&self, id: &str) -> Option<&AshEffectDescriptor> {
        self.ash_effects.iter().find(|e| e.effect_id == id)
    }
}

impl InterruptionConfig {
    pub fn validate_v6(&self, context: &FirstTurnConfig) -> Result<(), String> {
        context.validate()?;
        let mut counts = BTreeMap::new();
        for c in &self.opponent_deck.main {
            *counts.entry(c.0).or_insert(0usize) += 1;
        }
        if self.opponent_deck.main.len() != 40
            || !self.opponent_deck.extra.is_empty()
            || !self.opponent_deck.side.is_empty()
            || self.opponent_hand != [ygo_domain::CardId(14558127)]
            || counts.get(&14558127) != Some(&1)
            || counts.values().any(|n| *n > 3)
            || self.occurrence != 1
            || !matches!(self.policy.as_str(), "pass" | "ash_effect_once")
            || context.descriptor(&self.effect_id).is_none()
        {
            return Err("invalid independent v6 opponent or response strategy".into());
        }
        Ok(())
    }
}

impl RunDuelRequest {
    /// Structural dispatch before loading any native asset. Actual deck legality
    /// and the knowledge registry are additionally checked by the planning API.
    pub fn validate_protocol(&self) -> Result<(), String> {
        if !(2..=6).contains(&self.protocol_version)
            || (self.protocol_version < 6 && self.first_turn.is_some())
        {
            return Err("unsupported protocol or first-turn context".into());
        }
        if self.protocol_version == 6 {
            if self.scenario.is_some()
                || self.probe_only
                || self.versions.initializer != FIRST_TURN_INITIALIZER
            {
                return Err("invalid v6 initializer/scenario".into());
            }
            let context = self.first_turn.as_ref().ok_or("missing v6 context")?;
            self.interruption
                .as_ref()
                .ok_or("missing independent opponent")?
                .validate_v6(context)?;
        }
        Ok(())
    }
}

/// Bind the lazy script loader's hash allowlist and the native files to one
/// immutable group. Each actually loaded Lua file is still hashed by the worker.
pub fn verify_first_turn_assets(request: &RunDuelRequest) -> Result<(), String> {
    let context = request
        .first_turn
        .as_ref()
        .ok_or("missing v6 asset context")?;
    let root = request
        .engine
        .catalog_path
        .parent()
        .ok_or("missing asset root")?;
    let mut group: serde_json::Value = serde_json::from_slice(
        &std::fs::read(root.join("manifest.json")).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let actual_id = group["asset_group_id"]
        .as_str()
        .ok_or("missing asset group id")?
        .to_owned();
    group
        .as_object_mut()
        .ok_or("invalid asset manifest")?
        .remove("asset_group_id");
    if group["schema_version"] != 1
        || context.asset_group_id != actual_id
        || actual_id
            != format!(
                "asset-group-{}",
                crate::digest(&serde_json::to_vec(&group).unwrap())
            )
        || group["recipe"]["banlist_id"] != request.versions.banlist
    {
        return Err("asset group identity/rules mismatch".into());
    }
    for (name, path) in [
        ("cards.cdb", &request.engine.catalog_path),
        ("engine/ocgcore.dll", &request.engine.ocgcore_path),
        ("engine/manifest.json", &request.engine.engine_manifest_path),
        ("scripts.json", &request.engine.script_manifest_path),
    ] {
        if path.canonicalize().map_err(|e| e.to_string())?
            != root.join(name).canonicalize().map_err(|e| e.to_string())?
            || group["files"][name] != crate::hash_file(path)?
        {
            return Err(format!("asset group file mismatch: {name}"));
        }
    }
    if request
        .engine
        .scripts_path
        .canonicalize()
        .map_err(|e| e.to_string())?
        != root
            .join("script")
            .canonicalize()
            .map_err(|e| e.to_string())?
    {
        return Err("script root differs from frozen group".into());
    }
    let scripts: BTreeMap<String, String> = serde_json::from_slice(
        &std::fs::read(&request.engine.script_manifest_path).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let listed: BTreeMap<String, String> = group["files"]
        .as_object()
        .ok_or("missing group file hashes")?
        .iter()
        .filter_map(|(name, value)| {
            name.strip_prefix("script/")
                .map(|name| (name.to_owned(), value.as_str().unwrap_or("").to_owned()))
        })
        .collect();
    if scripts != listed {
        return Err("script allowlist differs from frozen group".into());
    }
    Ok(())
}
