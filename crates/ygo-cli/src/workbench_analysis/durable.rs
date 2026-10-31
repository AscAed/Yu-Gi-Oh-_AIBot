//! Persistence-first coordination for the in-process analysis queue.
//!
//! This coordinates metadata and private reports only. It does not execute an
//! analysis or authenticate the origin of a report.

use super::{
    jobs::{AnalysisJobEvent, AnalysisJobFailure, AnalysisJobRecordV1},
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
}

impl DurableCoordinatorError {
    pub fn code(self) -> &'static str {
        match self {
            Self::Stopped => "job_coordinator_stopped",
            Self::LockUnavailable => "job_coordinator_unavailable",
            Self::AssetMismatch => "analysis_asset_mismatch",
            Self::Persistence(error) => error.code(),
            Self::Queue(error) => error.code(),
        }
    }
}

/// A persistence-first coordinator. The OS store lock is acquired before any
/// queue operation and held for the coordinator lifetime.
pub struct DurableAnalysisCoordinator {
    store: PersistentAnalysisJobStore,
    queue: AnalysisJobQueue,
    stopped: Mutex<bool>,
}

impl DurableAnalysisCoordinator {
    pub fn open(root: PathBuf) -> Result<Self, DurableCoordinatorError> {
        let store =
            PersistentAnalysisJobStore::open(root).map_err(DurableCoordinatorError::Persistence)?;
        Ok(Self {
            store,
            queue: AnalysisJobQueue::default(),
            stopped: Mutex::new(false),
        })
    }

    #[cfg(test)]
    pub(super) fn inject_uncertain_after_next_publish(&self) {
        self.store.inject_uncertain_after_next_publish();
    }

    #[cfg(test)]
    pub(super) fn inject_failure_before_next_publish(&self) {
        self.store.inject_failure_before_next_publish();
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
        let stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
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
        let stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
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
        let stopped = self
            .stopped
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        if *stopped {
            return Err(DurableCoordinatorError::Stopped);
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
            if persistence == PersistenceError::CommitUncertain {
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
        if error == PersistenceError::CommitUncertain {
            *stopped = true;
        }
        Err(DurableCoordinatorError::Persistence(error))
    }
}
