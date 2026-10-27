use serde_json::{json, Value};
use ygo_engine_adapter::*;

fn folder() -> std::path::PathBuf {
    let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("target/curry-option-validation-tests/tmp")
        .join(format!(
            "placement-confirmation-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    std::fs::create_dir_all(&path).unwrap();
    path
}

fn request() -> RunDuelRequest {
    let fixture: Value =
        serde_json::from_str(include_str!("../../../tests/fixtures/rabbit.request.json")).unwrap();
    let mut request: RunDuelRequest = serde_json::from_value(json!({
        "protocol_version":2,"engine":{"timeout_ms":30000},
        "deck":fixture["deck"],"opening_hand":fixture["opening_hand"],"seed":1,
        "decisions":[],"versions":RuntimeVersions::default()
    }))
    .unwrap();
    request.deck.main[0] = ygo_domain::CardId(57_103_969);
    request.opening_hand[0] = ygo_domain::CardId(57_103_969);
    request.versions = serde_json::from_value(json!({
        "rules":"ocg-mr5","catalog":"","banlist":"",
        "core_commit":"38d04c9feb1a26617407091380634c87262fe3f8",
        "initializer":"fixed-hand-shuffle-v1",
        "engine_sha256":"446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9",
        "cdb_sha256":"c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225",
        "scripts_sha256":"69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91"
    }))
    .unwrap();
    request.decisions.push(Decision {
        prompt_id: 7,
        player: 0,
        choice: Choice::Command {
            command: 5,
            index: 0,
        },
    });
    request
}

fn result(raw: Vec<u8>) -> DuelResult {
    let prompt = parse_prompt(9, &raw).unwrap().unwrap();
    let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
    result.status = DuelStatus::DecisionRequired;
    result.error = None;
    result.prompt = Some(prompt.clone());
    let prior = idle_with_tenki();
    let prior_prompt = parse_prompt(7, &prior).unwrap().unwrap();
    result.resolved_decisions = vec![request().decisions[0].clone()];
    result.events = vec![
        CoreEventFrame {
            sequence: 7,
            opcode: 11,
            raw: prior,
            supported: true,
            fields: json!({"prompt":prior_prompt}),
        },
        CoreEventFrame {
            sequence: 9,
            opcode: raw[0],
            raw,
            supported: true,
            fields: json!({"prompt":prompt}),
        },
    ];
    result
}

fn with_auto_option(mut result: DuelResult, option_count: u8) -> DuelResult {
    let mut raw = vec![14, 0, option_count];
    for index in 0..option_count {
        raw.extend((100 + u64::from(index)).to_le_bytes());
    }
    let prompt = parse_prompt(8, &raw).unwrap().unwrap();
    result.resolved_decisions.push(Decision {
        prompt_id: 8,
        player: 0,
        choice: Choice::Option { index: 0 },
    });
    result.events.insert(
        1,
        CoreEventFrame {
            sequence: 8,
            opcode: 14,
            raw,
            supported: true,
            fields: serde_json::json!({"prompt":prompt}),
        },
    );
    result
}

fn prompt_frame(sequence: u64, raw: Vec<u8>) -> CoreEventFrame {
    let prompt = parse_prompt(sequence, &raw).unwrap().unwrap();
    CoreEventFrame {
        sequence,
        opcode: raw[0],
        raw,
        supported: true,
        fields: serde_json::json!({"prompt":prompt}),
    }
}

fn validation_stage_five_request() -> RunDuelRequest {
    let mut request = request();
    request.decisions.extend([
        Decision {
            prompt_id: 8,
            player: 0,
            choice: Choice::Option { index: 0 },
        },
        Decision {
            prompt_id: 9,
            player: 0,
            choice: Choice::Place {
                zones: vec![Zone {
                    player: 0,
                    location: 8,
                    sequence: 0,
                }],
            },
        },
        Decision {
            prompt_id: 10,
            player: 0,
            choice: Choice::YesNo { yes: true },
        },
    ]);
    request
}

fn validation_stage_three_request() -> RunDuelRequest {
    let mut request = request();
    request.decisions.extend([
        Decision {
            prompt_id: 8,
            player: 0,
            choice: Choice::Place {
                zones: vec![Zone {
                    player: 0,
                    location: 8,
                    sequence: 0,
                }],
            },
        },
        Decision {
            prompt_id: 9,
            player: 0,
            choice: Choice::YesNo { yes: false },
        },
    ]);
    request
}

fn validation_stage_three_result(request: &RunDuelRequest, resolve_pending: bool) -> DuelResult {
    let mut yes_no = vec![13, 0];
    yes_no.extend(59_877_851_398_144u64.to_le_bytes());
    let mut idle = vec![11, 0];
    for _ in 0..6 {
        idle.extend(0u32.to_le_bytes());
    }
    idle.extend([0, 1, 0]);
    let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
    result.status = DuelStatus::DecisionRequired;
    result.error = None;
    result.resolved_decisions = request.decisions.clone();
    if resolve_pending {
        result.resolved_decisions.push(Decision {
            prompt_id: 10,
            player: 0,
            choice: Choice::Command {
                command: 7,
                index: 0,
            },
        });
    }
    result.prompt = Some(parse_prompt(10, &idle).unwrap().unwrap());
    result.events = vec![
        prompt_frame(7, idle_with_tenki()),
        prompt_frame(8, vec![18, 0, 1, 255, 224, 255, 255]),
        prompt_frame(9, yes_no),
        prompt_frame(10, idle),
    ];
    result
}

fn validation_target_result(request: &RunDuelRequest, option_count: u8) -> DuelResult {
    let mut option = vec![14, 0, option_count];
    for index in 0..option_count {
        option.extend((100 + u64::from(index)).to_le_bytes());
    }
    let mut yes_no = vec![13, 0];
    yes_no.extend(59_877_851_398_144u64.to_le_bytes());
    let mut targets = vec![15, 0, 0];
    targets.extend(1u32.to_le_bytes());
    targets.extend(1u32.to_le_bytes());
    targets.extend(2u32.to_le_bytes());
    for (sequence, position) in [(3u32, 0u32), (7u32, 1u32)] {
        targets.extend(69_247_929u32.to_le_bytes());
        targets.extend([0, 1]);
        targets.extend(sequence.to_le_bytes());
        targets.extend(position.to_le_bytes());
    }
    let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
    result.status = DuelStatus::DecisionRequired;
    result.error = None;
    result.resolved_decisions = request.decisions.clone();
    result.prompt = Some(parse_prompt(11, &targets).unwrap().unwrap());
    result.events = vec![
        prompt_frame(7, idle_with_tenki()),
        prompt_frame(8, option),
        prompt_frame(9, vec![18, 0, 1, 255, 224, 255, 255]),
        prompt_frame(10, yes_no),
        prompt_frame(11, targets),
    ];
    result
}

fn with_ambiguous_automatic_tail(mut result: DuelResult, request: &RunDuelRequest) -> DuelResult {
    let targets = result.events.pop().unwrap().raw;
    let mut options = vec![14, 0, 2];
    options.extend(100u64.to_le_bytes());
    options.extend(101u64.to_le_bytes());
    result.resolved_decisions.push(Decision {
        prompt_id: 11,
        player: 0,
        choice: Choice::Option { index: 0 },
    });
    result.events.push(prompt_frame(11, options));
    result.events.push(prompt_frame(12, targets.clone()));
    result.prompt = Some(parse_prompt(12, &targets).unwrap().unwrap());
    assert_eq!(
        result.resolved_decisions[..request.decisions.len()],
        request.decisions
    );
    result
}

fn idle_with_tenki() -> Vec<u8> {
    let mut raw = vec![11, 0];
    for command in 0..6 {
        if command == 5 {
            raw.extend(1u32.to_le_bytes());
            raw.extend(57_103_969u32.to_le_bytes());
            raw.extend([0, 2]);
            raw.extend(0u32.to_le_bytes());
            raw.extend(0u64.to_le_bytes());
            raw.push(0);
        } else {
            raw.extend(0u32.to_le_bytes());
        }
    }
    raw.extend([0, 1, 0]);
    raw
}

#[test]
fn placement_scope_has_fixed_six_purpose_slots() {
    assert_eq!(tenki_placement_purpose(1).unwrap(), CallPurpose::Probe);
    assert_eq!(tenki_placement_purpose(2).unwrap(), CallPurpose::Probe);
    assert_eq!(tenki_placement_purpose(3).unwrap(), CallPurpose::Execution);
    assert_eq!(tenki_placement_purpose(4).unwrap(), CallPurpose::Replay);
    assert_eq!(tenki_placement_purpose(5).unwrap(), CallPurpose::Execution);
    assert_eq!(tenki_placement_purpose(6).unwrap(), CallPurpose::Replay);
    assert!(tenki_placement_purpose(0).is_err());
    assert!(tenki_placement_purpose(7).is_err());
}

#[test]
fn confirmation_scope_has_a_separate_fixed_root_and_ledger_context() {
    let dir = folder();
    let old_path = dir.join("old.jsonl");
    let new_path = dir.join("new.jsonl");
    let old = TenkiPlacementBatch::open(&old_path, "same-context", 1).unwrap();
    let new = TenkiPlacementBatch::open_confirmation(&new_path, "same-context", 1).unwrap();

    assert_eq!(old.stats().unwrap().limit, 6);
    assert_eq!(new.stats().unwrap().limit, 6);
    assert_ne!(TENKI_PLACEMENT_SCOPE, TENKI_PLACEMENT_CONFIRMATION_SCOPE);
    assert_eq!(
        tenki_placement_confirmation_research_root().unwrap(),
        std::env::current_dir()
            .unwrap()
            .join("data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/research")
    );
    drop(old);
    drop(new);

    assert!(TenkiPlacementBatch::open_confirmation(&old_path, "same-context", 1).is_err());
    assert!(TenkiPlacementBatch::open(&new_path, "same-context", 1).is_err());
}

#[test]
fn confirmation_recorded_verifier_rejects_a_legacy_scope_view() {
    let dir = folder();
    let path = dir.join("legacy.jsonl");
    drop(CallJournal::open(&path, "legacy", "same-context", 6).unwrap());
    let view = CallJournal::inspect_existing(&path, "legacy", "same-context", 6)
        .unwrap()
        .unwrap();
    assert!(
        verify_tenki_placement_confirmation_recorded(&view, 1, "same-context", 1, &json!({}),)
            .is_err()
    );
}

#[test]
fn validation_recorded_verifier_rejects_confirmation_scope_view() {
    let dir = folder();
    let path = dir.join("confirmation.jsonl");
    drop(CallJournal::open(&path, TENKI_PLACEMENT_CONFIRMATION_SCOPE, "same-context", 6).unwrap());
    let view =
        CallJournal::inspect_existing(&path, TENKI_PLACEMENT_CONFIRMATION_SCOPE, "same-context", 6)
            .unwrap()
            .unwrap();
    assert!(
        verify_tenki_placement_validation_recorded(&view, 1, "same-context", 1, &json!({}),)
            .is_err()
    );
}

#[test]
fn placement_slot_rejects_skips_unknown_debits_and_seventh_call() {
    let clean = LedgerStats {
        consumed: 0,
        reserved: 0,
        completed: 0,
        unknown: 0,
        abandoned: 0,
        limit: 6,
    };
    assert!(validate_placement_slot(1, &clean).is_ok());
    let skipped = LedgerStats {
        consumed: 1,
        reserved: 0,
        completed: 1,
        unknown: 0,
        abandoned: 0,
        limit: 6,
    };
    assert!(validate_placement_slot(1, &skipped).is_err());
    let unknown = LedgerStats {
        consumed: 1,
        reserved: 0,
        completed: 0,
        unknown: 1,
        abandoned: 0,
        limit: 6,
    };
    assert!(validate_placement_slot(2, &unknown).is_err());
    assert!(validate_placement_slot(7, &clean).is_err());
}

#[test]
fn raw_opcode18_requires_exact_mask_and_all_five_hand_written_responses() {
    let raw = [18, 0, 1, 255, 224, 255, 255].to_vec();
    assert!(validate_tenki_placement_result(1, &request(), &result(raw.clone())).is_ok());
    let mut bad_mask = raw.clone();
    bad_mask[3] ^= 1;
    assert!(validate_tenki_placement_result(1, &request(), &result(bad_mask)).is_err());
    let mut bad_player = raw.clone();
    bad_player[1] = 1;
    assert!(validate_tenki_placement_result(1, &request(), &result(bad_player)).is_err());
    let mut bad_count = raw;
    bad_count[2] = 2;
    assert!(validate_tenki_placement_result(1, &request(), &result(bad_count)).is_err());
}

#[test]
fn validation_scope_accepts_only_raw_bound_single_action_auto_responses() {
    let request = request();
    let valid = with_auto_option(result(vec![18, 0, 1, 255, 224, 255, 255]), 1);
    assert!(validate_tenki_placement_validation_result(1, &request, &valid).is_ok());

    let ambiguous = with_auto_option(result(vec![18, 0, 1, 255, 224, 255, 255]), 2);
    assert!(validate_tenki_placement_validation_result(1, &request, &ambiguous).is_err());
    assert!(validate_tenki_placement_result(1, &request, &ambiguous).is_err());

    let mut wrong_choice = valid;
    wrong_choice.resolved_decisions[1].choice = Choice::Option { index: 1 };
    assert!(validate_tenki_placement_validation_result(1, &request, &wrong_choice).is_err());
}

#[test]
fn validation_scope_rejects_a_resolved_decision_that_is_still_pending() {
    let request = validation_stage_three_request();
    let contradictory = validation_stage_three_result(&request, true);
    assert!(validate_tenki_placement_validation_result(3, &request, &contradictory).is_err());
}

#[test]
fn validation_scope_rejects_supported_events_after_the_pending_frame() {
    let mut result = result(vec![18, 0, 1, 255, 224, 255, 255]);
    result.events.push(CoreEventFrame {
        sequence: 10,
        opcode: 1,
        raw: vec![1],
        supported: true,
        fields: serde_json::json!({}),
    });
    assert!(validate_tenki_placement_validation_result(1, &request(), &result).is_err());
}

#[test]
fn validation_scope_accepts_stage_five_and_six_with_inherited_auto_decision() {
    let request = validation_stage_five_request();
    let result = validation_target_result(&request, 1);
    assert!(validate_tenki_placement_validation_result(5, &request, &result).is_ok());
    assert!(validate_tenki_placement_validation_result(6, &request, &result).is_ok());
    assert!(validate_tenki_placement_result(5, &request, &result).is_err());

    let ambiguous = with_ambiguous_automatic_tail(result.clone(), &request);
    assert!(validate_tenki_placement_validation_result(5, &request, &ambiguous).is_err());
}

#[test]
fn validation_scope_has_an_independent_fixed_root_and_ledger() {
    let dir = folder();
    let confirmation_path = dir.join("confirmation.jsonl");
    let validation_path = dir.join("validation.jsonl");
    let confirmation =
        TenkiPlacementBatch::open_confirmation(&confirmation_path, "same", 1).unwrap();
    let validation = TenkiPlacementBatch::open_validation(&validation_path, "same", 1).unwrap();
    assert_ne!(
        TENKI_PLACEMENT_CONFIRMATION_SCOPE,
        TENKI_PLACEMENT_VALIDATION_SCOPE
    );
    assert_eq!(confirmation.stats().unwrap().limit, 6);
    assert_eq!(validation.stats().unwrap().limit, 6);
    drop(confirmation);
    drop(validation);
    assert!(TenkiPlacementBatch::open_confirmation(&validation_path, "same", 1).is_err());
    assert!(TenkiPlacementBatch::open_validation(&confirmation_path, "same", 1).is_err());
}
