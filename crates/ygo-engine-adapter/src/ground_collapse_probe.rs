//! Dedicated charged stage driver for the fixed Ground Collapse opcode24 probe.
//!
//! This scope is separate from Tenki prompt probing. All methods are inert
//! until a caller explicitly opens a ledger and invokes `run`.

use crate::*;
use serde_json::{json, Value};
use std::path::Path;
use std::sync::{Arc, Mutex};

pub const GROUND_COLLAPSE_PROBE_SCOPE: &str = "p1-ground-collapse-opcode24-reachability-v1";
pub const GROUND_COLLAPSE_PROBE_LIMIT: usize = 5;
pub const GROUND_COLLAPSE_PROBE_WINDOW_SECONDS: u64 = 1800;
pub const GROUND_COLLAPSE_PROBE_TIMEOUT_MS: u64 = 30_000;

const TARGET_CARD: u32 = 90_502_999;
const TARGET_ZONES: [Zone; 2] = [
    Zone {
        player: 1,
        location: 4,
        sequence: 0,
    },
    Zone {
        player: 1,
        location: 4,
        sequence: 1,
    },
];
const OPCODE18_ZONE: Zone = Zone {
    player: 0,
    location: 8,
    sequence: 0,
};

fn fail(message: &str) -> WorkerError {
    WorkerError::new("ground_collapse_probe", "ground_collapse_probe", message)
}

fn now() -> Result<u64, WorkerError> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_secs())
        .map_err(|error| fail(&error.to_string()))
}

fn value<T: serde::Serialize>(item: &T) -> Result<Value, WorkerError> {
    serde_json::to_value(item).map_err(|error| fail(&error.to_string()))
}

fn same_request(left: &RunDuelRequest, right: &RunDuelRequest) -> Result<bool, WorkerError> {
    Ok(value(left)? == value(right)?)
}

fn base_request(request: &RunDuelRequest) -> Result<RunDuelRequest, WorkerError> {
    if request.protocol_version != PROTOCOL_VERSION
        || request.engine.timeout_ms != GROUND_COLLAPSE_PROBE_TIMEOUT_MS
        || request.seed != 1
        || request.deck.main.len() != 40
        || request.deck.extra.len() != 3
        || !request.deck.side.is_empty()
        || request.opening_hand.len() != 5
        || request.probe_only
        || request.scenario.is_some()
        || request.interruption.is_some()
        || request.first_turn.is_some()
        || request.research_capture.is_some()
        || request.versions.rules != "ocg-mr5"
        || request.versions.core_commit != CORE_COMMIT
        || request.versions.initializer != INITIALIZER_VERSION
        || request.versions.engine_sha256
            != "446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9"
        || request.versions.cdb_sha256
            != "c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225"
        || request.versions.scripts_sha256
            != "69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91"
        || request
            .deck
            .main
            .iter()
            .filter(|card| card.0 == TARGET_CARD)
            .count()
            != 1
        || request
            .opening_hand
            .iter()
            .filter(|card| card.0 == TARGET_CARD)
            .count()
            != 1
    {
        return Err(fail("unsupported frozen Ground Collapse request"));
    }
    let mut base = request.clone();
    base.decisions.clear();
    Ok(base)
}

fn prompt_frames(result: &DuelResult) -> Result<Vec<(CoreEventFrame, Prompt)>, String> {
    if result
        .events
        .windows(2)
        .any(|pair| pair[0].sequence >= pair[1].sequence)
    {
        return Err("event_sequence_not_strictly_increasing".into());
    }
    let mut prompts = Vec::new();
    for frame in &result.events {
        if matches!(frame.opcode, 11..=16 | 18 | 19 | 24 | 26) {
            let parsed = parse_prompt(frame.sequence, &frame.raw)?
                .ok_or_else(|| "raw_prompt_missing".to_string())?;
            let recorded: Prompt = serde_json::from_value(
                frame
                    .fields
                    .get("prompt")
                    .cloned()
                    .ok_or_else(|| "recorded_prompt_missing".to_string())?,
            )
            .map_err(|_| "recorded_prompt_malformed".to_string())?;
            if parsed != recorded || parsed.opcode != frame.opcode {
                return Err("raw_recorded_prompt_mismatch".into());
            }
            let audit = audit_prompt_responses(
                &frame.raw,
                &parsed
                    .actions
                    .iter()
                    .map(|action| action.bytes.clone())
                    .collect::<Vec<_>>(),
            )?;
            if !audit.matches {
                return Err("raw_response_oracle_mismatch".into());
            }
            prompts.push((frame.clone(), parsed));
        }
    }
    Ok(prompts)
}

fn unique_activation(prompt: &Prompt) -> Result<Action, String> {
    if prompt.opcode != 11 || prompt.player != 0 {
        return Err("ground_activation_requires_own_idle".into());
    }
    let found = prompt
        .actions
        .iter()
        .filter(|action| {
            matches!(action.choice, Choice::Command { command: 5, .. })
                && action.card_ids == [TARGET_CARD]
        })
        .collect::<Vec<_>>();
    if found.len() != 1 {
        return Err("ground_activation_not_unique".into());
    }
    let action = found[0];
    if let Choice::Command { index, .. } = action.choice {
        if action.bytes != ((index << 16) | 5).to_le_bytes() {
            return Err("ground_activation_response_mismatch".into());
        }
    }
    Ok(action.clone())
}

