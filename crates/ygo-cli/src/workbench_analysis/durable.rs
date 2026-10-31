//! Persistence-first coordination for the in-process analysis queue.
//!
//! This coordinates metadata and private reports only. It does not execute an
//! analysis or authenticate the origin of a report.

use super::{
    jobs::{AnalysisJobEvent, AnalysisJobFailure, AnalysisJobRecordV1},
    operations::{
        AnalysisOperationCommand as OperationCommand, AnalysisOperationContext as OperationContext,
        AnalysisOperationError, AnalysisOperationRecordV1 as Operation,
        AnalysisOperationState as OperationState,
    },
    persistence::{PersistenceError, PersistentAnalysisJobStore},
    queue::{AnalysisJobQueue, DispatchTicket, QueueError, QueueSnapshot},
    FrozenAnalysisInput,
};
use std::{path::PathBuf, sync::Mutex};
use ygo_api::combo::AnalysisReport;
use ygo_search::combo::ScoringConfig;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DurableCoordinatorError {
    Stopped,
    LockUnavailable,
    AssetMismatch,
    Persistence(PersistenceError),
    Queue(QueueError),
    Operation(AnalysisOperationError),
}

impl DurableCoordinatorError {
    pub fn code(self) -> &'static str {
        match self {
            Self::Stopped => "job_coordinator_stopped",
            Self::LockUnavailable => "job_coordinator_unavailable",
            Self::AssetMismatch => "analysis_asset_mismatch",
            Self::Persistence(error) => error.code(),
            Self::Queue(error) => error.code(),
            Self::Operation(error) => error.code(),
        }
    }
}

/// A persistence-first coordinator. The OS store lock is acquired before any
/// queue operation and held for the coordinator lifetime.
pub struct DurableAnalysisCoordinator {
    store: PersistentAnalysisJobStore,
    queue: AnalysisJobQueue,
    stopped: Mutex<bool>,
    reservation: Mutex<Option<String>>,
}

/// A durable accepting record and its optional, single-use freeze authority.
pub struct OperationSubmission {
    pub record: Operation,
    pub ticket: Option<OperationFreezeTicket>,
}

/// Owned authority to finish precisely one saved accepting operation.
/// Deliberately neither Clone nor serializable.
pub struct OperationFreezeTicket {
    operation: Operation,
}

fn requires_stop(error: PersistenceError) -> bool {
    matches!(
        error,
        PersistenceError::CommitUncertain
            | PersistenceError::InvalidChain
            | PersistenceError::RevisionConflict
            | PersistenceError::RecordInvalid
            | PersistenceError::InvalidPath
    )
}

impl DurableAnalysisCoordinator {
    pub fn open(root: PathBuf) -> Result<Self, DurableCoordinatorError> {
        let store =
            PersistentAnalysisJobStore::open(root).map_err(DurableCoordinatorError::Persistence)?;
        Ok(Self {
            store,
            queue: AnalysisJobQueue::default(),
            stopped: Mutex::new(false),
            reservation: Mutex::new(None),
        })
    }

    #[cfg(test)]
    pub(crate) fn inject_uncertain_after_next_publish(&self) {
        self.store.inject_uncertain_after_next_publish();
    }

    #[cfg(test)]
    pub(crate) fn inject_failure_before_next_publish(&self) {
        self.store.inject_failure_before_next_publish();
    }

    #[cfg(test)]
    pub(crate) fn inject_operation_failure_before_next_publish(&self) {
        self.store
            .operation_failure
            .store(0, std::sync::atomic::Ordering::SeqCst);
    }

    #[cfg(test)]
    pub(super) fn inject_failure_before_publish_after(&self, successful_publishes: usize) {
        self.store
            .inject_failure_before_publish_after(successful_publishes);
    }

    #[cfg(test)]
    pub(super) fn inject_report_publish_failure(&self, after_publish: bool) {
        self.store.inject_report_publish_failure(after_publish);
    }

    pub fn snapshot(&self) -> Result<QueueSnapshot, DurableCoordinatorError> {
        let stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        self.queue
            .snapshot()
            .map_err(DurableCoordinatorError::Queue)
    }

