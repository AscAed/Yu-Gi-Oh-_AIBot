//! Immutable revision storage for local analysis jobs.
//!
//! This persists validated job metadata and privately stores strictly checked
//! reports. It does not execute analysis or authenticate report provenance.

use super::jobs::{
    same_shape, strict_json_value, AnalysisJobEvent, AnalysisJobRecordV1, AnalysisJobState,
};
use super::FrozenAnalysisInput;
use serde::{Deserialize, Serialize};
use serde_json::Value;
#[cfg(test)]
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};
use ygo_api::combo::{validate_report_contract, AnalysisReport};

const STORE_LOCK: &str = ".ygo-analysis.lock";
const REVISION_KIND: &str = "workbench_analysis_job_revision";
const MAX_REPORT_BYTES: usize = 64 * 1024 * 1024;

#[cfg(test)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum FaultPhase {
    BeforePublish,
    AfterPublish,
    Reread,
}

#[cfg(test)]
#[derive(Debug)]
struct LogicalFault {
    chain: String,
    state: String,
    revision: u64,
    phase: FaultPhase,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PersistenceError {
    Locked,
    InvalidPath,
    InvalidChain,
    RevisionConflict,
    RecordInvalid,
    ReportInvalid,
    ReportBindingMismatch,
    ReportConflict,
    Io,
    CommitUncertain,
}

impl PersistenceError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::Locked => "job_store_locked",
            Self::InvalidPath => "job_store_path_invalid",
            Self::InvalidChain => "job_store_chain_invalid",
            Self::RevisionConflict => "job_store_revision_conflict",
            Self::RecordInvalid => "job_store_record_invalid",
            Self::ReportInvalid => "job_report_invalid",
            Self::ReportBindingMismatch => "job_report_binding_mismatch",
            Self::ReportConflict => "job_report_conflict",
            Self::Io => "job_store_io_failed",
            Self::CommitUncertain => "job_store_commit_uncertain",
        }
    }
}

impl std::fmt::Display for PersistenceError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.code())
    }
}
impl std::error::Error for PersistenceError {}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RevisionEnvelope {
    schema_version: u16,
    kind: String,
    job_id: String,
    revision: u64,
    previous_sha256: Option<String>,
    record_sha256: String,
    record: Value,
}

pub struct PersistentAnalysisJobStore {
    #[cfg(test)]
    logical_fault: std::sync::Mutex<Option<LogicalFault>>,
    #[cfg(test)]
    pub(super) logical_fault_hits: std::sync::Arc<AtomicUsize>,
    pub(super) root: PathBuf,
    initial_publish_lock: std::sync::RwLock<()>,
    #[cfg(test)]
    initial_publish_gate: std::sync::Mutex<
        Option<(
            std::sync::Arc<std::sync::Barrier>,
            std::sync::Arc<std::sync::Barrier>,
        )>,
    >,
    pub(super) attempt_receipt_states:
        std::sync::Mutex<BTreeMap<String, super::attempt_receipts::AttemptReceiptAppendState>>,
    #[cfg(test)]
    pub(super) attempt_receipt_history_reads: AtomicUsize,
    #[cfg(test)]
    pub(super) operation_failure: AtomicUsize,
    // Kept alive for the entire store lifetime; dropping releases the OS lock.
    _lock: ygo_storage::ExclusiveStoreLock,
    #[cfg(test)]
    fail_before_next_publish: AtomicBool,
    #[cfg(test)]
    fail_after_next_publish: AtomicBool,
    #[cfg(test)]
    fail_before_publish_after: AtomicUsize,
    #[cfg(test)]
    fail_before_next_report_publish: AtomicBool,
    #[cfg(test)]
    fail_after_next_report_publish: AtomicBool,
    #[cfg(test)]
    pub(super) fail_attempt_receipt_before_publish_after: AtomicUsize,
    #[cfg(test)]
    pub(super) fail_attempt_receipt_after_publish_after: AtomicUsize,
}

impl std::fmt::Debug for PersistentAnalysisJobStore {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PersistentAnalysisJobStore")
            .field("root", &self.root)
            .finish()
    }
}

impl PersistentAnalysisJobStore {
    #[cfg(test)]
    pub(super) fn pause_initial_publish_for_test(
        &self,
        entered: std::sync::Arc<std::sync::Barrier>,
        release: std::sync::Arc<std::sync::Barrier>,
    ) {
        *self
            .initial_publish_gate
            .lock()
            .expect("initial publish gate") = Some((entered, release));
    }

