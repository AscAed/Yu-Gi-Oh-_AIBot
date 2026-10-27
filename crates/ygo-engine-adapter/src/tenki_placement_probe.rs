//! Independent, fixed six-call Tenki placement/opcode-13 research scope.
use crate::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

pub const TENKI_PLACEMENT_SCOPE: &str = "tenki-placement-probe-v1";
pub const TENKI_PLACEMENT_CONFIRMATION_SCOPE: &str = "tenki-placement-confirmation-v1";
pub const TENKI_PLACEMENT_VALIDATION_SCOPE: &str = "tenki-placement-validation-v1";
const OLD_SCOPE: &str = "tenki-prompt-probe-v1";
const OLD_STAGE1_SHA256: &str = "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76";
const OLD_STAGE2_REQUEST_SHA256: &str =
    "cf2d94a3e5af74156c0bf47a3b380f7b7eab27c9784267fddb2d15a0f685284a";
const OLD_STAGE2_SHA256: &str = "9c32ae3020afcc088b188a9d7770eeb5ec309dc3be86bff5c8e86b4e974429f4";
const PLACE_MASK: u32 = 0xffff_e0ff;
const YES_NO_DESCRIPTION: u64 = 59_877_851_398_144;
const DECK_HASH: &str = "367b15e0e63359108fa74a33ee1db17d77f766aba88f2df3e0689ba023696e47";
const VERSIONS_HASH: &str = "cf7c2fefe9ed6d62c71f1f138cfee50428de80f1b9d7dbf66c20ef389071e6b1";
const NEW_ROOT: &str = "data/runtime/p1-tenki-placement-native-2026-10-22/research";
const CONFIRMATION_ROOT: &str =
    "data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/research";
const VALIDATION_ROOT: &str =
    "data/runtime/p1-tenki-placement-validation-native-2026-10-23/research";
pub const TENKI_PLACEMENT_VALIDATION_WORKER_RELATIVE_PATH: &str =
    "data/runtime/p1-tenki-placement-validation-native-2026-10-23/native-artifacts/ygo-engine-worker.exe";
const BASELINE_ROOT: &str = "data/runtime/p1-tenki-probe-native-2026-10-21/research";

#[derive(Clone, Copy)]
struct BatchSpec {
    scope: &'static str,
    key_prefix: &'static str,
    stage_kind: &'static str,
    allow_auto_decisions: bool,
    full_window_result: bool,
}

const PLACEMENT_SPEC: BatchSpec = BatchSpec {
    scope: TENKI_PLACEMENT_SCOPE,
    key_prefix: "tenki-placement",
    stage_kind: "native_tenki_placement_stage",
    allow_auto_decisions: false,
    full_window_result: false,
};
const CONFIRMATION_SPEC: BatchSpec = BatchSpec {
    scope: TENKI_PLACEMENT_CONFIRMATION_SCOPE,
    key_prefix: "tenki-placement-confirmation",
    stage_kind: "native_tenki_placement_confirmation_stage",
    allow_auto_decisions: false,
    full_window_result: true,
};
const VALIDATION_SPEC: BatchSpec = BatchSpec {
    scope: TENKI_PLACEMENT_VALIDATION_SCOPE,
    key_prefix: "tenki-placement-validation",
    stage_kind: "native_tenki_placement_validation_stage",
    allow_auto_decisions: true,
    full_window_result: true,
};

const fn is_sha256_hex(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 64 {
        return false;
    }
    let mut index = 0;
    while index < bytes.len() {
        let byte = bytes[index];
        if !((byte >= b'0' && byte <= b'9') || (byte >= b'a' && byte <= b'f')) {
            return false;
        }
        index += 1;
    }
    true
}

const _: () = {
    assert!(is_sha256_hex(OLD_STAGE1_SHA256));
    assert!(is_sha256_hex(OLD_STAGE2_REQUEST_SHA256));
    assert!(is_sha256_hex(OLD_STAGE2_SHA256));
    assert!(is_sha256_hex(DECK_HASH));
    assert!(is_sha256_hex(VERSIONS_HASH));
};

pub fn tenki_placement_research_root() -> Result<PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(NEW_ROOT))
}

pub fn tenki_placement_confirmation_research_root() -> Result<PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(CONFIRMATION_ROOT))
}

pub fn tenki_placement_validation_research_root() -> Result<PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(VALIDATION_ROOT))
}

fn fail(message: &str) -> WorkerError {
    WorkerError::new("tenki_placement_gate", "tenki_placement_probe", message)
}

fn encoded<T: Serialize>(value: &T) -> Result<Value, WorkerError> {
    serde_json::to_value(value).map_err(|_| fail("serialization failed"))
}

fn request_hash(request: &RunDuelRequest) -> Result<String, WorkerError> {
    Ok(digest(
        &serde_json::to_vec(request).map_err(|_| fail("request serialization"))?,
    ))
}

fn unix_now() -> Result<u64, WorkerError> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|time| time.as_secs())
        .map_err(|_| fail("invalid system clock"))
}

pub fn tenki_placement_purpose(stage: u8) -> Result<CallPurpose, WorkerError> {
    match stage {
        1 | 2 => Ok(CallPurpose::Probe),
        3 | 5 => Ok(CallPurpose::Execution),
        4 | 6 => Ok(CallPurpose::Replay),
        _ => Err(fail("stage outside fixed six-call scope")),
    }
}

/// Validate the exact pre-call accounting prefix for a fixed slot.
pub fn validate_placement_slot(stage: u8, stats: &LedgerStats) -> Result<(), WorkerError> {
    tenki_placement_purpose(stage)?;
    if stats.limit != 6
        || stats.consumed != stage as usize - 1
        || stats.completed != stats.consumed
        || stats.unknown != 0
        || stats.reserved != 0
        || stats.abandoned != 0
    {
        return Err(fail("ledger prefix is not the exact settled predecessor"));
    }
    Ok(())
}

fn frozen_input(request: &RunDuelRequest) -> Result<(), WorkerError> {
    let deck_binding = json!({
        "deck": request.deck,
        "opening_hand": request.opening_hand,
        "seed": request.seed
    });
    if digest(&serde_json::to_vec(&deck_binding).map_err(|_| fail("deck encoding"))?) != DECK_HASH
        || digest(
            &serde_json::to_vec(&encoded(&request.versions)?)
                .map_err(|_| fail("version encoding"))?,
        ) != VERSIONS_HASH
    {
        return Err(fail("frozen Tenki deck or versions differ"));
    }
    if request.protocol_version != 2
        || request.engine.timeout_ms != 30_000
        || request.probe_only
        || request.scenario.is_some()
        || request.interruption.is_some()
        || request.first_turn.is_some()
        || request.research_capture.is_some()
        || request.seed != 1
        || request.deck.main.len() != 40
        || request.deck.extra.len() != 3
        || !request.deck.side.is_empty()
        || request.opening_hand.len() != 5
        || request.deck.main.iter().any(|card| card.0 == 85_138_716)
        || request
            .deck
            .main
            .iter()
            .filter(|card| card.0 == 57_103_969)
            .count()
            != 1
        || request
            .opening_hand
            .iter()
            .filter(|card| card.0 == 57_103_969)
            .count()
            != 1
        || request
            .deck
            .main
            .iter()
            .filter(|card| card.0 == 69_247_929)
            .count()
            .checked_sub(
                request
                    .opening_hand
                    .iter()
                    .filter(|card| card.0 == 69_247_929)
                    .count(),
            )
            != Some(2)
    {
        return Err(fail("unsupported frozen Tenki request"));
    }
    let mut remaining = std::collections::BTreeMap::new();
    for card in &request.deck.main {
        *remaining.entry(card.0).or_insert(0usize) += 1;
    }
    for card in &request.opening_hand {
        let count = remaining
            .get_mut(&card.0)
            .ok_or_else(|| fail("opening card absent from main deck"))?;
        *count = count
            .checked_sub(1)
            .ok_or_else(|| fail("opening multiplicity exceeds deck"))?;
    }
    Ok(())
}

fn validate_decision_prefix(stage: u8, request: &RunDuelRequest) -> Result<(), WorkerError> {
    let expected_len = if stage == 1 {
        1
    } else if stage == 2 {
        2
    } else {
        3
    };
    if request.decisions.len() != expected_len {
        return Err(fail("request decision prefix length differs"));
    }
    let first = &request.decisions[0];
    if first.prompt_id != 7
        || first.player != 0
        || first.choice
            != (Choice::Command {
                command: 5,
                index: 0,
            })
    {
        return Err(fail("frozen Tenki activation prefix differs"));
    }
    if stage >= 2 {
        let placement = &request.decisions[1];
        let Choice::Place { zones } = &placement.choice else {
            return Err(fail("fixed spell-zone placement required"));
        };
        if placement.player != 0
            || placement.prompt_id <= first.prompt_id
            || zones
                != &[Zone {
                    player: 0,
                    location: 8,
                    sequence: 0,
                }]
        {
            return Err(fail("fixed zone-zero decision differs"));
        }
    }
    if stage >= 3 {
        let response = &request.decisions[2];
        let expected_yes = matches!(stage, 5 | 6);
        if response.player != 0
            || response.prompt_id <= request.decisions[1].prompt_id
            || response.choice != (Choice::YesNo { yes: expected_yes })
        {
            return Err(fail("fixed opcode13 branch differs"));
        }
    }
    Ok(())
}