    pub fn submit(
        &self,
        input: FrozenAnalysisInput,
        scoring: ScoringConfig,
        now_ms: u64,
    ) -> Result<AnalysisJobRecordV1, DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        if self
            .reservation
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?
            .is_some()
        {
            return Err(DurableCoordinatorError::Queue(QueueError::Full));
        }
        match self
            .queue
            .enqueue_with_persist(input, scoring, now_ms, |record| {
                self.store.append_initial(record.clone())
            }) {
            Ok(record) => Ok(record),
            Err(error) => self.map_queue_error(error, stopped),
        }
    }

    pub fn claim_next(
        &self,
        now_ms: u64,
    ) -> Result<Option<DispatchTicket>, DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        let claimed = match self.queue.claim_next_with_persist(now_ms, |record| {
            self.store
                .append_expected(record.job_id(), record.revision() - 1, record.clone())
        }) {
            Ok(ticket) => ticket,
            Err(error) => return self.map_queue_error(error, stopped),
        };
        let Some(ticket) = claimed else {
            return Ok(None);
        };
        if super::verify_frozen_asset_identity(ticket.input()).is_err() {
            match self.queue.settle_with_persist(
                &ticket,
                AnalysisJobEvent::Fail(AnalysisJobFailure::AssetMismatch),
                now_ms,
                |record| {
                    self.store.append_expected(
                        record.job_id(),
                        record.revision() - 1,
                        record.clone(),
                    )
                },
            ) {
                Ok(_) => return Err(DurableCoordinatorError::AssetMismatch),
                Err(QueueError::Persistence(error)) => {
                    // This internally claimed job has no dispatch ticket. A
                    // failed settlement leaves the in-memory and durable
                    // states divergent, so this coordinator cannot continue.
                    *stopped = true;
                    return self.map_persistence_error(error, stopped);
                }
                Err(error) => {
                    *stopped = true;
                    return Err(DurableCoordinatorError::Queue(error));
                }
            }
        }
        Ok(Some(ticket))
    }

    pub fn cancel(
        &self,
        job_id: &str,
        revision: u64,
        now_ms: u64,
    ) -> Result<AnalysisJobRecordV1, DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        match self
            .queue
            .cancel_with_persist(job_id, revision, now_ms, |record| {
                self.store
                    .append_expected(record.job_id(), record.revision() - 1, record.clone())
            }) {
            Ok(record) => Ok(record),
            Err(error) => self.map_queue_error(error, stopped),
        }
    }

    /// Persists the report first, then commits its terminal task revision, then
    /// removes the in-memory running slot. A report may be orphaned if the
    /// terminal append fails; the coordinator stops on an uncertain commit.
    pub fn publish_report(
        &self,
        ticket: &DispatchTicket,
        bytes: &[u8],
        now_ms: u64,
    ) -> Result<(AnalysisJobRecordV1, AnalysisReport), DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        let snapshot = self
            .queue
            .snapshot()
            .map_err(DurableCoordinatorError::Queue)?;
        let current = snapshot
            .running
            .ok_or(DurableCoordinatorError::Queue(QueueError::TicketMismatch))?;
        if current.encode_json().ok() != ticket.record().encode_json().ok() {
            return Err(DurableCoordinatorError::Queue(QueueError::TicketMismatch));
        }
        let reference = match self
            .store
            .persist_report(ticket.record(), ticket.input(), bytes)
        {
            Ok(reference) => reference,
            Err(error) => return self.map_persistence_error(error, stopped),
        };
        let report =
            match self
                .store
                .read_verified_report(ticket.record(), &reference, ticket.input())
            {
                Ok(report) => report,
                Err(_) => {
                    return self.map_persistence_error(PersistenceError::CommitUncertain, stopped)
                }
            };
        let event = AnalysisJobEvent::ReportPublished(reference);
        let outcome = self
            .queue
            .settle_with_persist(ticket, event, now_ms, |record| {
                self.store
                    .append_expected(record.job_id(), record.revision() - 1, record.clone())
            });
        match outcome {
            Ok(record) => Ok((record, report)),
            Err(error) => {
                // The report is already durable. Retrying this ticket with
                // another payload could publish a conflicting result for the
                // same execution, so require restart classification as unknown.
                *stopped = true;
                match error {
                    QueueError::Persistence(persistence) => {
                        self.map_persistence_error(persistence, stopped)
                    }
                    other => Err(DurableCoordinatorError::Queue(other)),
                }
            }
        }
    }

    pub fn fail(
        &self,
        ticket: &DispatchTicket,
        now_ms: u64,
    ) -> Result<AnalysisJobRecordV1, DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        match self.queue.settle_with_persist(
            ticket,
            AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
            now_ms,
            |record| {
                self.store
                    .append_expected(record.job_id(), record.revision() - 1, record.clone())
            },
        ) {
            Ok(record) => Ok(record),
            Err(QueueError::Persistence(error)) => self.map_persistence_error(error, stopped),
            Err(error) => Err(DurableCoordinatorError::Queue(error)),
        }
    }

    pub fn history(
        &self,
        job_id: &str,
    ) -> Result<Vec<AnalysisJobRecordV1>, DurableCoordinatorError> {
        let stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        self.store
            .history(job_id)
            .map_err(DurableCoordinatorError::Persistence)
    }

    fn map_queue_error<T>(
        &self,
        error: QueueError,
        mut stopped: std::sync::MutexGuard<'_, bool>,
    ) -> Result<T, DurableCoordinatorError> {
        if let QueueError::Persistence(persistence) = error {
            if requires_stop(persistence) {
                *stopped = true;
            }
            Err(DurableCoordinatorError::Persistence(persistence))
        } else {
            Err(DurableCoordinatorError::Queue(error))
        }
    }

    fn map_persistence_error<T>(
        &self,
        error: PersistenceError,
        mut stopped: std::sync::MutexGuard<'_, bool>,
    ) -> Result<T, DurableCoordinatorError> {
        if requires_stop(error) {
            *stopped = true;
        }
        Err(DurableCoordinatorError::Persistence(error))
    }
}

