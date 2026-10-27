//! Fixed seven-stage Mooyan Curry validation runner.
//!
//! All mode selection, paths, scope, request shape, and budget are fixed here.
//! Read-only modes use `CallJournal::inspect_existing`; only the normal mode
//! opens the mutable Curry journal, and only after input, parent, manifest,
//! prepared-report, time, and asset checks have passed.

use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use ygo_engine_adapter::*;

const BATCH_KIND: &str = "curry-option-validation-v1";
const CONFIRMATION_BATCH_KIND: &str = "curry-option-confirmation-v1";
const VERIFICATION_BATCH_KIND: &str = "curry-option-verification-v1";
const REVALIDATION_BATCH_KIND: &str = "curry-option-revalidation-v1";
const MANIFEST_KIND: &str = "native_curry_option_validation_manifest";
const PREPARED_KIND: &str = "native_curry_option_validation_prepared";
const SEAL_KIND: &str = "curry_option_validation_stage_input_seal";
const STAGE_KIND: &str = "native_curry_option_validation_stage";
const CONFIRMATION_MANIFEST_KIND: &str = "native_curry_option_confirmation_manifest";
const CONFIRMATION_PREPARED_KIND: &str = "native_curry_option_confirmation_prepared";
const CONFIRMATION_SEAL_KIND: &str = "curry_option_confirmation_stage_input_seal";
const CONFIRMATION_STAGE_KIND: &str = "native_curry_option_confirmation_stage";
const VERIFICATION_MANIFEST_KIND: &str = "native_curry_option_verification_manifest";
const VERIFICATION_PREPARED_KIND: &str = "native_curry_option_verification_prepared";
const VERIFICATION_SEAL_KIND: &str = "curry_option_verification_stage_input_seal";
const VERIFICATION_STAGE_KIND: &str = "native_curry_option_verification_stage";
const REVALIDATION_MANIFEST_KIND: &str = "native_curry_option_revalidation_manifest";
const REVALIDATION_PREPARED_KIND: &str = "native_curry_option_revalidation_prepared";
const REVALIDATION_SEAL_KIND: &str = "curry_option_revalidation_stage_input_seal";
const REVALIDATION_STAGE_KIND: &str = "native_curry_option_revalidation_stage";
const CONFIRMATION_ROOT: &str =
    "data/runtime/p1-curry-option-confirmation-native-2026-10-24/research";
const VERIFICATION_ROOT: &str =
    "data/runtime/p1-curry-option-verification-native-2026-10-25/research";
const REVALIDATION_ROOT: &str =
    "data/runtime/p1-curry-option-revalidation-native-2026-10-26/research";
const BASELINE_ACCEPTANCE_SHA256: &str =
    "242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9";
const BASELINE_DELIVERY_SHA256: &str =
    "7c46a4a790c56dea2daf77478c5a33654ee20bb3bd3179bdfb57ebf74cc21061";
const CONFIRMATION_BASELINE_DELIVERY_SHA256: &str =
    "58f9d28bcf5ac20cd3ee517aa70a6cc9fec294973a295a51d1dc415b4212eee0";
const CONFIRMATION_BASELINE_AUDIT_SHA256: &str =
    "f31e019affc99d3cf8cfc81921f72a424c904fcc4750b67a0a443ae3fc5a74b5";
const VERIFICATION_BASELINE_ACCEPTANCE_SHA256: &str =
    "704a72b2ad65ba95874030f199158a673ce18e19901b29d9bfb63f3fb8d78318";
const VERIFICATION_RESERVATION_SHA256: &str =
    "14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f";
const VERIFICATION_RESERVATION_ID: &str =
    "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63";
const VERIFICATION_RESERVATION_POLICY: &str = "curry-unknown-reserve-seven-v1";
const REVALIDATION_BASELINE_DELIVERY_SHA256: &str =
    "dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55";
const REVALIDATION_BASELINE_RECOVERY_SHA256: &str =
    "69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468";
const ADAPTER_CODEC_SHA256: &str =
    "68cf8de986c331060f72d95a56acc68ecec34d916230f5302d33210b254ca42d";
const PREPARATION_SHA256: &str = "235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022";
const PREPARATION_REPORT_SHA256: &str =
    "22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073";
const PREPARATION_ACCEPTANCE_SHA256: &str =
    "0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7";
const CANDIDATE_CASE_SHA256: &str =
    "71aa1e51edf74b3b4b572d61cbdaf7b25414ebc6fba745c72b1e82fe18e5a23c";
const BASE_REQUEST_SHA256: &str =
    "d25d2e79a58728221111d9007f5890b3e99be2bdcf4a8aee1a17554d59da91bb";
const OPERATIONS_SOURCE_SHA256: &str =
    "b46cf0d53825cb662af319a7382015b555422aa11903067445c994c4b0c8a990";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
enum BatchKind {
    #[serde(rename = "curry-option-validation-v1")]
    ValidationV1,
    #[serde(rename = "curry-option-confirmation-v1")]
    ConfirmationV1,
    #[serde(rename = "curry-option-verification-v1")]
    VerificationV1,
    #[serde(rename = "curry-option-revalidation-v1")]
    RevalidationV1,
}

#[derive(Clone, Copy)]
struct RunnerSpec {
    batch_kind: &'static str,
    scope: &'static str,
    root_relative: &'static str,
    manifest_kind: &'static str,
    prepared_kind: &'static str,
    seal_kind: &'static str,
    stage_kind: &'static str,
    limit: usize,
    planned_calls: usize,
    wall_seconds: u64,
    old_consumed: usize,
    baseline_acceptance_sha256: Option<&'static str>,
    baseline_delivery_sha256: &'static str,
    baseline_audit_sha256: Option<&'static str>,
    baseline_recovery_sha256: Option<&'static str>,
    reservation_sha256: Option<&'static str>,
    reservation_id: Option<&'static str>,
    reservation_policy_id: Option<&'static str>,
    certified_historical_consumed: Option<usize>,
    policy_reserved: Option<usize>,
    planning_base: Option<usize>,
    input_role_count: usize,
}

impl BatchKind {
    fn spec(self) -> RunnerSpec {
        match self {
            Self::ValidationV1 => RunnerSpec {
                batch_kind: BATCH_KIND,
                scope: CURRY_OPTION_SCOPE,
                root_relative: "data/runtime/p1-curry-option-validation-native-2026-10-23/research",
                manifest_kind: MANIFEST_KIND,
                prepared_kind: PREPARED_KIND,
                seal_kind: SEAL_KIND,
                stage_kind: STAGE_KIND,
                limit: 7,
                planned_calls: 7,
                wall_seconds: 7_200,
                old_consumed: 32,
                baseline_acceptance_sha256: Some(BASELINE_ACCEPTANCE_SHA256),
                baseline_delivery_sha256: BASELINE_DELIVERY_SHA256,
                baseline_audit_sha256: None,
                baseline_recovery_sha256: None,
                reservation_sha256: None,
                reservation_id: None,
                reservation_policy_id: None,
                certified_historical_consumed: None,
                policy_reserved: None,
                planning_base: None,
                input_role_count: 20,
            },
            Self::ConfirmationV1 => RunnerSpec {
                batch_kind: CONFIRMATION_BATCH_KIND,
                scope: CURRY_OPTION_CONFIRMATION_SCOPE,
                root_relative: CONFIRMATION_ROOT,
                manifest_kind: CONFIRMATION_MANIFEST_KIND,
                prepared_kind: CONFIRMATION_PREPARED_KIND,
                seal_kind: CONFIRMATION_SEAL_KIND,
                stage_kind: CONFIRMATION_STAGE_KIND,
                limit: 7,
                planned_calls: 7,
                wall_seconds: 7_200,
                old_consumed: 32,
                baseline_acceptance_sha256: None,
                baseline_delivery_sha256: CONFIRMATION_BASELINE_DELIVERY_SHA256,
                baseline_audit_sha256: Some(CONFIRMATION_BASELINE_AUDIT_SHA256),
                baseline_recovery_sha256: None,
                reservation_sha256: None,
                reservation_id: None,
                reservation_policy_id: None,
                certified_historical_consumed: None,
                policy_reserved: None,
                planning_base: None,
                input_role_count: 21,
            },
            Self::VerificationV1 => RunnerSpec {
                batch_kind: VERIFICATION_BATCH_KIND,
                scope: CURRY_OPTION_VERIFICATION_SCOPE,
                root_relative: VERIFICATION_ROOT,
                manifest_kind: VERIFICATION_MANIFEST_KIND,
                prepared_kind: VERIFICATION_PREPARED_KIND,
                seal_kind: VERIFICATION_SEAL_KIND,
                stage_kind: VERIFICATION_STAGE_KIND,
                limit: 7,
                planned_calls: 7,
                wall_seconds: 7_200,
                old_consumed: 32,
                baseline_acceptance_sha256: Some(VERIFICATION_BASELINE_ACCEPTANCE_SHA256),
                baseline_delivery_sha256: "",
                baseline_audit_sha256: None,
                baseline_recovery_sha256: None,
                reservation_sha256: Some(VERIFICATION_RESERVATION_SHA256),
                reservation_id: Some(VERIFICATION_RESERVATION_ID),
                reservation_policy_id: Some(VERIFICATION_RESERVATION_POLICY),
                certified_historical_consumed: Some(32),
                policy_reserved: Some(7),
                planning_base: Some(39),
                input_role_count: 21,
            },
            Self::RevalidationV1 => RunnerSpec {
                batch_kind: REVALIDATION_BATCH_KIND,
                scope: CURRY_OPTION_REVALIDATION_SCOPE,
                root_relative: REVALIDATION_ROOT,
                manifest_kind: REVALIDATION_MANIFEST_KIND,
                prepared_kind: REVALIDATION_PREPARED_KIND,
                seal_kind: REVALIDATION_SEAL_KIND,
                stage_kind: REVALIDATION_STAGE_KIND,
                limit: 7,
                planned_calls: 7,
                wall_seconds: 7_200,
                old_consumed: 33,
                baseline_acceptance_sha256: None,
                baseline_delivery_sha256: REVALIDATION_BASELINE_DELIVERY_SHA256,
                baseline_audit_sha256: None,
                baseline_recovery_sha256: Some(REVALIDATION_BASELINE_RECOVERY_SHA256),
                reservation_sha256: Some(VERIFICATION_RESERVATION_SHA256),
                reservation_id: Some(VERIFICATION_RESERVATION_ID),
                reservation_policy_id: Some(VERIFICATION_RESERVATION_POLICY),
                certified_historical_consumed: Some(33),
                policy_reserved: Some(7),
                planning_base: Some(40),
                input_role_count: 22,
            },
        }
    }
}

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
    batch_kind: BatchKind,
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Mode {
    Run,
    Preflight,
    Stats,
    VerifyRecorded,
    AuditSavedInputOnly,
}

struct Options {
    input: PathBuf,
    input_sha256: String,
    mode: Mode,
    prepared_sha256: Option<String>,
    trace_stderr: bool,
}

struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = StrictValue;

            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("JSON without duplicate object keys")
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

struct Trace {
    enabled: bool,
}

struct Phase {
    enabled: bool,
    name: &'static str,
    started: Instant,
}

impl Trace {
    fn phase(&self, name: &'static str) -> Phase {
        if self.enabled {
            eprintln!("{}", json!({"phase":name,"event":"start"}));
        }
        Phase {
            enabled: self.enabled,
            name,
            started: Instant::now(),
        }
    }
}

impl Drop for Phase {
    fn drop(&mut self) {
        if self.enabled {
            eprintln!(
                "{}",
                json!({"phase":self.name,"event":"end","elapsed_ns":self.started.elapsed().as_nanos()})
            );
        }
    }
}

fn fail(message: &'static str) -> Box<dyn std::error::Error> {
    message.into()
}

fn boxed_worker_error(error: WorkerError) -> Box<dyn std::error::Error> {
    error.message.into()
}

fn parse_options(args: &[String]) -> Result<Options, Box<dyn std::error::Error>> {
    if args.len() < 4 || args[2] != "--input-sha" || !valid_hash(&args[3]) {
        return Err(fail("input --input-sha HASH [mode flags] required"));
    }
    let mut mode = Mode::Run;
    let mut mode_seen = false;
    let mut prepared_sha256 = None;
    let mut trace_stderr = false;
    let mut i = 4;
    while i < args.len() {
        match args[i].as_str() {
            "--preflight-only" if !mode_seen => {
                mode = Mode::Preflight;
                mode_seen = true;
                i += 1;
            }
            "--stats" if !mode_seen => {
                mode = Mode::Stats;
                mode_seen = true;
                i += 1;
            }
            "--verify-recorded" if !mode_seen => {
                mode = Mode::VerifyRecorded;
                mode_seen = true;
                i += 1;
            }
            "--audit-saved-input-only" if !mode_seen => {
                mode = Mode::AuditSavedInputOnly;
                mode_seen = true;
                i += 1;
            }
            "--trace-stderr" if !trace_stderr => {
                trace_stderr = true;
                i += 1;
            }
            "--prepared-sha256" if prepared_sha256.is_none() && i + 1 < args.len() => {
                if !valid_hash(&args[i + 1]) {
                    return Err(fail("invalid prepared report hash"));
                }
                prepared_sha256 = Some(args[i + 1].clone());
                i += 2;
            }
            _ => return Err(fail("unknown, repeated, or conflicting runner option")),
        }
    }
    match mode {
        Mode::Run if prepared_sha256.is_none() || !trace_stderr => {
            return Err(fail("normal mode requires prepared hash and stderr trace"));
        }
        Mode::AuditSavedInputOnly if prepared_sha256.is_none() || !trace_stderr => {
            return Err(fail(
                "saved input audit requires prepared hash and stderr trace",
            ));
        }
        Mode::Preflight if prepared_sha256.is_some() || !trace_stderr => {
            return Err(fail("preflight requires stderr trace and no prepared hash"));
        }
        Mode::Stats | Mode::VerifyRecorded if prepared_sha256.is_some() || trace_stderr => {
            return Err(fail("read-only modes do not accept run-only flags"));
        }
        _ => {}
    }
    Ok(Options {
        input: PathBuf::from(&args[1]),
        input_sha256: args[3].clone(),
        mode,
        prepared_sha256,
        trace_stderr,
    })
}

fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn historical_source_transition() -> Value {
    json!({
        "scope": CURRY_OPTION_SCOPE,
        "path": "crates/ygo-engine-adapter/src/codec.rs",
        "historical_sha256": "224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e",
        "current_sha256": ADAPTER_CODEC_SHA256,
        "reason": "RECOVER-92-decoder-added-for-this-fixed-scope",
        "historical_bytes_verified_from_archive": true
    })
}

fn strict_value(raw: &[u8]) -> Result<Value, Box<dyn std::error::Error>> {
    Ok(serde_json::from_slice::<StrictValue>(raw)?.0)
}

fn no_link_components(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    for ancestor in path.ancestors() {
        if let Ok(metadata) = fs::symlink_metadata(ancestor) {
            if metadata.file_type().is_symlink() {
                return Err(fail("linked Curry evidence path rejected"));
            }
        }
    }
    Ok(())
}

fn read_strict(path: &Path) -> Result<(Vec<u8>, Value), Box<dyn std::error::Error>> {
    no_link_components(path)?;
    let raw = fs::read(path)?;
    let value = strict_value(&raw)?;
    Ok((raw, value))
}

fn fixed_paths(
    input: &Input,
    input_path: &Path,
    root: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let expected_input = root.join(format!("stage-{}-input.json", input.stage));
    if input_path != expected_input
        || input.ledger != root.join("calls.jsonl")
        || input.output != root.join(format!("stage-{}.json", input.stage))
        || !input_path.is_absolute()
        || !input.ledger.is_absolute()
        || !input.output.is_absolute()
    {
        return Err(fail("fixed Curry input, ledger, or output path required"));
    }
    for path in [input_path, &input.ledger, &input.output] {
        no_link_components(path)?;
    }
    Ok(())
}

fn validate_input_and_seal(
    options: &Options,
    input: &Input,
    input_raw: &[u8],
    root: &Path,
) -> Result<Value, Box<dyn std::error::Error>> {
    let spec = input.batch_kind.spec();
    if !valid_hash(&input.context)
        || input.stage == 0
        || input.stage > 7
        || digest(input_raw) != options.input_sha256
    {
        return Err(fail("frozen Curry input contract differs"));
    }
    fixed_paths(input, &options.input, root)?;
    let request_path = root.join(format!("stage-{}-request.json", input.stage));
    let seal_path = root.join(format!("stage-{}-input-seal.json", input.stage));
    let (_, request_value) = read_strict(&request_path)?;
    if request_value != serde_json::to_value(&input.request)? {
        return Err(fail("saved Curry request differs from invocation"));
    }
    let (_, seal_value) = read_strict(&seal_path)?;
    let seal: InputSeal = serde_json::from_value(seal_value)?;
    if seal.schema_version != 1
        || seal.kind != spec.seal_kind
        || seal.context != input.context
        || seal.stage != input.stage
        || seal.input_sha256 != digest(input_raw)
    {
        return Err(fail("Curry stage input seal differs"));
    }
    validate_curry_option_request_shape(&input.request).map_err(|error| error.message)?;
    validate_manifest(root, input)?;
    Ok(json!({"input_sha256":digest(input_raw),"stage":input.stage,"context":input.context}))
}

fn validate_fixed_worker(input: &Input, root: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let expected = root
        .parent()
        .ok_or_else(|| fail("Curry research root parent missing"))?
        .join("native-artifacts")
        .join("ygo-engine-worker.exe");
    let actual = &input.request.engine.worker_path;
    if !actual.is_absolute() || actual != &expected {
        return Err(fail("fixed Curry worker artifact path required"));
    }
    Ok(())
}

fn expected_input_roles(batch_kind: BatchKind) -> std::collections::BTreeSet<&'static str> {
    let mut roles = std::collections::BTreeSet::from([
        "preparation",
        "preparation_report",
        "preparation_acceptance",
        "candidate_case",
        "base_request",
        "operations_source",
        "adapter_codec",
        "runner",
        "worker",
        "cli",
        "build_record",
        "identity",
        "window_start",
        "source_archive",
        "source_file_list",
        "ordinary_config",
        "tournament_config",
        "banlist",
        "core_source",
    ]);
    match batch_kind {
        BatchKind::ValidationV1 => {
            roles.insert("baseline_delivery");
        }
        BatchKind::ConfirmationV1 => {
            roles.insert("baseline_delivery");
            roles.insert("baseline_audit");
        }
        BatchKind::VerificationV1 => {
            roles.insert("baseline_acceptance");
            roles.insert("consumption_reservation");
        }
        BatchKind::RevalidationV1 => {
            roles.insert("baseline_delivery");
            roles.insert("baseline_recovery");
            roles.insert("consumption_reservation");
        }
    }
    roles
}

fn validate_manifest(root: &Path, input: &Input) -> Result<Value, Box<dyn std::error::Error>> {
    let spec = input.batch_kind.spec();
    let manifest_path = root.join("manifest.json");
    let (manifest_raw, manifest) = read_strict(&manifest_path)?;
    let mut unsigned = manifest.clone();
    let object = unsigned
        .as_object_mut()
        .ok_or_else(|| fail("Curry manifest must be an object"))?;
    object.remove("context");
    let manifest_object = manifest
        .as_object()
        .ok_or_else(|| fail("Curry manifest must be an object"))?;
    let baseline_source_fields_match = match input.batch_kind {
        BatchKind::ValidationV1 => {
            manifest["baseline_acceptance_sha256"]
                == spec.baseline_acceptance_sha256.unwrap_or_default()
                && !manifest_object.contains_key("baseline_audit_sha256")
                && !manifest_object.contains_key("reservation_id")
                && !manifest_object.contains_key("reservation_policy_id")
                && !manifest_object.contains_key("certified_historical_consumed")
                && !manifest_object.contains_key("policy_reserved")
                && !manifest_object.contains_key("planning_base")
        }
        BatchKind::ConfirmationV1 => {
            !manifest_object.contains_key("baseline_acceptance_sha256")
                && spec
                    .baseline_audit_sha256
                    .is_some_and(|expected| manifest["baseline_audit_sha256"] == expected)
                && !manifest_object.contains_key("reservation_id")
                && !manifest_object.contains_key("reservation_policy_id")
                && !manifest_object.contains_key("certified_historical_consumed")
                && !manifest_object.contains_key("policy_reserved")
                && !manifest_object.contains_key("planning_base")
        }
        BatchKind::VerificationV1 => {
            manifest["baseline_acceptance_sha256"]
                == spec.baseline_acceptance_sha256.unwrap_or_default()
                && !manifest_object.contains_key("baseline_audit_sha256")
                && !manifest_object.contains_key("baseline_delivery_sha256")
                && spec.certified_historical_consumed == Some(32)
                && manifest["certified_historical_consumed"]
                    == spec.certified_historical_consumed.unwrap_or_default()
                && spec.policy_reserved == Some(7)
                && manifest["policy_reserved"] == spec.policy_reserved.unwrap_or_default()
                && spec.planning_base == Some(39)
                && manifest["planning_base"] == spec.planning_base.unwrap_or_default()
                && manifest["reservation_id"] == spec.reservation_id.unwrap_or_default()
                && manifest["reservation_policy_id"]
                    == spec.reservation_policy_id.unwrap_or_default()
        }
        BatchKind::RevalidationV1 => {
            !manifest_object.contains_key("baseline_acceptance_sha256")
                && !manifest_object.contains_key("baseline_audit_sha256")
                && manifest["baseline_recovery_sha256"]
                    == spec.baseline_recovery_sha256.unwrap_or_default()
                && spec.certified_historical_consumed == Some(33)
                && manifest["certified_historical_consumed"]
                    == spec.certified_historical_consumed.unwrap_or_default()
                && spec.policy_reserved == Some(7)
                && manifest["policy_reserved"] == spec.policy_reserved.unwrap_or_default()
                && spec.planning_base == Some(40)
                && manifest["planning_base"] == spec.planning_base.unwrap_or_default()
                && manifest["reservation_id"] == spec.reservation_id.unwrap_or_default()
                && manifest["reservation_policy_id"]
                    == spec.reservation_policy_id.unwrap_or_default()
        }
    };
    let baseline_delivery_matches = match input.batch_kind {
        BatchKind::VerificationV1 => !manifest_object.contains_key("baseline_delivery_sha256"),
        BatchKind::ValidationV1 | BatchKind::ConfirmationV1 | BatchKind::RevalidationV1 => {
            manifest["baseline_delivery_sha256"] == spec.baseline_delivery_sha256
        }
    };
    let old_consumed_matches = match input.batch_kind {
        BatchKind::VerificationV1 | BatchKind::RevalidationV1 => {
            !manifest_object.contains_key("old_consumed")
        }
        BatchKind::ValidationV1 | BatchKind::ConfirmationV1 => {
            manifest["old_consumed"] == spec.old_consumed
        }
    };
    let reservation_hash_matches = match spec.reservation_sha256 {
        Some(expected) => {
            manifest["consumption_reservation_sha256"] == expected
                && manifest["input_sha256"]["consumption_reservation"] == expected
        }
        None => true,
    };
    if manifest["schema_version"] != 1
        || manifest["kind"] != spec.manifest_kind
        || manifest["scope"] != spec.scope
        || manifest["context"] != input.context
        || manifest["context"] != digest(&serde_json::to_vec(&unsigned)?)
        || manifest["started_at"] != input.started_at
        || manifest["limit"] != spec.limit
        || manifest["planned_calls"] != spec.planned_calls
        || manifest["wall_seconds"] != spec.wall_seconds
        || !old_consumed_matches
        || manifest["batch_kind"] != spec.batch_kind
        || !baseline_source_fields_match
        || !baseline_delivery_matches
        || !reservation_hash_matches
        || manifest["assets"]["ordinary"] != input.expected_identity
        || manifest["input_sha256"]["worker"]
            != input.expected_identity["roles"]["worker"]["sha256"]
        || manifest["historical_source_transition"] != historical_source_transition()
        || manifest["input_sha256"].as_object().map_or(true, |hashes| {
            hashes.len() != spec.input_role_count
                || hashes
                    .keys()
                    .map(String::as_str)
                    .collect::<std::collections::BTreeSet<_>>()
                    != expected_input_roles(input.batch_kind)
                || hashes
                    .values()
                    .any(|value| !value.as_str().is_some_and(valid_hash))
        })
    {
        return Err(fail("Curry manifest binding differs"));
    }
    let role_hashes = manifest["input_sha256"].as_object().unwrap();
    for role in [
        "preparation",
        "preparation_report",
        "preparation_acceptance",
        "candidate_case",
        "base_request",
        "operations_source",
        "adapter_codec",
        "runner",
        "worker",
        "cli",
        "build_record",
        "identity",
        "window_start",
        "source_archive",
        "source_file_list",
        "ordinary_config",
        "tournament_config",
        "banlist",
        "core_source",
    ] {
        if !role_hashes.contains_key(role) {
            return Err(fail("Curry manifest input role missing"));
        }
    }
    for (role, expected) in [
        ("preparation", PREPARATION_SHA256),
        ("preparation_report", PREPARATION_REPORT_SHA256),
        ("preparation_acceptance", PREPARATION_ACCEPTANCE_SHA256),
        ("candidate_case", CANDIDATE_CASE_SHA256),
        ("base_request", BASE_REQUEST_SHA256),
        ("operations_source", OPERATIONS_SOURCE_SHA256),
        ("core_source", OPERATIONS_SOURCE_SHA256),
        ("adapter_codec", ADAPTER_CODEC_SHA256),
    ] {
        if role_hashes.get(role).and_then(Value::as_str) != Some(expected) {
            return Err(fail("Curry manifest frozen source hash differs"));
        }
    }
    if let Some(expected) = spec.baseline_audit_sha256 {
        if role_hashes.get("baseline_audit").and_then(Value::as_str) != Some(expected) {
            return Err(fail("Curry manifest baseline audit hash differs"));
        }
    } else if role_hashes.contains_key("baseline_audit") {
        return Err(fail(
            "legacy Curry manifest has an unexpected baseline audit role",
        ));
    }
    match input.batch_kind {
        BatchKind::ValidationV1 | BatchKind::ConfirmationV1 => {
            if role_hashes.get("baseline_delivery").and_then(Value::as_str)
                != Some(spec.baseline_delivery_sha256)
            {
                return Err(fail("Curry baseline delivery input hash differs"));
            }
        }
        BatchKind::VerificationV1 => {
            if role_hashes
                .get("baseline_acceptance")
                .and_then(Value::as_str)
                != Some(VERIFICATION_BASELINE_ACCEPTANCE_SHA256)
                || role_hashes
                    .get("consumption_reservation")
                    .and_then(Value::as_str)
                    != spec.reservation_sha256
            {
                return Err(fail("Curry reservation source hash differs"));
            }
        }
        BatchKind::RevalidationV1 => {
            if role_hashes.get("baseline_delivery").and_then(Value::as_str)
                != Some(spec.baseline_delivery_sha256)
                || role_hashes.get("baseline_recovery").and_then(Value::as_str)
                    != spec.baseline_recovery_sha256
                || role_hashes
                    .get("consumption_reservation")
                    .and_then(Value::as_str)
                    != spec.reservation_sha256
            {
                return Err(fail("Curry revalidation source hashes differ"));
            }
        }
    }
    if input.stage == 1 {
        let request = serde_json::to_value(&input.request)?;
        if manifest["request"] != request
            || manifest["stage1_request_sha256"] != digest(&serde_json::to_vec(&request)?)
        {
            return Err(fail("Curry stage 1 differs from manifest request"));
        }
    }
    Ok(json!({"manifest_sha256":digest(&manifest_raw),"context":input.context}))
}