fn validate_validation_decision_prefix(
    stage: u8,
    request: &RunDuelRequest,
) -> Result<(), WorkerError> {
    if stage == 1 {
        return validate_decision_prefix(1, request);
    }
    if request.decisions.len() < 2 {
        return Err(fail("validation request lacks a public menu decision"));
    }
    let first = &request.decisions[0];
    if first.prompt_id != 7
        || first.player != 0
        || first.choice
            != (Choice::Command {
                command: 5,
                index: 0,
            })
    {
        return Err(fail("frozen Tenki activation prefix differs"));
    }
    if request
        .decisions
        .windows(2)
        .any(|pair| pair[0].prompt_id >= pair[1].prompt_id)
    {
        return Err(fail("validation decision order differs"));
    }
    let final_decision = request.decisions.last().expect("length checked");
    let expected = match stage {
        2 => Choice::Place {
            zones: vec![Zone {
                player: 0,
                location: 8,
                sequence: 0,
            }],
        },
        3 | 4 => Choice::YesNo { yes: false },
        5 | 6 => Choice::YesNo { yes: true },
        _ => return Err(fail("stage outside fixed validation scope")),
    };
    if final_decision.player != 0
        || final_decision.prompt_id <= first.prompt_id
        || final_decision.choice != expected
    {
        return Err(fail("validation request final public choice differs"));
    }
    Ok(())
}

fn prompt_events(result: &DuelResult) -> Result<Vec<(CoreEventFrame, Prompt)>, String> {
    if result
        .events
        .windows(2)
        .any(|pair| pair[0].sequence >= pair[1].sequence)
    {
        return Err("event sequence is not increasing".into());
    }
    let mut prompts = Vec::new();
    for frame in &result.events {
        if !frame.supported {
            return Err("unsupported core event in frozen prefix".into());
        }
        if matches!(frame.opcode, 11..=16 | 18 | 19 | 24 | 26) {
            let prompt = parse_prompt(frame.sequence, &frame.raw)?.ok_or("raw prompt missing")?;
            let recorded: Prompt = serde_json::from_value(
                frame
                    .fields
                    .get("prompt")
                    .cloned()
                    .ok_or("recorded prompt missing")?,
            )
            .map_err(|_| "recorded prompt malformed")?;
            if prompt != recorded {
                return Err("raw and normalized prompt differ".into());
            }
            let responses = prompt
                .actions
                .iter()
                .map(|action| action.bytes.clone())
                .collect::<Vec<_>>();
            if !audit_prompt_responses(&frame.raw, &responses)?.matches {
                return Err("independent response audit failed".into());
            }
            prompts.push((frame.clone(), prompt));
        }
    }
    Ok(prompts)
}

fn check_response_set(prompt: &Prompt, expected: &[Vec<u8>]) -> Result<(), String> {
    let actual = prompt
        .actions
        .iter()
        .map(|action| action.bytes.clone())
        .collect::<Vec<_>>();
    let actual_set = actual.iter().cloned().collect::<BTreeSet<_>>();
    let expected_set = expected.iter().cloned().collect::<BTreeSet<_>>();
    if actual.len() != actual_set.len()
        || actual_set != expected_set
        || expected.len() != expected_set.len()
    {
        return Err("exact response set differs".into());
    }
    Ok(())
}

fn validate_place_prompt(frame: &CoreEventFrame, prompt: &Prompt) -> Result<(), String> {
    if frame.raw.len() != 7
        || frame.raw[..3] != [18, 0, 1]
        || u32::from_le_bytes(frame.raw[3..7].try_into().map_err(|_| "mask length")?) != PLACE_MASK
        || prompt.player != 0
        || prompt.opcode != 18
    {
        return Err("frozen opcode18 frame differs".into());
    }
    let expected = (0..5)
        .map(|sequence| vec![0, 8, sequence])
        .collect::<Vec<_>>();
    check_response_set(prompt, &expected)?;
    let mut coordinates = BTreeSet::new();
    for action in &prompt.actions {
        let Choice::Place { zones } = &action.choice else {
            return Err("non-place action in opcode18 menu".into());
        };
        if zones.len() != 1 {
            return Err("multi-zone action in opcode18 menu".into());
        }
        let zone = &zones[0];
        if zone.player != 0
            || zone.location != 8
            || zone.sequence > 4
            || action.bytes != [0, 8, zone.sequence]
            || !coordinates.insert(zone.sequence)
        {
            return Err("invalid or duplicate opcode18 coordinate".into());
        }
    }
    if coordinates != (0..5).collect() {
        return Err("incomplete spell/trap zone menu".into());
    }
    Ok(())
}

fn validate_yes_no(frame: &CoreEventFrame, prompt: &Prompt) -> Result<(), String> {
    let mut expected_raw = vec![13, 0];
    expected_raw.extend(YES_NO_DESCRIPTION.to_le_bytes());
    if frame.raw != expected_raw || prompt.opcode != 13 || prompt.player != 0 {
        return Err("frozen opcode13 frame differs".into());
    }
    check_response_set(prompt, &[vec![0, 0, 0, 0], vec![1, 0, 0, 0]])?;
    if prompt.actions.len() != 2
        || prompt.actions[0].choice != (Choice::YesNo { yes: false })
        || prompt.actions[0].bytes != [0, 0, 0, 0]
        || prompt.actions[1].choice != (Choice::YesNo { yes: true })
        || prompt.actions[1].bytes != [1, 0, 0, 0]
    {
        return Err("opcode13 false/true ordering or encoding differs".into());
    }
    Ok(())
}

fn validate_targets(frame: &CoreEventFrame, prompt: &Prompt) -> Result<(), String> {
    let raw = &frame.raw;
    if raw.len() != 43
        || raw[..3] != [15, 0, 0]
        || u32::from_le_bytes(raw[3..7].try_into().map_err(|_| "count")?) != 1
        || u32::from_le_bytes(raw[7..11].try_into().map_err(|_| "minimum")?) != 1
        || u32::from_le_bytes(raw[11..15].try_into().map_err(|_| "maximum")?) != 2
        || prompt.opcode != 15
        || prompt.player != 0
        || prompt.actions.len() != 2
    {
        return Err("expected exact two-card opcode15 prompt".into());
    }
    let mut sequences = BTreeSet::new();
    for (index, record) in raw[15..].chunks_exact(14).enumerate() {
        let code = u32::from_le_bytes(record[..4].try_into().map_err(|_| "target code")?);
        let sequence = u32::from_le_bytes(record[6..10].try_into().map_err(|_| "target sequence")?);
        let position =
            u32::from_le_bytes(record[10..14].try_into().map_err(|_| "target position")?);
        let action = &prompt.actions[index];
        let bytes = [0u32, 1, index as u32]
            .iter()
            .flat_map(|value| value.to_le_bytes())
            .collect::<Vec<_>>();
        if code != 69_247_929
            || record[4] != 0
            || record[5] != 1
            || sequence >= 35
            || !sequences.insert(sequence)
            || !matches!(position, 0 | 1 | 2 | 4 | 8)
            || action.card_ids != [69_247_929]
            || action.choice
                != (Choice::Cards {
                    indices: vec![index as u32],
                })
            || action.bytes != bytes
        {
            return Err("opcode15 candidate position or response differs".into());
        }
    }
    Ok(())
}

/// Independent protocol validator for all six pending decision prefixes.
pub fn validate_tenki_placement_result(
    stage: u8,
    request: &RunDuelRequest,
    result: &DuelResult,
) -> Result<Value, String> {
    validate_tenki_placement_result_with_policy(stage, request, result, false)
}

/// Validate a result used by the validation scope, whose child requests inherit
/// authenticated automatic responses from their parent receipt.
pub fn validate_tenki_placement_validation_result(
    stage: u8,
    request: &RunDuelRequest,
    result: &DuelResult,
) -> Result<Value, String> {
    validate_tenki_placement_result_with_policy(stage, request, result, true)
}

