"""Zero-call audit of the frozen Curry stage-2 ledger handoff input."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import time
import zipfile
from typing import Any, Callable

from ygo_data.identity import canonical, stable_source
from ygo_eval.prompt_probe_prepare import safe_path, strict_json


BASELINE_RELATIVE = Path(
    "data/runtime/p1-curry-option-verification-native-2026-10-25"
)
OUTPUT_RELATIVE = Path(
    "data/runtime/p1-curry-ledger-handoff-offline-2026-10-25"
)
V2_OUTPUT_RELATIVE = Path(
    "data/runtime/p1-curry-ledger-handoff-v2-offline-2026-10-25"
)
V3_OUTPUT_RELATIVE = Path(
    "data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25"
)
V4_OUTPUT_RELATIVE = Path(
    "data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26"
)
V5_OUTPUT_RELATIVE = Path(
    "data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26"
)
ACCEPTANCE_RELATIVE = Path("final-build/acceptance.json")
DELIVERY_RELATIVE = Path("final-build/delivery.json")
ACCEPTANCE_SHA256 = "d0283275972ce29fdb636ee2c5e005ab710b05c9125597cf6c34bdd67a56d9d3"
DELIVERY_SHA256 = "2326c1e19fb58b41635141a16ea4321ad94c3002afdf19484e7fb643250c2f55"
REPORT_RELATIVE = Path("audit-report.json")
RUNNER_RELATIVE = Path("native-artifacts/curry-option-validation.exe")
PREVIOUS_V1_RUNNER_RELATIVE = Path("native-artifacts/curry-option-verification.exe")
BUILD_RECORD_RELATIVE = Path("build-record.json")
SOURCE_ARCHIVE_RELATIVE = Path("source-native.zip")
SOURCE_FILE_LIST_RELATIVE = Path("source-native-file-list.json")
RUNNER_ROLE = "curry_ledger_handoff_audit_runner"
RUNNER_MODE = "audit_saved_input_only"
PREVIOUS_V1_REPORT_SHA256 = "4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e"
PREVIOUS_V1_BUILD_RECORD_SHA256 = "6f3526a656d28e19f8851f37ffda8d3bcd389c7cfb5a961f2d7ab15a702d9b73"
PREVIOUS_V1_RUNNER_RELATIVE_CORRECT = Path("native-artifacts/curry-option-validation.exe")
PREVIOUS_V1_RUNNER_SHA256 = "cd5f294e99aa5c44935e2ef414865a6f46fa2c8bbb5230f018d31ad606365b8d"
PREVIOUS_V1_ARCHIVE_SHA256 = "20ce6d7fde0a18f602c161c4a6b193795c1490eeedc138e2014e8bfa2c1fc20b"
PREVIOUS_V1_LIST_SHA256 = "713b24d41dbff9c1bf7a23f8529b0c348c28132d0645899dd328942dd215791d"
PREVIOUS_V1_SOURCE_IDENTITY = "9288335ca2fab0234489377ea1351bc651fca5b40fb6b03a25a472700b312ecc"
PREVIOUS_V2_REPORT_SHA256 = "9d74b97e6553ba141537bae414e0f60740220de48e0b031fdb6bff0bad0928c1"
PREVIOUS_V2_BUILD_RECORD_SHA256 = "eef3a7c9519c7996c12b65ef04b0b93a22448a1902419d1e70b7428581307930"
PREVIOUS_V2_RUNNER_SHA256 = "f3cd6148e62addb164e6efd1d613fbcfb6ec81f428ea77c273b436e5f98db8ac"
PREVIOUS_V2_ARCHIVE_SHA256 = "0f6851a7cb2dd9f03f96c730739b9ab6b57b966d8bc5a656a75acc71af570e2a"
PREVIOUS_V2_LIST_SHA256 = "3dd1eb14e80d97c7f1c6631c77b6817c75843e21d0d5fb721f7b02ac97558784"
PREVIOUS_V2_SOURCE_IDENTITY = "cf271cd66778dbc2f3ea066bb1be7df257163686745f8eafdc116a8a2fb52e6e"
PREVIOUS_V2_FINAL_RELEASE_SHA256 = "ffa42d5b1d3fbdf516b5a17c3fe26648b1a96b075518e0d87975297207634990"
PREVIOUS_V2_FINAL_ARCHIVE_SHA256 = "3bb72b6ae1e3c76bc39a3c481de38e738bbc818f48d3c6eb1d3cf68533677a53"
PREVIOUS_V2_FINAL_LIST_SHA256 = "423b048a98a5592fa0efe622f54d032414b3fa7ab494c5e4eb19acd307c13759"
PREVIOUS_V2_FINAL_SOURCE_IDENTITY = "ade156aafeea86cf6a3b12dc1e90d9ca67899b5eca8f7fe9d53618c9b857a3ba"
PREVIOUS_V2_FINAL_ROOT_RELATIVE = Path(
    "target/curry-ledger-handoff-v2-tests/final-source-release-doc-final"
)
ALLOWED_V2_SOURCE_DELTA = {
    "added": ["docs/superpowers/plans/2026-10-25-curry-ledger-handoff-v2-handoff.md"],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}
CHECK_NAMES = (
    "acceptance_delivery",
    "reservation_and_history",
    "frozen_scope_inputs",
    "stage1_parent_receipt",
    "stage2_saved_intent",
    "isolated_runner_build",
    "saved_input_audit",
    "input_stability",
)
V2_CHECK_NAMES = (
    "previous_failed_source",
    "acceptance_delivery",
    "dual_timepoint_sources",
    "reservation_and_history",
    "frozen_scope_inputs",
    "stage1_parent_receipt",
    "stage2_saved_intent",
    "isolated_runner_build",
    "saved_input_audit",
    "input_stability",
)
V3_CHECK_NAMES = (
    "previous_failed_sources",
    "v2_final_source",
    "acceptance_delivery",
    "dual_timepoint_sources",
    "reservation_and_history",
    "frozen_scope_inputs",
    "stage1_parent_receipt",
    "stage2_saved_intent",
    "isolated_runner_build",
    "saved_input_audit",
    "input_stability",
)
V4_CHECK_NAMES = ("previous_v3_failed_source", *V3_CHECK_NAMES)
V5_CHECK_NAMES = ("bundle_layout", "previous_v4_failed_source", *V4_CHECK_NAMES)
TRACE_EVENTS = (
    ("input_validation", "start"),
    ("input_validation", "end"),
    ("parent_request_check", "start"),
    ("parent_request_check", "end"),
    ("saved_input_asset_scan", "start"),
    ("saved_input_asset_scan", "end"),
    ("ledger_check", "start"),
    ("ledger_check", "end"),
)
V3_PRELAUNCH_DIAGNOSTICS = frozenset({
    "curry_handoff_expected_identity_invalid",
    "saved_input_changed_before_runner_start",
    "saved_input_input_preflight_failed",
    "saved_input_diagnostic_directory_prelaunch_failed",
})
V3_PROCESS_INPUT_ROLES = frozenset({
    "new_runner_capture_metadata", "new_runner_stdout", "new_runner_stderr",
})
QUALIFICATIONS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
HASH = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class AuditVersionSpec:
    version: int
    kind: str
    output_root: Path
    checks: tuple[str, ...]
    schema_path: Path
    stdout_contract: str = "legacy-v1"

    @property
    def source_layers(self) -> tuple[str, ...]:
        layers = {
            1: (),
            2: ("previous_v1",),
            3: ("previous_v1", "previous_v2", "v2_final"),
            4: ("previous_v1", "previous_v2", "v2_final", "previous_v3"),
            5: (
                "previous_v1", "previous_v2", "v2_final", "previous_v3",
                "previous_v4",
            ),
        }
        return layers[self.version]

    def has_source_layer(self, layer: str) -> bool:
        return layer in self.source_layers

    @property
    def required_input_roles(self) -> frozenset[str]:
        return {
            1: frozenset(),
            2: V2_REQUIRED_INPUT_ROLES,
            3: V3_REQUIRED_INPUT_ROLES,
            4: V4_REQUIRED_INPUT_ROLES,
            5: V5_REQUIRED_INPUT_ROLES,
        }[self.version]

    @property
    def input_count(self) -> int | None:
        return {
            1: None,
            2: None,
            3: V3_REPORT_INPUT_COUNT,
            4: V4_REPORT_INPUT_COUNT,
            5: V5_REPORT_INPUT_COUNT,
        }[self.version]

    @property
    def captures_process_diagnostics(self) -> bool:
        return self.version in (2, 3, 4, 5)

    @property
    def tracks_process_attempt(self) -> bool:
        return self.has_source_layer("previous_v2")

    @property
    def process_input_roles(self) -> frozenset[str]:
        return V3_PROCESS_INPUT_ROLES if self.captures_process_diagnostics else frozenset()

    @property
    def source_root_layers(self) -> tuple[tuple[str, Path], ...]:
        roots = {
            "previous_v1": OUTPUT_RELATIVE,
            "previous_v2": V2_OUTPUT_RELATIVE,
            "v2_final": PREVIOUS_V2_FINAL_ROOT_RELATIVE,
            "previous_v3": V3_OUTPUT_RELATIVE,
            "previous_v4": V4_OUTPUT_RELATIVE,
        }
        return tuple((layer, roots[layer]) for layer in self.source_layers)

    def source_root(self, repo: Path, layer: str) -> Path:
        for configured_layer, relative in self.source_root_layers:
            if configured_layer == layer:
                return repo / relative
        raise ValueError("curry_handoff_source_layer_not_configured")


AUDIT_VERSIONS = {
    1: AuditVersionSpec(
        1, "curry_ledger_handoff_audit_v1", OUTPUT_RELATIVE, CHECK_NAMES,
        Path("schemas/curry-ledger-handoff-audit-v1.schema.json"),
    ),
    2: AuditVersionSpec(
        2, "curry_ledger_handoff_audit_v2", V2_OUTPUT_RELATIVE, V2_CHECK_NAMES,
        Path("schemas/curry-ledger-handoff-audit-v2.schema.json"),
    ),
    3: AuditVersionSpec(
        3, "curry_ledger_handoff_audit_v3", V3_OUTPUT_RELATIVE, V3_CHECK_NAMES,
        Path("schemas/curry-ledger-handoff-audit-v3.schema.json"),
    ),
    4: AuditVersionSpec(
        4, "curry_ledger_handoff_audit_v4", V4_OUTPUT_RELATIVE, V4_CHECK_NAMES,
        Path("schemas/curry-ledger-handoff-audit-v4.schema.json"),
        "verification-accounting-v1",
    ),
    5: AuditVersionSpec(
        5, "curry_ledger_handoff_audit_v5", V5_OUTPUT_RELATIVE, V5_CHECK_NAMES,
        Path("schemas/curry-ledger-handoff-audit-v5.schema.json"),
        "verification-accounting-v1",
    ),
}

V2_REQUIRED_INPUT_ROLES = frozenset({
    "previous_v1_report", "previous_v1_build_record", "previous_v1_runner",
    "previous_v1_source_archive", "previous_v1_source_file_list",
    "acceptance", "delivery", "native_source_archive", "native_source_file_list",
    "final_build_record", "final_source_archive", "final_source_file_list",
    "final_cli_artifact", "final_worker_artifact", "final_runner_artifact",
    "manifest", "prepared", "stage1_receipt", "stage2_request", "stage2_input",
    "stage2_seal", "stage2_report", "charge_ledger", "new_runner",
    "new_build_record", "new_source_archive", "new_source_file_list",
    "new_runner_stdout", "new_runner_stderr", "new_runner_capture_metadata",
    "v3_reservation_report", "v3_reservation_acceptance",
})
V3_REQUIRED_INPUT_ROLES = V2_REQUIRED_INPUT_ROLES | frozenset({
    "previous_v2_report", "previous_v2_build_record", "previous_v2_runner",
    "previous_v2_source_archive", "previous_v2_source_file_list",
    "v2_final_release_record", "v2_final_source_archive", "v2_final_source_file_list",
})
V4_PREVIOUS_V3_INPUT_ROLES = frozenset({
    "previous_v3_report", "previous_v3_build_record", "previous_v3_runner",
    "previous_v3_source_archive", "previous_v3_source_file_list",
    "previous_v3_final_delivery", "previous_v3_final_source_archive",
    "previous_v3_final_source_file_list",
})
V4_STAGE1_DIAGNOSTIC_INPUT_ROLES = frozenset({
    "stage1_process_sidecar", "stage1_process_metadata",
    "stage1_process_stdout", "stage1_process_stderr",
})
V4_REQUIRED_INPUT_ROLES = (
    V3_REQUIRED_INPUT_ROLES | V4_PREVIOUS_V3_INPUT_ROLES
    | V4_STAGE1_DIAGNOSTIC_INPUT_ROLES
)
V4_REPORT_INPUT_COUNT = 156
V4_PREVIOUS_V3_REPORT_SHA256 = "b0c8aa022a02b00ad546a37d04890a36c14eeeb29082447aef4def35b6fe10bf"
V4_PREVIOUS_V3_DELIVERY_SHA256 = "444b3e3f24152969bb210e1b607b21cc0475469578a6222c6105b57ac0b74911"
V4_PREVIOUS_V3_BUILD_RECORD_SHA256 = "b87073c899124942148c623fe1f26e412172f10f38dd1d1009a897bb3f5e08b7"
V4_PREVIOUS_V3_RUNNER_SHA256 = "6f6cc47b090525f49fe4c443a91a0a63889d4b4284a1bad3b38d65086f2a7c44"
V4_PREVIOUS_V3_ARCHIVE_SHA256 = "80366616585ca58e59fac4fbabc793c66ce90bd0611e5da3558bff5c66255deb"
V4_PREVIOUS_V3_LIST_SHA256 = "7d05667aed55f0c1b03c0be0073afb3f45a2236bde5471975cceeecd48d5964c"
V4_PREVIOUS_V3_FINAL_ARCHIVE_SHA256 = "23206ba24d4c2607239048fdba1e3060197f868f830cb1b4de6c5d8c77a8e8d8"
V4_PREVIOUS_V3_FINAL_LIST_SHA256 = "b93a61b80295f4c3c18a2f1e537de55ffa3e0deb9f0bbbb473b1f9bb8089f08d"
V4_ALLOWED_SOURCE_DELTA = {
    "added": ["docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v3-handoff.md"],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}
V5_PREVIOUS_V4_INPUT_ROLES = frozenset({
    "previous_v4_report", "previous_v4_build_record", "previous_v4_runner",
    "previous_v4_source_archive", "previous_v4_source_file_list",
    "previous_v4_final_delivery", "previous_v4_final_source_archive",
    "previous_v4_final_source_file_list",
})
V5_REQUIRED_INPUT_ROLES = V4_REQUIRED_INPUT_ROLES | V5_PREVIOUS_V4_INPUT_ROLES
V5_REPORT_INPUT_COUNT = 164
V5_PREVIOUS_V4_REPORT_SHA256 = "02f69485390c98cec677da83d3e9df3df70ffb9f238d38d3e8acf861968bad05"
V5_PREVIOUS_V4_DELIVERY_SHA256 = "bfc4f04042aad0b07df53d71e3496611193d782c2d96e7f55cf5e887707ace0f"
V5_ALLOWED_SOURCE_DELTA = {
    "added": ["docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md"],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}
V3_SOURCE_INPUT_COUNT = 100
V3_REPORT_INPUT_COUNT = 144
V3_INPUT_ROLE_ALLOWLIST = frozenset({
    'acceptance',
    'charge_ledger',
    'delivery',
    'final_build_record',
    'final_cli_artifact',
    'final_runner_artifact',
    'final_source_archive',
    'final_source_file_list',
    'final_worker_artifact',
    'manifest',
    'native_build_record',
    'native_cli_artifact',
    'native_runner_artifact',
    'native_source_archive',
    'native_source_file_list',
    'native_worker_artifact',
    'new_build_record',
    'new_runner',
    'new_runner_capture_metadata',
    'new_runner_stderr',
    'new_runner_stdout',
    'new_source_archive',
    'new_source_file_list',
    'prepared',
    'previous_v1_build_record',
    'previous_v1_report',
    'previous_v1_runner',
    'previous_v1_source_archive',
    'previous_v1_source_file_list',
    'previous_v2_build_record',
    'previous_v2_report',
    'previous_v2_runner',
    'previous_v2_source_archive',
    'previous_v2_source_file_list',
    'stage1_receipt',
    'stage2_input',
    'stage2_report',
    'stage2_request',
    'stage2_seal',
    'v2_final_release_record',
    'v2_final_source_archive',
    'v2_final_source_file_list',
    'v3_reservation_acceptance',
    'v3_reservation_report',
    'v3_source_acceptance',
    'v3_source_authenticated_prior_v2_acceptance',
    'v3_source_authenticated_v2_report',
    'v3_source_confirmation_acceptance',
    'v3_source_confirmation_delivery',
    'v3_source_confirmation_evidence_file_001',
    'v3_source_confirmation_evidence_file_002',
    'v3_source_confirmation_evidence_file_003',
    'v3_source_confirmation_evidence_file_004',
    'v3_source_confirmation_evidence_file_005',
    'v3_source_confirmation_evidence_file_006',
    'v3_source_confirmation_evidence_file_007',
    'v3_source_confirmation_evidence_file_008',
    'v3_source_confirmation_evidence_file_009',
    'v3_source_confirmation_evidence_file_010',
    'v3_source_confirmation_evidence_file_011',
    'v3_source_confirmation_evidence_file_012',
    'v3_source_confirmation_evidence_file_013',
    'v3_source_confirmation_evidence_file_014',
    'v3_source_confirmation_evidence_file_015',
    'v3_source_confirmation_evidence_file_016',
    'v3_source_confirmation_evidence_file_017',
    'v3_source_confirmation_evidence_file_018',
    'v3_source_confirmation_evidence_file_019',
    'v3_source_confirmation_evidence_file_020',
    'v3_source_confirmation_evidence_file_021',
    'v3_source_confirmation_evidence_file_022',
    'v3_source_confirmation_evidence_file_023',
    'v3_source_confirmation_evidence_file_024',
    'v3_source_confirmation_evidence_file_025',
    'v3_source_confirmation_evidence_file_026',
    'v3_source_confirmation_evidence_file_027',
    'v3_source_confirmation_evidence_file_028',
    'v3_source_confirmation_evidence_file_029',
    'v3_source_confirmation_evidence_file_030',
    'v3_source_confirmation_evidence_file_031',
    'v3_source_confirmation_evidence_file_032',
    'v3_source_confirmation_evidence_file_033',
    'v3_source_confirmation_evidence_file_034',
    'v3_source_confirmation_evidence_file_035',
    'v3_source_confirmation_evidence_file_036',
    'v3_source_confirmation_evidence_file_037',
    'v3_source_confirmation_evidence_file_038',
    'v3_source_confirmation_evidence_file_039',
    'v3_source_confirmation_evidence_file_040',
    'v3_source_confirmation_evidence_inventory',
    'v3_source_confirmation_manifest',
    'v3_source_workspace_identity',
    'v3_source_corrected_534_source_archive',
    'v3_source_corrected_534_source_file_list',
    'v3_source_final_source_archive',
    'v3_source_final_source_file_list',
    'v3_source_historical_ledger_01',
    'v3_source_historical_ledger_02',
    'v3_source_historical_ledger_03',
    'v3_source_historical_ledger_04',
    'v3_source_historical_ledger_06',
    'v3_source_historical_ledger_07',
    'v3_source_historical_ledger_08',
    'v3_source_historical_ledger_09',
    'v3_source_independent_review',
    'v3_source_latest_delivery',
    'v3_source_manifest_role_build_record',
    'v3_source_manifest_role_cli',
    'v3_source_manifest_role_identity',
    'v3_source_manifest_role_ordinary_config',
    'v3_source_manifest_role_runner',
    'v3_source_manifest_role_source_archive',
    'v3_source_manifest_role_source_file_list',
    'v3_source_manifest_role_tournament_config',
    'v3_source_manifest_role_window_start',
    'v3_source_manifest_role_worker',
    'v3_source_native_source_archive',
    'v3_source_native_source_file_list',
    'v3_source_normal_attempt_observation',
    'v3_source_prepared',
    'v3_source_previous_v1_failed_reservation_report',
    'v3_source_previous_v1_failed_tool_archive',
    'v3_source_previous_v1_failed_tool_file_list',
    'v3_source_previous_v2_failed_reservation_report',
    'v3_source_previous_v2_failed_tool_archive',
    'v3_source_previous_v2_failed_tool_file_list',
    'v3_source_protected_material_check',
    'v3_source_source_archive',
    'v3_source_source_file_list',
    'v3_source_stage1_input',
    'v3_source_stage1_input_seal',
    'v3_source_stage1_request',
    'v3_source_synthetic_public_report',
    'v3_source_tenki_validation_acceptance',
    'v3_source_tenki_validation_directory_evidence',
    'v3_source_tenki_validation_ledger',
    'v3_source_test_log_pytest-files_txt',
    'v3_source_test_log_pytest-full-rerun_log',
    'v3_source_test_log_pytest-full_log',
    'v3_source_v2_audit_535_source_archive',
    'v3_source_v2_audit_535_source_file_list',
    'v3_source_v2_failure_acceptance',
    'v3_source_v2_final_536_source_archive',
    'v3_source_v2_final_536_source_file_list',
})
V3_SOURCE_REQUIRED_ROLES = frozenset({
    *(f"v3_source_historical_ledger_{index:02d}" for index in (1, 2, 3, 4, 6, 7, 8, 9)),
    "v3_source_tenki_validation_ledger",
    "v3_source_tenki_validation_directory_evidence",
})

ALLOWED_SOURCE_DELTA = {
    "added": ["docs/superpowers/plans/2026-10-25-curry-option-verification-handoff.md"],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    for name in ("baseline-dir", "runner", "build-record", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--report-version", type=int, choices=(1, 2, 3, 4, 5), default=1)


def _version_spec(version: int) -> AuditVersionSpec:
    try:
        return AUDIT_VERSIONS[version]
    except KeyError:
        raise ValueError("curry_handoff_report_version_invalid") from None


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _expected_curry_stage_process_output(
    manifest: dict[str, Any], receipt: dict[str, Any], *,
    stdout_contract: str = "legacy-v1",
    option_spec: Any | None = None,
) -> dict[str, Any]:
    """Build the fixed stage stdout contract from authenticated inputs and a receipt."""
    ledger = receipt.get("ledger") if isinstance(receipt, dict) else None
    _require(isinstance(ledger, dict) and set(ledger) == {
        "abandoned", "completed", "consumed", "limit", "reserved", "unknown",
    } and all(type(ledger.get(name)) is int and ledger[name] >= 0 for name in (
        "abandoned", "completed", "consumed", "limit", "reserved", "unknown",
    )), "curry_handoff_stage_stdout_ledger_invalid")
    if stdout_contract == "legacy-v1":
        return {"successful": True, "native_calls": 1, "ledger": ledger}
    _require(stdout_contract == "verification-accounting-v1",
             "curry_handoff_stage_stdout_contract_invalid")
    from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE
    scope_spec = option_spec or OPTION_VERIFICATION_SCOPE

    _require(isinstance(manifest, dict)
             and manifest.get("scope") == scope_spec.scope
             and manifest.get("batch_kind") == scope_spec.batch_kind,
             "curry_handoff_stage_stdout_contract_scope_invalid")
    fixed = {
        "certified_historical_consumed": scope_spec.certified_historical_consumed,
        "policy_reserved": scope_spec.policy_reserved,
        "planning_base": scope_spec.planning_base,
        "reservation_id": scope_spec.reservation_id,
        "reservation_policy_id": scope_spec.reservation_policy_id,
    }
    for key, expected in fixed.items():
        actual = manifest.get(key)
        if type(expected) is int:
            _require(type(actual) is int and actual == expected,
                     "curry_handoff_stage_stdout_manifest_accounting_invalid")
        else:
            _require(type(actual) is str and actual == expected,
                     "curry_handoff_stage_stdout_manifest_accounting_invalid")
    _require(ledger["limit"] == scope_spec.limit,
             "curry_handoff_stage_stdout_ledger_limit_invalid")
    settled = (
        ledger["unknown"] == 0 and ledger["reserved"] == 0
        and ledger["abandoned"] == 0 and ledger["consumed"] == ledger["completed"]
    )
    consumed = ledger["consumed"] if settled else None
    return {
        "successful": True,
        "native_calls": 1,
        "ledger": ledger,
        "certified_historical_consumed": scope_spec.certified_historical_consumed,
        "policy_reserved": scope_spec.policy_reserved,
        "planning_base": scope_spec.planning_base,
        "reservation_id": scope_spec.reservation_id,
        "reservation_policy_id": scope_spec.reservation_policy_id,
        "new_consumed": consumed,
        "certified_consumed_including_new": (
            scope_spec.certified_historical_consumed + consumed
            if consumed is not None else None
        ),
        "planning_total": (
            scope_spec.planning_base + consumed
            if consumed is not None else None
        ),
        "unknown": ledger["unknown"],
        "old_confirmation_actual_consumed": None,
        "actual_all_history_cumulative": None,
    }


def _read(path: Path, expected: str | None = None) -> tuple[bytes, str]:
    raw = safe_path(path).read_bytes()
    found = _sha(raw)
    _require(expected is None or found == expected, "pinned_source_hash_mismatch")
    return raw, found


def validate_fixed_build_bundle(root: Path, runner: Path, build_record: Path) -> None:
    """Require the isolated audit bundle to contain exactly its four pinned entries."""
    _require(root.is_dir() and not root.is_symlink(), "curry_handoff_build_root_missing")
    _require(not (root / REPORT_RELATIVE).exists(), "curry_handoff_output_already_exists")
    _require(not (root / "process-diagnostics").exists(),
             "curry_handoff_diagnostics_already_exist")
    _require({item.name for item in root.iterdir()} == {
        "native-artifacts", "build-record.json", "source-native.zip",
        "source-native-file-list.json",
    }, "curry_handoff_build_root_contents_invalid")
    artifact_dir = root / "native-artifacts"
    _require(artifact_dir.is_dir() and not artifact_dir.is_symlink()
             and {item.name for item in artifact_dir.iterdir()} == {RUNNER_RELATIVE.name}
             and runner.is_file() and not runner.is_symlink()
             and build_record.is_file() and not build_record.is_symlink()
             and (root / SOURCE_ARCHIVE_RELATIVE).is_file()
             and not (root / SOURCE_ARCHIVE_RELATIVE).is_symlink()
             and (root / SOURCE_FILE_LIST_RELATIVE).is_file()
             and not (root / SOURCE_FILE_LIST_RELATIVE).is_symlink(),
             "curry_handoff_build_material_missing")


def validate_cli_paths(args: argparse.Namespace, repo: Path) -> tuple[Path, Path, Path, Path]:
    """Require the four fixed paths; the public CLI cannot redirect this audit."""
    repo = _absolute(repo)
    version = _version_spec(getattr(args, "report_version", 1))
    baseline = _absolute(args.baseline_dir)
    runner = _absolute(args.runner)
    build_record = _absolute(args.build_record)
    output = _absolute(args.output)
    root = repo / version.output_root
    _require(baseline == repo / BASELINE_RELATIVE, "fixed_curry_handoff_baseline_required")
    _require(runner == root / RUNNER_RELATIVE, "fixed_curry_handoff_runner_required")
    _require(build_record == root / BUILD_RECORD_RELATIVE,
             "fixed_curry_handoff_build_record_required")
    _require(output == root / REPORT_RELATIVE, "fixed_curry_handoff_output_required")
    for path in (baseline, root, runner, build_record, output,
                 root / SOURCE_ARCHIVE_RELATIVE, root / SOURCE_FILE_LIST_RELATIVE,
                 root / "process-diagnostics"):
        _require(not path.is_symlink(), "curry_handoff_symlink_rejected")
    safe_path(baseline, file=False)
    safe_path(root, file=False)
    safe_path(root / "native-artifacts", file=False)
    safe_path(runner)
    safe_path(build_record)
    safe_path(root / SOURCE_ARCHIVE_RELATIVE)
    safe_path(root / SOURCE_FILE_LIST_RELATIVE)
    ignored = safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    _require(any(line.strip().strip("/") == "data/runtime" for line in ignored),
             "curry_handoff_output_must_be_ignored")
    _require(root.is_dir(), "curry_handoff_build_root_missing")
    _require(not output.exists(), "curry_handoff_output_already_exists")
    _require(not (root / "process-diagnostics").exists(),
             "curry_handoff_diagnostics_already_exist")
    validate_fixed_build_bundle(root, runner, build_record)
    return baseline, root, runner, build_record


def _report_template(
    source_identity: dict | None, version: int = 1, *, _sources: Any | None = None,
) -> dict[str, Any]:
    version_spec = _version_spec(version)
    acceptance_anchor = ACCEPTANCE_SHA256
    delivery_anchor = DELIVERY_SHA256
    previous_report_anchor = PREVIOUS_V1_REPORT_SHA256
    if version in (2, 3, 4, 5) and _sources is not None:
        acceptance_anchor = _sources.child("baseline").file_sha256_role("baseline_acceptance")
        delivery_anchor = _sources.child("baseline").file_sha256_role("baseline_delivery")
        previous_report_anchor = _sources.child("previous_failed_attempt").file_sha256_role(
            "previous_v1_report",
        )
    value = {
        "schema_version": version_spec.version,
        "kind": version_spec.kind,
        "status": "incomplete",
        "failure_checkpoint": None,
        "anchors": {
            "acceptance_sha256": acceptance_anchor,
            "delivery_sha256": delivery_anchor,
        },
        "tool_identity": _source_summary(source_identity),
        "checks": {name: "not_run" for name in version_spec.checks},
        "native_calls": 0,
        "execution_ready": False,
        "baseline": {
            "relative_root": BASELINE_RELATIVE.as_posix(),
            "acceptance_sha256": None,
            "delivery_sha256": None,
            "scope": "curry-option-verification-v1",
            "context": None,
            "manifest_sha256": None,
            "prepared_sha256": None,
            "stage1_receipt_sha256": None,
            "stage2_input_sha256": None,
            "stage2_request_sha256": None,
        },
        "accounting": {
            "certified_historical_consumed": 32,
            "policy_reserved": 7,
            "planning_base": 39,
            "new_consumed": None,
            "certified_consumed_including_new": None,
            "planning_total": None,
            "unknown": None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        },
        "historical_failure": {
            "scope": "curry-option-verification-v1",
            "stage1_passed": None,
            "stage2_failed": None,
            "stage2_diagnostic": None,
            "historical_exit_code_certified": False,
            "old_failure_rewritten": False,
        },
        "runner": {
            "role": RUNNER_ROLE,
            "mode": RUNNER_MODE,
            "sha256": None,
            "build_record_sha256": None,
            "build_record_identity": None,
            "source_identity": None,
            "source_file_count": None,
            "return_code": None,
            "process_status": None,
            "diagnostic_sha256": None,
            "stdout_sha256": None,
            "stdout_bytes": None,
            "stderr_sha256": None,
            "stderr_bytes": None,
            "trace": [],
            "saved_input_result": None,
        },
        "inputs": [],
        "stability": {
            "workspace_stable": "not_checked",
            "baseline_stable": "not_checked",
            "reservation_stable": "not_checked",
            "ledger_stable": "not_checked",
            "runner_build_stable": "not_checked",
            "stage2_receipt_absent_before": None,
            "stage2_receipt_absent_after": None,
        },
        "diagnostic": None,
        "elapsed_seconds": 0.0,
        **QUALIFICATIONS,
    }
    if version_spec.captures_process_diagnostics:
        value["runner"]["process_capture"] = {
            "metadata_path": None,
            "metadata_sha256": None,
            "stdout_path": None,
            "stderr_path": None,
        }
        if version_spec.tracks_process_attempt:
            value["runner"]["process_attempted"] = False
            value["runner"]["process_error_code"] = None
        value["stability"]["process_diagnostics_stable"] = "not_checked"
        value["historical_failure"].update({
            "acceptance_runner_return_code_claimed": None,
            "archived_static_return_code": None,
            "historical_actual_exit_code": None,
        })
        value["previous_failed_attempt"] = {
            "report_sha256": previous_report_anchor,
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "runner_sha256": None,
            "build_record_sha256": None,
            "source_archive_sha256": None,
            "source_file_list_sha256": None,
        }
        value["dual_timepoint_sources"] = {
            "native_source_identity": None,
            "native_file_count": None,
            "final_source_identity": None,
            "final_file_count": None,
            "source_delta": None,
            "parent_lock_path": "crates/ygo-engine-adapter/examples/curry-option-validation.rs",
            "parent_view_retained": None,
            "historical_actual_exit_code": None,
        }
        value["stability_rechecks"] = {
            "workspace": "not_collected",
            "previous_failure_tree": "not_collected",
            "baseline_tree": "not_collected",
            "reservation_tree": "not_collected",
            "ledger": "not_collected",
            "runner_build": "not_collected",
            "process_diagnostics": "not_collected",
            "stage2_receipt_absent": None,
        }
    if version_spec.has_source_layer("previous_v2"):
        previous_v2_hash = PREVIOUS_V2_REPORT_SHA256
        if _sources is not None:
            previous_v2_hash = _sources.child(
                "previous_v2_failed_attempt",
            ).file_sha256_role("previous_v2_report")
        value["previous_v2_failed_attempt"] = {
            "report_sha256": previous_v2_hash,
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "runner_sha256": None,
            "build_record_sha256": None,
            "source_archive_sha256": None,
            "source_file_list_sha256": None,
        }
        value["v2_final_source"] = {
            "release_record_sha256": (
                _sources.child("v2_final_source").file_sha256_role("v2_final_release_record")
                if _sources is not None else PREVIOUS_V2_FINAL_RELEASE_SHA256
            ),
            "source_archive_sha256": (
                _sources.child("v2_final_source").file_sha256_role("v2_final_source_archive")
                if _sources is not None else PREVIOUS_V2_FINAL_ARCHIVE_SHA256
            ),
            "source_file_list_sha256": (
                _sources.child("v2_final_source").file_sha256_role("v2_final_source_file_list")
                if _sources is not None else PREVIOUS_V2_FINAL_LIST_SHA256
            ),
            "source_identity": None,
            "file_count": None,
            "source_delta": None,
        }
        value["stability"]["previous_v2_failure_stable"] = "not_checked"
        value["stability"]["v2_final_source_stable"] = "not_checked"
        value["stability_rechecks"]["previous_v2_failure_tree"] = "not_collected"
        value["stability_rechecks"]["v2_final_source_tree"] = "not_collected"
    if version_spec.has_source_layer("previous_v3"):
        previous_v3_hash = V4_PREVIOUS_V3_REPORT_SHA256
        previous_v3_pins = {
            "previous_v3_final_delivery": V4_PREVIOUS_V3_DELIVERY_SHA256,
            "previous_v3_runner": V4_PREVIOUS_V3_RUNNER_SHA256,
            "previous_v3_build_record": V4_PREVIOUS_V3_BUILD_RECORD_SHA256,
            "previous_v3_source_archive": V4_PREVIOUS_V3_ARCHIVE_SHA256,
            "previous_v3_source_file_list": V4_PREVIOUS_V3_LIST_SHA256,
            "previous_v3_final_source_archive": V4_PREVIOUS_V3_FINAL_ARCHIVE_SHA256,
            "previous_v3_final_source_file_list": V4_PREVIOUS_V3_FINAL_LIST_SHA256,
        }
        if _sources is not None:
            previous_v3_sources = _sources.child("previous_v3_failed_source")
            previous_v3_hash = previous_v3_sources.file_sha256_role("previous_v3_report")
            previous_v3_pins = {
                role: previous_v3_sources.file_sha256_role(role)
                for role in previous_v3_pins
            }
        value["accounting"]["scope"] = "curry-option-verification-v1"
        value["previous_v3_failed_source"] = {
            "report_sha256": previous_v3_hash,
            "delivery_sha256": previous_v3_pins["previous_v3_final_delivery"],
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "runner_sha256": previous_v3_pins["previous_v3_runner"],
            "build_record_sha256": previous_v3_pins["previous_v3_build_record"],
            "source_archive_sha256": previous_v3_pins["previous_v3_source_archive"],
            "source_file_list_sha256": previous_v3_pins["previous_v3_source_file_list"],
            "final_delivery_sha256": previous_v3_pins["previous_v3_final_delivery"],
            "final_source_archive_sha256": previous_v3_pins[
                "previous_v3_final_source_archive"
            ],
            "final_source_file_list_sha256": previous_v3_pins[
                "previous_v3_final_source_file_list"
            ],
            "source_identity": None,
            "file_count": None,
            "final_source_identity": None,
            "final_file_count": None,
            "source_delta": None,
        }
        value["stability"]["previous_v3_failure_stable"] = "not_checked"
        value["stability_rechecks"]["previous_v3_failure_tree"] = "not_collected"
    if version_spec.has_source_layer("previous_v4"):
        previous_v4_hash = V5_PREVIOUS_V4_REPORT_SHA256
        # Only the two V4 top-level artifacts are fixed anchors. All remaining
        # artifact hashes are derived from the authenticated delivery/build
        # records by _verify_previous_v4_failed_source.
        previous_v4_pins = {
            "previous_v4_final_delivery": V5_PREVIOUS_V4_DELIVERY_SHA256,
            "previous_v4_runner": None,
            "previous_v4_build_record": None,
            "previous_v4_source_archive": None,
            "previous_v4_source_file_list": None,
            "previous_v4_final_source_archive": None,
            "previous_v4_final_source_file_list": None,
        }
        if _sources is not None:
            previous_v4_sources = _sources.child("previous_v4_failed_source")
            previous_v4_hash = previous_v4_sources.file_sha256_role("previous_v4_report")
            previous_v4_pins["previous_v4_final_delivery"] = (
                previous_v4_sources.file_sha256_role("previous_v4_final_delivery")
            )
        value["previous_v4_failed_source"] = {
            "report_sha256": previous_v4_hash,
            "delivery_sha256": previous_v4_pins["previous_v4_final_delivery"],
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "runner_sha256": previous_v4_pins["previous_v4_runner"],
            "build_record_sha256": previous_v4_pins["previous_v4_build_record"],
            "source_archive_sha256": previous_v4_pins["previous_v4_source_archive"],
            "source_file_list_sha256": previous_v4_pins["previous_v4_source_file_list"],
            "final_delivery_sha256": previous_v4_pins["previous_v4_final_delivery"],
            "final_source_archive_sha256": previous_v4_pins[
                "previous_v4_final_source_archive"
            ],
            "final_source_file_list_sha256": previous_v4_pins[
                "previous_v4_final_source_file_list"
            ],
            "report_tool_identity": None,
            "report_input_count": None,
            "source_identity": None,
            "file_count": None,
            "final_source_identity": None,
            "final_file_count": None,
            "source_delta": None,
        }
        value["stability"]["previous_v4_failure_stable"] = "not_checked"
        value["stability_rechecks"]["previous_v4_failure_tree"] = "not_collected"
    return value


def _source_summary(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {
        "head": value.get("head"),
        "identity": value.get("identity"),
        "file_count": len(value.get("files", {})) if isinstance(value.get("files"), dict) else None,
    }


def validate_report(
    value: Any, *, _sources: Any | None = None, repo: Path | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
) -> bool:
    if isinstance(value, dict) and value.get("schema_version") in (3, 4, 5):
        return _validate_report_v3(
            value, _sources=_sources, repo=repo, source_collector=source_collector,
            _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec, version=value["schema_version"],
        )
    if isinstance(value, dict) and value.get("schema_version") == 2:
        return _validate_report_v2(
            value, _sources=_sources, repo=repo, source_collector=source_collector,
            _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec,
        )
    return _validate_report_v1(value)


def _validate_report_v3(
    value: Any, *, _sources: Any | None = None, repo: Path | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    version: int = 3,
) -> bool:
    """Validate V3/V4 source roles while retaining each versioned report contract."""
    _require(version in (3, 4, 5), "curry_handoff_report_version_invalid")
    required = set(_report_template(None, version))
    _require(isinstance(value, dict) and set(value) == required,
             "curry_handoff_report_fields_invalid")
    spec = _version_spec(version)
    _require(type(value.get("schema_version")) is int and value["schema_version"] == version
             and value.get("kind") == spec.kind,
             "curry_handoff_report_version_invalid")
    _require(value.get("status") in ("passed", "failed", "incomplete"),
             "curry_handoff_report_status_invalid")
    diagnostic = value.get("diagnostic")
    if value["status"] == "failed":
        _require(isinstance(diagnostic, str)
                 and re.fullmatch(r"[a-z][a-z0-9_]{1,100}", diagnostic) is not None,
                 "curry_handoff_failed_diagnostic_invalid")
    else:
        _require(diagnostic is None, "curry_handoff_nonfailed_diagnostic_invalid")
    checks = value.get("checks")
    _require(isinstance(checks, dict) and set(checks) == set(spec.checks)
             and all(item in ("not_run", "passed", "failed") for item in checks.values()),
             "curry_handoff_check_set_invalid")
    checkpoint = value.get("failure_checkpoint")
    _require(checkpoint is None or checkpoint in spec.checks,
             "curry_handoff_report_checkpoint_invalid")
    if value["status"] == "failed":
        _require(checkpoint in spec.checks, "curry_handoff_failed_checkpoint_missing")
        index = spec.checks.index(checkpoint)
        _require([checks[name] for name in spec.checks[:index]] == ["passed"] * index
                 and checks[checkpoint] == "failed"
                 and all(checks[name] == "not_run" for name in spec.checks[index + 1:]),
                 "curry_handoff_failed_checkpoint_checks_inconsistent")
    elif value["status"] == "incomplete":
        _require(checkpoint is None, "curry_handoff_incomplete_checkpoint_must_be_null")
        seen_not_run = False
        for name in spec.checks:
            state = checks[name]
            _require(state != "failed", "curry_handoff_incomplete_contains_failed_check")
            if state == "not_run":
                seen_not_run = True
            else:
                _require(not seen_not_run, "curry_handoff_incomplete_check_order_invalid")
    else:
        _require(checkpoint is None and all(state == "passed" for state in checks.values()),
                 "curry_handoff_success_checks_incomplete")

    _require(type(value.get("native_calls")) is int and value["native_calls"] == 0
             and value.get("execution_ready") is False
             and all(value.get(flag) is False for flag in QUALIFICATIONS),
             "curry_handoff_zero_call_contract_invalid")
    expected_anchors = {"acceptance_sha256": ACCEPTANCE_SHA256,
                        "delivery_sha256": DELIVERY_SHA256}
    if _sources is not None:
        baseline_sources = _sources.child("baseline")
        expected_anchors = {
            "acceptance_sha256": baseline_sources.file_sha256_role("baseline_acceptance"),
            "delivery_sha256": baseline_sources.file_sha256_role("baseline_delivery"),
        }
    _require(value.get("anchors") == expected_anchors, "curry_handoff_anchor_set_invalid")

    accounting = value.get("accounting")
    accounting_fields = {
        "certified_historical_consumed", "policy_reserved", "planning_base",
        "new_consumed", "certified_consumed_including_new", "planning_total",
        "unknown", "old_confirmation_actual_consumed", "actual_all_history_cumulative",
    }
    if spec.has_source_layer("previous_v3"):
        accounting_fields.add("scope")
    _require(isinstance(accounting, dict) and set(accounting) == accounting_fields
        and accounting.get("certified_historical_consumed") == 32
        and accounting.get("policy_reserved") == 7 and accounting.get("planning_base") == 39
        and accounting.get("old_confirmation_actual_consumed") is None
        and accounting.get("actual_all_history_cumulative") is None,
        "curry_handoff_accounting_basis_invalid")
    if spec.has_source_layer("previous_v3"):
        _require(accounting.get("scope") == "curry-option-verification-v1",
                 "curry_handoff_accounting_scope_invalid")
    stats = tuple(accounting[key] for key in (
        "new_consumed", "certified_consumed_including_new", "planning_total", "unknown",
    ))
    _require(all(item is None or (type(item) is int and item >= 0) for item in stats)
             and (all(item is None for item in stats) or all(type(item) is int for item in stats)),
             "curry_handoff_accounting_stats_partially_known")

    for field, expected_hash in (
        ("previous_failed_attempt", PREVIOUS_V1_REPORT_SHA256),
        ("previous_v2_failed_attempt", PREVIOUS_V2_REPORT_SHA256),
    ):
        block = value.get(field)
        if _sources is not None:
            source_role = "previous_v1_report" if field == "previous_failed_attempt" else "previous_v2_report"
            source_node = "previous_failed_attempt" if field == "previous_failed_attempt" else "previous_v2_failed_attempt"
            expected_hash = _sources.child(source_node).file_sha256_role(source_role)
        _require(isinstance(block, dict) and set(block) == {
            "report_sha256", "status", "failure_checkpoint", "diagnostic", "runner_sha256",
            "build_record_sha256", "source_archive_sha256", "source_file_list_sha256",
        } and block.get("report_sha256") == expected_hash
            and block.get("status") in (None, "failed")
            and all(block.get(key) is None or HASH.fullmatch(str(block[key])) is not None
                    for key in ("runner_sha256", "build_record_sha256", "source_archive_sha256",
                                "source_file_list_sha256")),
            "curry_handoff_previous_failure_fields_invalid")

    if spec.has_source_layer("previous_v3"):
        previous_v3 = value.get("previous_v3_failed_source")
        expected_v3 = {
            "report_sha256": V4_PREVIOUS_V3_REPORT_SHA256,
            "delivery_sha256": V4_PREVIOUS_V3_DELIVERY_SHA256,
            "final_delivery_sha256": V4_PREVIOUS_V3_DELIVERY_SHA256,
            "runner_sha256": V4_PREVIOUS_V3_RUNNER_SHA256,
            "build_record_sha256": V4_PREVIOUS_V3_BUILD_RECORD_SHA256,
            "source_archive_sha256": V4_PREVIOUS_V3_ARCHIVE_SHA256,
            "source_file_list_sha256": V4_PREVIOUS_V3_LIST_SHA256,
            "final_source_archive_sha256": V4_PREVIOUS_V3_FINAL_ARCHIVE_SHA256,
            "final_source_file_list_sha256": V4_PREVIOUS_V3_FINAL_LIST_SHA256,
        }
        if _sources is not None:
            node = _sources.child("previous_v3_failed_source")
            for role, key in (
                ("previous_v3_report", "report_sha256"),
                ("previous_v3_final_delivery", "delivery_sha256"),
                ("previous_v3_final_delivery", "final_delivery_sha256"),
                ("previous_v3_runner", "runner_sha256"),
                ("previous_v3_build_record", "build_record_sha256"),
                ("previous_v3_source_archive", "source_archive_sha256"),
                ("previous_v3_source_file_list", "source_file_list_sha256"),
                ("previous_v3_final_source_archive", "final_source_archive_sha256"),
                ("previous_v3_final_source_file_list", "final_source_file_list_sha256"),
            ):
                expected_v3[key] = node.file_sha256_role(role)
        _require(isinstance(previous_v3, dict) and set(previous_v3) == {
            "report_sha256", "delivery_sha256", "status", "failure_checkpoint",
            "diagnostic", "runner_sha256", "build_record_sha256",
            "source_archive_sha256", "source_file_list_sha256",
            "final_delivery_sha256", "final_source_archive_sha256",
            "final_source_file_list_sha256", "source_identity", "file_count",
            "final_source_identity", "final_file_count", "source_delta",
        } and all(previous_v3.get(key) == expected for key, expected in expected_v3.items()),
                 "curry_handoff_previous_v3_source_fields_invalid")
        if checks["previous_v3_failed_source"] == "passed":
            _require(previous_v3.get("status") == "failed"
            and previous_v3.get("failure_checkpoint") == "stage1_parent_receipt"
            and previous_v3.get("diagnostic") == "curry_saved_stage_process_output_invalid"
            and (previous_v3.get("source_identity") is None
                 or HASH.fullmatch(str(previous_v3["source_identity"])) is not None)
            and (previous_v3.get("final_source_identity") is None
                 or HASH.fullmatch(str(previous_v3["final_source_identity"])) is not None)
            and (previous_v3.get("file_count") is None
                 or (type(previous_v3["file_count"]) is int and previous_v3["file_count"] == 563))
            and (previous_v3.get("final_file_count") is None
                 or (type(previous_v3["final_file_count"]) is int and previous_v3["final_file_count"] == 564))
            and (previous_v3.get("source_delta") is None
                 or previous_v3.get("source_delta") == V4_ALLOWED_SOURCE_DELTA),
                     "curry_handoff_previous_v3_source_fields_invalid")
        else:
            _require(all(previous_v3.get(key) is None for key in (
                "status", "failure_checkpoint", "diagnostic", "source_identity",
                "file_count", "final_source_identity", "final_file_count", "source_delta",
            )), "curry_handoff_previous_v3_unchecked_source_has_claims")

    if spec.has_source_layer("previous_v4"):
        previous_v4 = value.get("previous_v4_failed_source")
        expected_v4 = {
            "report_sha256": V5_PREVIOUS_V4_REPORT_SHA256,
            "delivery_sha256": V5_PREVIOUS_V4_DELIVERY_SHA256,
            "final_delivery_sha256": V5_PREVIOUS_V4_DELIVERY_SHA256,
        }
        if _sources is not None:
            node = _sources.child("previous_v4_failed_source")
            expected_v4.update({
                "report_sha256": node.file_sha256_role("previous_v4_report"),
                "delivery_sha256": node.file_sha256_role("previous_v4_final_delivery"),
                "final_delivery_sha256": node.file_sha256_role(
                    "previous_v4_final_delivery",
                ),
            })
        _require(isinstance(previous_v4, dict) and set(previous_v4) == {
            "report_sha256", "delivery_sha256", "final_delivery_sha256",
            "runner_sha256", "build_record_sha256", "source_archive_sha256",
            "source_file_list_sha256", "final_source_archive_sha256",
            "final_source_file_list_sha256", "status", "failure_checkpoint", "diagnostic",
            "report_tool_identity", "report_input_count", "source_identity", "file_count",
            "final_source_identity", "final_file_count", "source_delta",
        } and all(previous_v4.get(key) == expected for key, expected in expected_v4.items())
            and previous_v4.get("report_tool_identity") is None
            and (previous_v4.get("report_input_count") is None
                 or (type(previous_v4.get("report_input_count")) is int
                     and previous_v4.get("report_input_count") == 0))
            and all(previous_v4.get(key) is None or HASH.fullmatch(str(previous_v4[key]))
                    is not None for key in (
                        "runner_sha256", "build_record_sha256", "source_archive_sha256",
                        "source_file_list_sha256", "final_source_archive_sha256",
                        "final_source_file_list_sha256",
                    )),
            "curry_handoff_previous_v4_source_fields_invalid")
        if checks.get("previous_v4_failed_source") == "passed":
            _require(repo is not None,
                     "curry_handoff_previous_v4_validation_root_required")
            derived_v4 = _verify_previous_v4_failed_source(
                _absolute(repo), version_spec=spec, _sources=_sources,
            )["record"]
            _require(previous_v4 == derived_v4,
                     "curry_handoff_previous_v4_source_binding_mismatch")
            _require(previous_v4.get("status") == "failed"
                     and previous_v4.get("failure_checkpoint") == "previous_v3_failed_source"
                     and previous_v4.get("diagnostic") == "curry_handoff_build_root_contents_invalid"
                     and previous_v4.get("source_identity") is not None
                     and previous_v4.get("file_count") == 568
                     and previous_v4.get("final_source_identity") is not None
                     and previous_v4.get("final_file_count") == 569
                     and previous_v4.get("source_delta") == V5_ALLOWED_SOURCE_DELTA,
                     "curry_handoff_previous_v4_source_unbound")
        else:
            _require(all(previous_v4.get(key) is None for key in (
                "runner_sha256", "build_record_sha256", "source_archive_sha256",
                "source_file_list_sha256", "final_source_archive_sha256",
                "final_source_file_list_sha256", "status", "failure_checkpoint",
                "diagnostic", "source_identity", "file_count", "final_source_identity",
                "final_file_count", "source_delta",
            )), "curry_handoff_previous_v4_unchecked_source_has_claims")
            _require(previous_v4.get("report_input_count") is None,
                     "curry_handoff_previous_v4_unchecked_source_has_claims")

    v2_final = value.get("v2_final_source")
    v2_final_pins = {
        "release_record_sha256": PREVIOUS_V2_FINAL_RELEASE_SHA256,
        "source_archive_sha256": PREVIOUS_V2_FINAL_ARCHIVE_SHA256,
        "source_file_list_sha256": PREVIOUS_V2_FINAL_LIST_SHA256,
    }
    if _sources is not None:
        source_node = _sources.child("v2_final_source")
        v2_final_pins = {
            "release_record_sha256": source_node.file_sha256_role("v2_final_release_record"),
            "source_archive_sha256": source_node.file_sha256_role("v2_final_source_archive"),
            "source_file_list_sha256": source_node.file_sha256_role("v2_final_source_file_list"),
        }
    _require(isinstance(v2_final, dict) and set(v2_final) == {
        "release_record_sha256", "source_archive_sha256", "source_file_list_sha256",
        "source_identity", "file_count", "source_delta",
    } and all(v2_final.get(key) == expected for key, expected in v2_final_pins.items())
        and (v2_final.get("source_identity") is None
             or HASH.fullmatch(str(v2_final["source_identity"])) is not None)
        and (v2_final.get("file_count") is None
             or (type(v2_final["file_count"]) is int and v2_final["file_count"] == 558))
        and (v2_final.get("source_delta") is None
             or v2_final.get("source_delta") == ALLOWED_V2_SOURCE_DELTA),
        "curry_handoff_v2_final_source_fields_invalid")

    source_chain = value.get("dual_timepoint_sources")
    _require(isinstance(source_chain, dict) and set(source_chain) == set(
        _report_template(None, version)["dual_timepoint_sources"]
    ) and source_chain.get("parent_lock_path")
        == "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
        and source_chain.get("historical_actual_exit_code") is None,
        "curry_handoff_dual_timepoint_fields_invalid")
    _require(source_chain.get("source_delta") is None
             or source_chain.get("source_delta") == ALLOWED_SOURCE_DELTA,
             "curry_handoff_dual_timepoint_delta_invalid")
    failure = value.get("historical_failure")
    _require(isinstance(failure, dict) and failure.get("scope") == "curry-option-verification-v1"
             and failure.get("historical_actual_exit_code") is None
             and failure.get("historical_exit_code_certified") is False
             and failure.get("old_failure_rewritten") is False,
             "curry_handoff_historical_failure_fields_invalid")

    runner = value.get("runner")
    runner_template = _report_template(None, version)["runner"]
    _require(isinstance(runner, dict) and set(runner) == set(runner_template)
             and runner.get("role") == RUNNER_ROLE and runner.get("mode") == RUNNER_MODE,
             "curry_handoff_runner_fields_invalid")
    capture = runner.get("process_capture")
    _require(isinstance(capture, dict) and set(capture) == {
        "metadata_path", "metadata_sha256", "stdout_path", "stderr_path",
    }, "curry_handoff_process_capture_fields_invalid")
    capture_values = tuple(capture.get(key) for key in (
        "metadata_path", "metadata_sha256", "stdout_path", "stderr_path",
    ))
    process_attempted = runner.get("process_attempted")
    _require(type(process_attempted) is bool,
             "curry_handoff_process_attempt_state_invalid")
    if process_attempted:
        _require(value["status"] == "passed" or (
            value["status"] == "failed"
            and checkpoint in ("saved_input_audit", "input_stability")
        ), "curry_handoff_process_attempt_checkpoint_invalid")
        if value["status"] == "failed" and checkpoint == "input_stability":
            _require(runner.get("process_status") == "completed"
                     and runner.get("return_code") == 0
                     and isinstance(runner.get("saved_input_result"), dict),
                     "curry_handoff_input_stability_requires_successful_runner")
        if value["status"] == "failed" and checkpoint == "saved_input_audit":
            _require(value.get("diagnostic") not in V3_PRELAUNCH_DIAGNOSTICS,
                     "curry_handoff_attempted_runner_has_prelaunch_diagnostic")
        _require(all(item is not None for item in capture_values),
                 "curry_handoff_process_capture_missing")
        _require(repo is not None, "curry_handoff_process_capture_source_root_required")
        capture_input_rows = _verify_process_capture(
            value, _absolute(repo),
            require_success=(value["status"] == "passed" or (
                value["status"] == "failed" and checkpoint == "input_stability"
            )),
            output_root=_absolute(repo) / spec.output_root,
        )
    else:
        capture_input_rows = []
        _require(all(item is None for item in capture_values)
                 and all(runner.get(key) is None for key in (
                     "return_code", "process_status", "diagnostic_sha256", "stdout_sha256",
                     "stdout_bytes", "stderr_sha256", "stderr_bytes", "process_error_code",
                 )) and runner.get("trace") == []
                 and runner.get("saved_input_result") is None,
                 "curry_handoff_process_attempt_state_invalid")
        _require(value["status"] != "incomplete" or value.get("diagnostic") is None,
                 "curry_handoff_incomplete_diagnostic_invalid")
        if (value["status"] == "failed"
                and checkpoint == "saved_input_audit"):
            _require(value.get("diagnostic") in V3_PRELAUNCH_DIAGNOSTICS,
                     "curry_handoff_process_capture_missing")
        if repo is not None:
            _require_empty_process_diagnostics(_absolute(repo), output_root=spec.output_root)
    if value["status"] == "passed":
        _require(process_attempted is True,
                 "curry_handoff_process_capture_missing")
    stability = value.get("stability")
    stability_fields = (
        "workspace_stable", "baseline_stable", "reservation_stable", "ledger_stable",
        "runner_build_stable", "process_diagnostics_stable", "previous_v2_failure_stable",
        "v2_final_source_stable",
    )
    if spec.has_source_layer("previous_v3"):
        stability_fields = (*stability_fields, "previous_v3_failure_stable")
    if spec.has_source_layer("previous_v4"):
        stability_fields = (*stability_fields, "previous_v4_failure_stable")
    _require(isinstance(stability, dict) and set(stability) == set(
        _report_template(None, version)["stability"]
    ) and all(stability.get(key) in ("not_checked", "passed", "failed") for key in stability_fields)
        and all(stability.get(key) is None or type(stability[key]) is bool for key in (
        "stage2_receipt_absent_before", "stage2_receipt_absent_after",
    )), "curry_handoff_stability_fields_invalid")
    stability_rechecks = value.get("stability_rechecks")
    expected_recheck_keys = set(_report_template(None, version)["stability_rechecks"])
    _require(isinstance(stability_rechecks, dict)
             and set(stability_rechecks) == expected_recheck_keys
             and all(
                 stability_rechecks[key] in (
                     "not_collected", "consistent", "changed", "recheck_failed",
                 )
                 for key in expected_recheck_keys - {"stage2_receipt_absent"}
             )
             and (stability_rechecks["stage2_receipt_absent"] is None
                  or type(stability_rechecks["stage2_receipt_absent"]) is bool),
             "curry_handoff_stability_rechecks_invalid")
    for target, source in {
        "workspace_stable": "workspace",
        "baseline_stable": "baseline_tree",
        "reservation_stable": "reservation_tree",
        "ledger_stable": "ledger",
        "runner_build_stable": "runner_build",
        "process_diagnostics_stable": "process_diagnostics",
        "previous_v2_failure_stable": "previous_v2_failure_tree",
        "v2_final_source_stable": "v2_final_source_tree",
    }.items():
        recheck = stability_rechecks.get(source)
        expected_state = (
            "not_checked" if recheck == "not_collected" else
            "passed" if recheck == "consistent" else "failed"
        )
        _require(stability.get(target) == expected_state,
                 "curry_handoff_stability_recheck_mismatch")
    if spec.has_source_layer("previous_v3"):
        recheck = stability_rechecks.get("previous_v3_failure_tree")
        expected_state = (
            "not_checked" if recheck == "not_collected" else
            "passed" if recheck == "consistent" else "failed"
        )
        _require(stability.get("previous_v3_failure_stable") == expected_state,
                 "curry_handoff_stability_recheck_mismatch")
    if spec.has_source_layer("previous_v4"):
        recheck = stability_rechecks.get("previous_v4_failure_tree")
        expected_state = (
            "not_checked" if recheck == "not_collected" else
            "passed" if recheck == "consistent" else "failed"
        )
        _require(stability.get("previous_v4_failure_stable") == expected_state,
                 "curry_handoff_stability_recheck_mismatch")
    _require(stability.get("stage2_receipt_absent_after")
             == stability_rechecks.get("stage2_receipt_absent"),
             "curry_handoff_stability_recheck_mismatch")
    if value["status"] == "failed" and checkpoint == "input_stability":
        adverse_recheck = any(
            state in ("changed", "recheck_failed")
            for name, state in stability_rechecks.items()
            if name != "stage2_receipt_absent"
        ) or stability_rechecks.get("stage2_receipt_absent") is False
        _require(adverse_recheck,
                 "curry_handoff_input_stability_failure_without_adverse_recheck")
    if checks["frozen_scope_inputs"] == "passed":
        _require(stability.get("stage2_receipt_absent_before") is True,
                 "curry_handoff_initial_stage2_receipt_present")

    if (value["status"] == "failed" and checkpoint == "saved_input_audit"
            and process_attempted):
        runner_failed = (
            runner.get("process_status") != "completed"
            or runner.get("return_code") != 0
        )
        if runner_failed:
            _require(value.get("diagnostic") == "saved_input_runner_not_successful",
                     "curry_handoff_runner_failure_diagnostic_mismatch")
        else:
            _require(value.get("diagnostic") != "saved_input_runner_not_successful",
                     "curry_handoff_runner_failure_diagnostic_mismatch")

    inputs = value.get("inputs")
    _require(isinstance(inputs, list) and all(
        isinstance(item, dict) and set(item) == {"role", "path", "sha256", "bytes"}
        and isinstance(item.get("role"), str) and item["role"]
        and item["role"] in (
            V3_INPUT_ROLE_ALLOWLIST | spec.required_input_roles | spec.process_input_roles
        )
        and isinstance(item.get("path"), str) and item["path"]
        and "\\" not in item["path"] and ":" not in item["path"]
        and not PurePosixPath(item["path"]).is_absolute()
        and ".." not in PurePosixPath(item["path"]).parts
        and HASH.fullmatch(str(item.get("sha256", ""))) is not None
        and type(item.get("bytes")) is int and item["bytes"] >= 0
        for item in inputs), "curry_handoff_input_records_invalid")
    roles = [item["role"] for item in inputs]
    _require(len(roles) == len(set(roles)), "curry_handoff_input_roles_duplicate")
    role_set = set(roles)
    if process_attempted:
        _require(spec.process_input_roles <= role_set
                 and all(
                     next((row for row in inputs if row["role"] == captured["role"]), None)
                     == captured
                     for captured in capture_input_rows
                  ) and len(capture_input_rows) == len(spec.process_input_roles),
                 "curry_handoff_process_capture_input_binding_invalid")
    else:
        _require(not (spec.process_input_roles & role_set),
                 "curry_handoff_process_capture_input_without_attempt")
    by_path: dict[str, tuple[str, int]] = {}
    for item in inputs:
        identity = (item["sha256"], item["bytes"])
        _require(by_path.setdefault(item["path"], identity) == identity,
                 "curry_handoff_input_path_conflict")

    if checks["saved_input_audit"] != "passed":
        _require(all(item is None for item in stats)
                 and runner.get("saved_input_result") is None,
                 "curry_handoff_failed_statistics_must_remain_unknown")
    else:
        result = runner.get("saved_input_result")
        _require(isinstance(result, dict) and result.get("ledger", {}).get("consumed") == 1
                 and result.get("ledger", {}).get("completed") == 1
                 and result.get("ledger", {}).get("unknown") == 0
                 and stats == (1, 33, 40, 0),
                 "curry_handoff_authenticated_statistics_invalid")

    if value["status"] == "passed":
        required_roles = spec.required_input_roles
        expected_count = spec.input_count
        _require(value.get("failure_checkpoint") is None
                 and all(checks[name] == "passed" for name in spec.checks)
                 and value.get("previous_failed_attempt", {}).get("failure_checkpoint") == "acceptance_delivery"
                 and value.get("previous_failed_attempt", {}).get("diagnostic")
                 == "curry_handoff_acceptance_accounting_invalid"
                 and value.get("previous_v2_failed_attempt", {}).get("failure_checkpoint")
                 == "previous_failed_source"
                 and value.get("previous_v2_failed_attempt", {}).get("diagnostic") == "audit_failed"
                 and v2_final.get("source_identity") is not None
                 and v2_final.get("file_count") == 558
                  and v2_final.get("source_delta") == ALLOWED_V2_SOURCE_DELTA
                 and len([role for role in roles if role.startswith("v3_source_")]) == V3_SOURCE_INPUT_COUNT
                 and len(roles) == expected_count
                 and V3_SOURCE_REQUIRED_ROLES <= set(roles)
                 and required_roles <= set(roles),
                 "curry_handoff_success_sources_incomplete")
        expected_accounting = {
            "certified_historical_consumed": 32, "policy_reserved": 7, "planning_base": 39,
            "new_consumed": 1, "certified_consumed_including_new": 33,
            "planning_total": 40, "unknown": 0,
            "old_confirmation_actual_consumed": None, "actual_all_history_cumulative": None,
        }
        if spec.has_source_layer("previous_v3"):
            expected_accounting["scope"] = "curry-option-verification-v1"
            previous_v3_source = value["previous_v3_failed_source"]
            _require(previous_v3_source.get("source_identity") is not None
                     and previous_v3_source.get("file_count") == 563
                     and previous_v3_source.get("final_source_identity") is not None
                     and previous_v3_source.get("final_file_count") == 564
                     and previous_v3_source.get("source_delta") == V4_ALLOWED_SOURCE_DELTA,
                     "curry_handoff_previous_v3_source_unbound")
        _require(accounting == expected_accounting,
                 "curry_handoff_success_accounting_invalid")
        _require(source_chain.get("native_source_identity") is not None
                 and source_chain.get("final_source_identity") is not None
                 and source_chain.get("native_file_count") == 544
                 and source_chain.get("final_file_count") == 545
                 and source_chain.get("source_delta") == ALLOWED_SOURCE_DELTA
                 and source_chain.get("parent_view_retained") is True,
                 "curry_handoff_dual_timepoint_source_invalid")
        _require(failure.get("stage1_passed") is True and failure.get("stage2_failed") is True
                 and failure.get("acceptance_runner_return_code_claimed") == 2
                 and failure.get("archived_static_return_code") == 2,
                 "curry_handoff_historical_failure_unbound")
        expected_stability = {
            "workspace_stable": "passed", "baseline_stable": "passed",
            "reservation_stable": "passed", "ledger_stable": "passed",
            "runner_build_stable": "passed", "process_diagnostics_stable": "passed",
            "previous_v2_failure_stable": "passed", "v2_final_source_stable": "passed",
            "stage2_receipt_absent_before": True, "stage2_receipt_absent_after": True,
        }
        if spec.has_source_layer("previous_v3"):
            expected_stability["previous_v3_failure_stable"] = "passed"
        if spec.has_source_layer("previous_v4"):
            expected_stability["previous_v4_failure_stable"] = "passed"
            previous_v4_source = value["previous_v4_failed_source"]
            _require(previous_v4_source.get("source_identity") is not None
                     and previous_v4_source.get("file_count") == 568
                     and previous_v4_source.get("final_source_identity") is not None
                     and previous_v4_source.get("final_file_count") == 569
                     and previous_v4_source.get("source_delta") == V5_ALLOWED_SOURCE_DELTA,
                     "curry_handoff_previous_v4_source_unbound")
        _require(value["stability"] == expected_stability,
                 "curry_handoff_success_stability_incomplete")
        _require(repo is not None, "curry_handoff_success_source_root_required")
        try:
            _verify_success_report_inputs_v3(
                value, _absolute(repo), _sources=_sources,
                source_collector=source_collector, _reservation_profile=_reservation_profile,
                _reservation_spec=_reservation_spec, _option_spec=_option_spec,
                _candidate_spec=_candidate_spec, version=version,
            )
        except Exception as error:
            raise ReportSourceReconstructionError(error) from None
    return True


def _validate_report_v1(value: Any) -> bool:
    """Strict local contract check; the published JSON Schema remains independent."""
    required = set(_report_template(None))
    _require(isinstance(value, dict) and set(value) == required,
             "curry_handoff_report_fields_invalid")
    _require(type(value.get("schema_version")) is int and value["schema_version"] == 1,
             "curry_handoff_report_version_invalid")
    _require(value.get("kind") == "curry_ledger_handoff_audit_v1",
             "curry_handoff_report_kind_invalid")
    _require(value.get("status") in ("passed", "failed", "incomplete"),
             "curry_handoff_report_status_invalid")
    _require(value.get("failure_checkpoint") is None or value["failure_checkpoint"] in CHECK_NAMES,
             "curry_handoff_report_checkpoint_invalid")
    _require(type(value.get("native_calls")) is int and value["native_calls"] == 0
             and value.get("execution_ready") is False,
             "curry_handoff_zero_call_contract_invalid")
    _require(all(value.get(flag) is False for flag in QUALIFICATIONS),
             "curry_handoff_qualification_must_remain_false")
    _require(value.get("anchors") == {
        "acceptance_sha256": ACCEPTANCE_SHA256,
        "delivery_sha256": DELIVERY_SHA256,
    }, "curry_handoff_anchor_set_invalid")
    _require(value.get("checks") == {
        name: value["checks"].get(name) for name in CHECK_NAMES
    } and all(state in ("not_run", "passed", "failed")
              for state in value["checks"].values()),
             "curry_handoff_check_set_invalid")
    accounting = value.get("accounting")
    _require(isinstance(accounting, dict) and set(accounting) == {
        "certified_historical_consumed", "policy_reserved", "planning_base",
        "new_consumed", "certified_consumed_including_new", "planning_total",
        "unknown", "old_confirmation_actual_consumed", "actual_all_history_cumulative",
    }, "curry_handoff_accounting_fields_invalid")
    _require(accounting.get("certified_historical_consumed") == 32
             and accounting.get("policy_reserved") == 7
             and accounting.get("planning_base") == 39
             and accounting.get("old_confirmation_actual_consumed") is None
             and accounting.get("actual_all_history_cumulative") is None,
             "curry_handoff_accounting_basis_invalid")
    for key in ("new_consumed", "certified_consumed_including_new", "planning_total", "unknown"):
        item = accounting.get(key)
        _require(item is None or (type(item) is int and item >= 0),
                 "curry_handoff_accounting_stat_invalid")
    runner = value.get("runner")
    _require(isinstance(runner, dict) and runner.get("role") == RUNNER_ROLE
             and runner.get("mode") == RUNNER_MODE
             and isinstance(runner.get("trace"), list),
             "curry_handoff_runner_fields_invalid")
    stability = value.get("stability")
    _require(isinstance(stability, dict) and set(stability) == {
        "workspace_stable", "baseline_stable", "reservation_stable", "ledger_stable",
        "runner_build_stable",
        "stage2_receipt_absent_before", "stage2_receipt_absent_after",
    }, "curry_handoff_stability_fields_invalid")
    _require(isinstance(value.get("inputs"), list)
             and all(isinstance(item, dict) and set(item) == {"role", "path", "sha256", "bytes"}
                     and isinstance(item["role"], str)
                     and isinstance(item["path"], str)
                     and HASH.fullmatch(str(item["sha256"]))
                     and type(item["bytes"]) is int and item["bytes"] >= 0
                     for item in value["inputs"]),
             "curry_handoff_input_records_invalid")
    states = [value["checks"][name] for name in CHECK_NAMES]
    if value["status"] == "failed":
        checkpoint = value["failure_checkpoint"]
        _require(checkpoint in CHECK_NAMES,
                 "curry_handoff_failed_checkpoint_missing")
        index = CHECK_NAMES.index(checkpoint)
        _require(states[:index] == ["passed"] * index
                 and states[index] == "failed"
                 and states[index + 1:] == ["not_run"] * (len(states) - index - 1),
                 "curry_handoff_failed_checkpoint_checks_inconsistent")
    elif value["status"] == "incomplete":
        _require(all(state != "failed" for state in states),
                 "curry_handoff_incomplete_contains_failed_check")
        seen_not_run = False
        for state in states:
            if state == "not_run":
                seen_not_run = True
            elif seen_not_run:
                raise ValueError("curry_handoff_incomplete_check_order_invalid")
    stats = (accounting["new_consumed"],
             accounting["certified_consumed_including_new"],
             accounting["planning_total"], accounting["unknown"])
    _require((all(item is None for item in stats)
              or all(type(item) is int and item >= 0 for item in stats)),
             "curry_handoff_accounting_stats_partially_known")
    if value["checks"]["saved_input_audit"] != "passed":
        _require(all(item is None for item in stats),
                 "curry_handoff_accounting_without_saved_input_result")
    else:
        runner_result = runner.get("saved_input_result")
        _require(isinstance(runner_result, dict)
                 and stats == (1, 33, 40, 0)
                 and runner_result.get("ledger", {}).get("consumed") == 1
                 and runner_result.get("ledger", {}).get("unknown") == 0,
                 "curry_handoff_accounting_saved_input_mismatch")
    if value["status"] == "passed":
        _require(value["failure_checkpoint"] is None
                 and all(state == "passed" for state in value["checks"].values()),
                 "curry_handoff_success_checks_incomplete")
        _require(accounting == {
            "certified_historical_consumed": 32,
            "policy_reserved": 7,
            "planning_base": 39,
            "new_consumed": 1,
            "certified_consumed_including_new": 33,
            "planning_total": 40,
            "unknown": 0,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        }, "curry_handoff_success_accounting_invalid")
        baseline = value.get("baseline")
        _require(isinstance(baseline, dict)
                 and all(HASH.fullmatch(str(baseline.get(key, ""))) is not None for key in (
                     "acceptance_sha256", "delivery_sha256", "context", "manifest_sha256",
                     "prepared_sha256", "stage1_receipt_sha256", "stage2_input_sha256",
                     "stage2_request_sha256",
                 )), "curry_handoff_success_baseline_incomplete")
        _require(value["historical_failure"].get("stage1_passed") is True
                 and value["historical_failure"].get("stage2_failed") is True
                 and value["historical_failure"].get("stage2_diagnostic")
                 == "runner_output_invalid_or_nonzero",
                 "curry_handoff_success_history_incomplete")
        runner = value["runner"]
        _require(runner.get("return_code") == 0
                 and runner.get("process_status") == "completed"
                 and all(HASH.fullmatch(str(runner.get(key, ""))) is not None for key in (
                     "sha256", "build_record_sha256", "build_record_identity",
                     "source_identity", "diagnostic_sha256", "stdout_sha256", "stderr_sha256",
                 ))
                 and type(runner.get("source_file_count")) is int
                 and type(runner.get("stdout_bytes")) is int
                 and type(runner.get("stderr_bytes")) is int,
                 "curry_handoff_success_runner_incomplete")
        result = runner.get("saved_input_result")
        _require(isinstance(result, dict), "curry_handoff_success_result_missing")
        _validate_saved_input_output({
            **result, "native_calls": 0, "execution_ready": False,
        }, context=baseline["context"], identity_sha256=result.get("identity_sha256"))
        _require(result.get("ledger", {}).get("consumed") == accounting["new_consumed"],
                 "curry_handoff_success_result_accounting_mismatch")
        _require(_is_complete_trace_summary(runner.get("trace")),
                 "curry_handoff_success_trace_incomplete")
        _require(value["stability"] == {
            "workspace_stable": "passed", "baseline_stable": "passed",
            "reservation_stable": "passed", "ledger_stable": "passed",
            "runner_build_stable": "passed",
            "stage2_receipt_absent_before": True,
            "stage2_receipt_absent_after": True,
        }, "curry_handoff_success_stability_incomplete")
    return True


def _validate_report_v2(
    value: Any, *, _sources: Any | None = None, repo: Path | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
) -> bool:
    """Validate V2 structure and, for a success, recheck its pinned source files."""
    required = set(_report_template(None, 2))
    _require(isinstance(value, dict) and set(value) == required,
             "curry_handoff_report_fields_invalid")
    _require(type(value.get("schema_version")) is int and value["schema_version"] == 2
             and value.get("kind") == AUDIT_VERSIONS[2].kind,
             "curry_handoff_report_version_invalid")
    _require(value.get("status") in ("passed", "failed", "incomplete"),
             "curry_handoff_report_status_invalid")
    _require(value.get("failure_checkpoint") is None
             or value["failure_checkpoint"] in V2_CHECK_NAMES,
             "curry_handoff_report_checkpoint_invalid")
    _require(type(value.get("native_calls")) is int and value["native_calls"] == 0
             and value.get("execution_ready") is False,
             "curry_handoff_zero_call_contract_invalid")
    _require(all(value.get(flag) is False for flag in QUALIFICATIONS),
             "curry_handoff_qualification_must_remain_false")
    expected_acceptance = ACCEPTANCE_SHA256
    expected_delivery = DELIVERY_SHA256
    if _sources is not None:
        baseline_sources = _sources.child("baseline")
        expected_acceptance = baseline_sources.file_sha256_role("baseline_acceptance")
        expected_delivery = baseline_sources.file_sha256_role("baseline_delivery")
    _require(value.get("anchors") == {
        "acceptance_sha256": expected_acceptance,
        "delivery_sha256": expected_delivery,
    }, "curry_handoff_anchor_set_invalid")
    checks = value.get("checks")
    _require(isinstance(checks, dict) and set(checks) == set(V2_CHECK_NAMES)
             and all(state in ("not_run", "passed", "failed") for state in checks.values()),
             "curry_handoff_check_set_invalid")
    if value["status"] == "failed":
        checkpoint = value.get("failure_checkpoint")
        _require(checkpoint in V2_CHECK_NAMES, "curry_handoff_failed_checkpoint_missing")
        index = V2_CHECK_NAMES.index(checkpoint)
        _require([checks[name] for name in V2_CHECK_NAMES[:index]] == ["passed"] * index
                 and checks[checkpoint] == "failed"
                 and all(checks[name] == "not_run" for name in V2_CHECK_NAMES[index + 1:]),
                 "curry_handoff_failed_checkpoint_checks_inconsistent")
    elif value["status"] == "incomplete":
        _require(value.get("failure_checkpoint") is None,
                 "curry_handoff_incomplete_checkpoint_must_be_null")
        seen_not_run = False
        for name in V2_CHECK_NAMES:
            state = checks[name]
            _require(state != "failed", "curry_handoff_incomplete_contains_failed_check")
            if state == "not_run":
                seen_not_run = True
            else:
                _require(not seen_not_run, "curry_handoff_incomplete_check_order_invalid")

    accounting = value.get("accounting")
    _require(isinstance(accounting, dict) and set(accounting) == {
        "certified_historical_consumed", "policy_reserved", "planning_base",
        "new_consumed", "certified_consumed_including_new", "planning_total",
        "unknown", "old_confirmation_actual_consumed", "actual_all_history_cumulative",
    }, "curry_handoff_accounting_fields_invalid")
    _require(accounting.get("certified_historical_consumed") == 32
             and accounting.get("policy_reserved") == 7
             and accounting.get("planning_base") == 39
             and accounting.get("old_confirmation_actual_consumed") is None
             and accounting.get("actual_all_history_cumulative") is None,
             "curry_handoff_accounting_basis_invalid")
    stats = tuple(accounting.get(key) for key in (
        "new_consumed", "certified_consumed_including_new", "planning_total", "unknown",
    ))
    _require(all(item is None or (type(item) is int and item >= 0) for item in stats)
             and (all(item is None for item in stats)
                  or all(type(item) is int for item in stats)),
             "curry_handoff_accounting_stats_partially_known")

    runner = value.get("runner")
    runner_template = _report_template(None, 2)["runner"]
    _require(isinstance(runner, dict) and set(runner) == set(runner_template)
             and runner.get("role") == RUNNER_ROLE
             and runner.get("mode") == RUNNER_MODE,
             "curry_handoff_runner_fields_invalid")
    capture = runner.get("process_capture")
    _require(isinstance(capture, dict) and set(capture) == {
        "metadata_path", "metadata_sha256", "stdout_path", "stderr_path",
    }, "curry_handoff_process_capture_fields_invalid")
    capture_values = tuple(capture.get(key) for key in (
        "metadata_path", "metadata_sha256", "stdout_path", "stderr_path",
    ))
    if all(item is None for item in capture_values):
        _require(all(runner.get(key) is None for key in (
            "return_code", "process_status", "diagnostic_sha256", "stdout_sha256",
            "stdout_bytes", "stderr_sha256", "stderr_bytes",
        )), "curry_handoff_process_capture_missing")
    else:
        _require(all(isinstance(item, str) and item for item in capture_values)
                 and HASH.fullmatch(str(capture["metadata_sha256"])) is not None,
                 "curry_handoff_process_capture_fields_invalid")
        for key in ("metadata_path", "stdout_path", "stderr_path"):
            relative = PurePosixPath(capture[key])
            _require(not relative.is_absolute() and ".." not in relative.parts
                     and len(relative.parts) == 2
                     and relative.parts[0] == "process-diagnostics"
                     and relative.as_posix() == capture[key],
                     "curry_handoff_process_capture_path_invalid")
        _require(runner.get("process_status") in ("completed", "timeout", "launch_failed")
                 and (runner.get("return_code") is None
                      or type(runner.get("return_code")) is int)
                 and HASH.fullmatch(str(runner.get("diagnostic_sha256", ""))) is not None
                 and HASH.fullmatch(str(runner.get("stdout_sha256", ""))) is not None
                 and HASH.fullmatch(str(runner.get("stderr_sha256", ""))) is not None
                 and type(runner.get("stdout_bytes")) is int
                 and runner["stdout_bytes"] >= 0
                 and type(runner.get("stderr_bytes")) is int
                 and runner["stderr_bytes"] >= 0,
                 "curry_handoff_process_capture_summary_invalid")
    stability = value.get("stability")
    _require(isinstance(stability, dict) and set(stability) == set(
        _report_template(None, 2)["stability"]
    ), "curry_handoff_stability_fields_invalid")
    for name in (
        "workspace_stable", "baseline_stable", "reservation_stable", "ledger_stable",
        "runner_build_stable", "process_diagnostics_stable",
    ):
        _require(stability.get(name) in ("not_checked", "passed", "failed"),
                 "curry_handoff_stability_summary_invalid")
    for name in ("stage2_receipt_absent_before", "stage2_receipt_absent_after"):
        _require(stability.get(name) is None or type(stability[name]) is bool,
                 "curry_handoff_stability_summary_invalid")
    if repo is not None and not all(item is None for item in capture_values):
        _verify_process_capture(value, _absolute(repo), require_success=False)

    inputs = value.get("inputs")
    _require(isinstance(inputs, list) and all(
        isinstance(item, dict) and set(item) == {"role", "path", "sha256", "bytes"}
        and isinstance(item["role"], str) and item["role"]
        and isinstance(item["path"], str) and item["path"]
        and "\\" not in item["path"] and ":" not in item["path"]
        and not PurePosixPath(item["path"]).is_absolute()
        and ".." not in PurePosixPath(item["path"]).parts
        and bool(PurePosixPath(item["path"]).parts)
        and PurePosixPath(item["path"]).as_posix() == item["path"]
        and HASH.fullmatch(str(item["sha256"]))
        and type(item["bytes"]) is int and item["bytes"] >= 0
        for item in inputs
    ), "curry_handoff_input_records_invalid")
    roles = [item["role"] for item in inputs]
    _require(len(roles) == len(set(roles)), "curry_handoff_input_roles_duplicate")
    by_path: dict[str, tuple[str, int]] = {}
    for item in inputs:
        value_at_path = (item["sha256"], item["bytes"])
        previous = by_path.setdefault(item["path"], value_at_path)
        _require(previous == value_at_path, "curry_handoff_input_path_conflict")
    input_by_role = {item["role"]: item for item in inputs}

    def require_input_hash(role: str, expected: Any) -> None:
        item = input_by_role.get(role)
        _require(isinstance(item, dict) and HASH.fullmatch(str(expected or ""))
                 and item["sha256"] == expected,
                 "curry_handoff_input_binding_mismatch")

    previous = value.get("previous_failed_attempt")
    expected_previous_hash = (
        _sources.child("previous_failed_attempt").file_sha256_role("previous_v1_report")
        if _sources is not None else PREVIOUS_V1_REPORT_SHA256
    )
    _require(isinstance(previous, dict) and set(previous) == set(
        _report_template(None, 2)["previous_failed_attempt"]
    ) and previous.get("report_sha256") == expected_previous_hash,
             "curry_handoff_previous_failure_fields_invalid")
    _require(previous.get("status") in (None, "failed")
             and previous.get("failure_checkpoint") in (None, "acceptance_delivery")
             and previous.get("diagnostic") in (
                 None, "curry_handoff_acceptance_accounting_invalid",
             )
             and all(previous.get(key) is None or HASH.fullmatch(str(previous[key]))
                     for key in (
                         "runner_sha256", "build_record_sha256", "source_archive_sha256",
                         "source_file_list_sha256",
                     )), "curry_handoff_previous_failure_fields_invalid")
    source_chain = value.get("dual_timepoint_sources")
    _require(isinstance(source_chain, dict) and set(source_chain) == set(
        _report_template(None, 2)["dual_timepoint_sources"]
    ) and source_chain.get("parent_lock_path")
             == "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
             and source_chain.get("historical_actual_exit_code") is None,
             "curry_handoff_dual_timepoint_fields_invalid")
    for key in ("native_source_identity", "final_source_identity", "parent_lock_source_sha256"):
        _require(source_chain.get(key) is None or HASH.fullmatch(str(source_chain[key])) is not None,
                 "curry_handoff_dual_timepoint_hash_invalid")
    for key in ("native_file_count", "final_file_count"):
        _require(source_chain.get(key) is None or (
            type(source_chain[key]) is int and source_chain[key] >= 0
        ), "curry_handoff_dual_timepoint_count_invalid")
    _require(source_chain.get("source_delta") is None
             or source_chain.get("source_delta") == ALLOWED_SOURCE_DELTA,
             "curry_handoff_dual_timepoint_delta_invalid")
    failure = value.get("historical_failure")
    _require(isinstance(failure, dict) and set(failure) == set(
        _report_template(None, 2)["historical_failure"]
    ) and failure.get("scope") == "curry-option-verification-v1"
             and failure.get("historical_actual_exit_code") is None
             and failure.get("historical_exit_code_certified") is False
             and failure.get("old_failure_rewritten") is False
             and (failure.get("acceptance_runner_return_code_claimed") is None
                  or failure.get("acceptance_runner_return_code_claimed") == 2)
             and (failure.get("archived_static_return_code") is None
                  or failure.get("archived_static_return_code") == 2),
             "curry_handoff_historical_failure_fields_invalid")
    rechecks = value.get("stability_rechecks")
    _require(isinstance(rechecks, dict) and set(rechecks) == set(
        _report_template(None, 2)["stability_rechecks"]
    ) and all(rechecks[name] in (
        "not_collected", "consistent", "changed", "recheck_failed",
    ) for name in (
        "workspace", "previous_failure_tree", "baseline_tree", "reservation_tree",
        "ledger", "runner_build", "process_diagnostics",
    )) and (rechecks["stage2_receipt_absent"] is None
            or type(rechecks["stage2_receipt_absent"]) is bool),
             "curry_handoff_stability_rechecks_invalid")

    if value["status"] == "passed":
        _require(value.get("failure_checkpoint") is None
                 and all(checks[name] == "passed" for name in V2_CHECK_NAMES),
                 "curry_handoff_success_checks_incomplete")
        v3_roles = {role for role in roles if role.startswith("v3_source_")}
        _require(V2_REQUIRED_INPUT_ROLES <= set(roles)
                 and len(v3_roles) == V3_SOURCE_INPUT_COUNT
                 and V3_SOURCE_REQUIRED_ROLES <= v3_roles,
                 "curry_handoff_success_inputs_incomplete")
        bindings = {
            "acceptance": value["anchors"]["acceptance_sha256"],
            "delivery": value["anchors"]["delivery_sha256"],
            "previous_v1_report": previous["report_sha256"],
            "previous_v1_build_record": previous["build_record_sha256"],
            "previous_v1_runner": previous["runner_sha256"],
            "previous_v1_source_archive": previous["source_archive_sha256"],
            "previous_v1_source_file_list": previous["source_file_list_sha256"],
            "manifest": value["baseline"]["manifest_sha256"],
            "prepared": value["baseline"]["prepared_sha256"],
            "stage1_receipt": value["baseline"]["stage1_receipt_sha256"],
            "stage2_input": value["baseline"]["stage2_input_sha256"],
            "stage2_request": value["baseline"]["stage2_request_sha256"],
            "new_runner": value["runner"]["sha256"],
            "new_build_record": value["runner"]["build_record_sha256"],
        }
        for role, expected in bindings.items():
            require_input_hash(role, expected)
        _require(accounting == {
            "certified_historical_consumed": 32, "policy_reserved": 7,
            "planning_base": 39, "new_consumed": 1,
            "certified_consumed_including_new": 33, "planning_total": 40,
            "unknown": 0, "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        }, "curry_handoff_success_accounting_invalid")
        _require(previous.get("status") == "failed"
                 and previous.get("failure_checkpoint") == "acceptance_delivery"
                 and previous.get("diagnostic") == "curry_handoff_acceptance_accounting_invalid"
                 and all(HASH.fullmatch(str(previous.get(key, ""))) for key in (
                     "report_sha256", "runner_sha256", "build_record_sha256",
                     "source_archive_sha256", "source_file_list_sha256",
                 )), "curry_handoff_previous_failure_unbound")
        _require(source_chain.get("native_source_identity")
                 and source_chain.get("final_source_identity")
                 and type(source_chain.get("native_file_count")) is int
                 and type(source_chain.get("final_file_count")) is int
                 and source_chain.get("source_delta") == ALLOWED_SOURCE_DELTA
                 and source_chain.get("parent_view_retained") is True,
                 "curry_handoff_dual_timepoint_source_invalid")
        _require(failure.get("stage1_passed") is True
                 and failure.get("stage2_failed") is True
                 and failure.get("stage2_diagnostic") == "runner_output_invalid_or_nonzero"
                 and failure.get("acceptance_runner_return_code_claimed") == 2
                 and failure.get("archived_static_return_code") == 2,
                 "curry_handoff_historical_failure_unbound")
        _require(all(rechecks[name] == "consistent" for name in (
            "workspace", "previous_failure_tree", "baseline_tree", "reservation_tree",
            "ledger", "runner_build", "process_diagnostics",
        )) and rechecks["stage2_receipt_absent"] is True,
                 "curry_handoff_success_stability_incomplete")
        _require(value["stability"].get("process_diagnostics_stable") == "passed",
                 "curry_handoff_success_stability_incomplete")
        _require(repo is not None, "curry_handoff_success_source_root_required")
        try:
            _verify_success_report_inputs(
                value, _absolute(repo), _sources=_sources,
                source_collector=source_collector,
                _reservation_profile=_reservation_profile,
                _reservation_spec=_reservation_spec, _option_spec=_option_spec,
                _candidate_spec=_candidate_spec,
            )
        except Exception as error:
            raise ReportSourceReconstructionError(error) from None
        result = value.get("runner", {}).get("saved_input_result")
        _require(isinstance(result, dict)
                 and result.get("ledger", {}).get("consumed") == 1
                 and result.get("ledger", {}).get("completed") == 1
                 and result.get("ledger", {}).get("unknown") == 0
                 and stats == (1, 33, 40, 0),
                 "curry_handoff_accounting_saved_input_mismatch")
        _require(value["stability"].get("stage2_receipt_absent_before") is True
                 and value["stability"].get("stage2_receipt_absent_after") is True,
                 "curry_handoff_success_stability_incomplete")
    elif value["checks"]["saved_input_audit"] != "passed":
        _require(all(item is None for item in stats),
                 "curry_handoff_failed_statistics_must_remain_unknown")
    else:
        result = value.get("runner", {}).get("saved_input_result")
        _require(isinstance(result, dict)
                 and result.get("ledger", {}).get("consumed") == accounting["new_consumed"]
                 and result.get("ledger", {}).get("unknown") == accounting["unknown"]
                 and stats == (1, 33, 40, 0),
                 "curry_handoff_authenticated_statistics_invalid")
    return True


def _verify_success_report_inputs(
    report: dict[str, Any], repo: Path, *, _sources: Any | None,
    source_collector: Callable[[Path], dict] = stable_source,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
) -> None:
    """Rebuild each successful V2 input binding from the fixed source tree.

    The JSON schema and ``validate_report`` without ``repo`` validate structure
    only. A passed report is authenticated here, at publication time, against
    fixed paths and bytes; serialized provenance claims alone are insufficient.
    """
    previous = _verify_previous_failed_attempt(repo, _sources=_sources)
    baseline = repo / BASELINE_RELATIVE
    acceptance, delivery, acceptance_raw, delivery_raw = _verify_acceptance_delivery(
        baseline, _sources=_sources,
    )
    dual = _verify_final_build_chain(
        repo, baseline, acceptance, delivery, _sources=_sources,
    )
    # Reuse the same fixed-scope semantic gate used before normal execution.
    # This binds manifest/prepared hashes back to acceptance.preflight and
    # rechecks the stage-1 parent, stage-2 derivation, seal, and absent receipt.
    _snapshot_fixed_sources(
        repo, baseline, mark=lambda _name, _complete=False: None,
        _sources=_sources, source_collector=source_collector,
        _reservation_profile=_reservation_profile,
        _reservation_spec=_reservation_spec, _option_spec=_option_spec,
        _candidate_spec=_candidate_spec,
        _preverified_baseline=(acceptance, delivery, acceptance_raw, delivery_raw),
    )
    expected: list[dict[str, Any]] = [*previous["inputs"], *dual["inputs"]]
    expected.extend((
        _record_input(repo, "acceptance", baseline / ACCEPTANCE_RELATIVE, acceptance_raw),
        _record_input(repo, "delivery", baseline / DELIVERY_RELATIVE, delivery_raw),
    ))

    from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE

    _, option_paths = _fixed_option_paths(repo)
    research = option_paths["research"]
    fixed_roles = {
        "manifest": research / "manifest.json",
        "prepared": research / "prepared.json",
        "stage1_receipt": research / "stage-1.json",
        "stage2_request": research / "stage-2-request.json",
        "stage2_input": research / "stage-2-input.json",
        "stage2_seal": research / "stage-2-input-seal.json",
        "stage2_report": research / "stage-2-report.json",
        "charge_ledger": research / "calls.jsonl",
    }
    for role, path in fixed_roles.items():
        safe = safe_path(path)
        raw = safe.read_bytes()
        expected.append(_record_input(repo, role, safe, raw))
    expected.extend(_v3_source_input_records(
        repo, repo / OPTION_VERIFICATION_SCOPE.baseline_root,
    ))

    runner = repo / V2_OUTPUT_RELATIVE / RUNNER_RELATIVE
    build_record = repo / V2_OUTPUT_RELATIVE / BUILD_RECORD_RELATIVE
    build_raw, _ = _read(build_record)
    build = strict_json(build_raw)
    source = build.get("source_before") if isinstance(build, dict) else None
    _require(isinstance(source, dict)
             and source == build.get("source_after")
             and _source_summary(source) == report.get("tool_identity")
             and source.get("identity") == report.get("runner", {}).get("source_identity")
             and len(source.get("files", {})) == report.get("runner", {}).get("source_file_count"),
             "curry_handoff_success_build_source_binding_invalid")
    runner_build = _verify_runner_build(runner, build_record, repo, source)
    role_map = {
        "runner": "new_runner", "build_record": "new_build_record",
        "source_archive": "new_source_archive", "source_file_list": "new_source_file_list",
    }
    expected.extend({**item, "role": role_map[item["role"]]}
                    for item in runner_build["inputs"])
    expected.extend(_verify_process_capture(report, repo, require_success=True))

    _require(report.get("previous_failed_attempt") == previous["record"],
             "curry_handoff_success_previous_failure_claim_mismatch")
    expected_dual = dict(_report_template(None, 2)["dual_timepoint_sources"])
    expected_dual.update({
        key: value for key, value in dual["record"].items()
        if key in expected_dual
    })
    _require(report.get("dual_timepoint_sources") == expected_dual,
             "curry_handoff_success_dual_timepoint_claim_mismatch")
    expected_historical_failure = {
        "scope": "curry-option-verification-v1",
        "stage1_passed": True,
        "stage2_failed": True,
        "stage2_diagnostic": "runner_output_invalid_or_nonzero",
        "historical_exit_code_certified": False,
        "old_failure_rewritten": False,
        "acceptance_runner_return_code_claimed": acceptance[
            "native_result"]["stage_2"]["runner_return_code"],
        "archived_static_return_code": dual["record"]["archived_static_return_code"],
        "historical_actual_exit_code": None,
    }
    _require(report.get("historical_failure") == expected_historical_failure,
             "curry_handoff_success_historical_claim_mismatch")

    actual_rows = report["inputs"]
    expected_by_role = {item["role"]: item for item in expected}
    actual_by_role = {item["role"]: item for item in actual_rows}
    _require(len(expected_by_role) == len(expected)
             and len(actual_by_role) == len(actual_rows)
             and set(actual_by_role) == set(expected_by_role),
             "curry_handoff_success_input_role_binding_invalid")
    from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE
    from ygo_eval.native_curry_option_validation import (
        _curry_evidence_hash, _snapshot_curry_evidence,
    )

    directory_role = "v3_source_tenki_validation_directory_evidence"
    for role, expected_record in expected_by_role.items():
        actual = actual_by_role[role]
        _require(actual == expected_record,
                 "curry_handoff_success_input_binding_mismatch")
        relative = PurePosixPath(expected_record["path"])
        path = repo.joinpath(*relative.parts)
        if role == directory_role:
            _require(relative == PurePosixPath(V3_TENKI_EVIDENCE_RELATIVE.as_posix())
                     and expected_record["bytes"] == 0,
                     "curry_handoff_success_directory_role_invalid")
            directory = safe_path(path, file=False)
            found = _curry_evidence_hash(_snapshot_curry_evidence(directory))
            size = 0
        else:
            file = safe_path(path)
            raw = file.read_bytes()
            found = _sha(raw)
            size = len(raw)
        _require(found == expected_record["sha256"]
                 and size == expected_record["bytes"],
                 "curry_handoff_success_input_content_mismatch")


def _verify_success_report_inputs_v3(
    report: dict[str, Any], repo: Path, *, _sources: Any | None,
    source_collector: Callable[[Path], dict] = stable_source,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    version: int = 3,
) -> None:
    """Reconstruct every successful V3/V4 input from its fixed source roots."""
    version_spec = _version_spec(version)
    v1 = _verify_v1_audit_source_v3(repo, _sources=_sources)
    v2 = _verify_v2_audit_source_v3(repo, _sources=_sources)
    v2_final = _verify_v2_final_source_v3(repo, _sources=_sources)
    baseline = repo / BASELINE_RELATIVE
    acceptance, delivery, acceptance_raw, delivery_raw = _verify_acceptance_delivery(
        baseline, _sources=_sources,
    )
    dual = _verify_final_build_chain(
        repo, baseline, acceptance, delivery, _sources=_sources,
    )
    snapshot = _snapshot_fixed_sources(
        repo, baseline, mark=lambda _name, _complete=False: None,
        _sources=_sources, source_collector=source_collector,
        _reservation_profile=_reservation_profile,
        _reservation_spec=_reservation_spec, _option_spec=_option_spec,
        _candidate_spec=_candidate_spec,
        stdout_contract=_version_spec(version).stdout_contract,
        _preverified_baseline=(acceptance, delivery, acceptance_raw, delivery_raw),
    )
    expected: list[dict[str, Any]] = [
        *v1["inputs"], *v2["inputs"], *v2_final["inputs"], *dual["inputs"],
        *snapshot["inputs"],
    ]

    output_root = repo / _version_spec(version).output_root
    runner = output_root / RUNNER_RELATIVE
    build_record = output_root / BUILD_RECORD_RELATIVE
    build_raw, _ = _read(build_record)
    build = strict_json(build_raw)
    source = build.get("source_before") if isinstance(build, dict) else None
    _require(isinstance(source, dict) and source == build.get("source_after")
             and _source_summary(source) == report.get("tool_identity")
             and source.get("identity") == report.get("runner", {}).get("source_identity")
             and len(source.get("files", {})) == report.get("runner", {}).get("source_file_count"),
             "curry_handoff_success_build_source_binding_invalid")
    runner_build = _verify_runner_build(runner, build_record, repo, source)
    role_map = {
        "runner": "new_runner", "build_record": "new_build_record",
        "source_archive": "new_source_archive", "source_file_list": "new_source_file_list",
    }
    expected.extend({**item, "role": role_map[item["role"]]}
                    for item in runner_build["inputs"])
    if version_spec.captures_process_diagnostics:
        expected.extend(_verify_process_capture(
            report, repo, require_success=True, output_root=output_root,
        ))

    _require(report.get("previous_failed_attempt") == v1["record"],
             "curry_handoff_v3_previous_v1_claim_mismatch")
    _require(report.get("previous_v2_failed_attempt") == v2["record"],
             "curry_handoff_v3_previous_v2_claim_mismatch")
    _require(report.get("v2_final_source") == v2_final["record"],
             "curry_handoff_v3_final_source_claim_mismatch")
    if version_spec.has_source_layer("previous_v3"):
        previous_v3 = _verify_previous_v3_failed_source(repo, _sources=_sources)
        _require(report.get("previous_v3_failed_source") == previous_v3["record"],
                 "curry_handoff_v4_previous_v3_claim_mismatch")
        expected.extend(previous_v3["inputs"])
    if version_spec.has_source_layer("previous_v4"):
        previous_v4 = _verify_previous_v4_failed_source(
            repo, version_spec=version_spec, _sources=_sources,
        )
        _require(report.get("previous_v4_failed_source") == previous_v4["record"],
                 "curry_handoff_v5_previous_v4_claim_mismatch")
        expected.extend(previous_v4["inputs"])
    expected_dual = dict(_report_template(None, version)["dual_timepoint_sources"])
    expected_dual.update({
        key: value for key, value in dual["record"].items()
        if key in expected_dual
    })
    _require(report.get("dual_timepoint_sources") == expected_dual,
             "curry_handoff_v3_dual_timepoint_claim_mismatch")
    _require(report.get("baseline", {}).get("acceptance_sha256") == _sha(acceptance_raw)
             and report.get("baseline", {}).get("delivery_sha256") == _sha(delivery_raw)
             and report.get("baseline", {}).get("manifest_sha256") == snapshot["report_binding"]["manifest_sha256"]
             and report.get("baseline", {}).get("prepared_sha256") == snapshot["report_binding"]["prepared_sha256"]
             and report.get("baseline", {}).get("stage2_input_sha256") == snapshot["report_binding"]["stage2_input_sha256"],
             "curry_handoff_v3_baseline_claim_mismatch")
    expected_failure = {
        "scope": "curry-option-verification-v1",
        "stage1_passed": True,
        "stage2_failed": True,
        "stage2_diagnostic": "runner_output_invalid_or_nonzero",
        "historical_exit_code_certified": False,
        "old_failure_rewritten": False,
        "acceptance_runner_return_code_claimed": acceptance[
            "native_result"]["stage_2"]["runner_return_code"],
        "archived_static_return_code": dual["record"]["archived_static_return_code"],
        "historical_actual_exit_code": None,
    }
    _require(report.get("historical_failure") == expected_failure,
             "curry_handoff_v3_historical_failure_claim_mismatch")

    actual_rows = report.get("inputs")
    _require(isinstance(actual_rows, list), "curry_handoff_input_records_invalid")
    expected_by_role = {item["role"]: item for item in expected}
    actual_by_role = {item.get("role"): item for item in actual_rows if isinstance(item, dict)}
    _require(len(expected_by_role) == len(expected)
             and len(actual_by_role) == len(actual_rows)
             and set(actual_by_role) == set(expected_by_role)
             and version_spec.required_input_roles <= set(actual_by_role)
             and version_spec.input_count is not None
             and len(actual_by_role) == version_spec.input_count,
             "curry_handoff_v3_input_role_binding_invalid")
    for role, expected_record in expected_by_role.items():
        _require(actual_by_role[role] == expected_record,
                 "curry_handoff_v3_input_binding_mismatch")
        relative = PurePosixPath(expected_record["path"])
        path = repo.joinpath(*relative.parts)
        if role == "v3_source_tenki_validation_directory_evidence":
            from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE
            from ygo_eval.native_curry_option_validation import (
                _curry_evidence_hash, _snapshot_curry_evidence,
            )
            _require(relative == PurePosixPath(V3_TENKI_EVIDENCE_RELATIVE.as_posix())
                     and expected_record["bytes"] == 0,
                     "curry_handoff_v3_directory_role_invalid")
            found = _curry_evidence_hash(_snapshot_curry_evidence(safe_path(path, file=False)))
            size = 0
        else:
            raw = safe_path(path).read_bytes()
            found, size = _sha(raw), len(raw)
        _require(found == expected_record["sha256"] and size == expected_record["bytes"],
                 "curry_handoff_v3_input_content_mismatch")


def _is_complete_trace_summary(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != len(TRACE_EVENTS):
        return False
    for item, (phase, event) in zip(value, TRACE_EVENTS):
        if not isinstance(item, dict) or item.get("phase") != phase or item.get("event") != event:
            return False
        if event == "start" and set(item) != {"phase", "event"}:
            return False
        if event == "end" and (
            set(item) != {"phase", "event", "elapsed_ns"}
            or type(item.get("elapsed_ns")) is not int
            or item["elapsed_ns"] < 0
        ):
            return False
    return True


def _record_input(repo: Path, role: str, path: Path, raw: bytes) -> dict:
    absolute = _absolute(path)
    try:
        relative = absolute.relative_to(repo).as_posix()
    except ValueError:
        raise ValueError("curry_handoff_input_outside_repository") from None
    return {"role": role, "path": relative, "sha256": _sha(raw), "bytes": len(raw)}


def _record_directory_input(repo: Path, role: str, path: Path, digest: str) -> dict:
    absolute = _absolute(path)
    try:
        relative = absolute.relative_to(repo).as_posix()
    except ValueError:
        raise ValueError("curry_handoff_input_outside_repository") from None
    return {"role": role, "path": relative, "sha256": digest, "bytes": 0}


def _v3_source_input_records(repo: Path, reservation_root: Path) -> list[dict[str, Any]]:
    """Expand the authenticated V3 report's exact 100 pinned inputs."""
    from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE
    from ygo_eval.native_curry_option_validation import (
        _curry_evidence_hash, _snapshot_curry_evidence,
    )

    report_path = safe_path(reservation_root / "reservation.json")
    acceptance_path = safe_path(reservation_root / "delivery" / "acceptance.json")
    report_raw = report_path.read_bytes()
    report = strict_json(report_raw)
    _require(isinstance(report, dict), "curry_handoff_v3_source_report_invalid")
    rows = report.get("inputs")
    _require(report.get("status") == "passed" and report.get("schema_version") == 3
             and report.get("kind") == "curry_consumption_reservation_v3"
             and isinstance(rows, list) and len(rows) == V3_SOURCE_INPUT_COUNT,
             "curry_handoff_v3_source_input_set_invalid")
    roles: set[str] = set()
    paths: dict[str, tuple[str, int]] = {}
    records = [
        _record_input(repo, "v3_reservation_report", report_path, report_raw),
        _record_input(repo, "v3_reservation_acceptance", acceptance_path,
                      safe_path(acceptance_path).read_bytes()),
    ]
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {"role", "path", "sha256", "bytes"}
                 and isinstance(row.get("role"), str) and row["role"]
                 and isinstance(row.get("path"), str) and row["path"]
                 and HASH.fullmatch(str(row.get("sha256", ""))) is not None
                 and type(row.get("bytes")) is int and row["bytes"] >= 0,
                 "curry_handoff_v3_source_input_record_invalid")
        role = row["role"]
        raw_relative = row["path"]
        _require(role not in roles, "curry_handoff_v3_source_input_role_duplicate")
        roles.add(role)
        _require("\\" not in raw_relative and ":" not in raw_relative,
                 "curry_handoff_v3_source_input_path_unsafe")
        relative = PurePosixPath(raw_relative)
        _require(not relative.is_absolute() and ".." not in relative.parts
                 and bool(relative.parts), "curry_handoff_v3_source_input_path_unsafe")
        local = repo.joinpath(*relative.parts)
        if role == "tenki_validation_directory_evidence":
            _require(relative == PurePosixPath(V3_TENKI_EVIDENCE_RELATIVE.as_posix())
                     and row["bytes"] == 0,
                     "curry_handoff_v3_source_directory_binding_invalid")
            path = safe_path(local, file=False)
            digest = _curry_evidence_hash(_snapshot_curry_evidence(path))
            _require(digest == row["sha256"],
                     "curry_handoff_v3_source_directory_mismatch")
            current = (digest, 0)
            record = _record_directory_input(
                repo, f"v3_source_{role}", path, digest,
            )
        else:
            path = safe_path(local)
            raw = path.read_bytes()
            _require(_sha(raw) == row["sha256"] and len(raw) == row["bytes"],
                     "curry_handoff_v3_source_input_mismatch")
            current = (row["sha256"], row["bytes"])
            record = _record_input(repo, f"v3_source_{role}", path, raw)
        prior = paths.setdefault(raw_relative, current)
        _require(prior == current, "curry_handoff_v3_source_path_conflict")
        records.append(record)
    _require(roles >= {role.removeprefix("v3_source_") for role in V3_SOURCE_REQUIRED_ROLES}
             and len(roles) == V3_SOURCE_INPUT_COUNT,
             "curry_handoff_v3_source_roles_incomplete")
    _require("historical_ledger_05" not in roles,
             "curry_handoff_v3_source_ledger_05_must_use_directory_pin")
    return records


