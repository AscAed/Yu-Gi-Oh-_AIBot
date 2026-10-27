//! One stage at a time for the independent Tenki placement experiment.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    time::Instant,
};
use ygo_engine_adapter::*;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    context: String,
    ledger: PathBuf,
    output: PathBuf,
    stage: u8,
    request: RunDuelRequest,
    expected_identity: Value,
    started_at: u64,
    #[serde(default)]
    batch_kind: BatchKind,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "kebab-case")]
enum BatchKind {
    #[default]
    TenkiPlacementProbeV1,
    TenkiPlacementConfirmationV1,
    TenkiPlacementValidationV1,
}

impl BatchKind {
    fn has_prepared_report(self) -> bool {
        matches!(
            self,
            Self::TenkiPlacementConfirmationV1 | Self::TenkiPlacementValidationV1
        )
    }

    fn scope(self) -> &'static str {
        match self {
            Self::TenkiPlacementProbeV1 => TENKI_PLACEMENT_SCOPE,
            Self::TenkiPlacementConfirmationV1 => TENKI_PLACEMENT_CONFIRMATION_SCOPE,
            Self::TenkiPlacementValidationV1 => TENKI_PLACEMENT_VALIDATION_SCOPE,
        }
    }

    fn prepared_kinds(self) -> Option<(&'static str, &'static str)> {
        match self {
            Self::TenkiPlacementProbeV1 => None,
            Self::TenkiPlacementConfirmationV1 => Some((
                "native_tenki_placement_confirmation_manifest",
                "native_tenki_placement_confirmation_prepared",
            )),
            Self::TenkiPlacementValidationV1 => Some((
                "native_tenki_placement_validation_manifest",
                "native_tenki_placement_validation_prepared",
            )),
        }
    }

    fn seal_kind(self) -> &'static str {
        match self {
            Self::TenkiPlacementProbeV1 => "tenki_placement_stage_input_seal",
            Self::TenkiPlacementConfirmationV1 => "tenki_placement_confirmation_stage_input_seal",
            Self::TenkiPlacementValidationV1 => "tenki_placement_validation_stage_input_seal",
        }
    }

    fn requires_trace(self, mode: Mode) -> bool {
        self == Self::TenkiPlacementValidationV1 && matches!(mode, Mode::Run | Mode::PreflightOnly)
    }
}

fn required_prepared_hash(
    kind: BatchKind,
    mode: Mode,
    options: &RunnerOptions,
) -> Result<Option<&str>, &'static str> {
    match (kind, mode, options.prepared_sha256.as_deref()) {
        (BatchKind::TenkiPlacementProbeV1, _, Some(_)) => {
            Err("legacy batch cannot bind a prepared report")
        }
        (BatchKind::TenkiPlacementProbeV1, _, None) => Ok(None),
        (BatchKind::TenkiPlacementConfirmationV1, Mode::Run, Some(hash)) => Ok(Some(hash)),
        (BatchKind::TenkiPlacementConfirmationV1, Mode::Run, None) => {
            Err("confirmation run requires prepared report hash")
        }
        (BatchKind::TenkiPlacementValidationV1, Mode::Run, Some(hash)) => Ok(Some(hash)),
        (BatchKind::TenkiPlacementValidationV1, Mode::Run, None) => {
            Err("validation run requires prepared report hash")
        }
        (BatchKind::TenkiPlacementConfirmationV1, _, Some(_))
        | (BatchKind::TenkiPlacementValidationV1, _, Some(_)) => {
            Err("read-only modes do not accept prepared report hash")
        }
        (BatchKind::TenkiPlacementConfirmationV1, _, None)
        | (BatchKind::TenkiPlacementValidationV1, _, None) => Ok(None),
    }
}

fn validate_trace_requirement(
    kind: BatchKind,
    mode: Mode,
    options: &RunnerOptions,
) -> Result<(), &'static str> {
    if kind.requires_trace(mode) && !options.trace_stderr {
        return Err("validation run and preflight require --trace-stderr");
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Mode {
    Run,
    VerifyRecorded,
    Stats,
    PreflightOnly,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct RunnerOptions {
    mode: Mode,
    prepared_sha256: Option<String>,
    trace_stderr: bool,
}

#[derive(Clone, Copy)]
struct RunnerTrace {
    enabled: bool,
}

struct TracePhase {
    enabled: bool,
    name: &'static str,
    started: Instant,
}

impl RunnerTrace {
    fn phase(self, name: &'static str) -> TracePhase {
        if self.enabled {
            eprintln!("{}", json!({"phase":name,"event":"start"}));
        }
        TracePhase {
            enabled: self.enabled,
            name,
            started: Instant::now(),
        }
    }
}

impl Drop for TracePhase {
    fn drop(&mut self) {
        if self.enabled {
            eprintln!(
                "{}",
                json!({"phase":self.name,"event":"end","elapsed_ns":self.started.elapsed().as_nanos()})
            );
        }
    }
}

fn write_mode_output<W: Write + ?Sized>(
    mode: Mode,
    preflight_result: Option<&Value>,
    final_result: &Value,
    writer: &mut W,
) -> Result<(), Box<dyn std::error::Error>> {
    let result = if mode == Mode::PreflightOnly {
        preflight_result.ok_or("preflight result missing")?
    } else {
        final_result
    };
    serde_json::to_writer(&mut *writer, result)?;
    writer.write_all(b"\n")?;
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InputSeal {
    schema_version: u8,
    kind: String,
    context: String,
    stage: u8,
    input_sha256: String,
}

fn parse_options(arguments: &[String]) -> Result<RunnerOptions, &'static str> {
    if arguments.len() < 4 || arguments[2] != "--input-sha" {
        return Err("input --input-sha HASH [--verify-recorded|--stats|--preflight-only] required");
    }
    let mut mode = Mode::Run;
    let mut mode_seen = false;
    let mut prepared_sha256 = None;
    let mut trace_stderr = false;
    let mut index = 4;
    while index < arguments.len() {
        match arguments[index].as_str() {
            "--verify-recorded" if !mode_seen => {
                mode = Mode::VerifyRecorded;
                mode_seen = true;
                index += 1;
            }
            "--stats" if !mode_seen => {
                mode = Mode::Stats;
                mode_seen = true;
                index += 1;
            }
            "--preflight-only" if !mode_seen => {
                mode = Mode::PreflightOnly;
                mode_seen = true;
                index += 1;
            }
            "--trace-stderr" if !trace_stderr => {
                trace_stderr = true;
                index += 1;
            }
            "--prepared-sha256" if prepared_sha256.is_none() && index + 1 < arguments.len() => {
                let value = arguments[index + 1].as_str();
                if value.len() != 64
                    || !value
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
                {
                    return Err("invalid prepared report hash");
                }
                prepared_sha256 = Some(value.to_owned());
                index += 2;
            }
            _ => return Err("unknown, repeated or conflicting runner option"),
        }
    }
    Ok(RunnerOptions {
        mode,
        prepared_sha256,
        trace_stderr,
    })
}

#[cfg(test)]
fn parse_mode(arguments: &[String]) -> Result<Mode, &'static str> {
    Ok(parse_options(arguments)?.mode)
}

fn research_root(kind: BatchKind) -> Result<PathBuf, WorkerError> {
    match kind {
        BatchKind::TenkiPlacementProbeV1 => tenki_placement_research_root(),
        BatchKind::TenkiPlacementConfirmationV1 => tenki_placement_confirmation_research_root(),
        BatchKind::TenkiPlacementValidationV1 => tenki_placement_validation_research_root(),
    }
}

#[cfg(test)]
fn safe_for(path: &Path, kind: BatchKind) -> Result<(), Box<dyn std::error::Error>> {
    let root = research_root(kind).map_err(|error| error.message)?;
    safe_for_at(path, &root)
}

fn safe_for_at(path: &Path, root: &Path) -> Result<(), Box<dyn std::error::Error>> {
    if !path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
        || path.parent() != Some(root)
    {
        return Err("fixed placement research path required".into());
    }
    for ancestor in path.ancestors() {
        if let Ok(metadata) = fs::symlink_metadata(ancestor) {
            if metadata.file_type().is_symlink() {
                return Err("linked evidence path rejected".into());
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if metadata.file_attributes() & 0x400 != 0 {
                    return Err("reparse evidence path rejected".into());
                }
            }
        }
    }
    Ok(())
}

#[cfg(test)]
fn safe(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    safe_for(path, BatchKind::TenkiPlacementProbeV1)
}

struct StrictValue(Value);
impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = StrictValue;
            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("JSON without duplicate keys")
            }
            fn visit_bool<E: serde::de::Error>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_i64<E: serde::de::Error>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_u64<E: serde::de::Error>(self, value: u64) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_f64<E: serde::de::Error>(self, value: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(value)
                    .map(|number| StrictValue(Value::Number(number)))
                    .ok_or_else(|| E::custom("invalid number"))
            }
            fn visit_str<E: serde::de::Error>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_string<E: serde::de::Error>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut access: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(StrictValue(value)) = access.next_element::<StrictValue>()? {
                    values.push(value);
                }
                Ok(StrictValue(Value::Array(values)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut access: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(key) = access.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(serde::de::Error::custom("duplicate JSON key"));
                    }
                    let StrictValue(value) = access.next_value::<StrictValue>()?;
                    values.insert(key, value);
                }
                Ok(StrictValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}