fn validate_tenki_placement_result_with_policy(
    stage: u8,
    request: &RunDuelRequest,
    result: &DuelResult,
    allow_auto_prefix: bool,
) -> Result<Value, String> {
    tenki_placement_purpose(stage).map_err(|error| error.message)?;
    frozen_input(request).map_err(|error| error.message)?;
    if allow_auto_prefix {
        validate_validation_decision_prefix(stage, request).map_err(|error| error.message)?;
    } else {
        validate_decision_prefix(stage, request).map_err(|error| error.message)?;
    }
    if result.status != DuelStatus::DecisionRequired
        || result.error.is_some()
        || !result.coverage_gaps.is_empty()
        || result.resolved_decisions.len() < request.decisions.len()
        || result.resolved_decisions[..request.decisions.len()] != request.decisions
    {
        return Err("request decisions not fully consumed at a clean pending point".into());
    }
    let prompts = prompt_events(result)?;
    let pending = result.prompt.as_ref().ok_or("pending prompt missing")?;
    let (frame, parsed) = prompts
        .iter()
        .find(|(_, prompt)| prompt.id == pending.id)
        .ok_or("pending raw frame missing")?;
    if parsed != pending || pending.player != 0 || prompts.last().map(|(_, p)| p) != Some(pending) {
        return Err("pending prompt is not the final own prompt".into());
    }
    if allow_auto_prefix
        && (result
            .resolved_decisions
            .last()
            .is_some_and(|decision| decision.prompt_id >= pending.id)
            || result.events.last().map(|event| event.sequence) != Some(frame.sequence))
    {
        return Err("pending prompt is not after all resolved decisions and final event".into());
    }
    for (index, decision) in result.resolved_decisions.iter().enumerate() {
        if index > 0 && result.resolved_decisions[index - 1].prompt_id >= decision.prompt_id {
            return Err("resolved prompt order differs".into());
        }
        let (_, prompt) = prompts
            .iter()
            .find(|(_, prompt)| prompt.id == decision.prompt_id)
            .ok_or("resolved decision prompt missing")?;
        let encoded_choice = prompt.encode(&decision.choice);
        let matching_actions = encoded_choice.as_ref().map_or(0, |bytes| {
            prompt
                .actions
                .iter()
                .filter(|action| action.choice == decision.choice && action.bytes == *bytes)
                .count()
        });
        if decision.player != prompt.player
            || matching_actions != 1
            || (index >= request.decisions.len()
                && (prompt.actions.len() != 1 || prompt.actions[0].choice != decision.choice))
        {
            return Err("unapproved or invalid automatic decision".into());
        }
    }
    match stage {
        1 => validate_place_prompt(frame, pending)?,
        2 => validate_yes_no(frame, pending)?,
        3 | 4 if pending.opcode != 11 => {
            return Err("false branch must stop at next own idle".into())
        }
        5 | 6 => validate_targets(frame, pending)?,
        3 | 4 => {}
        _ => unreachable!(),
    }
    Ok(json!({
        "pending_opcode": pending.opcode,
        "raw_prompt_count": prompts.len(),
        "response_oracle_matches": true,
        "expected_target_matches": true,
        "automatic_decisions_single_legal": true,
        "stage": stage,
        "complete_action_coverage": false,
        "global_optimality": false
    }))
}

pub fn tenki_placement_replay_matches(a: &DuelResult, b: &DuelResult) -> bool {
    let mut left = encoded(a).ok();
    let mut right = encoded(b).ok();
    for value in [&mut left, &mut right].into_iter().flatten() {
        value["peak_working_set_bytes"] = Value::Null;
    }
    left == right
}

/// Validate the old success source and its old failing region-18 descendant.
/// The failed old stage is evidence of the prompt only; it is never an eligible parent.
pub fn validate_tenki_placement_genesis(
    old_stage1: &Value,
    old_stage2_request: &RunDuelRequest,
    old_stage2: &Value,
    new_request: &RunDuelRequest,
) -> Result<(), WorkerError> {
    if old_stage1["scope"] != OLD_SCOPE
        || old_stage1["stage"] != 1
        || old_stage1["successful"] != true
        || old_stage2["scope"] != OLD_SCOPE
        || old_stage2["stage"] != 2
        || old_stage2["successful"] != false
        || old_stage2["diagnostic"] != "unexpected_intermediate_prompt"
    {
        return Err(fail("historical stage roles or outcomes differ"));
    }
    let prior_request: RunDuelRequest = serde_json::from_value(old_stage1["request"].clone())
        .map_err(|_| fail("historical stage1 request malformed"))?;
    frozen_input(&prior_request)?;
    if !prior_request.decisions.is_empty() {
        return Err(fail("historical activation source request is not empty"));
    }
    let prior_result: Result<DuelResult, WorkerError> =
        serde_json::from_value(old_stage1["result"].clone())
            .map_err(|_| fail("historical stage1 result malformed"))?;
    let prior_result = prior_result.map_err(|_| fail("historical activation source failed"))?;
    if prior_result.status != DuelStatus::DecisionRequired
        || !prior_result.coverage_gaps.is_empty()
        || prior_result.error.is_some()
    {
        return Err(fail("historical activation result is not a clean prompt"));
    }
    let prompt = prior_result
        .prompt
        .as_ref()
        .ok_or_else(|| fail("historical idle missing"))?;
    let activation = unique_tenki_activation(prompt)?;
    let mut expected_old_stage2 = prior_request.clone();
    expected_old_stage2.decisions = prior_result.resolved_decisions.clone();
    expected_old_stage2.decisions.push(Decision {
        prompt_id: prompt.id,
        player: prompt.player,
        choice: activation.choice,
    });
    if encoded(&expected_old_stage2)? != encoded(old_stage2_request)?
        || old_stage2["request"] != encoded(old_stage2_request)?
    {
        return Err(fail(
            "historical stage2 is not derived from old public activation",
        ));
    }
    let old_stage2_result: Result<DuelResult, WorkerError> =
        serde_json::from_value(old_stage2["result"].clone())
            .map_err(|_| fail("historical stage2 result malformed"))?;
    let old_stage2_result = old_stage2_result.map_err(|_| fail("old stage2 has no raw result"))?;
    validate_tenki_placement_result(1, old_stage2_request, &old_stage2_result)
        .map_err(|_| fail("old stage2 region source is not the frozen prompt"))?;
    let mut expected_new = old_stage2_request.clone();
    expected_new.engine.worker_path = new_request.engine.worker_path.clone();
    if encoded(&expected_new)? != encoded(new_request)? {
        return Err(fail("new genesis request differs beyond worker path"));
    }
    Ok(())
}

fn verify_fixed_genesis(request: &RunDuelRequest, root: &Path) -> Result<(), WorkerError> {
    let baseline = root.join(BASELINE_ROOT);
    let stage1_path = baseline.join("stage-1.json");
    let stage2_request_path = baseline.join("stage-2-request.json");
    let stage2_path = baseline.join("stage-2.json");
    let stage1_raw =
        std::fs::read(stage1_path).map_err(|_| fail("old stage1 evidence unavailable"))?;
    let stage2_request_raw =
        std::fs::read(stage2_request_path).map_err(|_| fail("old stage2 request unavailable"))?;
    let stage2_raw =
        std::fs::read(stage2_path).map_err(|_| fail("old stage2 evidence unavailable"))?;
    if digest(&stage1_raw) != OLD_STAGE1_SHA256
        || digest(&stage2_request_raw) != OLD_STAGE2_REQUEST_SHA256
        || digest(&stage2_raw) != OLD_STAGE2_SHA256
    {
        return Err(fail("pinned historical evidence changed"));
    }
    let old_stage1: Value =
        serde_json::from_slice(&stage1_raw).map_err(|_| fail("old stage1 JSON invalid"))?;
    let old_stage2_request: RunDuelRequest = serde_json::from_slice(&stage2_request_raw)
        .map_err(|_| fail("old stage2 request invalid"))?;
    let old_stage2: Value =
        serde_json::from_slice(&stage2_raw).map_err(|_| fail("old stage2 JSON invalid"))?;
    validate_tenki_placement_genesis(&old_stage1, &old_stage2_request, &old_stage2, request)
}

/// Validate the frozen first-stage request without opening or creating its call journal.
pub fn validate_tenki_placement_stage1_request(
    request: &RunDuelRequest,
) -> Result<(), WorkerError> {
    let root = std::env::current_dir().map_err(|_| fail("current directory unavailable"))?;
    validate_tenki_placement_stage1_request_at(request, &root)
}

/// Validate the same frozen first-stage request against the fixed historical files under an
/// explicit repository root. The relative evidence paths and all pinned hashes remain fixed.
pub fn validate_tenki_placement_stage1_request_at(
    request: &RunDuelRequest,
    repository_root: &Path,
) -> Result<(), WorkerError> {
    frozen_input(request)?;
    validate_validation_worker_path(request, repository_root)?;
    validate_decision_prefix(1, request)?;
    verify_fixed_genesis(request, repository_root)
}

fn validation_path_key(path: &Path) -> String {
    let text = path.to_string_lossy().replace('\\', "/");
    #[cfg(windows)]
    {
        let normalized = if let Some(rest) = text.strip_prefix("//?/UNC/") {
            format!("//{rest}")
        } else {
            text.strip_prefix("//?/").unwrap_or(&text).to_owned()
        };
        normalized.to_ascii_lowercase()
    }
    #[cfg(not(windows))]
    {
        text
    }
}

