use serde_json::json;
use std::{
    fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::{SystemTime, UNIX_EPOCH},
};
use ygo_domain::{CardId, Deck};
use ygo_engine_adapter::*;

fn synthetic_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("target/curry-option-validation-tests/tmp")
}

fn unique_path(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    synthetic_root().join(format!("{label}-{nonce}.jsonl"))
}

fn snapshot_tree(root: &std::path::Path) -> Vec<(PathBuf, Vec<u8>)> {
    fn visit(root: &std::path::Path, current: &std::path::Path, out: &mut Vec<(PathBuf, Vec<u8>)>) {
        for entry in fs::read_dir(current).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                visit(root, &path, out);
            } else {
                out.push((
                    path.strip_prefix(root).unwrap().to_owned(),
                    fs::read(path).unwrap(),
                ));
            }
        }
    }
    let mut files = Vec::new();
    visit(root, root, &mut files);
    files.sort_by(|left, right| left.0.cmp(&right.0));
    files
}

fn request() -> RunDuelRequest {
    let main = [
        58_074_572, 69_247_929, 69_247_929, 2_964_201, 2_964_201, 2_964_201, 2_971_090, 2_971_090,
        2_971_090, 3_797_883, 3_797_883, 3_797_883, 4_035_199, 4_035_199, 4_035_199, 4_179_849,
        4_179_849, 4_179_849, 4_392_470, 4_392_470, 4_392_470, 6_368_038, 6_368_038, 6_368_038,
        6_631_034, 6_631_034, 6_631_034, 6_740_720, 6_740_720, 6_740_720, 7_562_372, 7_562_372,
        7_562_372, 8_353_769, 8_353_769, 8_353_769, 9_540_040, 9_540_040, 9_540_040, 10_538_007,
    ]
    .map(CardId)
    .to_vec();
    let versions = RuntimeVersions {
        rules: "ocg-mr5".into(),
        catalog: String::new(),
        banlist: String::new(),
        engine_sha256: "a".repeat(64),
        cdb_sha256: "b".repeat(64),
        scripts_sha256: "c".repeat(64),
        core_commit: CORE_COMMIT.into(),
        initializer: INITIALIZER_VERSION.into(),
    };
    RunDuelRequest {
        protocol_version: 2,
        engine: ProcessEngineConfig {
            timeout_ms: 30_000,
            ..Default::default()
        },
        deck: Deck {
            main,
            extra: vec![CardId(84_013_237), CardId(71_594_310), CardId(77_637_979)],
            side: vec![],
        },
        opening_hand: vec![
            CardId(58_074_572),
            CardId(2_964_201),
            CardId(2_964_201),
            CardId(2_964_201),
            CardId(2_971_090),
        ],
        seed: 1,
        decisions: vec![],
        versions,
        probe_only: false,
        scenario: None,
        interruption: None,
        first_turn: None,
        research_capture: None,
    }
}

#[test]
fn request_shape_rejects_non_curry_main_and_extra_deck_drift() {
    let frozen = request();
    validate_curry_option_request_shape(&frozen).unwrap();

    let mut changed_main = frozen.clone();
    changed_main.deck.main[10] = CardId(1);
    assert!(validate_curry_option_request_shape(&changed_main).is_err());

    let mut changed_extra = frozen;
    changed_extra.deck.extra.swap(0, 1);
    assert!(validate_curry_option_request_shape(&changed_extra).is_err());
}

fn prompt_frame(sequence: u64, raw: Vec<u8>) -> (CoreEventFrame, Prompt) {
    let frame = decode_frame(sequence, &raw).unwrap();
    let prompt = parse_prompt(sequence, &raw).unwrap().unwrap();
    (frame, prompt)
}

fn curry_idle(sequence: u64) -> (CoreEventFrame, Prompt) {
    let mut raw = vec![11, 0];
    for command in 0..6 {
        if command == 5 {
            raw.extend(1u32.to_le_bytes());
            raw.extend(58_074_572u32.to_le_bytes());
            raw.extend([0, 2]);
            raw.extend(0u32.to_le_bytes());
            raw.extend(0u64.to_le_bytes());
            raw.push(0);
        } else {
            raw.extend(0u32.to_le_bytes());
        }
    }
    raw.extend([0, 1, 0]);
    prompt_frame(sequence, raw)
}