    #[cfg(test)]
    pub(crate) fn inject_logical_fault(
        &self,
        chain: &str,
        state: &str,
        revision: u64,
        phase: FaultPhase,
    ) {
        *self.logical_fault.lock().expect("fault lock") = Some(LogicalFault {
            chain: chain.into(),
            state: state.into(),
            revision,
            phase,
        });
        self.logical_fault_hits.store(0, Ordering::SeqCst);
    }

    #[cfg(test)]
    pub(crate) fn logical_fault_hits(&self) -> usize {
        self.logical_fault_hits.load(Ordering::SeqCst)
    }

    #[cfg(test)]
    pub(super) fn check_logical_fault(
        &self,
        chain: &str,
        state: &str,
        revision: u64,
        phase: FaultPhase,
    ) -> Result<(), PersistenceError> {
        let mut configured = self.logical_fault.lock().expect("fault lock");
        if configured.as_ref().is_some_and(|f| {
            f.chain == chain && f.state == state && f.revision == revision && f.phase == phase
        }) {
            configured.take();
            self.logical_fault_hits.fetch_add(1, Ordering::SeqCst);
            return Err(if phase == FaultPhase::BeforePublish {
                PersistenceError::Io
            } else {
                PersistenceError::CommitUncertain
            });
        }
        Ok(())
    }

    pub fn open(root: PathBuf) -> Result<Self, PersistenceError> {
        let store = Self::open_unclassified(root)?;
        if store.root.join("operations").exists() {
            return Err(PersistenceError::InvalidPath);
        }
        store.classify_restart()?;
        Ok(store)
    }

    pub(super) fn open_unclassified(root: PathBuf) -> Result<Self, PersistenceError> {
        let root = ygo_storage::prepare_store_directory(&root)
            .map_err(|_| PersistenceError::InvalidPath)?;
        for dir in [root.join("jobs"), root.join("reports")] {
            ygo_storage::prepare_store_directory(&dir)
                .map_err(|_| PersistenceError::InvalidPath)?;
        }
        let lock_path = root.join(STORE_LOCK);
        let lock = ygo_storage::acquire_store_lock(&lock_path).map_err(|error| {
            if error.starts_with("store_lock_busy:") {
                PersistenceError::Locked
            } else {
                PersistenceError::InvalidPath
            }
        })?;
        let store = Self {
            #[cfg(test)]
            logical_fault: std::sync::Mutex::new(None),
            #[cfg(test)]
            logical_fault_hits: std::sync::Arc::new(AtomicUsize::new(0)),
            root,
            initial_publish_lock: std::sync::RwLock::new(()),
            #[cfg(test)]
            initial_publish_gate: std::sync::Mutex::new(None),
            attempt_receipt_states: std::sync::Mutex::new(BTreeMap::new()),
            #[cfg(test)]
            attempt_receipt_history_reads: AtomicUsize::new(0),
            #[cfg(test)]
            operation_failure: AtomicUsize::new(usize::MAX),
            _lock: lock,
            #[cfg(test)]
            fail_before_next_publish: AtomicBool::new(false),
            #[cfg(test)]
            fail_after_next_publish: AtomicBool::new(false),
            #[cfg(test)]
            fail_before_publish_after: AtomicUsize::new(usize::MAX),
            #[cfg(test)]
            fail_before_next_report_publish: AtomicBool::new(false),
            #[cfg(test)]
            fail_after_next_report_publish: AtomicBool::new(false),
            #[cfg(test)]
            fail_attempt_receipt_before_publish_after: AtomicUsize::new(usize::MAX),
            #[cfg(test)]
            fail_attempt_receipt_after_publish_after: AtomicUsize::new(usize::MAX),
        };
        store.scan()?;
        Ok(store)
    }

    pub(super) fn classify_restart(&self) -> Result<(), PersistenceError> {
        for (_, history) in self.scan()? {
            if let Some(last) = history.last() {
                if matches!(
                    last.state(),
                    AnalysisJobState::Queued | AnalysisJobState::Running
                ) {
                    let next = last
                        .transition(
                            last.revision(),
                            AnalysisJobEvent::ClassifyRestart,
                            now_ms()?,
                        )
                        .map_err(|_| PersistenceError::InvalidChain)?;
                    self.publish_next(last, next)?;
                }
            }
        }
        Ok(())
    }