fn validate_validation_worker_path(
    request: &RunDuelRequest,
    repository_root: &Path,
) -> Result<(), WorkerError> {
    let repository_root = repository_root
        .canonicalize()
        .map_err(|_| fail("validation repository root unavailable"))?;
    let expected = repository_root.join(TENKI_PLACEMENT_VALIDATION_WORKER_RELATIVE_PATH);
    let actual = &request.engine.worker_path;
    if !actual.is_absolute() || validation_path_key(actual) != validation_path_key(&expected) {
        return Err(fail(
            "validation worker path is not the fixed candidate artifact",
        ));
    }
    Ok(())
}

fn unique_tenki_activation(prompt: &Prompt) -> Result<Action, WorkerError> {
    if prompt.player != 0 || prompt.opcode != 11 {
        return Err(fail("historical Tenki activation is not an own idle"));
    }
    let actions = prompt
        .actions
        .iter()
        .filter(|action| {
            matches!(action.choice, Choice::Command { command: 5, .. })
                && action.card_ids == [57_103_969]
        })
        .collect::<Vec<_>>();
    if actions.len() != 1
        || actions[0].choice
            != (Choice::Command {
                command: 5,
                index: 0,
            })
        || actions[0].bytes != [5, 0, 0, 0]
    {
        return Err(fail(
            "historical Tenki activation is not unique or canonical",
        ));
    }
    Ok(actions[0].clone())
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    stage: u8,
    request: RunDuelRequest,
}

/// Durable journal wrapper with an independent stage graph and six-call ceiling.
pub struct TenkiPlacementBatch {
    journal: Arc<CallJournal>,
    context: String,
    started: u64,
    spec: BatchSpec,
    repository_root: Option<PathBuf>,
    gate: Mutex<()>,
}