def _resolve_final_delivery_path(repo: Path, final_root: Path, raw_path: str) -> Path:
    """Resolve a delivery ref whether it is repo-relative or final-build-relative.

    The serialized delivery uses repository-relative paths. Older build records
    may use paths relative to ``final-build``; both forms are accepted only
    when the resolved file remains inside the authenticated final-build tree.
    """
    _require(isinstance(raw_path, str) and raw_path and "\\" not in raw_path
             and ":" not in raw_path, "curry_handoff_final_build_reference_unsafe")
    rel = Path(raw_path)
    _require(not rel.is_absolute() and ".." not in rel.parts,
             "curry_handoff_final_build_reference_unsafe")
    repo = _absolute(repo)
    final_root = _absolute(final_root)
    workspace_candidate = repo / rel
    final_candidate = final_root / rel
    candidates = []
    for candidate in (workspace_candidate, final_candidate):
        try:
            candidate.absolute().relative_to(final_root)
        except ValueError:
            continue
        if candidate.exists() or candidate.is_symlink():
            candidates.append(candidate)
    _require(len(candidates) == 1, "curry_handoff_final_build_reference_unresolved")
    path = candidates[0]
    safe_path(path)
    _require(path.is_file(), "curry_handoff_final_build_reference_not_file")
    return path