fn empty_idle(sequence: u64) -> (CoreEventFrame, Prompt) {
    let mut raw = vec![11, 0];
    raw.extend([0; 24]);
    raw.extend([0, 1, 0]);
    prompt_frame(sequence, raw)
}

fn place_prompt(sequence: u64) -> (CoreEventFrame, Prompt) {
    prompt_frame(sequence, vec![18, 0, 1, 0xff, 0xe0, 0xff, 0xff])
}

fn option_prompt(sequence: u64) -> (CoreEventFrame, Prompt) {
    let mut raw = vec![14, 0, 2];
    raw.extend(60_895_602_409_472u64.to_le_bytes());
    raw.extend(60_895_602_409_473u64.to_le_bytes());
    prompt_frame(sequence, raw)
}

fn recover_frame(sequence: u64, player: u8) -> CoreEventFrame {
    let mut raw = vec![92, player];
    raw.extend(200u32.to_le_bytes());
    decode_frame(sequence, &raw).unwrap()
}

fn result_for(request: &RunDuelRequest) -> DuelResult {
    let (idle, _idle_prompt) = curry_idle(1);
    let (place, _place_prompt) = place_prompt(2);
    let (option, _option_prompt) = option_prompt(3);
    let final_frame = match request.decisions.last().map(|decision| &decision.choice) {
        Some(Choice::Option { index: 0 }) => empty_idle(5),
        Some(Choice::Option { index: 1 }) => empty_idle(5),
        Some(Choice::Place { .. }) => option_prompt(3),
        Some(Choice::Command { .. }) => place_prompt(2),
        None => curry_idle(1),
        _ => empty_idle(5),
    };
    let final_is_idle = final_frame.1.opcode == 11;

    let mut events = vec![idle.clone()];
    if !request.decisions.is_empty() {
        events.push(place.clone());
    }
    if request.decisions.len() >= 2 {
        events.push(option.clone());
    }
    let option_index = request
        .decisions
        .iter()
        .find_map(|decision| match decision.choice {
            Choice::Option { index } => Some(index as u8),
            _ => None,
        });
    if final_is_idle {
        if let Some(option_index) = option_index {
            events.push(recover_frame(4, option_index));
        }
    }
    if events.last().map(|event| event.sequence) != Some(final_frame.0.sequence) {
        events.push(final_frame.0.clone());
    }

    let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
    result.status = DuelStatus::DecisionRequired;
    result.error = None;
    result.versions = request.versions.clone();
    result.resolved_decisions = request.decisions.clone();
    for decision in &request.decisions {
        let action = events
            .iter()
            .filter_map(|frame| parse_prompt(frame.sequence, &frame.raw).unwrap())
            .find(|prompt| prompt.id == decision.prompt_id)
            .and_then(|prompt| {
                prompt
                    .actions
                    .into_iter()
                    .find(|action| action.choice == decision.choice)
            })
            .expect("synthetic requested action exists in its raw prompt");
        result.steps.push(action);
    }
    result.prompt = Some(final_frame.1);
    result.events = events;
    if let Some(option) = option_index {
        result.checkpoint.lp = if option == 0 {
            [8200, 8000]
        } else {
            [8000, 8200]
        };
    }
    result
}

fn stage3_fixture() -> (RunDuelRequest, DuelResult) {
    let mut request = request();
    let (idle_frame, idle_prompt) = curry_idle(1);
    let activation = idle_prompt.actions[0].clone();
    request.decisions.push(Decision {
        prompt_id: idle_prompt.id,
        player: 0,
        choice: activation.choice.clone(),
    });
    let (place_frame, place_menu) = place_prompt(2);
    let place_action = place_menu
        .actions
        .iter()
        .find(|action| {
            action.choice
                == (Choice::Place {
                    zones: vec![Zone {
                        player: 0,
                        location: 8,
                        sequence: 0,
                    }],
                })
        })
        .unwrap()
        .clone();
    request.decisions.push(Decision {
        prompt_id: place_menu.id,
        player: 0,
        choice: place_action.choice.clone(),
    });
    let (option_frame, option_menu) = option_prompt(3);
    let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
    result.status = DuelStatus::DecisionRequired;
    result.error = None;
    result.versions = request.versions.clone();
    result.events = vec![idle_frame, place_frame, option_frame];
    result.prompt = Some(option_menu);
    result.resolved_decisions = request.decisions.clone();
    result.steps = vec![activation, place_action];
    (request, result)
}