fn fixed_place_action(prompt: &Prompt, raw: &[u8], opcode: u8) -> Result<Action, String> {
    let (zones, response) = match opcode {
        18 => {
            if raw.len() != 7 || raw[1] != 0 || raw[2] != 1 {
                return Err("opcode18_fixed_count_or_player_mismatch".into());
            }
            (vec![OPCODE18_ZONE], vec![0, 8, 0])
        }
        24 => {
            if raw.len() != 7 || raw[1] != 0 || raw[2] != 2 {
                return Err("opcode24_fixed_count_or_player_mismatch".into());
            }
            (TARGET_ZONES.to_vec(), vec![1, 4, 0, 1, 4, 1])
        }
        _ => return Err("fixed_place_opcode_unsupported".into()),
    };
    if prompt.opcode != opcode || prompt.player != 0 {
        return Err("fixed_place_prompt_binding_mismatch".into());
    }
    let expected = Choice::Place { zones };
    let actions = prompt
        .actions
        .iter()
        .filter(|action| {
            action.choice == expected && action.card_ids.is_empty() && action.bytes == response
        })
        .collect::<Vec<_>>();
    if actions.len() != 1 || prompt.encode(&expected).as_deref() != Ok(response.as_slice()) {
        return Err(format!("opcode{opcode}_fixed_action_not_unique"));
    }
    Ok(actions[0].clone())
}

fn matching_prompt(
    prompts: &[(CoreEventFrame, Prompt)],
    id: u64,
) -> Result<(&CoreEventFrame, &Prompt), String> {
    let found = prompts
        .iter()
        .filter(|(_, prompt)| prompt.id == id)
        .collect::<Vec<_>>();
    if found.len() != 1 {
        return Err("prompt_id_not_unique_in_raw_events".into());
    }
    Ok((&found[0].0, &found[0].1))
}

fn validate_resolved_decisions(
    request: &RunDuelRequest,
    result: &DuelResult,
    prompts: &[(CoreEventFrame, Prompt)],
) -> Result<(), String> {
    if result.resolved_decisions.len() < request.decisions.len()
        || result.resolved_decisions[..request.decisions.len()] != request.decisions
    {
        return Err("request_decision_prefix_not_resolved".into());
    }
    for (index, decision) in result.resolved_decisions.iter().enumerate() {
        if result.resolved_decisions[..index]
            .iter()
            .any(|previous| previous.prompt_id >= decision.prompt_id)
        {
            return Err("resolved_decision_order_invalid".into());
        }
        let (_, prompt) = matching_prompt(prompts, decision.prompt_id)?;
        if prompt.player != decision.player || prompt.encode(&decision.choice).is_err() {
            return Err("resolved_decision_not_in_raw_menu".into());
        }
        if index >= request.decisions.len()
            && (prompt.actions.len() != 1 || prompt.actions[0].choice != decision.choice)
        {
            return Err("unapproved_automatic_decision".into());
        }
    }
    Ok(())
}

fn fixed_zone_decision(choice: &Choice, opcode: u8) -> bool {
    let zones = match choice {
        Choice::Place { zones } => zones,
        _ => return false,
    };
    if opcode == 18 {
        zones == &[OPCODE18_ZONE]
    } else {
        zones.as_slice() == TARGET_ZONES.as_slice()
    }
}