    pub fn append_initial(&self, record: AnalysisJobRecordV1) -> Result<(), PersistenceError> {
        let _publish_guard = self
            .initial_publish_lock
            .write()
            .map_err(|_| PersistenceError::CommitUncertain)?;
        record
            .validate()
            .map_err(|_| PersistenceError::RecordInvalid)?;
        if record.revision() != 1 || record.state() != AnalysisJobState::Queued {
            return Err(PersistenceError::RecordInvalid);
        }
        let dir = self.job_dir(record.job_id());
        if dir.exists() {
            let history = self.read_history(record.job_id())?;
            if history.len() == 1 && history[0].encode_json().ok() == record.encode_json().ok() {
                return Ok(());
            }
            return Err(PersistenceError::RevisionConflict);
        }
        ygo_storage::prepare_store_directory(&dir).map_err(|_| PersistenceError::InvalidPath)?;
        let revisions = dir.join("revisions");
        if ygo_storage::prepare_store_directory(&revisions).is_err() {
            self.remove_empty_job(record.job_id());
            return Err(PersistenceError::InvalidPath);
        }
        #[cfg(test)]
        if let Some((entered, release)) = self
            .initial_publish_gate
            .lock()
            .map_err(|_| PersistenceError::CommitUncertain)?
            .take()
        {
            entered.wait();
            release.wait();
        }
        let result = self.write_envelope(&record, None);
        if result.is_err() && !self.revision_path(record.job_id(), 1).exists() {
            self.remove_empty_job(record.job_id());
        }
        result
    }

    pub fn append_expected(
        &self,
        job_id: &str,
        expected_revision: u64,
        record: AnalysisJobRecordV1,
    ) -> Result<(), PersistenceError> {
        if !valid_id(job_id) || record.job_id() != job_id {
            return Err(PersistenceError::RecordInvalid);
        }
        let history = self.read_history(job_id)?;
        let previous = history.last().ok_or(PersistenceError::RevisionConflict)?;
        if previous.revision() != expected_revision
            || record.revision() != expected_revision.saturating_add(1)
        {
            return Err(PersistenceError::RevisionConflict);
        }
        record
            .validate()
            .map_err(|_| PersistenceError::RecordInvalid)?;
        validate_transition(previous, &record)?;
        self.publish_next(previous, record)
    }

    pub fn history(&self, job_id: &str) -> Result<Vec<AnalysisJobRecordV1>, PersistenceError> {
        self.read_history(job_id)
    }

    /// Validates and stores the private report bytes for a running task.
    /// This does not publish a terminal job revision or authenticate the report source.
    pub fn persist_report(
        &self,
        running: &AnalysisJobRecordV1,
        frozen: &FrozenAnalysisInput,
        bytes: &[u8],
    ) -> Result<super::jobs::AnalysisJobReportRefV1, PersistenceError> {
        validate_frozen_job_binding(running, frozen)?;
        let report = strict_report(bytes)?;
        validate_report_binding(&report, frozen, &running.input().scoring)?;
        let report_id = ygo_storage::secure_random_hex(16).map_err(|_| PersistenceError::Io)?;
        let report_sha256 = ygo_storage::hash(bytes);
        let path = self.report_path(&report_id);
        #[cfg(test)]
        if self
            .fail_before_next_report_publish
            .swap(false, Ordering::SeqCst)
        {
            return Err(PersistenceError::Io);
        }
        #[cfg(test)]
        self.check_logical_fault("report", "file", 0, FaultPhase::BeforePublish)?;
        ygo_storage::publish_exclusive_file(&path, bytes).map_err(|error| {
            if error.starts_with("store_commit_uncertain:") {
                PersistenceError::CommitUncertain
            } else if path.exists() {
                PersistenceError::ReportConflict
            } else {
                PersistenceError::Io
            }
        })?;
        #[cfg(test)]
        if self
            .fail_after_next_report_publish
            .swap(false, Ordering::SeqCst)
        {
            return Err(PersistenceError::CommitUncertain);
        }
        #[cfg(test)]
        self.check_logical_fault("report", "file", 0, FaultPhase::AfterPublish)?;
        #[cfg(test)]
        self.check_logical_fault("report", "file", 0, FaultPhase::Reread)?;
        let reread = fs::read(&path).map_err(|_| PersistenceError::CommitUncertain)?;
        if ygo_storage::hash(&reread) != report_sha256 || strict_report(&reread).is_err() {
            return Err(PersistenceError::CommitUncertain);
        }
        Ok(super::jobs::AnalysisJobReportRefV1 {
            report_id,
            sha256: report_sha256,
            termination: reference_termination(
                &report.search.termination,
                report.search.lines.is_empty(),
            ),
            verified_lines: report.search.lines.len() as u64,
        })
    }

