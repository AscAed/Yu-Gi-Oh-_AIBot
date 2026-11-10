use super::{
    jobs::AnalysisJobRecordV1,
    persistence::{is_unpublished_store_file, PersistenceError, PersistentAnalysisJobStore},
    FrozenAnalysisInput,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::PathBuf,
};
use ygo_search::combo::{
    SearchAttemptFfiDirection, SearchAttemptFfiReturnStatus, SearchAttemptJournalEvent,
    SearchAttemptObservation, SearchAttemptPhase, SearchAttemptResult,
};

const ZERO_HASH: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const RECEIPTS_DIR: &str = "attempt_receipts";
const RECEIPT_SEGMENT_EVENTS: u64 = 4_096;
const LEGACY_FLAT_RECEIPT_EVENTS: u64 = 20_000;
const MAX_RECEIPT_EVENT_BYTES: u64 = 256 * 1024;

fn receipt_event_path(dir: &std::path::Path, sequence: u64) -> PathBuf {
    if sequence <= RECEIPT_SEGMENT_EVENTS {
        dir.join(format!("{sequence}.json"))
    } else {
        let segment = (sequence - 1) / RECEIPT_SEGMENT_EVENTS;
        dir.join("segments")
            .join(format!("segment-{segment:08}"))
            .join(format!("{sequence}.json"))
    }
}

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

pub(super) struct AttemptReceiptAppendState {
    sequence: u64,
    previous_sha256: String,
    context: Option<AttemptReceiptContextV1>,
    context_sha256: Option<String>,
    pending: Option<(u64, String, SearchAttemptPhase)>,
    ffi_calls: BTreeMap<String, bool>,
    ffi_stack: Vec<String>,
    ffi_ordinal: u64,
    next_ordinal: u64,
    seen_attempt_ids: BTreeSet<String>,
    seen_ffi_call_ids: BTreeSet<String>,
}

impl AttemptReceiptAppendState {
    fn empty() -> Self {
        Self {
            sequence: 0,
            previous_sha256: ZERO_HASH.to_owned(),
            context: None,
            context_sha256: None,
            pending: None,
            ffi_calls: BTreeMap::new(),
            ffi_stack: Vec::new(),
            ffi_ordinal: 0,
            next_ordinal: 1,
            seen_attempt_ids: BTreeSet::new(),
            seen_ffi_call_ids: BTreeSet::new(),
        }
    }

    fn from_history(
        history: &[AttemptReceiptEnvelopeV1],
        job_id: &str,
    ) -> Result<Self, PersistenceError> {
        let mut state = Self::empty();
        for receipt in history {
            if receipt.context.job_id != job_id {
                return Err(PersistenceError::InvalidChain);
            }
            state.append(receipt)?;
        }
        Ok(state)
    }

    fn validate_next(
        &self,
        context: &AttemptReceiptContextV1,
        event: &AttemptReceiptEventV1,
    ) -> Result<(), PersistenceError> {
        validate_context(context)?;
        let next_context_sha256 = context_digest(context)?;
        if self
            .context
            .as_ref()
            .is_some_and(|existing| existing != context)
            || self
                .context_sha256
                .as_ref()
                .is_some_and(|existing| existing != &next_context_sha256)
        {
            return Err(PersistenceError::InvalidChain);
        }
        let valid = match event {
            AttemptReceiptEventV1::Started {
                ordinal,
                attempt_id,
                ..
            } => {
                self.pending.is_none()
                    && *ordinal == self.next_ordinal
                    && valid_id(attempt_id)
                    && !self.seen_attempt_ids.contains(attempt_id)
            }
            AttemptReceiptEventV1::HostResult {
                ordinal,
                attempt_id,
                phase,
                ..
            } => {
                self.pending.as_ref() == Some(&(*ordinal, attempt_id.clone(), *phase))
                    && self.ffi_calls.values().all(|returned| *returned)
                    && self.ffi_stack.is_empty()
            }
            AttemptReceiptEventV1::FfiEntered {
                attempt_ordinal,
                attempt_id,
                call_id,
                name,
                ffi_ordinal,
                ..
            } => {
                pending_matches(self.pending.as_ref(), *attempt_ordinal, attempt_id)
                    && valid_id(attempt_id)
                    && valid_id(call_id)
                    && valid_ffi_name(name)
                    && !self.ffi_calls.contains_key(call_id)
                    && !self.seen_ffi_call_ids.contains(call_id)
                    && *ffi_ordinal == self.ffi_ordinal + 1
            }
            AttemptReceiptEventV1::FfiReturned {
                attempt_ordinal,
                attempt_id,
                call_id,
                result_sha256,
                ..
            } => {
                pending_matches(self.pending.as_ref(), *attempt_ordinal, attempt_id)
                    && valid_id(call_id)
                    && self
                        .ffi_calls
                        .get(call_id)
                        .is_some_and(|returned| !returned)
                    && self.ffi_stack.last() == Some(call_id)
                    && result_sha256.as_deref().map_or(true, valid_hash)
            }
        };
        if valid {
            Ok(())
        } else {
            Err(PersistenceError::InvalidChain)
        }
    }