/// Validate one charged result against the frozen activation and zone route.
pub fn validate_ground_collapse_result(
    request: &RunDuelRequest,
    result: &DuelResult,
) -> Result<Value, String> {
    if result.protocol_version != PROTOCOL_VERSION
        || result.error.is_some()
        || !result.coverage_gaps.is_empty()
        || !matches!(
            result.status,
            DuelStatus::DecisionRequired | DuelStatus::EngineVerified | DuelStatus::ProbePassed
        )
    {
        return Err("engine_result_not_clean".into());
    }
    let prompts = prompt_frames(result)?;
    validate_resolved_decisions(request, result, &prompts)?;
    let pending = match result.status {
        DuelStatus::DecisionRequired => {
            let pending = result
                .prompt
                .as_ref()
                .ok_or_else(|| "pending_prompt_missing".to_string())?;
            if prompts.last().map(|(_, prompt)| prompt) != Some(pending) {
                return Err("pending_prompt_not_final_raw_prompt".into());
            }
            Some(pending)
        }
        DuelStatus::EngineVerified | DuelStatus::ProbePassed => {
            if result.prompt.is_some() {
                return Err("terminal_result_has_prompt".into());
            }
            None
        }
        _ => unreachable!(),
    };

    if request.decisions.is_empty() {
        if pending.is_none() {
            return Err("initial_request_did_not_reach_prompt".into());
        }
        let prompt = pending.unwrap();
        unique_activation(prompt)?;
        return Ok(json!({"phase":"activation_available","prompt_id":prompt.id,
            "opcode":11,"player":0,"proof_ready":false,"complete_action_coverage":false,
            "global_optimality":false,"native_probability_verified":false}));
    }

    let decision = request.decisions.last().ok_or("last_decision_missing")?;
    match &decision.choice {
        Choice::Command { command: 5, .. } => {
            let prompt = pending.ok_or("activation_followup_prompt_missing")?;
            if !matches!(prompt.opcode, 18 | 24) || prompt.player != 0 {
                return Err("unexpected_activation_followup".into());
            }
            let (frame, _) = matching_prompt(&prompts, prompt.id)?;
            fixed_place_action(prompt, &frame.raw, prompt.opcode)?;
            Ok(
                json!({"phase":if prompt.opcode == 18 {"opcode18_available"} else {"opcode24_available"},
                "prompt_id":prompt.id,"opcode":prompt.opcode,"player":prompt.player,
                "proof_ready":false,"complete_action_coverage":false,"global_optimality":false,
                "native_probability_verified":false}),
            )
        }
        Choice::Place { zones } if zones == &[OPCODE18_ZONE] => {
            let prompt = pending.ok_or("opcode24_prompt_after_opcode18_missing")?;
            if prompt.opcode != 24 || prompt.player != 0 {
                return Err("unexpected_opcode18_followup".into());
            }
            let (frame, _) = matching_prompt(&prompts, prompt.id)?;
            fixed_place_action(prompt, &frame.raw, 24)?;
            Ok(
                json!({"phase":"opcode24_available","prompt_id":prompt.id,"opcode":24,
                "player":0,"proof_ready":false,"complete_action_coverage":false,
                "global_optimality":false,"native_probability_verified":false}),
            )
        }
        Choice::Place { zones } if zones == &TARGET_ZONES => {
            let (frame, prompt) = matching_prompt(&prompts, decision.prompt_id)?;
            if prompt.opcode != 24 || prompt.player != 0 {
                return Err("selected_prompt_is_not_opcode24".into());
            }
            fixed_place_action(prompt, &frame.raw, 24)?;
            let later = result
                .events
                .iter()
                .filter(|event| event.sequence > frame.sequence)
                .collect::<Vec<_>>();
            if pending.is_some()
                || later
                    .iter()
                    .any(|event| matches!(event.opcode, 11..=16 | 18 | 19 | 24 | 26))
            {
                return Err("unexpected_post_response_prompt".into());
            }
            if later.is_empty()
                && !matches!(
                    result.status,
                    DuelStatus::EngineVerified | DuelStatus::ProbePassed
                )
            {
                return Err("post_response_event_or_terminal_state_missing".into());
            }
            if !result.resolved_decisions.contains(decision) {
                return Err("selected_response_not_consumed".into());
            }
            Ok(
                json!({"phase":"opcode24_response_accepted","prompt_id":decision.prompt_id,
                "opcode":24,"player":0,"response_bytes":[1,4,0,1,4,1],
                "proof_ready":false,"complete_action_coverage":false,"global_optimality":false,
                "native_probability_verified":false}),
            )
        }
        _ => Err("unsupported_ground_decision".into()),
    }
}

/// Replay comparison ignores only the volatile working-set sample.
pub fn ground_collapse_replay_matches(a: &DuelResult, b: &DuelResult) -> bool {
    let mut left = match value(a) {
        Ok(value) => value,
        Err(_) => return false,
    };
    let mut right = match value(b) {
        Ok(value) => value,
        Err(_) => return false,
    };
    left["peak_working_set_bytes"] = Value::Null;
    right["peak_working_set_bytes"] = Value::Null;
    left == right
}

fn append_action(
    request: &RunDuelRequest,
    result: &DuelResult,
    prompt: &Prompt,
    action: &Action,
) -> RunDuelRequest {
    let mut next = request.clone();
    next.decisions = result.resolved_decisions.clone();
    next.decisions.push(Decision {
        prompt_id: prompt.id,
        player: prompt.player,
        choice: action.choice.clone(),
    });
    next
}

fn derive_next_request(
    stage: u8,
    request: &RunDuelRequest,
    result: &DuelResult,
) -> Result<RunDuelRequest, WorkerError> {
    validate_ground_collapse_result(request, result).map_err(|error| fail(&error))?;
    if stage == 1 {
        let prompt = result
            .prompt
            .as_ref()
            .ok_or_else(|| fail("initial_prompt_missing"))?;
        let action = unique_activation(prompt).map_err(|error| fail(&error))?;
        return Ok(append_action(request, result, prompt, &action));
    }
    if stage == 2 {
        let prompt = result
            .prompt
            .as_ref()
            .ok_or_else(|| fail("activation_followup_missing"))?;
        let (frame, _) = prompt_frames(result)
            .map_err(|error| fail(&error))?
            .into_iter()
            .find(|(_, item)| item.id == prompt.id)
            .ok_or_else(|| fail("activation_prompt_frame_missing"))?;
        let action =
            fixed_place_action(prompt, &frame.raw, prompt.opcode).map_err(|error| fail(&error))?;
        return Ok(append_action(request, result, prompt, &action));
    }

    let last = request
        .decisions
        .last()
        .ok_or_else(|| fail("parent_decision_missing"))?;
    if stage == 3 && fixed_zone_decision(&last.choice, 18) {
        let prompt = result
            .prompt
            .as_ref()
            .ok_or_else(|| fail("parent_prompt_missing"))?;
        if prompt.opcode != 24 || prompt.player != 0 {
            return Err(fail("unexpected_opcode18_followup"));
        }
        let (frame, _) = prompt_frames(result)
            .map_err(|error| fail(&error))?
            .into_iter()
            .find(|(_, item)| item.id == prompt.id)
            .ok_or_else(|| fail("parent_prompt_frame_missing"))?;
        let action = fixed_place_action(prompt, &frame.raw, 24).map_err(|error| fail(&error))?;
        return Ok(append_action(request, result, prompt, &action));
    }
    if (stage == 3 || stage == 4) && fixed_zone_decision(&last.choice, 24) {
        return Ok(request.clone());
    }
    Err(fail("invalid_ground_stage_transition"))
}