    /// Reloads and revalidates a saved report against the same frozen task input.
    pub fn read_verified_report(
        &self,
        running: &AnalysisJobRecordV1,
        reference: &super::jobs::AnalysisJobReportRefV1,
        frozen: &FrozenAnalysisInput,
    ) -> Result<AnalysisReport, PersistenceError> {
        validate_frozen_job_binding(running, frozen)?;
        if !valid_id(&reference.report_id) || reference.sha256.len() != 64 {
            return Err(PersistenceError::ReportBindingMismatch);
        }
        let path = self.report_path(&reference.report_id);
        let metadata =
            ygo_storage::safe_store_metadata(&path).map_err(|_| PersistenceError::ReportInvalid)?;
        if !metadata.is_file() || metadata.len() > MAX_REPORT_BYTES as u64 {
            return Err(PersistenceError::ReportInvalid);
        }
        let bytes = fs::read(path).map_err(|_| PersistenceError::ReportInvalid)?;
        if ygo_storage::hash(&bytes) != reference.sha256 {
            return Err(PersistenceError::ReportInvalid);
        }
        let report = strict_report(&bytes)?;
        validate_report_binding(&report, frozen, &running.input().scoring)?;
        if !report_matches_reference(&report, reference) {
            return Err(PersistenceError::ReportBindingMismatch);
        }
        Ok(report)
    }

    fn publish_next(
        &self,
        previous: &AnalysisJobRecordV1,
        next: AnalysisJobRecordV1,
    ) -> Result<(), PersistenceError> {
        validate_transition(previous, &next)?;
        let previous_path = self.revision_path(previous.job_id(), previous.revision());
        let previous_bytes =
            fs::read(&previous_path).map_err(|_| PersistenceError::InvalidChain)?;
        let previous_hash = ygo_storage::hash(&previous_bytes);
        self.write_envelope(&next, Some(previous_hash))
    }

    fn write_envelope(
        &self,
        record: &AnalysisJobRecordV1,
        previous_sha256: Option<String>,
    ) -> Result<(), PersistenceError> {
        let bytes = record
            .encode_json()
            .map_err(|_| PersistenceError::RecordInvalid)?;
        let value: Value =
            serde_json::from_slice(&bytes).map_err(|_| PersistenceError::RecordInvalid)?;
        let envelope = RevisionEnvelope {
            schema_version: 1,
            kind: REVISION_KIND.into(),
            job_id: record.job_id().into(),
            revision: record.revision(),
            previous_sha256,
            record_sha256: ygo_storage::hash(&bytes),
            record: value,
        };
        let encoded =
            serde_json::to_vec_pretty(&envelope).map_err(|_| PersistenceError::RecordInvalid)?;
        let path = self.revision_path(record.job_id(), record.revision());
        if path.exists() {
            return match fs::read(&path) {
                Ok(existing) if existing == encoded => Ok(()),
                _ => Err(PersistenceError::RevisionConflict),
            };
        }
        #[cfg(test)]
        if self.fail_before_next_publish.swap(false, Ordering::SeqCst) {
            return Err(PersistenceError::Io);
        }
        #[cfg(test)]
        {
            let remaining = self.fail_before_publish_after.load(Ordering::SeqCst);
            if remaining == 0 {
                self.fail_before_publish_after
                    .store(usize::MAX, Ordering::SeqCst);
                return Err(PersistenceError::Io);
            }
            if remaining != usize::MAX {
                self.fail_before_publish_after
                    .fetch_sub(1, Ordering::SeqCst);
            }
        }
        #[cfg(test)]
        let logical_state = serde_json::to_value(record.state())
            .expect("state")
            .as_str()
            .expect("state string")
            .to_owned();
        #[cfg(test)]
        self.check_logical_fault(
            "job",
            &logical_state,
            record.revision(),
            FaultPhase::BeforePublish,
        )?;
        ygo_storage::publish_exclusive_file(&path, &encoded).map_err(|error| {
            if error.starts_with("store_commit_uncertain:") || path.exists() {
                PersistenceError::CommitUncertain
            } else if error.contains("already exists") || error.contains("File exists") {
                PersistenceError::RevisionConflict
            } else {
                PersistenceError::Io
            }
        })?;
        #[cfg(test)]
        if self.fail_after_next_publish.swap(false, Ordering::SeqCst) {
            return Err(PersistenceError::CommitUncertain);
        }
        #[cfg(test)]
        self.check_logical_fault(
            "job",
            &logical_state,
            record.revision(),
            FaultPhase::AfterPublish,
        )?;
        #[cfg(test)]
        self.check_logical_fault("job", &logical_state, record.revision(), FaultPhase::Reread)?;
        let history = self
            .read_history(record.job_id())
            .map_err(|_| PersistenceError::CommitUncertain)?;
        if history.last().and_then(|saved| saved.encode_json().ok()) != record.encode_json().ok() {
            return Err(PersistenceError::CommitUncertain);
        }
        Ok(())
    }

    #[cfg(test)]
    pub(super) fn inject_uncertain_after_next_publish(&self) {
        self.fail_after_next_publish.store(true, Ordering::SeqCst);
    }