    fn append(&mut self, envelope: &AttemptReceiptEnvelopeV1) -> Result<(), PersistenceError> {
        let expected_sequence = self
            .sequence
            .checked_add(1)
            .ok_or(PersistenceError::InvalidChain)?;
        let context_sha256 = context_digest(&envelope.context)?;
        if envelope.schema_version != 1
            || envelope.kind != "w1c_search_attempt_journal_event"
            || envelope.sequence != expected_sequence
            || envelope.previous_sha256 != self.previous_sha256
            || envelope.context_sha256 != context_sha256
            || envelope.event_sha256
                != event_digest(
                    &context_sha256,
                    envelope.sequence,
                    &envelope.previous_sha256,
                    &envelope.event,
                )?
        {
            return Err(PersistenceError::InvalidChain);
        }
        self.validate_next(&envelope.context, &envelope.event)?;
        match &envelope.event {
            AttemptReceiptEventV1::Started {
                ordinal,
                attempt_id,
                phase,
            } => {
                self.pending = Some((*ordinal, attempt_id.clone(), *phase));
                self.next_ordinal += 1;
                self.seen_attempt_ids.insert(attempt_id.clone());
                self.ffi_calls.clear();
                self.ffi_stack.clear();
                self.ffi_ordinal = 0;
            }
            AttemptReceiptEventV1::HostResult { .. } => {
                self.pending = None;
                self.ffi_calls.clear();
                self.ffi_stack.clear();
                self.ffi_ordinal = 0;
            }
            AttemptReceiptEventV1::FfiEntered {
                call_id,
                ffi_ordinal,
                ..
            } => {
                self.ffi_ordinal = *ffi_ordinal;
                self.ffi_calls.insert(call_id.clone(), false);
                self.ffi_stack.push(call_id.clone());
                self.seen_ffi_call_ids.insert(call_id.clone());
            }
            AttemptReceiptEventV1::FfiReturned { call_id, .. } => {
                self.ffi_calls.insert(call_id.clone(), true);
                self.ffi_stack.pop();
            }
        }
        self.sequence = envelope.sequence;
        self.previous_sha256 = envelope.event_sha256.clone();
        self.context = Some(envelope.context.clone());
        self.context_sha256 = Some(context_sha256);
        Ok(())
    }
}

impl PersistentAnalysisJobStore {
    pub(super) fn append_attempt_receipt(
        &self,
        context: &AttemptReceiptContextV1,
        event: AttemptReceiptEventV1,
    ) -> Result<(), PersistenceError> {
        validate_context(context)?;
        let mut states = self
            .attempt_receipt_states
            .lock()
            .map_err(|_| PersistenceError::CommitUncertain)?;
        if !states.contains_key(&context.job_id) {
            let history = self.read_attempt_receipts(&context.job_id)?;
            let state = AttemptReceiptAppendState::from_history(&history, &context.job_id)?;
            states.insert(context.job_id.clone(), state);
        }
        let state = states
            .get(&context.job_id)
            .ok_or(PersistenceError::CommitUncertain)?;
        state.validate_next(context, &event)?;
        let sequence = state
            .sequence
            .checked_add(1)
            .ok_or(PersistenceError::InvalidChain)?;
        let previous_sha256 = state.previous_sha256.clone();
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
        let path = receipt_event_path(&dir, sequence);
        ygo_storage::prepare_store_directory(path.parent().ok_or(PersistenceError::InvalidPath)?)
            .map_err(|_| PersistenceError::InvalidPath)?;
        #[cfg(test)]
        self.fail_attempt_receipt_before_publish()?;
        if let Err(error) = ygo_storage::publish_exclusive_file(&path, &bytes) {
            let persistence_error = if error.starts_with("store_commit_uncertain:") || path.exists()
            {
                PersistenceError::CommitUncertain
            } else if error.contains("already exists") || error.contains("File exists") {
                PersistenceError::RevisionConflict
            } else {
                PersistenceError::Io
            };
            if persistence_error == PersistenceError::CommitUncertain {
                states.remove(&context.job_id);
            }
            return Err(persistence_error);
        }

        // An uncertain post-publish result invalidates the in-memory tail; the
        // next open must authenticate the durable chain again.
        #[cfg(test)]
        if let Err(error) = self.fail_attempt_receipt_after_publish() {
            states.remove(&context.job_id);
            return Err(error);
        }

        let published_file_is_safe = matches!(
            ygo_storage::safe_store_metadata(&path),
            Ok(metadata)
                if metadata.is_file() && metadata.len() <= MAX_RECEIPT_EVENT_BYTES
        );
        if !published_file_is_safe {
            states.remove(&context.job_id);
            return Err(PersistenceError::CommitUncertain);
        }
        let reread = match fs::read(&path) {
            Ok(reread) => reread,
            Err(_) => {
                states.remove(&context.job_id);
                return Err(PersistenceError::CommitUncertain);
            }
        };
        if reread != bytes {
            states.remove(&context.job_id);
            return Err(PersistenceError::CommitUncertain);
        }
        let append_result = states
            .get_mut(&context.job_id)
            .ok_or(PersistenceError::CommitUncertain)?
            .append(&envelope);
        if append_result.is_err() {
            states.remove(&context.job_id);
            return Err(PersistenceError::CommitUncertain);
        }
        Ok(())
    }