fn chain_frame(sequence: u64, forced: bool, candidate_count: u32) -> (CoreEventFrame, Prompt) {
    let mut raw = vec![16, 1, 0, u8::from(forced)];
    raw.extend([0; 8]);
    raw.extend(candidate_count.to_le_bytes());
    for index in 0..candidate_count {
        raw.extend((85_138_716 + index).to_le_bytes());
        raw.extend([0, 4]);
        raw.extend(0u32.to_le_bytes());
        raw.extend(1u32.to_le_bytes());
        raw.extend(60_895_602_409_472u64.to_le_bytes());
        raw.push(0);
    }
    let frame = decode_frame(sequence, &raw).unwrap();
    let prompt = parse_prompt(sequence, &raw).unwrap().unwrap();
    (frame, prompt)
}

struct SyntheticAdapter(Arc<AtomicUsize>);
impl EngineAdapter for SyntheticAdapter {
    fn doctor(&self) -> DoctorReport {
        panic!("Curry batch must not call doctor")
    }

    fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        self.0.fetch_add(1, Ordering::SeqCst);
        Ok(result_for(request))
    }
}

struct FailingAdapter(Arc<AtomicUsize>);
impl EngineAdapter for FailingAdapter {
    fn doctor(&self) -> DoctorReport {
        panic!("Curry batch must not call doctor")
    }

    fn run(&self, _request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        self.0.fetch_add(1, Ordering::SeqCst);
        Err(WorkerError::new(
            "synthetic",
            "test",
            "synthetic stage failure",
        ))
    }
}

fn save_result(batch: &CurryOptionBatch, stage: u8, request: &RunDuelRequest, result: &DuelResult) {
    let assets = json!({"synthetic":"fixed"});
    let outcome = Ok(result.clone());
    batch
        .record_evidence(stage, request, &outcome, &assets, Some(&assets))
        .unwrap();
}

#[test]
fn curry_parent_map_is_fixed_and_branches_replay_their_own_execution() {
    assert_eq!(curry_option_parent_stage(1).unwrap(), None);
    assert_eq!(curry_option_parent_stage(2).unwrap(), Some(1));
    assert_eq!(curry_option_parent_stage(3).unwrap(), Some(2));
    assert_eq!(curry_option_parent_stage(4).unwrap(), Some(3));
    assert_eq!(curry_option_parent_stage(5).unwrap(), Some(4));
    assert_eq!(curry_option_parent_stage(6).unwrap(), Some(3));
    assert_eq!(curry_option_parent_stage(7).unwrap(), Some(6));
    assert!(curry_option_parent_stage(8).is_err());

    let path = unique_path("parent-map");
    let started = unix_now_for_test();
    let batch = CurryOptionBatch::open(&path, "synthetic-parent-map", started).unwrap();
    let first = request();
    batch.validate_request(1, &first).unwrap();

    let mut false_branch = first.clone();
    false_branch.decisions.push(Decision {
        prompt_id: 12,
        player: 0,
        choice: Choice::Option { index: 0 },
    });
    let mut true_branch = first.clone();
    true_branch.decisions.push(Decision {
        prompt_id: 12,
        player: 0,
        choice: Choice::Option { index: 1 },
    });
    assert_ne!(false_branch.decisions, true_branch.decisions);
}

#[test]
fn confirmation_scope_uses_an_isolated_ledger_and_receipt_contract() {
    let path = unique_path("confirmation-scope");
    let started = unix_now_for_test();
    let context = "synthetic-confirmation-scope";
    let batch = CurryOptionBatch::open_confirmation(&path, context, started).unwrap();
    let candidate = request();
    let assets = json!({"synthetic":"fixed"});
    batch.save_assets_before(1, &assets).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let outcome = batch
        .run(SyntheticAdapter(calls.clone()), 1, &candidate)
        .unwrap();
    let receipt = batch
        .record_evidence(1, &candidate, &Ok(outcome), &assets, Some(&assets))
        .unwrap();

    assert_eq!(receipt["scope"], CURRY_OPTION_CONFIRMATION_SCOPE);
    assert_eq!(receipt["kind"], "native_curry_option_confirmation_stage");
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    drop(batch);

    let view = CallJournal::inspect_existing(&path, CURRY_OPTION_CONFIRMATION_SCOPE, context, 7)
        .unwrap()
        .unwrap();
    assert!(view
        .checkpoint("immutable/curry-option-validation/start")
        .unwrap()
        .is_none());
    assert!(view
        .checkpoint("immutable/curry-option-confirmation/start")
        .unwrap()
        .is_some());
    verify_curry_option_confirmation_recorded(&view, 1, context, started, &receipt).unwrap();
    assert!(verify_curry_option_recorded(&view, 1, context, started, &receipt).is_err());
    assert!(CurryOptionBatch::open(&path, context, started).is_err());
    assert_eq!(view.stats().unwrap().consumed, 1);
}

