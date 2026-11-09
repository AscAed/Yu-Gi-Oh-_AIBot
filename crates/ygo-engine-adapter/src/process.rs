use crate::*;
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    process::{Command, Stdio},
    time::{Duration, Instant},
};
pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn hash_file(path: &std::path::Path) -> Result<String, String> {
    fs::read(path)
        .map(|b| digest(&b))
        .map_err(|e| e.to_string())
}
/// Windows process peak working set; unavailable platforms report null.
pub fn peak_working_set_bytes() -> Option<u64> {
    #[cfg(windows)]
    {
        #[repr(C)]
        struct Counters {
            cb: u32,
            faults: u32,
            peak: usize,
            working: usize,
            peak_paged: usize,
            paged: usize,
            peak_nonpaged: usize,
            nonpaged: usize,
            pagefile: usize,
            peak_pagefile: usize,
        }
        #[link(name = "psapi")]
        extern "system" {
            fn GetProcessMemoryInfo(
                process: *mut std::ffi::c_void,
                counters: *mut Counters,
                size: u32,
            ) -> i32;
        }
        let mut c = Counters {
            cb: std::mem::size_of::<Counters>() as u32,
            faults: 0,
            peak: 0,
            working: 0,
            peak_paged: 0,
            paged: 0,
            peak_nonpaged: 0,
            nonpaged: 0,
            pagefile: 0,
            peak_pagefile: 0,
        };
        let ok = unsafe {
            GetProcessMemoryInfo(
                -1isize as *mut std::ffi::c_void,
                &mut c,
                std::mem::size_of::<Counters>() as u32,
            )
        };
        if ok != 0 {
            Some(c.peak as u64)
        } else {
            None
        }
    }
    #[cfg(not(windows))]
    {
        None
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DoctorIssue {
    pub code: String,
    pub message: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DoctorReport {
    pub ready: bool,
    pub assets_ok: bool,
    pub abi_ok: bool,
    pub smoke_ok: Option<bool>,
    pub issues: Vec<DoctorIssue>,
}
pub trait EngineAdapter {
    fn doctor(&self) -> DoctorReport;
    fn run(&self, input: &RunDuelRequest) -> Result<DuelResult, WorkerError>;
}

/// Opt-in process observations for adapters that can report host-side pipe and
/// child-process facts. Implementations must not imply worker consumption.
pub trait ProcessObservedAdapter: EngineAdapter {
    fn run_process_observed(&self, input: &RunDuelRequest) -> ProcessObservedOutcome;
}
#[derive(Clone)]
pub struct ProcessEngineAdapter {
    pub config: ProcessEngineConfig,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessSpawnStatus {
    #[default]
    NotAttempted,
    Spawned,
    Failed,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessIoStatus {
    #[default]
    NotAttempted,
    /// The host pipe operation finished; this says nothing about remote parsing.
    Complete,
    Failed,
    Unknown,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessResponseValidation {
    #[default]
    NotAttempted,
    Parsed,
    InvalidJson,
    ProtocolVersionMismatch,
    RuntimeVersionMismatch,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessTermination {
    #[default]
    NotStarted,
    Exited,
    TimedOut,
    WaitFailed,
}

/// Host-side facts observed for one call to [`ProcessEngineAdapter::run_observed`].
/// The executable digest is read from the configured path immediately before
/// spawn; it does not authenticate the image loaded by the operating system.
/// Request and response digests cover exact pipe bytes, including a trailing
/// newline when present. A completed pipe write does not prove worker receipt.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ProcessRunObservation {
    pub worker_executable_sha256: Option<String>,
    pub spawn_status: ProcessSpawnStatus,
    pub worker_pid: Option<u32>,
    pub request_status: ProcessIoStatus,
    pub request_sha256: Option<String>,
    pub request_bytes: Option<u64>,
    pub response_status: ProcessIoStatus,
    pub response_sha256: Option<String>,
    pub response_bytes: Option<u64>,
    pub response_validation: ProcessResponseValidation,
    pub termination: ProcessTermination,
    pub exit_code: Option<i32>,
    pub elapsed_ms: u64,
}

#[derive(Debug)]
/// An adapter result with its in-memory host observations. The observation is
/// neither persisted nor authenticated and does not include worker FFI events.
pub struct ProcessObservedOutcome {
    pub result: Result<DuelResult, WorkerError>,
    pub observation: ProcessRunObservation,
}

impl ProcessEngineAdapter {
    pub fn new(config: ProcessEngineConfig) -> Self {
        Self { config }
    }

    /// Run through the normal process adapter and return the host-observed
    /// process, pipe, protocol-validation, and exit facts alongside its result.
    pub fn run_observed(&self, input: &RunDuelRequest) -> ProcessObservedOutcome {
        let mut observation = ProcessRunObservation::default();
        let start = Instant::now();
        let result = self.run_inner(input, Some(&mut observation), start);
        observation.elapsed_ms = elapsed_millis(start);
        ProcessObservedOutcome {
            result,
            observation,
        }
    }

    fn run_inner(
        &self,
        input: &RunDuelRequest,
        mut observation: Option<&mut ProcessRunObservation>,
        start: Instant,
    ) -> Result<DuelResult, WorkerError> {
        macro_rules! observe {
            ($field:ident, $value:expr) => {
                if let Some(observation) = observation.as_deref_mut() {
                    observation.$field = $value;
                }
            };
        }
        macro_rules! finish {
            ($result:expr) => {{
                observe!(elapsed_ms, elapsed_millis(start));
                return $result;
            }};
        }

        let timeout = Duration::from_millis(input.engine.timeout_ms);
        if timeout.is_zero() {
            finish!(Err(WorkerError::new("timeout", "spawn", "zero timeout")));
        }
        let bytes = match serde_json::to_vec(input) {
            Ok(bytes) => bytes,
            Err(error) => finish!(Err(WorkerError::new(
                "invalid_request",
                "encode",
                error.to_string(),
            ))),
        };
        if observation.is_some() {
            if let Some(observation) = observation.as_deref_mut() {
                observation.worker_executable_sha256 = hash_file(&self.config.worker_path).ok();
            }
        }
        let (request_sha256, request_bytes) = if observation.is_some() {
            let mut wire_request = bytes.clone();
            wire_request.push(b'\n');
            (Some(digest(&wire_request)), Some(wire_request.len() as u64))
        } else {
            (None, None)
        };

        let mut command = Command::new(&self.config.worker_path);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = match command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => child,
            Err(error) => {
                observe!(spawn_status, ProcessSpawnStatus::Failed);
                finish!(Err(WorkerError::new(
                    "spawn_failed",
                    "spawn",
                    error.to_string(),
                )));
            }
        };
        observe!(spawn_status, ProcessSpawnStatus::Spawned);
        observe!(worker_pid, Some(child.id()));
        let stdout = child.stdout.take().unwrap();
        let stderr = child.stderr.take().unwrap();
        let mut stdin = child.stdin.take().unwrap();
        let out = std::thread::spawn(move || read_limited(stdout));
        let err = std::thread::spawn(move || read_limited(stderr));
        let writer = std::thread::spawn(move || {
            stdin.write_all(&bytes)?;
            stdin.write_all(b"\n")
        });
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => {
                    observe!(termination, ProcessTermination::Exited);
                    observe!(exit_code, status.code());
                    break status;
                }
                Ok(None) => (),
                Err(error) => {
                    let _ = child.kill();
                    let waited = child.wait();
                    observe!(termination, ProcessTermination::WaitFailed);
                    observe!(exit_code, waited.ok().and_then(|status| status.code()));
                    if observation.is_some() {
                        observe!(request_status, ProcessIoStatus::Unknown);
                        observe!(response_status, ProcessIoStatus::Unknown);
                    }
                    finish!(Err(WorkerError::new(
                        "wait_failed",
                        "process",
                        error.to_string(),
                    )));
                }
            }
            if start.elapsed() >= timeout {
                let _ = child.kill();
                let waited = child.wait();
                observe!(termination, ProcessTermination::TimedOut);
                observe!(exit_code, waited.ok().and_then(|status| status.code()));

                let request_result = writer.join();
                match request_result {
                    Ok(Ok(())) => {
                        observe!(request_status, ProcessIoStatus::Complete);
                        observe!(request_sha256, request_sha256.clone());
                        observe!(request_bytes, request_bytes);
                    }
                    Ok(Err(_)) => observe!(request_status, ProcessIoStatus::Failed),
                    Err(_) => observe!(request_status, ProcessIoStatus::Unknown),
                }
                let response_result = out.join();
                match response_result {
                    Ok(Ok(bytes)) => {
                        observe!(response_status, ProcessIoStatus::Complete);
                        observe!(response_sha256, Some(digest(&bytes)));
                        observe!(response_bytes, Some(bytes.len() as u64));
                    }
                    Ok(Err(_)) => observe!(response_status, ProcessIoStatus::Failed),
                    Err(_) => observe!(response_status, ProcessIoStatus::Unknown),
                }
                let diagnostic = err.join().ok().and_then(Result::ok).unwrap_or_default();
                finish!(Err(WorkerError::new(
                    "timeout",
                    "process",
                    String::from_utf8_lossy(&diagnostic[..diagnostic.len().min(4096)]).into_owned(),
                )));
            }
            std::thread::sleep(Duration::from_millis(1));
        };
        let stderr = match err.join() {
            Ok(Ok(stderr)) => stderr,
            Ok(Err(error)) => {
                if observation.is_some() {
                    observe!(request_status, ProcessIoStatus::Unknown);
                    observe!(response_status, ProcessIoStatus::Unknown);
                }
                finish!(Err(WorkerError::new(
                    "reader_failed",
                    "stderr",
                    error.to_string(),
                )));
            }
            Err(_) => {
                if observation.is_some() {
                    observe!(request_status, ProcessIoStatus::Unknown);
                    observe!(response_status, ProcessIoStatus::Unknown);
                }
                finish!(Err(WorkerError::new(
                    "reader_failed",
                    "stderr",
                    "reader panicked",
                )));
            }
        };
        if !status.success() {
            match writer.join() {
                Ok(Ok(())) => {
                    observe!(request_status, ProcessIoStatus::Complete);
                    observe!(request_sha256, request_sha256.clone());
                    observe!(request_bytes, request_bytes);
                }
                Ok(Err(_)) => observe!(request_status, ProcessIoStatus::Failed),
                Err(_) => observe!(request_status, ProcessIoStatus::Unknown),
            }
            match out.join() {
                Ok(Ok(bytes)) => {
                    observe!(response_status, ProcessIoStatus::Complete);
                    observe!(response_sha256, Some(digest(&bytes)));
                    observe!(response_bytes, Some(bytes.len() as u64));
                }
                Ok(Err(_)) => observe!(response_status, ProcessIoStatus::Failed),
                Err(_) => observe!(response_status, ProcessIoStatus::Unknown),
            }
            finish!(Err(WorkerError::new(
                "process_failed",
                "process",
                format!(
                    "exit {:?}: {}",
                    status.code(),
                    String::from_utf8_lossy(&stderr[..stderr.len().min(4096)])
                ),
            )));
        }
        let write_result = writer.join();
        match &write_result {
            Ok(Ok(())) => {
                observe!(request_status, ProcessIoStatus::Complete);
                observe!(request_sha256, request_sha256.clone());
                observe!(request_bytes, request_bytes);
            }
            Ok(Err(_)) => observe!(request_status, ProcessIoStatus::Failed),
            Err(_) => observe!(request_status, ProcessIoStatus::Unknown),
        }
        let write_result = match write_result {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => Err(WorkerError::new("write_failed", "stdin", error.to_string())),
            Err(_) => Err(WorkerError::new("write_failed", "stdin", "writer panicked")),
        };
        if let Err(error) = write_result {
            if observation.is_some() {
                match out.join() {
                    Ok(Ok(bytes)) => {
                        observe!(response_status, ProcessIoStatus::Complete);
                        observe!(response_sha256, Some(digest(&bytes)));
                        observe!(response_bytes, Some(bytes.len() as u64));
                    }
                    Ok(Err(_)) => observe!(response_status, ProcessIoStatus::Failed),
                    Err(_) => observe!(response_status, ProcessIoStatus::Unknown),
                }
            }
            finish!(Err(error));
        }
        let bytes = match out.join() {
            Ok(Ok(bytes)) => {
                observe!(response_status, ProcessIoStatus::Complete);
                observe!(response_sha256, Some(digest(&bytes)));
                observe!(response_bytes, Some(bytes.len() as u64));
                bytes
            }
            Ok(Err(error)) => {
                observe!(response_status, ProcessIoStatus::Failed);
                finish!(Err(WorkerError::new(
                    "reader_failed",
                    "stdout",
                    error.to_string(),
                )));
            }
            Err(_) => {
                observe!(response_status, ProcessIoStatus::Unknown);
                finish!(Err(WorkerError::new(
                    "reader_failed",
                    "stdout",
                    "reader panicked",
                )));
            }
        };
        let result: DuelResult = match serde_json::from_slice(&bytes) {
            Ok(result) => {
                observe!(response_validation, ProcessResponseValidation::Parsed);
                result
            }
            Err(error) => {
                observe!(response_validation, ProcessResponseValidation::InvalidJson);
                finish!(Err(WorkerError::new(
                    "invalid_response",
                    "decode",
                    error.to_string(),
                )));
            }
        };
        if result.protocol_version != input.protocol_version {
            observe!(
                response_validation,
                ProcessResponseValidation::ProtocolVersionMismatch
            );
            finish!(Err(WorkerError::new(
                "protocol_version",
                "decode",
                "expected v2",
            )));
        }
        if result.status != DuelStatus::Failed && result.versions != input.versions {
            observe!(
                response_validation,
                ProcessResponseValidation::RuntimeVersionMismatch
            );
            finish!(Err(WorkerError::new(
                "version_mismatch",
                "decode",
                "worker returned different runtime versions",
            )));
        }
        finish!(Ok(result));
    }
}
fn read_limited(mut r: impl Read) -> std::io::Result<Vec<u8>> {
    let mut data = Vec::new();
    let mut chunk = [0; 8192];
    loop {
        let n = r.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        if data.len() + n > 64 * 1024 * 1024 {
            return Err(std::io::Error::other("worker output limit exceeded"));
        }
        data.extend_from_slice(&chunk[..n]);
    }
    Ok(data)
}

fn elapsed_millis(start: Instant) -> u64 {
    start.elapsed().as_millis().min(u64::MAX as u128) as u64
}

impl EngineAdapter for ProcessEngineAdapter {
    fn doctor(&self) -> DoctorReport {
        let mut issues = vec![];
        for (code, path, directory) in [
            ("worker_missing", &self.config.worker_path, false),
            ("dll_missing", &self.config.ocgcore_path, false),
            ("catalog_missing", &self.config.catalog_path, false),
            ("scripts_missing", &self.config.scripts_path, true),
            (
                "script_manifest_missing",
                &self.config.script_manifest_path,
                false,
            ),
            (
                "engine_manifest_missing",
                &self.config.engine_manifest_path,
                false,
            ),
        ] {
            if if directory {
                !path.is_dir()
            } else {
                !path.is_file()
            } {
                issues.push(DoctorIssue {
                    code: code.into(),
                    message: path.display().to_string(),
                });
            }
        }
        let assets_ok = issues.is_empty();
        let abi_ok = assets_ok
            && match crate::worker::probe_request(self.config.clone()).and_then(|r| self.run(&r)) {
                Ok(r) if r.status == DuelStatus::ProbePassed => true,
                Ok(r) => {
                    issues.push(DoctorIssue {
                        code: "abi_failed".into(),
                        message: format!("{:?}", r.error),
                    });
                    false
                }
                Err(e) => {
                    issues.push(DoctorIssue {
                        code: e.code,
                        message: e.message,
                    });
                    false
                }
            };
        DoctorReport {
            ready: assets_ok && abi_ok,
            assets_ok,
            abi_ok,
            smoke_ok: None,
            issues,
        }
    }
    fn run(&self, input: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        self.run_inner(input, None, Instant::now())
    }
}

impl ProcessObservedAdapter for ProcessEngineAdapter {
    fn run_process_observed(&self, input: &RunDuelRequest) -> ProcessObservedOutcome {
        self.run_observed(input)
    }
}