impl TenkiPlacementBatch {
    pub fn open(path: &Path, context: &str, started: u64) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, PLACEMENT_SPEC)
    }

    pub fn open_confirmation(
        path: &Path,
        context: &str,
        started: u64,
    ) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, CONFIRMATION_SPEC)
    }

    pub fn open_validation(path: &Path, context: &str, started: u64) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, VALIDATION_SPEC)
    }

    /// Open the fixed validation scope while resolving its frozen historical evidence from an
    /// explicit repository root. This does not alter the fixed scope, paths, or hashes.
    pub fn open_validation_at(
        path: &Path,
        context: &str,
        started: u64,
        repository_root: &Path,
    ) -> Result<Self, WorkerError> {
        let repository_root = repository_root
            .canonicalize()
            .map_err(|_| fail("repository root unavailable"))?;
        if !repository_root.is_dir() {
            return Err(fail("repository root is not a directory"));
        }
        Self::open_with_spec_at(
            path,
            context,
            started,
            VALIDATION_SPEC,
            Some(repository_root),
        )
    }

    fn open_with_spec(
        path: &Path,
        context: &str,
        started: u64,
        spec: BatchSpec,
    ) -> Result<Self, WorkerError> {
        Self::open_with_spec_at(path, context, started, spec, None)
    }

    fn open_with_spec_at(
        path: &Path,
        context: &str,
        started: u64,
        spec: BatchSpec,
        repository_root: Option<PathBuf>,
    ) -> Result<Self, WorkerError> {
        if context.is_empty() || started > unix_now()? {
            return Err(fail("invalid context or start"));
        }
        let journal = CallJournal::open(path, spec.scope, context, 6)?;
        let key = format!("immutable/{}/start", spec.key_prefix);
        match journal.checkpoint(&key)? {
            Some(saved) if saved != json!(started) => return Err(fail("start time changed")),
            Some(_) => {}
            None => journal.save_checkpoint(&key, &json!(started))?,
        }
        Ok(Self {
            journal,
            context: context.to_owned(),
            started,
            spec,
            repository_root,
            gate: Mutex::new(()),
        })
    }

    pub fn stats(&self) -> Result<LedgerStats, WorkerError> {
        self.journal.stats()
    }

    pub fn verify(&self) -> Result<(), WorkerError> {
        self.journal.verify()
    }

    pub fn require_time(&self) -> Result<(), WorkerError> {
        let now = unix_now()?;
        if now < self.started || now.saturating_sub(self.started) >= 7_170 {
            Err(fail("window has less than thirty seconds remaining"))
        } else {
            Ok(())
        }
    }

    fn result_window_valid_at(&self, now: u64) -> bool {
        if self.spec.full_window_result {
            now >= self.started && now < self.started.saturating_add(7_200)
        } else {
            now >= self.started && now.saturating_sub(self.started) < 7_170
        }
    }

    fn evidence_key(&self, stage: u8) -> String {
        format!("immutable/{}/evidence/{stage}", self.spec.key_prefix)
    }

    fn intent_key(&self, stage: u8) -> String {
        format!("immutable/{}/intent/{stage}", self.spec.key_prefix)
    }

    fn assets_key(&self, stage: u8) -> String {
        format!("immutable/{}/assets/{stage}", self.spec.key_prefix)
    }

    pub fn evidence(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        tenki_placement_purpose(stage)?;
        self.journal
            .checkpoint(&self.evidence_key(stage))?
            .map(|value| {
                value
                    .get("receipt")
                    .cloned()
                    .ok_or_else(|| fail("evidence payload missing"))
            })
            .transpose()
    }

    pub fn save_assets_before(&self, stage: u8, identity: &Value) -> Result<(), WorkerError> {
        tenki_placement_purpose(stage)?;
        self.journal
            .save_checkpoint(&self.assets_key(stage), identity)
    }

    pub fn assets_before(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        tenki_placement_purpose(stage)?;
        self.journal.checkpoint(&self.assets_key(stage))
    }

    fn intent(&self, stage: u8) -> Result<Option<Intent>, WorkerError> {
        self.journal
            .checkpoint(&self.intent_key(stage))?
            .map(|value| {
                serde_json::from_value(value).map_err(|_| fail("invalid immutable intent"))
            })
            .transpose()
    }

    pub fn has_intent(&self, stage: u8) -> Result<bool, WorkerError> {
        tenki_placement_purpose(stage)?;
        Ok(self.intent(stage)?.is_some())
    }

    pub fn load_outcome(
        &self,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<Option<Option<Result<DuelResult, WorkerError>>>, WorkerError> {
        tenki_placement_purpose(stage)?;
        let Some(intent) = self.intent(stage)? else {
            return Ok(None);
        };
        if request_hash(&intent.request)? != request_hash(request)? {
            return Err(fail("immutable request changed"));
        }
        Ok(Some(self.journal.load_outcome(stage.into(), request)?))
    }

    pub fn validate_request(&self, stage: u8, request: &RunDuelRequest) -> Result<(), WorkerError> {
        tenki_placement_purpose(stage)?;
        if stage == 1 {
            return match self.repository_root.as_deref() {
                Some(root) if self.spec.allow_auto_decisions => {
                    validate_tenki_placement_stage1_request_at(request, root)
                }
                _ => validate_tenki_placement_stage1_request(request),
            };
        }
        frozen_input(request)?;
        if self.spec.allow_auto_decisions {
            validate_validation_decision_prefix(stage, request)?;
        } else {
            validate_decision_prefix(stage, request)?;
        }
        let parent_stage = match stage {
            2 => 1,
            3 | 5 => 2,
            4 => 3,
            6 => 5,
            _ => unreachable!(),
        };
        let parent = self
            .evidence(parent_stage)?
            .ok_or_else(|| fail("successful parent receipt missing"))?;
        self.verify_evidence(parent_stage, &parent)?;
        if parent["successful"] != true {
            return Err(fail("parent receipt did not pass"));
        }
        let expected = derive_request_from_receipt(stage, &parent)?;
        if encoded(&expected)? != encoded(request)? {
            return Err(fail("request is not exact public-parent derivation"));
        }
        Ok(())
    }

    pub fn verify_evidence(&self, stage: u8, receipt: &Value) -> Result<(), WorkerError> {
        if receipt["kind"] != self.spec.stage_kind
            || receipt["scope"] != self.spec.scope
            || receipt["stage"] != json!(stage)
            || receipt["context"] != self.context
            || receipt["started_at"] != json!(self.started)
        {
            return Err(fail("receipt scope binding differs"));
        }
        let request: RunDuelRequest = serde_json::from_value(receipt["request"].clone())
            .map_err(|_| fail("receipt request malformed"))?;
        self.validate_request(stage, &request)?;
        let outcome = self
            .load_outcome(stage, &request)?
            .flatten()
            .ok_or_else(|| fail("charged outcome is not complete"))?;
        if encoded(&outcome)? != receipt["result"] {
            return Err(fail("result differs from journaled outcome"));
        }
        let validation = outcome
            .as_ref()
            .map_err(|error| error.message.clone())
            .and_then(|result| {
                if self.spec.allow_auto_decisions {
                    validate_tenki_placement_validation_result(stage, &request, result)
                } else {
                    validate_tenki_placement_result(stage, &request, result)
                }
            });
        if encoded(&validation)? != receipt["validation"] {
            return Err(fail("validation differs from independent oracle"));
        }
        if self.assets_before(stage)?.as_ref() != Some(&receipt["assets_before"]) {
            return Err(fail("asset precheck differs"));
        }
        let checkpoint = self.evidence_key(stage);
        let checkpoint_stats = self
            .journal
            .checkpoint_budget(&checkpoint)?
            .ok_or_else(|| fail("evidence prefix checkpoint missing"))?;
        let checkpoint_consumed = self
            .journal
            .checkpoint_consumed(&checkpoint)?
            .ok_or_else(|| fail("evidence consumed prefix missing"))?;
        let checkpoint_sequence = self
            .journal
            .checkpoint_charged_sequence_id(&checkpoint)?
            .ok_or_else(|| fail("evidence charged sequence missing"))?;
        if checkpoint_stats
            != serde_json::from_value(receipt["ledger"].clone())
                .map_err(|_| fail("receipt ledger malformed"))?
            || checkpoint_consumed != stage as usize
            || receipt["charged_sequence_id"] != checkpoint_sequence
            || checkpoint_stats.consumed != checkpoint_stats.completed
            || checkpoint_stats.unknown != 0
            || checkpoint_stats.reserved != 0
            || checkpoint_stats.abandoned != 0
            || checkpoint_stats.limit != 6
        {
            return Err(fail("receipt is not bound to exact settled ledger prefix"));
        }
        let replay = self.replay_match(stage, &outcome)?;
        if receipt["independent_replay_matches"] != replay {
            return Err(fail("replay comparison differs"));
        }
        let assets_unchanged = receipt["assets_unchanged"] == true
            && receipt["assets_after"].is_object()
            && receipt["assets_before"] == receipt["assets_after"];
        let window_valid = receipt["window_valid_at_result"] == true;
        let expected_diagnostic = if outcome.is_err() {
            Some("engine_or_journal_error")
        } else if validation.is_err() {
            Some("unexpected_intermediate_prompt")
        } else if !assets_unchanged {
            Some("asset_identity_drift")
        } else if replay == Value::Bool(false) {
            Some("independent_replay_mismatch")
        } else if checkpoint_stats.unknown != 0
            || checkpoint_stats.reserved != 0
            || checkpoint_stats.abandoned != 0
            || checkpoint_stats.completed != checkpoint_stats.consumed
        {
            Some("unresolved_consumption")
        } else if !window_valid {
            Some("window_exhausted")
        } else {
            None
        };
        let expected_success = expected_diagnostic.is_none()
            && (matches!(stage, 1 | 2 | 3 | 5) || replay == Value::Bool(true));
        let expected_diagnostic_value = expected_diagnostic.map(Value::from).unwrap_or(Value::Null);
        if receipt["successful"] != Value::Bool(expected_success)
            || receipt["diagnostic"] != expected_diagnostic_value
            || (matches!(stage, 1 | 2 | 3 | 5) && replay != Value::Null)
            || (matches!(stage, 4 | 6) && replay != Value::Bool(expected_success))
        {
            return Err(fail(
                "receipt success or diagnostic does not match journaled evidence",
            ));
        }
        if receipt["proof_ready"] != false
            || receipt["complete_action_coverage"] != false
            || receipt["global_optimality"] != false
            || receipt["native_probability_verified"] != false
        {
            return Err(fail("qualification flags must remain false"));
        }
        self.journal.verify()
    }

    fn replay_match(
        &self,
        stage: u8,
        outcome: &Result<DuelResult, WorkerError>,
    ) -> Result<Value, WorkerError> {
        if !matches!(stage, 4 | 6) {
            return Ok(Value::Null);
        }
        let parent = self
            .evidence(stage - 1)?
            .ok_or_else(|| fail("replay parent missing"))?;
        let previous: Result<DuelResult, WorkerError> =
            serde_json::from_value(parent["result"].clone())
                .map_err(|_| fail("replay parent result malformed"))?;
        Ok(json!(match (&previous, outcome) {
            (Ok(left), Ok(right)) => tenki_placement_replay_matches(left, right),
            _ => false,
        }))
    }

    pub fn record_evidence(
        &self,
        stage: u8,
        request: &RunDuelRequest,
        outcome: &Result<DuelResult, WorkerError>,
        assets_before: &Value,
        assets_after: Option<&Value>,
    ) -> Result<Value, WorkerError> {
        if self.spec.allow_auto_decisions {
            self.validate_request(stage, request)?;
        }
        let journaled = self
            .load_outcome(stage, request)?
            .flatten()
            .ok_or_else(|| fail("cannot record an incomplete call"))?;
        if encoded(&journaled)? != encoded(outcome)? {
            return Err(fail("recorded outcome differs from call journal"));
        }
        let validation = outcome
            .as_ref()
            .map_err(|error| error.message.clone())
            .and_then(|result| {
                if self.spec.allow_auto_decisions {
                    validate_tenki_placement_validation_result(stage, request, result)
                } else {
                    validate_tenki_placement_result(stage, request, result)
                }
            });
        let stats = self.stats()?;
        let prefix = self.journal.charged_sequence_id()?;
        let assets_unchanged = assets_after == Some(assets_before);
        let replay = self.replay_match(stage, outcome)?;
        let result_at = unix_now().ok();
        let in_time = result_at.is_some_and(|now| self.result_window_valid_at(now));
        let successful = validation.is_ok()
            && assets_unchanged
            && replay != Value::Bool(false)
            && in_time
            && stats.consumed == stage as usize
            && stats.completed == stats.consumed
            && stats.unknown == 0
            && stats.reserved == 0
            && stats.abandoned == 0;
        let diagnostic = if outcome.is_err() {
            Some("engine_or_journal_error")
        } else if validation.is_err() {
            Some("unexpected_intermediate_prompt")
        } else if !assets_unchanged {
            Some("asset_identity_drift")
        } else if replay == Value::Bool(false) {
            Some("independent_replay_mismatch")
        } else if stats.unknown != 0
            || stats.reserved != 0
            || stats.abandoned != 0
            || stats.completed != stats.consumed
        {
            Some("unresolved_consumption")
        } else if !in_time {
            Some("window_exhausted")
        } else {
            None
        };
        let mut receipt = json!({
            "schema_version":1,"kind":self.spec.stage_kind,
            "scope":self.spec.scope,"context":self.context,"stage":stage,
            "request":request,"result":outcome,"validation":validation,
            "assets_before":assets_before,"assets_after":assets_after,
            "assets_unchanged":assets_unchanged,"independent_replay_matches":replay,
            "ledger":stats,"charged_sequence_id":prefix,"started_at":self.started,
            "window_valid_at_result":in_time,
            "successful":successful,"diagnostic":diagnostic,
            "proof_ready":false,"complete_action_coverage":false,
            "global_optimality":false,"native_probability_verified":false
        });
        if self.spec.full_window_result {
            receipt["result_at"] = json!(result_at);
        }
        let checkpoint = self.evidence_key(stage);
        self.journal
            .save_checkpoint(&checkpoint, &json!({"receipt":receipt}))?;
        self.verify_evidence(stage, &receipt)?;
        Ok(receipt)
    }

    /// Debit exactly one stage. Existing intent blocks retries, including unknown outcomes.
    pub fn run<A: EngineAdapter>(
        &self,
        adapter: A,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<DuelResult, WorkerError> {
        let _guard = self.gate.lock().map_err(|_| fail("poisoned stage gate"))?;
        self.validate_request(stage, request)?;
        self.require_time()?;
        let stats = self.stats()?;
        validate_placement_slot(stage, &stats)?;
        if self.intent(stage)?.is_some() {
            return Err(fail("stage intent already charged or unresolved"));
        }
        if stage > 1 {
            let previous = self
                .evidence(stage - 1)?
                .ok_or_else(|| fail("immediately previous stage missing"))?;
            self.verify_evidence(stage - 1, &previous)?;
            if previous["successful"] != true {
                return Err(fail("immediately previous stage failed"));
            }
        }
        if self.evidence(stage)?.is_some() {
            return Err(fail("stage receipt already exists"));
        }
        self.journal.save_checkpoint(
            &self.intent_key(stage),
            &encoded(&Intent {
                stage,
                request: request.clone(),
            })?,
        )?;
        JournaledAdapter::new(
            adapter,
            self.journal.clone(),
            tenki_placement_purpose(stage)?,
        )
        .run(request)
    }
}

/// Verify one published confirmation receipt against an immutable journal view.
/// This path is safe after expiry and cannot append or recover ledger records.
pub fn verify_tenki_placement_confirmation_recorded(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
) -> Result<(), WorkerError> {
    verify_tenki_placement_recorded_with_spec(
        journal,
        stage,
        context,
        started,
        receipt,
        CONFIRMATION_SPEC,
        None,
    )
}

/// Verify one validation-scope receipt against an immutable journal view.
/// This path is safe after expiry and cannot append or recover ledger records.
pub fn verify_tenki_placement_validation_recorded(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
) -> Result<(), WorkerError> {
    verify_tenki_placement_validation_recorded_inner(
        journal, stage, context, started, receipt, None,
    )
}

/// Verify one validation-scope receipt using fixed historical evidence under an explicit
/// repository root. The evidence paths and expected hashes remain unchanged.
pub fn verify_tenki_placement_validation_recorded_at(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
    repository_root: &Path,
) -> Result<(), WorkerError> {
    verify_tenki_placement_validation_recorded_inner(
        journal,
        stage,
        context,
        started,
        receipt,
        Some(repository_root),
    )
}

fn verify_tenki_placement_validation_recorded_inner(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
    repository_root: Option<&Path>,
) -> Result<(), WorkerError> {
    verify_tenki_placement_recorded_with_spec(
        journal,
        stage,
        context,
        started,
        receipt,
        VALIDATION_SPEC,
        repository_root,
    )
}

#[derive(Clone, Copy)]
struct RecordedCheck<'a> {
    journal: &'a ReadOnlyJournal,
    context: &'a str,
    started: u64,
    spec: BatchSpec,
    repository_root: Option<&'a Path>,
}

