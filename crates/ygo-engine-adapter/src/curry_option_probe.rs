//! Fixed-scope Mooyan Curry prompt and recovery validation.
use crate::{CallPurpose, Checkpoint, Choice, CoreEventFrame, LedgerStats, Prompt, WorkerError};
use serde_json::json;

pub const CURRY_OPTION_SCOPE: &str = "curry-option-validation-v1";
pub const CURRY_OPTION_CONFIRMATION_SCOPE: &str = "curry-option-confirmation-v1";
pub const CURRY_OPTION_VERIFICATION_SCOPE: &str = "curry-option-verification-v1";
pub const CURRY_OPERATIONS_SOURCE_SHA256: &str =
    "b46cf0d53825cb662af319a7382015b555422aa11903067445c994c4b0c8a990";
const OPTION_DESCRIPTIONS: [u64; 2] = [60_895_602_409_472, 60_895_602_409_473];

fn curry_fail(message: &str) -> WorkerError {
    WorkerError::new("curry_option_gate", "curry_option_probe", message)
}

pub fn curry_option_purpose(stage: u8) -> Result<CallPurpose, WorkerError> {
    match stage {
        1..=3 => Ok(CallPurpose::Probe),
        4 | 6 => Ok(CallPurpose::Execution),
        5 | 7 => Ok(CallPurpose::Replay),
        _ => Err(curry_fail("stage outside fixed seven-call scope")),
    }
}

pub fn validate_curry_option_slot(stage: u8, stats: &LedgerStats) -> Result<(), WorkerError> {
    curry_option_purpose(stage)?;
    if stats.limit != 7
        || stats.consumed != stage as usize - 1
        || stats.completed != stats.consumed
        || stats.unknown != 0
        || stats.reserved != 0
        || stats.abandoned != 0
    {
        return Err(curry_fail(
            "ledger prefix is not the exact settled predecessor",
        ));
    }
    Ok(())
}

/// Independently validate the fixed opcode14 raw frame and its ordered responses.
pub fn validate_curry_option_prompt(frame: &CoreEventFrame, prompt: &Prompt) -> Result<(), String> {
    let raw = &frame.raw;
    if !frame.supported
        || frame.opcode != 14
        || raw.len() != 19
        || raw[..3] != [14, 0, 2]
        || prompt.opcode != 14
        || prompt.player != 0
        || frame.fields.get("prompt")
            != Some(&serde_json::to_value(prompt).map_err(|_| "prompt encoding")?)
    {
        return Err("frozen Curry opcode14 envelope differs".into());
    }
    let descriptions = [
        u64::from_le_bytes(raw[3..11].try_into().map_err(|_| "first option width")?),
        u64::from_le_bytes(raw[11..19].try_into().map_err(|_| "second option width")?),
    ];
    if descriptions != OPTION_DESCRIPTIONS || prompt.actions.len() != 2 {
        return Err("frozen Curry option descriptions differ".into());
    }
    for (index, action) in prompt.actions.iter().enumerate() {
        let mut expected = vec![0, 0, 0, 0];
        expected[0] = index as u8;
        if action.choice
            != (Choice::Option {
                index: index as u32,
            })
            || action.bytes != expected
            || !action.card_ids.is_empty()
        {
            return Err("Curry option response order or bytes differ".into());
        }
    }
    Ok(())
}

/// Validate exactly one raw RECOVER event and its matching fixed-prefix LP result.
/// The response player is selected by the option index in this candidate only.
pub fn validate_curry_recover_result(
    option: u8,
    option_prompt_sequence: u64,
    events: &[CoreEventFrame],
    checkpoint: &Checkpoint,
) -> Result<(), String> {
    if option > 1
        || events
            .windows(2)
            .any(|pair| pair[0].sequence >= pair[1].sequence)
    {
        return Err("Curry recovery option or event order differs".into());
    }
    let mut recoveries = Vec::new();
    for event in events {
        if !event.supported || event.raw.first().copied() != Some(event.opcode) {
            return Err("unsupported or inconsistent event in Curry prefix".into());
        }
        if event.opcode == 16 {
            let raw = &event.raw;
            if raw.len() != 16
                || raw.first().copied() != Some(16)
                || raw.get(2).copied() != Some(0)
                || raw.get(3).copied() != Some(0)
                || u32::from_le_bytes(
                    raw[12..16]
                        .try_into()
                        .map_err(|_| "Curry chain count width")?,
                ) != 0
            {
                return Err("Curry prefix contains forced or nonempty chain".into());
            }
        }
        if event.opcode == 92 {
            let raw = &event.raw;
            if raw.len() != 6 {
                return Err("RECOVER raw frame length differs".into());
            }
            let player = raw[1];
            let amount =
                u32::from_le_bytes(raw[2..6].try_into().map_err(|_| "RECOVER amount width")?);
            if player > 1 || event.fields != json!({"player": player, "amount": amount}) {
                return Err("RECOVER fields differ from raw bytes".into());
            }
            recoveries.push((event.sequence, player, amount));
        }
    }
    let player = option;
    let expected_lp = if player == 0 {
        [8200, 8000]
    } else {
        [8000, 8200]
    };
    if recoveries.len() != 1
        || recoveries[0].0 <= option_prompt_sequence
        || recoveries[0].1 != player
        || recoveries[0].2 != 200
        || checkpoint.lp != expected_lp
    {
        return Err("Curry recovery event or LP checkpoint differs".into());
    }
    Ok(())
}