def _parent_view_crosses_exclusive_open(source: bytes) -> bool:
    """Confirm the archived read view is retained across the exclusive open.

    This is deliberately a conservative static check: it binds ordering and
    rejects an explicit early drop, without executing historical source.
    """
    assignment = b"let _parent_view = verify_parent_request(&input, root)?;"
    start = source.find(assignment)
    if start < 0:
        return False
    # Identify the normal function body and the first later journal open. The
    # view binding and open must occur in the same lexical function and there
    # must be no explicit drop between them.
    function_start = source.rfind(b"fn ", 0, start)
    next_function = source.find(b"\nfn ", start)
    end = len(source) if next_function < 0 else next_function
    if function_start < 0:
        return False
    body = source[function_start:end]
    local_start = start - function_start
    opens = [
        body.find(b"CurryOptionBatch::open(", local_start),
        body.find(b"CurryOptionBatch::open_confirmation(", local_start),
        body.find(b"CurryOptionBatch::open_verification(", local_start),
    ]
    opens = [position for position in opens if position >= 0]
    if not opens:
        return False
    open_at = min(opens)
    between = body[local_start:open_at]
    if b"drop(_parent_view)" in between or b"drop(parent_view)" in between:
        return False
    return True


def _trace_summary(stderr: bytes) -> list[dict]:
    lines = stderr.decode("utf-8", "strict").splitlines()
    _require(len(lines) == len(TRACE_EVENTS), "saved_input_trace_incomplete")
    events: list[dict] = []
    for raw_line, expected in zip(lines, TRACE_EVENTS):
        item = strict_json(raw_line.encode("utf-8"))
        _require(isinstance(item, dict), "saved_input_trace_event_invalid")
        _require((item.get("phase"), item.get("event")) == expected,
                 "saved_input_trace_order_invalid")
        if expected[1] == "start":
            _require(set(item) == {"phase", "event"}, "saved_input_trace_event_invalid")
            events.append({"phase": expected[0], "event": "start"})
        else:
            elapsed = item.get("elapsed_ns")
            _require(set(item) == {"phase", "event", "elapsed_ns"}
                     and type(elapsed) is int and elapsed >= 0,
                     "saved_input_trace_duration_invalid")
            events.append({"phase": expected[0], "event": "end", "elapsed_ns": elapsed})
    return events