fn publish(path: &Path, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(&serde_json::to_vec_pretty(value)?)?;
    file.sync_all()?;
    Ok(())
}

fn identity(request: &RunDuelRequest) -> Result<Value, String> {
    let found = capture_engine_identity(&request.engine)?;
    if found["consistent"] != true {
        return Err("inconsistent engine identity".into());
    }
    let versions = serde_json::to_value(&request.versions).map_err(|error| error.to_string())?;
    for (role, key) in [
        ("dll", "engine_sha256"),
        ("cdb", "cdb_sha256"),
        ("script_manifest", "scripts_sha256"),
    ] {
        if found["roles"][role]["sha256"] != versions[key] {
            return Err("request asset identity mismatch".into());
        }
    }
    Ok(found)
}

trait WorkflowRuntime {
    fn now(&mut self) -> Result<u64, String>;
    fn scan_identity(&mut self, request: &RunDuelRequest) -> Result<Value, String>;
    fn adapter(&mut self, request: &RunDuelRequest) -> WorkflowAdapter;
}

enum WorkflowAdapter {
    Process(ProcessEngineAdapter),
    #[cfg(test)]
    Synthetic(Box<dyn EngineAdapter>),
}

impl EngineAdapter for WorkflowAdapter {
    fn doctor(&self) -> DoctorReport {
        match self {
            Self::Process(adapter) => adapter.doctor(),
            #[cfg(test)]
            Self::Synthetic(adapter) => adapter.doctor(),
        }
    }

    fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        match self {
            Self::Process(adapter) => adapter.run(request),
            #[cfg(test)]
            Self::Synthetic(adapter) => adapter.run(request),
        }
    }
}

struct ProductionRuntime;

impl WorkflowRuntime for ProductionRuntime {
    fn now(&mut self) -> Result<u64, String> {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_secs())
            .map_err(|error| error.to_string())
    }

    fn scan_identity(&mut self, request: &RunDuelRequest) -> Result<Value, String> {
        identity(request)
    }

    fn adapter(&mut self, request: &RunDuelRequest) -> WorkflowAdapter {
        WorkflowAdapter::Process(ProcessEngineAdapter::new(request.engine.clone()))
    }
}

fn validate_runner_window(started_at: u64, now: u64) -> Result<(), &'static str> {
    let deadline = started_at
        .checked_add(7200)
        .ok_or("invalid validation window start")?;
    if now < started_at || now.saturating_add(30) >= deadline {
        Err("validation window has less than thirty seconds remaining")
    } else {
        Ok(())
    }
}

fn verify_saved(
    batch: &TenkiPlacementBatch,
    input: &Input,
    value: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    batch
        .verify_evidence(input.stage, value)
        .map_err(|error| error.message)?;
    if value["context"] != input.context
        || value["request"] != serde_json::to_value(&input.request)?
        || value["assets_before"] != input.expected_identity
    {
        return Err("saved receipt differs from frozen invocation".into());
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct PreflightCheck<'a> {
    input_path: &'a Path,
    input_hash: &'a str,
    input: &'a Input,
    kind: BatchKind,
    root: &'a Path,
    repository_root: &'a Path,
    require_empty_output: bool,
}

fn validate_preflight_files_with(
    check: &PreflightCheck<'_>,
    scan_identity: &mut dyn FnMut(&RunDuelRequest) -> Result<Value, String>,
) -> Result<Value, Box<dyn std::error::Error>> {
    let PreflightCheck {
        input_path,
        input_hash,
        input,
        kind,
        root,
        repository_root,
        require_empty_output,
    } = *check;
    if input.stage != 1 {
        return Err("preflight-only supports frozen stage 1".into());
    }
    safe_for_at(input_path, root)?;
    let request_path = root.join("stage-1-request.json");
    let seal_path = root.join("stage-1-input-seal.json");
    safe_for_at(&request_path, root)?;
    safe_for_at(&seal_path, root)?;
    let StrictValue(saved_request) = serde_json::from_slice(&fs::read(&request_path)?)?;
    if saved_request != serde_json::to_value(&input.request)? {
        return Err("frozen stage request differs from input".into());
    }
    let StrictValue(seal_value) = serde_json::from_slice(&fs::read(&seal_path)?)?;
    let seal: InputSeal = serde_json::from_value(seal_value)?;
    if seal.schema_version != 1
        || seal.kind != kind.seal_kind()
        || seal.context != input.context
        || seal.stage != 1
        || seal.input_sha256 != input_hash
        || input_path != root.join("stage-1-input.json")
        || (require_empty_output && input.output.exists())
    {
        return Err("frozen stage input seal or output state mismatch".into());
    }
    if kind == BatchKind::TenkiPlacementValidationV1 {
        validate_tenki_placement_stage1_request_at(&input.request, repository_root)
            .map_err(|error| error.message)?;
    } else {
        validate_tenki_placement_stage1_request(&input.request).map_err(|error| error.message)?;
    }
    let found =
        scan_identity(&input.request).map_err(|error| format!("asset precheck: {error}"))?;
    if found != input.expected_identity {
        return Err("asset identity drift before preflight".into());
    }
    Ok(json!({
        "preflight_passed": true,
        "native_calls": 0,
        "stage": 1,
        "context": input.context,
        "identity_sha256": found["identity"],
    }))
}

fn stage1_input_path(root: &Path, _kind: BatchKind) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = root.join("stage-1-input.json");
    safe_for_at(&path, root)?;
    Ok(path)
}