fn verify_tenki_placement_recorded_with_spec(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
    spec: BatchSpec,
    repository_root: Option<&Path>,
) -> Result<(), WorkerError> {
    let check = RecordedCheck {
        journal,
        context,
        started,
        spec,
        repository_root,
    };
    validate_recorded_parent_chain(&check, stage, receipt)?;

    fn verify_inner(
        check: &RecordedCheck<'_>,
        stage: u8,
        receipt: &Value,
        active: &mut BTreeSet<u8>,
    ) -> Result<(), WorkerError> {
        let journal = check.journal;
        let context = check.context;
        let started = check.started;
        let spec = check.spec;
        tenki_placement_purpose(stage)?;
        if !active.insert(stage) {
            return Err(fail("confirmation receipt dependency cycle"));
        }
        if receipt["kind"] != spec.stage_kind
            || receipt["scope"] != spec.scope
            || receipt["stage"] != json!(stage)
            || receipt["context"] != context
            || receipt["started_at"] != json!(started)
        {
            return Err(fail("confirmation receipt scope binding differs"));
        }
        let request: RunDuelRequest = serde_json::from_value(receipt["request"].clone())
            .map_err(|_| fail("confirmation receipt request malformed"))?;
        let intent_key = format!("immutable/{}/intent/{stage}", spec.key_prefix);
        if journal.checkpoint(&intent_key)? != Some(json!({"stage":stage,"request":request})) {
            return Err(fail("confirmation receipt intent is not journal-bound"));
        }
        if stage == 1 {
            if spec.allow_auto_decisions {
                match check.repository_root {
                    Some(root) => validate_tenki_placement_stage1_request_at(&request, root)?,
                    None => validate_tenki_placement_stage1_request(&request)?,
                }
            } else {
                validate_tenki_placement_stage1_request(&request)?;
            }
        } else {
            let parent_stage = match stage {
                2 => 1,
                3 | 5 => 2,
                4 => 3,
                6 => 5,
                _ => unreachable!(),
            };
            let parent_key = format!("immutable/{}/evidence/{parent_stage}", spec.key_prefix);
            let parent = journal
                .checkpoint(&parent_key)?
                .and_then(|value| value.get("receipt").cloned())
                .ok_or_else(|| fail("successful confirmation parent receipt missing"))?;
            verify_inner(check, parent_stage, &parent, active)?;
            if parent["successful"] != true {
                return Err(fail("confirmation parent receipt did not pass"));
            }
            let expected = derive_request_from_receipt(stage, &parent)?;
            if encoded(&expected)? != encoded(&request)? {
                return Err(fail("confirmation request is not exact parent derivation"));
            }
        }
        let evidence_key = format!("immutable/{}/evidence/{stage}", spec.key_prefix);
        if journal
            .checkpoint(&evidence_key)?
            .and_then(|value| value.get("receipt").cloned())
            .as_ref()
            != Some(receipt)
        {
            return Err(fail(
                "confirmation receipt differs from immutable journal checkpoint",
            ));
        }
        let outcome = journal
            .load_outcome(stage.into(), &request)?
            .ok_or_else(|| fail("confirmation outcome is incomplete"))?;
        if encoded(&outcome)? != receipt["result"] {
            return Err(fail("confirmation result differs from journal"));
        }
        let validation = outcome
            .as_ref()
            .map_err(|error| error.message.clone())
            .and_then(|result| {
                if spec.allow_auto_decisions {
                    validate_tenki_placement_validation_result(stage, &request, result)
                } else {
                    validate_tenki_placement_result(stage, &request, result)
                }
            });
        if encoded(&validation)? != receipt["validation"] {
            return Err(fail(
                "confirmation validation differs from independent oracle",
            ));
        }
        let assets_key = format!("immutable/{}/assets/{stage}", spec.key_prefix);
        if journal.checkpoint(&assets_key)?.as_ref() != Some(&receipt["assets_before"]) {
            return Err(fail("confirmation asset checkpoint differs"));
        }
        let checkpoint_stats = journal
            .checkpoint_budget(&evidence_key)?
            .ok_or_else(|| fail("confirmation prefix checkpoint missing"))?;
        if checkpoint_stats
            != serde_json::from_value(receipt["ledger"].clone())
                .map_err(|_| fail("confirmation receipt ledger malformed"))?
            || journal.checkpoint_consumed(&evidence_key)? != Some(stage as usize)
            || receipt["charged_sequence_id"]
                != journal
                    .checkpoint_charged_sequence_id(&evidence_key)?
                    .ok_or_else(|| fail("confirmation sequence checkpoint missing"))?
            || checkpoint_stats.limit != 6
            || checkpoint_stats.completed != checkpoint_stats.consumed
            || checkpoint_stats.unknown != 0
            || checkpoint_stats.reserved != 0
            || checkpoint_stats.abandoned != 0
        {
            return Err(fail(
                "confirmation receipt is not bound to its settled prefix",
            ));
        }
        let replay = if matches!(stage, 4 | 6) {
            let parent_stage = stage - 1;
            let parent_key = format!("immutable/{}/evidence/{parent_stage}", spec.key_prefix);
            let parent = journal
                .checkpoint(&parent_key)?
                .and_then(|value| value.get("receipt").cloned())
                .ok_or_else(|| fail("confirmation replay parent missing"))?;
            let previous: Result<DuelResult, WorkerError> =
                serde_json::from_value(parent["result"].clone())
                    .map_err(|_| fail("confirmation replay parent malformed"))?;
            Value::Bool(match (&previous, &outcome) {
                (Ok(left), Ok(right)) => tenki_placement_replay_matches(left, right),
                _ => false,
            })
        } else {
            Value::Null
        };
        if receipt["independent_replay_matches"] != replay {
            return Err(fail("confirmation replay comparison differs"));
        }
        let assets_unchanged = receipt["assets_unchanged"] == true
            && receipt["assets_after"].is_object()
            && receipt["assets_before"] == receipt["assets_after"];
        let in_time = if spec.full_window_result {
            let result_at = receipt["result_at"].as_u64();
            let within =
                result_at.is_some_and(|at| at >= started && at < started.saturating_add(7_200));
            receipt["window_valid_at_result"] == Value::Bool(within) && within
        } else {
            receipt["window_valid_at_result"] == true
        };
        let expected_diagnostic = if outcome.is_err() {
            Some("engine_or_journal_error")
        } else if validation.is_err() {
            Some("unexpected_intermediate_prompt")
        } else if !assets_unchanged {
            Some("asset_identity_drift")
        } else if replay == Value::Bool(false) {
            Some("independent_replay_mismatch")
        } else if checkpoint_stats.unknown != 0
            || checkpoint_stats.reserved != 0
            || checkpoint_stats.abandoned != 0
            || checkpoint_stats.completed != checkpoint_stats.consumed
        {
            Some("unresolved_consumption")
        } else if !in_time {
            Some("window_exhausted")
        } else {
            None
        };
        let expected_success = expected_diagnostic.is_none()
            && (matches!(stage, 1 | 2 | 3 | 5) || replay == Value::Bool(true));
        if receipt["successful"] != Value::Bool(expected_success)
            || receipt["diagnostic"] != expected_diagnostic.map(Value::from).unwrap_or(Value::Null)
            || receipt["proof_ready"] != false
            || receipt["complete_action_coverage"] != false
            || receipt["global_optimality"] != false
            || receipt["native_probability_verified"] != false
        {
            return Err(fail("confirmation receipt status is inconsistent"));
        }
        active.remove(&stage);
        Ok(())
    }

    let mut active = BTreeSet::new();
    verify_inner(&check, stage, receipt, &mut active)?;
    journal.verify()
}

