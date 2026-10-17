use crate::{FactCard, Facts};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use ygo_engine_adapter::DuelResult;

/// Public query at a stopped prompt, bound to the exact raw and decision prefix.
/// Its authenticity must additionally be checked by independent native replay.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct QueryWitness {
    pub event: u64,
    pub raw_prefix_sha256: String,
    pub decisions_sha256: String,
    pub public: ygo_engine_adapter::FirstTurnPublicState,
}

impl QueryWitness {
    pub fn capture(result: &DuelResult) -> Result<Self, String> {
        let event = result.events.last().ok_or("missing stopped frame")?;
        let prompt = result.prompt.as_ref().ok_or("missing stopped prompt")?;
        if result.status != ygo_engine_adapter::DuelStatus::DecisionRequired
            || result.error.is_some()
            || prompt.id != event.sequence
            || ygo_engine_adapter::parse_prompt(event.sequence, &event.raw)?.as_ref()
                != Some(prompt)
        {
            return Err("query capture requires the actual stopped prompt".into());
        }
        let raw: Vec<_> = result.events.iter().map(|e| &e.raw).collect();
        Ok(Self {
            event: event.sequence,
            raw_prefix_sha256: digest(&raw),
            decisions_sha256: digest(&result.resolved_decisions),
            public: ygo_engine_adapter::first_turn_public_state(&result.checkpoint),
        })
    }
}

/// Not deserializable or externally constructible: hashes alone cannot mint a
/// successful native query audit. Portable reports retain the supporting ledger.
pub struct AuditedQueries {
    result_hash: String,
    queries_hash: String,
    pub call_ids: Vec<u64>,
}
impl AuditedQueries {
    pub fn matches(&self, result: &DuelResult, witnesses: &[QueryWitness]) -> bool {
        self.result_hash == normalized_hash(result) && self.queries_hash == digest(&witnesses)
    }
}

fn normalized_hash(result: &DuelResult) -> String {
    let mut normalized = result.clone();
    normalized.peak_working_set_bytes = None;
    digest(&normalized)
}

/// Fresh, charged native reruns of each public query and the complete root.
/// This does not reuse cached results or certify semantic rule coverage.
pub fn verify_query_replays(
    request: &ygo_engine_adapter::RunDuelRequest,
    result: &DuelResult,
    witnesses: &[QueryWitness],
    journal: std::sync::Arc<ygo_engine_adapter::CallJournal>,
) -> Result<AuditedQueries, String> {
    request.validate_protocol()?;
    if request.protocol_version != 6 || request.versions != result.versions {
        return Err("query audit runtime versions differ".into());
    }
    audit_queries(
        ygo_engine_adapter::ProcessEngineAdapter::new(request.engine.clone()),
        request,
        result,
        witnesses,
        journal,
    )
}