impl DurableAnalysisCoordinator {
    /// Opens operation-aware storage. Authentication precedes restart writes.
    pub fn open_operations(root: PathBuf) -> Result<Self, DurableCoordinatorError> {
        let store = PersistentAnalysisJobStore::open_unclassified(root)
            .map_err(DurableCoordinatorError::Persistence)?;
        let operations = store
            .scan_operations()
            .map_err(DurableCoordinatorError::Persistence)?;
        let jobs = store.scan().map_err(DurableCoordinatorError::Persistence)?;
        let mut bound = std::collections::BTreeSet::new();
        let mut repairs = Vec::new();
        for history in operations.values() {
            let op = history.last().ok_or(DurableCoordinatorError::Persistence(
                PersistenceError::InvalidChain,
            ))?;
            if let Some(id) = op.job_id() {
                if !bound.insert(id.to_owned()) {
                    return Err(DurableCoordinatorError::Persistence(
                        PersistenceError::InvalidChain,
                    ));
                }
                if let Some(job) = jobs.get(id).and_then(|h| h.first()) {
                    if !matches!(
                        op.state(),
                        OperationState::Accepting | OperationState::Accepted
                    ) || op.frozen_input().and_then(|x| serde_json::to_vec(x).ok())
                        != serde_json::to_vec(job.input()).ok()
                    {
                        return Err(DurableCoordinatorError::Persistence(
                            PersistenceError::InvalidChain,
                        ));
                    }
                } else if op.state() == OperationState::Accepted {
                    return Err(DurableCoordinatorError::Persistence(
                        PersistenceError::InvalidChain,
                    ));
                }
            }
            if op.state() == OperationState::Accepting {
                let now = op.updated_at_ms();
                let next = if op.job_id().is_some_and(|id| jobs.contains_key(id)) {
                    op.accept(now)
                } else {
                    op.mark_unknown(now)
                }
                .map_err(DurableCoordinatorError::Operation)?;
                repairs.push(next);
            }
        }
        // Every chain was authenticated before the first recovery append.
        for repair in repairs {
            store
                .append_operation(&repair)
                .map_err(DurableCoordinatorError::Persistence)?;
        }
        store
            .classify_restart()
            .map_err(DurableCoordinatorError::Persistence)?;
        Ok(Self {
            store,
            queue: AnalysisJobQueue::default(),
            stopped: Mutex::new(false),
            reservation: Mutex::new(None),
        })
    }
    /// Pure inspection under the existing store lock, including when stopped.
    pub fn inspect_operation(&self, id: &str) -> Result<Vec<Operation>, DurableCoordinatorError> {
        let _guard = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        self.store
            .authenticate_operation_bindings()
            .map_err(DurableCoordinatorError::Persistence)?;
        self.store
            .operation_history(id)
            .map_err(DurableCoordinatorError::Persistence)
    }
    pub fn inspect_job(
        &self,
        id: &str,
    ) -> Result<Vec<AnalysisJobRecordV1>, DurableCoordinatorError> {
        let _guard = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        self.store
            .authenticate_operation_bindings()
            .map_err(DurableCoordinatorError::Persistence)?;
        self.store
            .history(id)
            .map_err(DurableCoordinatorError::Persistence)
    }
    /// Distinguishes an authenticated absence from an unreadable or corrupt chain.
    pub fn inspect_operation_optional(
        &self,
        id: &str,
    ) -> Result<Option<Operation>, DurableCoordinatorError> {
        let _guard = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        self.store
            .authenticate_operation_bindings()
            .map_err(DurableCoordinatorError::Persistence)?;
        let mut all = self
            .store
            .scan_operations()
            .map_err(DurableCoordinatorError::Persistence)?;
        Ok(all.remove(id).and_then(|mut history| history.pop()))
    }

    pub fn inspect_job_optional(
        &self,
        id: &str,
    ) -> Result<Option<AnalysisJobRecordV1>, DurableCoordinatorError> {
        let _guard = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        self.store
            .authenticate_operation_bindings()
            .map_err(DurableCoordinatorError::Persistence)?;
        let mut all = self
            .store
            .scan()
            .map_err(DurableCoordinatorError::Persistence)?;
        Ok(all.remove(id).and_then(|mut history| history.pop()))
    }