/// Validate scope, intent, checkpoint, and exact parent-derived request bindings before checking
/// recorded outcomes. This keeps ancestry verification independently testable and read-only.
fn validate_recorded_parent_chain(
    check: &RecordedCheck<'_>,
    stage: u8,
    receipt: &Value,
) -> Result<(), WorkerError> {
    let mut validate_genesis = |check: &RecordedCheck<'_>, request: &RunDuelRequest| {
        if check.spec.allow_auto_decisions {
            match check.repository_root {
                Some(root) => validate_tenki_placement_stage1_request_at(request, root),
                None => validate_tenki_placement_stage1_request(request),
            }
        } else {
            validate_tenki_placement_stage1_request(request)
        }
    };
    validate_recorded_parent_chain_with(check, stage, receipt, &mut validate_genesis)
}

fn validate_recorded_parent_chain_with(
    check: &RecordedCheck<'_>,
    stage: u8,
    receipt: &Value,
    validate_genesis: &mut dyn FnMut(
        &RecordedCheck<'_>,
        &RunDuelRequest,
    ) -> Result<(), WorkerError>,
) -> Result<(), WorkerError> {
    fn visit(
        check: &RecordedCheck<'_>,
        stage: u8,
        receipt: &Value,
        active: &mut BTreeSet<u8>,
        validate_genesis: &mut dyn FnMut(
            &RecordedCheck<'_>,
            &RunDuelRequest,
        ) -> Result<(), WorkerError>,
    ) -> Result<(), WorkerError> {
        let journal = check.journal;
        let context = check.context;
        let started = check.started;
        let spec = check.spec;
        tenki_placement_purpose(stage)?;
        if !active.insert(stage) {
            return Err(fail("validation receipt dependency cycle"));
        }
        if receipt["kind"] != spec.stage_kind
            || receipt["scope"] != spec.scope
            || receipt["stage"] != json!(stage)
            || receipt["context"] != context
            || receipt["started_at"] != json!(started)
        {
            return Err(fail("validation receipt scope binding differs"));
        }
        let request: RunDuelRequest = serde_json::from_value(receipt["request"].clone())
            .map_err(|_| fail("validation receipt request malformed"))?;
        let intent_key = format!("immutable/{}/intent/{stage}", spec.key_prefix);
        if journal.checkpoint(&intent_key)? != Some(json!({"stage":stage,"request":request})) {
            return Err(fail("validation receipt intent is not journal-bound"));
        }
        if stage == 1 {
            validate_genesis(check, &request)?;
        } else {
            let parent_stage = match stage {
                2 => 1,
                3 | 5 => 2,
                4 => 3,
                6 => 5,
                _ => unreachable!(),
            };
            let parent_key = format!("immutable/{}/evidence/{parent_stage}", spec.key_prefix);
            let parent = journal
                .checkpoint(&parent_key)?
                .and_then(|value| value.get("receipt").cloned())
                .ok_or_else(|| fail("successful validation parent receipt missing"))?;
            visit(check, parent_stage, &parent, active, validate_genesis)?;
            if parent["successful"] != true {
                return Err(fail("validation parent receipt did not pass"));
            }
            let expected = derive_request_from_receipt(stage, &parent)?;
            if encoded(&expected)? != encoded(&request)? {
                return Err(fail("validation request is not exact parent derivation"));
            }
        }
        let evidence_key = format!("immutable/{}/evidence/{stage}", spec.key_prefix);
        if journal
            .checkpoint(&evidence_key)?
            .and_then(|value| value.get("receipt").cloned())
            .as_ref()
            != Some(receipt)
        {
            return Err(fail("validation receipt differs from journal checkpoint"));
        }
        active.remove(&stage);
        Ok(())
    }

    let mut active = BTreeSet::new();
    visit(check, stage, receipt, &mut active, validate_genesis)
}

fn derive_request_from_receipt(stage: u8, parent: &Value) -> Result<RunDuelRequest, WorkerError> {
    let mut request: RunDuelRequest = serde_json::from_value(parent["request"].clone())
        .map_err(|_| fail("parent request malformed"))?;
    if matches!(stage, 4 | 6) {
        return Ok(request);
    }
    let result: Result<DuelResult, WorkerError> = serde_json::from_value(parent["result"].clone())
        .map_err(|_| fail("parent result malformed"))?;
    let result = result.map_err(|_| fail("parent result failed"))?;
    let prompt = result
        .prompt
        .ok_or_else(|| fail("parent pending prompt missing"))?;
    let choice = match stage {
        2 => {
            if prompt.opcode != 18 || prompt.player != 0 {
                return Err(fail("parent is not frozen placement prompt"));
            }
            let matches = prompt
                .actions
                .iter()
                .filter(|action| {
                    action.choice
                        == (Choice::Place {
                            zones: vec![Zone {
                                player: 0,
                                location: 8,
                                sequence: 0,
                            }],
                        })
                        && action.bytes == [0, 8, 0]
                })
                .collect::<Vec<_>>();
            if matches.len() != 1 {
                return Err(fail("unique coordinate-based zone zero action missing"));
            }
            matches[0].choice.clone()
        }
        3 | 5 => {
            if prompt.opcode != 13 || prompt.player != 0 {
                return Err(fail("parent is not frozen opcode13 prompt"));
            }
            let yes = stage == 5;
            let bytes = if yes { [1, 0, 0, 0] } else { [0, 0, 0, 0] };
            let matches = prompt
                .actions
                .iter()
                .filter(|action| action.choice == (Choice::YesNo { yes }) && action.bytes == bytes)
                .collect::<Vec<_>>();
            if matches.len() != 1 {
                return Err(fail("unique fixed opcode13 response missing"));
            }
            matches[0].choice.clone()
        }
        _ => return Err(fail("unsupported stage derivation")),
    };
    prompt
        .encode(&choice)
        .map_err(|_| fail("parent menu does not permit fixed response"))?;
    request.decisions = result.resolved_decisions;
    request.decisions.push(Decision {
        prompt_id: prompt.id,
        player: prompt.player,
        choice,
    });
    Ok(request)
}

#[cfg(test)]
mod fixed_hash_tests {
    use super::*;