def _validate_saved_input_output(value: Any, *, context: str,
                                 identity_sha256: str) -> dict:
    keys = {
        "saved_input_audit_passed", "native_calls", "execution_ready", "stage",
        "context", "identity_sha256", "parent_receipt_valid",
        "request_derivation_valid", "stage_receipt_absent", "ledger",
    }
    _require(isinstance(value, dict) and set(value) == keys,
             "saved_input_output_fields_invalid")
    for key in ("saved_input_audit_passed", "execution_ready", "parent_receipt_valid",
                "request_derivation_valid", "stage_receipt_absent"):
        expected = key != "execution_ready"
        _require(type(value.get(key)) is bool and value[key] is expected,
                 "saved_input_output_boolean_invalid")
    _require(type(value.get("native_calls")) is int and value["native_calls"] == 0
             and type(value.get("stage")) is int and value["stage"] == 2
             and value.get("context") == context
             and value.get("identity_sha256") == identity_sha256
             and HASH.fullmatch(str(value.get("identity_sha256", ""))) is not None,
             "saved_input_output_binding_invalid")
    ledger = value.get("ledger")
    _require(isinstance(ledger, dict) and set(ledger) == {
        "consumed", "completed", "unknown", "reserved", "abandoned", "limit",
    } and all(type(ledger.get(key)) is int for key in ledger)
             and ledger == {"consumed": 1, "completed": 1, "unknown": 0,
                            "reserved": 0, "abandoned": 0, "limit": 7},
             "saved_input_output_ledger_invalid")
    return {
        "saved_input_audit_passed": True,
        "stage": 2,
        "context": context,
        "identity_sha256": identity_sha256,
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": dict(ledger),
    }


def _run_saved_input_audit(
    *, runner: Path, input_path: Path, prepared_sha256: str,
    context: str, identity_sha256: str, repo: Path, output_root: Path,
    expected_input_sha256: str,
    process_runner: Callable[..., Any] | None = None,
    stable_prelaunch_diagnostics: bool = False,
    on_attempted: Callable[[], None] | None = None,
    on_captured: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict, dict]:
    from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

    try:
        input_raw = safe_path(input_path).read_bytes()
    except Exception:
        if stable_prelaunch_diagnostics:
            raise ValueError("saved_input_input_preflight_failed") from None
        raise
    _require(HASH.fullmatch(expected_input_sha256) is not None
             and _sha(input_raw) == expected_input_sha256,
             "saved_input_changed_before_runner_start")
    command = [
        str(runner), str(input_path), "--input-sha", expected_input_sha256,
        "--prepared-sha256", prepared_sha256,
        "--audit-saved-input-only", "--trace-stderr",
    ]
    if on_attempted is not None:
        on_attempted()
    record, completed = capture_process_diagnostic(
        command, cwd=repo, evidence_root=output_root,
        mode=RUNNER_MODE, timeout=900, runner=process_runner,
        runner_role=RUNNER_ROLE,
    )
    if on_captured is not None:
        on_captured(record)
    _require_exact_process_diagnostic_set(output_root, record)
    # Capture owns raw persistence. Only after verifying those bytes do we decode them.
    stdout_path = safe_path(output_root / record["stdout"]["path"])
    stderr_path = safe_path(output_root / record["stderr"]["path"])
    stdout = stdout_path.read_bytes()
    stderr = stderr_path.read_bytes()
    _require(record.get("status") == "completed" and completed is not None
             and type(record.get("return_code")) is int
             and record["return_code"] == 0
             and getattr(completed, "returncode", None) == 0,
             "saved_input_runner_not_successful")
    _require(_sha(stdout) == record["stdout"].get("sha256")
             and len(stdout) == record["stdout"].get("bytes")
             and _sha(stderr) == record["stderr"].get("sha256")
             and len(stderr) == record["stderr"].get("bytes"),
             "saved_input_process_output_binding_invalid")
    trace = _trace_summary(stderr)
    output = strict_json(stdout)
    result = _validate_saved_input_output(
        output, context=context, identity_sha256=identity_sha256,
    )
    diagnostic_hash = _sha(canonical(record))
    return result, {
        "record": record,
        "diagnostic_sha256": diagnostic_hash,
        "trace": trace,
        "stdout_sha256": _sha(stdout),
        "stdout_bytes": len(stdout),
        "stderr_sha256": _sha(stderr),
        "stderr_bytes": len(stderr),
    }


def _create_process_diagnostics_dir(output_root: Path, *, audit_version: int) -> Path:
    diagnostics_dir = output_root / "process-diagnostics"
    version_spec = _version_spec(audit_version)
    try:
        diagnostics_dir.mkdir(parents=False, exist_ok=False)
    except OSError:
        if version_spec.tracks_process_attempt:
            raise ValueError(
                "saved_input_diagnostic_directory_prelaunch_failed",
            ) from None
        raise
    return diagnostics_dir