    /// Prevents further dispatch without changing authenticated saved history.
    pub fn stop_dispatch(&self) -> Result<(), DurableCoordinatorError> {
        *self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)? = true;
        Ok(())
    }

    pub fn is_stopped(&self) -> Result<bool, DurableCoordinatorError> {
        self.stopped
            .lock()
            .map(|guard| *guard)
            .map_err(|_| DurableCoordinatorError::LockUnavailable)
    }

    /// Authenticates a historical report without reconstructing runtime assets.
    pub fn inspect_report(&self, id: &str) -> Result<AnalysisReport, DurableCoordinatorError> {
        let _guard = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        self.store
            .authenticate_operation_bindings()
            .map_err(DurableCoordinatorError::Persistence)?;
        let history = self
            .store
            .history(id)
            .map_err(DurableCoordinatorError::Persistence)?;
        let record = history.last().ok_or(DurableCoordinatorError::Persistence(
            PersistenceError::InvalidChain,
        ))?;
        let reference = record.report().ok_or(DurableCoordinatorError::Persistence(
            PersistenceError::ReportBindingMismatch,
        ))?;
        self.store
            .read_saved_report(record, reference)
            .map_err(DurableCoordinatorError::Persistence)
    }

    pub fn allocate_operation(
        &self,
        context: OperationContext,
        now: u64,
    ) -> Result<Operation, DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        let id = ygo_storage::secure_random_hex(16)
            .map_err(|_| DurableCoordinatorError::Queue(QueueError::IdUnavailable))?;
        let op =
            Operation::allocate(id, context, now).map_err(DurableCoordinatorError::Operation)?;
        if let Err(e) = self.store.append_operation(&op) {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(e));
        }
        Ok(op)
    }
    /// Resolves a new operation through the actual W1-A freeze gate. Repeated
    /// commands return saved metadata without touching drafts or assets.
    #[allow(clippy::too_many_arguments)]
    pub fn submit_operation(
        &self,
        id: &str,
        command: OperationCommand,
        context: &OperationContext,
        now: u64,
        drafts: &ygo_storage::DeckDraftStore,
        snapshots: &ygo_storage::SnapshotStore,
        engine: ygo_engine_adapter::ProcessEngineConfig,
    ) -> Result<Operation, DurableCoordinatorError> {
        self.submit_operation_core(id, command, context, now, |cmd, ctx| {
            super::freeze_analysis_input(
                drafts,
                super::AnalysisFreezeSpec {
                    draft_id: cmd.draft_id.clone(),
                    expected_revision: cmd.draft_revision.clone(),
                    opening_hand: cmd.opening_hand.clone(),
                    seed: cmd.seed,
                    rules: cmd.rules.clone(),
                    catalog_id: cmd.catalog_id.clone(),
                    banlist_id: cmd.banlist_id.clone(),
                    as_of: cmd.as_of.clone(),
                    search: cmd.search.clone(),
                },
                engine,
                snapshots,
                &ctx.default_catalog_id,
            )
        })
    }
    fn submit_operation_core(
        &self,
        id: &str,
        command: OperationCommand,
        context: &OperationContext,
        now: u64,
        freeze: impl FnOnce(
            &OperationCommand,
            &OperationContext,
        ) -> Result<FrozenAnalysisInput, super::AnalysisFreezeError>,
    ) -> Result<Operation, DurableCoordinatorError> {
        let submission = self.begin_operation(id, command, context, now)?;
        match submission.ticket {
            None => Ok(submission.record),
            Some(ticket) => {
                let frozen = freeze(
                    ticket.operation.command().expect("accepting command"),
                    ticket.operation.context(),
                );
                self.finish_operation_core(ticket, now, frozen)
            }
        }
    }

    pub fn begin_operation(
        &self,
        id: &str,
        command: OperationCommand,
        context: &OperationContext,
        now: u64,
    ) -> Result<OperationSubmission, DurableCoordinatorError> {
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if let Err(e) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(e));
        }
        let mut op = self
            .store
            .operation_history(id)
            .map_err(DurableCoordinatorError::Persistence)?
            .pop()
            .ok_or(DurableCoordinatorError::Persistence(
                PersistenceError::InvalidChain,
            ))?;
        let digest = command
            .checksum(op.context())
            .map_err(DurableCoordinatorError::Operation)?;
        if now < op.updated_at_ms() {
            return Err(DurableCoordinatorError::Operation(
                AnalysisOperationError::TimeInvalid,
            ));
        }
        if let Some(saved) = op.command_sha256() {
            if saved != digest {
                return Err(DurableCoordinatorError::Persistence(
                    PersistenceError::RevisionConflict,
                ));
            }
            return Ok(OperationSubmission {
                record: op,
                ticket: None,
            });
        }
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        let context_changed =
            serde_json::to_vec(context).ok() != serde_json::to_vec(op.context()).ok();
        let mut reservation = self
            .reservation
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        let full = reservation.is_some()
            || self
                .queue
                .snapshot()
                .map_err(DurableCoordinatorError::Queue)?
                .queued
                .is_some();
        if context_changed || full {
            let code = if context_changed {
                "analysis_operation_context_changed"
            } else {
                "analysis_queue_full"
            };
            op = op
                .reject(command, 409, code, now)
                .map_err(DurableCoordinatorError::Operation)?;
            if let Err(e) = self.store.append_operation(&op) {
                *stopped = true;
                return Err(DurableCoordinatorError::Persistence(e));
            }
            return Ok(OperationSubmission {
                record: op,
                ticket: None,
            });
        }
        let job_id = ygo_storage::secure_random_hex(16)
            .map_err(|_| DurableCoordinatorError::Queue(QueueError::IdUnavailable))?;
        if self
            .store
            .scan()
            .map_err(DurableCoordinatorError::Persistence)?
            .contains_key(&job_id)
            || self
                .store
                .scan_operations()
                .map_err(DurableCoordinatorError::Persistence)?
                .values()
                .any(|h| {
                    h.last()
                        .is_some_and(|o| o.job_id() == Some(job_id.as_str()))
                })
        {
            return Err(DurableCoordinatorError::Queue(QueueError::IdUnavailable));
        }
        op = op
            .begin(command.clone(), job_id.clone(), now)
            .map_err(DurableCoordinatorError::Operation)?;
        if let Err(e) = self.store.append_operation(&op) {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(e));
        }
        *reservation = Some(id.to_owned());
        drop(reservation);
        drop(stopped);
        Ok(OperationSubmission {
            record: op.clone(),
            ticket: Some(OperationFreezeTicket { operation: op }),
        })
    }

    /// Completes freezing outside the coordination lock, then durably commits it.
    #[allow(clippy::too_many_arguments)]
    pub fn finish_operation(
        &self,
        ticket: OperationFreezeTicket,
        now: u64,
        drafts: &ygo_storage::DeckDraftStore,
        snapshots: &ygo_storage::SnapshotStore,
        engine: ygo_engine_adapter::ProcessEngineConfig,
    ) -> Result<Operation, DurableCoordinatorError> {
        self.finish_operation_with_clock(ticket, || now, drafts, snapshots, engine)
    }

    /// Samples completion time only after the potentially slow asset scan.
    pub fn finish_operation_with_clock(
        &self,
        ticket: OperationFreezeTicket,
        now: impl FnOnce() -> u64,
        drafts: &ygo_storage::DeckDraftStore,
        snapshots: &ygo_storage::SnapshotStore,
        engine: ygo_engine_adapter::ProcessEngineConfig,
    ) -> Result<Operation, DurableCoordinatorError> {
        let op = &ticket.operation;
        let cmd = op.command().expect("accepting command");
        let frozen = super::freeze_analysis_input(
            drafts,
            super::AnalysisFreezeSpec {
                draft_id: cmd.draft_id.clone(),
                expected_revision: cmd.draft_revision.clone(),
                opening_hand: cmd.opening_hand.clone(),
                seed: cmd.seed,
                rules: cmd.rules.clone(),
                catalog_id: cmd.catalog_id.clone(),
                banlist_id: cmd.banlist_id.clone(),
                as_of: cmd.as_of.clone(),
                search: cmd.search.clone(),
            },
            engine,
            snapshots,
            &op.context().default_catalog_id,
        );
        self.finish_operation_core(ticket, now(), frozen)
    }

    fn finish_operation_core(
        &self,
        ticket: OperationFreezeTicket,
        now: u64,
        frozen: Result<FrozenAnalysisInput, super::AnalysisFreezeError>,
    ) -> Result<Operation, DurableCoordinatorError> {
        let mut op = ticket.operation;
        let id = op.operation_id().to_owned();
        let command = op.command().expect("accepting command").clone();
        let job_id = op.job_id().expect("accepting job").to_owned();
        let mut stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
        }
        if now < op.updated_at_ms() {
            *stopped = true;
            return Err(DurableCoordinatorError::Operation(
                AnalysisOperationError::TimeInvalid,
            ));
        }
        if self
            .reservation
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?
            .as_deref()
            != Some(id.as_str())
        {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(
                PersistenceError::InvalidChain,
            ));
        }
        if let Err(error) = self.store.authenticate_operation_bindings() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(error));
        }
        let current = self
            .store
            .operation_history(&id)
            .map_err(|e| {
                *stopped = true;
                DurableCoordinatorError::Persistence(e)
            })?
            .pop()
            .ok_or(DurableCoordinatorError::Persistence(
                PersistenceError::InvalidChain,
            ))?;
        if current.encode_json().ok() != op.encode_json().ok() {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(
                PersistenceError::InvalidChain,
            ));
        }
        let input = match frozen {
            Ok(frozen) => frozen,
            Err(error) => {
                op = op
                    .reject(
                        command,
                        if error == super::AnalysisFreezeError::RevisionConflict {
                            409
                        } else {
                            422
                        },
                        error.code(),
                        now,
                    )
                    .map_err(DurableCoordinatorError::Operation)?;
                if let Err(e) = self.store.append_operation(&op) {
                    *stopped = true;
                    return Err(DurableCoordinatorError::Persistence(e));
                }
                *self
                    .reservation
                    .lock()
                    .map_err(|_| DurableCoordinatorError::LockUnavailable)? = None;
                return Ok(op);
            }
        };
        let job =
            AnalysisJobRecordV1::new(job_id.clone(), &input, op.context().scoring.clone(), now)
                .map_err(|e| {
                    *stopped = true;
                    DurableCoordinatorError::Queue(QueueError::Job(e))
                })?;
        op = op.bind_input(job.input().clone(), now).map_err(|e| {
            *stopped = true;
            DurableCoordinatorError::Operation(e)
        })?;
        if let Err(e) = self.store.append_operation(&op) {
            *stopped = true;
            return Err(DurableCoordinatorError::Persistence(e));
        }
        let accepted = op.accept(now).map_err(DurableCoordinatorError::Operation)?;
        let outcome = self.queue.enqueue_identified_with_persist(
            job_id,
            input,
            op.context().scoring.clone(),
            now,
            |record| {
                self.store.append_initial(record.clone())?;
                self.store.append_operation(&accepted)
            },
        );
        match outcome {
            Ok(_) => {
                *self
                    .reservation
                    .lock()
                    .map_err(|_| DurableCoordinatorError::LockUnavailable)? = None;
                Ok(accepted)
            }
            Err(error) => {
                *stopped = true;
                Err(DurableCoordinatorError::Queue(error))
            }
        }
    }
}

