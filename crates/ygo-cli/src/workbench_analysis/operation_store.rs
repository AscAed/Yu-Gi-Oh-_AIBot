//! Operation chains use the job store's existing lifetime lock.
use super::{
    jobs::strict_json_value,
    operations::{AnalysisOperationRecordV1 as Record, AnalysisOperationState as State},
    persistence::{PersistenceError as Error, PersistentAnalysisJobStore},
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fs};
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    schema_version: u16,
    kind: String,
    operation_id: String,
    revision: u64,
    previous_sha256: Option<String>,
    record_sha256: String,
    record: serde_json::Value,
}
fn id_ok(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn valid_edge(old: &Record, next: &Record) -> Result<(), Error> {
    let time = next.updated_at_ms();
    let result = match (old.state(), next.state()) {
        (State::Allocated, State::Accepting) => old.begin(
            next.command().ok_or(Error::InvalidChain)?.clone(),
            next.job_id().ok_or(Error::InvalidChain)?.to_owned(),
            time,
        ),
        (State::Allocated | State::Accepting, State::Rejected) => {
            let r = next.rejection().ok_or(Error::InvalidChain)?;
            old.reject(
                next.command().ok_or(Error::InvalidChain)?.clone(),
                r.http_status,
                &r.error_code,
                time,
            )
        }
        (State::Accepting, State::Accepting) => old.bind_input(
            next.frozen_input().ok_or(Error::InvalidChain)?.clone(),
            time,
        ),
        (State::Accepting, State::Accepted) => old.accept(time),
        (State::Accepting, State::Unknown) => old.mark_unknown(time),
        _ => return Err(Error::InvalidChain),
    }
    .map_err(|_| Error::InvalidChain)?;
    if result.encode_json().ok() != next.encode_json().ok() {
        return Err(Error::InvalidChain);
    }
    Ok(())
}
pub(super) struct AuthenticatedChains {
    pub operations: BTreeMap<String, Vec<Record>>,
    pub jobs: BTreeMap<String, Vec<super::jobs::AnalysisJobRecordV1>>,
    heads: BTreeMap<std::path::PathBuf, Vec<u8>>,
}

impl PersistentAnalysisJobStore {
    pub(super) fn authenticate_operation_bindings(&self) -> Result<(), Error> {
        self.authenticate_chains().map(|_| ())
    }
    pub(super) fn authenticate_chains(&self) -> Result<AuthenticatedChains, Error> {
        let jobs = self.scan()?;
        let operations = self.scan_operations()?;
        let mut ids = std::collections::BTreeSet::new();
        for op in operations.values().filter_map(|h| h.last()) {
            if let Some(id) = op.job_id() {
                if !ids.insert(id.to_owned()) {
                    return Err(Error::InvalidChain);
                }
                if let Some(job) = jobs.get(id).and_then(|h| h.first()) {
                    if !matches!(op.state(), State::Accepting | State::Accepted)
                        || op.frozen_input().and_then(|x| serde_json::to_vec(x).ok())
                            != serde_json::to_vec(job.input()).ok()
                    {
                        return Err(Error::InvalidChain);
                    }
                } else if op.state() == State::Accepted {
                    return Err(Error::InvalidChain);
                }
            }
        }
        let mut heads = BTreeMap::new();
        for (id, history) in &operations {
            let last = history.last().ok_or(Error::InvalidChain)?;
            let path = self
                .root
                .join("operations")
                .join(id)
                .join("revisions")
                .join(format!("{}.json", last.revision()));
            heads.insert(path.clone(), fs::read(path).map_err(|_| Error::Io)?);
        }
        for (id, history) in &jobs {
            let last = history.last().ok_or(Error::InvalidChain)?;
            let path = self
                .root
                .join("jobs")
                .join(id)
                .join("revisions")
                .join(format!("{}.json", last.revision()));
            heads.insert(path.clone(), fs::read(path).map_err(|_| Error::Io)?);
        }
        Ok(AuthenticatedChains {
            operations,
            jobs,
            heads,
        })
    }
    pub(super) fn recover_authenticated(&self) -> Result<(), Error> {
        let chains = self.authenticate_chains()?;
        let now = super::persistence::now_ms()?;
        let mut operations = Vec::new();
        let mut jobs = Vec::new();
        // Construct every transition before publishing any recovery revision.
        for history in chains.operations.values() {
            let old = history.last().ok_or(Error::InvalidChain)?;
            if old.state() == State::Accepting {
                let next = if old.job_id().is_some_and(|id| chains.jobs.contains_key(id)) {
                    old.accept(old.updated_at_ms())
                } else {
                    old.mark_unknown(old.updated_at_ms())
                }
                .map_err(|_| Error::InvalidChain)?;
                let path = self
                    .root
                    .join("operations")
                    .join(old.operation_id())
                    .join("revisions")
                    .join(format!("{}.json", old.revision()));
                operations.push((
                    path.clone(),
                    chains.heads.get(&path).ok_or(Error::InvalidChain)?.clone(),
                    next,
                ));
            }
        }
        for history in chains.jobs.values() {
            let old = history.last().ok_or(Error::InvalidChain)?;
            if matches!(
                old.state(),
                super::jobs::AnalysisJobState::Queued | super::jobs::AnalysisJobState::Running
            ) {
                let next = old
                    .transition(
                        old.revision(),
                        super::jobs::AnalysisJobEvent::ClassifyRestart,
                        now,
                    )
                    .map_err(|_| Error::InvalidChain)?;
                let path = self
                    .root
                    .join("jobs")
                    .join(old.job_id())
                    .join("revisions")
                    .join(format!("{}.json", old.revision()));
                jobs.push((
                    path.clone(),
                    chains.heads.get(&path).ok_or(Error::InvalidChain)?.clone(),
                    old.revision(),
                    next,
                ));
            }
        }
        for (path, bytes, next) in operations {
            if fs::read(path).map_err(|_| Error::Io)? != bytes {
                return Err(Error::RevisionConflict);
            }
            self.append_operation(&next)?;
            #[cfg(test)]
            super::durable::crash_checkpoint("recovery_first_operation_classified_before_next");
            #[cfg(test)]
            super::durable::crash_checkpoint(
                "recovery_mixed_operations_first_classified_before_next",
            );
        }
        #[cfg(test)]
        super::durable::crash_checkpoint("recovery_operation_repaired_before_task_classified");
        for (path, bytes, revision, next) in jobs {
            if fs::read(path).map_err(|_| Error::Io)? != bytes {
                return Err(Error::RevisionConflict);
            }
            self.append_expected(next.job_id(), revision, next.clone())?;
            #[cfg(test)]
            super::durable::crash_checkpoint("recovery_first_task_classified_before_next");
            #[cfg(test)]
            super::durable::crash_checkpoint("recovery_first_task_classified_before_running");
            #[cfg(test)]
            super::durable::crash_checkpoint("recovery_unknown_before_queued");
        }
        Ok(())
    }

    pub(super) fn scan_operations(&self) -> Result<BTreeMap<String, Vec<Record>>, Error> {
        let root = self.root.join("operations");
        let mut out = BTreeMap::new();
        if !root.exists() {
            return Ok(out);
        }
        if !ygo_storage::safe_store_metadata(&root)
            .map_err(|_| Error::InvalidPath)?
            .is_dir()
        {
            return Err(Error::InvalidPath);
        }
        for entry in fs::read_dir(root).map_err(|_| Error::Io)? {
            let entry = entry.map_err(|_| Error::Io)?;
            let id = entry
                .file_name()
                .into_string()
                .map_err(|_| Error::InvalidPath)?;
            if !id_ok(&id) {
                return Err(Error::InvalidPath);
            }
            out.insert(id.clone(), self.operation_history(&id)?);
        }
        Ok(out)
    }
    pub(super) fn operation_history(&self, id: &str) -> Result<Vec<Record>, Error> {
        if !id_ok(id) {
            return Err(Error::InvalidPath);
        }
        let dir = self.root.join("operations").join(id);
        if !ygo_storage::safe_store_metadata(&dir)
            .map_err(|_| Error::InvalidPath)?
            .is_dir()
        {
            return Err(Error::InvalidPath);
        }
        let names = fs::read_dir(&dir)
            .map_err(|_| Error::Io)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| Error::Io)?;
        if names.len() != 1 || names[0].file_name() != "revisions" {
            return Err(Error::InvalidPath);
        }
        let revisions = dir.join("revisions");
        if !ygo_storage::safe_store_metadata(&revisions)
            .map_err(|_| Error::InvalidPath)?
            .is_dir()
        {
            return Err(Error::InvalidPath);
        }
        let mut files = BTreeMap::new();
        for e in fs::read_dir(revisions).map_err(|_| Error::Io)? {
            let e = e.map_err(|_| Error::Io)?;
            let name = e
                .file_name()
                .into_string()
                .map_err(|_| Error::InvalidPath)?;
            let n = name
                .strip_suffix(".json")
                .and_then(|s| s.parse::<u64>().ok())
                .ok_or(Error::InvalidPath)?;
            if n == 0
                || name != format!("{n}.json")
                || !ygo_storage::safe_store_metadata(&e.path())
                    .map_err(|_| Error::InvalidPath)?
                    .is_file()
            {
                return Err(Error::InvalidPath);
            }
            files.insert(n, e.path());
        }
        if files.is_empty() {
            return Err(Error::InvalidChain);
        }
        let mut history = Vec::new();
        let mut previous = None;
        for (i, (n, path)) in files.into_iter().enumerate() {
            if n != i as u64 + 1 {
                return Err(Error::InvalidChain);
            }
            if fs::metadata(&path).map_err(|_| Error::Io)?.len() > 1024 * 1024 {
                return Err(Error::RecordInvalid);
            }
            let bytes = fs::read(path).map_err(|_| Error::Io)?;
            let value = strict_json_value(&bytes).map_err(|_| Error::RecordInvalid)?;
            let keys = [
                "schema_version",
                "kind",
                "operation_id",
                "revision",
                "previous_sha256",
                "record_sha256",
                "record",
            ];
            let object = value.as_object().ok_or(Error::RecordInvalid)?;
            if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
                return Err(Error::RecordInvalid);
            }
            let envelope: Envelope =
                serde_json::from_value(value).map_err(|_| Error::RecordInvalid)?;
            let record = Record::read_json(
                &serde_json::to_vec(&envelope.record).map_err(|_| Error::RecordInvalid)?,
            )
            .map_err(|_| Error::RecordInvalid)?;
            if envelope.schema_version != 1
                || envelope.kind != "workbench_analysis_operation_revision"
                || envelope.operation_id != id
                || envelope.revision != n
                || record.operation_id() != id
                || record.revision() != n
                || envelope.previous_sha256 != previous
                || envelope.record_sha256
                    != ygo_storage::hash(&record.encode_json().map_err(|_| Error::RecordInvalid)?)
            {
                return Err(Error::InvalidChain);
            }
            if let Some(old) = history.last() {
                valid_edge(old, &record)?;
            } else if record.state() != State::Allocated {
                return Err(Error::InvalidChain);
            }
            previous = Some(ygo_storage::hash(&bytes));
            history.push(record);
        }
        Ok(history)
    }
    pub(super) fn append_operation(&self, record: &Record) -> Result<(), Error> {
        record.validate().map_err(|_| Error::RecordInvalid)?;
        let dir = self
            .root
            .join("operations")
            .join(record.operation_id())
            .join("revisions");
        let previous = if record.revision() == 1 {
            if dir.exists() {
                return Err(Error::RevisionConflict);
            }
            None
        } else {
            let history = self.operation_history(record.operation_id())?;
            let old = history.last().ok_or(Error::InvalidChain)?;
            if old.revision() + 1 != record.revision() {
                return Err(Error::RevisionConflict);
            }
            valid_edge(old, record)?;
            Some(ygo_storage::hash(
                &fs::read(dir.join(format!("{}.json", old.revision()))).map_err(|_| Error::Io)?,
            ))
        };
        ygo_storage::prepare_store_directory(&dir).map_err(|_| Error::InvalidPath)?;
        let raw = record.encode_json().map_err(|_| Error::RecordInvalid)?;
        let envelope = Envelope {
            schema_version: 1,
            kind: "workbench_analysis_operation_revision".into(),
            operation_id: record.operation_id().into(),
            revision: record.revision(),
            previous_sha256: previous,
            record_sha256: ygo_storage::hash(&raw),
            record: serde_json::from_slice(&raw).map_err(|_| Error::RecordInvalid)?,
        };
        let bytes = serde_json::to_vec_pretty(&envelope).map_err(|_| Error::RecordInvalid)?;
        let path = dir.join(format!("{}.json", record.revision()));
        #[cfg(test)]
        {
            use std::sync::atomic::Ordering;
            let remaining = self.operation_failure.load(Ordering::SeqCst);
            if remaining == 0 {
                self.operation_failure.store(usize::MAX, Ordering::SeqCst);
                return Err(Error::Io);
            }
            if remaining != usize::MAX {
                self.operation_failure.fetch_sub(1, Ordering::SeqCst);
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
            "operation",
            &logical_state,
            record.revision(),
            super::persistence::FaultPhase::BeforePublish,
        )?;
        ygo_storage::publish_exclusive_file(&path, &bytes).map_err(|_| Error::CommitUncertain)?;
        #[cfg(test)]
        self.check_logical_fault(
            "operation",
            &logical_state,
            record.revision(),
            super::persistence::FaultPhase::AfterPublish,
        )?;
        #[cfg(test)]
        self.check_logical_fault(
            "operation",
            &logical_state,
            record.revision(),
            super::persistence::FaultPhase::Reread,
        )?;
        if self
            .operation_history(record.operation_id())
            .ok()
            .and_then(|h| h.last().and_then(|r| r.encode_json().ok()))
            != Some(raw)
        {
            return Err(Error::CommitUncertain);
        }
        Ok(())
    }
}