    #[cfg(test)]
    pub(super) fn inject_failure_before_next_publish(&self) {
        self.fail_before_next_publish.store(true, Ordering::SeqCst);
    }

    #[cfg(test)]
    pub(super) fn inject_failure_before_publish_after(&self, successful_publishes: usize) {
        self.fail_before_publish_after
            .store(successful_publishes, Ordering::SeqCst);
    }

    #[cfg(test)]
    pub(super) fn inject_report_publish_failure(&self, after_publish: bool) {
        if after_publish {
            self.fail_after_next_report_publish
                .store(true, Ordering::SeqCst);
        } else {
            self.fail_before_next_report_publish
                .store(true, Ordering::SeqCst);
        }
    }

    pub(super) fn scan(
        &self,
    ) -> Result<BTreeMap<String, Vec<AnalysisJobRecordV1>>, PersistenceError> {
        let _publish_guard = self
            .initial_publish_lock
            .read()
            .map_err(|_| PersistenceError::CommitUncertain)?;
        self.validate_root_layout()?;
        let jobs = self.root.join("jobs");
        let mut result = BTreeMap::new();
        for entry in fs::read_dir(&jobs).map_err(|_| PersistenceError::Io)? {
            let entry = entry.map_err(|_| PersistenceError::Io)?;
            let name = entry.file_name().to_string_lossy().into_owned();
            let metadata = ygo_storage::safe_store_metadata(&entry.path())
                .map_err(|_| PersistenceError::InvalidPath)?;
            if !metadata.is_dir() || !valid_id(&name) {
                return Err(PersistenceError::InvalidPath);
            }
            let history = self.read_history(&name)?;
            if history.is_empty() {
                return Err(PersistenceError::InvalidChain);
            }
            result.insert(name, history);
        }
        for history in result.values() {
            if let Some(record) = history.last() {
                if let Some(reference) = record.report() {
                    self.validate_saved_report_reference(record, reference)?;
                }
            }
        }
        for job_id in result.keys() {
            self.read_attempt_receipts(job_id)?;
        }
        Ok(result)
    }

    fn validate_saved_report_reference(
        &self,
        record: &AnalysisJobRecordV1,
        reference: &super::jobs::AnalysisJobReportRefV1,
    ) -> Result<(), PersistenceError> {
        self.read_saved_report(record, reference).map(|_| ())
    }

    pub(super) fn read_saved_report(
        &self,
        record: &AnalysisJobRecordV1,
        reference: &super::jobs::AnalysisJobReportRefV1,
    ) -> Result<AnalysisReport, PersistenceError> {
        if !valid_id(&reference.report_id) || reference.sha256.len() != 64 {
            return Err(PersistenceError::ReportBindingMismatch);
        }
        let path = self.report_path(&reference.report_id);
        let metadata =
            ygo_storage::safe_store_metadata(&path).map_err(|_| PersistenceError::ReportInvalid)?;
        if !metadata.is_file() || metadata.len() > MAX_REPORT_BYTES as u64 {
            return Err(PersistenceError::ReportInvalid);
        }
        let bytes = fs::read(path).map_err(|_| PersistenceError::ReportInvalid)?;
        if ygo_storage::hash(&bytes) != reference.sha256 {
            return Err(PersistenceError::ReportInvalid);
        }
        let report = strict_report(&bytes)?;
        let input = record.input();
        let identity = &input.identity;
        let runtime = &report.runtime_request;
        if !json_equal(&report.request, &input.request)
            || !json_equal(&report.search.scoring, &input.scoring)
            || !json_equal(&report.search.budget, &input.request.search)
            || runtime.protocol_version != identity.protocol_version
            || runtime.deck != input.request.deck
            || runtime.opening_hand != input.request.opening_hand
            || runtime.seed != input.request.seed
            || runtime.versions.rules != identity.rules
            || runtime.versions.catalog != identity.catalog_id
            || runtime.versions.banlist != identity.banlist_id
            || runtime.versions.engine_sha256 != identity.engine_sha256
            || runtime.versions.cdb_sha256 != identity.cdb_sha256
            || runtime.versions.scripts_sha256 != identity.scripts_sha256
            || runtime.versions.core_commit != identity.core_commit
            || runtime.versions.initializer != identity.initializer
            || !report_matches_reference(&report, reference)
        {
            return Err(PersistenceError::ReportBindingMismatch);
        }
        Ok(report)
    }

