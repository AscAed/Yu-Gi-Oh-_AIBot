//! In-memory scheduling only. No executor, persistence or report authentication.
use super::{jobs::*, FrozenAnalysisInput};
use std::{collections::BTreeSet, sync::Mutex};
use ygo_search::combo::ScoringConfig;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum QueueError {
    Full,
    NotFound,
    CannotCancelRunning,
    TicketMismatch,
    LockUnavailable,
    IdUnavailable,
    Job(AnalysisJobError),
}
impl QueueError {
    pub fn code(self) -> &'static str {
        match self {
            Self::Full => "analysis_queue_full",
            Self::NotFound => "analysis_job_not_found",
            Self::CannotCancelRunning => "cannot_cancel_running",
            Self::TicketMismatch => "analysis_ticket_mismatch",
            Self::LockUnavailable => "analysis_queue_unavailable",
            Self::IdUnavailable => "analysis_job_id_unavailable",
            Self::Job(e) => e.code(),
        }
    }
}
impl From<AnalysisJobError> for QueueError {
    fn from(e: AnalysisJobError) -> Self {
        Self::Job(e)
    }
}
#[derive(Default)]
struct State {
    queued: Option<(AnalysisJobRecordV1, FrozenAnalysisInput)>,
    running: Option<AnalysisJobRecordV1>,
    used_ids: BTreeSet<String>,
}
/// Thread-safe active queue. Terminal records are returned to the caller, not retained.
#[derive(Default)]
pub struct AnalysisJobQueue {
    state: Mutex<State>,
}
/// Owned runtime input stays private and is intentionally not serializable.
#[derive(Clone, Debug)]
pub struct DispatchTicket {
    record: AnalysisJobRecordV1,
    input: FrozenAnalysisInput,
}
impl DispatchTicket {
    pub fn record(&self) -> &AnalysisJobRecordV1 {
        &self.record
    }
    pub fn input(&self) -> &FrozenAnalysisInput {
        &self.input
    }
}
#[derive(Clone, Debug)]
pub struct QueueSnapshot {
    pub running: Option<AnalysisJobRecordV1>,
    pub queued: Option<AnalysisJobRecordV1>,
}
impl AnalysisJobQueue {
    pub fn snapshot(&self) -> Result<QueueSnapshot, QueueError> {
        let s = self.state.lock().map_err(|_| QueueError::LockUnavailable)?;
        Ok(QueueSnapshot {
            running: s.running.clone(),
            queued: s.queued.as_ref().map(|(r, _)| r.clone()),
        })
    }
    pub fn enqueue(
        &self,
        input: FrozenAnalysisInput,
        scoring: ScoringConfig,
        now_ms: u64,
    ) -> Result<AnalysisJobRecordV1, QueueError> {
        let mut s = self.state.lock().map_err(|_| QueueError::LockUnavailable)?;
        if s.queued.is_some() {
            return Err(QueueError::Full);
        }
        let id = ygo_storage::secure_random_hex(16).map_err(|_| QueueError::IdUnavailable)?;
        if s.used_ids.contains(&id) {
            return Err(QueueError::IdUnavailable);
        }
        let r = AnalysisJobRecordV1::new(id.clone(), &input, scoring, now_ms)?;
        s.used_ids.insert(id);
        s.queued = Some((r.clone(), input));
        Ok(r)
    }
    /// Claim does not invoke an executor. Callers execute outside this lock.
    pub fn claim_next(&self, now_ms: u64) -> Result<Option<DispatchTicket>, QueueError> {
        let mut s = self.state.lock().map_err(|_| QueueError::LockUnavailable)?;
        if s.running.is_some() {
            return Ok(None);
        }
        let Some((r, _)) = s.queued.as_ref() else {
            return Ok(None);
        };
        let next = r.transition(r.revision(), AnalysisJobEvent::Start, now_ms)?;
        let (_, input) = s.queued.take().expect("queued under lock");
        s.running = Some(next.clone());
        Ok(Some(DispatchTicket {
            record: next,
            input,
        }))
    }
    pub fn cancel(
        &self,
        id: &str,
        revision: u64,
        now_ms: u64,
    ) -> Result<AnalysisJobRecordV1, QueueError> {
        let mut s = self.state.lock().map_err(|_| QueueError::LockUnavailable)?;
        if s.running.as_ref().is_some_and(|r| r.job_id() == id) {
            return Err(QueueError::CannotCancelRunning);
        }
        let (r, _) = s
            .queued
            .as_ref()
            .filter(|(r, _)| r.job_id() == id)
            .ok_or(QueueError::NotFound)?;
        let next = r.transition(revision, AnalysisJobEvent::Cancel, now_ms)?;
        s.queued = None;
        Ok(next)
    }
    /// Structural settlement only. A future publisher must authenticate and persist
    /// a report before supplying ReportPublished. No report file is certified here.
    pub fn settle(
        &self,
        ticket: &DispatchTicket,
        event: AnalysisJobEvent,
        now_ms: u64,
    ) -> Result<AnalysisJobRecordV1, QueueError> {
        let mut s = self.state.lock().map_err(|_| QueueError::LockUnavailable)?;
        let r = s.running.as_ref().ok_or(QueueError::TicketMismatch)?;
        if r.encode_json()? != ticket.record.encode_json()? {
            return Err(QueueError::TicketMismatch);
        }
        // Recheck the runtime whitelist as well as the ticket's path-free record.
        let rebuilt = AnalysisJobRecordV1::new(
            r.job_id().into(),
            &ticket.input,
            r.input().scoring.clone(),
            now_ms,
        )?;
        if rebuilt.input().binding_sha256 != r.input().binding_sha256 {
            return Err(QueueError::TicketMismatch);
        }
        let next = r.transition(ticket.record.revision(), event, now_ms)?;
        s.running = None;
        Ok(next)
    }
}
#[cfg(test)]
impl DispatchTicket {
    pub(super) fn tamper_for_test(&mut self) {
        self.input.request.seed += 1;
    }
}
