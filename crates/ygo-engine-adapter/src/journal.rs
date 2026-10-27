//! Durable, per-scope call accounting. A reservation never starts an engine.
use crate::*;
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex, MutexGuard},
};

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CallPurpose {
    Execution,
    Replay,
    RuleVerification,
    Probe,
    Witness,
    Audit,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct LedgerStats {
    pub consumed: usize,
    pub reserved: usize,
    pub completed: usize,
    pub unknown: usize,
    #[serde(default)]
    pub abandoned: usize,
    pub limit: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct JournalRecovery {
    pub tail_hash: String,
    pub additional_charge: bool,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RecoveryMarker {
    prefix_hash: String,
    valid_length: u64,
    tail_hash: String,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum Entry {
    Header {
        version: u16,
        scope: String,
        context: String,
        limit: usize,
    },
    Reserve {
        token: String,
        amount: usize,
    },
    Release {
        token: String,
    },
    Begin {
        call_id: u64,
        request: String,
        purpose: CallPurpose,
        reservation: Option<String>,
    },
    Complete {
        call_id: u64,
        result: String,
        raw_hash: String,
        normalized_hash: String,
    },
    Recovery {
        evidence: JournalRecovery,
    },
    Checkpoint {
        name: String,
        blob: String,
        consumed: usize,
        charged_sequence: String,
    },
    Abandon {
        call_id: u64,
        reason: String,
    },
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    sequence: usize,
    previous: String,
    entry: Entry,
    hash: String,
}

#[derive(Clone)]
struct Call {
    request: String,
    purpose: CallPurpose,
    completed: Option<(String, String, String)>,
    abandoned: bool,
}
struct State {
    file: File,
    sequence: usize,
    last_hash: String,
    calls: BTreeMap<u64, Call>,
    reserved: BTreeMap<String, usize>,
    limit: usize,
    faulted: bool,
    recoveries: Vec<JournalRecovery>,
    checkpoints: BTreeMap<String, (String, usize, String)>,
    checkpoint_budgets: BTreeMap<String, LedgerStats>,
    checkpoint_reservations: BTreeMap<String, BTreeMap<String, usize>>,
}

/// An exclusively locked budget journal. Keep one instance alive for a scope.
pub struct CallJournal {
    state: Mutex<State>,
    blobs: PathBuf,
}

/// Read-only authenticated view of an existing journal. This type deliberately
/// exposes no accounting or recovery mutation methods.
pub struct ReadOnlyJournal {
    journal: CallJournal,
    recovery_markers: BTreeMap<String, (String, u64)>,
}

fn fail(code: &str, message: impl ToString) -> WorkerError {
    WorkerError::new(code, "call_journal", message.to_string())
}
fn io_fail(error: impl ToString) -> WorkerError {
    fail("journal_io", error)
}
fn encoded<T: Serialize>(value: &T) -> Result<Vec<u8>, WorkerError> {
    serde_json::to_vec(value).map_err(io_fail)
}
fn request_hash(request: &RunDuelRequest) -> Result<String, WorkerError> {
    let mut value = serde_json::to_value(request).map_err(io_fail)?;
    // Paths and wall-clock limits are deployment diagnostics, not duel input.
    value.as_object_mut().unwrap().remove("engine");
    Ok(digest(&encoded(&value)?))
}
fn record_hash(sequence: usize, previous: &str, entry: &Entry) -> Result<String, WorkerError> {
    Ok(digest(&encoded(&(sequence, previous, entry))?))
}

fn open_locked(path: &Path) -> Result<File, WorkerError> {
    let mut options = OpenOptions::new();
    options.create(true).write(true).read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0);
    }
    let file = options.open(path).map_err(io_fail)?;
    #[cfg(unix)]
    {
        use std::os::fd::AsRawFd;
        extern "C" {
            fn flock(fd: i32, operation: i32) -> i32;
        }
        // LOCK_EX | LOCK_NB: a second process must not share this budget.
        if unsafe { flock(file.as_raw_fd(), 2 | 4) } != 0 {
            return Err(io_fail(std::io::Error::last_os_error()));
        }
    }
    Ok(file)
}

impl State {
    fn sequence_id(&self, count: usize) -> Result<String, WorkerError> {
        let sequence: Vec<_> = self
            .calls
            .iter()
            .take(count)
            .map(|(id, c)| {
                (
                    id,
                    &c.request,
                    c.purpose,
                    c.completed.as_ref().map(|(_, _, hash)| hash),
                )
            })
            .collect();
        Ok(digest(&encoded(&sequence)?))
    }
    fn stats(&self) -> LedgerStats {
        let completed = self
            .calls
            .values()
            .filter(|c| c.completed.is_some())
            .count();
        LedgerStats {
            consumed: self.calls.len(),
            reserved: self.reserved.values().sum(),
            completed,
            unknown: self.calls.len() - completed,
            abandoned: self.calls.values().filter(|c| c.abandoned).count(),
            limit: self.limit,
        }
    }
    fn check(&self, entry: &Entry) -> Result<(), WorkerError> {
        let bad = || fail("journal_contract", "invalid accounting transition");
        match entry {
            Entry::Header { .. } if self.sequence != 0 => return Err(bad()),
            Entry::Reserve { token, amount } => {
                if token.is_empty() || *amount == 0 || self.reserved.contains_key(token) {
                    return Err(bad());
                }
                let s = self.stats();
                if *amount > self.limit.saturating_sub(s.consumed + s.reserved) {
                    return Err(fail("journal_budget", "reservation exceeds scope budget"));
                }
            }
            Entry::Release { token } if !self.reserved.contains_key(token) => return Err(bad()),
            Entry::Begin {
                call_id,
                reservation,
                ..
            } => {
                if *call_id != self.calls.len() as u64 + 1 {
                    return Err(bad());
                }
                let s = self.stats();
                let held = match reservation {
                    Some(token) => *self.reserved.get(token).ok_or_else(bad)?,
                    None => 0,
                };
                if s.consumed >= self.limit || (held == 0 && s.consumed + s.reserved >= self.limit)
                {
                    return Err(fail("journal_budget", "scope call budget exhausted"));
                }
            }
            Entry::Complete { call_id, .. } => {
                if self
                    .calls
                    .get(call_id)
                    .map_or(true, |c| c.completed.is_some() || c.abandoned)
                {
                    return Err(bad());
                }
            }
            Entry::Recovery { evidence } => {
                if self
                    .recoveries
                    .iter()
                    .any(|r| r.tail_hash == evidence.tail_hash)
                    || evidence.additional_charge
                        != (self.stats().unknown == self.stats().abandoned)
                {
                    return Err(bad());
                }
                if evidence.additional_charge && self.calls.len() >= self.limit {
                    return Err(fail(
                        "journal_budget",
                        "torn record requires an uncertain debit; scope budget exhausted",
                    ));
                }
            }
            Entry::Checkpoint {
                name,
                consumed,
                charged_sequence,
                ..
            } if name.is_empty()
                || (name.starts_with("immutable/") && self.checkpoints.contains_key(name))
                || *consumed != self.calls.len()
                || self.stats().unknown != self.stats().abandoned
                || *charged_sequence != self.sequence_id(*consumed)? =>
            {
                return Err(bad());
            }
            Entry::Abandon { call_id, reason }
                if reason.trim().is_empty()
                    || self
                        .calls
                        .get(call_id)
                        .map_or(true, |c| c.completed.is_some() || c.abandoned) =>
            {
                return Err(bad())
            }
            _ => {}
        }
        Ok(())
    }
    fn apply(&mut self, entry: Entry) {
        match entry {
            Entry::Header { limit, .. } => self.limit = limit,
            Entry::Reserve { token, amount } => {
                self.reserved.insert(token, amount);
            }
            Entry::Release { token } => {
                self.reserved.remove(&token);
            }
            Entry::Begin {
                call_id,
                request,
                purpose,
                reservation,
            } => {
                if let Some(token) = reservation {
                    let amount = self.reserved.get_mut(&token).unwrap();
                    *amount -= 1;
                    if *amount == 0 {
                        self.reserved.remove(&token);
                    }
                }
                self.calls.insert(
                    call_id,
                    Call {
                        request,
                        purpose,
                        completed: None,
                        abandoned: false,
                    },
                );
            }
            Entry::Complete {
                call_id,
                result,
                raw_hash,
                normalized_hash,
            } => {
                self.calls.get_mut(&call_id).unwrap().completed =
                    Some((result, raw_hash, normalized_hash));
            }
            Entry::Recovery { evidence } => {
                if evidence.additional_charge {
                    // A partially persisted debit cannot be refunded. Reservations are cancelled,
                    // and this conservative charge is disclosed separately from completed calls.
                    self.reserved.clear();
                    self.calls.insert(
                        self.calls.len() as u64 + 1,
                        Call {
                            request: format!("unknown-tail-{}", evidence.tail_hash),
                            purpose: CallPurpose::Audit,
                            completed: None,
                            abandoned: true,
                        },
                    );
                }
                self.recoveries.push(evidence);
            }
            Entry::Checkpoint {
                name,
                blob,
                consumed,
                charged_sequence,
            } => {
                self.checkpoint_budgets.insert(name.clone(), self.stats());
                self.checkpoint_reservations
                    .insert(name.clone(), self.reserved.clone());
                self.checkpoints
                    .insert(name, (blob, consumed, charged_sequence));
            }
            Entry::Abandon { call_id, .. } => {
                self.calls.get_mut(&call_id).unwrap().abandoned = true
            }
        }
    }
    fn append(&mut self, entry: Entry) -> Result<(), WorkerError> {
        if self.faulted {
            return Err(io_fail(
                "journal requires reopening after persistence failure",
            ));
        }
        self.check(&entry)?;
        let hash = record_hash(self.sequence, &self.last_hash, &entry)?;
        let record = Record {
            sequence: self.sequence,
            previous: self.last_hash.clone(),
            entry: entry.clone(),
            hash: hash.clone(),
        };
        let mut bytes = encoded(&record)?;
        bytes.push(b'\n');
        if let Err(e) = self
            .file
            .seek(SeekFrom::End(0))
            .and_then(|_| self.file.write_all(&bytes))
            .and_then(|_| self.file.sync_all())
        {
            self.faulted = true;
            return Err(io_fail(e));
        }
        self.apply(entry);
        self.sequence += 1;
        self.last_hash = hash;
        Ok(())
    }
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum StoredResult {
    Duel {
        result: Box<DuelResult>,
        event_chunks: Vec<String>,
    },
    Error {
        error: WorkerError,
    },
}

impl CallJournal {
    /// Inspect an existing journal without creating directories, appending a
    /// header, recovering a torn tail, or otherwise changing evidence.
    pub fn inspect_existing(
        path: impl AsRef<Path>,
        scope: &str,
        context: &str,
        limit: usize,
    ) -> Result<Option<ReadOnlyJournal>, WorkerError> {
        if scope.is_empty() || context.is_empty() || limit == 0 {
            return Err(fail(
                "journal_contract",
                "scope, context and positive limit required",
            ));
        }
        let path = path.as_ref();
        let mut options = OpenOptions::new();
        options.read(true);
        #[cfg(windows)]
        {
            use std::os::windows::fs::OpenOptionsExt;
            // Allow concurrent readers, while denying a writer or deletion for
            // the lifetime of the returned view.
            options.share_mode(1);
        }
        let mut file = match options.open(path) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(io_fail(error)),
        };
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            extern "C" {
                fn flock(fd: i32, operation: i32) -> i32;
            }
            // LOCK_SH | LOCK_NB: inspectors may coexist, writers may not.
            if unsafe { flock(file.as_raw_fd(), 1 | 4) } != 0 {
                return Err(io_fail(std::io::Error::last_os_error()));
            }
        }
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).map_err(io_fail)?;
        if bytes.is_empty() || bytes.last() != Some(&b'\n') {
            return Err(fail(
                "journal_readonly_incomplete",
                "empty or truncated journal cannot be inspected",
            ));
        }
        let mut state = State {
            file,
            sequence: 0,
            last_hash: String::new(),
            calls: BTreeMap::new(),
            reserved: BTreeMap::new(),
            limit,
            faulted: false,
            recoveries: Vec::new(),
            checkpoints: BTreeMap::new(),
            checkpoint_budgets: BTreeMap::new(),
            checkpoint_reservations: BTreeMap::new(),
        };
        let lines = bytes[..bytes.len() - 1]
            .split(|byte| *byte == b'\n')
            .collect::<Vec<_>>();
        if lines.iter().any(|line| line.is_empty()) {
            return Err(fail(
                "journal_readonly_incomplete",
                "blank journal record cannot be inspected",
            ));
        }
        let mut recovery_markers = BTreeMap::new();
        let mut byte_offset = 0usize;
        for line in lines {
            let record: Record = serde_json::from_slice(line).map_err(io_fail)?;
            if record.sequence != state.sequence
                || record.previous != state.last_hash
                || record.hash != record_hash(record.sequence, &record.previous, &record.entry)?
            {
                return Err(fail(
                    "journal_hash",
                    "journal sequence or hash chain mismatch",
                ));
            }
            if state.sequence == 0 {
                match &record.entry {
                    Entry::Header {
                        version: 1,
                        scope: found_scope,
                        context: found_context,
                        limit: found_limit,
                    } if found_scope == scope
                        && found_context == context
                        && *found_limit == limit => {}
                    _ => {
                        return Err(fail(
                            "journal_context",
                            "scope, context, version or budget changed",
                        ))
                    }
                }
            }
            if let Entry::Recovery { evidence } = &record.entry {
                if recovery_markers
                    .insert(
                        evidence.tail_hash.clone(),
                        (record.previous.clone(), byte_offset as u64),
                    )
                    .is_some()
                {
                    return Err(fail(
                        "journal_contract",
                        "duplicate recovery marker binding",
                    ));
                }
            }
            state.check(&record.entry)?;
            state.apply(record.entry);
            state.sequence += 1;
            state.last_hash = record.hash;
            byte_offset += line.len() + 1;
        }
        if state.sequence == 0 {
            return Err(fail(
                "journal_readonly_incomplete",
                "journal header missing",
            ));
        }

        let mut name = path.as_os_str().to_owned();
        name.push(".blobs");
        let journal = CallJournal {
            state: Mutex::new(state),
            blobs: PathBuf::from(name),
        };
        journal.verify()?;
        journal.verify_recovery_markers(&recovery_markers)?;
        Ok(Some(ReadOnlyJournal {
            journal,
            recovery_markers,
        }))
    }

    pub fn open(
        path: impl AsRef<Path>,
        scope: &str,
        context: &str,
        limit: usize,
    ) -> Result<Arc<Self>, WorkerError> {
        if scope.is_empty() || context.is_empty() || limit == 0 {
            return Err(fail(
                "journal_contract",
                "scope, context and positive limit required",
            ));
        }
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(io_fail)?;
        }
        let mut file = open_locked(path)?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).map_err(io_fail)?;
        let valid_length = if bytes.is_empty() || bytes.last() == Some(&b'\n') {
            bytes.len()
        } else {
            bytes.iter().rposition(|b| *b == b'\n').map_or(0, |p| p + 1)
        };
        let mut state = State {
            file,
            sequence: 0,
            last_hash: String::new(),
            calls: BTreeMap::new(),
            reserved: BTreeMap::new(),
            limit,
            faulted: false,
            recoveries: Vec::new(),
            checkpoints: BTreeMap::new(),
            checkpoint_budgets: BTreeMap::new(),
            checkpoint_reservations: BTreeMap::new(),
        };
        for line in bytes[..valid_length]
            .split(|b| *b == b'\n')
            .filter(|line| !line.is_empty())
        {
            let record: Record = serde_json::from_slice(line).map_err(io_fail)?;
            if record.sequence != state.sequence
                || record.previous != state.last_hash
                || record.hash != record_hash(record.sequence, &record.previous, &record.entry)?
            {
                return Err(fail(
                    "journal_hash",
                    "journal sequence or hash chain mismatch",
                ));
            }
            if state.sequence == 0 {
                match &record.entry {
                    Entry::Header {
                        version: 1,
                        scope: s,
                        context: c,
                        limit: l,
                    } if s == scope && c == context && *l == limit => {}
                    _ => {
                        return Err(fail(
                            "journal_context",
                            "scope, context, version or budget changed",
                        ))
                    }
                }
            }
            state.check(&record.entry)?;
            state.apply(record.entry);
            state.sequence += 1;
            state.last_hash = record.hash;
        }
        if state.sequence == 0 {
            if !bytes.is_empty() {
                return Err(fail(
                    "journal_torn_header",
                    "cannot bind a partially written header to this context",
                ));
            }
            state.append(Entry::Header {
                version: 1,
                scope: scope.into(),
                context: context.into(),
                limit,
            })?;
        }
        let mut name = path.as_os_str().to_owned();
        name.push(".blobs");
        let journal = Arc::new(Self {
            state: Mutex::new(state),
            blobs: PathBuf::from(name),
        });
        fs::create_dir_all(journal.blobs.join("results")).map_err(io_fail)?;
        fs::create_dir_all(journal.blobs.join("events")).map_err(io_fail)?;
        fs::create_dir_all(journal.blobs.join("recoveries")).map_err(io_fail)?;
        fs::create_dir_all(journal.blobs.join("checkpoints")).map_err(io_fail)?;
        journal.recover_tail(&bytes, valid_length)?;
        Ok(journal)
    }
    fn recover_tail(&self, bytes: &[u8], valid_length: usize) -> Result<(), WorkerError> {
        let mut state = self.lock()?;
        if valid_length < bytes.len() {
            let tail = &bytes[valid_length..];
            let tail_hash = self.put_blob("events", tail)?;
            let marker = RecoveryMarker {
                prefix_hash: state.last_hash.clone(),
                valid_length: valid_length as u64,
                tail_hash,
            };
            // Persist the marker before truncation: a second crash cannot erase this debit.
            self.put_blob("recoveries", &encoded(&marker)?)?;
        }
        let mut pending = Vec::new();
        for file in fs::read_dir(self.blobs.join("recoveries")).map_err(io_fail)? {
            let file = file.map_err(io_fail)?;
            let name = file.file_name().to_string_lossy().into_owned();
            let hash = name
                .strip_suffix(".json")
                .ok_or_else(|| fail("journal_contract", "unexpected recovery file"))?;
            let marker: RecoveryMarker =
                serde_json::from_slice(&self.blob("recoveries", hash)?).map_err(io_fail)?;
            self.blob("events", &marker.tail_hash)?;
            if !state
                .recoveries
                .iter()
                .any(|r| r.tail_hash == marker.tail_hash)
            {
                if marker.prefix_hash != state.last_hash
                    || marker.valid_length != valid_length as u64
                {
                    return Err(fail("journal_contract", "pending recovery prefix differs"));
                }
                pending.push(marker);
            }
        }
        if pending.len() > 1 {
            return Err(fail("journal_contract", "conflicting recovery markers"));
        }
        if let Some(marker) = pending.pop() {
            let entry = Entry::Recovery {
                evidence: JournalRecovery {
                    tail_hash: marker.tail_hash,
                    additional_charge: state.stats().unknown == state.stats().abandoned,
                },
            };
            state.check(&entry)?;
            state
                .file
                .set_len(marker.valid_length)
                .and_then(|_| state.file.sync_all())
                .map_err(io_fail)?;
            state.append(entry)?;
        }
        Ok(())
    }
    fn lock(&self) -> Result<MutexGuard<'_, State>, WorkerError> {
        self.state
            .lock()
            .map_err(|_| io_fail("poisoned journal lock"))
    }
    pub fn stats(&self) -> Result<LedgerStats, WorkerError> {
        Ok(self.lock()?.stats())
    }
    /// Disclose an uncertain completed/crashed call without refunding its debit.
    pub fn acknowledge_unknown(&self, call_id: u64, reason: &str) -> Result<(), WorkerError> {
        self.lock()?.append(Entry::Abandon {
            call_id,
            reason: reason.into(),
        })
    }
    pub fn unresolved_calls(&self) -> Result<Vec<u64>, WorkerError> {
        Ok(self
            .lock()?
            .calls
            .iter()
            .filter(|(_, c)| c.completed.is_none() && !c.abandoned)
            .map(|(id, _)| *id)
            .collect())
    }
    pub fn call_purpose(&self, call_id: u64) -> Result<CallPurpose, WorkerError> {
        self.lock()?
            .calls
            .get(&call_id)
            .map(|c| c.purpose)
            .ok_or_else(|| fail("journal_call", "unknown call"))
    }
    pub fn recoveries(&self) -> Result<Vec<JournalRecovery>, WorkerError> {
        Ok(self.lock()?.recoveries.clone())
    }
    /// Persist complete search state only after every started call has a result.
    pub fn save_checkpoint(
        &self,
        name: &str,
        search: &serde_json::Value,
    ) -> Result<(), WorkerError> {
        let mut state = self.lock()?;
        let consumed = state.calls.len();
        let charged_sequence = state.sequence_id(consumed)?;
        let payload = serde_json::json!({"search":search,"budget":state.stats(),"reservations":state.reserved,
            "charged_sequence":charged_sequence});
        if name.starts_with("immutable/") {
            if let Some((hash, count, sequence)) = state.checkpoints.get(name) {
                if *hash == digest(&encoded(&payload)?)
                    && *count == consumed
                    && *sequence == charged_sequence
                {
                    return Ok(());
                }
                return Err(fail(
                    "journal_checkpoint",
                    "immutable checkpoint already exists",
                ));
            }
        }
        let blob = self.put_blob("checkpoints", &encoded(&payload)?)?;
        state.append(Entry::Checkpoint {
            name: name.into(),
            blob,
            consumed,
            charged_sequence,
        })
    }
    pub fn checkpoint(&self, name: &str) -> Result<Option<serde_json::Value>, WorkerError> {
        let state = self.lock()?;
        let Some((hash, count, sequence)) = state.checkpoints.get(name) else {
            return Ok(None);
        };
        if state.sequence_id(*count)? != *sequence {
            return Err(fail("journal_checkpoint", "charged prefix changed"));
        }
        let payload: serde_json::Value =
            serde_json::from_slice(&self.blob("checkpoints", hash)?).map_err(io_fail)?;
        if payload.get("charged_sequence").and_then(|v| v.as_str()) != Some(sequence.as_str()) {
            return Err(fail("journal_checkpoint", "checkpoint sequence mismatch"));
        }
        Ok(Some(
            payload
                .get("search")
                .ok_or_else(|| fail("journal_checkpoint", "missing search state"))?
                .clone(),
        ))
    }
    /// Charged prefix saved with a verified checkpoint, for pre-call evidence.
    pub fn checkpoint_consumed(&self, name: &str) -> Result<Option<usize>, WorkerError> {
        if self.checkpoint(name)?.is_none() {
            return Ok(None);
        }
        Ok(self
            .lock()?
            .checkpoints
            .get(name)
            .map(|(_, count, _)| *count))
    }
    /// Budget reconstructed from ledger entries at this checkpoint, rather than
    /// trusted from the caller's search payload or a later ledger balance.
    pub fn checkpoint_budget(&self, name: &str) -> Result<Option<LedgerStats>, WorkerError> {
        if self.checkpoint(name)?.is_none() {
            return Ok(None);
        }
        Ok(self.lock()?.checkpoint_budgets.get(name).cloned())
    }
    /// Charged request-purpose-result identity at an immutable checkpoint.
    /// This stays stable when later calls extend the same journal.
    pub fn checkpoint_charged_sequence_id(
        &self,
        name: &str,
    ) -> Result<Option<String>, WorkerError> {
        if self.checkpoint(name)?.is_none() {
            return Ok(None);
        }
        Ok(self
            .lock()?
            .checkpoints
            .get(name)
            .map(|(_, _, sequence)| sequence.clone()))
    }
    /// A safe resume must preserve reservation ownership as well as totals.
    /// Both are reconstructed from journal entries, not the checkpoint payload.
    pub fn matches_checkpoint_state(&self, name: &str) -> Result<bool, WorkerError> {
        if self.checkpoint(name)?.is_none() {
            return Ok(false);
        }
        let state = self.lock()?;
        Ok(state.checkpoint_budgets.get(name) == Some(&state.stats())
            && state.checkpoint_reservations.get(name) == Some(&state.reserved))
    }
    pub fn reserve(&self, token: &str, amount: usize) -> Result<(), WorkerError> {
        self.lock()?.append(Entry::Reserve {
            token: token.into(),
            amount,
        })
    }
    pub fn release(&self, token: &str) -> Result<(), WorkerError> {
        self.lock()?.append(Entry::Release {
            token: token.into(),
        })
    }
    pub fn remaining_reservation(&self, token: &str) -> Result<Option<usize>, WorkerError> {
        Ok(self.lock()?.reserved.get(token).copied())
    }
    /// The returned call is charged even if the process crashes immediately.
    pub fn begin_call(
        &self,
        request: &RunDuelRequest,
        purpose: CallPurpose,
        reservation: Option<&str>,
    ) -> Result<u64, WorkerError> {
        let mut state = self.lock()?;
        let id = state.calls.len() as u64 + 1;
        state.append(Entry::Begin {
            call_id: id,
            request: request_hash(request)?,
            purpose,
            reservation: reservation.map(str::to_owned),
        })?;
        Ok(id)
    }
    fn put_blob(&self, folder: &str, bytes: &[u8]) -> Result<String, WorkerError> {
        let hash = digest(bytes);
        let path = self.blobs.join(folder).join(format!("{hash}.json"));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                file.write_all(bytes)
                    .and_then(|_| file.sync_all())
                    .map_err(io_fail)?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                if fs::read(&path).map_err(io_fail)? != bytes {
                    return Err(fail("journal_blob_hash", "existing blob is corrupt"));
                }
            }
            Err(e) => return Err(io_fail(e)),
        }
        Ok(hash)
    }
    fn blob(&self, folder: &str, hash: &str) -> Result<Vec<u8>, WorkerError> {
        if hash.len() != 64 || !hash.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(fail("journal_blob_hash", "invalid content address"));
        }
        let bytes =
            fs::read(self.blobs.join(folder).join(format!("{hash}.json"))).map_err(io_fail)?;
        if digest(&bytes) != hash {
            return Err(fail("journal_blob_hash", "result evidence was changed"));
        }
        Ok(bytes)
    }
    fn complete(
        &self,
        call_id: u64,
        outcome: &Result<DuelResult, WorkerError>,
    ) -> Result<(), WorkerError> {
        let (stored, raw, normalized) = match outcome {
            Ok(result) => {
                let raw = digest(&encoded(result)?);
                let mut normalized = result.clone();
                normalized.peak_working_set_bytes = None;
                let normalized = digest(&encoded(&normalized)?);
                let mut chunks = Vec::new();
                for chunk in result.events.chunks(64) {
                    chunks.push(self.put_blob("events", &encoded(&chunk)?)?);
                }
                let mut shell = result.clone();
                shell.events.clear();
                (
                    StoredResult::Duel {
                        result: Box::new(shell),
                        event_chunks: chunks,
                    },
                    raw,
                    normalized,
                )
            }
            Err(error) => {
                let hash = digest(&encoded(error)?);
                (
                    StoredResult::Error {
                        error: error.clone(),
                    },
                    hash.clone(),
                    hash,
                )
            }
        };
        let result = self.put_blob("results", &encoded(&stored)?)?;
        self.lock()?.append(Entry::Complete {
            call_id,
            result,
            raw_hash: raw,
            normalized_hash: normalized,
        })
    }
    /// Explicit resume only; ordinary adapter calls always consume a new debit.
    pub fn load_result(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<DuelResult>, WorkerError> {
        self.load_outcome(call_id, request)?.transpose()
    }
    /// Distinguish a recorded worker error from a corrupt or mismatched journal.
    /// None is a charged call whose result is still unknown; it is never free.
    pub fn load_outcome(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        let call = self
            .lock()?
            .calls
            .get(&call_id)
            .cloned()
            .ok_or_else(|| fail("journal_call", "unknown call"))?;
        if call.request != request_hash(request)? {
            return Err(fail("journal_request", "resume input differs"));
        }
        self.restore(&call)
    }
    fn restore(&self, call: &Call) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        let Some((reference, raw_hash, normalized_hash)) = &call.completed else {
            return Ok(None);
        };
        match serde_json::from_slice::<StoredResult>(&self.blob("results", reference)?)
            .map_err(io_fail)?
        {
            StoredResult::Duel {
                mut result,
                event_chunks,
            } => {
                if !result.events.is_empty() {
                    return Err(fail("journal_contract", "events must be chunked"));
                }
                for chunk in event_chunks {
                    result.events.extend(
                        serde_json::from_slice::<Vec<CoreEventFrame>>(
                            &self.blob("events", &chunk)?,
                        )
                        .map_err(io_fail)?,
                    );
                }
                if digest(&encoded(&result)?) != *raw_hash {
                    return Err(fail("journal_result", "raw result hash mismatch"));
                }
                let mut normalized = result.clone();
                normalized.peak_working_set_bytes = None;
                if digest(&encoded(&normalized)?) != *normalized_hash {
                    return Err(fail("journal_result", "normalized result hash mismatch"));
                }
                Ok(Some(Ok(*result)))
            }
            StoredResult::Error { error } => {
                if digest(&encoded(&error)?) != *raw_hash || raw_hash != normalized_hash {
                    return Err(fail("journal_result", "error hash mismatch"));
                }
                Ok(Some(Err(error)))
            }
        }
    }
    /// Verify every referenced result/chunk and the latest search checkpoints.
    pub fn verify(&self) -> Result<(), WorkerError> {
        let (calls, names) = {
            let state = self.lock()?;
            (
                state.calls.values().cloned().collect::<Vec<_>>(),
                state.checkpoints.keys().cloned().collect::<Vec<_>>(),
            )
        };
        for call in calls {
            self.restore(&call)?;
        }
        for name in names {
            self.checkpoint(&name)?;
        }
        Ok(())
    }

    fn verify_recovery_markers(
        &self,
        expected_markers: &BTreeMap<String, (String, u64)>,
    ) -> Result<(), WorkerError> {
        let recovery_dir = self.blobs.join("recoveries");
        let mut recorded = self
            .lock()?
            .recoveries
            .iter()
            .map(|recovery| recovery.tail_hash.clone())
            .collect::<BTreeSet<_>>();
        if !recovery_dir.exists() {
            if recorded.is_empty() {
                return Ok(());
            }
            return Err(fail("journal_blob_hash", "recovery evidence is missing"));
        }
        for item in fs::read_dir(&recovery_dir).map_err(io_fail)? {
            let item = item.map_err(io_fail)?;
            let file_type = item.file_type().map_err(io_fail)?;
            if !file_type.is_file() {
                return Err(fail(
                    "journal_contract",
                    "unexpected recovery evidence entry",
                ));
            }
            let filename = item.file_name().to_string_lossy().into_owned();
            let marker_hash = filename
                .strip_suffix(".json")
                .ok_or_else(|| fail("journal_contract", "unexpected recovery evidence name"))?;
            let bytes = fs::read(item.path()).map_err(io_fail)?;
            if digest(&bytes) != marker_hash {
                return Err(fail(
                    "journal_blob_hash",
                    "recovery marker content address mismatch",
                ));
            }
            let marker: RecoveryMarker = serde_json::from_slice(&bytes).map_err(io_fail)?;
            if expected_markers.get(&marker.tail_hash)
                != Some(&(marker.prefix_hash.clone(), marker.valid_length))
            {
                return Err(fail(
                    "journal_recovery_binding",
                    "recovery marker prefix or length differs from its journal record",
                ));
            }
            self.blob("events", &marker.tail_hash)?;
            if !recorded.remove(&marker.tail_hash) {
                return Err(fail(
                    "journal_pending_recovery",
                    "pending recovery marker requires writable recovery",
                ));
            }
        }
        if !recorded.is_empty() {
            return Err(fail("journal_blob_hash", "recovery marker is missing"));
        }
        Ok(())
    }
    /// Stable charged-call sequence; excludes machine diagnostics and storage layout.
    pub fn charged_sequence_id(&self) -> Result<String, WorkerError> {
        let state = self.lock()?;
        state.sequence_id(state.calls.len())
    }
}