    fn validate_root_layout(&self) -> Result<(), PersistenceError> {
        let mut names = std::collections::BTreeSet::new();
        for entry in fs::read_dir(&self.root).map_err(|_| PersistenceError::Io)? {
            let entry = entry.map_err(|_| PersistenceError::Io)?;
            let name = entry.file_name().to_string_lossy().into_owned();
            let metadata = ygo_storage::safe_store_metadata(&entry.path())
                .map_err(|_| PersistenceError::InvalidPath)?;
            match name.as_str() {
                STORE_LOCK if metadata.is_file() => {}
                "jobs" | "reports" if metadata.is_dir() => {}
                "operations" if metadata.is_dir() => {
                    self.scan_operations()?;
                }
                _ => return Err(PersistenceError::InvalidPath),
            }
            names.insert(name);
        }
        if ![STORE_LOCK, "jobs", "reports"]
            .iter()
            .all(|name| names.contains(*name))
        {
            return Err(PersistenceError::InvalidPath);
        }
        let reports = self.root.join("reports");
        for entry in fs::read_dir(reports).map_err(|_| PersistenceError::Io)? {
            let entry = entry.map_err(|_| PersistenceError::Io)?;
            let name = entry.file_name().to_string_lossy().into_owned();
            let metadata = ygo_storage::safe_store_metadata(&entry.path())
                .map_err(|_| PersistenceError::InvalidPath)?;
            if is_unpublished_store_file(&name, &metadata, MAX_REPORT_BYTES as u64)
                .map_err(|_| PersistenceError::ReportInvalid)?
            {
                // An interrupted exclusive publish can leave its synced,
                // unpublished temporary bytes behind. Preserve them as
                // evidence, but never treat them as an indexed report.
                continue;
            }
            let id = name
                .strip_suffix(".json")
                .ok_or(PersistenceError::ReportInvalid)?;
            if !valid_id(id) || !metadata.is_file() || metadata.len() > MAX_REPORT_BYTES as u64 {
                return Err(PersistenceError::ReportInvalid);
            }
            let bytes = fs::read(entry.path()).map_err(|_| PersistenceError::ReportInvalid)?;
            strict_report(&bytes)?;
        }
        Ok(())
    }

    fn read_history(&self, job_id: &str) -> Result<Vec<AnalysisJobRecordV1>, PersistenceError> {
        if !valid_id(job_id) {
            return Err(PersistenceError::RecordInvalid);
        }
        let dir = self.job_dir(job_id);
        let metadata =
            ygo_storage::safe_store_metadata(&dir).map_err(|_| PersistenceError::InvalidPath)?;
        if !metadata.is_dir() {
            return Err(PersistenceError::InvalidPath);
        }
        let revisions = dir.join("revisions");
        let revisions_meta = ygo_storage::safe_store_metadata(&revisions)
            .map_err(|_| PersistenceError::InvalidPath)?;
        if !revisions_meta.is_dir() {
            return Err(PersistenceError::InvalidPath);
        }
        for entry in fs::read_dir(&dir).map_err(|_| PersistenceError::Io)? {
            let entry = entry.map_err(|_| PersistenceError::Io)?;
            match entry.file_name().to_str() {
                Some("revisions") => {}
                Some("attempt_receipts") => {
                    let metadata = ygo_storage::safe_store_metadata(&entry.path())
                        .map_err(|_| PersistenceError::InvalidPath)?;
                    if !metadata.is_dir() {
                        return Err(PersistenceError::InvalidPath);
                    }
                }
                _ => return Err(PersistenceError::InvalidChain),
            }
        }
        let mut files = Vec::new();
        for entry in fs::read_dir(&revisions).map_err(|_| PersistenceError::Io)? {
            let entry = entry.map_err(|_| PersistenceError::Io)?;
            let name = entry.file_name().to_string_lossy().into_owned();
            let metadata = ygo_storage::safe_store_metadata(&entry.path())
                .map_err(|_| PersistenceError::InvalidPath)?;
            if is_unpublished_store_file(&name, &metadata, 1024 * 1024)? {
                continue;
            }
            if !metadata.is_file() || !name.ends_with(".json") {
                return Err(PersistenceError::InvalidChain);
            }
            let number = name
                .strip_suffix(".json")
                .and_then(|v| v.parse::<u64>().ok())
                .filter(|n| *n > 0)
                .ok_or(PersistenceError::InvalidChain)?;
            if name != format!("{number}.json") {
                return Err(PersistenceError::InvalidChain);
            }
            files.push((number, entry.path()));
        }
        files.sort_by_key(|(number, _)| *number);
        if files.is_empty()
            || files
                .iter()
                .enumerate()
                .any(|(i, (n, _))| *n != i as u64 + 1)
        {
            return Err(PersistenceError::InvalidChain);
        }
        let mut records = Vec::with_capacity(files.len());
        let mut prior_hash: Option<String> = None;
        for (expected, path) in files {
            let bytes = fs::read(path).map_err(|_| PersistenceError::Io)?;
            let value = strict_json_value(&bytes).map_err(|_| PersistenceError::InvalidChain)?;
            let envelope: RevisionEnvelope = serde_json::from_value(value.clone())
                .map_err(|_| PersistenceError::InvalidChain)?;
            let shape =
                serde_json::to_value(&envelope).map_err(|_| PersistenceError::InvalidChain)?;
            if !same_shape(&value, &shape)
                || envelope.schema_version != 1
                || envelope.kind != REVISION_KIND
                || envelope.job_id != job_id
                || envelope.revision != expected
                || envelope.previous_sha256 != prior_hash
            {
                return Err(PersistenceError::InvalidChain);
            }
            let record_bytes =
                serde_json::to_vec(&envelope.record).map_err(|_| PersistenceError::InvalidChain)?;
            let record = AnalysisJobRecordV1::read_json(&record_bytes)
                .map_err(|_| PersistenceError::InvalidChain)?;
            if ygo_storage::hash(
                &record
                    .encode_json()
                    .map_err(|_| PersistenceError::InvalidChain)?,
            ) != envelope.record_sha256
            {
                return Err(PersistenceError::InvalidChain);
            }
            if record.job_id() != job_id || record.revision() != expected {
                return Err(PersistenceError::InvalidChain);
            }
            if let Some(previous) = records.last() {
                validate_transition(previous, &record)?;
            } else if record.state() != AnalysisJobState::Queued {
                return Err(PersistenceError::InvalidChain);
            }
            prior_hash = Some(ygo_storage::hash(&bytes));
            records.push(record);
        }
        Ok(records)
    }