#[test]
fn verification_scope_uses_its_own_fixed_ledger_and_receipt_verifier() {
    let path = unique_path("verification-scope");
    let started = unix_now_for_test();
    let context = "synthetic-verification-scope";
    let batch = CurryOptionBatch::open_verification(&path, context, started).unwrap();
    let candidate = request();
    let assets = json!({"synthetic":"fixed-verification"});
    batch.save_assets_before(1, &assets).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let outcome = batch
        .run(SyntheticAdapter(calls.clone()), 1, &candidate)
        .unwrap();
    let receipt = batch
        .record_evidence(1, &candidate, &Ok(outcome), &assets, Some(&assets))
        .unwrap();

    assert_eq!(receipt["scope"], CURRY_OPTION_VERIFICATION_SCOPE);
    assert_eq!(receipt["kind"], "native_curry_option_verification_stage");
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    drop(batch);

    let view = CallJournal::inspect_existing(&path, CURRY_OPTION_VERIFICATION_SCOPE, context, 7)
        .unwrap()
        .unwrap();
    assert!(view
        .checkpoint("immutable/curry-option-validation/start")
        .unwrap()
        .is_none());
    assert!(view
        .checkpoint("immutable/curry-option-confirmation/start")
        .unwrap()
        .is_none());
    assert!(view
        .checkpoint("immutable/curry-option-verification/start")
        .unwrap()
        .is_some());
    verify_curry_option_verification_recorded(&view, 1, context, started, &receipt).unwrap();
    assert!(verify_curry_option_recorded(&view, 1, context, started, &receipt).is_err());
    assert!(
        verify_curry_option_confirmation_recorded(&view, 1, context, started, &receipt).is_err()
    );
    assert!(CurryOptionBatch::open(&path, context, started).is_err());
    assert!(CurryOptionBatch::open_confirmation(&path, context, started).is_err());
    assert_eq!(view.stats().unwrap().consumed, 1);
}

#[test]
fn confirmation_scope_accounts_all_seven_stages_and_verifies_read_only() {
    let path = unique_path("confirmation-seven-stages");
    let started = unix_now_for_test();
    let context = "synthetic-confirmation-seven-stage";
    let batch = CurryOptionBatch::open_confirmation(&path, context, started).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let root = request();
    let assets = json!({"synthetic":"fixed-confirmation"});
    let mut receipts = Vec::new();

    for stage in 1..=7 {
        let stage_request = if stage == 1 {
            root.clone()
        } else {
            batch.derive_request(stage).unwrap()
        };
        batch.save_assets_before(stage, &assets).unwrap();
        let result = batch
            .run(SyntheticAdapter(calls.clone()), stage, &stage_request)
            .unwrap();
        let receipt = batch
            .record_evidence(stage, &stage_request, &Ok(result), &assets, Some(&assets))
            .unwrap();
        assert_eq!(receipt["scope"], CURRY_OPTION_CONFIRMATION_SCOPE);
        assert_eq!(receipt["kind"], "native_curry_option_confirmation_stage");
        receipts.push(receipt);
    }

    assert_eq!(calls.load(Ordering::SeqCst), 7);
    assert_eq!(batch.stats().unwrap().consumed, 7);
    assert_eq!(batch.stats().unwrap().completed, 7);
    assert_eq!(batch.stats().unwrap().limit, 7);
    drop(batch);

    let ledger_before = fs::read(&path).unwrap();
    let blobs_path = PathBuf::from(format!("{}.blobs", path.display()));
    let blobs_before = snapshot_tree(&blobs_path);
    let view = CallJournal::inspect_existing(&path, CURRY_OPTION_CONFIRMATION_SCOPE, context, 7)
        .unwrap()
        .unwrap();
    for (index, receipt) in receipts.iter().enumerate() {
        verify_curry_option_confirmation_recorded(
            &view,
            (index + 1) as u8,
            context,
            started,
            receipt,
        )
        .unwrap();
    }
    assert!(verify_curry_option_recorded(&view, 1, context, started, &receipts[0]).is_err());
    assert_eq!(view.stats().unwrap().consumed, 7);
    drop(view);
    assert_eq!(fs::read(&path).unwrap(), ledger_before);
    assert_eq!(snapshot_tree(&blobs_path), blobs_before);
}