fn receipt_name(stage: u8) -> Result<String, WorkerError> {
    if !(1..=GROUND_COLLAPSE_PROBE_LIMIT as u8).contains(&stage) {
        return Err(fail("stage_outside_ground_window"));
    }
    Ok(format!("immutable/ground-collapse/evidence/{stage}"))
}

fn intent_name(stage: u8) -> Result<String, WorkerError> {
    if !(1..=GROUND_COLLAPSE_PROBE_LIMIT as u8).contains(&stage) {
        return Err(fail("stage_outside_ground_window"));
    }
    Ok(format!("immutable/ground-collapse/intent/{stage}"))
}

/// One authenticated 1,800-second, five-request Ground Collapse scope.
pub struct GroundCollapseProbeBatch {
    journal: ProbeJournal,
    context: String,
    started: u64,
    gate: Mutex<()>,
}

enum ProbeJournal {
    Writable(Arc<CallJournal>),
    ReadOnly(Box<ReadOnlyJournal>),
}

impl ProbeJournal {
    fn stats(&self) -> Result<LedgerStats, WorkerError> {
        match self {
            Self::Writable(journal) => journal.stats(),
            Self::ReadOnly(journal) => journal.stats(),
        }
    }

    fn verify(&self) -> Result<(), WorkerError> {
        match self {
            Self::Writable(journal) => journal.verify(),
            Self::ReadOnly(journal) => journal.verify(),
        }
    }

    fn checkpoint(&self, name: &str) -> Result<Option<Value>, WorkerError> {
        match self {
            Self::Writable(journal) => journal.checkpoint(name),
            Self::ReadOnly(journal) => journal.checkpoint(name),
        }
    }

    fn load_outcome(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        match self {
            Self::Writable(journal) => journal.load_outcome(call_id, request),
            Self::ReadOnly(journal) => journal.load_outcome(call_id, request),
        }
    }

    fn save_checkpoint(&self, name: &str, value: &Value) -> Result<(), WorkerError> {
        match self {
            Self::Writable(journal) => journal.save_checkpoint(name, value),
            Self::ReadOnly(_) => Err(WorkerError::new(
                "journal_readonly",
                "ground_collapse_probe",
                "read-only Ground Collapse inspection cannot write checkpoints",
            )),
        }
    }

    fn writable(&self) -> Result<Arc<CallJournal>, WorkerError> {
        match self {
            Self::Writable(journal) => Ok(journal.clone()),
            Self::ReadOnly(_) => Err(WorkerError::new(
                "journal_readonly",
                "ground_collapse_probe",
                "read-only Ground Collapse inspection cannot execute requests",
            )),
        }
    }
}

impl GroundCollapseProbeBatch {
    pub fn open(path: &Path, context: &str, started: u64) -> Result<Self, WorkerError> {
        if context.is_empty() || started > now()? {
            return Err(fail("invalid_context_or_start"));
        }
        let journal = CallJournal::open(
            path,
            GROUND_COLLAPSE_PROBE_SCOPE,
            context,
            GROUND_COLLAPSE_PROBE_LIMIT,
        )?;
        match journal.checkpoint("immutable/ground-collapse/start")? {
            Some(existing) if existing != json!(started) => {
                return Err(fail("immutable_start_changed"));
            }
            Some(_) => {}
            None => journal.save_checkpoint("immutable/ground-collapse/start", &json!(started))?,
        }
        Ok(Self {
            journal: ProbeJournal::Writable(journal),
            context: context.into(),
            started,
            gate: Mutex::new(()),
        })
    }