    fn job_dir(&self, id: &str) -> PathBuf {
        self.root.join("jobs").join(id)
    }
    fn remove_empty_job(&self, id: &str) {
        let dir = self.job_dir(id);
        let _ = fs::remove_dir(dir.join("revisions"));
        let _ = fs::remove_dir(dir);
    }
    fn revision_path(&self, id: &str, revision: u64) -> PathBuf {
        self.job_dir(id)
            .join("revisions")
            .join(format!("{revision}.json"))
    }
    fn report_path(&self, id: &str) -> PathBuf {
        self.root.join("reports").join(format!("{id}.json"))
    }

    #[cfg(test)]
    pub(super) fn inject_attempt_receipt_failure_after(
        &self,
        successful_publishes: usize,
        after_publish: bool,
    ) {
        let target = if after_publish {
            &self.fail_attempt_receipt_after_publish_after
        } else {
            &self.fail_attempt_receipt_before_publish_after
        };
        target.store(successful_publishes, Ordering::SeqCst);
    }

    #[cfg(test)]
    pub(super) fn fail_attempt_receipt_before_publish(&self) -> Result<(), PersistenceError> {
        let remaining = self
            .fail_attempt_receipt_before_publish_after
            .load(Ordering::SeqCst);
        if remaining == 0 {
            self.fail_attempt_receipt_before_publish_after
                .store(usize::MAX, Ordering::SeqCst);
            return Err(PersistenceError::Io);
        }
        if remaining != usize::MAX {
            self.fail_attempt_receipt_before_publish_after
                .fetch_sub(1, Ordering::SeqCst);
        }
        Ok(())
    }

    #[cfg(test)]
    pub(super) fn fail_attempt_receipt_after_publish(&self) -> Result<(), PersistenceError> {
        let remaining = self
            .fail_attempt_receipt_after_publish_after
            .load(Ordering::SeqCst);
        if remaining == 0 {
            self.fail_attempt_receipt_after_publish_after
                .store(usize::MAX, Ordering::SeqCst);
            return Err(PersistenceError::CommitUncertain);
        }
        if remaining != usize::MAX {
            self.fail_attempt_receipt_after_publish_after
                .fetch_sub(1, Ordering::SeqCst);
        }
        Ok(())
    }
}

fn strict_report(bytes: &[u8]) -> Result<AnalysisReport, PersistenceError> {
    if bytes.is_empty() || bytes.len() > MAX_REPORT_BYTES {
        return Err(PersistenceError::ReportInvalid);
    }
    let raw = strict_json_value(bytes).map_err(|_| PersistenceError::ReportInvalid)?;
    let report: AnalysisReport =
        serde_json::from_value(raw.clone()).map_err(|_| PersistenceError::ReportInvalid)?;
    let canonical = serde_json::to_value(&report).map_err(|_| PersistenceError::ReportInvalid)?;
    if !same_shape(&raw, &canonical)
        || report.schema_version != 2
        || validate_report_contract(&report).is_err()
    {
        return Err(PersistenceError::ReportInvalid);
    }
    Ok(report)
}