fn validate_prepared(
    root: &Path,
    input: &Input,
    prepared_sha256: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let spec = input.batch_kind.spec();
    let (prepared_raw, prepared) = read_strict(&root.join("prepared.json"))?;
    let (manifest_raw, _) = read_strict(&root.join("manifest.json"))?;
    let (stage1_raw, stage1_value) = read_strict(&root.join("stage-1-input.json"))?;
    if digest(&prepared_raw) != prepared_sha256
        || prepared["schema_version"] != 1
        || prepared["kind"] != spec.prepared_kind
        || prepared["prepared"] != true
        || prepared["execution_ready"] != true
        || prepared["native_calls"] != 0
        || prepared["planned_calls"] != spec.planned_calls
        || prepared["context"] != input.context
        || prepared["manifest_sha256"] != digest(&manifest_raw)
        || prepared["stage1_input_sha256"] != digest(&stage1_raw)
        || prepared["stage1_request_sha256"]
            != digest(&serde_json::to_vec(&stage1_value["request"])?)
        || [
            "proof_ready",
            "complete_action_coverage",
            "global_optimality",
            "native_probability_verified",
        ]
        .iter()
        .any(|field| prepared[*field] != false)
    {
        return Err(fail("Curry prepared report binding differs"));
    }
    let stage1: Input = serde_json::from_value(stage1_value)?;
    if stage1.stage != 1
        || stage1.context != input.context
        || stage1.started_at != input.started_at
        || stage1.ledger != input.ledger
        || stage1.batch_kind != input.batch_kind
    {
        return Err(fail("Curry prepared stage 1 differs"));
    }
    Ok(())
}

fn verify_parent_request(input: &Input, root: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let spec = input.batch_kind.spec();
    let parent_stage = curry_option_parent_stage(input.stage).map_err(|error| error.message)?;
    if parent_stage.is_none() {
        if !input.request.decisions.is_empty() {
            return Err(fail("Curry stage 1 decisions must be empty"));
        }
        return Ok(());
    }
    let view = CallJournal::inspect_existing(&input.ledger, spec.scope, &input.context, spec.limit)
        .map_err(boxed_worker_error)?
        .ok_or_else(|| fail("Curry parent ledger is required"))?;
    verify_parent_request_in_view(&view, input, root)?;
    // Drop the shared read-only file handle before the normal path opens the
    // same ledger exclusively. The caller repeats parent validation under the
    // exclusive journal lock before it can charge a request.
    drop(view);
    Ok(())
}

fn verify_parent_request_in_view(
    view: &ReadOnlyJournal,
    input: &Input,
    root: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let parent_stage = curry_option_parent_stage(input.stage).map_err(|error| error.message)?;
    let Some(parent_stage) = parent_stage else {
        if !input.request.decisions.is_empty() {
            return Err(fail("Curry stage 1 decisions must be empty"));
        }
        return Ok(());
    };
    let parent_path = root.join(format!("stage-{parent_stage}.json"));
    let (_, parent) = read_strict(&parent_path)?;
    verify_recorded_for_input(view, input, parent_stage, &parent).map_err(|error| error.message)?;
    if parent["successful"] != true {
        return Err(fail("Curry parent receipt did not pass"));
    }
    let expected = derive_curry_option_request_from_receipt(input.stage, &parent)
        .map_err(|error| error.message)?;
    if serde_json::to_value(expected)? != serde_json::to_value(&input.request)? {
        return Err(fail(
            "Curry child request differs from authenticated parent",
        ));
    }
    Ok(())
}

fn verify_recorded_for_input(
    view: &ReadOnlyJournal,
    input: &Input,
    stage: u8,
    receipt: &Value,
) -> Result<(), WorkerError> {
    let spec = input.batch_kind.spec();
    if receipt["kind"] != spec.stage_kind || receipt["scope"] != spec.scope {
        return Err(WorkerError::new(
            "curry_option_gate",
            "curry_option_runner",
            "recorded receipt uses a different fixed batch contract",
        ));
    }
    match input.batch_kind {
        BatchKind::ValidationV1 => {
            verify_curry_option_recorded(view, stage, &input.context, input.started_at, receipt)
        }
        BatchKind::ConfirmationV1 => verify_curry_option_confirmation_recorded(
            view,
            stage,
            &input.context,
            input.started_at,
            receipt,
        ),
        BatchKind::VerificationV1 => verify_curry_option_verification_recorded(
            view,
            stage,
            &input.context,
            input.started_at,
            receipt,
        ),
        BatchKind::RevalidationV1 => verify_curry_option_revalidation_recorded(
            view,
            stage,
            &input.context,
            input.started_at,
            receipt,
        ),
    }
}

trait RunnerServices {
    fn now(&mut self) -> Result<u64, Box<dyn std::error::Error>>;
    fn scan_identity(&mut self, input: &Input) -> Result<Value, Box<dyn std::error::Error>>;
    fn adapter(&mut self, input: &Input) -> Box<dyn EngineAdapter>;

    // Test services may change the journal after the read-only precheck. The
    // exclusive batch open must reject that change before the adapter runs.
    fn after_readonly_ledger_check(
        &mut self,
        _input: &Input,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }
}

struct ProductionServices;

impl RunnerServices for ProductionServices {
    fn now(&mut self) -> Result<u64, Box<dyn std::error::Error>> {
        unix_now()
    }

    fn scan_identity(&mut self, input: &Input) -> Result<Value, Box<dyn std::error::Error>> {
        capture_engine_identity(&input.request.engine)
            .map_err(|_| fail("Curry asset identity scan failed"))
    }

    fn adapter(&mut self, input: &Input) -> Box<dyn EngineAdapter> {
        Box::new(ProcessEngineAdapter::new(input.request.engine.clone()))
    }
}

struct AdapterHandle(Box<dyn EngineAdapter>);

impl EngineAdapter for AdapterHandle {
    fn doctor(&self) -> DoctorReport {
        self.0.doctor()
    }

    fn run(&self, input: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        self.0.run(input)
    }
}

fn verify_asset_identity(
    input: &Input,
    services: &mut dyn RunnerServices,
) -> Result<Value, Box<dyn std::error::Error>> {
    let found = services.scan_identity(input)?;
    if found != input.expected_identity
        || found["consistent"] != true
        || found["roles"]["dll"]["sha256"] != input.request.versions.engine_sha256
        || found["roles"]["cdb"]["sha256"] != input.request.versions.cdb_sha256
        || found["roles"]["script_manifest"]["sha256"] != input.request.versions.scripts_sha256
    {
        return Err(fail("Curry asset identity differs from frozen request"));
    }
    Ok(found)
}

fn publish_create_new(path: &Path, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(&serde_json::to_vec_pretty(value)?)?;
    file.sync_all()?;
    Ok(())
}

fn unix_now() -> Result<u64, Box<dyn std::error::Error>> {
    Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())
}

fn emit_to(output: &mut dyn Write, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    serde_json::to_writer(&mut *output, value)?;
    output.write_all(b"\n")?;
    Ok(())
}

fn add_verification_accounting(summary: &mut Value, spec: RunnerSpec, stats: &LedgerStats) {
    if spec.reservation_id.is_none() {
        return;
    }
    let known = stats.unknown == 0
        && stats.reserved == 0
        && stats.abandoned == 0
        && stats.consumed == stats.completed;
    let new_consumed = known.then_some(stats.consumed);
    summary["certified_historical_consumed"] = json!(spec.certified_historical_consumed);
    summary["policy_reserved"] = json!(spec.policy_reserved);
    summary["planning_base"] = json!(spec.planning_base);
    summary["reservation_id"] = json!(spec.reservation_id);
    summary["reservation_policy_id"] = json!(spec.reservation_policy_id);
    summary["new_consumed"] = json!(new_consumed);
    summary["certified_consumed_including_new"] = json!(new_consumed
        .zip(spec.certified_historical_consumed)
        .map(|(new, old)| old + new));
    summary["planning_total"] = json!(new_consumed
        .zip(spec.planning_base)
        .map(|(new, base)| base + new));
    summary["old_confirmation_actual_consumed"] = Value::Null;
    summary["actual_all_history_cumulative"] = Value::Null;
    summary["unknown"] = json!(stats.unknown);
}

fn root_for_input(input_path: &Path) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let (_, value) = read_strict(input_path)?;
    let input: Input = serde_json::from_value(value)?;
    let root = std::env::current_dir()?.join(input.batch_kind.spec().root_relative);
    if input_path.parent() != Some(root.as_path()) {
        return Err(fail("input path differs from fixed batch kind root"));
    }
    Ok(root)
}

fn execute(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let options = parse_options(args)?;
    let root = root_for_input(&options.input)?;
    let stdout = std::io::stdout();
    let mut output = stdout.lock();
    execute_with_services(args, &root, &mut ProductionServices, &mut output)
}

fn execute_with_services(
    args: &[String],
    root: &Path,
    services: &mut dyn RunnerServices,
    output: &mut dyn Write,
) -> Result<(), Box<dyn std::error::Error>> {
    let options = parse_options(args)?;
    let trace = Trace {
        enabled: options.trace_stderr,
    };
    let input_phase = trace.phase("input_validation");
    if !options.input.is_absolute() || options.input.parent() != Some(root) {
        return Err(fail("fixed Curry input path required"));
    }
    no_link_components(&options.input)?;
    let (input_raw, input_value) = read_strict(&options.input)?;
    if digest(&input_raw) != options.input_sha256 {
        return Err(fail("frozen Curry input hash mismatch"));
    }
    let input: Input = serde_json::from_value(input_value)?;
    let spec = input.batch_kind.spec();
    validate_input_and_seal(&options, &input, &input_raw, root)?;
    validate_fixed_worker(&input, root)?;
    drop(input_phase);

    match options.mode {
        Mode::Preflight => {
            if input.stage != 1 || input.output.exists() {
                return Err(fail("Curry preflight only accepts fresh stage 1"));
            }
            if services.now()? < input.started_at {
                return Err(fail("Curry clock precedes frozen window"));
            }
            let _phase = trace.phase("shared_preflight");
            let found = verify_asset_identity(&input, services)?;
            emit_to(
                output,
                &json!({
                    "preflight_passed":true,"native_calls":0,"execution_ready":false,
                    "stage":1,"context":input.context,"identity_sha256":found["identity"]
                }),
            )?;
            return Ok(());
        }
        Mode::Stats | Mode::VerifyRecorded => {
            let _phase = trace.phase("ledger_check");
            let view = CallJournal::inspect_existing(
                &input.ledger,
                spec.scope,
                &input.context,
                spec.limit,
            )
            .map_err(boxed_worker_error)?
            .ok_or_else(|| fail("existing Curry ledger required"))?;
            let stats = view.stats().map_err(boxed_worker_error)?;
            if options.mode == Mode::Stats {
                let mut summary = json!({"native_calls":0,"ledger":stats});
                add_verification_accounting(&mut summary, spec, &stats);
                emit_to(output, &summary)?;
                return Ok(());
            }
            let (_, receipt) = read_strict(&input.output)?;
            if receipt["request"] != serde_json::to_value(&input.request)?
                || receipt["stage"] != input.stage
                || receipt["context"] != input.context
            {
                return Err(fail("saved Curry receipt differs from invocation"));
            }
            verify_recorded_for_input(&view, &input, input.stage, &receipt)
                .map_err(|error| error.message)?;
            let mut summary = json!({
                "verified_recorded":true,"native_calls":0,
                "successful":receipt["successful"],"ledger":stats
            });
            add_verification_accounting(&mut summary, spec, &stats);
            emit_to(output, &summary)?;
            // A valid failed receipt is still a successful read-only verification.
            // The Python orchestrator inspects `successful` and stops the batch.
            return Ok(());
        }
        Mode::AuditSavedInputOnly => {
            if input.batch_kind != BatchKind::VerificationV1 || input.stage != 2 {
                return Err(fail(
                    "saved input audit only accepts verification scope stage 2",
                ));
            }
            let prepared_hash = options
                .prepared_sha256
                .as_deref()
                .ok_or_else(|| fail("saved input audit requires prepared report hash"))?;
            validate_prepared(root, &input, prepared_hash)?;
            if input.output.exists() {
                return Err(fail("saved stage output already exists"));
            }
            // Keep a single shared view for both parent receipt validation and
            // ledger statistics. This makes the read-only audit internally
            // consistent even if an external process attempts to replace the
            // ledger between checks.
            let view = CallJournal::inspect_existing(
                &input.ledger,
                spec.scope,
                &input.context,
                spec.limit,
            )
            .map_err(boxed_worker_error)?
            .ok_or_else(|| fail("existing Curry ledger required"))?;
            {
                let _phase = trace.phase("parent_request_check");
                verify_parent_request_in_view(&view, &input, root)?;
            }
            let found = {
                let _phase = trace.phase("saved_input_asset_scan");
                verify_asset_identity(&input, services)?
            };
            let stats = {
                let _phase = trace.phase("ledger_check");
                let stats = view.stats().map_err(boxed_worker_error)?;
                validate_curry_option_slot(input.stage, &stats).map_err(|error| error.message)?;
                if stats.consumed != 1
                    || stats.completed != 1
                    || stats.unknown != 0
                    || stats.reserved != 0
                    || stats.abandoned != 0
                {
                    return Err(fail("saved stage 2 ledger prefix differs"));
                }
                stats
            };
            emit_to(
                output,
                &json!({
                    "saved_input_audit_passed":true,
                    "native_calls":0,
                    "execution_ready":false,
                    "stage":2,
                    "context":input.context,
                    "identity_sha256":found["identity"],
                    "parent_receipt_valid":true,
                    "request_derivation_valid":true,
                    "stage_receipt_absent":true,
                    "ledger":stats
                }),
            )?;
            return Ok(());
        }
        Mode::Run => {}
    }

    let prepared_hash = options
        .prepared_sha256
        .as_deref()
        .ok_or_else(|| fail("normal Curry invocation lacks prepared hash"))?;
    validate_prepared(root, &input, prepared_hash)?;
    if input.output.exists() {
        return Err(fail("Curry stage output already exists"));
    }
    let now = services.now()?;
    if !curry_option_window_allows_request(input.started_at, now) {
        return Err(fail("Curry request window has insufficient time"));
    }
    {
        let _phase = trace.phase("shared_preflight");
        verify_asset_identity(&input, services)?;
    }
    verify_parent_request(&input, root)?;
    let found = {
        let _phase = trace.phase("precharge_scan");
        verify_asset_identity(&input, services)?
    };
    {
        let existing =
            CallJournal::inspect_existing(&input.ledger, spec.scope, &input.context, spec.limit)
                .map_err(boxed_worker_error)?;
        if let Some(view) = existing {
            let stats = view.stats().map_err(boxed_worker_error)?;
            validate_curry_option_slot(input.stage, &stats).map_err(|error| error.message)?;
        } else if input.stage != 1 {
            return Err(fail("Curry later stage requires existing ledger"));
        }
    }
    services.after_readonly_ledger_check(&input)?;
    let batch = {
        let _phase = trace.phase("ledger_check");
        match input.batch_kind {
            BatchKind::ValidationV1 => {
                CurryOptionBatch::open(&input.ledger, &input.context, input.started_at)
            }
            BatchKind::ConfirmationV1 => {
                CurryOptionBatch::open_confirmation(&input.ledger, &input.context, input.started_at)
            }
            BatchKind::VerificationV1 => {
                CurryOptionBatch::open_verification(&input.ledger, &input.context, input.started_at)
            }
            BatchKind::RevalidationV1 => {
                CurryOptionBatch::open_revalidation(&input.ledger, &input.context, input.started_at)
            }
        }
        .map_err(|error| error.message)?
    };
    batch
        .validate_request(input.stage, &input.request)
        .map_err(|error| error.message)?;
    batch
        .save_assets_before(input.stage, &found)
        .map_err(|error| error.message)?;
    batch
        .require_time_at(services.now()?)
        .map_err(|error| error.message)?;
    let adapter = AdapterHandle(services.adapter(&input));
    let run = {
        let _phase = trace.phase("batch_call");
        batch.run(adapter, input.stage, &input.request)
    };
    let outcome = if run.is_err() {
        batch
            .load_outcome(input.stage, &input.request)
            .map_err(|error| error.message)?
            .ok_or_else(|| run.err().unwrap().message)?
    } else {
        run
    };
    let after = {
        let _phase = trace.phase("postcharge_scan");
        verify_asset_identity(&input, services).ok()
    };
    let receipt = {
        let _phase = trace.phase("receipt_save");
        batch
            .record_evidence(
                input.stage,
                &input.request,
                &outcome,
                &found,
                after.as_ref(),
            )
            .map_err(|error| error.message)?
    };
    publish_create_new(&input.output, &receipt)?;
    let stats = batch.stats().map_err(boxed_worker_error)?;
    let mut summary = json!({
        "successful":receipt["successful"],"native_calls":1,"ledger":stats
    });
    add_verification_accounting(&mut summary, spec, &stats);
    emit_to(output, &summary)?;
    if receipt["successful"] != true {
        std::process::exit(1);
    }
    Ok(())
}

fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    if let Err(error) = execute(&args) {
        eprintln!("{error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use ygo_domain::{CardId, Deck};

    fn argv(flags: &[&str]) -> Vec<String> {
        let mut result = vec![
            "curry-option-validation".to_string(),
            "stage-1-input.json".to_string(),
            "--input-sha".to_string(),
            "a".repeat(64),
        ];
        result.extend(flags.iter().map(|item| (*item).to_string()));
        result
    }

    #[test]
    fn batch_kind_routes_only_to_fixed_scope_contracts() {
        let old: BatchKind = serde_json::from_str(r#""curry-option-validation-v1""#).unwrap();
        let new: BatchKind = serde_json::from_str(r#""curry-option-confirmation-v1""#).unwrap();
        assert_eq!(old, BatchKind::ValidationV1);
        assert_eq!(new, BatchKind::ConfirmationV1);

        let old_spec = old.spec();
        assert_eq!(old_spec.scope, CURRY_OPTION_SCOPE);
        assert_eq!(old_spec.manifest_kind, MANIFEST_KIND);
        assert_eq!(old_spec.seal_kind, SEAL_KIND);
        assert_eq!(old_spec.input_role_count, 20);
        assert_eq!(
            curry_option_validation_research_root().unwrap(),
            std::env::current_dir()
                .unwrap()
                .join(old_spec.root_relative)
        );

        let new_spec = new.spec();
        assert_eq!(new_spec.scope, CURRY_OPTION_CONFIRMATION_SCOPE);
        assert_eq!(
            new_spec.manifest_kind,
            "native_curry_option_confirmation_manifest"
        );
        assert_eq!(
            new_spec.prepared_kind,
            "native_curry_option_confirmation_prepared"
        );
        assert_eq!(
            new_spec.seal_kind,
            "curry_option_confirmation_stage_input_seal"
        );
        assert_eq!(new_spec.input_role_count, 21);
        assert_ne!(old_spec.root_relative, new_spec.root_relative);
        assert_eq!(
            curry_option_confirmation_research_root().unwrap(),
            std::env::current_dir()
                .unwrap()
                .join(new_spec.root_relative)
        );

        let verification: BatchKind =
            serde_json::from_str(r#""curry-option-verification-v1""#).unwrap();
        assert_eq!(verification, BatchKind::VerificationV1);
        let verification_spec = verification.spec();
        assert_eq!(verification_spec.scope, CURRY_OPTION_VERIFICATION_SCOPE);
        assert_eq!(verification_spec.batch_kind, "curry-option-verification-v1");
        assert_eq!(
            verification_spec.manifest_kind,
            "native_curry_option_verification_manifest"
        );
        assert_eq!(
            verification_spec.prepared_kind,
            "native_curry_option_verification_prepared"
        );
        assert_eq!(
            verification_spec.seal_kind,
            "curry_option_verification_stage_input_seal"
        );
        assert_eq!(
            verification_spec.stage_kind,
            "native_curry_option_verification_stage"
        );
        assert_eq!(verification_spec.input_role_count, 21);
        assert_eq!(verification_spec.limit, 7);
        assert_eq!(verification_spec.wall_seconds, 7_200);
        assert_ne!(verification_spec.root_relative, old_spec.root_relative);
        assert_ne!(verification_spec.root_relative, new_spec.root_relative);
        assert!(std::env::current_dir()
            .unwrap()
            .join(verification_spec.root_relative)
            .ends_with("p1-curry-option-verification-native-2026-10-25/research"));

        assert!(serde_json::from_str::<BatchKind>("null").is_err());
        assert!(serde_json::from_str::<BatchKind>(r#""unknown-v1""#).is_err());
    }

    #[test]
    fn revalidation_batch_kind_routes_to_its_own_fixed_contract() {
        let kind: BatchKind = serde_json::from_str(r#""curry-option-revalidation-v1""#).unwrap();
        assert_eq!(kind, BatchKind::RevalidationV1);
        let spec = kind.spec();
        assert_eq!(spec.batch_kind, "curry-option-revalidation-v1");
        assert_eq!(spec.scope, "curry-option-revalidation-v1");
        assert_eq!(
            spec.root_relative,
            "data/runtime/p1-curry-option-revalidation-native-2026-10-26/research"
        );
        assert_eq!(
            spec.manifest_kind,
            "native_curry_option_revalidation_manifest"
        );
        assert_eq!(
            spec.prepared_kind,
            "native_curry_option_revalidation_prepared"
        );
        assert_eq!(spec.seal_kind, "curry_option_revalidation_stage_input_seal");
        assert_eq!(spec.stage_kind, "native_curry_option_revalidation_stage");
        assert_eq!(spec.input_role_count, 22);
        assert_eq!(spec.limit, 7);
        assert_eq!(spec.planned_calls, 7);
        assert_eq!(spec.wall_seconds, 7_200);
        assert_eq!(spec.certified_historical_consumed, Some(33));
        assert_eq!(spec.policy_reserved, Some(7));
        assert_eq!(spec.planning_base, Some(40));
        assert_eq!(spec.reservation_id, Some(VERIFICATION_RESERVATION_ID));
        assert_eq!(
            spec.reservation_policy_id,
            Some(VERIFICATION_RESERVATION_POLICY)
        );
        assert!(spec.reservation_sha256.is_some());
        assert!(spec.baseline_recovery_sha256.is_some());
        assert_ne!(
            spec.root_relative,
            BatchKind::VerificationV1.spec().root_relative
        );
        assert!(serde_json::from_str::<BatchKind>(r#""future-curry-kind""#).is_err());
    }

    #[test]
    fn verification_manifest_binds_reservation_roles_and_accounting() {
        let fixture = runner_fixture_for(BatchKind::VerificationV1);
        let (_, input_value) = read_strict(&fixture.input_path).unwrap();
        let mut input: Input = serde_json::from_value(input_value).unwrap();
        let (_, manifest) = read_strict(&fixture.root.join("manifest.json")).unwrap();
        assert!(validate_manifest(&fixture.root, &input).is_ok());
        assert!(manifest.get("old_consumed").is_none());
        assert_eq!(
            manifest["consumption_reservation_sha256"],
            manifest["input_sha256"]["consumption_reservation"]
        );

        for (field, value) in [
            ("certified_historical_consumed", json!(31)),
            ("policy_reserved", json!(8)),
            ("planning_base", json!(40)),
            ("reservation_id", json!("f".repeat(64))),
            ("reservation_policy_id", json!("other-policy")),
        ] {
            let mut changed = manifest.clone();
            changed[field] = value;
            let new_context = rebind_manifest_context(&mut changed);
            write_json(&fixture.root.join("manifest.json"), &changed);
            input.context = new_context;
            assert!(
                validate_manifest(&fixture.root, &input).is_err(),
                "tampered verification field {field} must be rejected"
            );
        }

        let mut changed = manifest.clone();
        changed["input_sha256"]["consumption_reservation"] = json!("e".repeat(64));
        let new_context = rebind_manifest_context(&mut changed);
        write_json(&fixture.root.join("manifest.json"), &changed);
        input.context = new_context;
        assert!(validate_manifest(&fixture.root, &input).is_err());

        let mut changed = manifest.clone();
        changed["consumption_reservation_sha256"] = json!("f".repeat(64));
        let new_context = rebind_manifest_context(&mut changed);
        write_json(&fixture.root.join("manifest.json"), &changed);
        input.context = new_context;
        assert!(validate_manifest(&fixture.root, &input).is_err());

        let mut changed = manifest.clone();
        changed
            .as_object_mut()
            .unwrap()
            .remove("consumption_reservation_sha256");
        let new_context = rebind_manifest_context(&mut changed);
        write_json(&fixture.root.join("manifest.json"), &changed);
        input.context = new_context;
        assert!(validate_manifest(&fixture.root, &input).is_err());

        let mut changed = manifest.clone();
        changed["input_sha256"]["baseline_delivery"] = json!("d".repeat(64));
        let new_context = rebind_manifest_context(&mut changed);
        write_json(&fixture.root.join("manifest.json"), &changed);
        input.context = new_context;
        assert!(validate_manifest(&fixture.root, &input).is_err());

        let mut changed = manifest;
        changed["baseline_delivery_sha256"] = json!("");
        let new_context = rebind_manifest_context(&mut changed);
        write_json(&fixture.root.join("manifest.json"), &changed);
        input.context = new_context;
        assert!(validate_manifest(&fixture.root, &input).is_err());
    }

    #[test]
    fn verification_accounting_keeps_totals_unknown_for_unsettled_ledger() {
        let spec = BatchKind::VerificationV1.spec();
        let stats = LedgerStats {
            consumed: 2,
            reserved: 0,
            completed: 1,
            unknown: 1,
            abandoned: 0,
            limit: 7,
        };
        let mut summary = json!({});
        add_verification_accounting(&mut summary, spec, &stats);
        assert_eq!(summary["new_consumed"], Value::Null);
        assert_eq!(summary["certified_consumed_including_new"], Value::Null);
        assert_eq!(summary["planning_total"], Value::Null);
        assert_eq!(summary["unknown"], 1);
        assert_eq!(summary["old_confirmation_actual_consumed"], Value::Null);
        assert_eq!(summary["actual_all_history_cumulative"], Value::Null);
    }

    fn rebind_manifest_context(manifest: &mut Value) -> String {
        let mut unsigned = manifest.clone();
        unsigned.as_object_mut().unwrap().remove("context");
        let context = digest(&serde_json::to_vec(&unsigned).unwrap());
        manifest["context"] = json!(context);
        context
    }

    #[test]
    fn runner_cli_has_only_fixed_nonconflicting_modes() {
        assert_eq!(
            parse_options(&argv(&["--preflight-only", "--trace-stderr"]))
                .unwrap()
                .mode,
            Mode::Preflight
        );
        assert_eq!(
            parse_options(&argv(&["--stats"])).unwrap().mode,
            Mode::Stats
        );
        assert_eq!(
            parse_options(&argv(&["--verify-recorded"])).unwrap().mode,
            Mode::VerifyRecorded
        );
        let prepared_hash = "b".repeat(64);
        let audit_args = [
            "--audit-saved-input-only",
            "--prepared-sha256",
            prepared_hash.as_str(),
            "--trace-stderr",
        ];
        assert_eq!(
            parse_options(&argv(&audit_args)).unwrap().mode,
            Mode::AuditSavedInputOnly
        );
        assert!(parse_options(&argv(&["--audit-saved-input-only", "--trace-stderr"])).is_err());
        assert!(parse_options(&argv(&[
            "--audit-saved-input-only",
            "--prepared-sha256",
            prepared_hash.as_str(),
            "--trace-stderr",
            "--audit-saved-input-only"
        ]))
        .is_err());
        assert!(parse_options(&argv(&[
            "--audit-saved-input-only",
            "--prepared-sha256",
            prepared_hash.as_str(),
            "--trace-stderr",
            "--stats"
        ]))
        .is_err());
        assert!(parse_options(&argv(&["--stats", "--verify-recorded"])).is_err());
        assert!(parse_options(&argv(&[
            "--preflight-only",
            "--prepared-sha256",
            &"b".repeat(64),
            "--trace-stderr"
        ]))
        .is_err());
        assert!(parse_options(&argv(&["--trace-stderr"])).is_err());
        assert!(parse_options(&argv(&[
            "--prepared-sha256",
            &"b".repeat(64),
            "--trace-stderr"
        ]))
        .is_ok());
    }

    #[test]
    fn strict_json_rejects_duplicate_keys_recursively() {
        assert!(strict_value(br#"{"x":1,"x":2}"#).is_err());
        assert!(strict_value(br#"{"a":[{"b":1,"b":2}]}"#).is_err());
    }

    fn temporary_root() -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join("target/curry-option-validation-tests/tmp")
            .join(format!("runner-e2e-{nonce}"))
            .join("research")
    }

    fn write_json(path: &Path, value: &Value) -> Vec<u8> {
        let raw = serde_json::to_vec_pretty(value).unwrap();
        fs::write(path, &raw).unwrap();
        raw
    }

    fn synthetic_request(worker: PathBuf) -> RunDuelRequest {
        let main = [
            58_074_572, 69_247_929, 69_247_929, 2_964_201, 2_964_201, 2_964_201, 2_971_090,
            2_971_090, 2_971_090, 3_797_883, 3_797_883, 3_797_883, 4_035_199, 4_035_199, 4_035_199,
            4_179_849, 4_179_849, 4_179_849, 4_392_470, 4_392_470, 4_392_470, 6_368_038, 6_368_038,
            6_368_038, 6_631_034, 6_631_034, 6_631_034, 6_740_720, 6_740_720, 6_740_720, 7_562_372,
            7_562_372, 7_562_372, 8_353_769, 8_353_769, 8_353_769, 9_540_040, 9_540_040, 9_540_040,
            10_538_007,
        ]
        .map(CardId)
        .to_vec();
        RunDuelRequest {
            protocol_version: 2,
            engine: ProcessEngineConfig {
                worker_path: worker,
                timeout_ms: 30_000,
                ..Default::default()
            },
            deck: Deck {
                main,
                extra: vec![CardId(84_013_237), CardId(71_594_310), CardId(77_637_979)],
                side: vec![],
            },
            opening_hand: vec![
                CardId(58_074_572),
                CardId(2_964_201),
                CardId(2_964_201),
                CardId(2_964_201),
                CardId(2_971_090),
            ],
            seed: 1,
            decisions: vec![],
            versions: RuntimeVersions {
                rules: "ocg-mr5".into(),
                catalog: String::new(),
                banlist: String::new(),
                engine_sha256: "a".repeat(64),
                cdb_sha256: "b".repeat(64),
                scripts_sha256: "c".repeat(64),
                core_commit: CORE_COMMIT.into(),
                initializer: INITIALIZER_VERSION.into(),
            },
            probe_only: false,
            scenario: None,
            interruption: None,
            first_turn: None,
            research_capture: None,
        }
    }

    fn synthetic_identity() -> Value {
        json!({
            "schema_version":1,
            "kind":"engine_identity",
            "identity":"e".repeat(64),
            "consistent":true,
            "roles":{
                "worker":{"sha256":"d".repeat(64)},
                "dll":{"sha256":"a".repeat(64)},
                "cdb":{"sha256":"b".repeat(64)},
                "script_manifest":{"sha256":"c".repeat(64)}
            }
        })
    }

    fn synthetic_input_hashes(spec: RunnerSpec) -> serde_json::Map<String, Value> {
        let mut hashes = serde_json::Map::new();
        for role in [
            "preparation",
            "preparation_report",
            "preparation_acceptance",
            "candidate_case",
            "base_request",
            "operations_source",
            "adapter_codec",
            "runner",
            "worker",
            "cli",
            "build_record",
            "identity",
            "window_start",
            "source_archive",
            "source_file_list",
            "ordinary_config",
            "tournament_config",
            "banlist",
            "core_source",
        ] {
            hashes.insert(role.to_owned(), Value::String("d".repeat(64)));
        }
        match spec.batch_kind {
            BATCH_KIND | CONFIRMATION_BATCH_KIND => {
                hashes.insert(
                    "baseline_delivery".to_owned(),
                    Value::String("d".repeat(64)),
                );
                if spec.batch_kind == CONFIRMATION_BATCH_KIND {
                    hashes.insert("baseline_audit".to_owned(), Value::String("d".repeat(64)));
                }
            }
            VERIFICATION_BATCH_KIND => {
                hashes.insert(
                    "baseline_acceptance".to_owned(),
                    Value::String("d".repeat(64)),
                );
                hashes.insert(
                    "consumption_reservation".to_owned(),
                    Value::String("d".repeat(64)),
                );
            }
            REVALIDATION_BATCH_KIND => {
                hashes.insert(
                    "baseline_delivery".to_owned(),
                    Value::String("d".repeat(64)),
                );
                hashes.insert(
                    "baseline_recovery".to_owned(),
                    Value::String("d".repeat(64)),
                );
                hashes.insert(
                    "consumption_reservation".to_owned(),
                    Value::String("d".repeat(64)),
                );
            }
            _ => unreachable!("RunnerSpec is private and has only fixed batch kinds"),
        }
        for (role, expected) in [
            ("preparation", PREPARATION_SHA256),
            ("preparation_report", PREPARATION_REPORT_SHA256),
            ("preparation_acceptance", PREPARATION_ACCEPTANCE_SHA256),
            ("candidate_case", CANDIDATE_CASE_SHA256),
            ("base_request", BASE_REQUEST_SHA256),
            ("operations_source", OPERATIONS_SOURCE_SHA256),
            ("core_source", OPERATIONS_SOURCE_SHA256),
            ("adapter_codec", ADAPTER_CODEC_SHA256),
        ] {
            hashes.insert(role.to_owned(), Value::String(expected.to_owned()));
        }
        match spec.batch_kind {
            BATCH_KIND | CONFIRMATION_BATCH_KIND => {
                hashes.insert(
                    "baseline_delivery".to_owned(),
                    Value::String(spec.baseline_delivery_sha256.to_owned()),
                );
            }
            VERIFICATION_BATCH_KIND => {
                hashes.insert(
                    "baseline_acceptance".to_owned(),
                    Value::String(VERIFICATION_BASELINE_ACCEPTANCE_SHA256.to_owned()),
                );
                hashes.insert(
                    "consumption_reservation".to_owned(),
                    Value::String(VERIFICATION_RESERVATION_SHA256.to_owned()),
                );
            }
            REVALIDATION_BATCH_KIND => {
                hashes.insert(
                    "baseline_delivery".to_owned(),
                    Value::String(spec.baseline_delivery_sha256.to_owned()),
                );
                hashes.insert(
                    "baseline_recovery".to_owned(),
                    Value::String(
                        spec.baseline_recovery_sha256
                            .expect("fixed revalidation spec has recovery source")
                            .to_owned(),
                    ),
                );
                hashes.insert(
                    "consumption_reservation".to_owned(),
                    Value::String(
                        spec.reservation_sha256
                            .expect("fixed revalidation spec has reservation")
                            .to_owned(),
                    ),
                );
            }
            _ => unreachable!("RunnerSpec is private and has only fixed batch kinds"),
        }
        if let Some(expected) = spec.baseline_audit_sha256 {
            hashes.insert(
                "baseline_audit".to_owned(),
                Value::String(expected.to_owned()),
            );
        }
        hashes
    }

    struct RunnerFixture {
        root: PathBuf,
        started: u64,
        context: String,
        request: RunDuelRequest,
        identity: Value,
        ledger: PathBuf,
        output: PathBuf,
        input_path: PathBuf,
        input_hash: String,
    }

    fn runner_fixture() -> RunnerFixture {
        runner_fixture_for(BatchKind::ValidationV1)
    }

    fn runner_fixture_for(batch_kind: BatchKind) -> RunnerFixture {
        let root = temporary_root();
        fs::create_dir_all(&root).unwrap();
        let spec = batch_kind.spec();
        let started = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs()
            - 5;
        let worker = root
            .parent()
            .unwrap()
            .join("native-artifacts/ygo-engine-worker.exe");
        let request = synthetic_request(worker);
        let identity = synthetic_identity();
        let ledger = root.join("calls.jsonl");
        let output = root.join("stage-1.json");
        let hashes = synthetic_input_hashes(spec);
        let request_value = serde_json::to_value(&request).unwrap();
        let mut manifest = json!({
            "schema_version":1,
            "kind":spec.manifest_kind,
            "scope":spec.scope,
            "started_at":started,
            "limit":spec.limit,
            "planned_calls":spec.planned_calls,
            "wall_seconds":spec.wall_seconds,
            "batch_kind":spec.batch_kind,
            "historical_source_transition":historical_source_transition(),
            "assets":{"ordinary":identity},
            "input_sha256":Value::Object(hashes),
            "request":request_value,
            "stage1_request_sha256":digest(&serde_json::to_vec(&request_value).unwrap())
        });
        match batch_kind {
            BatchKind::ValidationV1 => {
                manifest["old_consumed"] = json!(spec.old_consumed);
                manifest["baseline_acceptance_sha256"] = json!(BASELINE_ACCEPTANCE_SHA256);
                manifest["baseline_delivery_sha256"] = json!(spec.baseline_delivery_sha256);
            }
            BatchKind::ConfirmationV1 => {
                manifest["old_consumed"] = json!(spec.old_consumed);
                manifest["baseline_delivery_sha256"] = json!(spec.baseline_delivery_sha256);
                manifest["baseline_audit_sha256"] = json!(CONFIRMATION_BASELINE_AUDIT_SHA256);
            }
            BatchKind::VerificationV1 => {
                manifest["baseline_acceptance_sha256"] =
                    json!(VERIFICATION_BASELINE_ACCEPTANCE_SHA256);
                manifest["consumption_reservation_sha256"] = json!(VERIFICATION_RESERVATION_SHA256);
                manifest["certified_historical_consumed"] = json!(32);
                manifest["policy_reserved"] = json!(7);
                manifest["planning_base"] = json!(39);
                manifest["reservation_id"] = json!(VERIFICATION_RESERVATION_ID);
                manifest["reservation_policy_id"] = json!(VERIFICATION_RESERVATION_POLICY);
            }
            BatchKind::RevalidationV1 => {
                manifest["baseline_delivery_sha256"] = json!(REVALIDATION_BASELINE_DELIVERY_SHA256);
                manifest["baseline_recovery_sha256"] = json!(REVALIDATION_BASELINE_RECOVERY_SHA256);
                manifest["consumption_reservation_sha256"] = json!(VERIFICATION_RESERVATION_SHA256);
                manifest["certified_historical_consumed"] = json!(33);
                manifest["policy_reserved"] = json!(7);
                manifest["planning_base"] = json!(40);
                manifest["reservation_id"] = json!(VERIFICATION_RESERVATION_ID);
                manifest["reservation_policy_id"] = json!(VERIFICATION_RESERVATION_POLICY);
            }
        }
        let context = digest(&serde_json::to_vec(&manifest).unwrap());
        manifest["context"] = json!(context);
        write_json(&root.join("manifest.json"), &manifest);
        let input_path = root.join("stage-1-input.json");
        let input_value = json!({
            "context":context,
            "ledger":ledger,
            "output":output,
            "stage":1,
            "request":request,
            "expected_identity":identity,
            "started_at":started,
            "batch_kind":spec.batch_kind
        });
        let input_raw = write_json(&input_path, &input_value);
        let input_hash = digest(&input_raw);
        write_json(
            &root.join("stage-1-request.json"),
            &serde_json::to_value(&request).unwrap(),
        );
        write_json(
            &root.join("stage-1-input-seal.json"),
            &json!({
                "schema_version":1,
                "kind":spec.seal_kind,
                "context":context,
                "stage":1,
                "input_sha256":input_hash
            }),
        );
        RunnerFixture {
            root,
            started,
            context,
            request,
            identity,
            ledger,
            output,
            input_path,
            input_hash,
        }
    }

    fn save_prepared_for_fixture(fixture: &RunnerFixture) -> String {
        let manifest_raw = fs::read(fixture.root.join("manifest.json")).unwrap();
        let input_raw = fs::read(&fixture.input_path).unwrap();
        let (_, input_value) = read_strict(&fixture.input_path).unwrap();
        let input: Input = serde_json::from_value(input_value.clone()).unwrap();
        let spec = input.batch_kind.spec();
        let request_sha256 = digest(&serde_json::to_vec(&input_value["request"]).unwrap());
        let prepared = json!({
            "schema_version":1,
            "kind":spec.prepared_kind,
            "prepared":true,
            "execution_ready":true,
            "native_calls":0,
            "planned_calls":spec.planned_calls,
            "context":fixture.context,
            "manifest_sha256":digest(&manifest_raw),
            "stage1_input_sha256":digest(&input_raw),
            "stage1_request_sha256":request_sha256,
            "preflight_diagnostic_sha256":"e".repeat(64),
            "proof_ready":false,
            "complete_action_coverage":false,
            "global_optimality":false,
            "native_probability_verified":false
        });
        digest(&write_json(&fixture.root.join("prepared.json"), &prepared))
    }

    fn valid_stage1_result(request: &RunDuelRequest) -> DuelResult {
        let mut raw = vec![11, 0];
        for command in 0..6 {
            if command == 5 {
                raw.extend(1u32.to_le_bytes());
                raw.extend(58_074_572u32.to_le_bytes());
                raw.extend([0, 2]);
                raw.extend(0u32.to_le_bytes());
                raw.extend(0u64.to_le_bytes());
                raw.push(0);
            } else {
                raw.extend(0u32.to_le_bytes());
            }
        }
        raw.extend([0, 1, 0]);
        let frame = decode_frame(1, &raw).unwrap();
        let prompt = parse_prompt(1, &raw).unwrap().unwrap();
        let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
        result.status = DuelStatus::DecisionRequired;
        result.error = None;
        result.versions = request.versions.clone();
        result.events = vec![frame];
        result.prompt = Some(prompt);
        result
    }

    struct SyntheticAdapter {
        calls: Arc<AtomicUsize>,
    }

    fn prompt_frame(sequence: u64, raw: Vec<u8>) -> (CoreEventFrame, Prompt) {
        let frame = decode_frame(sequence, &raw).unwrap();
        let prompt = parse_prompt(sequence, &raw).unwrap().unwrap();
        (frame, prompt)
    }

    fn synthetic_result_for(request: &RunDuelRequest) -> DuelResult {
        assert!(request.decisions.len() <= 3);
        let (idle_frame, idle_prompt) = {
            let base = valid_stage1_result(request);
            (base.events[0].clone(), base.prompt.unwrap())
        };
        let (place_frame, place_prompt) = prompt_frame(2, vec![18, 0, 1, 0xff, 0xe0, 0xff, 0xff]);
        let mut option_raw = vec![14, 0, 2];
        option_raw.extend(60_895_602_409_472u64.to_le_bytes());
        option_raw.extend(60_895_602_409_473u64.to_le_bytes());
        let (option_frame, option_prompt) = prompt_frame(3, option_raw);
        let (pending_frame, pending_prompt) =
            match request.decisions.last().map(|item| &item.choice) {
                Some(Choice::Option { index: 0 | 1 }) => prompt_frame(5, {
                    let mut raw = vec![11, 0];
                    raw.extend([0; 24]);
                    raw.extend([0, 1, 0]);
                    raw
                }),
                Some(Choice::Place { .. }) => (option_frame.clone(), option_prompt.clone()),
                Some(Choice::Command { .. }) => (place_frame.clone(), place_prompt.clone()),
                None => (idle_frame.clone(), idle_prompt.clone()),
                _ => unreachable!("only the fixed command, place, and option route is supported"),
            };

        let mut events = vec![idle_frame];
        if !request.decisions.is_empty() {
            events.push(place_frame);
        }
        if request.decisions.len() >= 2 {
            events.push(option_frame.clone());
        }
        let option_index = request
            .decisions
            .iter()
            .find_map(|decision| match decision.choice {
                Choice::Option { index } => Some(index as u8),
                _ => None,
            });
        if pending_prompt.opcode == 11 && option_index.is_some() {
            let player = option_index.unwrap();
            let mut recover_raw = vec![92, player];
            recover_raw.extend(200u32.to_le_bytes());
            events.push(decode_frame(4, &recover_raw).unwrap());
        }
        if events.last().map(|event| event.sequence) != Some(pending_frame.sequence) {
            events.push(pending_frame.clone());
        }

        let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
        result.status = DuelStatus::DecisionRequired;
        result.error = None;
        result.versions = request.versions.clone();
        result.resolved_decisions = request.decisions.clone();
        for decision in &request.decisions {
            let action = events
                .iter()
                .filter_map(|frame| parse_prompt(frame.sequence, &frame.raw).unwrap())
                .find(|prompt| prompt.id == decision.prompt_id)
                .and_then(|prompt| {
                    prompt
                        .actions
                        .into_iter()
                        .find(|action| action.choice == decision.choice)
                })
                .expect("synthetic requested action exists in its raw prompt");
            result.steps.push(action);
        }
        result.prompt = Some(pending_prompt);
        result.events = events;
        if let Some(option) = option_index {
            result.checkpoint.lp = if option == 0 {
                [8_200, 8_000]
            } else {
                [8_000, 8_200]
            };
        }
        result
    }

    impl EngineAdapter for SyntheticAdapter {
        fn doctor(&self) -> DoctorReport {
            panic!("runner must not call doctor")
        }

        fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            Ok(synthetic_result_for(request))
        }
    }

    struct FailingSyntheticAdapter;

    impl EngineAdapter for FailingSyntheticAdapter {
        fn doctor(&self) -> DoctorReport {
            panic!("runner must not call doctor")
        }

        fn run(&self, _request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            Err(WorkerError::new(
                "synthetic_failure",
                "test",
                "synthetic worker failure",
            ))
        }
    }

    struct SyntheticServices {
        now: u64,
        identity: Value,
        scans: usize,
        calls: Arc<AtomicUsize>,
    }

    impl RunnerServices for SyntheticServices {
        fn now(&mut self) -> Result<u64, Box<dyn std::error::Error>> {
            Ok(self.now)
        }

        fn scan_identity(&mut self, _input: &Input) -> Result<Value, Box<dyn std::error::Error>> {
            self.scans += 1;
            self.now += 61;
            Ok(self.identity.clone())
        }

        fn adapter(&mut self, input: &Input) -> Box<dyn EngineAdapter> {
            assert_eq!(input.request.engine.timeout_ms, 30_000);
            Box::new(SyntheticAdapter {
                calls: self.calls.clone(),
            })
        }
    }

    struct ParentLedgerMutationServices {
        inner: SyntheticServices,
    }

    #[derive(serde::Serialize)]
    #[serde(tag = "kind", rename_all = "snake_case")]
    enum TestJournalEntry<'a> {
        Checkpoint {
            name: &'a str,
            blob: &'a str,
            consumed: usize,
            charged_sequence: &'a str,
        },
    }

    fn checkpoint_record_hash(
        sequence: usize,
        previous: &str,
        name: &str,
        blob: &str,
        consumed: usize,
        charged_sequence: &str,
    ) -> String {
        let entry = TestJournalEntry::Checkpoint {
            name,
            blob,
            consumed,
            charged_sequence,
        };
        digest(&serde_json::to_vec(&(sequence, previous, entry)).unwrap())
    }

    impl RunnerServices for ParentLedgerMutationServices {
        fn now(&mut self) -> Result<u64, Box<dyn std::error::Error>> {
            self.inner.now()
        }

        fn scan_identity(&mut self, input: &Input) -> Result<Value, Box<dyn std::error::Error>> {
            self.inner.scan_identity(input)
        }

        fn adapter(&mut self, input: &Input) -> Box<dyn EngineAdapter> {
            self.inner.adapter(input)
        }

        fn after_readonly_ledger_check(
            &mut self,
            input: &Input,
        ) -> Result<(), Box<dyn std::error::Error>> {
            let contents = fs::read_to_string(&input.ledger)?;
            let mut records = contents
                .lines()
                .map(serde_json::from_str::<Value>)
                .collect::<Result<Vec<_>, _>>()?;
            let last = records
                .last_mut()
                .ok_or("synthetic parent ledger is empty")?;
            if last["entry"]["kind"] != "checkpoint"
                || !last["entry"]["name"]
                    .as_str()
                    .is_some_and(|name| name.ends_with("/evidence/1"))
            {
                return Err("synthetic parent evidence is not the final record".into());
            }
            let sequence = last["sequence"].as_u64().ok_or("record sequence missing")? as usize;
            let previous = last["previous"]
                .as_str()
                .ok_or("record predecessor missing")?
                .to_owned();
            let name = last["entry"]["name"]
                .as_str()
                .ok_or("checkpoint name missing")?
                .to_owned();
            let old_blob = last["entry"]["blob"]
                .as_str()
                .ok_or("checkpoint blob missing")?
                .to_owned();
            let consumed = last["entry"]["consumed"]
                .as_u64()
                .ok_or("checkpoint consumption missing")? as usize;
            let charged_sequence = last["entry"]["charged_sequence"]
                .as_str()
                .ok_or("checkpoint charged sequence missing")?
                .to_owned();
            let original_hash = checkpoint_record_hash(
                sequence,
                &previous,
                &name,
                &old_blob,
                consumed,
                &charged_sequence,
            );
            if last["hash"].as_str() != Some(original_hash.as_str()) {
                return Err("synthetic checkpoint hash encoding changed".into());
            }

            let blob_path = input
                .ledger
                .parent()
                .ok_or("ledger parent directory missing")?
                .join("calls.jsonl.blobs")
                .join("checkpoints")
                .join(format!("{old_blob}.json"));
            let mut checkpoint: Value = serde_json::from_slice(&fs::read(&blob_path)?)?;
            checkpoint["search"]["receipt"]["successful"] = json!(false);
            let checkpoint_bytes = serde_json::to_vec(&checkpoint)?;
            let new_blob = digest(&checkpoint_bytes);
            fs::write(
                blob_path.with_file_name(format!("{new_blob}.json")),
                checkpoint_bytes,
            )?;
            last["entry"]["blob"] = json!(new_blob);
            let updated_hash = checkpoint_record_hash(
                sequence,
                &previous,
                &name,
                &new_blob,
                consumed,
                &charged_sequence,
            );
            last["hash"] = json!(updated_hash);
            let mut changed = Vec::new();
            for record in records {
                serde_json::to_writer(&mut changed, &record)?;
                changed.push(b'\n');
            }
            fs::write(&input.ledger, changed)?;
            Ok(())
        }
    }

    #[test]
    fn production_normal_dispatch_preflights_scans_charges_and_saves_one_receipt() {
        let root = temporary_root();
        fs::create_dir_all(&root).unwrap();
        let started = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs()
            - 5;
        let worker = root
            .parent()
            .unwrap()
            .join("native-artifacts/ygo-engine-worker.exe");
        let request = synthetic_request(worker);
        let identity = synthetic_identity();
        let ledger = root.join("calls.jsonl");
        let output = root.join("stage-1.json");
        let hashes = synthetic_input_hashes(BatchKind::ValidationV1.spec());
        let request_value = serde_json::to_value(&request).unwrap();
        let mut manifest = json!({
            "schema_version":1,
            "kind":MANIFEST_KIND,
            "scope":CURRY_OPTION_SCOPE,
            "started_at":started,
            "limit":7,
            "planned_calls":7,
            "wall_seconds":7200,
            "old_consumed":32,
            "batch_kind":BATCH_KIND,
            "baseline_acceptance_sha256":BASELINE_ACCEPTANCE_SHA256,
            "baseline_delivery_sha256":BASELINE_DELIVERY_SHA256,
            "historical_source_transition":historical_source_transition(),
            "assets":{"ordinary":identity},
            "input_sha256":Value::Object(hashes),
            "request":request_value,
            "stage1_request_sha256":digest(&serde_json::to_vec(&request_value).unwrap())
        });
        let context_hash = digest(&serde_json::to_vec(&manifest).unwrap());
        manifest["context"] = json!(context_hash);
        let manifest_raw = write_json(&root.join("manifest.json"), &manifest);
        let context = context_hash;
        let input_value = json!({
            "context":context,
            "ledger":ledger,
            "output":output,
            "stage":1,
            "request":request,
            "expected_identity":identity,
            "started_at":started,
            "batch_kind":BATCH_KIND
        });
        let input_path = root.join("stage-1-input.json");
        let input_raw = write_json(&input_path, &input_value);
        let input_hash = digest(&input_raw);
        write_json(
            &root.join("stage-1-request.json"),
            &serde_json::to_value(&request).unwrap(),
        );
        write_json(
            &root.join("stage-1-input-seal.json"),
            &json!({
                "schema_version":1,
                "kind":SEAL_KIND,
                "context":context,
                "stage":1,
                "input_sha256":input_hash
            }),
        );

        let mut services = SyntheticServices {
            now: started + 10,
            identity,
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };
        let mut stdout = Vec::new();
        let preflight_args = vec![
            "curry-option-validation".into(),
            input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            input_hash.clone(),
            "--preflight-only".into(),
            "--trace-stderr".into(),
        ];
        execute_with_services(&preflight_args, &root, &mut services, &mut stdout).unwrap();
        let preflight: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(preflight["preflight_passed"], true);
        assert_eq!(preflight["native_calls"], 0);
        assert_eq!(preflight["identity_sha256"], services.identity["identity"]);
        assert_eq!(services.scans, 1);
        assert!(!ledger.exists());
        assert!(!output.exists());

        let stage1_raw = fs::read(&input_path).unwrap();
        let stage1_value: Value = serde_json::from_slice(&stage1_raw).unwrap();
        let prepared = json!({
            "schema_version":1,
            "kind":PREPARED_KIND,
            "prepared":true,
            "execution_ready":true,
            "native_calls":0,
            "planned_calls":7,
            "context":context,
            "manifest_sha256":digest(&manifest_raw),
            "stage1_input_sha256":digest(&stage1_raw),
            "stage1_request_sha256":digest(&serde_json::to_vec(&stage1_value["request"]).unwrap()),
            "preflight_diagnostic_sha256":"e".repeat(64),
            "proof_ready":false,
            "complete_action_coverage":false,
            "global_optimality":false,
            "native_probability_verified":false
        });
        let prepared_raw = write_json(&root.join("prepared.json"), &prepared);
        let prepared_hash = digest(&prepared_raw);

        services.scans = 0;
        services.calls = Arc::new(AtomicUsize::new(0));
        stdout.clear();
        let normal_args = vec![
            "curry-option-validation".into(),
            input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            input_hash,
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        execute_with_services(&normal_args, &root, &mut services, &mut stdout).unwrap();
        let summary: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(summary["successful"], true);
        assert_eq!(summary["native_calls"], 1);
        assert_eq!(summary["ledger"]["consumed"], 1);
        assert_eq!(services.scans, 3);
        assert!(services.now >= started + 183);
        assert_eq!(services.calls.load(Ordering::SeqCst), 1);
        let (_, receipt) = read_strict(&output).unwrap();
        assert_eq!(receipt["successful"], true);
        assert_eq!(receipt["stage"], 1);

        stdout.clear();
        let verify_args = vec![
            "curry-option-validation".into(),
            input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            digest(&fs::read(&input_path).unwrap()),
            "--verify-recorded".into(),
        ];
        execute_with_services(&verify_args, &root, &mut services, &mut stdout).unwrap();
        let verified: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(verified["verified_recorded"], true);
        assert_eq!(verified["native_calls"], 0);
        assert_eq!(verified["successful"], true);
    }

    fn write_stage_input(
        fixture: &RunnerFixture,
        batch_kind: BatchKind,
        stage: u8,
        request: RunDuelRequest,
    ) -> (PathBuf, String, PathBuf) {
        let spec = batch_kind.spec();
        let input_path = fixture.root.join(format!("stage-{stage}-input.json"));
        let output_path = fixture.root.join(format!("stage-{stage}.json"));
        let input_raw = write_json(
            &input_path,
            &json!({
                "context":fixture.context,
                "ledger":fixture.ledger,
                "output":output_path,
                "stage":stage,
                "request":request,
                "expected_identity":fixture.identity,
                "started_at":fixture.started,
                "batch_kind":spec.batch_kind
            }),
        );
        let input_hash = digest(&input_raw);
        write_json(
            &fixture.root.join(format!("stage-{stage}-request.json")),
            &serde_json::to_value(request).unwrap(),
        );
        write_json(
            &fixture.root.join(format!("stage-{stage}-input-seal.json")),
            &json!({
                "schema_version":1,
                "kind":spec.seal_kind,
                "context":fixture.context,
                "stage":stage,
                "input_sha256":input_hash
            }),
        );
        (input_path, input_hash, output_path)
    }

    #[test]
    fn production_normal_stage_two_releases_parent_read_view_before_exclusive_open() {
        for batch_kind in [BatchKind::VerificationV1, BatchKind::RevalidationV1] {
            production_normal_stage_two_releases_parent_read_view_for(batch_kind);
        }
    }

    fn production_normal_stage_two_releases_parent_read_view_for(batch_kind: BatchKind) {
        let spec = batch_kind.spec();
        let fixture = runner_fixture_for(batch_kind);
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let calls = Arc::new(AtomicUsize::new(0));
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity: fixture.identity.clone(),
            scans: 0,
            calls: calls.clone(),
        };

        let mut stdout = Vec::new();
        let stage1_args = vec![
            spec.batch_kind.into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash.clone(),
            "--prepared-sha256".into(),
            prepared_hash.clone(),
            "--trace-stderr".into(),
        ];
        execute_with_services(&stage1_args, &fixture.root, &mut services, &mut stdout).unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(services.scans, 3);
        assert_eq!(
            serde_json::from_slice::<Value>(&stdout).unwrap()["successful"],
            true
        );

        let parent: Value = serde_json::from_slice(&fs::read(&fixture.output).unwrap()).unwrap();
        let stage2_request = derive_curry_option_request_from_receipt(2, &parent).unwrap();
        let (stage2_input, stage2_hash, stage2_output) =
            write_stage_input(&fixture, batch_kind, 2, stage2_request);

        if matches!(batch_kind, BatchKind::VerificationV1) {
            let ledger_before_audit = fs::read(&fixture.ledger).unwrap();
            services.scans = 0;
            stdout.clear();
            let audit_args = vec![
                spec.batch_kind.into(),
                stage2_input.to_string_lossy().into_owned(),
                "--input-sha".into(),
                stage2_hash.clone(),
                "--audit-saved-input-only".into(),
                "--prepared-sha256".into(),
                prepared_hash.clone(),
                "--trace-stderr".into(),
            ];
            execute_with_services(&audit_args, &fixture.root, &mut services, &mut stdout).unwrap();
            let audited: Value = serde_json::from_slice(&stdout).unwrap();
            assert_eq!(audited["saved_input_audit_passed"], true);
            assert_eq!(audited["native_calls"], 0);
            assert_eq!(audited["execution_ready"], false);
            assert_eq!(audited["parent_receipt_valid"], true);
            assert_eq!(audited["request_derivation_valid"], true);
            assert_eq!(audited["stage_receipt_absent"], true);
            assert_eq!(audited["ledger"]["consumed"], 1);
            assert_eq!(audited["ledger"]["completed"], 1);
            assert_eq!(audited["ledger"]["unknown"], 0);
            assert_eq!(services.scans, 1);
            assert_eq!(calls.load(Ordering::SeqCst), 1);
            assert!(!stage2_output.exists());
            assert_eq!(fs::read(&fixture.ledger).unwrap(), ledger_before_audit);
        }

        services.scans = 0;
        stdout.clear();
        let stage2_args = vec![
            spec.batch_kind.into(),
            stage2_input.to_string_lossy().into_owned(),
            "--input-sha".into(),
            stage2_hash,
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        execute_with_services(&stage2_args, &fixture.root, &mut services, &mut stdout).unwrap();

        let summary: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(summary["successful"], true);
        assert_eq!(summary["native_calls"], 1);
        assert_eq!(calls.load(Ordering::SeqCst), 2);
        assert_eq!(services.scans, 3);
        assert!(stage2_output.is_file());
        let ledger =
            CallJournal::inspect_existing(&fixture.ledger, spec.scope, &fixture.context, 7)
                .unwrap()
                .unwrap();
        assert_eq!(ledger.stats().unwrap().consumed, 2);
        assert_eq!(ledger.stats().unwrap().completed, 2);
        assert_eq!(ledger.stats().unwrap().unknown, 0);
    }

    #[test]
    fn exclusive_open_rejects_parent_ledger_changed_after_readonly_validation() {
        for batch_kind in [BatchKind::VerificationV1, BatchKind::RevalidationV1] {
            exclusive_open_rejects_parent_ledger_changed_after_readonly_validation_for(batch_kind);
        }
    }

    fn exclusive_open_rejects_parent_ledger_changed_after_readonly_validation_for(
        batch_kind: BatchKind,
    ) {
        let spec = batch_kind.spec();
        let fixture = runner_fixture_for(batch_kind);
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let calls = Arc::new(AtomicUsize::new(0));
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity: fixture.identity.clone(),
            scans: 0,
            calls: calls.clone(),
        };

        let stage1_args = vec![
            spec.batch_kind.into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash.clone(),
            "--prepared-sha256".into(),
            prepared_hash.clone(),
            "--trace-stderr".into(),
        ];
        let mut stdout = Vec::new();
        execute_with_services(&stage1_args, &fixture.root, &mut services, &mut stdout).unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 1);

        let parent: Value = serde_json::from_slice(&fs::read(&fixture.output).unwrap()).unwrap();
        let stage2_request = derive_curry_option_request_from_receipt(2, &parent).unwrap();
        let (stage2_input, stage2_hash, stage2_output) =
            write_stage_input(&fixture, batch_kind, 2, stage2_request);
        let ledger = fs::read(&fixture.ledger).unwrap();

        let mut mutating = ParentLedgerMutationServices {
            inner: SyntheticServices {
                now: fixture.started + 10,
                identity: fixture.identity.clone(),
                scans: 0,
                calls: calls.clone(),
            },
        };
        let stage2_args = vec![
            spec.batch_kind.into(),
            stage2_input.to_string_lossy().into_owned(),
            "--input-sha".into(),
            stage2_hash,
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        stdout.clear();
        let error = execute_with_services(&stage2_args, &fixture.root, &mut mutating, &mut stdout)
            .expect_err("exclusive open must reject the changed parent ledger");

        assert!(error.to_string().contains("receipt success"), "{error}");
        assert_eq!(calls.load(Ordering::SeqCst), 1, "no second adapter call");
        assert!(
            !stage2_output.exists(),
            "failed gate must not publish a receipt"
        );
        assert_ne!(fs::read(&fixture.ledger).unwrap(), ledger);
        let view = CallJournal::inspect_existing(&fixture.ledger, spec.scope, &fixture.context, 7)
            .expect("mutated parent evidence retains a valid ledger chain")
            .expect("existing parent ledger");
        assert_eq!(view.stats().unwrap().consumed, 1);
        assert_eq!(view.stats().unwrap().completed, 1);
        assert_eq!(view.stats().unwrap().unknown, 0);
    }

    #[test]
    fn saved_input_audit_rejects_bad_parent_and_existing_output_without_charge() {
        let fixture = runner_fixture_for(BatchKind::VerificationV1);
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let calls = Arc::new(AtomicUsize::new(0));
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity: fixture.identity.clone(),
            scans: 0,
            calls: calls.clone(),
        };
        let mut stdout = Vec::new();
        let stage1_args = vec![
            "curry-option-verification".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash.clone(),
            "--prepared-sha256".into(),
            prepared_hash.clone(),
            "--trace-stderr".into(),
        ];
        execute_with_services(&stage1_args, &fixture.root, &mut services, &mut stdout).unwrap();
        let parent_path = fixture.root.join("stage-1.json");
        let parent_before = fs::read(&parent_path).unwrap();
        let parent: Value = serde_json::from_slice(&parent_before).unwrap();
        let child = derive_curry_option_request_from_receipt(2, &parent).unwrap();
        let (stage2_input, stage2_hash, stage2_output) =
            write_stage_input(&fixture, BatchKind::VerificationV1, 2, child);
        let ledger_before = fs::read(&fixture.ledger).unwrap();
        let audit_args = vec![
            "curry-option-verification".into(),
            stage2_input.to_string_lossy().into_owned(),
            "--input-sha".into(),
            stage2_hash,
            "--audit-saved-input-only".into(),
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];

        let mut damaged_parent = parent;
        damaged_parent["successful"] = json!(false);
        write_json(&parent_path, &damaged_parent);
        services.scans = 0;
        stdout.clear();
        assert!(
            execute_with_services(&audit_args, &fixture.root, &mut services, &mut stdout).is_err()
        );
        assert_eq!(services.scans, 0);
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(fs::read(&fixture.ledger).unwrap(), ledger_before);
        assert!(!stage2_output.exists());

        fs::write(&parent_path, parent_before).unwrap();
        fs::write(&stage2_output, b"already published").unwrap();
        stdout.clear();
        assert!(
            execute_with_services(&audit_args, &fixture.root, &mut services, &mut stdout).is_err()
        );
        assert_eq!(services.scans, 0);
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(fs::read(&fixture.ledger).unwrap(), ledger_before);
        assert_eq!(fs::read(&stage2_output).unwrap(), b"already published");
    }

    #[test]
    fn production_normal_dispatch_completes_seven_stages_for_all_fixed_scopes() {
        for batch_kind in [
            BatchKind::ValidationV1,
            BatchKind::ConfirmationV1,
            BatchKind::VerificationV1,
            BatchKind::RevalidationV1,
        ] {
            let fixture = runner_fixture_for(batch_kind);
            let prepared_hash = save_prepared_for_fixture(&fixture);
            let calls = Arc::new(AtomicUsize::new(0));
            let mut services = SyntheticServices {
                now: fixture.started + 10,
                identity: fixture.identity.clone(),
                scans: 0,
                calls: calls.clone(),
            };
            let mut receipts: Vec<Value> = Vec::new();
            let mut requests = Vec::new();
            let mut final_summary = Value::Null;

            let preflight_args = vec![
                "curry-option-fixed-runner".into(),
                fixture.input_path.to_string_lossy().into_owned(),
                "--input-sha".into(),
                fixture.input_hash.clone(),
                "--preflight-only".into(),
                "--trace-stderr".into(),
            ];
            services.scans = 0;
            let mut preflight_stdout = Vec::new();
            execute_with_services(
                &preflight_args,
                &fixture.root,
                &mut services,
                &mut preflight_stdout,
            )
            .unwrap();
            let preflight: Value = serde_json::from_slice(&preflight_stdout).unwrap();
            assert_eq!(preflight["preflight_passed"], true, "{batch_kind:?}");
            assert_eq!(preflight["native_calls"], 0, "{batch_kind:?}");
            assert_eq!(services.scans, 1, "{batch_kind:?} preflight");
            assert_eq!(calls.load(Ordering::SeqCst), 0, "{batch_kind:?} preflight");
            assert!(!fixture.ledger.exists(), "{batch_kind:?} preflight");

            for stage in 1..=7 {
                let (input_path, input_hash, output_path, request) = if stage == 1 {
                    (
                        fixture.input_path.clone(),
                        fixture.input_hash.clone(),
                        fixture.output.clone(),
                        fixture.request.clone(),
                    )
                } else {
                    let parent_stage = curry_option_parent_stage(stage)
                        .unwrap()
                        .expect("all non-root stages have a fixed parent");
                    let parent = receipts[(parent_stage - 1) as usize].clone();
                    let request = derive_curry_option_request_from_receipt(stage, &parent)
                        .unwrap_or_else(|error| {
                            panic!(
                                "{batch_kind:?} stage {stage} derivation failed from stage {} result prompt {}: {error:?}",
                                parent["stage"],
                                parent["result"]["Ok"]["prompt"]
                            )
                        });
                    let (input_path, input_hash, output_path) =
                        write_stage_input(&fixture, batch_kind, stage, request.clone());
                    (input_path, input_hash, output_path, request)
                };
                let args = vec![
                    "curry-option-fixed-runner".into(),
                    input_path.to_string_lossy().into_owned(),
                    "--input-sha".into(),
                    input_hash,
                    "--prepared-sha256".into(),
                    prepared_hash.clone(),
                    "--trace-stderr".into(),
                ];
                services.scans = 0;
                let mut stdout = Vec::new();
                execute_with_services(&args, &fixture.root, &mut services, &mut stdout)
                    .unwrap_or_else(|error| {
                        panic!("{batch_kind:?} stage {stage} normal path failed: {error}")
                    });
                let summary: Value = serde_json::from_slice(&stdout).unwrap();
                assert_eq!(summary["successful"], true, "{batch_kind:?} stage {stage}");
                assert_eq!(summary["native_calls"], 1);
                final_summary = summary.clone();
                assert_eq!(services.scans, 3, "{batch_kind:?} stage {stage}");
                assert_eq!(calls.load(Ordering::SeqCst), stage as usize);
                assert!(output_path.is_file());
                let (_, receipt) = read_strict(&output_path).unwrap();
                assert_eq!(receipt["successful"], true);
                assert_eq!(receipt["stage"], stage);
                requests.push(request);
                receipts.push(receipt);
            }

            assert_eq!(calls.load(Ordering::SeqCst), 7);
            assert_eq!(
                serde_json::to_value(&requests[3]).unwrap(),
                serde_json::to_value(&requests[4]).unwrap(),
                "stage 5 replays stage 4"
            );
            assert_eq!(
                serde_json::to_value(&requests[5]).unwrap(),
                serde_json::to_value(&requests[6]).unwrap(),
                "stage 7 replays stage 6"
            );
            let view = CallJournal::inspect_existing(
                &fixture.ledger,
                batch_kind.spec().scope,
                &fixture.context,
                7,
            )
            .unwrap()
            .unwrap();
            let stats = view.stats().unwrap();
            assert_eq!(stats.consumed, 7, "{batch_kind:?}");
            assert_eq!(stats.completed, 7, "{batch_kind:?}");
            assert_eq!(stats.unknown, 0, "{batch_kind:?}");
            assert_eq!(stats.limit, 7, "{batch_kind:?}");
            if batch_kind == BatchKind::RevalidationV1 {
                for (index, receipt) in receipts.iter().enumerate() {
                    verify_curry_option_revalidation_recorded(
                        &view,
                        (index + 1) as u8,
                        &fixture.context,
                        fixture.started,
                        receipt,
                    )
                    .unwrap();
                }
                assert_eq!(final_summary["new_consumed"], 7);
                assert_eq!(final_summary["certified_historical_consumed"], 33);
                assert_eq!(final_summary["certified_consumed_including_new"], 40);
                assert_eq!(final_summary["policy_reserved"], 7);
                assert_eq!(final_summary["planning_base"], 40);
                assert_eq!(final_summary["planning_total"], 47);
                assert_eq!(
                    final_summary["old_confirmation_actual_consumed"],
                    Value::Null
                );
                assert_eq!(final_summary["actual_all_history_cumulative"], Value::Null);
            }
            drop(view);
        }
    }

    #[test]
    fn confirmation_runner_uses_its_fixed_scope_preflight_and_normal_contract() {
        let fixture = runner_fixture_for(BatchKind::ConfirmationV1);
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity: fixture.identity.clone(),
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };
        let mut stdout = Vec::new();
        let preflight_args = vec![
            "curry-option-confirmation".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash.clone(),
            "--preflight-only".into(),
            "--trace-stderr".into(),
        ];
        execute_with_services(&preflight_args, &fixture.root, &mut services, &mut stdout).unwrap();
        let preflight: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(preflight["preflight_passed"], true);
        assert_eq!(preflight["native_calls"], 0);
        assert_eq!(services.scans, 1);
        assert!(!fixture.ledger.exists());

        let prepared_hash = save_prepared_for_fixture(&fixture);
        services.scans = 0;
        services.calls = Arc::new(AtomicUsize::new(0));
        stdout.clear();
        let normal_args = vec![
            "curry-option-confirmation".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash.clone(),
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        execute_with_services(&normal_args, &fixture.root, &mut services, &mut stdout).unwrap();
        let summary: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(summary["successful"], true);
        assert_eq!(summary["native_calls"], 1);
        assert_eq!(summary["ledger"]["consumed"], 1);
        assert_eq!(services.scans, 3);
        assert_eq!(services.calls.load(Ordering::SeqCst), 1);
        let (_, receipt) = read_strict(&fixture.output).unwrap();
        assert_eq!(receipt["scope"], CURRY_OPTION_CONFIRMATION_SCOPE);
        assert_eq!(receipt["kind"], CONFIRMATION_STAGE_KIND);

        let ledger_before = fs::read(&fixture.ledger).unwrap();
        services.now = fixture.started + 7_201;
        services.scans = 0;
        stdout.clear();
        let verify_args = vec![
            "curry-option-confirmation".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash,
            "--verify-recorded".into(),
        ];
        execute_with_services(&verify_args, &fixture.root, &mut services, &mut stdout).unwrap();
        let verified: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(verified["verified_recorded"], true);
        assert_eq!(verified["successful"], true);
        assert_eq!(services.scans, 0);
        assert_eq!(services.calls.load(Ordering::SeqCst), 1);
        assert_eq!(fs::read(&fixture.ledger).unwrap(), ledger_before);
    }

    #[test]
    fn verification_runner_dispatches_to_reserved_scope_and_reports_separate_accounting() {
        let fixture = runner_fixture_for(BatchKind::VerificationV1);
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let calls = Arc::new(AtomicUsize::new(0));
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity: fixture.identity.clone(),
            scans: 0,
            calls: calls.clone(),
        };
        let mut stdout = Vec::new();
        let normal_args = vec![
            "curry-option-verification".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash.clone(),
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        execute_with_services(&normal_args, &fixture.root, &mut services, &mut stdout).unwrap();

        let summary: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(summary["successful"], true);
        assert_eq!(summary["native_calls"], 1);
        assert_eq!(summary["ledger"]["consumed"], 1);
        assert_eq!(summary["certified_historical_consumed"], 32);
        assert_eq!(summary["policy_reserved"], 7);
        assert_eq!(summary["planning_base"], 39);
        assert_eq!(summary["reservation_id"], VERIFICATION_RESERVATION_ID);
        assert_eq!(
            summary["reservation_policy_id"],
            VERIFICATION_RESERVATION_POLICY
        );
        assert_eq!(summary["new_consumed"], 1);
        assert_eq!(summary["certified_consumed_including_new"], 33);
        assert_eq!(summary["planning_total"], 40);
        assert_eq!(summary["old_confirmation_actual_consumed"], Value::Null);
        assert_eq!(summary["actual_all_history_cumulative"], Value::Null);
        assert_eq!(summary["unknown"], 0);
        assert_eq!(services.scans, 3);
        assert_eq!(calls.load(Ordering::SeqCst), 1);

        let (_, receipt) = read_strict(&fixture.output).unwrap();
        assert_eq!(receipt["scope"], CURRY_OPTION_VERIFICATION_SCOPE);
        assert_eq!(receipt["kind"], VERIFICATION_STAGE_KIND);
    }

    #[test]
    fn verify_recorded_accepts_failed_receipt_read_only_after_window_expiry() {
        let fixture = runner_fixture();
        let batch =
            CurryOptionBatch::open(&fixture.ledger, &fixture.context, fixture.started).unwrap();
        batch.save_assets_before(1, &fixture.identity).unwrap();
        let outcome = batch.run(FailingSyntheticAdapter, 1, &fixture.request);
        assert!(outcome.is_err());
        let receipt = batch
            .record_evidence(
                1,
                &fixture.request,
                &outcome,
                &fixture.identity,
                Some(&fixture.identity),
            )
            .unwrap();
        assert_eq!(receipt["successful"], false);
        write_json(&fixture.output, &receipt);
        drop(batch);

        let ledger_before = fs::read(&fixture.ledger).unwrap();
        let mut services = SyntheticServices {
            now: fixture.started + 7_201,
            identity: fixture.identity,
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };
        let args = vec![
            "curry-option-validation".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash,
            "--verify-recorded".into(),
        ];
        let mut stdout = Vec::new();
        // Structural verification succeeds; the caller must stop on successful=false.
        execute_with_services(&args, &fixture.root, &mut services, &mut stdout).unwrap();
        let summary: Value = serde_json::from_slice(&stdout).unwrap();
        assert_eq!(summary["verified_recorded"], true);
        assert_eq!(summary["successful"], false);
        assert_eq!(summary["native_calls"], 0);
        assert_eq!(services.scans, 0);
        assert_eq!(services.calls.load(Ordering::SeqCst), 0);
        assert_eq!(fs::read(fixture.ledger).unwrap(), ledger_before);
    }

    #[test]
    fn manifest_rejects_rebound_candidate_hash_even_with_consistent_context() {
        let fixture = runner_fixture();
        let (_, input_value) = read_strict(&fixture.input_path).unwrap();
        let mut input: Input = serde_json::from_value(input_value).unwrap();
        let manifest_path = fixture.root.join("manifest.json");
        let (_, mut manifest) = read_strict(&manifest_path).unwrap();
        manifest["input_sha256"]["candidate_case"] = json!("f".repeat(64));
        let mut unsigned = manifest.clone();
        unsigned.as_object_mut().unwrap().remove("context");
        let context = digest(&serde_json::to_vec(&unsigned).unwrap());
        manifest["context"] = json!(context);
        input.context = context;
        write_json(&manifest_path, &manifest);

        assert!(validate_manifest(&fixture.root, &input).is_err());
    }

    #[test]
    fn manifest_rejects_worker_hash_that_differs_from_frozen_worker_identity() {
        let fixture = runner_fixture();
        let (_, input_value) = read_strict(&fixture.input_path).unwrap();
        let mut input: Input = serde_json::from_value(input_value).unwrap();
        let manifest_path = fixture.root.join("manifest.json");
        let (_, mut manifest) = read_strict(&manifest_path).unwrap();
        manifest["input_sha256"]["worker"] = json!("e".repeat(64));
        let mut unsigned = manifest.clone();
        unsigned.as_object_mut().unwrap().remove("context");
        let context = digest(&serde_json::to_vec(&unsigned).unwrap());
        manifest["context"] = json!(context);
        input.context = context;
        write_json(&manifest_path, &manifest);

        assert!(validate_manifest(&fixture.root, &input).is_err());
    }

    #[test]
    fn normal_shared_preflight_rejects_dll_worker_confusion_before_adapter_or_ledger() {
        let fixture = runner_fixture();
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let mut identity = fixture.identity.clone();
        identity["roles"]["dll"] = identity["roles"]["worker"].clone();
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity,
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };
        let args = vec![
            "curry-option-validation".into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash,
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        let mut stdout = Vec::new();

        let error =
            execute_with_services(&args, &fixture.root, &mut services, &mut stdout).unwrap_err();
        assert!(error.to_string().contains("identity differs"), "{error}");
        assert_eq!(services.scans, 1);
        assert_eq!(services.calls.load(Ordering::SeqCst), 0);
        assert!(!fixture.ledger.exists());
        assert!(!fixture.output.exists());
    }

    #[test]
    fn asset_identity_rejects_a_missing_dll_role() {
        let fixture = runner_fixture();
        let (_, input_value) = read_strict(&fixture.input_path).unwrap();
        let input: Input = serde_json::from_value(input_value).unwrap();
        let mut identity = fixture.identity.clone();
        identity["roles"].as_object_mut().unwrap().remove("dll");
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity,
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };

        assert!(verify_asset_identity(&input, &mut services).is_err());
        assert_eq!(services.scans, 1);
        assert_eq!(services.calls.load(Ordering::SeqCst), 0);
    }

    #[test]
    fn later_stage_checks_asset_identity_before_parent_ledger_access() {
        let fixture = runner_fixture();
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let (_, mut input_value) = read_strict(&fixture.input_path).unwrap();
        let stage2_input_path = fixture.root.join("stage-2-input.json");
        let stage2_output_path = fixture.root.join("stage-2.json");
        let stage2_request_path = fixture.root.join("stage-2-request.json");
        let stage2_seal_path = fixture.root.join("stage-2-input-seal.json");
        input_value["stage"] = json!(2);
        input_value["output"] = json!(stage2_output_path);
        write_json(&stage2_request_path, &input_value["request"]);
        let input_raw = write_json(&stage2_input_path, &input_value);
        write_json(
            &stage2_seal_path,
            &json!({
                "schema_version":1,
                "kind":SEAL_KIND,
                "context":fixture.context,
                "stage":2,
                "input_sha256":digest(&input_raw)
            }),
        );
        let mut identity = fixture.identity.clone();
        identity["roles"]["dll"]["sha256"] = identity["roles"]["worker"]["sha256"].clone();
        let mut services = SyntheticServices {
            now: fixture.started + 10,
            identity,
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };
        let args = vec![
            "curry-option-validation".into(),
            stage2_input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            digest(&input_raw),
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        let mut stdout = Vec::new();

        let error =
            execute_with_services(&args, &fixture.root, &mut services, &mut stdout).unwrap_err();
        assert!(
            error.to_string().contains("asset identity differs"),
            "{error}"
        );
        assert_eq!(services.scans, 1);
        assert_eq!(services.calls.load(Ordering::SeqCst), 0);
        assert!(!fixture.ledger.exists());
        assert!(!stage2_output_path.exists());
    }

    #[test]
    fn normal_precharge_expiry_after_scans_never_calls_adapter() {
        for batch_kind in [BatchKind::ValidationV1, BatchKind::RevalidationV1] {
            normal_precharge_expiry_after_scans_never_calls_adapter_for(batch_kind);
        }
    }

    fn normal_precharge_expiry_after_scans_never_calls_adapter_for(batch_kind: BatchKind) {
        let spec = batch_kind.spec();
        let fixture = runner_fixture_for(batch_kind);
        let prepared_hash = save_prepared_for_fixture(&fixture);
        let mut services = SyntheticServices {
            now: fixture.started + 7_169,
            identity: fixture.identity.clone(),
            scans: 0,
            calls: Arc::new(AtomicUsize::new(0)),
        };
        let args = vec![
            spec.batch_kind.into(),
            fixture.input_path.to_string_lossy().into_owned(),
            "--input-sha".into(),
            fixture.input_hash,
            "--prepared-sha256".into(),
            prepared_hash,
            "--trace-stderr".into(),
        ];
        let mut stdout = Vec::new();

        let error =
            execute_with_services(&args, &fixture.root, &mut services, &mut stdout).unwrap_err();
        assert!(
            error.to_string().contains("less than thirty seconds"),
            "{error}"
        );
        assert_eq!(services.scans, 2);
        assert_eq!(services.calls.load(Ordering::SeqCst), 0);
        assert!(!fixture.output.exists());
    }
}