    /// Open a fully authenticated existing scope without recovering or writing
    /// checkpoints. Inspection requires the original start checkpoint to exist.
    pub fn inspect_existing(path: &Path, context: &str, started: u64) -> Result<Self, WorkerError> {
        if context.is_empty() || started > now()? {
            return Err(fail("invalid_context_or_start"));
        }
        let journal = CallJournal::inspect_existing(
            path,
            GROUND_COLLAPSE_PROBE_SCOPE,
            context,
            GROUND_COLLAPSE_PROBE_LIMIT,
        )?
        .ok_or_else(|| {
            WorkerError::new(
                "journal_readonly_incomplete",
                "ground_collapse_probe",
                "existing ledger required",
            )
        })?;
        match journal.checkpoint("immutable/ground-collapse/start")? {
            Some(existing) if existing == json!(started) => {}
            Some(_) => return Err(fail("immutable_start_changed")),
            None => {
                return Err(WorkerError::new(
                    "start_checkpoint_missing",
                    "ground_collapse_probe",
                    "read-only scope start checkpoint is missing",
                ))
            }
        }
        Ok(Self {
            journal: ProbeJournal::ReadOnly(Box::new(journal)),
            context: context.into(),
            started,
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
        let at = now()?;
        if at < self.started || at - self.started >= GROUND_COLLAPSE_PROBE_WINDOW_SECONDS {
            Err(fail("scope_window_exhausted"))
        } else {
            Ok(())
        }
    }

    fn require_call_time(&self) -> Result<(), WorkerError> {
        self.require_time()?;
        if now()?
            .saturating_sub(self.started)
            .saturating_add(GROUND_COLLAPSE_PROBE_TIMEOUT_MS / 1000)
            >= GROUND_COLLAPSE_PROBE_WINDOW_SECONDS
        {
            return Err(fail("insufficient_window_for_request"));
        }
        Ok(())
    }

    pub fn evidence(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        self.journal.checkpoint(&receipt_name(stage)?)
    }

    pub fn save_evidence(&self, stage: u8, receipt: &Value) -> Result<(), WorkerError> {
        self.journal.save_checkpoint(&receipt_name(stage)?, receipt)
    }

    pub fn validate_request(&self, stage: u8, request: &RunDuelRequest) -> Result<(), WorkerError> {
        self.validate_request_inner(stage, request, true)
    }

    fn validate_request_inner(
        &self,
        stage: u8,
        request: &RunDuelRequest,
        initialize_base_request: bool,
    ) -> Result<(), WorkerError> {
        if !(1..=GROUND_COLLAPSE_PROBE_LIMIT as u8).contains(&stage) {
            return Err(fail("stage_outside_ground_window"));
        }
        let base = base_request(request)?;
        if stage == 1 {
            if !request.decisions.is_empty() {
                return Err(fail("initial_request_has_decisions"));
            }
            match self
                .journal
                .checkpoint("immutable/ground-collapse/base-request")?
            {
                Some(existing) if existing != value(&base)? => {
                    return Err(fail("base_request_changed"));
                }
                Some(_) => {}
                None if initialize_base_request => self
                    .journal
                    .save_checkpoint("immutable/ground-collapse/base-request", &value(&base)?)?,
                None => {
                    return Err(WorkerError::new(
                        "base_request_checkpoint_missing",
                        "ground_collapse_probe",
                        "read-only stage receipt has no base request checkpoint",
                    ))
                }
            }
            return Ok(());
        }
        let base_checkpoint = self
            .journal
            .checkpoint("immutable/ground-collapse/base-request")?
            .ok_or_else(|| fail("base_request_checkpoint_missing"))?;
        if base_checkpoint != value(&base)? {
            return Err(fail("base_request_changed"));
        }
        let parent = self
            .evidence(stage - 1)?
            .ok_or_else(|| fail("parent_stage_receipt_missing"))?;
        self.verify_evidence(stage - 1, &parent)?;
        if parent.get("successful") != Some(&Value::Bool(true)) {
            return Err(fail("parent_stage_unsuccessful"));
        }
        let parent_request: RunDuelRequest = serde_json::from_value(
            parent
                .get("request")
                .cloned()
                .ok_or_else(|| fail("parent_request_missing"))?,
        )
        .map_err(|error| fail(&error.to_string()))?;
        let parent_result: Result<DuelResult, WorkerError> = serde_json::from_value(
            parent
                .get("result")
                .cloned()
                .ok_or_else(|| fail("parent_result_missing"))?,
        )
        .map_err(|error| fail(&error.to_string()))?;
        let parent_result = parent_result.map_err(|_| fail("parent_engine_result_failed"))?;
        let expected = derive_next_request(stage - 1, &parent_request, &parent_result)?;
        if !same_request(&expected, request)? {
            return Err(fail("request_not_exact_parent_derivation"));
        }
        Ok(())
    }

    pub fn verify_evidence(&self, stage: u8, receipt: &Value) -> Result<(), WorkerError> {
        if receipt.get("stage") != Some(&json!(stage))
            || receipt.get("scope") != Some(&json!(GROUND_COLLAPSE_PROBE_SCOPE))
            || receipt.get("context") != Some(&json!(self.context))
            || receipt.get("started_at") != Some(&json!(self.started))
        {
            return Err(fail("receipt_scope_binding_mismatch"));
        }
        let request: RunDuelRequest = serde_json::from_value(
            receipt
                .get("request")
                .cloned()
                .ok_or_else(|| fail("receipt_request_missing"))?,
        )
        .map_err(|error| fail(&error.to_string()))?;
        self.validate_request_inner(stage, &request, false)?;
        let outcome: Result<DuelResult, WorkerError> = serde_json::from_value(
            receipt
                .get("result")
                .cloned()
                .ok_or_else(|| fail("receipt_result_missing"))?,
        )
        .map_err(|error| fail(&error.to_string()))?;
        let saved = self
            .journal
            .load_outcome(stage.into(), &request)?
            .ok_or_else(|| fail("charged_outcome_missing"))?;
        if value(&saved)? != value(&outcome)? {
            return Err(fail("receipt_outcome_changed"));
        }
        let validation = outcome
            .as_ref()
            .map_err(|error| error.message.clone())
            .and_then(|result| validate_ground_collapse_result(&request, result));
        if receipt.get("validation") != Some(&value(&validation)?) {
            return Err(fail("receipt_validation_changed"));
        }
        let before_key = format!("immutable/ground-collapse/assets/{stage}");
        if self.journal.checkpoint(&before_key)?.as_ref() != receipt.get("assets_before") {
            return Err(fail("receipt_asset_precheck_changed"));
        }
        let replay = if self.is_replay(stage, &request)? {
            let parent: Result<DuelResult, WorkerError> = serde_json::from_value(
                self.evidence(stage - 1)?
                    .and_then(|value| value.get("result").cloned())
                    .ok_or_else(|| fail("replay_parent_missing"))?,
            )
            .map_err(|error| fail(&error.to_string()))?;
            json!(match (&parent, &outcome) {
                (Ok(a), Ok(b)) => ground_collapse_replay_matches(a, b),
                _ => false,
            })
        } else {
            Value::Null
        };
        if receipt.get("independent_replay_matches") != Some(&replay) {
            return Err(fail("receipt_replay_comparison_changed"));
        }
        if receipt.get("successful") == Some(&Value::Bool(true))
            && (validation.is_err()
                || receipt.get("assets_unchanged") != Some(&Value::Bool(true))
                || receipt.get("assets_before") != receipt.get("assets_after")
                || (replay != Value::Null && replay != Value::Bool(true)))
        {
            return Err(fail("successful_receipt_has_failed_gate"));
        }
        self.journal.verify()
    }

    fn is_replay(&self, stage: u8, request: &RunDuelRequest) -> Result<bool, WorkerError> {
        if stage <= 1 {
            return Ok(false);
        }
        let Some(parent) = self.evidence(stage - 1)? else {
            return Ok(false);
        };
        let parent_request: RunDuelRequest = serde_json::from_value(
            parent
                .get("request")
                .cloned()
                .ok_or_else(|| fail("parent_request_missing"))?,
        )
        .map_err(|error| fail(&error.to_string()))?;
        same_request(&parent_request, request)
    }

    /// Debit and execute exactly one request. There is no retry or refund path.
    pub fn run<A: EngineAdapter>(
        &self,
        adapter: A,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<DuelResult, WorkerError> {
        self.run_with_time_check(adapter, stage, request, || self.require_call_time())
    }

    fn run_with_time_check<A, F>(
        &self,
        adapter: A,
        stage: u8,
        request: &RunDuelRequest,
        mut require_call_time: F,
    ) -> Result<DuelResult, WorkerError>
    where
        A: EngineAdapter,
        F: FnMut() -> Result<(), WorkerError>,
    {
        let _guard = self.gate.lock().map_err(|_| fail("poisoned_scope_gate"))?;
        self.validate_request(stage, request)?;
        require_call_time()?;
        let stats = self.stats()?;
        if stats.consumed != stage as usize - 1
            || stats.unknown != 0
            || stats.reserved != 0
            || stats.consumed >= GROUND_COLLAPSE_PROBE_LIMIT
            || self.journal.checkpoint(&intent_name(stage)?)?.is_some()
            || self.evidence(stage)?.is_some()
        {
            return Err(fail("out_of_sequence_or_unresolved_scope"));
        }
        let purpose = if stage == 1 {
            CallPurpose::Probe
        } else if self.is_replay(stage, request)? {
            CallPurpose::Replay
        } else {
            CallPurpose::Execution
        };
        require_call_time()?;
        self.journal.save_checkpoint(
            &intent_name(stage)?,
            &json!({"stage":stage,"purpose":purpose,"request":request}),
        )?;
        JournaledAdapter::new(adapter, self.journal.writable()?, purpose).run(request)
    }

    pub fn save_assets_before(&self, stage: u8, identity: &Value) -> Result<(), WorkerError> {
        if !(1..=GROUND_COLLAPSE_PROBE_LIMIT as u8).contains(&stage) {
            return Err(fail("stage_outside_ground_window"));
        }
        self.journal.save_checkpoint(
            &format!("immutable/ground-collapse/assets/{stage}"),
            identity,
        )
    }

    pub fn assets_before(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        self.journal
            .checkpoint(&format!("immutable/ground-collapse/assets/{stage}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::{fs::OpenOptions, io::Write};

    #[derive(Clone)]
    struct SyntheticGroundEngine(Arc<AtomicU64>);
    impl EngineAdapter for SyntheticGroundEngine {
        fn doctor(&self) -> DoctorReport {
            panic!("Ground Collapse stage tests must not call doctor")
        }

        fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            let peak = self.0.fetch_add(1, Ordering::SeqCst) + 1;
            let idle_raw = idle_frame();
            let idle_prompt = parse_prompt(1, &idle_raw).unwrap().unwrap();
            let idle_event = CoreEventFrame {
                sequence: 1,
                opcode: 11,
                raw: idle_raw,
                supported: true,
                fields: json!({"prompt":idle_prompt}),
            };
            let mut result = DuelResult::failure(WorkerError::new("unused", "test", "unused"));
            result.error = None;
            result.coverage_gaps.clear();
            result.versions = request.versions.clone();
            result.resolved_decisions = request.decisions.clone();
            result.peak_working_set_bytes = Some(peak);
            if request.decisions.is_empty() {
                result.status = DuelStatus::DecisionRequired;
                result.prompt = Some(idle_prompt);
                result.events = vec![idle_event];
                return Ok(result);
            }
            let last = request.decisions.last().unwrap();
            if matches!(last.choice, Choice::Command { command: 5, .. }) {
                let raw = opcode24_frame();
                let prompt = parse_prompt(2, &raw).unwrap().unwrap();
                result.status = DuelStatus::DecisionRequired;
                result.prompt = Some(prompt.clone());
                result.events = vec![
                    idle_event,
                    CoreEventFrame {
                        sequence: 2,
                        opcode: 24,
                        raw,
                        supported: true,
                        fields: json!({"prompt":prompt}),
                    },
                ];
                return Ok(result);
            }
            if fixed_zone_decision(&last.choice, 24) {
                let raw = opcode24_frame();
                let prompt = parse_prompt(last.prompt_id, &raw).unwrap().unwrap();
                result.status = DuelStatus::EngineVerified;
                result.prompt = None;
                result.events = vec![
                    idle_event,
                    CoreEventFrame {
                        sequence: last.prompt_id,
                        opcode: 24,
                        raw,
                        supported: true,
                        fields: json!({"prompt":prompt}),
                    },
                    CoreEventFrame {
                        sequence: last.prompt_id + 1,
                        opcode: 52,
                        raw: vec![52],
                        supported: true,
                        fields: json!({}),
                    },
                ];
                return Ok(result);
            }
            Err(fail("synthetic unsupported request"))
        }
    }

    fn idle_frame() -> Vec<u8> {
        let mut raw = vec![11, 0];
        for command in 0..6 {
            raw.extend(u32::from(command == 5).to_le_bytes());
            if command == 5 {
                raw.extend(TARGET_CARD.to_le_bytes());
                raw.extend([0, 2]);
                raw.extend(0u32.to_le_bytes());
                raw.extend(0u64.to_le_bytes());
                raw.push(0);
            }
        }
        raw.extend([0, 0, 0]);
        raw
    }

    fn opcode24_frame() -> Vec<u8> {
        vec![24, 0, 2, 224, 255, 224, 255]
    }

    fn frozen_request() -> RunDuelRequest {
        let fixture: Value =
            serde_json::from_str(include_str!("../../../tests/fixtures/rabbit.request.json"))
                .unwrap();
        let mut request: RunDuelRequest = serde_json::from_value(json!({
            "protocol_version":2,
            "engine":{"timeout_ms":GROUND_COLLAPSE_PROBE_TIMEOUT_MS},
            "deck":fixture["deck"],
            "opening_hand":fixture["opening_hand"],
            "seed":1,
            "decisions":[],
            "versions":{
                "rules":"ocg-mr5",
                "catalog":"",
                "banlist":"",
                "engine_sha256":"446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9",
                "cdb_sha256":"c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225",
                "scripts_sha256":"69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91",
                "core_commit":CORE_COMMIT,
                "initializer":INITIALIZER_VERSION
            }
        }))
        .unwrap();
        request.deck.main[0] = ygo_domain::CardId(TARGET_CARD);
        request.opening_hand[0] = ygo_domain::CardId(TARGET_CARD);
        request
    }

    fn test_root(label: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "ground-collapse-{label}-{}-{}",
            std::process::id(),
            now().unwrap()
        ))
    }

    fn save_stage(
        batch: &GroundCollapseProbeBatch,
        stage: u8,
        request: &RunDuelRequest,
        result: Result<DuelResult, WorkerError>,
        identity: &Value,
    ) -> Value {
        let validation = result
            .as_ref()
            .map_err(|error| error.message.clone())
            .and_then(|value| validate_ground_collapse_result(request, value));
        let replay = if batch.is_replay(stage, request).unwrap() {
            let previous: Result<DuelResult, WorkerError> = serde_json::from_value(
                batch.evidence(stage - 1).unwrap().unwrap()["result"].clone(),
            )
            .unwrap();
            json!(match (&previous, &result) {
                (Ok(left), Ok(right)) => ground_collapse_replay_matches(left, right),
                _ => false,
            })
        } else {
            Value::Null
        };
        let successful = validation.is_ok()
            && result.is_ok()
            && (replay.is_null() || replay == Value::Bool(true));
        let receipt = json!({
            "schema_version":1,
            "kind":"ground_collapse_probe_stage",
            "scope":GROUND_COLLAPSE_PROBE_SCOPE,
            "context":"synthetic-context",
            "stage":stage,
            "request":request,
            "result":result,
            "validation":validation,
            "assets_before":identity,
            "assets_after":identity,
            "assets_unchanged":true,
            "independent_replay_matches":replay,
            "successful":successful,
            "diagnostic":if successful {Value::Null} else {json!("synthetic_failure")},
            "started_at":batch.started
        });
        batch.save_evidence(stage, &receipt).unwrap();
        receipt
    }

    #[test]
    fn synthetic_direct_route_charges_four_requests_and_replays_exact_response() {
        let root = test_root("direct");
        let started = now().unwrap();
        let ledger = root.join("calls.jsonl");
        let batch = GroundCollapseProbeBatch::open(&ledger, "synthetic-context", started).unwrap();
        let identity = json!({"synthetic":true});
        let initial = frozen_request();
        batch.validate_request(1, &initial).unwrap();

        let engine = SyntheticGroundEngine(Arc::new(AtomicU64::new(0)));
        let mut request = initial.clone();
        for stage in 1..=4 {
            if stage > 1 {
                let previous = batch.evidence(stage - 1).unwrap().unwrap();
                let prior_request: RunDuelRequest =
                    serde_json::from_value(previous["request"].clone()).unwrap();
                let prior_result: Result<DuelResult, WorkerError> =
                    serde_json::from_value(previous["result"].clone()).unwrap();
                request =
                    derive_next_request(stage - 1, &prior_request, &prior_result.unwrap()).unwrap();
            }
            batch.validate_request(stage, &request).unwrap();
            batch.save_assets_before(stage, &identity).unwrap();
            let result = batch.run(engine.clone(), stage, &request);
            let receipt = save_stage(&batch, stage, &request, result, &identity);
            assert_eq!(receipt["successful"], true);
        }

        let replay: Result<DuelResult, WorkerError> =
            serde_json::from_value(batch.evidence(4).unwrap().unwrap()["result"].clone()).unwrap();
        let original: Result<DuelResult, WorkerError> =
            serde_json::from_value(batch.evidence(3).unwrap().unwrap()["result"].clone()).unwrap();
        assert!(ground_collapse_replay_matches(
            &original.unwrap(),
            &replay.unwrap()
        ));
        let replay_purpose = match &batch.journal {
            ProbeJournal::Writable(journal) => journal.call_purpose(4).unwrap(),
            ProbeJournal::ReadOnly(_) => panic!("running batch must use a writable journal"),
        };
        assert_eq!(replay_purpose, CallPurpose::Replay);
        assert_eq!(batch.stats().unwrap().consumed, 4);
        assert_eq!(batch.stats().unwrap().completed, 4);
        assert_eq!(batch.stats().unwrap().unknown, 0);
        batch
            .verify_evidence(4, &batch.evidence(4).unwrap().unwrap())
            .unwrap();
        batch.verify().unwrap();
        drop(batch);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn ground_batch_rejects_tenki_scope_reuse_and_sixth_call() {
        let root = test_root("scope");
        let started = now().unwrap();
        let ledger = root.join("calls.jsonl");
        let batch = GroundCollapseProbeBatch::open(&ledger, "synthetic-context", started).unwrap();
        assert!(
            CallJournal::open(&ledger, "tenki-prompt-probe-v1", "synthetic-context", 6).is_err()
        );
        assert!(batch.validate_request(6, &frozen_request()).is_err());
        let consumed_before = batch.stats().unwrap().consumed;
        assert!(batch
            .run(
                SyntheticGroundEngine(Arc::new(AtomicU64::new(0))),
                6,
                &frozen_request()
            )
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, consumed_before);
        drop(batch);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn final_time_check_fails_before_persisting_stage_intent() {
        let root = test_root("time-check-before-intent");
        let started = now().unwrap();
        let ledger = root.join("calls.jsonl");
        let batch = GroundCollapseProbeBatch::open(&ledger, "synthetic-context", started).unwrap();
        let request = frozen_request();
        batch.validate_request(1, &request).unwrap();
        batch
            .save_assets_before(1, &json!({"synthetic":true}))
            .unwrap();
        let engine_calls = Arc::new(AtomicU64::new(0));
        let mut time_checks = 0;

        let result = batch.run_with_time_check(
            SyntheticGroundEngine(engine_calls.clone()),
            1,
            &request,
            || {
                time_checks += 1;
                if time_checks == 2 {
                    assert!(
                        batch
                            .journal
                            .checkpoint(&intent_name(1).unwrap())
                            .unwrap()
                            .is_none(),
                        "the final time check ran after the stage intent was saved"
                    );
                    return Err(fail("insufficient_window_for_request"));
                }
                Ok(())
            },
        );

        assert_eq!(
            result.unwrap_err().message,
            "insufficient_window_for_request"
        );
        assert_eq!(time_checks, 2);
        assert_eq!(engine_calls.load(Ordering::SeqCst), 0);
        assert!(batch
            .journal
            .checkpoint(&intent_name(1).unwrap())
            .unwrap()
            .is_none());
        drop(batch);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn read_only_inspection_requires_start_and_preserves_torn_ledger_bytes() {
        let root = test_root("readonly-start");
        let started = now().unwrap();
        let missing_start = root.join("missing-start.jsonl");
        let journal = CallJournal::open(
            &missing_start,
            GROUND_COLLAPSE_PROBE_SCOPE,
            "synthetic-context",
            GROUND_COLLAPSE_PROBE_LIMIT,
        )
        .unwrap();
        drop(journal);
        let before = std::fs::read(&missing_start).unwrap();
        assert_eq!(
            GroundCollapseProbeBatch::inspect_existing(
                &missing_start,
                "synthetic-context",
                started
            )
            .err()
            .unwrap()
            .code,
            "start_checkpoint_missing"
        );
        assert_eq!(std::fs::read(&missing_start).unwrap(), before);

        let torn = root.join("torn.jsonl");
        let batch = GroundCollapseProbeBatch::open(&torn, "synthetic-context", started).unwrap();
        drop(batch);
        let mut file = OpenOptions::new().append(true).open(&torn).unwrap();
        file.write_all(b"{\"torn\":").unwrap();
        file.sync_all().unwrap();
        drop(file);
        let before = std::fs::read(&torn).unwrap();
        assert!(
            GroundCollapseProbeBatch::inspect_existing(&torn, "synthetic-context", started)
                .is_err()
        );
        assert_eq!(std::fs::read(&torn).unwrap(), before);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn read_only_evidence_validation_never_creates_missing_base_checkpoint() {
        let root = test_root("readonly-base");
        let started = now().unwrap();
        let ledger = root.join("calls.jsonl");
        let batch = GroundCollapseProbeBatch::open(&ledger, "synthetic-context", started).unwrap();
        drop(batch);
        let before = std::fs::read(&ledger).unwrap();
        let batch =
            GroundCollapseProbeBatch::inspect_existing(&ledger, "synthetic-context", started)
                .unwrap();

        assert_eq!(batch.stats().unwrap().consumed, 0);
        batch.verify().unwrap();
        let receipt = json!({
            "stage": 1,
            "scope": GROUND_COLLAPSE_PROBE_SCOPE,
            "context": "synthetic-context",
            "started_at": started,
            "request": frozen_request()
        });
        assert_eq!(
            batch.verify_evidence(1, &receipt).unwrap_err().code,
            "base_request_checkpoint_missing"
        );
        assert!(batch
            .journal
            .checkpoint("immutable/ground-collapse/base-request")
            .unwrap()
            .is_none());
        assert_eq!(std::fs::read(&ledger).unwrap(), before);
        drop(batch);
        std::fs::remove_dir_all(root).unwrap();
    }
}