#[test]
fn curry_batch_accounts_seven_calls_derives_decisions_and_verifies_read_only() {
    let path = unique_path("seven-stages");
    let started = unix_now_for_test();
    let batch = CurryOptionBatch::open(&path, "synthetic-seven-stage", started).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let root = request();
    let mut requests = Vec::new();
    requests.push(root.clone());

    for stage in 1..=7 {
        let request = if stage == 1 {
            root.clone()
        } else {
            batch.derive_request(stage).unwrap()
        };
        let assets = json!({"synthetic":"fixed"});
        batch.save_assets_before(stage, &assets).unwrap();
        batch.validate_request(stage, &request).unwrap();
        let result = batch
            .run(SyntheticAdapter(calls.clone()), stage, &request)
            .unwrap();
        if stage == 1 {
            let mut valid_chain = vec![16, 1, 0, 0];
            valid_chain.extend([0; 8]);
            valid_chain.extend(0u32.to_le_bytes());
            let mut with_chain = result.clone();
            with_chain
                .events
                .insert(0, decode_frame(0, &valid_chain).unwrap());
            let chain_prompt = parse_prompt(0, &valid_chain).unwrap().unwrap();
            with_chain.steps.insert(0, chain_prompt.actions[0].clone());
            let valid = validate_curry_option_result(1, &request, &with_chain);
            assert!(valid.is_ok(), "{valid:?}");

            let mut trailing_chain = valid_chain.clone();
            trailing_chain.push(0);
            let mut malformed_chain = result.clone();
            let mut trailing_frame = decode_frame(0, &valid_chain).unwrap();
            trailing_frame.raw = trailing_chain;
            malformed_chain.events.insert(0, trailing_frame);
            malformed_chain
                .steps
                .insert(0, chain_prompt.actions[0].clone());
            assert!(validate_curry_option_result(1, &request, &malformed_chain).is_err());
        }
        if stage == 2 {
            let mut unordered = result.clone();
            unordered.events[1].sequence = unordered.events[0].sequence;
            assert!(validate_curry_option_result(2, &request, &unordered).is_err());
        }
        save_result(&batch, stage, &request, &result);
        requests.push(request);
    }

    assert_eq!(calls.load(Ordering::SeqCst), 7);
    let stats = batch.stats().unwrap();
    assert_eq!(stats.consumed, 7);
    assert_eq!(stats.completed, 7);
    assert_eq!(stats.unknown, 0);
    assert_eq!(stats.limit, 7);
    assert_eq!(
        serde_json::to_value(&requests[5]).unwrap(),
        serde_json::to_value(&requests[4]).unwrap()
    );
    assert_eq!(
        serde_json::to_value(&requests[7]).unwrap(),
        serde_json::to_value(&requests[6]).unwrap()
    );
    assert_ne!(
        serde_json::to_value(&requests[4]).unwrap(),
        serde_json::to_value(&requests[6]).unwrap()
    );
    assert!(batch
        .run(SyntheticAdapter(calls.clone()), 8, &root)
        .is_err());
    assert_eq!(calls.load(Ordering::SeqCst), 7);

    let receipts = (1..=7)
        .map(|stage| batch.evidence(stage).unwrap().unwrap())
        .collect::<Vec<_>>();
    assert!(receipts.iter().all(|receipt| receipt["successful"] == true));
    drop(batch);

    let ledger_before = fs::read(&path).unwrap();
    let blobs_path = PathBuf::from(format!("{}.blobs", path.display()));
    let blob_snapshot_before = snapshot_tree(&blobs_path);
    let view = CallJournal::inspect_existing(&path, CURRY_OPTION_SCOPE, "synthetic-seven-stage", 7)
        .unwrap()
        .unwrap();
    for (index, receipt) in receipts.iter().enumerate() {
        verify_curry_option_recorded(
            &view,
            (index + 1) as u8,
            "synthetic-seven-stage",
            started,
            receipt,
        )
        .unwrap();
    }
    assert_eq!(view.stats().unwrap().consumed, 7);
    drop(view);
    assert_eq!(fs::read(path).unwrap(), ledger_before);
    let blob_snapshot_after = snapshot_tree(&blobs_path);
    assert_eq!(blob_snapshot_after, blob_snapshot_before);
}