fn reference_termination(termination: &str, no_verified_lines: bool) -> String {
    if no_verified_lines {
        format!("{termination}:no_verified_lines")
    } else {
        termination.to_owned()
    }
}

fn report_matches_reference(
    report: &AnalysisReport,
    reference: &super::jobs::AnalysisJobReportRefV1,
) -> bool {
    let (termination, marked_empty) = match reference.termination.strip_suffix(":no_verified_lines")
    {
        Some(termination) => (termination, true),
        None => (reference.termination.as_str(), false),
    };
    termination == report.search.termination
        && marked_empty == report.search.lines.is_empty()
        && report.search.lines.len() as u64 == reference.verified_lines
}

fn validate_report_binding(
    report: &AnalysisReport,
    frozen: &FrozenAnalysisInput,
    scoring: &ygo_search::combo::ScoringConfig,
) -> Result<(), PersistenceError> {
    if !json_equal(&report.request, &frozen.request)
        || !json_equal(&report.runtime_request, &frozen.runtime_request)
        || !json_equal(&report.search.scoring, scoring)
        || !json_equal(&report.search.budget, &frozen.request.search)
    {
        return Err(PersistenceError::ReportBindingMismatch);
    }
    Ok(())
}

fn validate_frozen_job_binding(
    running: &AnalysisJobRecordV1,
    frozen: &FrozenAnalysisInput,
) -> Result<(), PersistenceError> {
    running
        .validate()
        .map_err(|_| PersistenceError::ReportBindingMismatch)?;
    if running.state() != AnalysisJobState::Running
        || running.input().identity.input_sha256 != frozen.identity.input_sha256
        || running.input().draft_id != frozen.draft_id
        || running.input().draft_revision != frozen.draft_revision
        || !json_equal(&running.input().request, &frozen.request)
        || running.input().identity != frozen.identity
    {
        return Err(PersistenceError::ReportBindingMismatch);
    }
    Ok(())
}

fn json_equal<T: Serialize, U: Serialize>(left: &T, right: &U) -> bool {
    serde_json::to_value(left).ok() == serde_json::to_value(right).ok()
}

fn validate_transition(
    previous: &AnalysisJobRecordV1,
    next: &AnalysisJobRecordV1,
) -> Result<(), PersistenceError> {
    if previous.job_id() != next.job_id()
        || previous.revision().checked_add(1) != Some(next.revision())
    {
        return Err(PersistenceError::InvalidChain);
    }
    let event = match (previous.state(), next.state()) {
        (AnalysisJobState::Queued, AnalysisJobState::Running) => AnalysisJobEvent::Start,
        (AnalysisJobState::Queued, AnalysisJobState::Cancelled) => AnalysisJobEvent::Cancel,
        (AnalysisJobState::Queued, AnalysisJobState::Interrupted)
        | (AnalysisJobState::Running, AnalysisJobState::Unknown) => {
            AnalysisJobEvent::ClassifyRestart
        }
        (AnalysisJobState::Running, AnalysisJobState::Failed) => {
            AnalysisJobEvent::Fail(next.error_code().ok_or(PersistenceError::InvalidChain)?)
        }
        (
            AnalysisJobState::Running,
            AnalysisJobState::Completed | AnalysisJobState::BudgetLimited,
        ) => AnalysisJobEvent::ReportPublished(
            next.report()
                .cloned()
                .ok_or(PersistenceError::InvalidChain)?,
        ),
        _ => return Err(PersistenceError::InvalidChain),
    };
    let transitioned = previous
        .transition(previous.revision(), event, next.updated_at_ms())
        .map_err(|_| PersistenceError::InvalidChain)?;
    if transitioned.encode_json().ok() != next.encode_json().ok() {
        return Err(PersistenceError::InvalidChain);
    }
    Ok(())
}

fn valid_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub(super) fn unpublished_store_file_id(name: &str) -> Option<&str> {
    let id = name.strip_prefix(".ygo-draft-")?.strip_suffix(".tmp")?;
    valid_id(id).then_some(id)
}

pub(super) fn is_unpublished_store_file(
    name: &str,
    metadata: &fs::Metadata,
    max_bytes: u64,
) -> Result<bool, PersistenceError> {
    if unpublished_store_file_id(name).is_none() {
        return Ok(false);
    }
    if !metadata.is_file() || metadata.len() > max_bytes {
        return Err(PersistenceError::InvalidPath);
    }
    Ok(true)
}

pub(super) fn now_ms() -> Result<u64, PersistenceError> {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| PersistenceError::RecordInvalid)?
        .as_millis();
    u64::try_from(millis).map_err(|_| PersistenceError::RecordInvalid)
}