fn validate_prepared(
    root: &Path,
    input: &Input,
    prepared_hash: &str,
    kind: BatchKind,
) -> Result<(), Box<dyn std::error::Error>> {
    let (manifest_kind, prepared_kind) = kind
        .prepared_kinds()
        .ok_or("legacy batch cannot use a prepared report")?;
    let prepared_path = root.join("prepared.json");
    safe_for_at(&prepared_path, root)?;
    let prepared_raw = fs::read(&prepared_path)?;
    if digest(&prepared_raw) != prepared_hash {
        return Err("prepared report hash mismatch".into());
    }
    let StrictValue(prepared) = serde_json::from_slice(&prepared_raw)?;
    let manifest_path = root.join("manifest.json");
    safe_for_at(&manifest_path, root)?;
    let manifest_raw = fs::read(&manifest_path)?;
    let StrictValue(manifest) = serde_json::from_slice(&manifest_raw)?;
    let stage1_path = root.join("stage-1-input.json");
    safe_for_at(&stage1_path, root)?;
    let stage1_raw = fs::read(&stage1_path)?;
    let StrictValue(stage1_value) = serde_json::from_slice(&stage1_raw)?;
    let stage1: Input = serde_json::from_value(stage1_value)?;
    let worker_sha256 = stage1.expected_identity["roles"]["worker"]["sha256"].clone();
    if prepared["schema_version"] != 1
        || prepared["kind"] != prepared_kind
        || prepared["prepared"] != true
        || prepared["native_calls"] != 0
        || prepared["context"] != input.context
        || prepared["manifest_sha256"] != digest(&manifest_raw)
        || prepared["stage1_input_sha256"] != digest(&stage1_raw)
        || prepared["execution_ready"] != true
        || manifest["schema_version"] != 1
        || manifest["kind"] != manifest_kind
        || manifest["scope"] != kind.scope()
        || manifest["context"] != input.context
        || manifest["request"] != serde_json::to_value(&stage1.request)?
        || manifest["assets"]["ordinary"] != stage1.expected_identity
        || manifest["input_sha256"]["worker"] != worker_sha256
        || input.expected_identity != manifest["assets"]["ordinary"]
        || stage1.batch_kind != kind
        || stage1.stage != 1
        || stage1.context != input.context
        || stage1.started_at != input.started_at
        || stage1.ledger != input.ledger
        || prepared["proof_ready"] != false
        || prepared["complete_action_coverage"] != false
        || prepared["global_optimality"] != false
        || prepared["native_probability_verified"] != false
    {
        return Err("prepared report does not bind the frozen confirmation inputs".into());
    }
    Ok(())
}

fn validate_scoped_preflight_with(
    root: &Path,
    repository_root: &Path,
    input: &Input,
    kind: BatchKind,
    scan_identity: &mut dyn FnMut(&RunDuelRequest) -> Result<Value, String>,
) -> Result<(), Box<dyn std::error::Error>> {
    if !kind.has_prepared_report() {
        return Err("legacy batch has no scoped prepared preflight".into());
    }
    let stage1_path = stage1_input_path(root, kind)?;
    let raw = fs::read(&stage1_path)?;
    let StrictValue(value) = serde_json::from_slice(&raw)?;
    let stage1: Input = serde_json::from_value(value)?;
    if stage1.batch_kind != kind
        || stage1.stage != 1
        || stage1.context != input.context
        || stage1.started_at != input.started_at
        || stage1.ledger != input.ledger
    {
        return Err("confirmation stage 1 frozen input mismatch".into());
    }
    let input_hash = digest(&raw);
    validate_preflight_files_with(
        &PreflightCheck {
            input_path: &stage1_path,
            input_hash: &input_hash,
            input: &stage1,
            kind,
            root,
            repository_root,
            require_empty_output: false,
        },
        scan_identity,
    )
    .map(|_| ())
}

fn verify_validation_saved(
    input: &Input,
    journal: &ReadOnlyJournal,
    allow_publish: bool,
    repository_root: &Path,
) -> Result<Value, Box<dyn std::error::Error>> {
    let receipt = if input.output.exists() {
        let receipt_raw = fs::read(&input.output)?;
        let StrictValue(receipt) = serde_json::from_slice(&receipt_raw)?;
        receipt
    } else {
        if !allow_publish {
            return Err("published validation receipt missing in read-only verification".into());
        }
        let key = format!(
            "immutable/tenki-placement-validation/evidence/{}",
            input.stage
        );
        let value = journal
            .checkpoint(&key)
            .map_err(|error| error.message)?
            .and_then(|checkpoint| checkpoint.get("receipt").cloned())
            .ok_or("validation receipt missing")?;
        publish(&input.output, &value)?;
        value
    };
    if receipt["request"] != serde_json::to_value(&input.request)?
        || receipt["context"] != input.context
        || receipt["stage"] != input.stage
    {
        return Err("published validation receipt differs from frozen invocation".into());
    }
    verify_tenki_placement_validation_recorded_at(
        journal,
        input.stage,
        &input.context,
        input.started_at,
        &receipt,
        repository_root,
    )
    .map_err(|error| error.message)?;
    Ok(receipt)
}

fn verify_scoped_saved(
    input: &Input,
    root: &Path,
    journal: &ReadOnlyJournal,
    allow_publish: bool,
    kind: BatchKind,
    repository_root: &Path,
) -> Result<Value, Box<dyn std::error::Error>> {
    match kind {
        BatchKind::TenkiPlacementConfirmationV1 => {
            verify_confirmation_saved(input, root, journal, allow_publish)
        }
        BatchKind::TenkiPlacementValidationV1 => {
            verify_validation_saved(input, journal, allow_publish, repository_root)
        }
        BatchKind::TenkiPlacementProbeV1 => {
            Err("legacy batch cannot use a scoped receipt verifier".into())
        }
    }
}

fn verify_confirmation_saved(
    input: &Input,
    root: &Path,
    journal: &ReadOnlyJournal,
    allow_publish: bool,
) -> Result<Value, Box<dyn std::error::Error>> {
    let receipt = if input.output.exists() {
        let receipt_raw = fs::read(&input.output)?;
        let StrictValue(receipt) = serde_json::from_slice(&receipt_raw)?;
        receipt
    } else {
        if !allow_publish {
            return Err("confirmation receipt file missing in read-only verification".into());
        }
        let key = format!(
            "immutable/tenki-placement-confirmation/evidence/{}",
            input.stage
        );
        let value = journal
            .checkpoint(&key)
            .map_err(|error| error.message)?
            .and_then(|checkpoint| checkpoint.get("receipt").cloned())
            .ok_or("confirmation receipt missing")?;
        publish(&input.output, &value)?;
        value
    };
    if receipt["request"] != serde_json::to_value(&input.request)?
        || receipt["context"] != input.context
        || receipt["stage"] != input.stage
    {
        return Err("published confirmation receipt differs from frozen invocation".into());
    }
    verify_tenki_placement_confirmation_recorded(
        journal,
        input.stage,
        &input.context,
        input.started_at,
        &receipt,
    )
    .map_err(|error| error.message)?;
    let _ = root;
    Ok(receipt)
}