#[test]
fn curry_request_derivation_uses_unique_public_actions_and_refuses_wrong_order() {
    let path = unique_path("derive");
    let batch = CurryOptionBatch::open(&path, "synthetic-derive", unix_now_for_test()).unwrap();
    let root = request();
    batch.validate_request(1, &root).unwrap();
    assert!(batch.derive_request(2).is_err());
    assert!(batch.derive_request(3).is_err());
    assert!(batch.derive_request(5).is_err());
}

#[test]
fn curry_result_oracle_rejects_malformed_option_zone_chain_and_unbound_actions() {
    let (candidate_request, valid) = stage3_fixture();
    validate_curry_option_result(3, &candidate_request, &valid).unwrap();

    let mut bad_option = valid.clone();
    let mut raw = vec![14, 0, 2];
    raw.extend(60_895_602_409_473u64.to_le_bytes());
    raw.extend(60_895_602_409_472u64.to_le_bytes());
    let frame = decode_frame(3, &raw).unwrap();
    bad_option.events[2] = frame.clone();
    bad_option.prompt = parse_prompt(3, &raw).unwrap();
    assert!(validate_curry_option_result(3, &candidate_request, &bad_option).is_err());

    let mut duplicate_zone = valid.clone();
    let duplicate_action = duplicate_zone.events[1].fields["prompt"]["actions"][0].clone();
    duplicate_zone.events[1].fields["prompt"]["actions"][1] = duplicate_action;
    assert!(validate_curry_option_result(3, &candidate_request, &duplicate_zone).is_err());

    let mut extra_prompt = valid.clone();
    let (extra_frame, _) = option_prompt(3);
    let (pending_frame, pending_prompt) = option_prompt(4);
    extra_prompt.events[2] = extra_frame;
    extra_prompt.events.push(pending_frame);
    extra_prompt.prompt = Some(pending_prompt);
    assert!(validate_curry_option_result(3, &candidate_request, &extra_prompt).is_err());

    let mut non_unique_automatic = extra_prompt.clone();
    let (auto_frame, auto_prompt) = option_prompt(3);
    non_unique_automatic.events[2] = auto_frame;
    non_unique_automatic.resolved_decisions.push(Decision {
        prompt_id: 3,
        player: 0,
        choice: Choice::Option { index: 0 },
    });
    non_unique_automatic
        .steps
        .push(auto_prompt.actions[0].clone());
    assert!(validate_curry_option_result(3, &candidate_request, &non_unique_automatic).is_err());

    let mut forced_chain = result_for(&RunDuelRequest {
        decisions: vec![],
        ..request()
    });
    let (frame, prompt) = chain_frame(0, true, 1);
    forced_chain.events.insert(0, frame);
    forced_chain.steps.insert(0, prompt.actions[0].clone());
    assert!(validate_curry_option_result(1, &request(), &forced_chain).is_err());

    let mut nonempty_chain = result_for(&request());
    let (frame, prompt) = chain_frame(0, false, 1);
    nonempty_chain.events.insert(0, frame);
    nonempty_chain.steps.insert(0, prompt.actions[0].clone());
    assert!(validate_curry_option_result(1, &request(), &nonempty_chain).is_err());
}