fn audit_queries<A: ygo_engine_adapter::EngineAdapter>(
    inner: A,
    request: &ygo_engine_adapter::RunDuelRequest,
    result: &DuelResult,
    witnesses: &[QueryWitness],
    journal: std::sync::Arc<ygo_engine_adapter::CallJournal>,
) -> Result<AuditedQueries, String> {
    validate_evidence(result, witnesses)?;
    let start = journal.stats().map_err(|e| e.message)?.consumed as u64;
    let token = format!("query-audit-{}-{start}", normalized_hash(result));
    journal
        .reserve(&token, witnesses.len() + 1)
        .map_err(|e| e.message)?;
    let adapter = ygo_engine_adapter::JournaledAdapter::new(
        inner,
        journal.clone(),
        ygo_engine_adapter::CallPurpose::Witness,
    );
    let checked = (|| {
        for witness in witnesses {
            let mut prefix = request.clone();
            prefix.decisions = result
                .resolved_decisions
                .iter()
                .filter(|d| d.prompt_id < witness.event)
                .cloned()
                .collect();
            let actual = adapter
                .run_reserved(&prefix, &token)
                .map_err(|e| e.message)?;
            let queried = QueryWitness::capture(&actual)?;
            if queried.event != witness.event
                || serde_json::to_value(&queried).unwrap() != serde_json::to_value(witness).unwrap()
            {
                return Err("public query differs from independent native prefix".into());
            }
            if actual.versions != result.versions {
                return Err("query prefix runtime changed".into());
            }
        }
        let mut full = request.clone();
        full.decisions = result.resolved_decisions.clone();
        let replay = adapter.run_reserved(&full, &token).map_err(|e| e.message)?;
        if normalized_hash(&replay) != normalized_hash(result) {
            return Err("complete root differs from independent native replay".into());
        }
        Ok(AuditedQueries {
            result_hash: normalized_hash(result),
            queries_hash: digest(&witnesses),
            call_ids: (start + 1..=start + witnesses.len() as u64 + 1).collect(),
        })
    })();
    if journal
        .remaining_reservation(&token)
        .map_err(|e| e.message)?
        .is_some()
    {
        journal.release(&token).map_err(|e| e.message)?;
    }
    checked
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActivationWitness {
    pub event: u64,
    pub chain: u64,
    pub rule_id: Option<String>,
    pub source: FactCard,
    pub after_cost: Option<FactCard>,
    pub resolved: bool,
    pub negated: bool,
    pub activation_negated: bool,
    pub solving_event: Option<u64>,
    pub resolution_event: Option<u64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DrawWitness {
    pub event: u64,
    pub player: u8,
    pub count: usize,
    /// Only our actually drawn identities; opponent draws expose count only.
    pub cards: Vec<u32>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObservedLocation {
    pub player: u8,
    pub location: u8,
    /// Hidden deck/hand/extra positions never enter the planning state.
    pub sequence: Option<u32>,
    pub position: Option<u32>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MovementWitness {
    pub instance: String,
    pub identity_known: bool,
    pub event: u64,
    pub reason: u32,
    pub from: ObservedLocation,
    pub to: ObservedLocation,
    pub epoch_before: u64,
    pub epoch_after: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FirstTurnTrace {
    pub facts: Facts,
    pub material_instances: Vec<FactCard>,
    pub activations: Vec<ActivationWitness>,
    pub movements: Vec<MovementWitness>,
    pub epochs: BTreeMap<String, u64>,
    pub normal_remaining: Option<u8>,
    pub used: BTreeMap<String, usize>,
    pub draws: Vec<DrawWitness>,
    pub window: TraceWindow,
    pub identity_bindings: Vec<IdentityBinding>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdentityBinding {
    pub instance: String,
    pub event: u64,
    pub prior_event: u64,
    pub basis: String,
    pub rule_id: Option<String>,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TraceWindow {
    OwnMainAction,
    Pending,
    OwnTurnEnded,
    Unknown,
}

fn digest(value: &impl Serialize) -> String {
    format!("{:x}", Sha256::digest(serde_json::to_vec(value).unwrap()))
}

pub(super) fn from_query(
    c: &ygo_engine_adapter::StateCard,
    instance: String,
    identity_known: bool,
    proper_xyz: Option<bool>,
) -> FactCard {
    FactCard {
        instance,
        identity_known,
        type_flags: c.type_flags,
        code: c.code,
        player: c.player,
        location: c.location,
        sequence: c.sequence,
        position: c.position,
        level: c.level,
        rank: c.rank,
        proper_xyz,
        materials: c.overlay.clone(),
        materials_complete: Some(true),
    }
}

pub(super) fn public_location(v: &serde_json::Value) -> ObservedLocation {
    let player = v["player"].as_u64().unwrap_or(0) as u8;
    let location = v["location"].as_u64().unwrap_or(0) as u8;
    let hidden = location == 1 || (player == 1 && matches!(location, 2 | 64));
    ObservedLocation {
        player,
        location,
        sequence: (!hidden).then(|| v["sequence"].as_u64().unwrap_or(0) as u32),
        position: (!hidden).then(|| v["position"].as_u64().unwrap_or(0) as u32),
    }
}

pub(super) fn reconcile(
    tracked: &mut [FactCard],
    cards: &[ygo_engine_adapter::StateCard],
    shuffled: &mut BTreeMap<String, u64>,
    bindings: &mut Vec<IdentityBinding>,
    event: u64,
) {
    for c in tracked.iter_mut() {
        let matches = cards
            .iter()
            .filter(|q| {
                q.code == c.code
                    && q.player == c.player
                    && q.location == c.location
                    && q.sequence == c.sequence
            })
            .collect::<Vec<_>>();
        if matches.len() == 1 {
            *c = from_query(
                matches[0],
                c.instance.clone(),
                c.identity_known,
                c.proper_xyz,
            );
        }
    }
    // A shuffle does not tell same-name instances apart. Only a unique leftover
    // original and a unique unassigned actual slot permit this bijection.
    for i in 0..tracked.len() {
        let c = &tracked[i];
        if c.identity_known
            || c.location != 2
            || c.sequence != u32::MAX
            || !shuffled.contains_key(&c.instance)
        {
            continue;
        }
        let originals = tracked
            .iter()
            .filter(|x| {
                x.code == c.code
                    && x.player == c.player
                    && x.location == 2
                    && !x.identity_known
                    && shuffled.contains_key(&x.instance)
            })
            .count();
        let unassigned = cards
            .iter()
            .filter(|q| {
                q.code == c.code
                    && q.player == c.player
                    && q.location == 2
                    && !tracked.iter().any(|x| {
                        x.player == q.player
                            && x.location == 2
                            && x.sequence == q.sequence
                            && x.sequence != u32::MAX
                    })
            })
            .collect::<Vec<_>>();
        if originals == 1 && unassigned.len() == 1 {
            let prior_event = shuffled.remove(&c.instance).unwrap();
            bindings.push(IdentityBinding {
                instance: c.instance.clone(),
                event,
                prior_event,
                basis: "unique_unassigned_query_after_shuffle".into(),
                rule_id: None,
            });
            tracked[i] = from_query(unassigned[0], c.instance.clone(), true, c.proper_xyz);
        }
    }
}

pub(super) fn validate_evidence(
    result: &DuelResult,
    witnesses: &[QueryWitness],
) -> Result<(), String> {
    if result.protocol_version != 6
        || result.versions.initializer != ygo_engine_adapter::FIRST_TURN_INITIALIZER
        || witnesses.is_empty()
    {
        return Err("v6 trace requires its initializer and initial public witness".into());
    }
    for (i, e) in result.events.iter().enumerate() {
        let decoded = ygo_engine_adapter::decode_frame(i as u64 + 1, &e.raw)?;
        if e.sequence != decoded.sequence
            || e.opcode != decoded.opcode
            || e.fields != decoded.fields
            || e.supported != decoded.supported
        {
            return Err("decoded event does not match original raw frame".into());
        }
        let locations: Vec<_> = match e.opcode {
            50 => vec![&e.fields["from"], &e.fields["to"]],
            54 | 60 | 62 | 70 => vec![&e.fields["location"]],
            83 => e.fields["targets"]
                .as_array()
                .map_or_else(Vec::new, |xs| xs.iter().collect()),
            _ => vec![],
        };
        if locations
            .iter()
            .any(|loc| loc["player"].as_u64().map_or(true, |p| p > 1))
        {
            return Err("invalid raw controller coordinate".into());
        }
    }
    let mut previous_decision = 0;
    for d in &result.resolved_decisions {
        let event = result
            .events
            .get(
                d.prompt_id
                    .checked_sub(1)
                    .ok_or("invalid decision sequence")? as usize,
            )
            .ok_or("missing decision prompt")?;
        let prompt = ygo_engine_adapter::parse_prompt(d.prompt_id, &event.raw)?
            .ok_or("decision has no supported prompt")?;
        if d.player > 1
            || d.prompt_id <= previous_decision
            || prompt.player != d.player
            || !prompt.actions.iter().any(|a| a.choice == d.choice)
        {
            return Err("invalid or unordered actual decision".into());
        }
        previous_decision = d.prompt_id;
    }
    let mut previous = 0;
    for w in witnesses {
        if w.event <= previous || w.event as usize > result.events.len() {
            return Err("invalid query witness sequence".into());
        }
        let raw: Vec<_> = result.events[..w.event as usize]
            .iter()
            .map(|e| &e.raw)
            .collect();
        let decisions: Vec<_> = result
            .resolved_decisions
            .iter()
            .filter(|d| d.prompt_id < w.event)
            .collect();
        if digest(&raw) != w.raw_prefix_sha256 || digest(&decisions) != w.decisions_sha256 {
            return Err("query witness prefix mismatch".into());
        }
        let event = &result.events[w.event as usize - 1];
        if ygo_engine_adapter::parse_prompt(w.event, &event.raw)?.is_none() {
            return Err("public query witness is not at a stopped prompt".into());
        }
        let mut positions = std::collections::BTreeSet::new();
        for c in &w.public.visible.cards {
            if c.player > 1
                || !matches!(c.location, 2 | 4 | 8 | 16 | 32 | 64)
                || (c.player == 1 && (matches!(c.location, 2 | 64) || c.position & 5 == 0))
                || !positions.insert((c.player, c.location, c.sequence))
            {
                return Err("invalid or hidden public query card".into());
            }
        }
        previous = w.event;
    }
    let first = &witnesses[0];
    if first.public.visible.turn != 1
        || first.public.visible.turn_player != 0
        || first.public.visible.phase != 4
        || result
            .resolved_decisions
            .iter()
            .any(|d| d.prompt_id < first.event)
        || first
            .public
            .visible
            .cards
            .iter()
            .any(|c| c.player != 0 || !matches!(c.location, 2 | 64))
        || first
            .public
            .visible
            .cards
            .iter()
            .filter(|c| c.location == 2)
            .count()
            != 5
    {
        return Err("trace must start at the untouched own first main phase".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use ygo_engine_adapter::*;

    #[test]
    fn same_name_count_mismatch_never_picks_an_original_by_name() {
        let mut tracked = vec![
            FactCard {
                instance: "a".into(),
                code: 7,
                location: 2,
                sequence: u32::MAX,
                ..Default::default()
            },
            FactCard {
                instance: "b".into(),
                code: 7,
                location: 2,
                sequence: u32::MAX,
                ..Default::default()
            },
        ];
        let cards = vec![StateCard {
            code: 7,
            location: 2,
            sequence: 0,
            ..Default::default()
        }];
        let mut shuffled = BTreeMap::from([("a".into(), 1), ("b".into(), 1)]);
        let mut bindings = vec![];
        reconcile(&mut tracked, &cards, &mut shuffled, &mut bindings, 2);
        assert!(tracked
            .iter()
            .all(|c| !c.identity_known && c.sequence == u32::MAX));
        assert!(bindings.is_empty());
    }

    fn fixture() -> (DuelResult, Vec<QueryWitness>, RunDuelRequest) {
        let mut data: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/tournament-2026.trace-resource.json"
        ))
        .unwrap();
        data["result"]["events"] = serde_json::json!([]);
        let mut result: DuelResult = serde_json::from_value(data["result"].clone()).unwrap();
        result.events = data["frames"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .map(|(i, raw)| {
                decode_frame(
                    i as u64 + 1,
                    &serde_json::from_value::<Vec<u8>>(raw.clone()).unwrap(),
                )
                .unwrap()
            })
            .collect();
        let witnesses = serde_json::from_value(data["witnesses"].clone()).unwrap();
        let report: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
        ))
        .unwrap();
        (
            result,
            witnesses,
            serde_json::from_value(report["cases"][0]["runtime_request"].clone()).unwrap(),
        )
    }
    fn journal(limit: usize) -> Arc<CallJournal> {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "query-audit-{}-{}.jsonl",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        CallJournal::open(&p, "query-audit-unit", "recorded-oracle", limit).unwrap()
    }
    struct RecordedOracle {
        root: DuelResult,
        witnesses: Vec<QueryWitness>,
        calls: Arc<AtomicUsize>,
    }
    impl EngineAdapter for RecordedOracle {
        fn doctor(&self) -> DoctorReport {
            panic!("audit must not use uncharged doctor")
        }
        fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            if request.decisions == self.root.resolved_decisions {
                return Ok(self.root.clone());
            }
            let witness = self
                .witnesses
                .iter()
                .find(|w| {
                    self.root
                        .resolved_decisions
                        .iter()
                        .filter(|d| d.prompt_id < w.event)
                        .cloned()
                        .collect::<Vec<_>>()
                        == request.decisions
                })
                .unwrap();
            let mut result = self.root.clone();
            result.events.truncate(witness.event as usize);
            result.resolved_decisions = request.decisions.clone();
            result.prompt =
                parse_prompt(witness.event, &result.events.last().unwrap().raw).unwrap();
            result.checkpoint = witness.public.visible.clone();
            for (code, count) in &witness.public.own_deck_counts {
                for _ in 0..*count {
                    result.checkpoint.cards.push(StateCard {
                        code: *code,
                        player: 0,
                        location: 1,
                        ..Default::default()
                    });
                }
            }
            for _ in 0..witness.public.opponent_hand_count {
                result.checkpoint.cards.push(StateCard {
                    code: 14558127,
                    player: 1,
                    location: 2,
                    ..Default::default()
                });
            }
            for _ in 0..witness.public.opponent_deck_count {
                result.checkpoint.cards.push(StateCard {
                    code: 0,
                    player: 1,
                    location: 1,
                    ..Default::default()
                });
            }
            Ok(result)
        }
    }
    fn oracle(
        root: &DuelResult,
        witnesses: &[QueryWitness],
        calls: &Arc<AtomicUsize>,
    ) -> RecordedOracle {
        RecordedOracle {
            root: root.clone(),
            witnesses: witnesses.to_vec(),
            calls: calls.clone(),
        }
    }
    #[test]
    fn query_audit_reexecutes_each_prefix_and_root_and_charges_repeated_audits() {
        let (root, witnesses, request) = fixture();
        let j = journal(512);
        let calls = Arc::new(AtomicUsize::new(0));
        let receipt = audit_queries(
            oracle(&root, &witnesses, &calls),
            &request,
            &root,
            &witnesses,
            j.clone(),
        )
        .unwrap();
        assert_eq!(receipt.call_ids.len(), 8);
        assert!(receipt.matches(&root, &witnesses));
        let mut forged = root.clone();
        forged.checkpoint.cards[0].attack += 1;
        assert!(!receipt.matches(&forged, &witnesses));
        audit_queries(
            oracle(&root, &witnesses, &calls),
            &request,
            &root,
            &witnesses,
            j.clone(),
        )
        .unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 16);
        assert_eq!(j.stats().unwrap().consumed, 16);
        assert_eq!(j.stats().unwrap().reserved, 0);
    }
    #[test]
    fn a_forged_query_is_rejected_by_new_observation_despite_matching_prefix_hashes() {
        let (root, witnesses, request) = fixture();
        let j = journal(512);
        let calls = Arc::new(AtomicUsize::new(0));
        let mut forged = witnesses.clone();
        forged[0].public.visible.cards[0].level = Some(99);
        assert!(audit_queries(
            oracle(&root, &witnesses, &calls),
            &request,
            &root,
            &forged,
            j.clone()
        )
        .is_err());
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(j.stats().unwrap().consumed, 1);
        assert_eq!(j.stats().unwrap().reserved, 0);
    }
    #[test]
    fn insufficient_replay_reservation_prevents_starting_any_audit_call() {
        let (root, witnesses, request) = fixture();
        let j = journal(7);
        let calls = Arc::new(AtomicUsize::new(0));
        assert!(audit_queries(
            oracle(&root, &witnesses, &calls),
            &request,
            &root,
            &witnesses,
            j.clone()
        )
        .is_err());
        assert_eq!(calls.load(Ordering::SeqCst), 0);
        assert_eq!(j.stats().unwrap().consumed, 0);
    }
}