fn execute() -> Result<(), Box<dyn std::error::Error>> {
    let arguments = std::env::args().collect::<Vec<_>>();
    execute_with_runtime(&arguments, &mut ProductionRuntime, None, None)
}

fn execute_with_runtime(
    arguments: &[String],
    runtime: &mut dyn WorkflowRuntime,
    root_override: Option<&Path>,
    repository_root_override: Option<&Path>,
) -> Result<(), Box<dyn std::error::Error>> {
    let stdout = std::io::stdout();
    let mut writer = stdout.lock();
    execute_with_runtime_to(
        arguments,
        runtime,
        root_override,
        repository_root_override,
        &mut writer,
    )
}

fn execute_with_runtime_to(
    arguments: &[String],
    runtime: &mut dyn WorkflowRuntime,
    root_override: Option<&Path>,
    repository_root_override: Option<&Path>,
    writer: &mut dyn Write,
) -> Result<(), Box<dyn std::error::Error>> {
    let options = parse_options(arguments)?;
    let mode = options.mode;
    let trace = RunnerTrace {
        enabled: options.trace_stderr,
    };
    let verify = mode == Mode::VerifyRecorded;
    let stats_only = mode == Mode::Stats;
    let input_phase = trace.phase("input_validation");
    let raw_input = fs::read(&arguments[1])?;
    if digest(&raw_input) != arguments[3] {
        return Err("frozen input hash mismatch".into());
    }
    let input_path = PathBuf::from(&arguments[1]);
    let StrictValue(value) = serde_json::from_slice(&raw_input)?;
    let input: Input = serde_json::from_value(value)?;
    let kind = input.batch_kind;
    validate_trace_requirement(kind, mode, &options)?;
    let root = match root_override {
        Some(root) => root.to_path_buf(),
        None => research_root(kind).map_err(|error| error.message)?,
    };
    let repository_root = match repository_root_override {
        Some(root) => root.to_path_buf(),
        None => std::env::current_dir()?,
    };
    safe_for_at(&input_path, &root)?;
    tenki_placement_purpose(input.stage).map_err(|error| error.message)?;
    safe_for_at(&input.ledger, &root)?;
    safe_for_at(&input.output, &root)?;
    if input.ledger != root.join("calls.jsonl")
        || input.output != root.join(format!("stage-{}.json", input.stage))
        || input_path != root.join(format!("stage-{}-input.json", input.stage))
    {
        return Err("fixed ledger or stage filenames required".into());
    }
    if input.ledger == input.output
        || input.output.starts_with(&input.ledger)
        || input.ledger.starts_with(&input.output)
    {
        return Err("ledger and output paths overlap".into());
    }
    for asset in [
        &input.request.engine.worker_path,
        &input.request.engine.ocgcore_path,
        &input.request.engine.catalog_path,
        &input.request.engine.scripts_path,
        &input.request.engine.script_manifest_path,
        &input.request.engine.engine_manifest_path,
    ] {
        let asset = if asset.is_absolute() {
            asset.clone()
        } else {
            repository_root.join(asset)
        };
        if input.output.starts_with(&asset)
            || asset.starts_with(&input.output)
            || input.ledger.starts_with(&asset)
            || asset.starts_with(&input.ledger)
        {
            return Err("evidence overlaps engine assets".into());
        }
    }
    drop(input_phase);
    if mode == Mode::PreflightOnly {
        if options.prepared_sha256.is_some() {
            return Err("preflight mode cannot bind a prepared report".into());
        }
        let preflight_result = {
            let _phase = trace.phase("shared_preflight");
            validate_preflight_files_with(
                &PreflightCheck {
                    input_path: &input_path,
                    input_hash: &arguments[3],
                    input: &input,
                    kind,
                    root: &root,
                    repository_root: &repository_root,
                    require_empty_output: true,
                },
                &mut |request| runtime.scan_identity(request),
            )?
        };
        write_mode_output(mode, Some(&preflight_result), &Value::Null, writer)?;
        return Ok(());
    }
    if kind.has_prepared_report() {
        let prepared_hash = required_prepared_hash(kind, mode, &options)?;
        if let Some(prepared_hash) = prepared_hash {
            validate_prepared(&root, &input, prepared_hash, kind)?;
        }
        if stats_only || verify {
            let journal = {
                let _phase = trace.phase("ledger_check");
                CallJournal::inspect_existing(&input.ledger, kind.scope(), &input.context, 6)
                    .map_err(|error| error.message)?
                    .ok_or("existing scoped ledger required")?
            };
            if stats_only {
                let result = json!({"native_calls":0,"ledger":journal.stats().map_err(|error|error.message)?});
                write_mode_output(mode, None, &result, writer)?;
                return Ok(());
            }
            let receipt =
                verify_scoped_saved(&input, &root, &journal, false, kind, &repository_root)?;
            let result = json!({"verified_recorded":true,"native_calls":0,"successful":receipt["successful"],"ledger":journal.stats().map_err(|error|error.message)?});
            write_mode_output(mode, None, &result, writer)?;
            if receipt["successful"] != true {
                std::process::exit(1);
            }
            return Ok(());
        }
        let existing = {
            let _phase = trace.phase("ledger_check");
            CallJournal::inspect_existing(&input.ledger, kind.scope(), &input.context, 6)
                .map_err(|error| error.message)?
        };
        if let Some(journal) = existing {
            let stats = journal.stats().map_err(|error| error.message)?;
            if stats.unknown != 0 || stats.reserved != 0 || stats.abandoned != 0 {
                return Err("scoped ledger has unresolved consumption".into());
            }
            if stats.consumed == input.stage as usize
                && stats.completed == stats.consumed
                && stats.unknown == 0
            {
                let receipt =
                    verify_scoped_saved(&input, &root, &journal, true, kind, &repository_root)?;
                let result = json!({"verified_recorded":true,"native_calls":0,"successful":receipt["successful"],"ledger":stats});
                write_mode_output(mode, None, &result, writer)?;
                if receipt["successful"] != true {
                    std::process::exit(1);
                }
                return Ok(());
            }
            validate_placement_slot(input.stage, &stats).map_err(|error| error.message)?;
        } else if input.stage != 1 {
            return Err("scoped ledger required for noninitial stage".into());
        }
        {
            if kind == BatchKind::TenkiPlacementValidationV1 {
                validate_runner_window(input.started_at, runtime.now()?)
                    .map_err(|error| error.to_string())?;
            }
            let _phase = trace.phase("shared_preflight");
            validate_scoped_preflight_with(
                &root,
                &repository_root,
                &input,
                kind,
                &mut |request| runtime.scan_identity(request),
            )?;
        }
    } else {
        required_prepared_hash(kind, mode, &options).map_err(|error| error.to_string())?;
    }
    if (stats_only || verify) && !input.ledger.exists() {
        return Err("existing ledger required".into());
    }
    let batch = {
        let _phase = trace.phase("ledger_check");
        match kind {
            BatchKind::TenkiPlacementProbeV1 => {
                TenkiPlacementBatch::open(&input.ledger, &input.context, input.started_at)
            }
            BatchKind::TenkiPlacementConfirmationV1 => TenkiPlacementBatch::open_confirmation(
                &input.ledger,
                &input.context,
                input.started_at,
            ),
            BatchKind::TenkiPlacementValidationV1 => TenkiPlacementBatch::open_validation_at(
                &input.ledger,
                &input.context,
                input.started_at,
                &repository_root,
            ),
        }
        .map_err(|error| error.message)?
    };
    if stats_only {
        batch.verify().map_err(|error| error.message)?;
        let result =
            json!({"native_calls":0,"ledger":batch.stats().map_err(|error|error.message)?});
        write_mode_output(mode, None, &result, writer)?;
        return Ok(());
    }
    if kind == BatchKind::TenkiPlacementProbeV1 {
        if let Some(receipt) = batch.evidence(input.stage).map_err(|error| error.message)? {
            verify_saved(&batch, &input, &receipt)?;
            if input.output.exists() {
                let saved: StrictValue = serde_json::from_slice(&fs::read(&input.output)?)?;
                if saved.0 != receipt {
                    return Err("published receipt differs from immutable checkpoint".into());
                }
            } else if verify {
                return Err("published receipt missing".into());
            } else {
                publish(&input.output, &receipt)?;
            }
            let result = json!({"verified_recorded":true,"native_calls":0,"successful":receipt["successful"],"ledger":batch.stats().map_err(|error|error.message)?});
            write_mode_output(mode, None, &result, writer)?;
            if receipt["successful"] != true {
                std::process::exit(1);
            }
            return Ok(());
        }
    }
    if verify {
        return Err("immutable stage receipt missing".into());
    }
    if input.output.exists() {
        return Err("stage output already exists without checkpoint".into());
    }

    let intent_exists = batch
        .has_intent(input.stage)
        .map_err(|error| error.message)?;
    let recovered = if intent_exists {
        batch
            .load_outcome(input.stage, &input.request)
            .map_err(|error| error.message)?
            .flatten()
    } else {
        None
    };
    if intent_exists && recovered.is_none() {
        return Err("stage has an unresolved charged intent; retry is forbidden".into());
    }
    batch
        .validate_request(input.stage, &input.request)
        .map_err(|error| error.message)?;
    let before = if recovered.is_some() {
        batch
            .assets_before(input.stage)
            .map_err(|error| error.message)?
            .ok_or("precharge identity checkpoint missing")?
    } else {
        batch.require_time().map_err(|error| error.message)?;
        if kind == BatchKind::TenkiPlacementValidationV1 {
            validate_runner_window(input.started_at, runtime.now()?)
                .map_err(|error| error.to_string())?;
        }
        let found = {
            let _phase = trace.phase("precharge_scan");
            runtime
                .scan_identity(&input.request)
                .map_err(|error| format!("asset precheck: {error}"))?
        };
        if found != input.expected_identity {
            return Err("asset identity drift before call".into());
        }
        batch
            .save_assets_before(input.stage, &found)
            .map_err(|error| error.message)?;
        found
    };
    let native_calls = usize::from(recovered.is_none());
    let outcome = match recovered {
        Some(result) => result,
        None => {
            if kind == BatchKind::TenkiPlacementValidationV1 {
                validate_runner_window(input.started_at, runtime.now()?)
                    .map_err(|error| error.to_string())?;
            }
            let adapter = runtime.adapter(&input.request);
            let run = {
                let _phase = trace.phase("batch_call");
                batch.run(adapter, input.stage, &input.request)
            };
            if run.is_err() {
                // A worker-level error may have been completed and charged. Restore only that receipt.
                batch
                    .load_outcome(input.stage, &input.request)
                    .map_err(|error| error.message)?
                    .flatten()
                    .ok_or_else(|| run.err().unwrap().message)?
            } else {
                run
            }
        }
    };
    let after = {
        let _phase = trace.phase("postcharge_scan");
        runtime.scan_identity(&input.request).ok()
    };
    let receipt = {
        let _phase = trace.phase("receipt_save");
        let receipt = batch
            .record_evidence(
                input.stage,
                &input.request,
                &outcome,
                &before,
                after.as_ref(),
            )
            .map_err(|error| error.message)?;
        publish(&input.output, &receipt)?;
        receipt
    };
    let result = json!({"successful":receipt["successful"],"native_calls":native_calls,"ledger":receipt["ledger"]});
    write_mode_output(mode, None, &result, writer)?;
    if receipt["successful"] != true {
        std::process::exit(1);
    }
    Ok(())
}