#[test]
fn protocol_two_opponent_empty_chain_is_bound_by_step_not_resolved_decision() {
    let request = request();
    let mut result = result_for(&request);
    let mut raw = vec![16, 1, 0, 0];
    raw.extend([0; 8]);
    raw.extend(0u32.to_le_bytes());
    let frame = decode_frame(0, &raw).unwrap();
    let prompt = parse_prompt(0, &raw).unwrap().unwrap();
    result.events.insert(0, frame);
    result.steps.insert(0, prompt.actions[0].clone());

    assert!(!result
        .resolved_decisions
        .iter()
        .any(|decision| decision.player == 1));
    assert_eq!(result.steps[0].choice, Choice::Chain { index: None });
    validate_curry_option_result(1, &request, &result).unwrap();

    let mut nonzero_special_count = result_for(&request);
    let mut raw = vec![16, 1, 1, 0];
    raw.extend([0; 8]);
    raw.extend(0u32.to_le_bytes());
    let (frame, prompt) = prompt_frame(0, raw);
    nonzero_special_count.events.insert(0, frame);
    nonzero_special_count
        .steps
        .insert(0, prompt.actions[0].clone());
    assert!(validate_curry_option_result(1, &request, &nonzero_special_count).is_err());
}

#[test]
fn failed_parent_is_receipted_but_cannot_charge_a_child() {
    let path = unique_path("failed-parent");
    let started = unix_now_for_test();
    let batch = CurryOptionBatch::open(&path, "synthetic-failed-parent", started).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let root = request();
    let assets = json!({"synthetic":"fixed"});
    batch.save_assets_before(1, &assets).unwrap();
    let outcome = batch.run(FailingAdapter(calls.clone()), 1, &root);
    assert!(outcome.is_err());
    let receipt = batch
        .record_evidence(1, &root, &outcome, &assets, Some(&assets))
        .unwrap();
    assert_eq!(receipt["successful"], false);
    assert!(batch.derive_request(2).is_err());
    assert!(batch
        .run(SyntheticAdapter(calls.clone()), 2, &root)
        .is_err());
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(batch.stats().unwrap().consumed, 1);
}

#[test]
fn replay_receipt_preserves_matching_replay_when_asset_gate_fails() {
    let path = unique_path("failed-replay-gate");
    let started = unix_now_for_test();
    let batch = CurryOptionBatch::open(&path, "synthetic-failed-replay-gate", started).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let root = request();
    let assets = json!({"synthetic":"fixed"});
    for stage in 1..=4 {
        let stage_request = if stage == 1 {
            root.clone()
        } else {
            batch.derive_request(stage).unwrap()
        };
        batch.save_assets_before(stage, &assets).unwrap();
        let result = batch
            .run(SyntheticAdapter(calls.clone()), stage, &stage_request)
            .unwrap();
        save_result(&batch, stage, &stage_request, &result);
    }
    let replay_request = batch.derive_request(5).unwrap();
    batch.save_assets_before(5, &assets).unwrap();
    let result = batch
        .run(SyntheticAdapter(calls.clone()), 5, &replay_request)
        .unwrap();
    let drifted_assets = json!({"synthetic":"drifted"});
    let receipt = batch
        .record_evidence(
            5,
            &replay_request,
            &Ok(result),
            &assets,
            Some(&drifted_assets),
        )
        .unwrap();
    assert_eq!(receipt["successful"], false);
    assert_eq!(receipt["independent_replay_matches"], true);
    batch.verify_evidence(5, &receipt).unwrap();
    assert_eq!(calls.load(Ordering::SeqCst), 5);
    assert_eq!(batch.stats().unwrap().consumed, 5);
    drop(batch);

    let ledger_before = fs::read(&path).unwrap();
    let view =
        CallJournal::inspect_existing(&path, CURRY_OPTION_SCOPE, "synthetic-failed-replay-gate", 7)
            .unwrap()
            .unwrap();
    verify_curry_option_recorded(&view, 5, "synthetic-failed-replay-gate", started, &receipt)
        .unwrap();
    assert_eq!(view.stats().unwrap().consumed, 5);
    drop(view);
    assert_eq!(fs::read(path).unwrap(), ledger_before);
}

#[test]
fn curry_window_requires_more_than_thirty_seconds_and_forbids_clock_reversal() {
    let start = 100;
    assert!(curry_option_window_allows_request(start, 101));
    assert!(curry_option_window_allows_request(start, 7_269));
    assert!(!curry_option_window_allows_request(start, 7_270));
    assert!(!curry_option_window_allows_request(start, 99));
    assert!(!curry_option_window_allows_result(start, 7_300));
    assert!(curry_option_window_allows_result(start, 7_299));
}

fn unix_now_for_test() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs()
}