impl ReadOnlyJournal {
    pub fn stats(&self) -> Result<LedgerStats, WorkerError> {
        self.journal.stats()
    }

    pub fn checkpoint(&self, name: &str) -> Result<Option<serde_json::Value>, WorkerError> {
        self.journal.checkpoint(name)
    }

    pub fn checkpoint_consumed(&self, name: &str) -> Result<Option<usize>, WorkerError> {
        self.journal.checkpoint_consumed(name)
    }

    pub fn checkpoint_budget(&self, name: &str) -> Result<Option<LedgerStats>, WorkerError> {
        self.journal.checkpoint_budget(name)
    }

    pub fn checkpoint_charged_sequence_id(
        &self,
        name: &str,
    ) -> Result<Option<String>, WorkerError> {
        self.journal.checkpoint_charged_sequence_id(name)
    }

    pub fn charged_sequence_id(&self) -> Result<String, WorkerError> {
        self.journal.charged_sequence_id()
    }

    pub fn load_outcome(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        self.journal.load_outcome(call_id, request)
    }

    pub fn verify(&self) -> Result<(), WorkerError> {
        self.journal.verify()?;
        self.journal.verify_recovery_markers(&self.recovery_markers)
    }
}

pub struct JournaledAdapter<A> {
    inner: A,
    journal: Arc<CallJournal>,
    purpose: CallPurpose,
}
impl<A: EngineAdapter> JournaledAdapter<A> {
    pub fn new(inner: A, journal: Arc<CallJournal>, purpose: CallPurpose) -> Self {
        Self {
            inner,
            journal,
            purpose,
        }
    }
    pub fn run_reserved(
        &self,
        request: &RunDuelRequest,
        token: &str,
    ) -> Result<DuelResult, WorkerError> {
        self.execute(request, Some(token))
    }
    fn execute(
        &self,
        request: &RunDuelRequest,
        reservation: Option<&str>,
    ) -> Result<DuelResult, WorkerError> {
        let id = self
            .journal
            .begin_call(request, self.purpose, reservation)?;
        let result = self.inner.run(request);
        self.journal.complete(id, &result)?;
        result
    }
}
impl<A: EngineAdapter> EngineAdapter for JournaledAdapter<A> {
    fn doctor(&self) -> DoctorReport {
        // Delegating doctor could launch an uncharged ABI subprocess.
        DoctorReport {
            ready: false,
            assets_ok: false,
            abi_ok: false,
            smoke_ok: None,
            issues: vec![DoctorIssue {
                code: "journal_explicit_probe_required".into(),
                message:
                    "Run an explicit probe request through this adapter so the ABI call is charged"
                        .into(),
            }],
        }
    }
    fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        self.execute(request, None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    struct Count(Arc<AtomicUsize>);
    impl EngineAdapter for Count {
        fn doctor(&self) -> DoctorReport {
            panic!("doctor must not bypass accounting")
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(DuelResult::failure(fail("test", "test")))
        }
    }
    #[test]
    fn immutable_prediction_survives_a_conflicting_write_and_reopen() {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "immutable-checkpoint-{}.jsonl",
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let j = CallJournal::open(&path, "case", "frozen", 4).unwrap();
        j.save_checkpoint("immutable/prediction", &serde_json::json!({"choice":1}))
            .unwrap();
        j.save_checkpoint("immutable/prediction", &serde_json::json!({"choice":1}))
            .unwrap();
        assert!(j
            .save_checkpoint("immutable/prediction", &serde_json::json!({"choice":2}))
            .is_err());
        drop(j);
        let j = CallJournal::open(&path, "case", "frozen", 4).unwrap();
        assert_eq!(
            j.checkpoint("immutable/prediction").unwrap().unwrap(),
            serde_json::json!({"choice":1})
        );
        assert_eq!(j.stats().unwrap().consumed, 0);
    }
    #[test]
    fn failed_debit_write_prevents_engine_start() {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "debit-failure-{}-{}.jsonl",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let journal = CallJournal::open(&path, "case", "frozen", 1).unwrap();
        // Inject a genuine read-only handle; the debit write fails at the OS boundary.
        journal.lock().unwrap().file = File::open(std::env::current_exe().unwrap()).unwrap();
        let count = Arc::new(AtomicUsize::new(0));
        let adapter = JournaledAdapter::new(
            Count(count.clone()),
            journal.clone(),
            CallPurpose::Execution,
        );
        let q:RunDuelRequest=serde_json::from_value(serde_json::json!({"protocol_version":2,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":RuntimeVersions::default()})).unwrap();
        assert_eq!(adapter.run(&q).unwrap_err().code, "journal_io");
        assert_eq!(count.load(Ordering::SeqCst), 0);
        assert_eq!(journal.stats().unwrap().consumed, 0);
        assert!(!adapter.doctor().ready);
    }
}
