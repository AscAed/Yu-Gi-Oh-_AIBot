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
#[derive(Clone)]
pub struct ProcessEngineAdapter {
    pub config: ProcessEngineConfig,
}
impl ProcessEngineAdapter {
    pub fn new(config: ProcessEngineConfig) -> Self {
        Self { config }
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
        let start = Instant::now();
        let timeout = Duration::from_millis(input.engine.timeout_ms);
        if timeout.is_zero() {
            return Err(WorkerError::new("timeout", "spawn", "zero timeout"));
        }
        let bytes = serde_json::to_vec(input)
            .map_err(|e| WorkerError::new("invalid_request", "encode", e.to_string()))?;
        let mut command = Command::new(&self.config.worker_path);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| WorkerError::new("spawn_failed", "spawn", e.to_string()))?;
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
                Ok(Some(status)) => break status,
                Ok(None) => (),
                Err(e) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(WorkerError::new("wait_failed", "process", e.to_string()));
                }
            }
            if start.elapsed() >= timeout {
                let _ = child.kill();
                let _ = child.wait();
                let _ = writer.join();
                let _ = out.join();
                let diagnostic = err.join().ok().and_then(Result::ok).unwrap_or_default();
                return Err(WorkerError::new(
                    "timeout",
                    "process",
                    String::from_utf8_lossy(&diagnostic[..diagnostic.len().min(4096)]).into_owned(),
                ));
            }
            std::thread::sleep(Duration::from_millis(1));
        };
        let stderr = err
            .join()
            .map_err(|_| WorkerError::new("reader_failed", "stderr", "reader panicked"))?
            .map_err(|e| WorkerError::new("reader_failed", "stderr", e.to_string()))?;
        if !status.success() {
            let _ = writer.join();
            let _ = out.join();
            return Err(WorkerError::new(
                "process_failed",
                "process",
                format!(
                    "exit {:?}: {}",
                    status.code(),
                    String::from_utf8_lossy(&stderr[..stderr.len().min(4096)])
                ),
            ));
        }
        writer
            .join()
            .map_err(|_| WorkerError::new("write_failed", "stdin", "writer panicked"))?
            .map_err(|e| WorkerError::new("write_failed", "stdin", e.to_string()))?;
        let bytes = out
            .join()
            .map_err(|_| WorkerError::new("reader_failed", "stdout", "reader panicked"))?
            .map_err(|e| WorkerError::new("reader_failed", "stdout", e.to_string()))?;
        let result: DuelResult = serde_json::from_slice(&bytes)
            .map_err(|e| WorkerError::new("invalid_response", "decode", e.to_string()))?;
        if result.protocol_version != input.protocol_version {
            return Err(WorkerError::new(
                "protocol_version",
                "decode",
                "expected v2",
            ));
        }
        if result.status != DuelStatus::Failed && result.versions != input.versions {
            return Err(WorkerError::new(
                "version_mismatch",
                "decode",
                "worker returned different runtime versions",
            ));
        }
        Ok(result)
    }
}