    pub(super) fn read_attempt_receipts(
        &self,
        job_id: &str,
    ) -> Result<Vec<AttemptReceiptEnvelopeV1>, PersistenceError> {
        #[cfg(test)]
        self.attempt_receipt_history_reads
            .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
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
            if name == "segments" {
                if !metadata.is_dir() {
                    return Err(PersistenceError::InvalidPath);
                }
                for segment_entry in fs::read_dir(entry.path()).map_err(|_| PersistenceError::Io)? {
                    let segment_entry = segment_entry.map_err(|_| PersistenceError::Io)?;
                    let segment_name = segment_entry
                        .file_name()
                        .into_string()
                        .map_err(|_| PersistenceError::InvalidPath)?;
                    let segment_metadata = ygo_storage::safe_store_metadata(&segment_entry.path())
                        .map_err(|_| PersistenceError::InvalidPath)?;
                    let segment = segment_name
                        .strip_prefix("segment-")
                        .and_then(|text| text.parse::<u64>().ok())
                        .filter(|segment| *segment > 0)
                        .ok_or(PersistenceError::InvalidChain)?;
                    if segment_name != format!("segment-{segment:08}") || !segment_metadata.is_dir()
                    {
                        return Err(PersistenceError::InvalidPath);
                    }
                    let mut segment_files = Vec::new();
                    for event_entry in
                        fs::read_dir(segment_entry.path()).map_err(|_| PersistenceError::Io)?
                    {
                        let event_entry = event_entry.map_err(|_| PersistenceError::Io)?;
                        let event_name = event_entry
                            .file_name()
                            .into_string()
                            .map_err(|_| PersistenceError::InvalidPath)?;
                        let event_metadata = ygo_storage::safe_store_metadata(&event_entry.path())
                            .map_err(|_| PersistenceError::InvalidPath)?;
                        if is_unpublished_store_file(
                            &event_name,
                            &event_metadata,
                            MAX_RECEIPT_EVENT_BYTES,
                        )? {
                            continue;
                        }
                        if !event_metadata.is_file()
                            || event_metadata.len() > MAX_RECEIPT_EVENT_BYTES
                        {
                            return Err(PersistenceError::InvalidPath);
                        }
                        let sequence = event_name
                            .strip_suffix(".json")
                            .and_then(|text| text.parse::<u64>().ok())
                            .filter(|sequence| *sequence > RECEIPT_SEGMENT_EVENTS)
                            .ok_or(PersistenceError::InvalidChain)?;
                        if event_name != format!("{sequence}.json")
                            || (sequence - 1) / RECEIPT_SEGMENT_EVENTS != segment
                        {
                            return Err(PersistenceError::InvalidChain);
                        }
                        segment_files.push((sequence, event_entry.path()));
                    }
                    if segment_files.len() as u64 > RECEIPT_SEGMENT_EVENTS {
                        return Err(PersistenceError::InvalidChain);
                    }
                    files.extend(segment_files);
                }
                continue;
            }
            if is_unpublished_store_file(&name, &metadata, MAX_RECEIPT_EVENT_BYTES)? {
                continue;
            }
            if !metadata.is_file() || metadata.len() > MAX_RECEIPT_EVENT_BYTES {
                return Err(PersistenceError::InvalidPath);
            }
            let sequence = name
                .strip_suffix(".json")
                .and_then(|text| text.parse::<u64>().ok())
                .filter(|sequence| *sequence > 0)
                .ok_or(PersistenceError::InvalidChain)?;
            if name != format!("{sequence}.json") || sequence > LEGACY_FLAT_RECEIPT_EVENTS {
                return Err(PersistenceError::InvalidChain);
            }
            files.push((sequence, entry.path()));
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
    fn receipt_event_paths_segment_after_the_legacy_flat_region() {
        let dir = std::path::Path::new("attempt_receipts");
        assert_eq!(receipt_event_path(dir, 1), dir.join("1.json"));
        assert_eq!(
            receipt_event_path(dir, RECEIPT_SEGMENT_EVENTS),
            dir.join(format!("{RECEIPT_SEGMENT_EVENTS}.json"))
        );
        assert_eq!(
            receipt_event_path(dir, RECEIPT_SEGMENT_EVENTS + 1),
            dir.join("segments/segment-00000001/4097.json")
        );
        assert_eq!(
            receipt_event_path(dir, 20_001),
            dir.join("segments/segment-00000004/20001.json")
        );
    }

    #[test]
    fn legacy_flat_receipt_history_appends_to_segments_past_twenty_thousand_events() {
        use std::time::{SystemTime, UNIX_EPOCH};

        let root = std::env::temp_dir().join(format!(
            "ygo-receipt-segments-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock after epoch")
                .as_nanos()
        ));
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
        let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
        let receipt_dir = store.attempt_receipt_dir(&context.job_id);
        fs::create_dir_all(&receipt_dir).unwrap();
        let mut previous_sha256 = ZERO_HASH.to_owned();
        let mut sequence = 0_u64;

        for ordinal in 1..=10_000_u64 {
            let attempt_id = format!("{ordinal:032x}");
            let events = [
                AttemptReceiptEventV1::Started {
                    ordinal,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                },
                AttemptReceiptEventV1::HostResult {
                    ordinal,
                    attempt_id,
                    phase: SearchAttemptPhase::Initial,
                    result: SearchAttemptResult::DuelResult {
                        status: ygo_engine_adapter::DuelStatus::Failed,
                    },
                    process_observation: ygo_engine_adapter::ProcessRunObservation::default(),
                },
            ];
            for event in events {
                sequence += 1;
                let event_sha256 =
                    event_digest(&context_sha256, sequence, &previous_sha256, &event).unwrap();
                let envelope = AttemptReceiptEnvelopeV1 {
                    schema_version: 1,
                    kind: "w1c_search_attempt_journal_event".into(),
                    context: context.clone(),
                    context_sha256: context_sha256.clone(),
                    sequence,
                    previous_sha256,
                    event,
                    event_sha256: event_sha256.clone(),
                };
                let path = receipt_dir.join(format!("{sequence}.json"));
                fs::create_dir_all(path.parent().unwrap()).unwrap();
                fs::write(path, serde_json::to_vec(&envelope).unwrap()).unwrap();
                previous_sha256 = event_sha256;
            }
        }
        let ordinal = 10_001;
        let attempt_id = format!("{ordinal:032x}");
        store
            .append_attempt_receipt(
                &context,
                AttemptReceiptEventV1::Started {
                    ordinal,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                },
            )
            .unwrap();
        store
            .append_attempt_receipt(
                &context,
                AttemptReceiptEventV1::HostResult {
                    ordinal,
                    attempt_id,
                    phase: SearchAttemptPhase::Initial,
                    result: SearchAttemptResult::DuelResult {
                        status: ygo_engine_adapter::DuelStatus::Failed,
                    },
                    process_observation: ygo_engine_adapter::ProcessRunObservation::default(),
                },
            )
            .unwrap();
        let history = store.read_attempt_receipts(&context.job_id).unwrap();
        assert_eq!(history.len(), 20_002);
        assert_eq!(history.last().unwrap().sequence, 20_002);
        assert!(receipt_event_path(&receipt_dir, 20_001).is_file());
        assert!(receipt_event_path(&receipt_dir, 20_002).is_file());
        drop(store);
        fs::remove_dir_all(root).unwrap();
    }

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