#[cfg(test)]
mod operation_tests {
    use super::*;
    use crate::workbench_analysis::{operations::*, tests::fixtures};
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Barrier,
    };
    fn root() -> PathBuf {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h21-analysis-operation-tests")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        root
    }
    fn setup(
        root: &std::path::Path,
    ) -> (
        ygo_storage::DeckDraftStore,
        ygo_storage::SnapshotStore,
        ygo_engine_adapter::ProcessEngineConfig,
        AnalysisOperationContext,
        AnalysisOperationCommand,
    ) {
        let f = root.join("fixture");
        std::fs::create_dir_all(&f).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&f);
        std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
        let saved = drafts.create(draft.clone()).unwrap();
        let context = AnalysisOperationContext {
            scoring: ScoringConfig::default(),
            default_catalog_id: catalog,
            configuration_sha256: "a".repeat(64),
        };
        let command = AnalysisOperationCommand {
            draft_id: saved.id,
            draft_revision: saved.revision,
            opening_hand: draft.main[..5].to_vec(),
            seed: 1,
            rules: "ocg-mr5".into(),
            catalog_id: None,
            banlist_id: banlist,
            as_of: "2026-10-30".into(),
            search: Default::default(),
        };
        (drafts, snapshots, engine, context, command)
    }
    #[test]
    fn split_completion_samples_clock_after_freeze_and_stopped_queries_remain_read_only() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let started = c
            .begin_operation(op.operation_id(), cmd, &ctx, 101)
            .unwrap();
        let accepted = c
            .finish_operation_with_clock(
                started.ticket.unwrap(),
                || 200,
                &drafts,
                &snapshots,
                engine,
            )
            .unwrap();
        assert_eq!(accepted.updated_at_ms(), 200);
        c.stop_dispatch().unwrap();
        assert!(c.is_stopped().unwrap());
        assert_eq!(
            c.inspect_operation(op.operation_id())
                .unwrap()
                .last()
                .unwrap()
                .state(),
            OperationState::Accepted
        );
        assert_eq!(c.inspect_job(accepted.job_id().unwrap()).unwrap().len(), 1);
        assert_eq!(
            c.claim_next(201).err(),
            Some(DurableCoordinatorError::Stopped)
        );
    }

    #[test]
    fn split_completion_time_rollback_stops_without_publishing_task() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let started = c
            .begin_operation(op.operation_id(), cmd, &ctx, 101)
            .unwrap();
        let job_id = started.record.job_id().unwrap().to_owned();
        assert!(c
            .finish_operation(started.ticket.unwrap(), 100, &drafts, &snapshots, engine)
            .is_err());
        assert!(c.is_stopped().unwrap());
        assert!(c.inspect_job(&job_id).is_err());
        assert_eq!(
            c.inspect_operation(op.operation_id())
                .unwrap()
                .last()
                .unwrap()
                .state(),
            OperationState::Accepting
        );
    }

    #[test]
    fn split_accepting_is_saved_before_freeze_and_duplicates_have_no_ticket() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let started = c
            .begin_operation(op.operation_id(), cmd.clone(), &ctx, 101)
            .unwrap();
        assert_eq!(started.record.state(), OperationState::Accepting);
        assert!(c.inspect_job(started.record.job_id().unwrap()).is_err());
        let repeated = c
            .begin_operation(op.operation_id(), cmd, &ctx, 102)
            .unwrap();
        assert!(repeated.ticket.is_none());
        let accepted = c
            .finish_operation(started.ticket.unwrap(), 103, &drafts, &snapshots, engine)
            .unwrap();
        assert_eq!(accepted.state(), OperationState::Accepted);
        assert_eq!(accepted.updated_at_ms(), 103);
    }
    #[test]
    fn operation_actual_freeze_duplicate_and_restart_do_not_resubmit() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let saved = c
            .submit_operation(
                op.operation_id(),
                cmd.clone(),
                &ctx,
                101,
                &drafts,
                &snapshots,
                engine,
            )
            .unwrap();
        assert_eq!(saved.state(), AnalysisOperationState::Accepted);
        let job_id = saved.job_id().unwrap().to_owned();
        let again = c
            .submit_operation_core(op.operation_id(), cmd.clone(), &ctx, 102, |_, _| {
                panic!("duplicate froze")
            })
            .unwrap();
        assert_eq!(again.encode_json().unwrap(), saved.encode_json().unwrap());
        let mut changed = cmd.clone();
        changed.seed = 9;
        assert!(c
            .submit_operation_core(op.operation_id(), changed, &ctx, 102, |_, _| panic!(
                "conflict froze"
            ))
            .is_err());
        assert_eq!(c.inspect_job(&job_id).unwrap().len(), 1);
        drop(c);
        assert!(PersistentAnalysisJobStore::open(root.join("store")).is_err());
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        assert_eq!(
            c.inspect_job(&job_id).unwrap().last().unwrap().state(),
            super::super::jobs::AnalysisJobState::Interrupted
        );
        assert_eq!(
            c.submit_operation_core(op.operation_id(), cmd, &ctx, 103, |_, _| panic!(
                "restart froze"
            ))
            .unwrap()
            .state(),
            AnalysisOperationState::Accepted
        );
        assert!(c.snapshot().unwrap().queued.is_none());
    }
    #[test]
    fn reservation_blocks_old_submit_and_parallel_duplicates_freeze_once() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let frozen = crate::workbench_analysis::freeze_analysis_input(
            &drafts,
            crate::workbench_analysis::AnalysisFreezeSpec {
                draft_id: cmd.draft_id.clone(),
                expected_revision: cmd.draft_revision.clone(),
                opening_hand: cmd.opening_hand.clone(),
                seed: cmd.seed,
                rules: cmd.rules.clone(),
                catalog_id: cmd.catalog_id.clone(),
                banlist_id: cmd.banlist_id.clone(),
                as_of: cmd.as_of.clone(),
                search: cmd.search.clone(),
            },
            engine,
            &snapshots,
            &ctx.default_catalog_id,
        )
        .unwrap();
        let c = Arc::new(DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap());
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let gate = Arc::new(Barrier::new(2));
        let count = Arc::new(AtomicUsize::new(0));
        let (c2, ctx2, cmd2, gate2, count2, input) = (
            c.clone(),
            ctx.clone(),
            cmd.clone(),
            gate.clone(),
            count.clone(),
            frozen.clone(),
        );
        let id = op.operation_id().to_owned();
        let thread = std::thread::spawn(move || {
            c2.submit_operation_core(&id, cmd2, &ctx2, 101, |_, _| {
                count2.fetch_add(1, Ordering::SeqCst);
                gate2.wait();
                gate2.wait();
                Ok(input)
            })
        });
        gate.wait();
        let other = c.allocate_operation(ctx.clone(), 101).unwrap();
        let capacity = c
            .submit_operation_core(other.operation_id(), cmd.clone(), &ctx, 101, |_, _| {
                panic!("other operation stole reservation")
            })
            .unwrap();
        assert_eq!(capacity.error_code(), Some("analysis_queue_full"));
        assert_eq!(
            c.submit_operation_core(op.operation_id(), cmd, &ctx, 101, |_, _| panic!(
                "duplicate"
            ))
            .unwrap()
            .state(),
            AnalysisOperationState::Accepting
        );
        assert!(matches!(
            c.submit(frozen, ctx.scoring.clone(), 101),
            Err(DurableCoordinatorError::Queue(QueueError::Full))
        ));
        gate.wait();
        assert_eq!(
            thread.join().unwrap().unwrap().state(),
            AnalysisOperationState::Accepted
        );
        assert_eq!(count.load(Ordering::SeqCst), 1);
    }
    #[test]
    fn task_commit_before_accepted_is_repaired_without_requeue() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        c.store.operation_failure.store(2, Ordering::SeqCst);
        assert!(c
            .submit_operation(
                op.operation_id(),
                cmd.clone(),
                &ctx,
                101,
                &drafts,
                &snapshots,
                engine
            )
            .is_err());
        assert!(matches!(
            c.snapshot(),
            Err(DurableCoordinatorError::Stopped)
        ));
        let current = c
            .inspect_operation(op.operation_id())
            .unwrap()
            .pop()
            .unwrap();
        assert_eq!(current.state(), AnalysisOperationState::Accepting);
        let id = current.job_id().unwrap().to_owned();
        assert_eq!(c.inspect_job(&id).unwrap().len(), 1);
        drop(c);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        assert_eq!(
            c.inspect_operation(op.operation_id())
                .unwrap()
                .pop()
                .unwrap()
                .state(),
            AnalysisOperationState::Accepted
        );
        assert_eq!(c.inspect_job(&id).unwrap().len(), 2);
        assert!(c.snapshot().unwrap().queued.is_none());
        assert_eq!(
            c.submit_operation_core(op.operation_id(), cmd, &ctx, 102, |_, _| panic!(
                "recovery froze"
            ))
            .unwrap()
            .job_id(),
            Some(id.as_str())
        );
    }

    #[test]
    fn preparation_rejection_and_changed_context_never_refreeze() {
        let root = root();
        let (_, _, _, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let rejected = c
            .submit_operation_core(op.operation_id(), cmd.clone(), &ctx, 101, |_, _| {
                Err(super::super::AnalysisFreezeError::OpeningHandInvalid)
            })
            .unwrap();
        assert_eq!(rejected.state(), AnalysisOperationState::Rejected);
        assert_eq!(rejected.rejection().unwrap().http_status, 422);
        assert_eq!(
            c.submit_operation_core(op.operation_id(), cmd.clone(), &ctx, 102, |_, _| panic!(
                "rejected refroze"
            ))
            .unwrap()
            .state(),
            AnalysisOperationState::Rejected
        );
        let op = c.allocate_operation(ctx.clone(), 103).unwrap();
        let mut changed = ctx.clone();
        changed.configuration_sha256 = "f".repeat(64);
        assert_eq!(
            c.submit_operation_core(op.operation_id(), cmd, &changed, 104, |_, _| panic!(
                "changed context froze"
            ))
            .unwrap()
            .error_code(),
            Some("analysis_operation_context_changed")
        );
        assert!(c.snapshot().unwrap().queued.is_none());
    }
    #[test]
    fn beforewrite_failure_stops_dispatch() {
        let root = root();
        let (_, _, _, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        c.store.operation_failure.store(0, Ordering::SeqCst);
        assert!(c
            .submit_operation_core(op.operation_id(), cmd, &ctx, 101, |_, _| panic!(
                "write failed but froze"
            ))
            .is_err());
        assert!(matches!(
            c.claim_next(102),
            Err(DurableCoordinatorError::Stopped)
        ));
        assert_eq!(
            c.inspect_operation(op.operation_id())
                .unwrap()
                .pop()
                .unwrap()
                .state(),
            AnalysisOperationState::Allocated
        );
    }
    #[test]
    fn accepting_without_job_becomes_unknown_without_adapter() {
        let root = root();
        let (_, _, _, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let accepting = op.begin(cmd.clone(), "1".repeat(32), 101).unwrap();
        c.store.append_operation(&accepting).unwrap();
        drop(c);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let unknown = c
            .submit_operation_core(op.operation_id(), cmd, &ctx, 102, |_, _| {
                panic!("unknown refroze")
            })
            .unwrap();
        assert_eq!(unknown.state(), AnalysisOperationState::Unknown);
        assert!(c.snapshot().unwrap().queued.is_none());
        assert!(c.inspect_job("11111111111111111111111111111111").is_err());
    }
    #[test]
    fn corrupt_operation_binding_blocks_claim_before_running_revision() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let accepted = c
            .submit_operation(
                op.operation_id(),
                cmd,
                &ctx,
                101,
                &drafts,
                &snapshots,
                engine,
            )
            .unwrap();
        let id = accepted.job_id().unwrap();
        let path = c
            .store
            .root
            .join("operations")
            .join(op.operation_id())
            .join("revisions/4.json");
        let mut value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        value["record"]["frozen_input"]["request"]["seed"] = serde_json::json!(9);
        std::fs::write(path, serde_json::to_vec(&value).unwrap()).unwrap();
        assert!(c.claim_next(102).is_err());
        assert!(matches!(
            c.snapshot(),
            Err(DurableCoordinatorError::Stopped)
        ));
        assert_eq!(c.store.history(id).unwrap().len(), 1);
    }
    #[test]
    fn post_freeze_missing_intent_stops_without_task() {
        let root = root();
        let (_, _, _, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let result = c.submit_operation_core(op.operation_id(), cmd, &ctx, 101, |_, _| {
            let path = c
                .store
                .root
                .join("operations")
                .join(op.operation_id())
                .join("revisions/2.json");
            std::fs::write(path, b"{}").unwrap();
            Err(super::super::AnalysisFreezeError::OpeningHandInvalid)
        });
        assert!(result.is_err());
        assert!(matches!(
            c.snapshot(),
            Err(DurableCoordinatorError::Stopped)
        ));
        assert_eq!(
            std::fs::read_dir(c.store.root.join("jobs"))
                .unwrap()
                .count(),
            0
        );
    }
    #[test]
    fn duplicate_job_binding_is_rejected_before_dispatch() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let accepted = c
            .submit_operation(
                op.operation_id(),
                cmd.clone(),
                &ctx,
                101,
                &drafts,
                &snapshots,
                engine,
            )
            .unwrap();
        let duplicate = c.allocate_operation(ctx, 102).unwrap();
        let begin = duplicate
            .begin(cmd, accepted.job_id().unwrap().into(), 103)
            .unwrap();
        c.store.append_operation(&begin).unwrap();
        let bind = begin
            .bind_input(accepted.frozen_input().unwrap().clone(), 104)
            .unwrap();
        c.store.append_operation(&bind).unwrap();
        c.store
            .append_operation(&bind.accept(105).unwrap())
            .unwrap();
        assert!(c.inspect_operation(op.operation_id()).is_err());
        assert!(c.claim_next(106).is_err());
        assert_eq!(
            c.store.history(accepted.job_id().unwrap()).unwrap().len(),
            1
        );
    }
    #[test]
    fn operation_predecessor_and_output_collision_are_rejected() {
        let root = root();
        let (_, _, _, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx, 100).unwrap();
        let first = c
            .store
            .root
            .join("operations")
            .join(op.operation_id())
            .join("revisions/1.json");
        let bytes = std::fs::read(&first).unwrap();
        assert!(c.store.append_operation(&op).is_err());
        assert_eq!(std::fs::read(&first).unwrap(), bytes);
        c.store
            .append_operation(&op.begin(cmd, "1".repeat(32), 101).unwrap())
            .unwrap();
        let second = first.with_file_name("2.json");
        let mut value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&second).unwrap()).unwrap();
        value["previous_sha256"] = serde_json::json!("f".repeat(64));
        std::fs::write(second, serde_json::to_vec(&value).unwrap()).unwrap();
        assert!(c.inspect_operation(op.operation_id()).is_err());
        drop(c);
        assert!(DurableAnalysisCoordinator::open_operations(root.join("store")).is_err());
    }
    #[test]
    fn disk_revision_conflict_stops_but_caller_revision_conflict_does_not() {
        let root = root();
        let (drafts, snapshots, engine, ctx, cmd) = setup(&root);
        let c = DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap();
        let op = c.allocate_operation(ctx.clone(), 100).unwrap();
        let accepted = c
            .submit_operation(
                op.operation_id(),
                cmd,
                &ctx,
                101,
                &drafts,
                &snapshots,
                engine,
            )
            .unwrap();
        let id = accepted.job_id().unwrap();
        assert!(c.cancel(id, 2, 102).is_err());
        assert!(c.snapshot().is_ok());
        let queued = c.store.history(id).unwrap().pop().unwrap();
        let changed = queued.transition(1, AnalysisJobEvent::Start, 103).unwrap();
        // Model a durable change between the queue's accepted state and its
        // next expected-revision commit, without bypassing chain parsing.
        c.store.append_expected(id, 1, changed).unwrap();
        assert!(matches!(
            c.claim_next(104),
            Err(DurableCoordinatorError::Persistence(
                PersistenceError::RevisionConflict
            ))
        ));
        assert!(matches!(
            c.claim_next(105),
            Err(DurableCoordinatorError::Stopped)
        ));
        assert_eq!(c.inspect_job(id).unwrap().len(), 2);
    }
}