def _verify_process_capture(
    report: dict[str, Any], repo: Path, *, require_success: bool,
    output_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Authenticate the persisted process record and its raw stdout/stderr."""
    runner = report.get("runner")
    _require(isinstance(runner, dict), "curry_handoff_process_capture_summary_invalid")
    capture = runner.get("process_capture")
    _require(isinstance(capture, dict), "curry_handoff_process_capture_fields_invalid")
    output_root = output_root or repo / V2_OUTPUT_RELATIVE
    paths = {
        "metadata": capture.get("metadata_path"),
        "stdout": capture.get("stdout_path"),
        "stderr": capture.get("stderr_path"),
    }
    _require(all(isinstance(value, str) and value for value in paths.values()),
             "curry_handoff_process_capture_fields_invalid")
    absolute = {
        name: safe_path(output_root.joinpath(*PurePosixPath(relative).parts))
        for name, relative in paths.items()
    }
    metadata_raw = absolute["metadata"].read_bytes()
    stdout_raw = absolute["stdout"].read_bytes()
    stderr_raw = absolute["stderr"].read_bytes()
    record = strict_json(metadata_raw)
    _require(isinstance(record, dict) and set(record) == {
        "mode", "runner_role", "status", "return_code", "error_code",
        "stdout", "stderr", "metadata_path",
    } and record.get("mode") == RUNNER_MODE
             and record.get("runner_role") == RUNNER_ROLE
             and record.get("metadata_path") == paths["metadata"],
             "curry_handoff_process_capture_metadata_invalid")
    status = record.get("status")
    return_code = record.get("return_code")
    error_code = record.get("error_code")
    valid_status_tuple = (
        status == "completed" and type(return_code) is int and error_code is None
    ) or (
        status == "timeout" and return_code is None and error_code == "runner_timeout"
    ) or (
        status == "launch_failed" and return_code is None
        and error_code in ("runner_start_failed", "runner_launch_exception")
    )
    _require(valid_status_tuple, "curry_handoff_process_capture_status_tuple_invalid")
    _require_exact_process_diagnostic_set(output_root, record)
    for name in ("stdout", "stderr"):
        output = record.get(name)
        _require(isinstance(output, dict) and set(output) == {"path", "sha256", "bytes"}
                 and output.get("path") == paths[name]
                 and HASH.fullmatch(str(output.get("sha256", ""))) is not None
                 and type(output.get("bytes")) is int and output["bytes"] >= 0,
                 "curry_handoff_process_capture_metadata_invalid")
    summary_return_code = runner.get("return_code")
    summary_stdout_bytes = runner.get("stdout_bytes")
    summary_stderr_bytes = runner.get("stderr_bytes")
    _require((summary_return_code is None or type(summary_return_code) is int)
             and type(summary_stdout_bytes) is int
             and type(summary_stderr_bytes) is int
             and _sha(metadata_raw) == capture.get("metadata_sha256")
             and _sha(canonical(record)) == runner.get("diagnostic_sha256")
             and _sha(stdout_raw) == record["stdout"]["sha256"]
             and len(stdout_raw) == record["stdout"]["bytes"]
             and _sha(stderr_raw) == record["stderr"]["sha256"]
             and len(stderr_raw) == record["stderr"]["bytes"]
             and runner.get("return_code") == record.get("return_code")
             and runner.get("process_status") == record.get("status")
             and ("process_error_code" not in runner
                  or runner.get("process_error_code") == record.get("error_code"))
             and runner.get("stdout_sha256") == record["stdout"]["sha256"]
             and runner.get("stdout_bytes") == record["stdout"]["bytes"]
             and runner.get("stderr_sha256") == record["stderr"]["sha256"]
             and runner.get("stderr_bytes") == record["stderr"]["bytes"],
             "curry_handoff_process_capture_content_mismatch")
    if require_success:
        _require(record.get("status") == "completed" and record.get("return_code") == 0
                 and record.get("error_code") is None,
                 "curry_handoff_process_capture_not_successful")
        manifest_path = _fixed_option_paths(repo)[1]["research"] / "manifest.json"
        manifest = strict_json(safe_path(manifest_path).read_bytes())
        _require(isinstance(manifest, dict)
                 and manifest.get("context") == report.get("baseline", {}).get("context"),
                 "curry_handoff_process_capture_manifest_mismatch")
        identity = manifest.get("assets", {}).get("ordinary", {}).get("identity")
        result = _validate_saved_input_output(
            strict_json(stdout_raw), context=manifest["context"],
            identity_sha256=identity,
        )
        _require(result == runner.get("saved_input_result")
                 and _trace_summary(stderr_raw) == runner.get("trace"),
                 "curry_handoff_process_capture_result_mismatch")
    output_rows = (
        ("new_runner_capture_metadata", absolute["metadata"], metadata_raw),
        ("new_runner_stdout", absolute["stdout"], stdout_raw),
        ("new_runner_stderr", absolute["stderr"], stderr_raw),
    )
    return [_record_input(repo, role, path, raw) for role, path, raw in output_rows]


def _require_exact_process_diagnostic_set(output_root: Path, record: dict[str, Any]) -> None:
    diagnostics = safe_path(output_root / "process-diagnostics", file=False)
    stdout = record.get("stdout")
    stderr = record.get("stderr")
    paths = [
        stdout.get("path") if isinstance(stdout, dict) else None,
        stderr.get("path") if isinstance(stderr, dict) else None,
        record.get("metadata_path"),
    ]
    _require(all(isinstance(value, str) and value for value in paths)
             and len(paths) == len(set(paths)),
             "saved_input_diagnostic_paths_invalid")
    for value in paths:
        relative = PurePosixPath(value)
        _require(not relative.is_absolute() and ".." not in relative.parts
                 and len(relative.parts) == 2
                 and relative.parts[0] == "process-diagnostics"
                 and relative.as_posix() == value,
                 "saved_input_diagnostic_paths_invalid")
        safe_path(output_root.joinpath(*relative.parts))
    actual: set[str] = set()
    for item in diagnostics.iterdir():
        _require(item.is_file() and not item.is_symlink(),
                 "saved_input_unexpected_diagnostic_sidecar")
        actual.add(item.relative_to(output_root).as_posix())
    _require(actual == set(paths), "saved_input_unexpected_diagnostic_sidecar")


def _require_empty_process_diagnostics(
    repo: Path, *, output_root: Path = V3_OUTPUT_RELATIVE,
) -> None:
    output_root = repo / output_root
    if output_root.exists() or output_root.is_symlink():
        output_root = safe_path(output_root, file=False)
        diagnostics = output_root / "process-diagnostics"
        if diagnostics.exists() or diagnostics.is_symlink():
            diagnostics = safe_path(diagnostics, file=False)
            _require(not any(diagnostics.iterdir()),
                     "saved_input_unexpected_diagnostic_sidecar")


def _fixed_option_paths(repo: Path) -> tuple[Path, dict[str, Path]]:
    from ygo_eval.native_curry_option_validation import (
        OPTION_VERIFICATION_SCOPE, _fixed_curry_paths,
    )

    root = repo / OPTION_VERIFICATION_SCOPE.output_root
    args = argparse.Namespace(
        baseline_dir=repo / OPTION_VERIFICATION_SCOPE.baseline_root,
        runner=root / "native-artifacts/curry-option-verification.exe",
        worker=root / "native-artifacts/ygo-engine-worker.exe",
        build_record=root / "build-record.json",
        identity=root / "identity.json",
        window_start=root / "window-start.json",
        output=root / "research",
        preparation=repo / "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json",
        cases=repo / "data/runtime/baseline-2026-10-19/research/frozen-cases.json",
        core_source=repo / "data/tmp/ocgcore-source/operations.cpp",
    )
    resolved_root, output, paths = _fixed_curry_paths(args, repo, OPTION_VERIFICATION_SCOPE)
    return resolved_root, {**paths, "research": output}


def _verify_acceptance_delivery(
    baseline: Path, *, _sources: Any | None = None,
) -> tuple[dict, dict, bytes, bytes]:
    from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE

    baseline_sources = _sources.child("baseline") if _sources is not None else None
    acceptance_expected = _source_role_sha256(
        baseline_sources, "baseline_acceptance", ACCEPTANCE_SHA256,
    )
    delivery_expected = _source_role_sha256(
        baseline_sources, "baseline_delivery", DELIVERY_SHA256,
    )
    acceptance_raw, acceptance_hash = _read(baseline / ACCEPTANCE_RELATIVE, acceptance_expected)
    delivery_raw, delivery_hash = _read(baseline / DELIVERY_RELATIVE, delivery_expected)
    acceptance = strict_json(acceptance_raw)
    delivery = strict_json(delivery_raw)
    _require(acceptance_hash == acceptance_expected,
             "curry_handoff_acceptance_scope_anchor_invalid")
    scope = acceptance.get("scope")
    _require(acceptance.get("kind") == "curry_option_verification_final_acceptance"
             and isinstance(scope, dict)
             and scope.get("id") == OPTION_VERIFICATION_SCOPE.scope
             and acceptance.get("status") == "partial_failed"
             and scope.get("limit") == 7
             and scope.get("wall_seconds") == 7200
             and scope.get("worker_timeout_ms") == 30000
             and scope.get("execution_order") == "serial",
             "curry_handoff_acceptance_content_invalid")
    _require(delivery.get("kind") == "curry_option_verification_delivery"
             and delivery.get("scope") == OPTION_VERIFICATION_SCOPE.scope
             and delivery.get("status") == "partial_failed",
             "curry_handoff_delivery_content_invalid")
    delivery_acceptance = delivery.get("acceptance")
    _require(isinstance(delivery_acceptance, dict)
             and delivery_acceptance.get("path") == (
                 BASELINE_RELATIVE / ACCEPTANCE_RELATIVE
             ).as_posix()
             and delivery_acceptance.get("sha256") == acceptance_hash
             and delivery_acceptance.get("bytes") == len(acceptance_raw),
             "curry_handoff_delivery_acceptance_binding_invalid")
    _require(delivery_hash == delivery_expected,
             "curry_handoff_delivery_scope_anchor_invalid")
    accounting = acceptance.get("accounting")
    expected_accounting = {
        "certified_historical_consumed": 32,
        "policy_reserve": 7,
        "planning_base": 39,
        "new_consumed": 1,
        "certified_consumed_including_new": 33,
        "planning_total": 40,
        "unknown": 0,
        "old_confirmation_actual_consumed": None,
        "actual_all_history_cumulative": None,
    }
    _require(isinstance(accounting, dict)
             and all(accounting.get(key) == expected for key, expected in expected_accounting.items())
             and all(type(accounting.get(key)) is int for key in (
                 "certified_historical_consumed", "policy_reserve", "planning_base",
                 "new_consumed", "certified_consumed_including_new", "planning_total", "unknown",
             )), "curry_handoff_acceptance_accounting_invalid")
    native = acceptance.get("native_result")
    _require(isinstance(native, dict)
             and native.get("stage_1", {}).get("passed") is True
             and native.get("stage_1", {}).get("charged") is True
             and native.get("stage_2", {}).get("passed") is False
             and native.get("stage_2", {}).get("charged") is False
             and native.get("stage_2", {}).get("runner_return_code") == 2
             and native.get("stage_2", {}).get("diagnostic") == "runner_output_invalid_or_nonzero"
             and native.get("native_calls_total") == 1
             and native.get("unknown_consumption") == 0,
             "curry_handoff_acceptance_native_history_invalid")
    qualifications = acceptance.get("qualifications")
    _require(isinstance(qualifications, dict)
             and all(qualifications.get(flag) is False for flag in QUALIFICATIONS),
             "curry_handoff_acceptance_qualifications_invalid")
    return acceptance, delivery, acceptance_raw, delivery_raw


def _verify_source_bundle(
    archive_path: Path, file_list_path: Path, *, expected_identity: str,
    expected_count: int,
) -> tuple[dict, bytes, bytes]:
    """Verify a source ZIP and its certified file list as one content set."""
    archive_raw, _ = _read(archive_path)
    list_raw, _ = _read(file_list_path)
    listing = strict_json(list_raw)
    _require(isinstance(listing, dict)
             and listing.get("schema_version") == 1
             and listing.get("kind") == "workspace_source_archive"
             and type(listing.get("file_count")) is int
             and listing.get("file_count") == expected_count
             and isinstance(listing.get("head"), (str, type(None)))
             and listing.get("source_identity") == expected_identity
             and isinstance(listing.get("files"), dict)
             and len(listing["files"]) == expected_count,
             "curry_handoff_source_file_list_invalid")
    source_identity = listing.get("source_identity")
    source_files = listing["files"]
    _require(_sha(canonical({"head": listing["head"], "files": source_files}))
             == source_identity,
             "curry_handoff_source_identity_invalid")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        _require(len(names) == len(set(names)) and set(names) == set(source_files),
                 "curry_handoff_source_archive_membership_mismatch")
        for name, expected_hash in source_files.items():
            _require(isinstance(name, str) and isinstance(expected_hash, str)
                     and HASH.fullmatch(expected_hash) is not None
                     and _sha(archive.read(name)) == expected_hash,
                     "curry_handoff_source_archive_member_mismatch")
    return listing, archive_raw, list_raw


def _source_role_sha256(sources: Any | None, role: str, fallback: str | None) -> str | None:
    if sources is None:
        return fallback
    return sources.file_sha256_role(role)


def _verify_previous_failed_attempt(
    repo: Path, *, _sources: Any | None = None,
) -> dict[str, Any]:
    """Authenticate the prior V1 failure and its inert runner/source bundle."""
    previous_root = repo / OUTPUT_RELATIVE
    report_path = safe_path(previous_root / REPORT_RELATIVE)
    previous_sources = _sources.child("previous_failed_attempt") if _sources is not None else None
    report_hash_expected = _source_role_sha256(
        previous_sources, "previous_v1_report", PREVIOUS_V1_REPORT_SHA256,
    )
    report_raw, report_hash = _read(report_path, report_hash_expected)
    report = strict_json(report_raw)
    validate_report(report)
    _require(report_hash == report_hash_expected
             and report.get("status") == "failed"
             and report.get("failure_checkpoint") == "acceptance_delivery"
             and report.get("diagnostic") == "curry_handoff_acceptance_accounting_invalid"
             and report.get("checks", {}).get("acceptance_delivery") == "failed"
             and report.get("native_calls") == 0
             and report.get("execution_ready") is False
             and report.get("accounting", {}).get("new_consumed") is None,
             "curry_handoff_previous_failure_binding_invalid")
    build_record_path = safe_path(previous_root / BUILD_RECORD_RELATIVE)
    runner_path = safe_path(_previous_v1_runner_path(previous_root))
    archive_path = safe_path(previous_root / SOURCE_ARCHIVE_RELATIVE)
    list_path = safe_path(previous_root / SOURCE_FILE_LIST_RELATIVE)
    build_raw, build_hash = _read(
        build_record_path,
        _source_role_sha256(previous_sources, "previous_v1_build_record", None),
    )
    runner_raw, runner_hash = _read(
        runner_path,
        _source_role_sha256(previous_sources, "previous_v1_runner", None),
    )
    archive_raw, archive_hash = _read(
        archive_path,
        _source_role_sha256(previous_sources, "previous_v1_source_archive", None),
    )
    list_raw, list_hash = _read(
        list_path,
        _source_role_sha256(previous_sources, "previous_v1_source_file_list", None),
    )
    build = strict_json(build_raw)
    identity = report.get("tool_identity")
    source_before = build.get("source_before") if isinstance(build, dict) else None
    previous_count = (
        previous_sources.dataset_count("previous_source_file_count")
        if previous_sources is not None else 548
    )
    _require(isinstance(build, dict) and build.get("kind") == "build_record"
             and build.get("status") == "recorded"
             and build.get("reproducible_build_proven") is False
             and build.get("source_after") == source_before
             and isinstance(identity, dict)
             and source_before.get("identity") == identity.get("identity")
             and len(source_before.get("files", {})) == previous_count,
             "curry_handoff_previous_build_invalid")
    unsigned = {key: value for key, value in build.items() if key != "identity"}
    _require(build.get("identity") == _sha(canonical(unsigned)),
             "curry_handoff_previous_build_identity_invalid")
    _require(build.get("artifacts") == {
        "runner": runner_hash, "source_archive": archive_hash,
        "source_file_list": list_hash,
    }, "curry_handoff_previous_build_artifacts_invalid")
    listing, archive_raw, list_raw = _verify_source_bundle(
        archive_path, list_path, expected_identity=identity["identity"], expected_count=previous_count,
    )
    _require(listing.get("head") == identity.get("head"),
             "curry_handoff_previous_source_head_invalid")
    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    lock_source = zipfile.ZipFile(archive_path).read(lock_path)
    _require(_parent_view_crosses_exclusive_open(lock_source),
             "curry_handoff_archived_parent_lock_cause_missing")
    return {
        "report": {
            "status": report["status"], "failure_checkpoint": report["failure_checkpoint"],
            "diagnostic": report["diagnostic"], "report_sha256": report_hash,
        },
        "inputs": [
            _record_input(repo, "previous_v1_report", report_path, report_raw),
            _record_input(repo, "previous_v1_build_record", build_record_path, build_raw),
            _record_input(repo, "previous_v1_runner", runner_path, runner_raw),
            _record_input(repo, "previous_v1_source_archive", archive_path, archive_raw),
            _record_input(repo, "previous_v1_source_file_list", list_path, list_raw),
        ],
        "record": {
            "report_sha256": report_hash,
            "status": report["status"],
            "failure_checkpoint": report["failure_checkpoint"],
            "diagnostic": report["diagnostic"],
            "runner_sha256": runner_hash,
            "build_record_sha256": build_hash,
            "source_archive_sha256": archive_hash,
            "source_file_list_sha256": list_hash,
        },
        "root": previous_root,
    }


def _previous_v1_runner_path(previous_root: Path) -> Path:
    """Return the runner filename recorded by the prior verification batch."""
    return previous_root / PREVIOUS_V1_RUNNER_RELATIVE


def _previous_v1_audit_runner_path(previous_root: Path) -> Path:
    """Resolve the V1 audit runner from its own fixed artifact role."""
    return previous_root / PREVIOUS_V1_RUNNER_RELATIVE_CORRECT


def _repaired_parent_view_source(source: bytes) -> bool:
    """Recognize the repaired parent check without executing archived Rust."""
    start = source.find(b"fn verify_parent_request(")
    if start < 0:
        return False
    next_fn = source.find(b"\nfn ", start + 3)
    body = source[start:next_fn if next_fn >= 0 else len(source)]
    signature = re.search(rb"->\s*Result\s*<\s*\(\s*\)\s*,", body)
    drop_at = body.find(b"drop(view);")
    return bool(
        signature and drop_at >= 0 and body.find(b"Ok(())", drop_at) > drop_at
        and b"let _parent_view = verify_parent_request" not in body
    )


def _v1_accounting_mismatch_source(source: bytes) -> bool:
    """Bind the exact frozen V1 typo: source says policy_reserve, check says reserved."""
    start = source.find(b"def _verify_acceptance_delivery(")
    if start < 0:
        return False
    end = source.find(b"\ndef ", start + 5)
    body = source[start:end if end >= 0 else len(source)]
    expected = re.search(
        rb"expected_accounting\s*=\s*\{(?P<body>.*?)\n\s*\}", body, re.DOTALL,
    )
    integer_fields = re.search(
        rb"all\(type\(accounting\.get\(key\)\)\s+is\s+int\s+for\s+key\s+in\s*\((?P<body>.*?)\)\)",
        body, re.DOTALL,
    )
    return bool(
        expected and integer_fields
        and b'"policy_reserve"' in expected.group("body")
        and b'"policy_reserved"' in integer_fields.group("body")
        and b'"policy_reserve"' not in integer_fields.group("body")
        and b'"policy_reserved"' not in expected.group("body")
    )


def _verify_v1_audit_archive_semantics(
    archive_path: Path, list_path: Path, *, expected_identity: str,
    expected_count: int,
) -> dict[str, Any]:
    """Authenticate the V1 audit's repaired Rust and its independent Python typo."""
    _verify_source_bundle(
        archive_path, list_path, expected_identity=expected_identity,
        expected_count=expected_count,
    )
    with zipfile.ZipFile(archive_path) as archive:
        rust = archive.read("crates/ygo-engine-adapter/examples/curry-option-validation.rs")
        python = archive.read("python/ygo_eval/curry_ledger_handoff_audit.py")
    _require(_repaired_parent_view_source(rust), "curry_handoff_v1_repaired_rust_missing")
    _require(_v1_accounting_mismatch_source(python),
             "curry_handoff_v1_accounting_failure_cause_missing")
    listing = strict_json(safe_path(list_path).read_bytes())
    return {
        "rust_repaired": True,
        "python_accounting_mismatch": True,
        "rust_member_sha256": listing["files"]["crates/ygo-engine-adapter/examples/curry-option-validation.rs"],
        "python_member_sha256": listing["files"]["python/ygo_eval/curry_ledger_handoff_audit.py"],
    }


def _v3_source_file_hash(
    sources: Any | None, node: str, role: str, fallback: str,
) -> str:
    return sources.child(node).file_sha256_role(role) if sources is not None else fallback


def _v3_source_semantic_hash(
    sources: Any | None, node: str, role: str, fallback: str,
) -> str:
    """Return an immutable source-description semantic pin or production constant."""
    return sources.child(node).semantic_sha256(role) if sources is not None else fallback


def _verify_previous_v3_failed_source(
    repo: Path, *, _sources: Any | None = None,
) -> dict[str, Any]:
    """Authenticate the failed V3 audit and its final source release without execution."""
    root = repo / V3_OUTPUT_RELATIVE
    node = _sources.child("previous_v3_failed_source") if _sources is not None else None
    paths = {
        "previous_v3_report": root / REPORT_RELATIVE,
        "previous_v3_build_record": root / BUILD_RECORD_RELATIVE,
        "previous_v3_runner": root / RUNNER_RELATIVE,
        "previous_v3_source_archive": root / SOURCE_ARCHIVE_RELATIVE,
        "previous_v3_source_file_list": root / SOURCE_FILE_LIST_RELATIVE,
        "previous_v3_final_delivery": root / "final-build/delivery.json",
        "previous_v3_final_source_archive": root / "final-build/source-native.zip",
        "previous_v3_final_source_file_list": root / "final-build/source-native-file-list.json",
    }
    pins = {
        "previous_v3_report": V4_PREVIOUS_V3_REPORT_SHA256,
        "previous_v3_build_record": V4_PREVIOUS_V3_BUILD_RECORD_SHA256,
        "previous_v3_runner": V4_PREVIOUS_V3_RUNNER_SHA256,
        "previous_v3_source_archive": V4_PREVIOUS_V3_ARCHIVE_SHA256,
        "previous_v3_source_file_list": V4_PREVIOUS_V3_LIST_SHA256,
        "previous_v3_final_delivery": V4_PREVIOUS_V3_DELIVERY_SHA256,
        "previous_v3_final_source_archive": V4_PREVIOUS_V3_FINAL_ARCHIVE_SHA256,
        "previous_v3_final_source_file_list": V4_PREVIOUS_V3_FINAL_LIST_SHA256,
    }
    raws: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for role, path in paths.items():
        expected = node.file_sha256_role(role) if node is not None else pins[role]
        raws[role], hashes[role] = _read(safe_path(path), expected)

    report = strict_json(raws["previous_v3_report"])
    _validate_report_v3(report, repo=repo, version=3, _sources=_sources)
    _require(report.get("status") == "failed"
             and report.get("failure_checkpoint") == "stage1_parent_receipt"
             and report.get("diagnostic") == "curry_saved_stage_process_output_invalid"
             and report.get("runner", {}).get("process_attempted") is False,
             "curry_handoff_previous_v3_failure_binding_invalid")

    build = strict_json(raws["previous_v3_build_record"])
    source = build.get("source_before") if isinstance(build, dict) else None
    _require(isinstance(source, dict) and source == build.get("source_after")
             and source.get("identity") == report.get("tool_identity", {}).get("identity")
             and len(source.get("files", {})) == 563
             and build.get("kind") == "build_record" and build.get("status") == "recorded"
             and build.get("reproducible_build_proven") is False,
             "curry_handoff_previous_v3_build_source_invalid")
    unsigned = {key: value for key, value in build.items() if key != "identity"}
    _require(build.get("identity") == _sha(canonical(unsigned)),
             "curry_handoff_previous_v3_build_identity_invalid")
    _require(build.get("artifacts") == {
        "runner": hashes["previous_v3_runner"],
        "source_archive": hashes["previous_v3_source_archive"],
        "source_file_list": hashes["previous_v3_source_file_list"],
    }, "curry_handoff_previous_v3_build_artifact_binding_invalid")
    listing, archive_raw, list_raw = _verify_source_bundle(
        paths["previous_v3_source_archive"], paths["previous_v3_source_file_list"],
        expected_identity=source["identity"], expected_count=563,
    )
    _require(listing.get("head") == source.get("head"),
             "curry_handoff_previous_v3_source_head_invalid")

    final_delivery = strict_json(raws["previous_v3_final_delivery"])
    final = final_delivery.get("final_document_source") if isinstance(final_delivery, dict) else None
    audit_time = final_delivery.get("audit_time_source") if isinstance(final_delivery, dict) else None
    _require(final_delivery.get("schema_version") == 1
             and final_delivery.get("kind") == "curry_ledger_handoff_v3_final_delivery"
             and final_delivery.get("status") == "failed_before_saved_input_audit"
             and final_delivery.get("audit_report") == {
                 "path": "audit-report.json",
                 "sha256": hashes["previous_v3_report"],
                 "bytes": len(raws["previous_v3_report"]),
             }
             and final_delivery.get("runner_process_attempted") is False
             and final_delivery.get("stage2_receipt_absent") is True
             and final_delivery.get("qualifications") == QUALIFICATIONS
             and isinstance(audit_time, dict)
             and audit_time.get("identity") == source.get("identity")
             and audit_time.get("file_count") == 563
             and audit_time.get("runner_sha256") == hashes["previous_v3_runner"]
             and audit_time.get("build_record_sha256") == hashes["previous_v3_build_record"],
             "curry_handoff_previous_v3_delivery_binding_invalid")
    _require(isinstance(final, dict) and final.get("identity") is not None
             and final.get("file_count") == 564
             and final.get("source_archive") == "final-build/source-native.zip"
             and final.get("source_archive_sha256") == hashes["previous_v3_final_source_archive"]
             and final.get("source_file_list") == "final-build/source-native-file-list.json"
             and final.get("source_file_list_sha256") == hashes["previous_v3_final_source_file_list"]
             and final.get("source_delta") == V4_ALLOWED_SOURCE_DELTA,
             "curry_handoff_previous_v3_final_source_binding_invalid")
    final_listing, final_archive_raw, final_list_raw = _verify_source_bundle(
        paths["previous_v3_final_source_archive"],
        paths["previous_v3_final_source_file_list"],
        expected_identity=final["identity"], expected_count=564,
    )
    source_delta = {
        "added": sorted(set(final_listing["files"]) - set(listing["files"])),
        "removed": sorted(set(listing["files"]) - set(final_listing["files"])),
        "changed": sorted(
            name for name in set(listing["files"]) & set(final_listing["files"])
            if listing["files"][name] != final_listing["files"][name]
        ),
    }
    _require(source_delta == V4_ALLOWED_SOURCE_DELTA,
             "curry_handoff_previous_v3_source_delta_invalid")

    # Recompute the legacy V3 equality against the saved stage-1 stdout. The
    # old archive is read as bytes only; it is never imported or executed.
    baseline = repo / BASELINE_RELATIVE
    stage1_receipt_path = baseline / "research/stage-1.json"
    stage1_receipt = strict_json(safe_path(stage1_receipt_path).read_bytes())
    process_sidecar_path = baseline / "stage-1-process-diagnostic.json"
    process_sidecar_raw = safe_path(process_sidecar_path).read_bytes()
    process_record = strict_json(process_sidecar_raw)
    metadata_path = safe_path(baseline / process_record["metadata_path"])
    metadata_raw = metadata_path.read_bytes()
    metadata = strict_json(metadata_raw)
    _require(metadata == process_record,
             "curry_handoff_previous_v3_stage1_process_metadata_invalid")
    stdout_raw = safe_path(baseline / process_record["stdout"]["path"]).read_bytes()
    stderr_raw = safe_path(baseline / process_record["stderr"]["path"]).read_bytes()
    _require(_sha(stdout_raw) == process_record["stdout"]["sha256"]
             and len(stdout_raw) == process_record["stdout"]["bytes"]
             and _sha(stderr_raw) == process_record["stderr"]["sha256"]
             and len(stderr_raw) == process_record["stderr"]["bytes"],
             "curry_handoff_previous_v3_stage1_process_stream_invalid")
    actual_stdout = strict_json(stdout_raw)
    old_expected = {
        "successful": True, "native_calls": 1, "ledger": stage1_receipt["ledger"],
    }
    _require(isinstance(actual_stdout, dict) and len(actual_stdout) == 14
             and actual_stdout != old_expected,
             "curry_handoff_previous_v3_legacy_stdout_rejection_not_reproduced")
    with zipfile.ZipFile(paths["previous_v3_source_archive"]) as archive:
        archived_runner = archive.read("python/ygo_eval/native_curry_option_validation.py")
    _require(b'output != {"successful": True, "native_calls": 1,' in archived_runner
             and b'"ledger": receipt.get("ledger")' in archived_runner
             and b'curry_saved_stage_process_output_invalid' in archived_runner,
             "curry_handoff_previous_v3_legacy_stdout_source_missing")

    input_rows = [
        _record_input(repo, "previous_v3_report", paths["previous_v3_report"], raws["previous_v3_report"]),
        _record_input(repo, "previous_v3_build_record", paths["previous_v3_build_record"], raws["previous_v3_build_record"]),
        _record_input(repo, "previous_v3_runner", paths["previous_v3_runner"], raws["previous_v3_runner"]),
        _record_input(repo, "previous_v3_source_archive", paths["previous_v3_source_archive"], archive_raw),
        _record_input(repo, "previous_v3_source_file_list", paths["previous_v3_source_file_list"], list_raw),
        _record_input(repo, "previous_v3_final_delivery", paths["previous_v3_final_delivery"], raws["previous_v3_final_delivery"]),
        _record_input(repo, "previous_v3_final_source_archive", paths["previous_v3_final_source_archive"], final_archive_raw),
        _record_input(repo, "previous_v3_final_source_file_list", paths["previous_v3_final_source_file_list"], final_list_raw),
    ]
    return {
        "root": root,
        "record": {
            "report_sha256": hashes["previous_v3_report"],
            "delivery_sha256": hashes["previous_v3_final_delivery"],
            "status": report["status"],
            "failure_checkpoint": report["failure_checkpoint"],
            "diagnostic": report["diagnostic"],
            "runner_sha256": hashes["previous_v3_runner"],
            "build_record_sha256": hashes["previous_v3_build_record"],
            "source_archive_sha256": hashes["previous_v3_source_archive"],
            "source_file_list_sha256": hashes["previous_v3_source_file_list"],
            "final_delivery_sha256": hashes["previous_v3_final_delivery"],
            "final_source_archive_sha256": hashes["previous_v3_final_source_archive"],
            "final_source_file_list_sha256": hashes["previous_v3_final_source_file_list"],
            "source_identity": source["identity"],
            "file_count": 563,
            "final_source_identity": final["identity"],
            "final_file_count": 564,
            "source_delta": source_delta,
        },
        "inputs": input_rows,
    }


def _verify_previous_v4_failed_source(
    repo: Path, *, version_spec: AuditVersionSpec | None = None,
    _sources: Any | None = None,
) -> dict[str, Any]:
    """Authenticate V4 anchors first, then derive all subordinate hashes from them."""
    source_spec = version_spec or _version_spec(5)
    root = source_spec.source_root(repo, "previous_v4")
    node = _sources.child("previous_v4_failed_source") if _sources is not None else None
    paths = {
        "previous_v4_report": root / REPORT_RELATIVE,
        "previous_v4_build_record": root / BUILD_RECORD_RELATIVE,
        "previous_v4_runner": root / "native-artifacts/curry-option-validation.exe",
        "previous_v4_source_archive": root / SOURCE_ARCHIVE_RELATIVE,
        "previous_v4_source_file_list": root / SOURCE_FILE_LIST_RELATIVE,
        "previous_v4_final_delivery": root / "final-build/delivery-final.json",
        "previous_v4_final_source_archive": root / "final-build/source-final.zip",
        "previous_v4_final_source_file_list": root / "final-build/source-final-file-list.json",
    }
    # Authenticate the two specified anchors before trusting any V4 path/hash
    # references. Remaining expected hashes come only from these parsed records.
    report_anchor = (
        node.file_sha256_role("previous_v4_report")
        if node is not None else V5_PREVIOUS_V4_REPORT_SHA256
    )
    delivery_anchor = (
        node.file_sha256_role("previous_v4_final_delivery")
        if node is not None else V5_PREVIOUS_V4_DELIVERY_SHA256
    )
    report_raw, report_hash = _read(safe_path(paths["previous_v4_report"]), report_anchor)
    delivery_raw, delivery_hash = _read(
        safe_path(paths["previous_v4_final_delivery"]), delivery_anchor,
    )
    report = strict_json(report_raw)
    delivery = strict_json(delivery_raw)
    _require(isinstance(delivery, dict),
             "curry_handoff_previous_v4_delivery_binding_invalid")
    _require(_validate_report_v3(report, repo=repo, version=4, _sources=_sources)
             and report.get("status") == "failed"
             and report.get("failure_checkpoint") == "previous_v3_failed_source"
             and report.get("diagnostic") == "curry_handoff_build_root_contents_invalid"
             and report.get("native_calls") == 0
             and report.get("runner", {}).get("process_attempted") is False
             and report.get("tool_identity") is None
             and report.get("inputs") == [],
             "curry_handoff_previous_v4_failure_binding_invalid")
    # Preserve the old strict failure: its root had entries beyond the four-item
    # build bundle, so V5 authenticates it but never repairs or reuses that root.
    _require(root.is_dir() and {"build-target", "build-command.json"} <= {
        item.name for item in root.iterdir()
    }, "curry_handoff_previous_v4_failure_root_claim_invalid")

    audit_time = delivery.get("audit_time") if isinstance(delivery, dict) else None
    source_after_docs = delivery.get("source_after_docs") if isinstance(delivery, dict) else None
    final_source = delivery.get("source_archive") if isinstance(delivery, dict) else None
    audit_build = delivery.get("audit_build") if isinstance(delivery, dict) else None
    _require(delivery.get("schema_version") == 1
             and delivery.get("kind") == "curry_ledger_handoff_v4_final_delivery"
             and isinstance(audit_time, dict)
             and audit_time == {
                 "report_path": "../audit-report.json",
                 "report_sha256": report_hash,
                 "status": "failed",
                 "failure_checkpoint": "previous_v3_failed_source",
                 "diagnostic": "curry_handoff_build_root_contents_invalid",
                 "native_calls": 0,
                 "runner_process_attempted": False,
                 "runner_started": False,
             }
             and isinstance(source_after_docs, dict)
             and type(source_after_docs.get("file_count")) is int
             and source_after_docs.get("file_count") == 569
             and isinstance(source_after_docs.get("identity"), str)
             and HASH.fullmatch(source_after_docs["identity"]) is not None
             and isinstance(source_after_docs.get("head"), str)
             and isinstance(final_source, dict)
             and final_source.get("archive_path") == "source-final.zip"
             and final_source.get("file_list_path") == "source-final-file-list.json"
             and type(final_source.get("file_count")) is int
             and final_source.get("file_count") == 569
             and isinstance(audit_build, dict)
             and set(audit_build) == {
                 "build_record_path", "build_record_sha256", "runner_path",
                 "runner_sha256", "runner_executed",
             }
             and audit_build.get("build_record_path") == "../build-record.json"
             and audit_build.get("runner_path")
             == "../native-artifacts/curry-option-validation.exe"
             and audit_build.get("runner_executed") is False
             and HASH.fullmatch(str(audit_build.get("build_record_sha256", ""))) is not None
             and HASH.fullmatch(str(audit_build.get("runner_sha256", ""))) is not None
             and final_source.get("archive_sha256") is not None
             and final_source.get("file_list_sha256") is not None
             and HASH.fullmatch(str(final_source.get("archive_sha256"))) is not None
             and HASH.fullmatch(str(final_source.get("file_list_sha256"))) is not None,
             "curry_handoff_previous_v4_delivery_binding_invalid")
    if node is not None:
        _require(node.file_sha256_role("previous_v4_report") == report_hash
                 and node.file_sha256_role("previous_v4_final_delivery") == delivery_hash,
                 "curry_handoff_previous_v4_source_anchor_mismatch")

    derived = {
        "previous_v4_report": report_hash,
        "previous_v4_final_delivery": delivery_hash,
        "previous_v4_build_record": audit_build["build_record_sha256"],
        "previous_v4_runner": audit_build["runner_sha256"],
        "previous_v4_final_source_archive": final_source["archive_sha256"],
        "previous_v4_final_source_file_list": final_source["file_list_sha256"],
    }
    build_raw, build_hash = _read(
        safe_path(paths["previous_v4_build_record"]), derived["previous_v4_build_record"],
    )
    runner_raw, runner_hash = _read(
        safe_path(paths["previous_v4_runner"]), derived["previous_v4_runner"],
    )
    build = strict_json(build_raw)
    source = build.get("source_before") if isinstance(build, dict) else None
    _require(isinstance(source, dict) and source == build.get("source_after")
             and isinstance(source.get("files"), dict)
             and len(source["files"]) == 568
             and build.get("kind") == "build_record" and build.get("status") == "recorded"
             and build.get("reproducible_build_proven") is False,
             "curry_handoff_previous_v4_build_source_invalid")
    unsigned = {key: value for key, value in build.items() if key != "identity"}
    _require(build.get("identity") == _sha(canonical(unsigned)),
             "curry_handoff_previous_v4_build_identity_invalid")
    artifacts = build.get("artifacts")
    _require(isinstance(artifacts, dict) and set(artifacts) == {
        "runner", "source_archive", "source_file_list",
    } and artifacts.get("runner") == runner_hash
             and all(isinstance(artifacts.get(key), str)
                     and HASH.fullmatch(artifacts[key]) is not None
                     for key in ("source_archive", "source_file_list")),
             "curry_handoff_previous_v4_build_artifact_binding_invalid")
    derived["previous_v4_source_archive"] = artifacts["source_archive"]
    derived["previous_v4_source_file_list"] = artifacts["source_file_list"]
    if node is not None:
        for role, expected in derived.items():
            _require(node.file_sha256_role(role) == expected,
                     "curry_handoff_previous_v4_derived_hash_mismatch")
    archive_raw, archive_hash = _read(
        safe_path(paths["previous_v4_source_archive"]),
        derived["previous_v4_source_archive"],
    )
    list_raw, list_hash = _read(
        safe_path(paths["previous_v4_source_file_list"]),
        derived["previous_v4_source_file_list"],
    )
    final_archive_raw, final_archive_hash = _read(
        safe_path(paths["previous_v4_final_source_archive"]),
        derived["previous_v4_final_source_archive"],
    )
    final_list_raw, final_list_hash = _read(
        safe_path(paths["previous_v4_final_source_file_list"]),
        derived["previous_v4_final_source_file_list"],
    )
    listing, archive_raw, list_raw = _verify_source_bundle(
        paths["previous_v4_source_archive"], paths["previous_v4_source_file_list"],
        expected_identity=source["identity"], expected_count=568,
    )
    _require(listing.get("head") == source.get("head"),
             "curry_handoff_previous_v4_source_head_invalid")

    _require(delivery.get("source_after_docs") == {
                 "identity": source_after_docs["identity"],
                 "head": source_after_docs["head"],
                 "file_count": 569,
             }, "curry_handoff_previous_v4_final_source_anchor_invalid")
    final_listing, final_archive_raw, final_list_raw = _verify_source_bundle(
        paths["previous_v4_final_source_archive"],
        paths["previous_v4_final_source_file_list"],
        expected_identity=source_after_docs["identity"], expected_count=569,
    )
    _require(final_listing.get("head") == source_after_docs["head"],
             "curry_handoff_previous_v4_final_source_head_invalid")
    source_delta = {
        "added": sorted(set(final_listing["files"]) - set(listing["files"])),
        "removed": sorted(set(listing["files"]) - set(final_listing["files"])),
        "changed": sorted(
            name for name in set(listing["files"]) & set(final_listing["files"])
            if listing["files"][name] != final_listing["files"][name]
        ),
    }
    _require(source_delta == V5_ALLOWED_SOURCE_DELTA,
             "curry_handoff_previous_v4_source_delta_invalid")

    role_to_raw = {
        "previous_v4_report": report_raw,
        "previous_v4_build_record": build_raw,
        "previous_v4_runner": runner_raw,
        "previous_v4_source_archive": archive_raw,
        "previous_v4_source_file_list": list_raw,
        "previous_v4_final_delivery": delivery_raw,
        "previous_v4_final_source_archive": final_archive_raw,
        "previous_v4_final_source_file_list": final_list_raw,
    }
    input_rows = [
        _record_input(repo, role, paths[role], role_to_raw[role]) for role in paths
    ]
    return {
        "root": root,
        "record": {
            "report_sha256": report_hash,
            "delivery_sha256": delivery_hash,
            "status": report["status"],
            "failure_checkpoint": report["failure_checkpoint"],
            "diagnostic": report["diagnostic"],
            "runner_sha256": runner_hash,
            "build_record_sha256": build_hash,
            "source_archive_sha256": archive_hash,
            "source_file_list_sha256": list_hash,
            "final_delivery_sha256": delivery_hash,
            "final_source_archive_sha256": final_archive_hash,
            "final_source_file_list_sha256": final_list_hash,
            "report_tool_identity": report["tool_identity"],
            "report_input_count": len(report["inputs"]),
            "source_identity": source["identity"],
            "file_count": 568,
            "final_source_identity": delivery["source_after_docs"]["identity"],
            "final_file_count": 569,
            "source_delta": source_delta,
        },
        "inputs": input_rows,
    }


def _verify_v1_audit_source_v3(repo: Path, *, _sources: Any | None = None) -> dict[str, Any]:
    """Read-only verification of the completed V1 audit artifact chain."""
    root = repo / OUTPUT_RELATIVE
    node = _sources.child("previous_failed_attempt") if _sources is not None else None
    pins = {
        "previous_v1_report": PREVIOUS_V1_REPORT_SHA256,
        "previous_v1_build_record": PREVIOUS_V1_BUILD_RECORD_SHA256,
        "previous_v1_runner": PREVIOUS_V1_RUNNER_SHA256,
        "previous_v1_source_archive": PREVIOUS_V1_ARCHIVE_SHA256,
        "previous_v1_source_file_list": PREVIOUS_V1_LIST_SHA256,
    }
    paths = {
        "previous_v1_report": root / REPORT_RELATIVE,
        "previous_v1_build_record": root / BUILD_RECORD_RELATIVE,
        "previous_v1_runner": root / PREVIOUS_V1_RUNNER_RELATIVE_CORRECT,
        "previous_v1_source_archive": root / SOURCE_ARCHIVE_RELATIVE,
        "previous_v1_source_file_list": root / SOURCE_FILE_LIST_RELATIVE,
    }
    raws: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for role, path in paths.items():
        expected = node.file_sha256_role(role) if node is not None else pins[role]
        raws[role], hashes[role] = _read(safe_path(path), expected)
    report = strict_json(raws["previous_v1_report"])
    _require(_validate_report_v1(report)
             and report["status"] == "failed"
             and report["failure_checkpoint"] == "acceptance_delivery"
             and report["diagnostic"] == "curry_handoff_acceptance_accounting_invalid"
             and report["native_calls"] == 0 and report["accounting"]["new_consumed"] is None,
             "curry_handoff_v1_failure_binding_invalid")
    build = strict_json(raws["previous_v1_build_record"])
    source = build.get("source_before") if isinstance(build, dict) else None
    _require(isinstance(source, dict) and source == build.get("source_after")
             and source.get("identity") == report.get("tool_identity", {}).get("identity")
             and len(source.get("files", {})) == 548
             and build.get("kind") == "build_record" and build.get("status") == "recorded"
             and build.get("reproducible_build_proven") is False,
             "curry_handoff_v1_build_source_invalid")
    unsigned = {key: value for key, value in build.items() if key != "identity"}
    _require(build.get("identity") == _sha(canonical(unsigned)),
             "curry_handoff_v1_build_identity_invalid")
    _require(build.get("artifacts") == {
        "runner": hashes["previous_v1_runner"],
        "source_archive": hashes["previous_v1_source_archive"],
        "source_file_list": hashes["previous_v1_source_file_list"],
    }, "curry_handoff_v1_build_artifact_binding_invalid")
    listing, archive_raw, list_raw = _verify_source_bundle(
        paths["previous_v1_source_archive"], paths["previous_v1_source_file_list"],
        expected_identity=source["identity"], expected_count=548,
    )
    _require(listing.get("head") == source.get("head"),
             "curry_handoff_v1_source_head_invalid")
    semantic = _verify_v1_audit_archive_semantics(
        paths["previous_v1_source_archive"], paths["previous_v1_source_file_list"],
        expected_identity=source["identity"], expected_count=548,
    )
    inputs = [
        _record_input(repo, role, paths[role], raws[role])
        for role in ("previous_v1_report", "previous_v1_build_record", "previous_v1_runner")
    ]
    inputs.extend((
        _record_input(repo, "previous_v1_source_archive", paths["previous_v1_source_archive"], archive_raw),
        _record_input(repo, "previous_v1_source_file_list", paths["previous_v1_source_file_list"], list_raw),
    ))
    return {
        "root": root,
        "report": report,
        "record": {
            "report_sha256": hashes["previous_v1_report"],
            "status": report["status"],
            "failure_checkpoint": report["failure_checkpoint"],
            "diagnostic": report["diagnostic"],
            "runner_sha256": hashes["previous_v1_runner"],
            "build_record_sha256": hashes["previous_v1_build_record"],
            "source_archive_sha256": hashes["previous_v1_source_archive"],
            "source_file_list_sha256": hashes["previous_v1_source_file_list"],
        },
        "source_identity": source["identity"],
        "file_count": 548,
        "semantic": semantic,
        "inputs": inputs,
    }


def _v2_archive_semantics(source: bytes) -> bool:
    """Confirm the V2 implementation contains both historically wrong bindings."""
    return (
        b"PREVIOUS_V1_RUNNER_RELATIVE = Path(\"native-artifacts/curry-option-verification.exe\")" in source
        and b"return previous_root / PREVIOUS_V1_RUNNER_RELATIVE" in source
        and b"_parent_view_crosses_exclusive_open(lock_source)" in source
        and b"curry_handoff_archived_parent_lock_cause_missing" in source
        and b"_repaired_parent_view_source" not in source
    )


def _verify_v2_audit_source_v3(repo: Path, *, _sources: Any | None = None) -> dict[str, Any]:
    """Authenticate the failed V2 audit and its distinct source-role defects."""
    root = repo / V2_OUTPUT_RELATIVE
    node = _sources.child("previous_v2_failed_attempt") if _sources is not None else None
    pins = {
        "previous_v2_report": PREVIOUS_V2_REPORT_SHA256,
        "previous_v2_build_record": PREVIOUS_V2_BUILD_RECORD_SHA256,
        "previous_v2_runner": PREVIOUS_V2_RUNNER_SHA256,
        "previous_v2_source_archive": PREVIOUS_V2_ARCHIVE_SHA256,
        "previous_v2_source_file_list": PREVIOUS_V2_LIST_SHA256,
    }
    paths = {
        "previous_v2_report": root / REPORT_RELATIVE,
        "previous_v2_build_record": root / BUILD_RECORD_RELATIVE,
        "previous_v2_runner": root / RUNNER_RELATIVE,
        "previous_v2_source_archive": root / SOURCE_ARCHIVE_RELATIVE,
        "previous_v2_source_file_list": root / SOURCE_FILE_LIST_RELATIVE,
    }
    raws: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for role, path in paths.items():
        expected = node.file_sha256_role(role) if node is not None else pins[role]
        raws[role], hashes[role] = _read(safe_path(path), expected)
    report = strict_json(raws["previous_v2_report"])
    _require(report.get("schema_version") == 2
             and report.get("kind") == "curry_ledger_handoff_audit_v2"
             and report.get("status") == "failed"
             and report.get("failure_checkpoint") == "previous_failed_source"
             and report.get("diagnostic") == "audit_failed"
             and report.get("checks", {}).get("previous_failed_source") == "failed"
             and report.get("native_calls") == 0 and report.get("execution_ready") is False,
             "curry_handoff_v2_failure_binding_invalid")
    build = strict_json(raws["previous_v2_build_record"])
    source = build.get("source_before") if isinstance(build, dict) else None
    expected_source_identity = _v3_source_semantic_hash(
        _sources, "previous_v2_failed_attempt", "v2_source_identity",
        PREVIOUS_V2_SOURCE_IDENTITY,
    )
    _require(isinstance(source, dict) and source == build.get("source_after")
             and source.get("identity") == report.get("tool_identity", {}).get("identity")
             and source.get("identity") == expected_source_identity
             and len(source.get("files", {})) == 557
             and build.get("kind") == "build_record" and build.get("status") == "recorded"
             and build.get("reproducible_build_proven") is False,
             "curry_handoff_v2_build_source_invalid")
    unsigned = {key: value for key, value in build.items() if key != "identity"}
    _require(build.get("identity") == _sha(canonical(unsigned)),
             "curry_handoff_v2_build_identity_invalid")
    _require(build.get("artifacts") == {
        "runner": hashes["previous_v2_runner"],
        "source_archive": hashes["previous_v2_source_archive"],
        "source_file_list": hashes["previous_v2_source_file_list"],
    }, "curry_handoff_v2_build_artifact_binding_invalid")
    listing, archive_raw, list_raw = _verify_source_bundle(
        paths["previous_v2_source_archive"], paths["previous_v2_source_file_list"],
        expected_identity=source["identity"], expected_count=557,
    )
    with zipfile.ZipFile(paths["previous_v2_source_archive"]) as archive:
        python_source = archive.read("python/ygo_eval/curry_ledger_handoff_audit.py")
        rust_source = archive.read("crates/ygo-engine-adapter/examples/curry-option-validation.rs")
    _require(_v2_archive_semantics(python_source)
             and _repaired_parent_view_source(rust_source),
             "curry_handoff_v2_archived_failure_cause_missing")
    return {
        "root": root,
        "report": report,
        "record": {
            "report_sha256": hashes["previous_v2_report"],
            "status": report["status"],
            "failure_checkpoint": report["failure_checkpoint"],
            "diagnostic": report["diagnostic"],
            "runner_sha256": hashes["previous_v2_runner"],
            "build_record_sha256": hashes["previous_v2_build_record"],
            "source_archive_sha256": hashes["previous_v2_source_archive"],
            "source_file_list_sha256": hashes["previous_v2_source_file_list"],
        },
        "source_identity": source["identity"], "file_count": 557,
        "inputs": [
            _record_input(repo, "previous_v2_report", paths["previous_v2_report"], raws["previous_v2_report"]),
            _record_input(repo, "previous_v2_build_record", paths["previous_v2_build_record"], raws["previous_v2_build_record"]),
            _record_input(repo, "previous_v2_runner", paths["previous_v2_runner"], raws["previous_v2_runner"]),
            _record_input(repo, "previous_v2_source_archive", paths["previous_v2_source_archive"], archive_raw),
            _record_input(repo, "previous_v2_source_file_list", paths["previous_v2_source_file_list"], list_raw),
        ],
    }


def _verify_v2_final_source_v3(repo: Path, *, _sources: Any | None = None) -> dict[str, Any]:
    """Authenticate the 558-member V2 final release and exact documentation delta."""
    root = repo / PREVIOUS_V2_FINAL_ROOT_RELATIVE
    node = _sources.child("v2_final_source") if _sources is not None else None
    release_path = root / "release-record.json"
    archive_path = root / "source-native.zip"
    list_path = root / "source-native-file-list.json"
    release_expected = node.file_sha256_role("v2_final_release_record") if node else PREVIOUS_V2_FINAL_RELEASE_SHA256
    archive_expected = node.file_sha256_role("v2_final_source_archive") if node else PREVIOUS_V2_FINAL_ARCHIVE_SHA256
    list_expected = node.file_sha256_role("v2_final_source_file_list") if node else PREVIOUS_V2_FINAL_LIST_SHA256
    release_raw, release_hash = _read(release_path, release_expected)
    archive_raw, archive_hash = _read(archive_path, archive_expected)
    list_raw, list_hash = _read(list_path, list_expected)
    release = strict_json(release_raw)
    expected_identity = _v3_source_semantic_hash(
        _sources, "v2_final_source", "v2_final_source_identity",
        PREVIOUS_V2_FINAL_SOURCE_IDENTITY,
    )
    expected_head = _v3_source_semantic_hash(
        _sources, "v2_final_source", "v2_final_source_head",
        "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
    )
    expected_v2_identity = _v3_source_semantic_hash(
        _sources, "previous_v2_failed_attempt", "v2_source_identity",
        PREVIOUS_V2_SOURCE_IDENTITY,
    )
    expected_v2_report = _v3_source_file_hash(
        _sources, "previous_v2_failed_attempt", "previous_v2_report",
        PREVIOUS_V2_REPORT_SHA256,
    )
    expected_ledger_hash = _v3_source_semantic_hash(
        _sources, "v2_final_source", "scope_ledger_sha256",
        "7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c",
    )
    _require(release.get("schema_version") == 1
             and release.get("kind") == "curry_ledger_handoff_v2_final_source_release"
             and release.get("head") == expected_head
             and release.get("source_identity") == expected_identity,
             "curry_handoff_v2_release_invalid")
    _require(release.get("file_count") == 558
             and release.get("source_archive") == {"path": "source-native.zip", "sha256": archive_hash}
             and release.get("source_file_list") == {"path": "source-native-file-list.json", "sha256": list_hash}
             and release.get("v2_report_sha256") == expected_v2_report
             and release.get("scope_ledger_sha256") == expected_ledger_hash
             and release.get("stage2_receipt_exists") is False
             and release.get("native_calls") == 0 and release.get("execution_ready") is False
             and release.get("qualifications") == QUALIFICATIONS,
             "curry_handoff_v2_release_binding_invalid")
    identity = release.get("source_identity")
    listing, archive_bytes, list_bytes = _verify_source_bundle(
        archive_path, list_path, expected_identity=identity, expected_count=558,
    )
    v2_listing, _, _ = _verify_source_bundle(
        repo / V2_OUTPUT_RELATIVE / SOURCE_ARCHIVE_RELATIVE,
        repo / V2_OUTPUT_RELATIVE / SOURCE_FILE_LIST_RELATIVE,
        expected_identity=expected_v2_identity, expected_count=557,
    )
    v2_files, final_files = v2_listing["files"], listing["files"]
    delta = {
        "added": sorted(set(final_files) - set(v2_files)),
        "removed": sorted(set(v2_files) - set(final_files)),
        "changed": sorted(name for name in set(v2_files) & set(final_files)
                           if v2_files[name] != final_files[name]),
    }
    _require(delta == ALLOWED_V2_SOURCE_DELTA and identity == expected_identity,
             "curry_handoff_v2_final_source_delta_invalid")
    return {
        "root": root, "release": release, "identity": identity,
        "file_count": 558, "source_delta": delta,
        "record": {
            "release_record_sha256": release_hash,
            "source_archive_sha256": archive_hash,
            "source_file_list_sha256": list_hash,
            "source_identity": identity, "file_count": 558,
            "source_delta": delta,
        },
        "inputs": [
            _record_input(repo, "v2_final_release_record", release_path, release_raw),
            _record_input(repo, "v2_final_source_archive", archive_path, archive_bytes),
            _record_input(repo, "v2_final_source_file_list", list_path, list_bytes),
        ],
    }


def _archived_static_return_code(source: bytes) -> int:
    """Read the frozen runner's error exit branch without executing it."""
    match = re.search(rb"(?m)^fn main\(\)\s*\{(?P<body>.*?)^\}", source, re.DOTALL)
    _require(match is not None, "curry_handoff_archived_main_missing")
    body = match.group("body")
    _require(re.search(
        rb"if let Err\(error\) = execute\(&args\)\s*\{\s*"
        rb"eprintln!\(\"\{error\}\"\);\s*"
        rb"std::process::exit\(2\);\s*\}", body,
    ) is not None, "curry_handoff_archived_static_exit_branch_missing")
    return 2


def _verify_final_build_chain(
    repo: Path, baseline: Path, acceptance: dict, delivery: dict,
    *, _sources: Any | None = None,
) -> dict[str, Any]:
    """Recompute native/final source bundles and the fixed documentation delta."""
    source_build = acceptance.get("source_and_build")
    _require(isinstance(source_build, dict), "curry_handoff_source_build_missing")
    native = source_build.get("native_time")
    final = source_build.get("final_after_docs")
    final_delivery = delivery.get("final_build")
    _require(isinstance(native, dict) and isinstance(final, dict)
             and isinstance(final_delivery, dict), "curry_handoff_dual_build_missing")

    native_root, old_paths = _fixed_option_paths(repo)
    native_record_path = safe_path(old_paths["build_record"])
    native_archive_path = safe_path(old_paths["source_archive"])
    native_list_path = safe_path(old_paths["source_file_list"])
    native_record_raw, native_record_hash = _read(native_record_path)
    _require(native_record_hash == native.get("build_record_sha256"),
             "curry_handoff_native_build_record_hash_mismatch")
    native_record = strict_json(native_record_raw)
    native_unsigned = {key: value for key, value in native_record.items() if key != "identity"}
    native_source = native_record.get("source_before")
    _require(native_record.get("kind") == "build_record"
             and native_record.get("status") == "recorded"
             and native_record.get("reproducible_build_proven") is False
             and native_record.get("identity") == _sha(canonical(native_unsigned))
             and native_record.get("source_before") == native_record.get("source_after")
             and isinstance(native_source, dict)
             and native_source.get("identity") == native.get("source_identity")
             and isinstance(native_source.get("files"), dict)
             and len(native_source["files"]) == native.get("file_count"),
             "curry_handoff_native_build_record_invalid")
    native_listing, native_archive_raw, native_list_raw = _verify_source_bundle(
        native_archive_path, native_list_path,
        expected_identity=native.get("source_identity"),
        expected_count=native.get("file_count"),
    )
    _require(_sha(native_archive_raw) == native.get("source_archive_sha256")
             and _sha(native_list_raw) == native.get("source_file_list_sha256"),
             "curry_handoff_native_source_hash_mismatch")
    native_artifact_names = {
        "cli": "ygo-cli.exe", "runner": "curry-option-verification.exe",
        "worker": "ygo-engine-worker.exe",
    }
    native_artifact_hashes: dict[str, str] = {}
    native_artifact_inputs: list[dict[str, Any]] = []
    for role, name in native_artifact_names.items():
        path = safe_path(native_root / "native-artifacts" / name)
        raw, found = _read(path)
        native_artifact_hashes[role] = found
        native_artifact_inputs.append(_record_input(repo, f"native_{role}_artifact", path, raw))
    _require(native_record.get("artifacts") == native_artifact_hashes,
             "curry_handoff_native_artifact_build_mismatch")

    final_root = safe_path(baseline / "final-build", file=False)
    refs = {
        "record": final_delivery.get("record"),
        "source_archive": final_delivery.get("source_archive"),
        "source_file_list": final_delivery.get("source_file_list"),
    }
    resolved: dict[str, Path] = {}
    raws: dict[str, bytes] = {}
    for role, ref in refs.items():
        _require(isinstance(ref, dict)
                 and set(ref) == {"path", "sha256", "bytes"}
                 and isinstance(ref.get("path"), str),
                 "curry_handoff_final_build_reference_invalid")
        path = _resolve_final_delivery_path(repo, final_root, ref["path"])
        raw, found = _read(path, ref.get("sha256"))
        _require(len(raw) == ref.get("bytes"), "curry_handoff_final_build_reference_size_mismatch")
        resolved[role] = path
        raws[role] = raw

    record = strict_json(raws["record"])
    unsigned = {key: value for key, value in record.items() if key != "identity"}
    _require(record.get("kind") == "build_record" and record.get("status") == "recorded"
             and record.get("reproducible_build_proven") is False
             and record.get("identity") == _sha(canonical(unsigned))
             and record.get("identity") == final.get("build_record_identity")
             and _sha(raws["record"]) == final.get("build_record_sha256")
             and record.get("source_before") == record.get("source_after")
             and record["source_before"].get("identity") == final.get("source_identity"),
             "curry_handoff_final_build_record_invalid")
    final_listing = strict_json(raws["source_file_list"])
    final_identity = final.get("source_identity")
    final_count = final.get("file_count")
    _require(final_listing.get("head") == record["source_before"].get("head")
             and record["source_before"].get("files") == final_listing.get("files")
             and record["source_before"].get("identity") == final_identity
             and final_listing.get("source_identity") == final_identity
             and final_listing.get("file_count") == final_count,
             "curry_handoff_final_source_identity_invalid")
    _verify_source_bundle(
        resolved["source_archive"], resolved["source_file_list"],
        expected_identity=final_identity, expected_count=final_count,
    )
    _require(_sha(raws["source_archive"]) == final.get("source_archive_sha256")
             and _sha(raws["source_file_list"]) == final.get("source_file_list_sha256"),
             "curry_handoff_final_source_hash_mismatch")

    artifact_rows = final_delivery.get("artifacts")
    _require(isinstance(artifact_rows, list) and len(artifact_rows) == 3,
             "curry_handoff_final_artifact_list_invalid")
    artifact_hashes: dict[str, str] = {}
    artifact_inputs = []
    artifact_role_by_name = {
        "ygo-cli.exe": "cli", "ygo-engine-worker.exe": "worker",
        "curry-option-validation.exe": "runner",
    }
    for row in artifact_rows:
        _require(isinstance(row, dict) and set(row) == {"path", "sha256", "bytes"}
                 and isinstance(row.get("path"), str),
                 "curry_handoff_final_artifact_reference_invalid")
        path = _resolve_final_delivery_path(repo, final_root, row["path"])
        raw, found = _read(path, row.get("sha256"))
        _require(len(raw) == row.get("bytes"), "curry_handoff_final_artifact_size_mismatch")
        name = path.name
        role = artifact_role_by_name.get(name)
        _require(role is not None and role not in artifact_hashes,
                 "curry_handoff_final_artifact_role_invalid")
        artifact_hashes[role] = found
        report_role = f"final_{role}_artifact"
        artifact_inputs.append(_record_input(repo, report_role, path, raw))
    _require(artifact_hashes == record.get("artifacts"),
             "curry_handoff_final_artifact_build_mismatch")
    _require(final.get("source_delta_vs_native") == ALLOWED_SOURCE_DELTA,
             "curry_handoff_source_delta_pin_invalid")

    native_files = native_listing["files"]
    final_files = final_listing["files"]
    actual_delta = {
        "added": sorted(set(final_files) - set(native_files)),
        "removed": sorted(set(native_files) - set(final_files)),
        "changed": sorted(name for name in set(native_files) & set(final_files)
                           if native_files[name] != final_files[name]),
    }
    _require(actual_delta == ALLOWED_SOURCE_DELTA
             and native.get("file_count") == 544 and final_count == 545,
             "curry_handoff_source_delta_invalid")
    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    with zipfile.ZipFile(native_archive_path) as archive:
        lock_source = archive.read(lock_path)
    _require(_parent_view_crosses_exclusive_open(lock_source),
             "curry_handoff_archived_parent_lock_cause_missing")
    static_return_code = _archived_static_return_code(lock_source)

    input_rows = [
        _record_input(repo, "native_build_record", native_record_path, native_record_raw),
        _record_input(repo, "native_source_archive", native_archive_path, native_archive_raw),
        _record_input(repo, "native_source_file_list", native_list_path, native_list_raw),
        *native_artifact_inputs,
        _record_input(repo, "final_build_record", resolved["record"], raws["record"]),
        _record_input(repo, "final_source_archive", resolved["source_archive"], raws["source_archive"]),
        _record_input(repo, "final_source_file_list", resolved["source_file_list"], raws["source_file_list"]),
        *artifact_inputs,
    ]
    return {
        "record": {
            "native_source_identity": native.get("source_identity"),
            "native_file_count": native.get("file_count"),
            "final_source_identity": final_identity,
            "final_file_count": final_count,
            "source_delta": actual_delta,
            "parent_lock_source_sha256": native_files.get(lock_path),
            "parent_view_retained": True,
            "archived_static_return_code": static_return_code,
            "historical_actual_exit_code": None,
        },
        "inputs": input_rows,
        "baseline_root": baseline,
        "reservation_root": repo / "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25",
        "native_root": native_root,
        "ledger_path": repo / "data/runtime/p1-curry-option-verification-native-2026-10-25/research/calls.jsonl",
        "stage2_receipt": repo / "data/runtime/p1-curry-option-verification-native-2026-10-25/research/stage-2.json",
        "native_archive_path": native_archive_path,
        "final_root": final_root,
    }


def _build_material_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    paths = (
        root / RUNNER_RELATIVE,
        root / BUILD_RECORD_RELATIVE,
        root / SOURCE_ARCHIVE_RELATIVE,
        root / SOURCE_FILE_LIST_RELATIVE,
    )
    snapshot = {}
    for path in paths:
        raw, found = _read(path)
        snapshot[path.relative_to(root).as_posix()] = (found, len(raw))
    return snapshot


def _verify_runner_build(runner: Path, build_record: Path, repo: Path,
                         source_identity: dict) -> dict:
    """Authenticate the isolated runner and the exact source snapshot that built it."""
    build_raw, build_hash = _read(build_record)
    runner_raw, runner_hash = _read(runner)
    archive_path = runner.parents[1] / SOURCE_ARCHIVE_RELATIVE
    list_path = runner.parents[1] / SOURCE_FILE_LIST_RELATIVE
    archive_raw, archive_hash = _read(archive_path)
    list_raw, list_hash = _read(list_path)
    build = strict_json(build_raw)
    _require(isinstance(build, dict) and build.get("kind") == "build_record"
             and build.get("status") == "recorded"
             and build.get("reproducible_build_proven") is False,
             "curry_handoff_build_record_invalid")
    unsigned = {key: value for key, value in build.items() if key != "identity"}
    _require(build.get("identity") == _sha(canonical(unsigned)),
             "curry_handoff_build_record_identity_invalid")
    _require(build.get("source_before") == source_identity
             and build.get("source_after") == source_identity,
             "curry_handoff_build_source_mismatch")
    artifacts = build.get("artifacts")
    _require(isinstance(artifacts, dict)
             and artifacts == {
                 "runner": runner_hash,
                 "source_archive": archive_hash,
                 "source_file_list": list_hash,
             }, "curry_handoff_build_artifact_hash_mismatch")
    listing = strict_json(list_raw)
    source_files = source_identity.get("files")
    _require(isinstance(source_files, dict)
             and isinstance(listing, dict)
             and set(listing) == {
                 "schema_version", "kind", "head", "source_identity", "file_count", "files",
             }
             and listing.get("schema_version") == 1
             and listing.get("kind") == "workspace_source_archive"
             and listing.get("head") == source_identity.get("head")
             and listing.get("source_identity") == source_identity.get("identity")
             and type(listing.get("file_count")) is int
             and listing.get("file_count") == len(source_files)
             and listing.get("files") == source_files,
             "curry_handoff_source_file_list_mismatch")
    with zipfile.ZipFile(runner.parents[1] / SOURCE_ARCHIVE_RELATIVE) as archive:
        names = archive.namelist()
        _require(len(names) == len(set(names)) and set(names) == set(source_files),
                 "curry_handoff_source_archive_membership_mismatch")
        for name, expected_hash in source_files.items():
            _require(isinstance(name, str) and isinstance(expected_hash, str)
                     and HASH.fullmatch(expected_hash) is not None
                     and _sha(archive.read(name)) == expected_hash,
                     "curry_handoff_source_archive_member_mismatch")
    return {
        "runner_sha256": runner_hash,
        "build_record_sha256": build_hash,
        "build_record_identity": build["identity"],
        "source_identity": source_identity["identity"],
        "source_file_count": len(source_files),
        "inputs": [
            _record_input(repo, "runner", runner, runner_raw),
            _record_input(repo, "build_record", build_record, build_raw),
            _record_input(repo, "source_archive", archive_path, archive_raw),
            _record_input(repo, "source_file_list", list_path, list_raw),
        ],
    }


def _verify_stability(
    *, repo: Path, baseline: Path, output_root: Path,
    initial: dict, protected: dict[Path, str], stage2_receipt: Path,
    source_collector: Callable[[Path], dict] = stable_source,
) -> dict:
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree
    from ygo_eval.native_curry_option_validation import (
        _assert_option_verification_protected, _snapshot_curry_evidence,
    )
    from ygo_eval.curry_consumption_reservation import _snapshot_tree as reservation_snapshot

    _assert_option_verification_protected(protected, repo)
    current_workspace = source_collector(repo)
    current_baseline = _snapshot_tree(baseline)
    current_evidence = _snapshot_curry_evidence(baseline)
    v3 = repo / "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"
    current_reservation = reservation_snapshot(v3)
    receipt_absent = not stage2_receipt.exists() and not stage2_receipt.is_symlink()
    build_materials_stable = (
        _build_material_snapshot(output_root) == initial.get("build_materials")
    )
    _require(current_workspace == initial["workspace"], "curry_handoff_workspace_changed")
    _require(current_baseline == initial["baseline_tree"]
             and current_evidence == initial["baseline_evidence"],
             "curry_handoff_baseline_changed")
    _require(current_reservation == initial["reservation_tree"],
             "curry_handoff_reservation_changed")
    _require(receipt_absent, "curry_handoff_stage2_receipt_appeared")
    return {
        "workspace_stable": "passed",
        "baseline_stable": "passed",
        "reservation_stable": "passed",
        "ledger_stable": "passed",
        "runner_build_stable": "passed" if build_materials_stable else "failed",
        "stage2_receipt_absent_before": initial["stage2_receipt_absent"],
        "stage2_receipt_absent_after": receipt_absent,
    }


def _save_report(
    path: Path, report: dict, *, _sources: Any | None = None,
    repo: Path | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
) -> None:
    from ygo_eval.terminal_regression import immutable_write
    phase = "report_validation"
    write_completed = False
    try:
        validate_report(
            report, _sources=_sources, repo=repo, source_collector=source_collector,
            _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec,
        )
        phase = "exclusive_report_write"
        immutable_write(path, report)
        write_completed = True
        phase = "post_write_revalidation"
        saved = strict_json(safe_path(path).read_bytes())
        _require(saved == report, "curry_handoff_saved_report_mismatch")
        validate_report(
            saved, _sources=_sources, repo=repo, source_collector=source_collector,
            _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec,
        )
    except Exception as error:
        if isinstance(error, ReportSourceReconstructionError):
            phase = "source_reconstruction"
            diagnostic_error = error.original_error
        else:
            diagnostic_error = error
        if repo is None:
            repo = _absolute(Path(__file__).resolve().parents[2])
        from ygo_eval.curry_ledger_handoff_recovery import _create_publication_diagnostic
        output_state = "not_written"
        output_sha256 = None
        try:
            if path.is_symlink():
                output_state = "write_attempted_unverified"
            elif path.is_file():
                output_sha256 = _sha(path.read_bytes())
                output_state = (
                    "written_unverified" if write_completed
                    else "write_attempted_unverified"
                )
            elif path.exists() and phase == "exclusive_report_write":
                output_state = "write_attempted_unverified"
        except OSError:
            if write_completed or phase in {"exclusive_report_write", "post_write_revalidation"}:
                output_state = "write_attempted_unverified"
        try:
            diagnostic_id = _create_publication_diagnostic(
                repo, phase=phase, error=diagnostic_error, report=report,
                output_state=output_state, output_sha256=output_sha256,
            )
        except Exception:
            raise AuditPublicationError(
                phase, "publication_diagnostic_save_failed", None,
            ) from None
        phase_codes = {
            "report_validation": "report_validation_failed",
            "source_reconstruction": "source_reconstruction_failed",
            "exclusive_report_write": "exclusive_report_write_failed",
            "post_write_revalidation": "post_write_revalidation_failed",
        }
        raise AuditPublicationError(
            phase, phase_codes[phase], diagnostic_id,
        ) from None


class AuditPublicationError(RuntimeError):
    def __init__(self, phase: str, code: str, diagnostic_id: str | None):
        self.phase = phase
        self.code = code
        self.diagnostic_id = diagnostic_id
        super().__init__("audit_publication_diagnostic_saved")


class ReportSourceReconstructionError(ValueError):
    """Preserve the original failure while distinguishing source binding."""

    def __init__(self, original_error: BaseException):
        self.original_error = original_error
        value = str(original_error)
        code = value if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", value) else "source_reconstruction_failed"
        super().__init__(code)


def _run_audit_v1(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    process_runner: Callable[..., Any] | None = None,
    runner_build_verifier: Callable[..., Any] | None = None,
    stability_verifier: Callable[..., Any] | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Verify the fixed failed stage-2 input and run only its read-only audit mode."""
    repo = _absolute(repo or Path(__file__).resolve().parents[2])
    started = clock()
    baseline, output_root, runner, build_record = validate_cli_paths(args, repo)
    output_path = output_root / REPORT_RELATIVE
    report = _report_template(None)
    protected: dict[Path, str] = {}
    initial: dict | None = None
    source_before: dict | None = None
    build_materials_before: dict | None = None
    checkpoint = CHECK_NAMES[0]
    def mark(name: str, complete: bool = False) -> None:
        nonlocal checkpoint
        if name not in CHECK_NAMES:
            raise ValueError("curry_handoff_checkpoint_invalid")
        checkpoint = name
        if complete:
            report["checks"][name] = "passed"

    try:
        source_before = source_collector(repo)
        report["tool_identity"] = _source_summary(source_before)
        build_materials_before = _build_material_snapshot(output_root)
        baseline_snapshot = _snapshot_fixed_sources(repo, baseline, mark=mark)
        report["baseline"].update(baseline_snapshot["report_binding"])
        report["inputs"].extend(baseline_snapshot["inputs"])
        for check in CHECK_NAMES[:5]:
            report["checks"][check] = "passed"
        protected = baseline_snapshot["protected"]
        initial = baseline_snapshot["initial"]
        initial["build_materials"] = build_materials_before
        stage2_input = baseline_snapshot["stage2_input"]
        manifest = baseline_snapshot["manifest"]
        prepared_hash = baseline_snapshot["prepared_sha256"]

        checkpoint = "isolated_runner_build"
        if runner_build_verifier is None:
            runner_build = _verify_runner_build(
                runner, build_record, repo, source_before,
            )
        else:
            runner_build = runner_build_verifier(runner, build_record, repo)
        report["runner"].update({
            "sha256": runner_build["runner_sha256"],
            "build_record_sha256": runner_build["build_record_sha256"],
            "build_record_identity": runner_build["build_record_identity"],
            "source_identity": runner_build["source_identity"],
            "source_file_count": runner_build["source_file_count"],
        })
        report["inputs"].extend(runner_build.get("inputs", []))
        report["checks"]["isolated_runner_build"] = "passed"

        checkpoint = "saved_input_audit"
        identity_sha256 = manifest["assets"]["ordinary"].get("identity")
        _require(isinstance(identity_sha256, str) and HASH.fullmatch(identity_sha256),
                 "curry_handoff_expected_identity_invalid")
        diagnostics_dir = output_root / "process-diagnostics"
        try:
            diagnostics_dir.mkdir(parents=False, exist_ok=False)
        except OSError:
            raise ValueError("saved_input_diagnostic_directory_prelaunch_failed") from None
        result, process = _run_saved_input_audit(
            runner=runner, input_path=stage2_input,
            prepared_sha256=prepared_hash, context=manifest["context"],
            identity_sha256=identity_sha256, repo=repo,
            output_root=output_root,
            expected_input_sha256=baseline_snapshot["report_binding"]["stage2_input_sha256"],
            process_runner=process_runner,
        )
        record = process["record"]
        report["runner"].update({
            "return_code": record["return_code"],
            "process_status": record["status"],
            "diagnostic_sha256": process["diagnostic_sha256"],
            "stdout_sha256": process["stdout_sha256"],
            "stdout_bytes": process["stdout_bytes"],
            "stderr_sha256": process["stderr_sha256"],
            "stderr_bytes": process["stderr_bytes"],
            "trace": process["trace"],
            "saved_input_result": result,
        })
        report["checks"]["saved_input_audit"] = "passed"
        report["accounting"].update({
            "new_consumed": result["ledger"]["consumed"],
            "certified_consumed_including_new": 32 + result["ledger"]["consumed"],
            "planning_total": 39 + result["ledger"]["consumed"],
            "unknown": result["ledger"]["unknown"],
        })
        report["historical_failure"].update({
            "stage1_passed": True,
            "stage2_failed": True,
            "stage2_diagnostic": "runner_output_invalid_or_nonzero",
        })

        checkpoint = "input_stability"
        stability_args = {
            "repo": repo, "baseline": baseline, "output_root": output_root,
            "initial": initial, "protected": protected,
            "stage2_receipt": baseline / "research/stage-2.json",
        }
        if stability_verifier is None:
            report["stability"] = _verify_stability(
                **stability_args, source_collector=source_collector,
            )
        else:
            report["stability"] = stability_verifier(**stability_args)
        if source_collector(repo) != source_before:
            raise ValueError("curry_handoff_tool_source_changed")
        _require(_build_material_snapshot(output_root) == build_materials_before,
                 "curry_handoff_build_material_changed")
        _require(report["stability"].get("runner_build_stable") == "passed",
                 "curry_handoff_runner_build_unstable")
        report["checks"]["input_stability"] = "passed"
        report["status"] = "passed"
        report["failure_checkpoint"] = None
    except Exception as error:
        report["status"] = "failed"
        report["failure_checkpoint"] = checkpoint
        report["checks"][checkpoint] = "failed"
        code = str(error)
        report["diagnostic"] = code if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", code) else "audit_failed"
        if initial is not None:
            try:
                stability_args = {
                    "repo": repo, "baseline": baseline, "output_root": output_root,
                    "initial": initial, "protected": protected,
                    "stage2_receipt": baseline / "research/stage-2.json",
                }
                if stability_verifier is None:
                    report["stability"] = _verify_stability(
                        **stability_args, source_collector=source_collector,
                    )
                else:
                    report["stability"] = stability_verifier(**stability_args)
            except Exception:
                report["stability"].update({
                    "workspace_stable": "failed",
                    "baseline_stable": "failed",
                    "reservation_stable": "failed",
                    "ledger_stable": "failed",
                    "runner_build_stable": "failed",
                    "stage2_receipt_absent_after": False,
                })
    report["elapsed_seconds"] = round(max(0.0, clock() - started), 6)
    _save_report(output_path, report, repo=repo)
    return report


def _collect_v2_samples(
    *, repo: Path, baseline: Path, output_root: Path,
    previous_root: Path | None, reservation_root: Path | None,
    source_collector: Callable[[Path], dict], stage2_receipt: Path | None,
    ledger_path: Path | None,
    only_names: frozenset[str] | None = None,
) -> dict[str, Any]:
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree

    samples: dict[str, Any] = {}
    operations: dict[str, Callable[[], Any]] = {
        "workspace": lambda: source_collector(repo),
        "previous_failure_tree": lambda: _snapshot_tree(previous_root),
        "baseline_tree": lambda: _snapshot_tree(baseline),
        "reservation_tree": lambda: _snapshot_tree(reservation_root),
        "runner_build": lambda: _build_material_snapshot(output_root),
        "process_diagnostics": lambda: _snapshot_tree(
            output_root / "process-diagnostics",
        ),
        "stage2_receipt_absent": lambda: bool(
            stage2_receipt is not None
            and not stage2_receipt.exists() and not stage2_receipt.is_symlink()
        ),
        "ledger": lambda: _sha(safe_path(ledger_path).read_bytes())
        if ledger_path is not None and ledger_path.is_file() and not ledger_path.is_symlink()
        else None,
    }
    for name, operation in operations.items():
        if only_names is not None and name not in only_names:
            continue
        try:
            if name == "previous_failure_tree" and previous_root is None:
                raise FileNotFoundError
            if name == "reservation_tree" and reservation_root is None:
                raise FileNotFoundError
            samples[name] = operation()
        except Exception:
            samples[name] = None
    return samples


def _v2_recheck_statuses(
    *, before: dict[str, Any], repo: Path, baseline: Path, output_root: Path,
    previous_root: Path | None, reservation_root: Path | None,
    source_collector: Callable[[Path], dict], stage2_receipt: Path | None,
    ledger_path: Path | None,
) -> dict[str, Any]:
    result = {}
    for name in ("workspace", "previous_failure_tree", "baseline_tree",
                 "reservation_tree", "ledger", "runner_build", "process_diagnostics"):
        old = before.get(name)
        try:
            sample = _collect_v2_samples(
                repo=repo, baseline=baseline, output_root=output_root,
                previous_root=previous_root, reservation_root=reservation_root,
                source_collector=source_collector, stage2_receipt=stage2_receipt,
                ledger_path=ledger_path, only_names=frozenset({name}),
            )
            new = sample.get(name)
        except Exception:
            new = None
        if old is None:
            result[name] = "not_collected"
        elif new is None:
            result[name] = "recheck_failed"
        else:
            result[name] = "consistent" if old == new else "changed"
    try:
        receipt_sample = _collect_v2_samples(
            repo=repo, baseline=baseline, output_root=output_root,
            previous_root=previous_root, reservation_root=reservation_root,
            source_collector=source_collector, stage2_receipt=stage2_receipt,
            ledger_path=ledger_path, only_names=frozenset({"stage2_receipt_absent"}),
        )
        result["stage2_receipt_absent"] = receipt_sample.get("stage2_receipt_absent")
    except Exception:
        result["stage2_receipt_absent"] = None
    return result


def _collect_v3_samples(
    *, repo: Path, baseline: Path, output_root: Path,
    previous_root: Path | None, reservation_root: Path | None,
    previous_v2_root: Path, v2_final_root: Path,
    previous_v3_root: Path | None = None,
    previous_v4_root: Path | None = None,
    source_collector: Callable[[Path], dict], stage2_receipt: Path | None,
    ledger_path: Path | None, only_names: frozenset[str] | None = None,
) -> dict[str, Any]:
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree

    samples = _collect_v2_samples(
        repo=repo, baseline=baseline, output_root=output_root,
        previous_root=previous_root, reservation_root=reservation_root,
        source_collector=source_collector, stage2_receipt=stage2_receipt,
        ledger_path=ledger_path, only_names=only_names,
    )
    extra = {
        "previous_v2_failure_tree": previous_v2_root,
        "v2_final_source_tree": v2_final_root,
    }
    if previous_v3_root is not None:
        extra["previous_v3_failure_tree"] = previous_v3_root
    if previous_v4_root is not None:
        extra["previous_v4_failure_tree"] = previous_v4_root
    for name, root in extra.items():
        if only_names is not None and name not in only_names:
            continue
        try:
            samples[name] = _snapshot_tree(root)
        except Exception:
            samples[name] = None
    return samples


def _v3_recheck_statuses(
    *, before: dict[str, Any], repo: Path, baseline: Path, output_root: Path,
    previous_root: Path | None, reservation_root: Path | None,
    previous_v2_root: Path, v2_final_root: Path,
    previous_v3_root: Path | None = None,
    previous_v4_root: Path | None = None,
    source_collector: Callable[[Path], dict], stage2_receipt: Path | None,
    ledger_path: Path | None,
) -> dict[str, Any]:
    result = _v2_recheck_statuses(
        before=before, repo=repo, baseline=baseline, output_root=output_root,
        previous_root=previous_root, reservation_root=reservation_root,
        source_collector=source_collector, stage2_receipt=stage2_receipt,
        ledger_path=ledger_path,
    )
    for name, root in (
        ("previous_v2_failure_tree", previous_v2_root),
        ("v2_final_source_tree", v2_final_root),
    ):
        old = before.get(name)
        try:
            from ygo_eval.curry_asset_binding_audit import _snapshot_tree
            new = _snapshot_tree(root)
        except Exception:
            new = None
        if old is None:
            result[name] = "not_collected"
        elif new is None:
            result[name] = "recheck_failed"
        else:
            result[name] = "consistent" if old == new else "changed"
    if previous_v3_root is not None:
        old = before.get("previous_v3_failure_tree")
        try:
            from ygo_eval.curry_asset_binding_audit import _snapshot_tree
            new = _snapshot_tree(previous_v3_root)
        except Exception:
            new = None
        result["previous_v3_failure_tree"] = (
            "not_collected" if old is None else
            "recheck_failed" if new is None else
            "consistent" if old == new else "changed"
        )
    if previous_v4_root is not None:
        old = before.get("previous_v4_failure_tree")
        try:
            from ygo_eval.curry_asset_binding_audit import _snapshot_tree
            new = _snapshot_tree(previous_v4_root)
        except Exception:
            new = None
        result["previous_v4_failure_tree"] = (
            "not_collected" if old is None else
            "recheck_failed" if new is None else
            "consistent" if old == new else "changed"
        )
    return result


def _run_audit_v2(
    args: argparse.Namespace,
    repo: Path,
    *,
    process_runner: Callable[..., Any] | None,
    runner_build_verifier: Callable[..., Any] | None,
    stability_verifier: Callable[..., Any] | None,
    source_collector: Callable[[Path], dict],
    clock: Callable[[], float],
    _sources: Any | None = None,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    _audit_version: int = 2,
) -> dict:
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree

    started = clock()
    baseline = repo / BASELINE_RELATIVE
    version_spec = _version_spec(_audit_version)
    output_root = repo / version_spec.output_root
    runner = output_root / RUNNER_RELATIVE
    build_record = output_root / BUILD_RECORD_RELATIVE
    output_path = output_root / REPORT_RELATIVE
    report = _report_template(None, _audit_version, _sources=_sources)
    report["tool_identity"] = None
    checkpoint = version_spec.checks[0]
    samples: dict[str, Any] = {}
    source_before = None
    previous_root: Path | None = version_spec.source_root(repo, "previous_v1")
    reservation_root: Path | None = repo / (
        "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"
    )
    previous_v2_root = (
        version_spec.source_root(repo, "previous_v2")
        if version_spec.has_source_layer("previous_v2") else None
    )
    v2_final_root = (
        version_spec.source_root(repo, "v2_final")
        if version_spec.has_source_layer("v2_final") else None
    )
    previous_v3_root = (
        version_spec.source_root(repo, "previous_v3")
        if version_spec.has_source_layer("previous_v3") else None
    )
    previous_v4_root = (
        version_spec.source_root(repo, "previous_v4")
        if version_spec.has_source_layer("previous_v4") else None
    )
    scope_research = repo / (
        "data/runtime/p1-curry-option-verification-native-2026-10-25/research"
    )
    stage2_receipt: Path | None = scope_research / "stage-2.json"
    ledger_path: Path | None = scope_research / "calls.jsonl"
    protected: dict[Path, str] = {}
    initial: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    process: dict[str, Any] | None = None

    def capture_process_record(record: dict[str, Any]) -> None:
        stdout_record = record.get("stdout") if isinstance(record.get("stdout"), dict) else {}
        stderr_record = record.get("stderr") if isinstance(record.get("stderr"), dict) else {}
        capture = report["runner"]["process_capture"]
        capture.update({
            "metadata_path": record.get("metadata_path"),
            "metadata_sha256": None,
            "stdout_path": stdout_record.get("path"),
            "stderr_path": stderr_record.get("path"),
        })
        runner_summary = {
            "return_code": record.get("return_code"),
            "process_status": record.get("status"),
            "diagnostic_sha256": _sha(canonical(record)),
            "stdout_sha256": stdout_record.get("sha256"),
            "stdout_bytes": stdout_record.get("bytes"),
            "stderr_sha256": stderr_record.get("sha256"),
            "stderr_bytes": stderr_record.get("bytes"),
        }
        if version_spec.tracks_process_attempt:
            runner_summary["process_error_code"] = record.get("error_code")
        report["runner"].update(runner_summary)
        capture_paths = {
            "new_runner_capture_metadata": record.get("metadata_path"),
            "new_runner_stdout": stdout_record.get("path"),
            "new_runner_stderr": stderr_record.get("path"),
        }
        _require(version_spec.captures_process_diagnostics,
                 "curry_handoff_process_capture_unexpected")
        for role in (
            "new_runner_capture_metadata", "new_runner_stdout", "new_runner_stderr",
        ):
            if role not in version_spec.process_input_roles:
                continue
            relative = capture_paths[role]
            _require(isinstance(relative, str), "saved_input_diagnostic_paths_invalid")
            path = safe_path(output_root.joinpath(*PurePosixPath(relative).parts))
            raw = path.read_bytes()
            if role == "new_runner_capture_metadata":
                capture["metadata_sha256"] = _sha(raw)
            report["inputs"].append(_record_input(repo, role, path, raw))
        samples["process_diagnostics"] = _snapshot_tree(
            output_root / "process-diagnostics",
        )

    def mark(name: str, complete: bool = False) -> None:
        nonlocal checkpoint
        if name == "acceptance_delivery":
            if complete:
                report["checks"][name] = "passed"
            return
        mapping = {
            "reservation_and_history": "reservation_and_history",
            "frozen_scope_inputs": "frozen_scope_inputs",
            "stage1_parent_receipt": "stage1_parent_receipt",
            "stage2_saved_intent": "stage2_saved_intent",
        }
        if name in ("bundle_layout", "previous_v4_failed_source"):
            checkpoint = name
            if complete:
                report["checks"][name] = "passed"
            return
        target = mapping.get(name)
        _require(target is not None, "curry_handoff_checkpoint_invalid")
        checkpoint = target
        if complete:
            report["checks"][target] = "passed"

    try:
        # The output location is derived from the fixed version spec before
        # caller paths are checked, so a malformed CLI cannot redirect failure
        # evidence to an attacker-controlled path.
        validate_cli_paths(args, repo)
        if "bundle_layout" in version_spec.checks:
            report["checks"]["bundle_layout"] = "passed"
        source_before = source_collector(repo)
        report["tool_identity"] = _source_summary(source_before)
        if version_spec.has_source_layer("previous_v4"):
            checkpoint = "previous_v4_failed_source"
            previous_v4 = _verify_previous_v4_failed_source(
                repo, version_spec=version_spec, _sources=_sources,
            )
            _require(previous_v4["root"] == previous_v4_root,
                     "curry_handoff_previous_v4_failure_root_changed")
            report["previous_v4_failed_source"].update(previous_v4["record"])
            report["inputs"].extend(previous_v4["inputs"])
            report["checks"][checkpoint] = "passed"
        if version_spec.has_source_layer("previous_v3"):
            checkpoint = "previous_v3_failed_source"
            previous_v3 = _verify_previous_v3_failed_source(repo, _sources=_sources)
            _require(previous_v3["root"] == previous_v3_root,
                     "curry_handoff_previous_v3_failure_root_changed")
            report["previous_v3_failed_source"].update(previous_v3["record"])
            report["inputs"].extend(previous_v3["inputs"])
            report["checks"][checkpoint] = "passed"
        checkpoint = (
            "previous_failed_sources" if version_spec.has_source_layer("previous_v2")
            else "previous_failed_source"
        )
        collect = (
            _collect_v3_samples if version_spec.has_source_layer("previous_v2")
            else _collect_v2_samples
        )
        collect_kwargs = dict(
            repo=repo, baseline=baseline, output_root=output_root,
            previous_root=previous_root, reservation_root=reservation_root,
            source_collector=source_collector, stage2_receipt=stage2_receipt,
            ledger_path=ledger_path,
        )
        if version_spec.has_source_layer("previous_v2"):
            collect_kwargs.update(previous_v2_root=previous_v2_root, v2_final_root=v2_final_root)
            if version_spec.has_source_layer("previous_v3"):
                collect_kwargs.update(previous_v3_root=previous_v3_root)
            if version_spec.has_source_layer("previous_v4"):
                collect_kwargs.update(previous_v4_root=previous_v4_root)
        samples = collect(**collect_kwargs)
        if version_spec.has_source_layer("previous_v2"):
            v1 = _verify_v1_audit_source_v3(repo, _sources=_sources)
            _require(v1["root"] == previous_root, "curry_handoff_v1_failure_root_changed")
            report["previous_failed_attempt"].update(v1["record"])
            report["inputs"].extend(v1["inputs"])
            v2 = _verify_v2_audit_source_v3(repo, _sources=_sources)
            _require(v2["root"] == previous_v2_root, "curry_handoff_v2_failure_root_changed")
            report["previous_v2_failed_attempt"].update(v2["record"])
            report["inputs"].extend(v2["inputs"])
        else:
            previous = _verify_previous_failed_attempt(repo, _sources=_sources)
            _require(previous["root"] == previous_root,
                     "curry_handoff_previous_failure_root_changed")
            report["previous_failed_attempt"].update(previous["record"])
            report["inputs"].extend(previous["inputs"])
        report["checks"][checkpoint] = "passed"

        if version_spec.has_source_layer("previous_v2"):
            checkpoint = "v2_final_source"
            final_source = _verify_v2_final_source_v3(repo, _sources=_sources)
            report["v2_final_source"].update(final_source["record"])
            report["inputs"].extend(final_source["inputs"])
            report["checks"][checkpoint] = "passed"

        checkpoint = "acceptance_delivery"
        baseline_tree_before = _snapshot_tree(baseline)
        report["checks"][checkpoint] = "not_run"
        acceptance, delivery, acceptance_raw, delivery_raw = _verify_acceptance_delivery(
            baseline, _sources=_sources,
        )
        report["baseline"]["acceptance_sha256"] = _sha(acceptance_raw)
        report["baseline"]["delivery_sha256"] = _sha(delivery_raw)
        report["checks"][checkpoint] = "passed"

        checkpoint = "dual_timepoint_sources"
        dual = _verify_final_build_chain(
            repo, baseline, acceptance, delivery, _sources=_sources,
        )
        # The verifier carries additional internal pins (the archived static
        # return code and lock-source hash) for later checks. Keep the public
        # dual-timepoint object on its versioned contract and bind those extra
        # facts in their dedicated report fields/input records instead.
        dual_report_fields = set(report["dual_timepoint_sources"])
        report["dual_timepoint_sources"].update({
            key: value for key, value in dual["record"].items()
            if key in dual_report_fields
        })
        report["inputs"].extend(dual["inputs"])
        reservation_root = dual["reservation_root"]
        stage2_receipt = dual["stage2_receipt"]
        ledger_path = dual["ledger_path"]
        report["checks"][checkpoint] = "passed"

        report["checks"]["acceptance_delivery"] = "passed"
        baseline_snapshot = _snapshot_fixed_sources(
            repo, baseline, mark=mark, _sources=_sources,
            _option_spec=_option_spec, _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _candidate_spec=_candidate_spec,
            source_collector=source_collector,
            stdout_contract=version_spec.stdout_contract,
            _preverified_baseline=(acceptance, delivery, acceptance_raw, delivery_raw),
        )
        report["baseline"].update(baseline_snapshot["report_binding"])
        # Acceptance and delivery are recorded by this fixed snapshot exactly
        # once; duplicate roles make provenance ambiguous and are rejected.
        report["inputs"].extend(baseline_snapshot["inputs"])
        _require(dual["reservation_root"] == reservation_root
                 and dual["stage2_receipt"] == stage2_receipt
                 and dual["ledger_path"] == ledger_path,
                 "curry_handoff_fixed_scope_paths_changed")
        protected = baseline_snapshot["protected"]
        initial = baseline_snapshot["initial"]
        initial["build_materials"] = _build_material_snapshot(output_root)
        initial["previous_failure_tree"] = samples.get("previous_failure_tree")
        if version_spec.has_source_layer("previous_v3"):
            initial["previous_v3_failure_tree"] = samples.get("previous_v3_failure_tree")
        if version_spec.has_source_layer("previous_v4"):
            initial["previous_v4_failure_tree"] = samples.get("previous_v4_failure_tree")
        if samples.get("workspace") is not None:
            initial["workspace"] = samples["workspace"]
        initial["baseline_tree"] = samples.get("baseline_tree")
        initial["reservation_tree"] = samples.get("reservation_tree")
        initial["stage2_receipt_absent"] = samples.get("stage2_receipt_absent")
        initial["ledger_sha256"] = samples.get("ledger")
        stage2_input = baseline_snapshot["stage2_input"]
        manifest = baseline_snapshot["manifest"]
        prepared_hash = baseline_snapshot["prepared_sha256"]
        report["historical_failure"].update({
            "stage1_passed": True,
            "stage2_failed": True,
            "stage2_diagnostic": "runner_output_invalid_or_nonzero",
            "acceptance_runner_return_code_claimed": acceptance[
                "native_result"]["stage_2"]["runner_return_code"],
            "archived_static_return_code": dual["record"]["archived_static_return_code"],
            "historical_actual_exit_code": None,
            "historical_exit_code_certified": False,
            "old_failure_rewritten": False,
        })

        checkpoint = "isolated_runner_build"
        if runner_build_verifier is None:
            runner_build = _verify_runner_build(runner, build_record, repo, source_before)
        else:
            runner_build = runner_build_verifier(runner, build_record, repo)
        report["runner"].update({
            "sha256": runner_build["runner_sha256"],
            "build_record_sha256": runner_build["build_record_sha256"],
            "build_record_identity": runner_build["build_record_identity"],
            "source_identity": runner_build["source_identity"],
            "source_file_count": runner_build["source_file_count"],
        })
        role_map = {
            "runner": "new_runner", "build_record": "new_build_record",
            "source_archive": "new_source_archive", "source_file_list": "new_source_file_list",
        }
        for item in runner_build.get("inputs", []):
            report["inputs"].append({**item, "role": role_map.get(item["role"], item["role"])})
        report["checks"][checkpoint] = "passed"

        checkpoint = "saved_input_audit"
        identity_sha256 = manifest["assets"]["ordinary"].get("identity")
        _require(isinstance(identity_sha256, str) and HASH.fullmatch(identity_sha256),
                 "curry_handoff_expected_identity_invalid")
        _create_process_diagnostics_dir(output_root, audit_version=_audit_version)

        def mark_process_attempted() -> None:
            report["runner"]["process_attempted"] = True

        result, process = _run_saved_input_audit(
            runner=runner, input_path=stage2_input, prepared_sha256=prepared_hash,
            context=manifest["context"], identity_sha256=identity_sha256, repo=repo,
            output_root=output_root,
            expected_input_sha256=baseline_snapshot["report_binding"]["stage2_input_sha256"],
            process_runner=process_runner,
            stable_prelaunch_diagnostics=version_spec.tracks_process_attempt,
            on_attempted=(
                mark_process_attempted if version_spec.tracks_process_attempt else None
            ),
            on_captured=capture_process_record,
        )
        record = process["record"]
        runner_summary = {
            "return_code": record["return_code"],
            "process_status": record["status"],
            "diagnostic_sha256": process["diagnostic_sha256"],
            "stdout_sha256": process["stdout_sha256"], "stdout_bytes": process["stdout_bytes"],
            "stderr_sha256": process["stderr_sha256"], "stderr_bytes": process["stderr_bytes"],
            "trace": process["trace"], "saved_input_result": result,
        }
        if version_spec.tracks_process_attempt:
            runner_summary["process_error_code"] = record["error_code"]
        report["runner"].update(runner_summary)
        report["checks"][checkpoint] = "passed"
        report["accounting"].update({
            "new_consumed": result["ledger"]["consumed"],
            "certified_consumed_including_new": 32 + result["ledger"]["consumed"],
            "planning_total": 39 + result["ledger"]["consumed"],
            "unknown": result["ledger"]["unknown"],
        })

        checkpoint = "input_stability"
        stability_args = {
            "repo": repo, "baseline": baseline, "output_root": output_root,
            "initial": initial, "protected": protected,
            "stage2_receipt": stage2_receipt,
        }
        if stability_verifier is None:
            report["stability"] = _verify_stability(
                **stability_args, source_collector=source_collector,
            )
        else:
            report["stability"] = stability_verifier(**stability_args)
        if version_spec.has_source_layer("previous_v3"):
            from ygo_eval.curry_asset_binding_audit import _snapshot_tree
            previous_v3_now = _snapshot_tree(previous_v3_root)
            previous_v3_before = initial.get("previous_v3_failure_tree")
            previous_v3_state = (
                "consistent" if previous_v3_before == previous_v3_now else "changed"
            )
            report["stability_rechecks"] = report.get("stability_rechecks", {})
            report["stability_rechecks"]["previous_v3_failure_tree"] = previous_v3_state
            report["stability"]["previous_v3_failure_stable"] = (
                "passed" if previous_v3_state == "consistent" else "failed"
            )
        if version_spec.has_source_layer("previous_v4"):
            from ygo_eval.curry_asset_binding_audit import _snapshot_tree
            previous_v4_now = _snapshot_tree(previous_v4_root)
            previous_v4_before = initial.get("previous_v4_failure_tree")
            previous_v4_state = (
                "consistent" if previous_v4_before == previous_v4_now else "changed"
            )
            report["stability_rechecks"]["previous_v4_failure_tree"] = previous_v4_state
            report["stability"]["previous_v4_failure_stable"] = (
                "passed" if previous_v4_state == "consistent" else "failed"
            )
        report["checks"][checkpoint] = "passed"
        report["status"] = "passed"
        report["failure_checkpoint"] = None
    except Exception as error:
        report["status"] = "failed"
        report["failure_checkpoint"] = checkpoint
        if checkpoint in report["checks"]:
            report["checks"][checkpoint] = "failed"
        code = str(error)
        report["diagnostic"] = code if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", code) else "audit_failed"

    try:
        recheck = (
            _v3_recheck_statuses if version_spec.has_source_layer("previous_v2")
            else _v2_recheck_statuses
        )
        recheck_kwargs = dict(
            before=samples, repo=repo, baseline=baseline, output_root=output_root,
            previous_root=previous_root, reservation_root=reservation_root,
            source_collector=source_collector, stage2_receipt=stage2_receipt,
            ledger_path=ledger_path,
        )
        if version_spec.has_source_layer("previous_v2"):
            recheck_kwargs.update(previous_v2_root=previous_v2_root, v2_final_root=v2_final_root)
            if version_spec.has_source_layer("previous_v3"):
                recheck_kwargs.update(previous_v3_root=previous_v3_root)
            if version_spec.has_source_layer("previous_v4"):
                recheck_kwargs.update(previous_v4_root=previous_v4_root)
        report["stability_rechecks"] = recheck(**recheck_kwargs)
    except Exception:
        report["stability_rechecks"] = {
            name: ("not_collected" if samples.get(name) is None else "recheck_failed")
            for name in (
                "workspace", "previous_failure_tree", "baseline_tree",
                "reservation_tree", "ledger", "runner_build", "process_diagnostics",
            )
        }
        report["stability_rechecks"]["stage2_receipt_absent"] = None
        if version_spec.has_source_layer("previous_v2"):
            report["stability_rechecks"].update({
                "previous_v2_failure_tree": (
                    "not_collected" if samples.get("previous_v2_failure_tree") is None
                    else "recheck_failed"
                ),
                "v2_final_source_tree": (
                    "not_collected" if samples.get("v2_final_source_tree") is None
                    else "recheck_failed"
                ),
            })
        if version_spec.has_source_layer("previous_v3"):
            report["stability_rechecks"]["previous_v3_failure_tree"] = (
                "not_collected" if samples.get("previous_v3_failure_tree") is None
                else "recheck_failed"
            )
        if version_spec.has_source_layer("previous_v4"):
            report["stability_rechecks"]["previous_v4_failure_tree"] = (
                "not_collected" if samples.get("previous_v4_failure_tree") is None
                else "recheck_failed"
            )
    rechecks = report["stability_rechecks"]
    stability_map = {
        "workspace_stable": "workspace",
        "baseline_stable": "baseline_tree",
        "reservation_stable": "reservation_tree",
        "ledger_stable": "ledger",
        "runner_build_stable": "runner_build",
        "process_diagnostics_stable": "process_diagnostics",
    }
    if version_spec.has_source_layer("previous_v2"):
        stability_map.update({
            "previous_v2_failure_stable": "previous_v2_failure_tree",
            "v2_final_source_stable": "v2_final_source_tree",
        })
    if version_spec.has_source_layer("previous_v3"):
        stability_map["previous_v3_failure_stable"] = "previous_v3_failure_tree"
    if version_spec.has_source_layer("previous_v4"):
        stability_map["previous_v4_failure_stable"] = "previous_v4_failure_tree"
    for target, name in stability_map.items():
        state = rechecks.get(name)
        report["stability"][target] = (
            "not_checked" if state == "not_collected" else
            "passed" if state == "consistent" else "failed"
        )
    report["stability"]["stage2_receipt_absent_before"] = samples.get(
        "stage2_receipt_absent",
    )
    report["stability"]["stage2_receipt_absent_after"] = rechecks.get(
        "stage2_receipt_absent",
    )
    if report["status"] == "passed":
        try:
            required_rechecks = [
                "workspace", "previous_failure_tree", "baseline_tree", "reservation_tree",
                "ledger", "runner_build", "process_diagnostics",
            ]
            if version_spec.has_source_layer("previous_v2"):
                required_rechecks.extend(("previous_v2_failure_tree", "v2_final_source_tree"))
                if version_spec.has_source_layer("previous_v3"):
                    required_rechecks.append("previous_v3_failure_tree")
                if version_spec.has_source_layer("previous_v4"):
                    required_rechecks.append("previous_v4_failure_tree")
            _require(all(report["stability_rechecks"][name] == "consistent" for name in (
                *required_rechecks,
            )) and report["stability_rechecks"]["stage2_receipt_absent"] is True,
                     "curry_handoff_input_stability_failed")
        except Exception as error:
            report["status"] = "failed"
            report["failure_checkpoint"] = "input_stability"
            report["checks"]["input_stability"] = "failed"
            code = str(error)
            report["diagnostic"] = (
                code if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", code)
                else "audit_failed"
            )
    report["elapsed_seconds"] = round(max(0.0, clock() - started), 6)
    _save_report(
        output_path, report, _sources=_sources, repo=repo,
        source_collector=source_collector,
        _reservation_profile=_reservation_profile,
        _reservation_spec=_reservation_spec, _option_spec=_option_spec,
        _candidate_spec=_candidate_spec,
    )
    return report


def run_audit(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    process_runner: Callable[..., Any] | None = None,
    runner_build_verifier: Callable[..., Any] | None = None,
    stability_verifier: Callable[..., Any] | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    clock: Callable[[], float] = time.monotonic,
    _sources: Any | None = None,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
) -> dict:
    repo = _absolute(repo or Path(__file__).resolve().parents[2])
    version = _version_spec(getattr(args, "report_version", 1)).version
    if version in (2, 3, 4, 5):
        return _run_audit_v2(
            args, repo, process_runner=process_runner,
            runner_build_verifier=runner_build_verifier,
            stability_verifier=stability_verifier,
            source_collector=source_collector, clock=clock,
            _sources=_sources, _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec, _audit_version=version,
        )
    return _run_audit_v1(
        args, repo, process_runner=process_runner,
        runner_build_verifier=runner_build_verifier,
        stability_verifier=stability_verifier,
        source_collector=source_collector, clock=clock,
    )


def _snapshot_fixed_sources(
    repo: Path, baseline: Path, *, mark: Callable[[str, bool], None],
    _sources: Any | None = None, _option_spec: Any | None = None,
    _reservation_profile: Any | None = None, _reservation_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    source_collector: Callable[[Path], dict] = stable_source,
    _preverified_baseline: tuple[dict, dict, bytes, bytes] | None = None,
    stdout_contract: str = "legacy-v1",
) -> dict[str, Any]:
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree
    from ygo_eval.native_curry_option_validation import (
        OPTION_VERIFICATION_SCOPE, _assert_option_verification_protected,
        _process_diagnostics_with_hash, _report_kind,
        _snapshot_curry_evidence, _verify_curry_basic_receipt,
        _verify_curry_stage_artifacts, _verify_option_verification_baseline,
        _verify_saved_confirmation_build_and_archive,
        _verify_saved_option_verification_inputs, derive_curry_stage_request,
        validate_curry_report, validate_curry_stage_receipt,
    )
    from ygo_eval.native_tenki_placement_validation import (
        _diagnostic_hash, _verify_stage_intent,
    )
    option_spec = _option_spec or OPTION_VERIFICATION_SCOPE

    _require(baseline == repo / BASELINE_RELATIVE and baseline.is_dir(),
             "curry_handoff_fixed_baseline_missing")
    baseline_tree_before = _snapshot_tree(baseline)
    if _preverified_baseline is None:
        mark("acceptance_delivery", False)
        acceptance, delivery, acceptance_raw, delivery_raw = _verify_acceptance_delivery(
            baseline, _sources=_sources,
        )
        mark("acceptance_delivery", True)
    else:
        acceptance, delivery, acceptance_raw, delivery_raw = _preverified_baseline

    mark("reservation_and_history", False)
    reservation_root = repo / option_spec.baseline_root
    reservation_tree_before = _snapshot_tree(reservation_root)
    reservation, protected = _verify_option_verification_baseline(
        repo, reservation_root, _profile=_reservation_profile,
        _reservation_spec=_reservation_spec, _sources=_sources,
        _option_spec=option_spec, _candidate_spec=_candidate_spec,
        source_collector=source_collector,
    )
    v3_inputs = _v3_source_input_records(repo, reservation_root)
    mark("reservation_and_history", True)

    mark("frozen_scope_inputs", False)
    root, paths = _fixed_option_paths(repo)
    research = paths["research"]
    manifest_path = safe_path(research / "manifest.json")
    manifest_raw = manifest_path.read_bytes()
    manifest = strict_json(manifest_raw)
    validate_curry_report(manifest, repo=repo, spec=option_spec, _sources=_sources)
    prepared_path = safe_path(research / "prepared.json")
    prepared_raw = prepared_path.read_bytes()
    prepared = strict_json(prepared_raw)
    validate_curry_report(prepared, repo=repo, spec=option_spec, _sources=_sources)
    manifest_hash = _sha(manifest_raw)
    prepared_hash = _sha(prepared_raw)
    _require(acceptance.get("context") == manifest.get("context")
             or acceptance.get("preflight", {}).get("context") == manifest.get("context"),
             "curry_handoff_acceptance_context_mismatch")
    _require(acceptance.get("preflight", {}).get("manifest_sha256") == manifest_hash
             and acceptance.get("preflight", {}).get("prepared_sha256") == prepared_hash
             and acceptance.get("preflight", {}).get("prepared") is True
             and acceptance.get("preflight", {}).get("execution_ready_at_prepare") is True
             and acceptance.get("preflight", {}).get("passed") is True
             and acceptance.get("preflight", {}).get("native_calls") == 0
             and acceptance.get("preflight", {}).get("input_roles") == 21,
             "curry_handoff_acceptance_preflight_binding_invalid")
    _require(delivery.get("acceptance") == {
                 "path": (BASELINE_RELATIVE / ACCEPTANCE_RELATIVE).as_posix(),
                 # The acceptance bytes were already authenticated by the
                 # acceptance_delivery checkpoint. Rebind this reference to
                 # those exact bytes instead of duplicating the production
                 # anchor here; this also keeps the private synthetic source
                 # profile coherent without weakening the earlier pin check.
                 "sha256": _sha(acceptance_raw),
                 "bytes": len(acceptance_raw),
             },
             "curry_handoff_delivery_acceptance_binding_invalid")
    saved_build = _verify_saved_confirmation_build_and_archive(root, manifest, paths)
    source_args = argparse.Namespace(
        preparation=repo / "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json",
        cases=repo / "data/runtime/baseline-2026-10-19/research/frozen-cases.json",
        core_source=repo / "data/tmp/ocgcore-source/operations.cpp",
    )
    protected = _verify_saved_option_verification_inputs(
        source_args, repo, root, paths, manifest, protected,
        spec=option_spec, _sources=_sources,
        archived_source_hashes=(
            saved_build.get("source_file_hashes")
            if stdout_contract == "verification-accounting-v1"
            and option_spec.scope == OPTION_VERIFICATION_SCOPE.scope
            else None
        ),
    )
    mark("frozen_scope_inputs", True)

    mark("stage1_parent_receipt", False)
    stage1_summary = strict_json(safe_path(research / "summary.json").read_bytes())
    validate_curry_report(stage1_summary, repo=repo, spec=option_spec, _sources=_sources)
    summaries = stage1_summary.get("stages")
    _require(isinstance(summaries, list) and len(summaries) >= 1
             and summaries[0].get("stage") == 1
             and summaries[0].get("successful") is True,
             "curry_handoff_stage1_summary_invalid")
    stage1_artifacts = _verify_curry_stage_artifacts(
        root=root, research=research, manifest=manifest, stage=1,
        expected_request=manifest["request"], stage_summary=summaries[0],
        spec=option_spec,
        stdout_contract=stdout_contract,
        stdout_contract_spec=option_spec,
        report_kind=_report_kind(option_spec, "stage_report"),
        validate_report=lambda value: validate_curry_report(
            value, repo=repo, spec=option_spec, _sources=_sources,
        ),
        diagnostic_hash=lambda root_path, record: _diagnostic_hash(
            root_path, record, option_spec,
        ),
    )
    v4_stage1_inputs: list[dict[str, Any]] = []
    if stdout_contract == "verification-accounting-v1":
        process_record = stage1_artifacts["diagnostic_record"]
        sidecar_path = safe_path(root / "stage-1-process-diagnostic.json")
        sidecar_raw = sidecar_path.read_bytes()
        _require(strict_json(sidecar_raw) == process_record,
                 "curry_handoff_stage1_diagnostic_sidecar_mismatch")
        metadata_path = safe_path(root / process_record["metadata_path"])
        metadata_raw = metadata_path.read_bytes()
        _require(strict_json(metadata_raw) == process_record,
                 "curry_handoff_stage1_diagnostic_metadata_mismatch")
        stdout_path = safe_path(root / process_record["stdout"]["path"])
        stderr_path = safe_path(root / process_record["stderr"]["path"])
        for role, path, raw in (
            ("stage1_process_sidecar", sidecar_path, sidecar_raw),
            ("stage1_process_metadata", metadata_path, metadata_raw),
            ("stage1_process_stdout", stdout_path, stdout_path.read_bytes()),
            ("stage1_process_stderr", stderr_path, stderr_path.read_bytes()),
        ):
            v4_stage1_inputs.append(_record_input(repo, role, path, raw))
    stage1_request = strict_json(safe_path(research / "stage-1-request.json").read_bytes())
    stage1_receipt = stage1_artifacts["receipt"]
    _verify_curry_basic_receipt(stage1_receipt, stage1_request,
                                manifest["context"], 1, option_spec)
    validate_curry_stage_receipt(
        stage1_receipt, stage1_request, manifest["context"], 1,
        manifest["assets"]["ordinary"], option_spec,
    )
    _require(stage1_request == manifest.get("request"), "curry_handoff_stage1_request_invalid")
    mark("stage1_parent_receipt", True)

    mark("stage2_saved_intent", False)
    request_path = safe_path(research / "stage-2-request.json")
    input_path = safe_path(research / "stage-2-input.json")
    seal_path = safe_path(research / "stage-2-input-seal.json")
    stage_report_path = safe_path(research / "stage-2-report.json")
    request_raw = request_path.read_bytes()
    input_raw = input_path.read_bytes()
    seal_raw = seal_path.read_bytes()
    stage_report_raw = stage_report_path.read_bytes()
    request = strict_json(request_raw)
    invocation = strict_json(input_raw)
    seal = strict_json(seal_raw)
    stage_report = strict_json(stage_report_raw)
    expected_request = derive_curry_stage_request(2, stage1_receipt, option_spec)
    _require(request == expected_request, "curry_handoff_stage2_parent_request_mismatch")
    _verify_stage_intent(input_path, research, manifest["context"], 2,
                         expected_request, manifest["assets"]["ordinary"],
                         manifest["started_at"], option_spec)
    _require(invocation.get("request") == expected_request
             and invocation.get("context") == manifest["context"]
             and invocation.get("stage") == 2
             and invocation.get("batch_kind") == option_spec.batch_kind
             and invocation.get("expected_identity") == manifest["assets"]["ordinary"]
             and seal.get("kind") == option_spec.input_seal_kind,
             "curry_handoff_stage2_input_binding_invalid")
    validate_curry_report(stage_report, repo=repo, spec=option_spec, _sources=_sources)
    _require(stage_report.get("kind") == _report_kind(option_spec, "stage_report")
             and stage_report.get("context") == manifest["context"]
             and stage_report.get("stage") == 2
             and stage_report.get("successful") is False
             and stage_report.get("diagnostic") == "runner_output_invalid_or_nonzero"
             and stage_report.get("receipt_sha256") is None
             and stage_report.get("independent_replay_matches") is None,
             "curry_handoff_stage2_failure_record_invalid")
    receipt_path = research / "stage-2.json"
    receipt_absent = not receipt_path.exists() and not receipt_path.is_symlink()
    _require(receipt_absent, "curry_handoff_stage2_receipt_unexpected")
    process_records = _process_diagnostics_with_hash(
        root, stage_report.get("diagnostic_sha256"), "normal", option_spec,
        diagnostic_hash=lambda root_path, record: _diagnostic_hash(
            root_path, record, option_spec,
        ),
    )
    _require(len(process_records) == 1, "curry_handoff_stage2_diagnostic_invalid")
    sidecar = strict_json(safe_path(root / "stage-2-process-diagnostic.json").read_bytes())
    _require(sidecar == process_records[0]
             and _diagnostic_hash(root, sidecar, OPTION_VERIFICATION_SCOPE)
             == stage_report.get("diagnostic_sha256"),
             "curry_handoff_stage2_diagnostic_sidecar_invalid")
    ledger_path = safe_path(research / "calls.jsonl")
    ledger_raw = ledger_path.read_bytes()

    _assert_option_verification_protected(protected, repo)
    protected.update({
        _absolute(reservation_root): _sha(canonical(reservation_tree_before)),
        _absolute(ledger_path): _sha(ledger_raw),
    })
    # These exact snapshots are repeated after the process. Protected identities
    # separately retain the legacy ledger and all nine historical source pins.
    initial = {
        "workspace": source_collector(repo),
        "baseline_tree": baseline_tree_before,
        "baseline_evidence": _snapshot_curry_evidence(baseline),
        "reservation_tree": reservation_tree_before,
        "stage2_receipt_absent": receipt_absent,
    }
    _require(_snapshot_tree(baseline) == baseline_tree_before
             and _snapshot_tree(reservation_root) == reservation_tree_before,
             "curry_handoff_source_changed_during_check")
    _require(_snapshot_curry_evidence(baseline) == initial["baseline_evidence"],
             "curry_handoff_evidence_changed_during_check")
    mark("stage2_saved_intent", True)
    return {
        "report_binding": {
            "acceptance_sha256": _source_role_sha256(
                _sources.child("baseline") if _sources is not None else None,
                "baseline_acceptance", ACCEPTANCE_SHA256,
            ),
            "delivery_sha256": _source_role_sha256(
                _sources.child("baseline") if _sources is not None else None,
                "baseline_delivery", DELIVERY_SHA256,
            ),
            "context": manifest["context"],
            "manifest_sha256": manifest_hash,
            "prepared_sha256": prepared_hash,
            "stage1_receipt_sha256": _sha(safe_path(research / "stage-1.json").read_bytes()),
            "stage2_input_sha256": _sha(input_raw),
            "stage2_request_sha256": _sha(request_raw),
        },
        "inputs": [
            _record_input(repo, "acceptance", baseline / ACCEPTANCE_RELATIVE, acceptance_raw),
            _record_input(repo, "delivery", baseline / DELIVERY_RELATIVE, delivery_raw),
            _record_input(repo, "manifest", research / "manifest.json", manifest_raw),
            _record_input(repo, "prepared", research / "prepared.json", prepared_raw),
            _record_input(repo, "stage1_receipt", research / "stage-1.json",
                          safe_path(research / "stage-1.json").read_bytes()),
            _record_input(repo, "stage2_request", request_path, request_raw),
            _record_input(repo, "stage2_input", input_path, input_raw),
            _record_input(repo, "stage2_seal", seal_path, seal_raw),
            _record_input(repo, "stage2_report", stage_report_path, stage_report_raw),
            _record_input(repo, "charge_ledger", ledger_path, ledger_raw),
            *v3_inputs,
            *v4_stage1_inputs,
        ],
        "protected": protected,
        "initial": initial,
        "stage2_input": input_path,
        "manifest": manifest,
        "prepared_sha256": prepared_hash,
        "reservation": reservation,
        "acceptance": acceptance,
        "delivery": delivery,
    }
