use super::{
    jobs::AnalysisJobRecordV1,
    persistence::{PersistenceError, PersistentAnalysisJobStore},
    FrozenAnalysisInput,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{fs, path::PathBuf};
use ygo_search::combo::{
    SearchAttemptFfiDirection, SearchAttemptFfiReturnStatus, SearchAttemptJournalEvent,
    SearchAttemptObservation, SearchAttemptPhase, SearchAttemptResult,
};

const ZERO_HASH: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const RECEIPTS_DIR: &str = "attempt_receipts";
const MAX_RECEIPT_EVENTS: usize = 20_000;
const MAX_RECEIPT_EVENT_BYTES: u64 = 256 * 1024;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct AttemptReceiptAssetsV1 {
    pub engine_sha256: String,
    pub worker_sha256: String,
    pub cdb_sha256: String,
    pub scripts_sha256: String,
    pub engine_manifest_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct AttemptReceiptContextV1 {
    pub operation_id: String,
    pub job_id: String,
    pub running_job_revision: u64,
    pub command_sha256: String,
    pub job_input_binding_sha256: String,
    pub input_sha256: String,
    pub source_bundle_identity: Option<String>,
    pub build_record_identity: Option<String>,
    pub assets: AttemptReceiptAssetsV1,
}

impl AttemptReceiptContextV1 {
    pub(super) fn for_running_job(
        operation_id: &str,
        command_sha256: &str,
        record: &AnalysisJobRecordV1,
        input: &FrozenAnalysisInput,
    ) -> Result<Self, PersistenceError> {
        let context = Self {
            operation_id: operation_id.to_owned(),
            job_id: record.job_id().to_owned(),
            running_job_revision: record.revision(),
            command_sha256: command_sha256.to_owned(),
            job_input_binding_sha256: record.input().binding_sha256.clone(),
            input_sha256: input.identity.input_sha256.clone(),
            // These identities are produced by the offline source/build tools,
            // not by the workbench process. Keep them explicitly unknown here.
            source_bundle_identity: None,
            build_record_identity: None,
            assets: AttemptReceiptAssetsV1 {
                engine_sha256: input.identity.engine_sha256.clone(),
                worker_sha256: input.identity.worker_sha256.clone(),
                cdb_sha256: input.identity.cdb_sha256.clone(),
                scripts_sha256: input.identity.scripts_sha256.clone(),
                engine_manifest_sha256: input.identity.engine_manifest_sha256.clone(),
            },
        };
        validate_context(&context)?;
        Ok(context)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "event_type", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum AttemptReceiptEventV1 {
    Started {
        ordinal: u64,
        attempt_id: String,
        phase: SearchAttemptPhase,
    },
    HostResult {
        ordinal: u64,
        attempt_id: String,
        phase: SearchAttemptPhase,
        result: SearchAttemptResult,
        process_observation: ygo_engine_adapter::ProcessRunObservation,
    },
    FfiEntered {
        attempt_ordinal: u64,
        attempt_id: String,
        call_id: String,
        direction: SearchAttemptFfiDirection,
        name: String,
        ffi_ordinal: u64,
    },
    FfiReturned {
        attempt_ordinal: u64,
        attempt_id: String,
        call_id: String,
        status: SearchAttemptFfiReturnStatus,
        result_sha256: Option<String>,
    },
}

impl TryFrom<SearchAttemptJournalEvent> for AttemptReceiptEventV1 {
    type Error = PersistenceError;

    fn try_from(event: SearchAttemptJournalEvent) -> Result<Self, Self::Error> {
        Ok(match event {
            SearchAttemptJournalEvent::Started(start) => Self::Started {
                ordinal: start.ordinal,
                attempt_id: start.attempt_id,
                phase: start.phase,
            },
            SearchAttemptJournalEvent::Finished(observation) => Self::from_observation(observation),
            SearchAttemptJournalEvent::FfiEntered(entry) => Self::FfiEntered {
                attempt_ordinal: entry.attempt_ordinal,
                attempt_id: entry.attempt_id,
                call_id: entry.call_id,
                direction: entry.direction,
                name: entry.name,
                ffi_ordinal: entry.ffi_ordinal,
            },
            SearchAttemptJournalEvent::FfiReturned(result) => Self::FfiReturned {
                attempt_ordinal: result.attempt_ordinal,
                attempt_id: result.attempt_id,
                call_id: result.call_id,
                status: result.status,
                result_sha256: result.result_sha256,
            },
        })
    }
}

impl AttemptReceiptEventV1 {
    fn from_observation(observation: SearchAttemptObservation) -> Self {
        Self::HostResult {
            ordinal: observation.ordinal,
            attempt_id: observation.attempt_id,
            phase: observation.phase,
            result: observation.result,
            process_observation: observation.process_observation,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct AttemptReceiptEnvelopeV1 {
    pub schema_version: u16,
    pub kind: String,
    pub context: AttemptReceiptContextV1,
    pub context_sha256: String,
    pub sequence: u64,
    pub previous_sha256: String,
    pub event: AttemptReceiptEventV1,
    pub event_sha256: String,
}

impl PersistentAnalysisJobStore {
    pub(super) fn append_attempt_receipt(
        &self,
        context: &AttemptReceiptContextV1,
        event: AttemptReceiptEventV1,
    ) -> Result<(), PersistenceError> {
        validate_context(context)?;
        let history = self.read_attempt_receipts(&context.job_id)?;
        validate_next_event(&history, context, &event)?;
        if history.len() >= MAX_RECEIPT_EVENTS {
            return Err(PersistenceError::InvalidChain);
        }
        let sequence = history.len() as u64 + 1;
        let previous_sha256 = history
            .last()
            .map(|receipt| receipt.event_sha256.clone())
            .unwrap_or_else(|| ZERO_HASH.to_owned());
        let context_sha256 = context_digest(context)?;
        let event_sha256 = event_digest(&context_sha256, sequence, &previous_sha256, &event)?;
        let envelope = AttemptReceiptEnvelopeV1 {
            schema_version: 1,
            kind: "w1c_search_attempt_journal_event".into(),
            context: context.clone(),
            context_sha256,
            sequence,
            previous_sha256,
            event,
            event_sha256,
        };
        let bytes =
            serde_json::to_vec_pretty(&envelope).map_err(|_| PersistenceError::RecordInvalid)?;
        if bytes.len() as u64 > MAX_RECEIPT_EVENT_BYTES {
            return Err(PersistenceError::RecordInvalid);
        }
        let dir = self.attempt_receipt_dir(&context.job_id);
        ygo_storage::prepare_store_directory(&dir).map_err(|_| PersistenceError::InvalidPath)?;
        let path = dir.join(format!("{sequence}.json"));
        #[cfg(test)]
        self.fail_attempt_receipt_before_publish()?;
        ygo_storage::publish_exclusive_file(&path, &bytes).map_err(|error| {
            if error.starts_with("store_commit_uncertain:") || path.exists() {
                PersistenceError::CommitUncertain
            } else if error.contains("already exists") || error.contains("File exists") {
                PersistenceError::RevisionConflict
            } else {
                PersistenceError::Io
            }
        })?;

        // If the caller cannot prove the new bytes were committed, leave the
        // evidence in place and prevent any later adapter call.
        #[cfg(test)]
        self.fail_attempt_receipt_after_publish()?;

        let reread = self
            .read_attempt_receipts(&context.job_id)
            .map_err(|_| PersistenceError::CommitUncertain)?;
        if reread.last() != Some(&envelope) {
            return Err(PersistenceError::CommitUncertain);
        }
        Ok(())
    }

    pub(super) fn read_attempt_receipts(
        &self,
        job_id: &str,
    ) -> Result<Vec<AttemptReceiptEnvelopeV1>, PersistenceError> {
        if !valid_id(job_id) {
            return Err(PersistenceError::InvalidChain);
        }
        let dir = self.attempt_receipt_dir(job_id);
        if !dir.exists() {
            return Ok(Vec::new());
        }
        let metadata =
            ygo_storage::safe_store_metadata(&dir).map_err(|_| PersistenceError::InvalidPath)?;
        if !metadata.is_dir() {
            return Err(PersistenceError::InvalidPath);
        }
        let mut files = Vec::new();
        for entry in fs::read_dir(&dir).map_err(|_| PersistenceError::Io)? {
            let entry = entry.map_err(|_| PersistenceError::Io)?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| PersistenceError::InvalidPath)?;
            let metadata = ygo_storage::safe_store_metadata(&entry.path())
                .map_err(|_| PersistenceError::InvalidPath)?;
            if !metadata.is_file() || metadata.len() > MAX_RECEIPT_EVENT_BYTES {
                return Err(PersistenceError::InvalidPath);
            }
            let sequence = name
                .strip_suffix(".json")
                .and_then(|text| text.parse::<u64>().ok())
                .filter(|sequence| *sequence > 0)
                .ok_or(PersistenceError::InvalidChain)?;
            if name != format!("{sequence}.json") {
                return Err(PersistenceError::InvalidChain);
            }
            files.push((sequence, entry.path()));
            if files.len() > MAX_RECEIPT_EVENTS {
                return Err(PersistenceError::InvalidChain);
            }
        }
        files.sort_by_key(|(sequence, _)| *sequence);
        if files
            .iter()
            .enumerate()
            .any(|(index, (sequence, _))| *sequence != index as u64 + 1)
        {
            return Err(PersistenceError::InvalidChain);
        }

        let mut history = Vec::with_capacity(files.len());
        for (sequence, path) in files {
            let bytes = fs::read(path).map_err(|_| PersistenceError::Io)?;
            let value = super::jobs::strict_json_value(&bytes)
                .map_err(|_| PersistenceError::InvalidChain)?;
            let envelope: AttemptReceiptEnvelopeV1 = serde_json::from_value(value.clone())
                .map_err(|_| PersistenceError::InvalidChain)?;
            let shape =
                serde_json::to_value(&envelope).map_err(|_| PersistenceError::InvalidChain)?;
            if !super::jobs::same_shape(&value, &shape)
                || envelope.schema_version != 1
                || envelope.kind != "w1c_search_attempt_journal_event"
                || envelope.sequence != sequence
            {
                return Err(PersistenceError::InvalidChain);
            }
            history.push(envelope);
        }
        validate_history(&history, job_id)?;
        Ok(history)
    }

    fn attempt_receipt_dir(&self, job_id: &str) -> PathBuf {
        self.root.join("jobs").join(job_id).join(RECEIPTS_DIR)
    }
}

pub(super) fn validate_receipt_binding(
    context: &AttemptReceiptContextV1,
    operation_id: &str,
    command_sha256: &str,
    job: &AnalysisJobRecordV1,
) -> Result<(), PersistenceError> {
    validate_context(context)?;
    let identity = &job.input().identity;
    if context.operation_id != operation_id
        || context.job_id != job.job_id()
        || context.command_sha256 != command_sha256
        || context.job_input_binding_sha256 != job.input().binding_sha256
        || context.input_sha256 != identity.input_sha256
        || context.assets.engine_sha256 != identity.engine_sha256
        || context.assets.worker_sha256 != identity.worker_sha256
        || context.assets.cdb_sha256 != identity.cdb_sha256
        || context.assets.scripts_sha256 != identity.scripts_sha256
        || context.assets.engine_manifest_sha256 != identity.engine_manifest_sha256
    {
        return Err(PersistenceError::InvalidChain);
    }
    Ok(())
}

fn validate_history(
    history: &[AttemptReceiptEnvelopeV1],
    job_id: &str,
) -> Result<(), PersistenceError> {
    let mut previous_sha256 = ZERO_HASH.to_owned();
    let mut context: Option<&AttemptReceiptContextV1> = None;
    let mut context_sha256 = None;
    let mut pending: Option<(u64, String, SearchAttemptPhase)> = None;
    let mut ffi_calls = std::collections::BTreeMap::<String, bool>::new();
    let mut ffi_stack = Vec::<String>::new();
    let mut ffi_ordinal = 0;
    let mut next_ordinal = 1;
    let mut seen = std::collections::BTreeSet::new();
    let mut seen_ffi_call_ids = std::collections::BTreeSet::new();

    for (index, receipt) in history.iter().enumerate() {
        validate_context(&receipt.context)?;
        if receipt.context.job_id != job_id
            || receipt.sequence != index as u64 + 1
            || receipt.previous_sha256 != previous_sha256
        {
            return Err(PersistenceError::InvalidChain);
        }
        let expected_context = context_digest(&receipt.context)?;
        if receipt.context_sha256 != expected_context
            || context.is_some_and(|existing| existing != &receipt.context)
            || context_sha256
                .as_ref()
                .is_some_and(|existing| existing != &receipt.context_sha256)
        {
            return Err(PersistenceError::InvalidChain);
        }
        match &receipt.event {
            AttemptReceiptEventV1::Started {
                ordinal,
                attempt_id,
                phase,
            } => {
                if pending.is_some()
                    || *ordinal != next_ordinal
                    || !valid_id(attempt_id)
                    || !seen.insert(attempt_id.clone())
                {
                    return Err(PersistenceError::InvalidChain);
                }
                pending = Some((*ordinal, attempt_id.clone(), *phase));
                next_ordinal += 1;
                ffi_calls.clear();
                ffi_stack.clear();
                ffi_ordinal = 0;
            }
            AttemptReceiptEventV1::HostResult {
                ordinal,
                attempt_id,
                phase,
                ..
            } => {
                if pending.as_ref() != Some(&(*ordinal, attempt_id.clone(), *phase))
                    || ffi_calls.values().any(|returned| !returned)
                    || !ffi_stack.is_empty()
                {
                    return Err(PersistenceError::InvalidChain);
                }
                pending = None;
                ffi_calls.clear();
                ffi_stack.clear();
                ffi_ordinal = 0;
            }
            AttemptReceiptEventV1::FfiEntered {
                attempt_ordinal,
                attempt_id,
                call_id,
                name,
                ffi_ordinal: entry_ordinal,
                ..
            } => {
                if !pending_matches(pending.as_ref(), *attempt_ordinal, attempt_id)
                    || !valid_id(attempt_id)
                    || !valid_id(call_id)
                    || !valid_ffi_name(name)
                    || ffi_calls.contains_key(call_id)
                    || !seen_ffi_call_ids.insert(call_id.clone())
                    || *entry_ordinal != ffi_ordinal + 1
                {
                    return Err(PersistenceError::InvalidChain);
                }
                ffi_ordinal = *entry_ordinal;
                ffi_calls.insert(call_id.clone(), false);
                ffi_stack.push(call_id.clone());
            }
            AttemptReceiptEventV1::FfiReturned {
                attempt_ordinal,
                attempt_id,
                call_id,
                result_sha256,
                ..
            } => {
                if !pending_matches(pending.as_ref(), *attempt_ordinal, attempt_id)
                    || !valid_id(call_id)
                    || !ffi_calls.get(call_id).is_some_and(|returned| !returned)
                    || ffi_stack.last() != Some(call_id)
                    || result_sha256
                        .as_deref()
                        .is_some_and(|hash| !valid_hash(hash))
                {
                    return Err(PersistenceError::InvalidChain);
                }
                ffi_calls.insert(call_id.clone(), true);
                ffi_stack.pop();
            }
        }
        let expected_event = event_digest(
            &receipt.context_sha256,
            receipt.sequence,
            &receipt.previous_sha256,
            &receipt.event,
        )?;
        if receipt.event_sha256 != expected_event || !valid_hash(&receipt.event_sha256) {
            return Err(PersistenceError::InvalidChain);
        }
        context = Some(&receipt.context);
        context_sha256 = Some(receipt.context_sha256.clone());
        previous_sha256 = receipt.event_sha256.clone();
    }
    Ok(())
}

fn validate_next_event(
    history: &[AttemptReceiptEnvelopeV1],
    context: &AttemptReceiptContextV1,
    event: &AttemptReceiptEventV1,
) -> Result<(), PersistenceError> {
    validate_history(history, &context.job_id)?;
    if history
        .first()
        .is_some_and(|receipt| receipt.context != *context)
    {
        return Err(PersistenceError::InvalidChain);
    }
    let mut pending: Option<(u64, String, SearchAttemptPhase)> = None;
    let mut ffi_calls = std::collections::BTreeMap::<String, bool>::new();
    let mut ffi_stack = Vec::<String>::new();
    let mut ffi_ordinal = 0;
    for receipt in history {
        match &receipt.event {
            AttemptReceiptEventV1::Started {
                ordinal,
                attempt_id,
                phase,
            } => {
                pending = Some((*ordinal, attempt_id.clone(), *phase));
                ffi_calls.clear();
                ffi_stack.clear();
                ffi_ordinal = 0;
            }
            AttemptReceiptEventV1::FfiEntered {
                attempt_id,
                call_id,
                ffi_ordinal: entry_ordinal,
                ..
            } => {
                if pending.as_ref().map_or(true, |(_, id, _)| id != attempt_id)
                    || ffi_calls.contains_key(call_id)
                    || *entry_ordinal != ffi_ordinal + 1
                {
                    return Err(PersistenceError::InvalidChain);
                }
                ffi_ordinal = *entry_ordinal;
                ffi_calls.insert(call_id.clone(), false);
                ffi_stack.push(call_id.clone());
            }
            AttemptReceiptEventV1::FfiReturned { call_id, .. } => {
                if !ffi_calls.get(call_id).is_some_and(|returned| !returned)
                    || ffi_stack.last() != Some(call_id)
                {
                    return Err(PersistenceError::InvalidChain);
                }
                ffi_calls.insert(call_id.clone(), true);
                ffi_stack.pop();
            }
            AttemptReceiptEventV1::HostResult { .. } => {
                pending = None;
                ffi_calls.clear();
                ffi_stack.clear();
                ffi_ordinal = 0;
            }
        }
    }
    let previous_ordinal = history
        .iter()
        .filter_map(|receipt| match receipt.event {
            AttemptReceiptEventV1::Started { ordinal, .. } => Some(ordinal),
            _ => None,
        })
        .next_back()
        .unwrap_or(0);
    match event {
        AttemptReceiptEventV1::Started {
            ordinal,
            attempt_id,
            ..
        } if pending.is_none()
            && *ordinal == previous_ordinal + 1
            && valid_id(attempt_id)
            && !history.iter().any(|receipt| {
                matches!(&receipt.event,
                    AttemptReceiptEventV1::Started { attempt_id: existing, .. }
                    | AttemptReceiptEventV1::HostResult { attempt_id: existing, .. }
                    if existing == attempt_id)
            }) =>
        {
            Ok(())
        }
        AttemptReceiptEventV1::HostResult {
            ordinal,
            attempt_id,
            phase,
            ..
        } if pending.as_ref() == Some(&(*ordinal, attempt_id.clone(), *phase))
            && ffi_calls.values().all(|returned| *returned)
            && ffi_stack.is_empty() =>
        {
            Ok(())
        }
        AttemptReceiptEventV1::FfiEntered {
            attempt_ordinal,
            attempt_id,
            call_id,
            name,
            ffi_ordinal: entry_ordinal,
            ..
        } if pending
            .as_ref()
            .is_some_and(|(ordinal, id, _)| *ordinal == *attempt_ordinal && id == attempt_id)
            && valid_id(call_id)
            && valid_ffi_name(name)
            && !ffi_calls.contains_key(call_id)
            && !history.iter().any(|receipt| {
                matches!(&receipt.event,
                    AttemptReceiptEventV1::FfiEntered { call_id: existing, .. }
                    if existing == call_id)
            })
            && *entry_ordinal == ffi_ordinal + 1 =>
        {
            Ok(())
        }
        AttemptReceiptEventV1::FfiReturned {
            attempt_ordinal,
            attempt_id,
            call_id,
            result_sha256,
            ..
        } if pending
            .as_ref()
            .is_some_and(|(ordinal, id, _)| *ordinal == *attempt_ordinal && id == attempt_id)
            && ffi_calls.get(call_id).is_some_and(|returned| !returned)
            && ffi_stack.last() == Some(call_id)
            && result_sha256.as_deref().map_or(true, valid_hash) =>
        {
            Ok(())
        }
        _ => Err(PersistenceError::InvalidChain),
    }
}

fn validate_context(context: &AttemptReceiptContextV1) -> Result<(), PersistenceError> {
    if !valid_id(&context.operation_id)
        || !valid_id(&context.job_id)
        || context.running_job_revision < 2
        || !valid_hash(&context.command_sha256)
        || !valid_hash(&context.job_input_binding_sha256)
        || !valid_hash(&context.input_sha256)
        || context
            .source_bundle_identity
            .as_deref()
            .is_some_and(|value| !valid_hash(value))
        || context
            .build_record_identity
            .as_deref()
            .is_some_and(|value| !valid_hash(value))
        || !valid_hash(&context.assets.engine_sha256)
        || !valid_hash(&context.assets.worker_sha256)
        || !valid_hash(&context.assets.cdb_sha256)
        || !valid_hash(&context.assets.scripts_sha256)
        || !valid_hash(&context.assets.engine_manifest_sha256)
    {
        return Err(PersistenceError::InvalidChain);
    }
    Ok(())
}

fn context_digest(context: &AttemptReceiptContextV1) -> Result<String, PersistenceError> {
    let value = serde_json::to_value(context).map_err(|_| PersistenceError::RecordInvalid)?;
    let bytes = serde_json::to_vec(&value).map_err(|_| PersistenceError::RecordInvalid)?;
    Ok(ygo_storage::hash(&bytes))
}

fn event_digest(
    context_sha256: &str,
    sequence: u64,
    previous_sha256: &str,
    event: &AttemptReceiptEventV1,
) -> Result<String, PersistenceError> {
    let event = serde_json::to_value(event).map_err(|_| PersistenceError::RecordInvalid)?;
    let body: Value = json!({
        "context_sha256": context_sha256,
        "sequence": sequence,
        "previous_sha256": previous_sha256,
        "event": event,
    });
    let bytes = serde_json::to_vec(&body).map_err(|_| PersistenceError::RecordInvalid)?;
    Ok(ygo_storage::hash(&bytes))
}

fn valid_id(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn pending_matches(
    pending: Option<&(u64, String, SearchAttemptPhase)>,
    ordinal: u64,
    attempt_id: &str,
) -> bool {
    match pending {
        Some((pending_ordinal, pending_id, _)) => {
            *pending_ordinal == ordinal && pending_id == attempt_id
        }
        None => false,
    }
}

fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_ffi_name(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_alphabetic())
        && value.len() <= 64
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disk_history_rejects_ffi_call_id_reused_by_a_later_attempt() {
        let context = AttemptReceiptContextV1 {
            operation_id: "1".repeat(32),
            job_id: "2".repeat(32),
            running_job_revision: 2,
            command_sha256: "3".repeat(64),
            job_input_binding_sha256: "4".repeat(64),
            input_sha256: "5".repeat(64),
            source_bundle_identity: None,
            build_record_identity: None,
            assets: AttemptReceiptAssetsV1 {
                engine_sha256: "6".repeat(64),
                worker_sha256: "7".repeat(64),
                cdb_sha256: "8".repeat(64),
                scripts_sha256: "9".repeat(64),
                engine_manifest_sha256: "a".repeat(64),
            },
        };
        let context_sha256 = context_digest(&context).unwrap();
        let mut previous_sha256 = ZERO_HASH.to_owned();
        let call_id = "b".repeat(32);
        let mut events = vec![
            AttemptReceiptEventV1::Started {
                ordinal: 1,
                attempt_id: "c".repeat(32),
                phase: SearchAttemptPhase::Initial,
            },
            AttemptReceiptEventV1::FfiEntered {
                attempt_ordinal: 1,
                attempt_id: "c".repeat(32),
                call_id: call_id.clone(),
                direction: SearchAttemptFfiDirection::HostToOcgcore,
                name: "OCG_DuelProcess".into(),
                ffi_ordinal: 1,
            },
            AttemptReceiptEventV1::FfiReturned {
                attempt_ordinal: 1,
                attempt_id: "c".repeat(32),
                call_id: call_id.clone(),
                status: SearchAttemptFfiReturnStatus::Returned,
                result_sha256: None,
            },
            AttemptReceiptEventV1::HostResult {
                ordinal: 1,
                attempt_id: "c".repeat(32),
                phase: SearchAttemptPhase::Initial,
                result: SearchAttemptResult::DuelResult {
                    status: ygo_engine_adapter::DuelStatus::Failed,
                },
                process_observation: ygo_engine_adapter::ProcessRunObservation::default(),
            },
            AttemptReceiptEventV1::Started {
                ordinal: 2,
                attempt_id: "d".repeat(32),
                phase: SearchAttemptPhase::Replay,
            },
            AttemptReceiptEventV1::FfiEntered {
                attempt_ordinal: 2,
                attempt_id: "d".repeat(32),
                call_id,
                direction: SearchAttemptFfiDirection::HostToOcgcore,
                name: "OCG_DuelProcess".into(),
                ffi_ordinal: 1,
            },
        ];
        let history = events
            .drain(..)
            .enumerate()
            .map(|(index, event)| {
                let sequence = index as u64 + 1;
                let event_sha256 =
                    event_digest(&context_sha256, sequence, &previous_sha256, &event).unwrap();
                let envelope = AttemptReceiptEnvelopeV1 {
                    schema_version: 1,
                    kind: "w1c_search_attempt_journal_event".into(),
                    context: context.clone(),
                    context_sha256: context_sha256.clone(),
                    sequence,
                    previous_sha256: previous_sha256.clone(),
                    event,
                    event_sha256: event_sha256.clone(),
                };
                previous_sha256 = event_sha256;
                envelope
            })
            .collect::<Vec<_>>();

        assert_eq!(history.len(), 6);
        assert!(validate_history(&history, &context.job_id).is_err());
    }
}