fn main() {
    if let Err(error) = execute() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};
    use ygo_domain::{CardId, Deck};

    fn synthetic_validation_request() -> RunDuelRequest {
        let repository_root = workspace_root();
        let main = [
            57_103_969, 69_247_929, 69_247_929, 2_964_201, 2_964_201, 2_964_201, 2_971_090,
            2_971_090, 2_971_090, 3_797_883, 3_797_883, 3_797_883, 4_035_199, 4_035_199, 4_035_199,
            4_179_849, 4_179_849, 4_179_849, 4_392_470, 4_392_470, 4_392_470, 6_368_038, 6_368_038,
            6_368_038, 6_631_034, 6_631_034, 6_631_034, 6_740_720, 6_740_720, 6_740_720, 7_562_372,
            7_562_372, 7_562_372, 8_353_769, 8_353_769, 8_353_769, 9_540_040, 9_540_040, 9_540_040,
            10_538_007,
        ]
        .into_iter()
        .map(CardId)
        .collect();
        RunDuelRequest {
            protocol_version: 2,
            engine: ProcessEngineConfig {
                worker_path: repository_root.join(TENKI_PLACEMENT_VALIDATION_WORKER_RELATIVE_PATH),
                ..ProcessEngineConfig::default()
            },
            deck: Deck {
                main,
                extra: [84_013_237, 71_594_310, 77_637_979]
                    .into_iter()
                    .map(CardId)
                    .collect(),
                side: Vec::new(),
            },
            opening_hand: [57_103_969, 2_964_201, 2_964_201, 2_964_201, 2_971_090]
                .into_iter()
                .map(CardId)
                .collect(),
            seed: 1,
            decisions: vec![Decision {
                prompt_id: 7,
                player: 0,
                choice: Choice::Command {
                    command: 5,
                    index: 0,
                },
            }],
            versions: RuntimeVersions {
                rules: "ocg-mr5".into(),
                catalog: String::new(),
                banlist: String::new(),
                engine_sha256: "446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9"
                    .into(),
                cdb_sha256: "c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225"
                    .into(),
                scripts_sha256: "69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91"
                    .into(),
                core_commit: "38d04c9feb1a26617407091380634c87262fe3f8".into(),
                initializer: "fixed-hand-shuffle-v1".into(),
            },
            probe_only: false,
            scenario: None,
            interruption: None,
            first_turn: None,
            research_capture: None,
        }
    }

    struct SyntheticAdapter {
        result: DuelResult,
        calls: std::sync::Arc<AtomicUsize>,
        clock: std::sync::Arc<AtomicU64>,
    }

    impl EngineAdapter for SyntheticAdapter {
        fn doctor(&self) -> DoctorReport {
            panic!("normal validation workflow must not call doctor")
        }

        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.clock.fetch_add(12, Ordering::SeqCst);
            Ok(self.result.clone())
        }
    }

    struct SyntheticRuntime {
        identity: Value,
        scans: std::sync::Arc<AtomicUsize>,
        calls: std::sync::Arc<AtomicUsize>,
        clock: std::sync::Arc<AtomicU64>,
        result: DuelResult,
    }

    impl WorkflowRuntime for SyntheticRuntime {
        fn now(&mut self) -> Result<u64, String> {
            Ok(self.clock.load(Ordering::SeqCst))
        }

        fn scan_identity(&mut self, _: &RunDuelRequest) -> Result<Value, String> {
            self.scans.fetch_add(1, Ordering::SeqCst);
            self.clock.fetch_add(61, Ordering::SeqCst);
            Ok(self.identity.clone())
        }

        fn adapter(&mut self, _: &RunDuelRequest) -> WorkflowAdapter {
            WorkflowAdapter::Synthetic(Box::new(SyntheticAdapter {
                result: self.result.clone(),
                calls: self.calls.clone(),
                clock: self.clock.clone(),
            }))
        }
    }

    fn synthetic_identity(request: &RunDuelRequest) -> Value {
        json!({
            "consistent":true,
            "identity":"synthetic-test-identity",
            "roles": {
                "worker":{"sha256":"a".repeat(64)},
                "dll":{"sha256":request.versions.engine_sha256},
                "cdb":{"sha256":request.versions.cdb_sha256},
                "script_manifest":{"sha256":request.versions.scripts_sha256}
            }
        })
    }

    fn idle_with_tenki() -> Vec<u8> {
        let mut raw = vec![11, 0];
        for command in 0..6 {
            if command == 5 {
                raw.extend(1u32.to_le_bytes());
                raw.extend(57_103_969u32.to_le_bytes());
                raw.extend([0, 2]);
                raw.extend(0u32.to_le_bytes());
                raw.extend(0u64.to_le_bytes());
                raw.push(0);
            } else {
                raw.extend(0u32.to_le_bytes());
            }
        }
        raw.extend([0, 1, 0]);
        raw
    }

    fn synthetic_stage1_result(request: &RunDuelRequest) -> DuelResult {
        let activation_raw = idle_with_tenki();
        let activation = parse_prompt(7, &activation_raw).unwrap().unwrap();
        let placement_raw = vec![18, 0, 1, 255, 224, 255, 255];
        let placement = parse_prompt(9, &placement_raw).unwrap().unwrap();
        let mut result = DuelResult::failure(WorkerError::new("test", "synthetic", "unused"));
        result.status = DuelStatus::DecisionRequired;
        result.error = None;
        result.resolved_decisions = request.decisions.clone();
        result.prompt = Some(placement.clone());
        result.events = vec![
            CoreEventFrame {
                sequence: 7,
                opcode: 11,
                raw: activation_raw,
                supported: true,
                fields: json!({"prompt":activation}),
            },
            CoreEventFrame {
                sequence: 9,
                opcode: 18,
                raw: placement_raw,
                supported: true,
                fields: json!({"prompt":placement}),
            },
        ];
        result
    }

    fn now_unix() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs()
    }

    fn workspace_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap()
    }

    struct ValidationStage1Fixture {
        request: RunDuelRequest,
        identity: Value,
        input_path: PathBuf,
        ledger: PathBuf,
        output: PathBuf,
        input_sha256: String,
        prepared_sha256: String,
        started_at: u64,
    }

    fn write_validation_stage1_fixture(
        root: &Path,
        mut request: RunDuelRequest,
        worker_path: PathBuf,
        context: &str,
    ) -> ValidationStage1Fixture {
        fs::create_dir_all(root).unwrap();
        request.engine.worker_path = worker_path;
        let started_at = now_unix().saturating_sub(2);
        let identity = synthetic_identity(&request);
        let input_path = root.join("stage-1-input.json");
        let ledger = root.join("calls.jsonl");
        let output = root.join("stage-1.json");
        let input_value = json!({
            "context":context,
            "ledger":ledger,
            "output":output,
            "stage":1,
            "request":request,
            "expected_identity":identity,
            "started_at":started_at,
            "batch_kind":"tenki-placement-validation-v1"
        });
        let input_raw = serde_json::to_vec(&input_value).unwrap();
        fs::write(&input_path, &input_raw).unwrap();
        fs::write(
            root.join("stage-1-request.json"),
            serde_json::to_vec(&request).unwrap(),
        )
        .unwrap();
        fs::write(
            root.join("stage-1-input-seal.json"),
            serde_json::to_vec(&json!({
                "schema_version":1,
                "kind":"tenki_placement_validation_stage_input_seal",
                "context":context,
                "stage":1,
                "input_sha256":digest(&input_raw)
            }))
            .unwrap(),
        )
        .unwrap();
        let manifest_raw = serde_json::to_vec(&json!({
            "schema_version":1,
            "kind":"native_tenki_placement_validation_manifest",
            "scope":TENKI_PLACEMENT_VALIDATION_SCOPE,
            "context":context,
            "request":request,
            "assets":{"ordinary":identity},
            "input_sha256":{"worker":identity["roles"]["worker"]["sha256"]}
        }))
        .unwrap();
        fs::write(root.join("manifest.json"), &manifest_raw).unwrap();
        let prepared_raw = serde_json::to_vec(&json!({
            "schema_version":1,
            "kind":"native_tenki_placement_validation_prepared",
            "prepared":true,
            "native_calls":0,
            "context":context,
            "manifest_sha256":digest(&manifest_raw),
            "stage1_input_sha256":digest(&input_raw),
            "execution_ready":true,
            "proof_ready":false,
            "complete_action_coverage":false,
            "global_optimality":false,
            "native_probability_verified":false
        }))
        .unwrap();
        let prepared_sha256 = digest(&prepared_raw);
        fs::write(root.join("prepared.json"), &prepared_raw).unwrap();

        ValidationStage1Fixture {
            request,
            identity,
            input_path,
            ledger,
            output,
            input_sha256: digest(&input_raw),
            prepared_sha256,
            started_at,
        }
    }

    #[test]
    fn validation_batch_kind_is_an_explicit_input_value() {
        let kind = serde_json::from_str::<BatchKind>("\"tenki-placement-validation-v1\"");
        assert!(
            kind.is_ok(),
            "the dedicated validation scope must parse without falling back to legacy"
        );
    }

    #[test]
    fn runner_modes_are_single_and_mutually_exclusive() {
        let base = vec![
            "runner".into(),
            "input".into(),
            "--input-sha".into(),
            "hash".into(),
        ];
        assert_eq!(parse_mode(&base), Ok(Mode::Run));
        for (flag, expected) in [
            ("--stats", Mode::Stats),
            ("--verify-recorded", Mode::VerifyRecorded),
            ("--preflight-only", Mode::PreflightOnly),
        ] {
            let mut arguments = base.clone();
            arguments.push(flag.into());
            assert_eq!(parse_mode(&arguments), Ok(expected));
        }
        for flags in [
            vec!["--stats".into(), "--preflight-only".into()],
            vec!["--stats".into(), "--stats".into()],
            vec!["--unknown".into()],
        ] {
            let mut arguments = base.clone();
            arguments.extend(flags);
            assert!(parse_mode(&arguments).is_err());
        }
        let mut prepared = base.clone();
        prepared.extend(["--prepared-sha256".into(), "a".repeat(64), "--stats".into()]);
        assert_eq!(parse_options(&prepared).unwrap().mode, Mode::Stats);
        prepared.push("--prepared-sha256".into());
        prepared.push("b".repeat(64));
        assert!(parse_options(&prepared).is_err());
    }

    #[test]
    fn trace_flag_is_optional_and_cannot_be_repeated() {
        let mut arguments = vec![
            "runner".into(),
            "input".into(),
            "--input-sha".into(),
            "hash".into(),
        ];
        assert!(!parse_options(&arguments).unwrap().trace_stderr);
        arguments.push("--trace-stderr".into());
        assert!(parse_options(&arguments).unwrap().trace_stderr);
        arguments.push("--trace-stderr".into());
        assert!(parse_options(&arguments).is_err());
    }

    #[test]
    fn mode_output_writes_one_json_document_for_normal_and_preflight() {
        let normal = json!({"successful": true, "native_calls": 1});
        let preflight = json!({"preflight_passed": true, "native_calls": 0});
        let mut normal_stdout = Vec::new();
        write_mode_output(Mode::Run, None, &normal, &mut normal_stdout).unwrap();
        assert_eq!(normal_stdout, b"{\"native_calls\":1,\"successful\":true}\n");

        for mode in [Mode::Stats, Mode::VerifyRecorded] {
            let mut stdout = Vec::new();
            write_mode_output(mode, None, &normal, &mut stdout).unwrap();
            assert_eq!(stdout, b"{\"native_calls\":1,\"successful\":true}\n");
        }

        let mut preflight_stdout = Vec::new();
        write_mode_output(
            Mode::PreflightOnly,
            Some(&preflight),
            &normal,
            &mut preflight_stdout,
        )
        .unwrap();
        assert_eq!(
            preflight_stdout,
            b"{\"native_calls\":0,\"preflight_passed\":true}\n"
        );
    }

    #[test]
    fn batch_kind_defaults_for_old_inputs_and_rejects_null_or_unknown_values() {
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct LegacyCompatible {
            #[serde(default)]
            batch_kind: BatchKind,
        }
        let omitted: LegacyCompatible = serde_json::from_str("{}").unwrap();
        assert_eq!(omitted.batch_kind, BatchKind::TenkiPlacementProbeV1);
        let old: LegacyCompatible =
            serde_json::from_str(r#"{"batch_kind":"tenki-placement-probe-v1"}"#).unwrap();
        assert_eq!(old.batch_kind, BatchKind::TenkiPlacementProbeV1);
        let new: LegacyCompatible =
            serde_json::from_str(r#"{"batch_kind":"tenki-placement-confirmation-v1"}"#).unwrap();
        assert_eq!(new.batch_kind, BatchKind::TenkiPlacementConfirmationV1);
        let validation: LegacyCompatible =
            serde_json::from_str(r#"{"batch_kind":"tenki-placement-validation-v1"}"#).unwrap();
        assert_eq!(validation.batch_kind, BatchKind::TenkiPlacementValidationV1);
        assert!(serde_json::from_str::<LegacyCompatible>(r#"{"batch_kind":null}"#).is_err());
        assert!(serde_json::from_str::<LegacyCompatible>(r#"{"batch_kind":"other"}"#).is_err());

        let request = RunDuelRequest {
            protocol_version: 2,
            engine: ProcessEngineConfig::default(),
            deck: Default::default(),
            opening_hand: Vec::new(),
            seed: 1,
            decisions: Vec::new(),
            versions: Default::default(),
            probe_only: false,
            scenario: None,
            interruption: None,
            first_turn: None,
            research_capture: None,
        };
        let mut input_value = json!({
            "context":"c", "ledger":"ledger", "output":"out", "stage":1,
            "request":request, "expected_identity":{}, "started_at":1
        });
        let omitted: Input = serde_json::from_value(input_value.clone()).unwrap();
        assert_eq!(omitted.batch_kind, BatchKind::TenkiPlacementProbeV1);
        input_value["batch_kind"] = json!("tenki-placement-confirmation-v1");
        let explicit: Input = serde_json::from_value(input_value.clone()).unwrap();
        assert_eq!(explicit.batch_kind, BatchKind::TenkiPlacementConfirmationV1);
        input_value["batch_kind"] = json!("tenki-placement-validation-v1");
        let validation: Input = serde_json::from_value(input_value.clone()).unwrap();
        assert_eq!(validation.batch_kind, BatchKind::TenkiPlacementValidationV1);
        input_value["batch_kind"] = Value::Null;
        assert!(serde_json::from_value::<Input>(input_value.clone()).is_err());
        input_value["batch_kind"] = json!("unknown-v1");
        assert!(serde_json::from_value::<Input>(input_value).is_err());
    }

    #[test]
    fn confirmation_native_run_requires_prepared_hash_but_read_only_does_not() {
        let missing = RunnerOptions {
            mode: Mode::Run,
            prepared_sha256: None,
            trace_stderr: false,
        };
        let valid = RunnerOptions {
            mode: Mode::Run,
            prepared_sha256: Some("a".repeat(64)),
            trace_stderr: false,
        };
        let verify = RunnerOptions {
            mode: Mode::VerifyRecorded,
            prepared_sha256: None,
            trace_stderr: false,
        };
        assert!(required_prepared_hash(
            BatchKind::TenkiPlacementConfirmationV1,
            Mode::Run,
            &missing
        )
        .is_err());
        assert!(
            required_prepared_hash(BatchKind::TenkiPlacementConfirmationV1, Mode::Run, &valid)
                .unwrap()
                .is_some()
        );
        assert_eq!(
            required_prepared_hash(
                BatchKind::TenkiPlacementConfirmationV1,
                Mode::VerifyRecorded,
                &verify
            ),
            Ok(None)
        );
    }

    #[test]
    fn confirmation_stage1_input_path_is_validated_before_reading() {
        let root = research_root(BatchKind::TenkiPlacementConfirmationV1).unwrap();
        let expected = root.join("stage-1-input.json");
        assert_eq!(
            stage1_input_path(&root, BatchKind::TenkiPlacementConfirmationV1).unwrap(),
            expected
        );
        assert!(stage1_input_path(
            Path::new("other-root"),
            BatchKind::TenkiPlacementConfirmationV1
        )
        .is_err());
    }

    #[test]
    fn validation_scope_has_fixed_disjoint_paths_and_contract_kinds() {
        let root = research_root(BatchKind::TenkiPlacementValidationV1).unwrap();
        assert!(
            root.ends_with("data/runtime/p1-tenki-placement-validation-native-2026-10-23/research")
        );
        let input = root.join("stage-1-input.json");
        assert!(safe_for(&input, BatchKind::TenkiPlacementValidationV1).is_ok());
        assert!(safe_for(
            &research_root(BatchKind::TenkiPlacementProbeV1)
                .unwrap()
                .join("stage-1-input.json"),
            BatchKind::TenkiPlacementValidationV1
        )
        .is_err());
        assert_eq!(
            BatchKind::TenkiPlacementValidationV1.prepared_kinds(),
            Some((
                "native_tenki_placement_validation_manifest",
                "native_tenki_placement_validation_prepared"
            ))
        );
        assert_eq!(
            BatchKind::TenkiPlacementValidationV1.seal_kind(),
            "tenki_placement_validation_stage_input_seal"
        );
        assert_eq!(
            BatchKind::TenkiPlacementValidationV1.scope(),
            TENKI_PLACEMENT_VALIDATION_SCOPE
        );
    }

    #[test]
    fn validation_mode_requires_prepared_binding_only_for_normal_runs() {
        let missing = RunnerOptions {
            mode: Mode::Run,
            prepared_sha256: None,
            trace_stderr: true,
        };
        let prepared_hash = "b".repeat(64);
        let valid = RunnerOptions {
            mode: Mode::Run,
            prepared_sha256: Some(prepared_hash.clone()),
            trace_stderr: true,
        };
        let readonly = RunnerOptions {
            mode: Mode::VerifyRecorded,
            prepared_sha256: None,
            trace_stderr: false,
        };
        assert!(
            required_prepared_hash(BatchKind::TenkiPlacementValidationV1, Mode::Run, &missing)
                .is_err()
        );
        assert_eq!(
            required_prepared_hash(BatchKind::TenkiPlacementValidationV1, Mode::Run, &valid)
                .unwrap(),
            Some(prepared_hash.as_str())
        );
        assert_eq!(
            required_prepared_hash(
                BatchKind::TenkiPlacementValidationV1,
                Mode::VerifyRecorded,
                &readonly
            ),
            Ok(None)
        );
        assert!(validate_trace_requirement(
            BatchKind::TenkiPlacementValidationV1,
            Mode::Run,
            &missing
        )
        .is_ok());
        assert!(validate_trace_requirement(
            BatchKind::TenkiPlacementValidationV1,
            Mode::PreflightOnly,
            &RunnerOptions {
                mode: Mode::PreflightOnly,
                prepared_sha256: None,
                trace_stderr: false,
            }
        )
        .is_err());
        assert!(validate_trace_requirement(
            BatchKind::TenkiPlacementValidationV1,
            Mode::Stats,
            &readonly
        )
        .is_ok());
        assert!(validate_trace_requirement(
            BatchKind::TenkiPlacementProbeV1,
            Mode::Run,
            &RunnerOptions {
                mode: Mode::Run,
                prepared_sha256: None,
                trace_stderr: false,
            }
        )
        .is_ok());
    }

    #[test]
    #[ignore = "requires the pinned historical genesis evidence; run only in an explicitly provisioned opt-in workspace"]
    fn validation_normal_dispatch_runs_preflight_gate_scans_adapter_and_saves_receipt() {
        let repository_root = workspace_root();
        let request = synthetic_validation_request();
        let root = repository_root
            .join("target/curry-option-validation-tests/tmp")
            .join(format!("full-normal-{}-{}", std::process::id(), now_unix()));
        let context = "synthetic-validation-normal";
        let fixture = write_validation_stage1_fixture(
            &root,
            request,
            repository_root.join(TENKI_PLACEMENT_VALIDATION_WORKER_RELATIVE_PATH),
            context,
        );

        let scans = std::sync::Arc::new(AtomicUsize::new(0));
        let calls = std::sync::Arc::new(AtomicUsize::new(0));
        let clock = std::sync::Arc::new(AtomicU64::new(fixture.started_at));
        let mut runtime = SyntheticRuntime {
            identity: fixture.identity.clone(),
            scans: scans.clone(),
            calls: calls.clone(),
            clock: clock.clone(),
            result: synthetic_stage1_result(&fixture.request),
        };
        let arguments = vec![
            "runner".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_sha256.clone(),
            "--prepared-sha256".into(),
            fixture.prepared_sha256.clone(),
            "--trace-stderr".into(),
        ];
        let mut stdout = Vec::new();
        execute_with_runtime_to(
            &arguments,
            &mut runtime,
            Some(&root),
            Some(&repository_root),
            &mut stdout,
        )
        .unwrap();

        let mut decoder = serde_json::Deserializer::from_slice(&stdout);
        let summary: Value = Value::deserialize(&mut decoder).unwrap();
        decoder.end().unwrap();
        assert!(summary.is_object());
        assert_eq!(summary["native_calls"], 1);

        assert_eq!(scans.load(Ordering::SeqCst), 3);
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert!(clock.load(Ordering::SeqCst) >= fixture.started_at + 3 * 61 + 12);
        let receipt: Value = serde_json::from_slice(&fs::read(&fixture.output).unwrap()).unwrap();
        assert_eq!(receipt["successful"], true);
        assert_eq!(receipt["scope"], TENKI_PLACEMENT_VALIDATION_SCOPE);
        let journal = CallJournal::inspect_existing(
            &fixture.ledger,
            TENKI_PLACEMENT_VALIDATION_SCOPE,
            context,
            6,
        )
        .unwrap()
        .unwrap();
        let stats = journal.stats().unwrap();
        assert_eq!(stats.consumed, 1);
        assert_eq!(stats.completed, 1);
        assert_eq!(stats.unknown, 0);
        drop(journal);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn forged_prepared_manifest_with_alternate_worker_is_rejected_before_adapter() {
        let repository_root = workspace_root();
        let request = synthetic_validation_request();
        let root = repository_root
            .join("target/curry-option-validation-tests/tmp")
            .join(format!(
                "forged-worker-{}-{}",
                std::process::id(),
                now_unix()
            ));
        let context = "synthetic-forged-worker-path";
        let fixture = write_validation_stage1_fixture(
            &root,
            request,
            repository_root.join("target/debug/ygo-engine-worker.exe"),
            context,
        );

        // This synthetic request is rejected by the fixed worker-path gate before historical
        // genesis files are opened, so the default test remains independent of local evidence.
        // The manifest and prepared report have mutually consistent caller-computed hashes and
        // identities. The fixed Rust path gate must still reject the substituted worker before
        // an adapter is constructed or a ledger is created.
        let scans = std::sync::Arc::new(AtomicUsize::new(0));
        let calls = std::sync::Arc::new(AtomicUsize::new(0));
        let clock = std::sync::Arc::new(AtomicU64::new(fixture.started_at));
        let mut runtime = SyntheticRuntime {
            identity: fixture.identity.clone(),
            scans: scans.clone(),
            calls: calls.clone(),
            clock,
            result: synthetic_stage1_result(&fixture.request),
        };
        let arguments = vec![
            "runner".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_sha256,
            "--prepared-sha256".into(),
            fixture.prepared_sha256,
            "--trace-stderr".into(),
        ];
        let mut stdout = Vec::new();
        let error = execute_with_runtime_to(
            &arguments,
            &mut runtime,
            Some(&root),
            Some(&repository_root),
            &mut stdout,
        )
        .expect_err("alternate worker path must be rejected");

        assert!(error
            .to_string()
            .contains("validation worker path is not the fixed candidate artifact"));
        assert_eq!(scans.load(Ordering::SeqCst), 0);
        assert_eq!(calls.load(Ordering::SeqCst), 0);
        assert!(!fixture.ledger.exists());
        assert!(!fixture.output.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_duplicate_keys_and_noncanonical_paths() {
        assert!(serde_json::from_str::<StrictValue>(r#"{"x":1,"x":2}"#).is_err());
        assert!(serde_json::from_str::<StrictValue>(r#"{"a":[{"b":1,"b":2}]}"#).is_err());
        let root = research_root(BatchKind::TenkiPlacementProbeV1).unwrap();
        assert!(safe(&root.join("stage-1.json")).is_ok());
        assert!(safe(&root.join("nested/stage-1.json")).is_err());
        assert!(safe(&root.join("../stage-1.json")).is_err());
        let confirmation_root = research_root(BatchKind::TenkiPlacementConfirmationV1).unwrap();
        assert!(safe_for(
            &confirmation_root.join("stage-1.json"),
            BatchKind::TenkiPlacementConfirmationV1
        )
        .is_ok());
        assert!(safe_for(
            &root.join("stage-1.json"),
            BatchKind::TenkiPlacementConfirmationV1
        )
        .is_err());
    }
}