    fn test_repository_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap()
    }

    fn synthetic_test_root(label: &str) -> PathBuf {
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        test_repository_root()
            .join("target/curry-option-validation-tests/tmp")
            .join(format!("{label}-{nonce}"))
    }

    fn synthetic_frozen_tenki_request(repository_root: &Path) -> RunDuelRequest {
        use ygo_domain::{CardId, Deck};

        let main = [
            57_103_969, 69_247_929, 69_247_929, 2_964_201, 2_964_201, 2_964_201, 2_971_090,
            2_971_090, 2_971_090, 3_797_883, 3_797_883, 3_797_883, 4_035_199, 4_035_199, 4_035_199,
            4_179_849, 4_179_849, 4_179_849, 4_392_470, 4_392_470, 4_392_470, 6_368_038, 6_368_038,
            6_368_038, 6_631_034, 6_631_034, 6_631_034, 6_740_720, 6_740_720, 6_740_720, 7_562_372,
            7_562_372, 7_562_372, 8_353_769, 8_353_769, 8_353_769, 9_540_040, 9_540_040, 9_540_040,
            10_538_007,
        ]
        .into_iter()
        .map(CardId)
        .collect();
        let request = RunDuelRequest {
            protocol_version: 2,
            engine: ProcessEngineConfig {
                worker_path: repository_root.join(TENKI_PLACEMENT_VALIDATION_WORKER_RELATIVE_PATH),
                ..ProcessEngineConfig::default()
            },
            deck: Deck {
                main,
                extra: [84_013_237, 71_594_310, 77_637_979]
                    .into_iter()
                    .map(CardId)
                    .collect(),
                side: Vec::new(),
            },
            opening_hand: [57_103_969, 2_964_201, 2_964_201, 2_964_201, 2_971_090]
                .into_iter()
                .map(CardId)
                .collect(),
            seed: 1,
            decisions: vec![Decision {
                prompt_id: 7,
                player: 0,
                choice: Choice::Command {
                    command: 5,
                    index: 0,
                },
            }],
            versions: RuntimeVersions {
                rules: "ocg-mr5".into(),
                catalog: String::new(),
                banlist: String::new(),
                engine_sha256: "446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9"
                    .into(),
                cdb_sha256: "c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225"
                    .into(),
                scripts_sha256: "69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91"
                    .into(),
                core_commit: "38d04c9feb1a26617407091380634c87262fe3f8".into(),
                initializer: "fixed-hand-shuffle-v1".into(),
            },
            probe_only: false,
            scenario: None,
            interruption: None,
            first_turn: None,
            research_capture: None,
        };
        frozen_input(&request).expect("synthetic request must match frozen deck/version contract");
        validate_decision_prefix(1, &request).expect("synthetic activation prefix is valid");
        request
    }

    #[test]
    fn all_pinned_hashes_are_lowercase_sha256_and_stage1_matches_the_history_digest() {
        for value in [
            OLD_STAGE1_SHA256,
            OLD_STAGE2_REQUEST_SHA256,
            OLD_STAGE2_SHA256,
            DECK_HASH,
            VERSIONS_HASH,
        ] {
            assert!(is_sha256_hex(value), "invalid pinned hash: {value}");
        }
        assert_eq!(
            OLD_STAGE1_SHA256,
            "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76"
        );
        assert!(!is_sha256_hex("A".repeat(64).as_str()));
        assert!(!is_sha256_hex("a".repeat(63).as_str()));
        assert!(!is_sha256_hex("g".repeat(64).as_str()));
    }

    #[test]
    fn validation_worker_path_rejects_worker_outside_the_fixed_candidate_path() {
        let repository_root = test_repository_root();
        let mut request = synthetic_frozen_tenki_request(&repository_root);
        assert!(validate_validation_worker_path(&request, &repository_root).is_ok());

        request.engine.worker_path = repository_root.join("target/debug/ygo-engine-worker.exe");

        let error = validate_validation_worker_path(&request, &repository_root)
            .expect_err("validation must reject a caller-selected worker path");
        assert_eq!(
            error.message,
            "validation worker path is not the fixed candidate artifact"
        );
    }

    #[test]
    fn validation_open_pins_a_canonical_repository_root() {
        let evidence_root = synthetic_test_root("canonical-root");
        std::fs::create_dir_all(&evidence_root).unwrap();
        let started = unix_now().unwrap();
        let repository_root = test_repository_root();
        let batch = TenkiPlacementBatch::open_validation_at(
            &evidence_root.join("calls.jsonl"),
            "canonical-root-context",
            started,
            &repository_root,
        )
        .unwrap();
        assert_eq!(
            batch.repository_root.as_deref(),
            Some(repository_root.as_path())
        );
        drop(batch);
        std::fs::remove_dir_all(evidence_root).unwrap();
    }

    fn chain_pending_result(request: &RunDuelRequest, prompt_id: u64, raw: &[u8]) -> DuelResult {
        let prompt = parse_prompt(prompt_id, raw).unwrap().unwrap();
        let mut result = DuelResult::failure(WorkerError::new(
            "synthetic",
            "receipt_chain",
            "not an engine result",
        ));
        result.status = DuelStatus::DecisionRequired;
        result.error = None;
        result.resolved_decisions = request.decisions.clone();
        result.prompt = Some(prompt);
        result
    }

    fn chain_receipt(
        stage: u8,
        context: &str,
        started: u64,
        request: &RunDuelRequest,
        result: Option<DuelResult>,
    ) -> Value {
        let result = result.map_or(Value::Null, |result| {
            serde_json::to_value(Ok::<DuelResult, WorkerError>(result)).unwrap()
        });
        json!({
            "kind": VALIDATION_SPEC.stage_kind,
            "scope": TENKI_PLACEMENT_VALIDATION_SCOPE,
            "stage": stage,
            "context": context,
            "started_at": started,
            "request": request,
            "result": result,
            "successful": true
        })
    }

    fn synthetic_stage6_chain(
        ledger_path: &Path,
        context: &str,
        started: u64,
        tamper_stage1_prompt: bool,
    ) -> Vec<Value> {
        let repository_root = test_repository_root();
        let stage1_request = synthetic_frozen_tenki_request(&repository_root);
        let stage1_result =
            chain_pending_result(&stage1_request, 9, &[18, 0, 1, 255, 224, 255, 255]);
        let stage1_receipt =
            chain_receipt(1, context, started, &stage1_request, Some(stage1_result));

        let stage2_request = derive_request_from_receipt(2, &stage1_receipt).unwrap();
        let mut yes_no_raw = vec![13, 0];
        yes_no_raw.extend(YES_NO_DESCRIPTION.to_le_bytes());
        let stage2_result = chain_pending_result(&stage2_request, 12, &yes_no_raw);
        let stage2_receipt =
            chain_receipt(2, context, started, &stage2_request, Some(stage2_result));

        let stage3_request = derive_request_from_receipt(3, &stage2_receipt).unwrap();
        let stage3_receipt = chain_receipt(3, context, started, &stage3_request, None);
        let stage4_request = derive_request_from_receipt(4, &stage3_receipt).unwrap();
        let stage4_receipt = chain_receipt(4, context, started, &stage4_request, None);
        let stage5_request = derive_request_from_receipt(5, &stage2_receipt).unwrap();
        let stage5_receipt = chain_receipt(5, context, started, &stage5_request, None);
        let stage6_request = derive_request_from_receipt(6, &stage5_receipt).unwrap();
        let stage6_receipt = chain_receipt(6, context, started, &stage6_request, None);
        let mut receipts = vec![
            stage1_receipt,
            stage2_receipt,
            stage3_receipt,
            stage4_receipt,
            stage5_receipt,
            stage6_receipt,
        ];
        if tamper_stage1_prompt {
            receipts[0]["result"]["Ok"]["prompt"]["id"] = json!(10);
        }

        let journal =
            CallJournal::open(ledger_path, TENKI_PLACEMENT_VALIDATION_SCOPE, context, 6).unwrap();
        for (index, receipt) in receipts.iter().enumerate() {
            let stage = index as u8 + 1;
            journal
                .save_checkpoint(
                    &format!("immutable/tenki-placement-validation/intent/{stage}"),
                    &json!({"stage":stage,"request":receipt["request"]}),
                )
                .unwrap();
            journal
                .save_checkpoint(
                    &format!("immutable/tenki-placement-validation/evidence/{stage}"),
                    &json!({"receipt":receipt}),
                )
                .unwrap();
        }
        drop(journal);
        receipts
    }

    #[test]
    fn read_only_stage6_parent_chain_accepts_and_rejects_tampered_ancestor() {
        let root = synthetic_test_root("ancestry");
        std::fs::create_dir_all(&root).unwrap();
        let started = unix_now().unwrap();
        let context = "synthetic-stage6-ancestry";

        let valid_path = root.join("valid.jsonl");
        let valid_receipts = synthetic_stage6_chain(&valid_path, context, started, false);
        let valid_view = CallJournal::inspect_existing(
            &valid_path,
            TENKI_PLACEMENT_VALIDATION_SCOPE,
            context,
            6,
        )
        .unwrap()
        .unwrap();
        let repository_root = test_repository_root();
        let valid_check = RecordedCheck {
            journal: &valid_view,
            context,
            started,
            spec: VALIDATION_SPEC,
            repository_root: Some(&repository_root),
        };
        let mut validate_synthetic_genesis =
            |check: &RecordedCheck<'_>, request: &RunDuelRequest| {
                frozen_input(request)?;
                let root = check
                    .repository_root
                    .ok_or_else(|| fail("synthetic repository root missing"))?;
                validate_validation_worker_path(request, root)?;
                validate_validation_decision_prefix(1, request)
            };
        validate_recorded_parent_chain_with(
            &valid_check,
            6,
            &valid_receipts[5],
            &mut validate_synthetic_genesis,
        )
        .expect("synthetic stage 1->2->5->6 request ancestry should be valid");
        drop(valid_view);

        let tampered_path = root.join("tampered.jsonl");
        let tampered_receipts = synthetic_stage6_chain(&tampered_path, context, started, true);
        let tampered_view = CallJournal::inspect_existing(
            &tampered_path,
            TENKI_PLACEMENT_VALIDATION_SCOPE,
            context,
            6,
        )
        .unwrap()
        .unwrap();
        let tampered_check = RecordedCheck {
            journal: &tampered_view,
            context,
            started,
            spec: VALIDATION_SPEC,
            repository_root: Some(&repository_root),
        };
        let tampered_error = validate_recorded_parent_chain_with(
            &tampered_check,
            6,
            &tampered_receipts[5],
            &mut validate_synthetic_genesis,
        )
        .expect_err("tampering with the ancestor prompt must invalidate descendants");
        assert_eq!(
            tampered_error.message,
            "validation request is not exact parent derivation"
        );
        drop(tampered_view);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn confirmation_window_checks_new_calls_and_result_deadline_separately() {
        let root = synthetic_test_root("confirmation-window");
        std::fs::create_dir_all(&root).unwrap();
        let now = unix_now().unwrap();
        let started = now.saturating_sub(1);
        let batch = TenkiPlacementBatch::open_confirmation(
            &root.join("calls.jsonl"),
            "confirmation-window-context",
            started,
        )
        .unwrap();

        assert!(batch.require_time().is_ok());
        assert!(batch.result_window_valid_at(started + 7_199));
        assert!(!batch.result_window_valid_at(started + 7_200));
        assert!(!batch.result_window_valid_at(started.saturating_sub(1)));

        let expired = TenkiPlacementBatch::open_confirmation(
            &root.join("expired.jsonl"),
            "expired-confirmation-window-context",
            now.saturating_sub(7_200),
        )
        .unwrap();
        assert!(expired.require_time().is_err());
        drop(expired);
        drop(batch);
        std::fs::remove_dir_all(root).unwrap();
    }
}
