//! Source-bound, manually authored native cases. These do not prove planner reachability.
use super::{FirstTurnKnowledge, FirstTurnRule};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, path::Path};
use ygo_domain::{CardId, Deck};
use ygo_engine_adapter::*;

fn keys(value: &serde_json::Value, allowed: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("expected a structured object")?;
    if object.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err("unknown field in new native contract".into());
    }
    Ok(())
}
fn strict_decision_values(value: &serde_json::Value) -> Result<(), String> {
    for decision in value.as_array().ok_or("expected native decisions")? {
        keys(decision, &["prompt_id", "player", "choice"])?;
        let choice = &decision["choice"];
        let fields: &[&str] = match choice["kind"].as_str() {
            Some("command") => &["kind", "command", "index"],
            Some("cards") => &["kind", "indices"],
            Some("toggle" | "option" | "chain") => &["kind", "index"],
            Some("finish") => &["kind"],
            Some("yes_no") => &["kind", "yes"],
            Some("position") => &["kind", "position"],
            Some("place") => &["kind", "zones"],
            _ => return Err("unknown native choice kind".into()),
        };
        keys(choice, fields)?;
        if let Some(zones) = choice.get("zones") {
            for zone in zones.as_array().ok_or("expected zones")? {
                keys(zone, &["player", "location", "sequence"])?;
            }
        }
    }
    Ok(())
}
fn strict_decisions<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<Vec<Decision>, D::Error> {
    let value = serde_json::Value::deserialize(deserializer)?;
    strict_decision_values(&value).map_err(serde::de::Error::custom)?;
    serde_json::from_value(value).map_err(serde::de::Error::custom)
}
fn strict_deck<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<Deck, D::Error> {
    let value = serde_json::Value::deserialize(deserializer)?;
    keys(&value, &["main", "extra", "side"]).map_err(serde::de::Error::custom)?;
    serde_json::from_value(value).map_err(serde::de::Error::custom)
}
fn strict_runtime<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<RunDuelRequest, D::Error> {
    let value = serde_json::Value::deserialize(deserializer)?;
    strict_decision_values(&value["decisions"]).map_err(serde::de::Error::custom)?;
    keys(&value["deck"], &["main", "extra", "side"]).map_err(serde::de::Error::custom)?;
    keys(
        &value["interruption"]["opponent_deck"],
        &["main", "extra", "side"],
    )
    .map_err(serde::de::Error::custom)?;
    keys(
        &value["versions"],
        &[
            "rules",
            "catalog",
            "banlist",
            "engine_sha256",
            "cdb_sha256",
            "scripts_sha256",
            "core_commit",
            "initializer",
        ],
    )
    .map_err(serde::de::Error::custom)?;
    serde_json::from_value(value).map_err(serde::de::Error::custom)
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CaseKind {
    Positive,
    Negative,
    Procedure,
    Continuous,
    ProcedureNegative,
    ContinuousNegative,
    Delayed,
    DelayedNegative,
    /// Own tested activation is interrupted by a native opponent Ash response.
    AshResponse,
}

fn procedure_rule(rule: &FirstTurnRule) -> bool {
    rule.description.is_none()
        && matches!(
            rule.operation,
            super::Operation::NormalSummonSet
                | super::Operation::EmptyFieldSpecial
                | super::Operation::PhantomFieldSpecial
                | super::Operation::ExactDarkGraveSpecial
                | super::Operation::LinkProcedure
                | super::Operation::XyzProcedure
        )
}
fn delayed_rule(rule: &FirstTurnRule) -> bool {
    matches!(
        rule.operation,
        super::Operation::DelayedExosisterSet | super::Operation::EndPhaseHandReduce
    )
}
impl CaseKind {
    fn absence(self) -> bool {
        matches!(self, Self::Negative | Self::ProcedureNegative)
    }
    fn bound(self, rule: &FirstTurnRule) -> bool {
        matches!(self, Self::Positive | Self::Procedure | Self::AshResponse)
            || matches!(self, Self::Delayed | Self::DelayedNegative) && rule.description.is_some()
    }
    fn resolution(self, rule: &FirstTurnRule) -> bool {
        self == Self::Positive
            || matches!(self, Self::Delayed | Self::DelayedNegative) && rule.description.is_some()
    }
    pub(super) fn positive(self) -> bool {
        matches!(
            self,
            Self::Positive | Self::Procedure | Self::Continuous | Self::Delayed
        )
    }
    pub(super) fn negative(self) -> bool {
        matches!(
            self,
            Self::Negative
                | Self::ProcedureNegative
                | Self::ContinuousNegative
                | Self::DelayedNegative
        )
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Observation {
    OwnMainWindow,
    DecisionWindow,
    EndPhaseComplete,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeCase {
    pub id: String,
    pub rule_id: String,
    pub kind: CaseKind,
    /// Always explicit: directed rule decks are not tournament samples.
    pub scope: String,
    #[serde(deserialize_with = "strict_deck")]
    pub deck: Deck,
    pub opening_hand: Vec<CardId>,
    pub seed: u64,
    #[serde(deserialize_with = "strict_decisions")]
    pub decisions: Vec<Decision>,
    /// Index of the tested choice; preceding choices are native preparation.
    pub focus: Option<usize>,
    pub observation: Observation,
    pub assertions: Vec<NativeAssertion>,
    pub branch: String,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeCases {
    pub schema_version: u16,
    pub knowledge_id: String,
    pub cases: Vec<NativeCase>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum NativeAssertion {
    Count {
        card_id: u32,
        player: u8,
        location: u8,
        count: usize,
    },
    Delta {
        card_id: u32,
        player: u8,
        location: u8,
        change: i64,
    },
    Instance {
        card_id: u32,
        player: u8,
        location: u8,
        sequence: u32,
        level: Option<u32>,
        rank: Option<u32>,
        position: Option<u32>,
        materials: Option<Vec<u32>>,
        attribute: Option<u32>,
        status_all: Option<u32>,
    },
    Event {
        opcode: u8,
        fields: serde_json::Value,
        count: usize,
    },
    Reason {
        card_id: u32,
        player: u8,
        from: u8,
        to: u8,
        all_bits: u64,
        count: usize,
    },
}

fn subset(expected: &serde_json::Value, actual: &serde_json::Value) -> bool {
    match expected {
        serde_json::Value::Object(keys) => actual.as_object().is_some_and(|a| {
            keys.iter()
                .all(|(k, v)| a.get(k).is_some_and(|value| subset(v, value)))
        }),
        _ => expected == actual,
    }
}
fn raw_event(event: &CoreEventFrame) -> Result<CoreEventFrame, String> {
    let decoded = decode_frame(event.sequence, &event.raw)?;
    if decoded != *event {
        return Err("raw event and decoded evidence differ".into());
    }
    Ok(decoded)
}
fn count(result: &DuelResult, code: u32, player: u8, zone: u8) -> usize {
    result
        .checkpoint
        .cards
        .iter()
        .filter(|c| c.code == code && c.player == player && c.location == zone)
        .count()
}
impl NativeAssertion {
    fn validate(&self) -> Result<(), String> {
        let valid = match self {
            Self::Count {
                card_id,
                player,
                location,
                count,
            } => {
                *card_id > 0
                    && *player <= 1
                    && [1, 2, 4, 8, 16, 32, 64].contains(location)
                    && *count <= 60
            }
            Self::Delta {
                card_id,
                player,
                location,
                change,
            } => {
                *card_id > 0
                    && *player <= 1
                    && [1, 2, 4, 8, 16, 32, 64].contains(location)
                    && (-60..=60).contains(change)
            }
            Self::Instance {
                card_id,
                player,
                location,
                materials,
                ..
            } => {
                *card_id > 0
                    && *player <= 1
                    && [1, 2, 4, 8, 16, 32, 64].contains(location)
                    && materials.as_ref().map_or(true, |cards| {
                        cards.len() <= 64 && cards.iter().all(|c| *c > 0)
                    })
            }
            Self::Event { opcode, fields, .. } => *opcode > 0 && fields.is_object(),
            Self::Reason {
                card_id,
                player,
                from,
                to,
                all_bits,
                ..
            } => *card_id > 0 && *player <= 1 && *from > 0 && *to > 0 && *all_bits > 0,
        };
        if valid {
            Ok(())
        } else {
            Err("native assertion has an unsupported player, zone or resource domain".into())
        }
    }
    pub fn check(&self, before: &DuelResult, after: &DuelResult, since: u64) -> Result<(), String> {
        let valid = match self {
            Self::Count {
                card_id,
                player,
                location,
                count: expected,
            } => count(after, *card_id, *player, *location) == *expected,
            Self::Delta {
                card_id,
                player,
                location,
                change,
            } => {
                count(after, *card_id, *player, *location) as i64
                    - count(before, *card_id, *player, *location) as i64
                    == *change
            }
            Self::Instance {
                card_id,
                player,
                location,
                sequence,
                level,
                rank,
                position,
                materials,
                attribute,
                status_all,
            } => {
                let found: Vec<_> = after
                    .checkpoint
                    .cards
                    .iter()
                    .filter(|c| {
                        c.code == *card_id
                            && c.player == *player
                            && c.location == *location
                            && c.sequence == *sequence
                    })
                    .collect();
                found.len() == 1
                    && found.iter().all(|c| {
                        level.map_or(true, |v| c.level == Some(v))
                            && rank.map_or(true, |v| c.rank == Some(v))
                            && position.map_or(true, |v| c.position == v)
                            && attribute.map_or(true, |v| c.attribute == Some(v))
                            && status_all
                                .map_or(true, |bits| c.status.is_some_and(|v| v & bits == bits))
                            && materials.as_ref().map_or(true, |expected| {
                                let mut e = expected.clone();
                                let mut a = c.overlay.clone();
                                e.sort();
                                a.sort();
                                e == a
                            })
                    })
            }
            Self::Event {
                opcode,
                fields,
                count: expected,
            } => {
                let mut matched = 0;
                for event in after
                    .events
                    .iter()
                    .filter(|e| e.sequence > since && e.opcode == *opcode)
                {
                    let event = raw_event(event)?;
                    if subset(fields, &event.fields) {
                        matched += 1;
                    }
                }
                matched == *expected
            }
            Self::Reason {
                card_id,
                player,
                from,
                to,
                all_bits,
                count: expected,
            } => {
                let mut matched = 0;
                for event in after
                    .events
                    .iter()
                    .filter(|e| e.sequence > since && e.opcode == 50)
                {
                    let event = raw_event(event)?;
                    let f = &event.fields;
                    if f["code"] == *card_id
                        && f["from"]["player"] == *player
                        && f["from"]["location"] == *from
                        && f["to"]["location"] == *to
                        && f["reason"]
                            .as_u64()
                            .is_some_and(|v| v & all_bits == *all_bits)
                    {
                        matched += 1;
                    }
                }
                matched == *expected
            }
        };
        if valid {
            Ok(())
        } else {
            Err(format!("native assertion failed: {self:?}"))
        }
    }
}

impl NativeCase {
    pub fn validate(&self, pack: &FirstTurnKnowledge) -> Result<(), String> {
        let rule = pack.rule(&self.rule_id).ok_or("unknown tested rule")?;
        for assertion in &self.assertions {
            assertion.validate()?;
        }
        if !rule.applicable
            || self.id.is_empty()
            || self.scope != "independent_rule_verification"
            || self.seed != 1
            || self.branch.trim().is_empty()
            || self.limitations.is_empty()
            || self.assertions.is_empty()
            || self.decisions.len() > 1024
            || self
                .decisions
                .windows(2)
                .any(|d| d[0].prompt_id >= d[1].prompt_id)
            || self.decisions.iter().any(|d| d.player > 1)
        {
            return Err("invalid native case scope, assertions or recipe".into());
        }
        ygo_domain::validate_hand(&self.deck, &self.opening_hand)?;
        if !self
            .deck
            .validate(
                &ygo_domain::Banlist::ocg("shape", []),
                &ygo_domain::DeckValidationRules::ocg(),
            )
            .is_legal()
        {
            return Err("invalid case deck shape".into());
        }
        if self.kind.bound(rule) && self.focus.map_or(true, |i| i >= self.decisions.len()) {
            return Err("positive case needs a tested choice".into());
        }
        if self.focus.is_some_and(|i| i >= self.decisions.len()) {
            return Err("invalid preparation boundary".into());
        }
        match self.kind {
            CaseKind::AshResponse
                if rule.description.is_none() || !rule.deck_interaction.is_ash_candidate() =>
            {
                return Err("Ash response case needs a supported Ash-sensitive activation".into())
            }
            CaseKind::Procedure | CaseKind::ProcedureNegative if !procedure_rule(rule) => {
                return Err("procedure case does not describe a summon procedure".into())
            }
            CaseKind::Positive if rule.description.is_none() => {
                return Err("activation case requires an effect description".into())
            }
            CaseKind::Negative | CaseKind::ProcedureNegative
                if self.focus.is_some() || self.observation == Observation::EndPhaseComplete =>
            {
                return Err("negative case needs an actual action window".into())
            }
            CaseKind::Negative if rule.description.is_none() && !procedure_rule(rule) => {
                return Err("continuous/delayed rules need observable counterexamples".into())
            }
            CaseKind::Continuous | CaseKind::ContinuousNegative
                if rule.description.is_some() || procedure_rule(rule) || delayed_rule(rule) =>
            {
                return Err("continuous case does not describe a continuous rule".into())
            }
            CaseKind::Delayed | CaseKind::DelayedNegative
                if !delayed_rule(rule) || self.observation != Observation::EndPhaseComplete =>
            {
                return Err("delayed cases require their completed end-phase boundary".into())
            }
            _ => {}
        }
        Ok(())
    }
}
impl NativeCases {
    pub fn validate(&self, pack: &FirstTurnKnowledge) -> Result<(), String> {
        pack.validate()?;
        if self.schema_version != 1 || self.knowledge_id != pack.id() || self.cases.is_empty() {
            return Err("native suite identity/version/empty cases".into());
        }
        let mut ids = BTreeSet::new();
        for case in &self.cases {
            case.validate(pack)?;
            if !ids.insert(&case.id) {
                return Err("duplicate native case".into());
            }
        }
        Ok(())
    }
}

/// Requires the actual activation, chain solving, successful resolution and chain end.
pub fn resolution_witness(
    rule: &FirstTurnRule,
    result: &DuelResult,
    since: u64,
) -> Result<Vec<u64>, String> {
    let events: Vec<_> = result
        .events
        .iter()
        .filter(|e| e.sequence > since)
        .map(raw_event)
        .collect::<Result<_, _>>()?;
    let start = events
        .iter()
        .position(|e| {
            e.opcode == 70
                && e.fields["code"] == rule.card_id
                && e.fields["player"] == 0
                && e.fields["description"].as_u64() == rule.description
                && e.fields["trigger_location"]
                    .as_u64()
                    .is_some_and(|z| z as u8 & rule.source_locations != 0)
        })
        .ok_or("missing matching actual activation")?;
    let activation = &events[start];
    let chain = activation.fields["chain"]
        .as_u64()
        .ok_or("missing chain index")?;
    let end = events[start..]
        .iter()
        .position(|e| e.opcode == 74)
        .map(|i| start + i)
        .ok_or("chain did not finish")?;
    let chain_events = &events[start..=end];
    if chain_events
        .iter()
        .any(|e| matches!(e.opcode, 75 | 76) && e.fields["chain"] == chain)
    {
        return Err("tested effect was negated, not a resolution positive".into());
    }
    let solve = chain_events
        .iter()
        .find(|e| e.opcode == 72 && e.fields["chain"] == chain)
        .ok_or("missing chain solving")?;
    let solved = chain_events
        .iter()
        .find(|e| e.opcode == 73 && e.fields["chain"] == chain)
        .ok_or("missing chain solved")?;
    if solve.sequence >= solved.sequence {
        return Err("resolution order mismatch".into());
    }
    Ok(vec![
        activation.sequence,
        solve.sequence,
        solved.sequence,
        events[end].sequence,
    ])
}

pub struct NativeEnvironment<'a> {
    pub engine: ProcessEngineConfig,
    pub asset_root: &'a Path,
    pub store: &'a ygo_storage::SnapshotStore,
    pub catalog_id: &'a str,
    pub banlist_id: &'a str,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeCaseResult {
    pub case_id: String,
    pub case_sha256: String,
    pub journal_id: String,
    pub rule_id: String,
    pub kind: CaseKind,
    pub passed: bool,
    pub error: Option<String>,
    #[serde(deserialize_with = "strict_runtime")]
    pub runtime_request: RunDuelRequest,
    pub before_call: u64,
    pub after_call: Option<u64>,
    pub replay_calls: Vec<u64>,
    pub resolution_events: Vec<u64>,
    pub binding: Option<TestChoiceBinding>,
    pub ledger: LedgerStats,
    pub charged_sequence: String,
    pub branch: String,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeVerificationReport {
    pub schema_version: u16,
    pub knowledge_id: String,
    pub source_id: String,
    pub asset_group_id: String,
    pub coverage_id: String,
    pub suite_sha256: String,
    pub worker_sha256: String,
    pub cases: Vec<NativeCaseResult>,
    pub passed: bool,
    /// Case success is not a claim that all rules or branches were tested.
    pub complete_coverage: bool,
    pub missing_rules: Vec<String>,
}

impl NativeVerificationReport {
    /// Recompute claims before opening native assets or charging an audit replay.
    pub fn validate_contract(
        &self,
        pack: &FirstTurnKnowledge,
        suite: &NativeCases,
    ) -> Result<(), String> {
        suite.validate(pack)?;
        let recipe: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../configs/tournament-2026.assets.json"
        ))
        .map_err(|e| e.to_string())?;
        if self.schema_version != 1
            || self.knowledge_id != pack.id()
            || self.source_id != pack.source_id
            || self.asset_group_id != pack.asset_group_id
            || self.coverage_id != pack.coverage_id
            || self.suite_sha256 != crate::hash(&serde_json::to_vec(suite).unwrap())
            || self.cases.len() != suite.cases.len()
            || self.worker_sha256.len() != 64
            || !self
                .worker_sha256
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        {
            return Err("native report provenance/version/suite mismatch".into());
        }
        for (case, result) in suite.cases.iter().zip(&self.cases) {
            let q = &result.runtime_request;
            let r = q.first_turn.as_ref().ok_or("missing native case context")?;
            q.validate_protocol()?;
            let expected_descriptors: Vec<_> = pack
                .potential_ash_effects()
                .iter()
                .map(|r| AshEffectDescriptor {
                    effect_id: r.id.clone(),
                    card_id: r.card_id,
                    description: r.description.unwrap(),
                    source_locations: r.source_locations,
                })
                .collect();
            let opponent: Deck = serde_json::from_str(include_str!(
                "../../../../tests/fixtures/tournament-2026.opponent.json"
            ))
            .map_err(|e| e.to_string())?;
            let interruption = q
                .interruption
                .as_ref()
                .ok_or("missing native controlled opponent")?;
            let expected_journal = crate::hash(
                &serde_json::to_vec(&(
                    &suite.knowledge_id,
                    &result.case_sha256,
                    &q.versions,
                    &q.first_turn,
                    &q.interruption,
                    &self.worker_sha256,
                ))
                .unwrap(),
            );
            let budget = &result.ledger;
            if result.case_id != case.id
                || result.rule_id != case.rule_id
                || result.kind != case.kind
                || result.branch != case.branch
                || result.limitations != case.limitations
                || result.case_sha256 != crate::hash(&serde_json::to_vec(case).unwrap())
                || result.journal_id != expected_journal
                || q.protocol_version != 6
                || q.probe_only
                || q.scenario.is_some()
                || q.deck != case.deck
                || q.opening_hand != case.opening_hand
                || q.seed != case.seed
                || q.decisions != case.decisions
                || r.asset_group_id != pack.asset_group_id
                || r.source_id != pack.source_id
                || r.coverage_id != pack.coverage_id
                || r.knowledge_id != pack.id()
                || r.ash_effects != expected_descriptors
                || interruption.policy
                    != if case.kind == CaseKind::AshResponse {
                        "ash_effect_once"
                    } else {
                        "pass"
                    }
                || interruption.opponent_deck != opponent
                || interruption.effect_id
                    != if case.kind == CaseKind::AshResponse {
                        &case.rule_id
                    } else {
                        &expected_descriptors[0].effect_id
                    }
                    .as_str()
                || q.versions.rules != "ocg-mr5"
                || q.versions.initializer != FIRST_TURN_INITIALIZER
                || q.versions.banlist != recipe["banlist_id"]
                || q.versions.cdb_sha256 != recipe["catalog"]["sha256"]
                || q.versions.engine_sha256 != recipe["core"]["sha256"]
                || q.versions.core_commit != recipe["core"]["core_commit"]
                || q.versions.scripts_sha256 != recipe["scripts"]["manifest_sha256"]
                || budget.limit != 512
                || budget.consumed > 512
                || budget.consumed + budget.reserved > 512
                || budget.completed + budget.unknown != budget.consumed
                || budget.abandoned > budget.unknown
            {
                return Err(format!(
                    "native case request/identity/accounting differs: {}",
                    case.id
                ));
            }
            if result.passed {
                let mut refs = result.replay_calls.clone();
                refs.push(result.before_call);
                if let Some(id) = result.after_call {
                    refs.push(id);
                }
                let unique: BTreeSet<_> = refs.iter().collect();
                if result.error.is_some()
                    || result.before_call == 0
                    || result.replay_calls.len() != 2
                    || refs
                        .iter()
                        .any(|id| *id == 0 || *id > budget.consumed as u64)
                    || unique.len() != refs.len()
                    || case.kind.absence() != result.after_call.is_none()
                    || (case.kind.resolution(pack.rule(&case.rule_id).unwrap())
                        && result.resolution_events.len() != 4)
                    || (!case.kind.resolution(pack.rule(&case.rule_id).unwrap())
                        && !result.resolution_events.is_empty())
                    || result.resolution_events.windows(2).any(|v| v[0] >= v[1])
                    || result.replay_calls.windows(2).any(|v| v[0] >= v[1])
                    || result
                        .replay_calls
                        .first()
                        .is_some_and(|id| *id <= result.after_call.unwrap_or(result.before_call))
                    || result.after_call.is_some_and(|id| id <= result.before_call)
                {
                    return Err("invalid successful native evidence references".into());
                }
                if case.kind.bound(pack.rule(&case.rule_id).unwrap()) {
                    let binding = result
                        .binding
                        .as_ref()
                        .ok_or("missing pre-execution native test binding")?;
                    let rule = pack.rule(&case.rule_id).unwrap();
                    let focus = case.focus.ok_or("missing tested choice")?;
                    let action = ActionMetadata {
                        choice: case.decisions[focus].choice.clone(),
                        source: Some(binding.source.clone()),
                        effect_description: binding.prompt_description,
                        selected: vec![],
                        selection_group: None,
                    };
                    if binding.source.code != rule.card_id
                        || binding.source.player != 0
                        || binding.source.location & rule.source_locations == 0
                        || binding.expected_description != rule.description
                        || bind_test_choice(rule, &action, case.kind).as_ref() != Some(binding)
                    {
                        return Err("native choice binding differs".into());
                    }
                } else if result.binding.is_some() {
                    return Err("non-activation case has invented binding".into());
                }
            } else if result.error.as_ref().map_or(true, |e| e.is_empty()) {
                return Err("failed native case lacks reason".into());
            }
        }
        let missing = missing_rules(pack, &self.cases);
        if self.passed != self.cases.iter().all(|c| c.passed)
            || self.missing_rules != missing
            || self.complete_coverage != missing.is_empty()
        {
            return Err("native coverage/verification claim differs".into());
        }
        Ok(())
    }
}

fn missing_rules(pack: &FirstTurnKnowledge, outputs: &[NativeCaseResult]) -> Vec<String> {
    pack.rules
        .iter()
        .filter(|r| r.applicable)
        .filter(|r| {
            let successful: Vec<_> = outputs
                .iter()
                .filter(|c| c.rule_id == r.id && c.passed)
                .collect();
            !successful.iter().any(|c| c.kind.positive())
                || !successful.iter().any(|c| c.kind.negative())
        })
        .map(|r| r.id.clone())
        .collect()
}

fn native_error(e: WorkerError) -> String {
    format!("{}: {}", e.code, e.message)
}
fn equivalent(a: &DuelResult, b: &DuelResult) -> bool {
    let mut a = a.clone();
    let mut b = b.clone();
    a.peak_working_set_bytes = None;
    b.peak_working_set_bytes = None;
    serde_json::to_value(a).unwrap() == serde_json::to_value(b).unwrap()
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TestChoiceBinding {
    pub kind: String,
    pub source: CardReference,
    pub expected_description: Option<u64>,
    pub prompt_description: Option<u64>,
}
/// Manual experiment binding only. Generic code221 is not an effect identity;
/// its intended effect must be independently confirmed by actual CHAINING.
pub fn bind_test_choice(
    rule: &FirstTurnRule,
    action: &ActionMetadata,
    kind: CaseKind,
) -> Option<TestChoiceBinding> {
    let source = action.source.as_ref()?;
    if source.code != rule.card_id
        || source.player != 0
        || source.location & rule.source_locations == 0
    {
        return None;
    }
    let binding = if kind == CaseKind::Procedure {
        let command = match rule.operation {
            super::Operation::NormalSummonSet => {
                matches!(action.choice, Choice::Command { command: 0 | 3, .. })
            }
            _ => matches!(action.choice, Choice::Command { command: 1, .. }),
        };
        if !command {
            return None;
        }
        "procedure"
    } else if rule.description.is_some()
        && action.effect_description == rule.description
        && matches!(
            action.choice,
            Choice::Command { command: 5, .. }
                | Choice::Chain { index: Some(_) }
                | Choice::YesNo { yes: true }
        )
    {
        "exact_effect_description"
    } else if rule.description.is_some()
        && action.effect_description == Some(221)
        && action.choice == (Choice::YesNo { yes: true })
    {
        "generic_trigger_requires_chain_confirmation"
    } else {
        return None;
    };
    Some(TestChoiceBinding {
        kind: binding.into(),
        source: source.clone(),
        expected_description: rule.description,
        prompt_description: action.effect_description,
    })
}
fn action_matches(rule: &FirstTurnRule, action: &ActionMetadata, kind: CaseKind) -> bool {
    bind_test_choice(rule, action, kind).is_some()
}
fn metadata(result: &DuelResult) -> Result<Vec<ActionMetadata>, String> {
    let prompt = result
        .prompt
        .as_ref()
        .ok_or("missing native operation window")?;
    let event = result
        .events
        .iter()
        .find(|e| e.sequence == prompt.id)
        .ok_or("missing prompt frame")?;
    raw_event(event)?;
    prompt_metadata(prompt.id, &event.raw)
}
fn observation(result: &DuelResult, expected: Observation) -> Result<(), String> {
    if result.error.is_some()
        || !result.coverage_gaps.is_empty()
        || result.status == DuelStatus::Failed
    {
        return Err(format!(
            "native failure/gap: {:?} {:?}",
            result.error, result.coverage_gaps
        ));
    }
    let ok = match expected {
        Observation::OwnMainWindow => {
            result.status == DuelStatus::DecisionRequired
                && result.checkpoint.turn_player == 0
                && result.checkpoint.phase == 4
                && result
                    .prompt
                    .as_ref()
                    .is_some_and(|p| p.player == 0 && p.opcode == 11)
        }
        Observation::DecisionWindow => {
            result.status == DuelStatus::DecisionRequired && result.prompt.is_some()
        }
        Observation::EndPhaseComplete => {
            let frames = result
                .events
                .iter()
                .map(raw_event)
                .collect::<Result<Vec<_>, _>>()?;
            let boundary = frames
                .iter()
                .rev()
                .find(|e| e.opcode == 41 && e.fields["phase"] == 512);
            result.status == DuelStatus::EngineVerified
                && result.prompt.is_none()
                && boundary.is_some_and(|end| {
                    frames.iter().any(|e| {
                        e.sequence > end.sequence && e.opcode == 40 && e.fields["player"] == 1
                    })
                })
        }
    };
    if ok {
        Ok(())
    } else {
        Err("case did not reach its declared observation window".into())
    }
}

/// Runs only real native adapters. Every case has a separate durable 512-call budget.
fn case_stage<A: EngineAdapter>(
    label: &str,
    request: &RunDuelRequest,
    adapter: &A,
    journal: &CallJournal,
    reuse: bool,
) -> Result<(u64, DuelResult), String> {
    if let Some(saved) = if reuse {
        journal.checkpoint(label).map_err(native_error)?
    } else {
        None
    } {
        let id = saved["call_id"]
            .as_u64()
            .ok_or("invalid native case checkpoint")?;
        return journal
            .load_result(id, request)
            .map_err(native_error)?
            .map(|result| (id, result))
            .ok_or("checkpoint references an incomplete native call".into());
    }
    let id = journal.stats().map_err(native_error)?.consumed as u64 + 1;
    let outcome = adapter.run(request);
    // Persist completed failures too. Unknown calls have no checkpoint and cost a retry.
    if !journal
        .unresolved_calls()
        .map_err(native_error)?
        .contains(&id)
    {
        journal
            .save_checkpoint(label, &serde_json::json!({"call_id":id}))
            .map_err(native_error)?;
    }
    outcome.map(|result| (id, result)).map_err(native_error)
}

/// Runs only real native adapters. Every case has a separate durable 512-call budget.
pub fn verify_cases(
    pack: &FirstTurnKnowledge,
    suite: &NativeCases,
    environment: &NativeEnvironment<'_>,
    output_dir: &Path,
) -> Result<NativeVerificationReport, String> {
    run_cases(pack, suite, environment, output_dir, true)
}
fn run_cases(
    pack: &FirstTurnKnowledge,
    suite: &NativeCases,
    environment: &NativeEnvironment<'_>,
    output_dir: &Path,
    reuse: bool,
) -> Result<NativeVerificationReport, String> {
    suite.validate(pack)?;
    pack.validate_sources(environment.asset_root)?;
    let catalog = environment.store.catalog(environment.catalog_id)?;
    let banlist = environment.store.banlist(environment.banlist_id)?;
    let recipe: serde_json::Value = serde_json::from_str(include_str!(
        "../../../../configs/tournament-2026.assets.json"
    ))
    .map_err(|e| e.to_string())?;
    if recipe["banlist_id"] != environment.banlist_id
        || recipe["catalog"]["sha256"] != catalog.source_sha256
    {
        return Err("verification snapshot provenance differs from frozen assets/rules".into());
    }
    let opponent: Deck = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/tournament-2026.opponent.json"
    ))
    .map_err(|e| e.to_string())?;
    if banlist.data.region != "OCG" || banlist.data.version != "2026-10-01" {
        return Err("requires frozen October 2026 OCG rules".into());
    }
    for deck in std::iter::once(&opponent).chain(suite.cases.iter().map(|c| &c.deck)) {
        if !ygo_domain::validate_catalog_deck(deck, &banlist.data, &catalog.data).is_legal() {
            return Err("rule case/opponent deck is not legal".into());
        }
    }
    let descriptors: Vec<_> = pack
        .potential_ash_effects()
        .iter()
        .map(|r| AshEffectDescriptor {
            effect_id: r.id.clone(),
            card_id: r.card_id,
            description: r.description.unwrap(),
            source_locations: r.source_locations,
        })
        .collect();
    let worker_hash = hash_file(&environment.engine.worker_path)?;
    let mut outputs = Vec::new();
    for case in &suite.cases {
        let hash = crate::hash(&serde_json::to_vec(case).unwrap());
        let mut request = runtime_request(
            environment.engine.clone(),
            case.deck.clone(),
            case.opening_hand.clone(),
            case.seed,
        )
        .map_err(native_error)?;
        request.protocol_version = 6;
        request.versions.initializer = FIRST_TURN_INITIALIZER.into();
        request.versions.catalog = environment.catalog_id.into();
        request.versions.banlist = environment.banlist_id.into();
        request.first_turn = Some(FirstTurnConfig {
            asset_group_id: pack.asset_group_id.clone(),
            source_id: pack.source_id.clone(),
            coverage_id: pack.coverage_id.clone(),
            knowledge_id: pack.id(),
            ash_effects: descriptors.clone(),
        });
        request.interruption = Some(InterruptionConfig {
            opponent_deck: opponent.clone(),
            opponent_hand: vec![CardId(14558127)],
            policy: if case.kind == CaseKind::AshResponse {
                "ash_effect_once"
            } else {
                "pass"
            }
            .into(),
            effect_id: if case.kind == CaseKind::AshResponse {
                case.rule_id.clone()
            } else {
                descriptors
                    .first()
                    .ok_or("missing native verification response descriptor")?
                    .effect_id
                    .clone()
            },
            occurrence: 1,
        });
        request.decisions = case.decisions.clone();
        let journal_id = crate::hash(
            &serde_json::to_vec(&(
                &suite.knowledge_id,
                &hash,
                &request.versions,
                &request.first_turn,
                &request.interruption,
                &worker_hash,
            ))
            .unwrap(),
        );
        let journal = CallJournal::open(
            output_dir.join(format!("{journal_id}.jsonl")),
            &case.id,
            &journal_id,
            512,
        )
        .map_err(native_error)?;
        for id in journal.unresolved_calls().map_err(native_error)? {
            journal
                .acknowledge_unknown(
                    id,
                    "verifier resumed without a persisted result; any retry is charged separately",
                )
                .map_err(native_error)?;
        }
        let adapter = JournaledAdapter::new(
            ProcessEngineAdapter::new(environment.engine.clone()),
            journal.clone(),
            CallPurpose::RuleVerification,
        );
        let mut result = NativeCaseResult {
            case_id: case.id.clone(),
            case_sha256: hash,
            journal_id,
            rule_id: case.rule_id.clone(),
            kind: case.kind,
            passed: false,
            error: None,
            runtime_request: request.clone(),
            before_call: 0,
            after_call: None,
            replay_calls: vec![],
            resolution_events: vec![],
            binding: None,
            ledger: journal.stats().map_err(native_error)?,
            charged_sequence: String::new(),
            branch: case.branch.clone(),
            limitations: case.limitations.clone(),
        };
        let outcome = (|| -> Result<(), String> {
            let rule = pack.rule(&case.rule_id).unwrap();
            let mut before_request = request.clone();
            if let Some(focus) = case.focus {
                before_request.decisions.truncate(focus);
            }
            let (id, before) = case_stage("before", &before_request, &adapter, &journal, reuse)?;
            result.before_call = id;
            if case.kind.absence() {
                observation(&before, case.observation)?;
                if metadata(&before)?.iter().any(|a| {
                    action_matches(
                        rule,
                        a,
                        if rule.description.is_some() {
                            CaseKind::Positive
                        } else {
                            CaseKind::Procedure
                        },
                    )
                }) {
                    return Err("negative still offers the tested action".into());
                }
            } else if case.kind.bound(pack.rule(&case.rule_id).unwrap()) {
                let choice = &case.decisions[case.focus.unwrap()];
                if before.prompt.as_ref().map(|p| (p.id, p.player))
                    != Some((choice.prompt_id, choice.player))
                    || !metadata(&before)?
                        .iter()
                        .any(|a| a.choice == choice.choice && action_matches(rule, a, case.kind))
                {
                    return Err("tested choice does not bind to the actual source/effect".into());
                }
                result.binding = metadata(&before)?
                    .iter()
                    .find(|a| a.choice == choice.choice)
                    .and_then(|a| bind_test_choice(rule, a, case.kind));
            }
            let after = if case.kind.absence() {
                before.clone()
            } else {
                let (id, after) = case_stage("after", &request, &adapter, &journal, reuse)?;
                result.after_call = Some(id);
                observation(&after, case.observation)?;
                after
            };
            let since = if case.kind.absence() {
                0
            } else {
                before.events.last().map_or(0, |e| e.sequence)
            };
            if case.kind.resolution(pack.rule(&case.rule_id).unwrap()) {
                result.resolution_events = resolution_witness(rule, &after, since)?;
                if let Some(binding) = &result.binding {
                    if binding.kind == "generic_trigger_requires_chain_confirmation" {
                        let activation = after
                            .events
                            .iter()
                            .find(|e| e.sequence == result.resolution_events[0])
                            .ok_or("missing activation instance")?;
                        let location = &activation.fields["location"];
                        if location["player"] != binding.source.player
                            || location["location"] != binding.source.location
                            || location["sequence"] != binding.source.sequence
                        {
                            return Err(
                                "generic trigger actual activation belongs to a different instance"
                                    .into(),
                            );
                        }
                    }
                }
            }
            if case.kind == CaseKind::AshResponse {
                let ash = super::certification::ash_legality(rule, &after)?
                    .ok_or("native Ash response evidence not reached")?;
                if ash.target_activation <= since {
                    return Err(
                        "Ash responded during preparation rather than to the tested choice".into(),
                    );
                }
            }
            for assertion in &case.assertions {
                assertion.check(&before, &after, since)?;
            }
            for (label, q, actual) in [
                ("replay_before", &before_request, &before),
                ("replay_after", &request, &after),
            ] {
                let replay_adapter = JournaledAdapter::new(
                    ProcessEngineAdapter::new(environment.engine.clone()),
                    journal.clone(),
                    CallPurpose::Replay,
                );
                let (id, replay) = case_stage(label, q, &replay_adapter, &journal, reuse)?;
                result.replay_calls.push(id);
                if !equivalent(actual, &replay) {
                    return Err("independent native witness replay differs".into());
                }
            }
            journal.verify().map_err(native_error)?;
            Ok(())
        })();
        result.passed = outcome.is_ok();
        result.error = outcome.err();
        result.ledger = journal.stats().map_err(native_error)?;
        result.charged_sequence = journal.charged_sequence_id().map_err(native_error)?;
        outputs.push(result);
    }
    let missing_rules = missing_rules(pack, &outputs);
    let report = NativeVerificationReport {
        schema_version: 1,
        knowledge_id: pack.id(),
        source_id: pack.source_id.clone(),
        asset_group_id: pack.asset_group_id.clone(),
        coverage_id: pack.coverage_id.clone(),
        suite_sha256: crate::hash(&serde_json::to_vec(suite).unwrap()),
        worker_sha256: worker_hash,
        passed: outputs.iter().all(|c| c.passed),
        complete_coverage: missing_rules.is_empty(),
        missing_rules,
        cases: outputs,
    };
    report.validate_contract(pack, suite)?;
    Ok(report)
}

pub(super) fn persisted_observations(
    case: &NativeCase,
    result: &NativeCaseResult,
    directory: &Path,
) -> Result<(DuelResult, DuelResult), String> {
    let journal = CallJournal::open(
        directory.join(format!("{}.jsonl", result.journal_id)),
        &case.id,
        &result.journal_id,
        512,
    )
    .map_err(native_error)?;
    journal.verify().map_err(native_error)?;
    if journal.stats().map_err(native_error)? != result.ledger
        || journal.charged_sequence_id().map_err(native_error)? != result.charged_sequence
    {
        return Err("native report ledger differs from persistent evidence".into());
    }
    let mut prefix = result.runtime_request.clone();
    if let Some(focus) = case.focus {
        prefix.decisions.truncate(focus);
    }
    let before = journal
        .load_result(result.before_call, &prefix)
        .map_err(native_error)?
        .ok_or("missing before witness")?;
    if journal
        .call_purpose(result.before_call)
        .map_err(native_error)?
        != CallPurpose::RuleVerification
    {
        return Err("before witness is not an execution call".into());
    }
    let after = if let Some(id) = result.after_call {
        if journal.call_purpose(id).map_err(native_error)? != CallPurpose::RuleVerification {
            return Err("after witness is not an execution call".into());
        }
        journal
            .load_result(id, &result.runtime_request)
            .map_err(native_error)?
            .ok_or("missing after witness")?
    } else {
        before.clone()
    };
    for (index, (request, actual)) in [(&prefix, &before), (&result.runtime_request, &after)]
        .iter()
        .enumerate()
    {
        let id = result.replay_calls[index];
        if journal.call_purpose(id).map_err(native_error)? != CallPurpose::Replay {
            return Err("replay reference names a non-replay call".into());
        }
        let replay = journal
            .load_result(id, request)
            .map_err(native_error)?
            .ok_or("missing independent replay")?;
        if !equivalent(actual, &replay) {
            return Err("persisted native replay differs".into());
        }
    }
    Ok((before, after))
}

/// Audit an imported report against its persistent evidence and fresh independent
/// native executions. Audit calls use separate per-case budgets and output paths.
pub fn verify_report(
    pack: &FirstTurnKnowledge,
    suite: &NativeCases,
    report: &NativeVerificationReport,
    environment: &NativeEnvironment<'_>,
    evidence_dir: &Path,
    audit_dir: &Path,
) -> Result<NativeVerificationReport, String> {
    report.validate_contract(pack, suite)?;
    if !report.passed {
        return Err("failed native cases cannot grant verification evidence".into());
    }
    std::fs::create_dir_all(audit_dir).map_err(|e| e.to_string())?;
    if evidence_dir.canonicalize().map_err(|e| e.to_string())?
        == audit_dir.canonicalize().map_err(|e| e.to_string())?
    {
        return Err("audit must use a separate accounting scope".into());
    }
    let originals: Vec<_> = suite
        .cases
        .iter()
        .zip(&report.cases)
        .map(|(case, result)| persisted_observations(case, result, evidence_dir))
        .collect::<Result<_, _>>()?;
    for ((case, result), (before_call, after)) in
        suite.cases.iter().zip(&report.cases).zip(&originals)
    {
        if case.kind.resolution(pack.rule(&case.rule_id).unwrap()) {
            let since = before_call.events.last().map_or(0, |e| e.sequence);
            if resolution_witness(pack.rule(&case.rule_id).unwrap(), after, since)?
                != result.resolution_events
            {
                return Err("reported resolution references differ from raw native chain".into());
            }
        }
    }
    let audit = run_cases(pack, suite, environment, audit_dir, false)?;
    if !audit.passed {
        return Err("independent imported-evidence audit failed".into());
    }
    for ((case, result), (before, after)) in suite.cases.iter().zip(&audit.cases).zip(originals) {
        let (new_before, new_after) = persisted_observations(case, result, audit_dir)?;
        if !equivalent(&before, &new_before) || !equivalent(&after, &new_after) {
            return Err(
                "imported native evidence differs from independent engine execution".into(),
            );
        }
        if let Some(binding) = &report
            .cases
            .iter()
            .find(|r| r.case_id == case.id)
            .unwrap()
            .binding
        {
            let focus = case.focus.ok_or("missing tested focus")?;
            let expected = metadata(&before)?
                .iter()
                .find(|a| a.choice == case.decisions[focus].choice)
                .and_then(|a| bind_test_choice(pack.rule(&case.rule_id).unwrap(), a, case.kind));
            if expected.as_ref() != Some(binding) {
                return Err(
                    "reported pre-execution source binding differs from native prefix".into(),
                );
            }
        }
    }
    Ok(audit)
}

#[cfg(test)]
mod boundary_tests {
    use super::*;
    #[test]
    fn native_verified_status_alone_does_not_prove_completed_end_phase() {
        let mut result = DuelResult::failure(WorkerError::new("test", "test", "test"));
        result.status = DuelStatus::EngineVerified;
        result.error = None;
        assert!(observation(&result, Observation::EndPhaseComplete).is_err());
        result.events.push(decode_frame(1, &[41, 0, 2]).unwrap());
        assert!(observation(&result, Observation::EndPhaseComplete).is_err());
        result.events.push(decode_frame(2, &[40, 1]).unwrap());
        observation(&result, Observation::EndPhaseComplete).unwrap();
    }
}
