"""Read-only recovery of the saved Curry V5 handoff evidence."""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, replace
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import uuid
import zipfile
from typing import Any, Callable

import jsonschema

from ygo_data.identity import canonical, stable_source
from ygo_eval.prompt_probe_prepare import safe_path, strict_json


V5_ROOT = Path("data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26")
OUTPUT_ROOT = Path(
    "data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26"
)
OUTPUT_NAME = "recovery-report.json"
V5_DELIVERY_SHA256 = "3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278"
V5_NATIVE_ARCHIVE_SHA256 = "ce194380f6d2bb6c587e96009382cac6d9ed03f24af4fe660873da4b5d3480fa"
V5_NATIVE_LIST_SHA256 = "c776edf40bcab67da85e011770d9c3ffdb27806c9aca8f72ed39ccc49df512f6"
V5_FINAL_ARCHIVE_SHA256 = "d06e55a18c53e4de004ac178e51191741c83803acb4c2ea05a2ff1a13e35fafb"
V5_FINAL_LIST_SHA256 = "8db08aa7448dd1c73366d4de4a268fe7a60b7fae7cda0121f159baeb0014b379"
OBSERVATION_RELATIVE = Path(
    "target/curry-ledger-handoff-v5-tests/real-audit-attempt-observation.json"
)
COMMAND_LOG_RELATIVE = Path("target/curry-ledger-handoff-v5-tests/audit-command.log")
OBSERVATION_SHA256 = "386aba20924ced9d7f686c6691b7d7e7219fd0922588cc511c1ebd8969e377e8"
COMMAND_LOG_SHA256 = "13d58e319136732edd70edfa44d11d3d3efb4986abe594b25d7efbf1ce977efa"
STAGE2_INPUT_SHA256 = "b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8"
PREPARED_SHA256 = "7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee"
LEDGER_SHA256 = "7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c"
RESERVATION_ID = "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63"
RESERVATION_POLICY_ID = "curry-unknown-reserve-seven-v1"
SCOPE = "curry-option-verification-v1"
LIMIT = 7
V5_SOURCE_DELTA = {
    "added": [
        "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md"
    ],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}
CHECKS = (
    "v5_delivery_and_archives",
    "historical_sources",
    "frozen_input_and_parent",
    "saved_process_evidence",
    "scope_ledger_semantics",
    "input_stability",
    "report_publication",
)
V2_CHECKS = ("previous_recovery_failed_source", *CHECKS)
V3_CHECKS = ("previous_recovery_v2_failed_source", *V2_CHECKS)
QUALIFICATIONS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
HASH = re.compile(r"^[a-f0-9]{64}$")
TOOL_FILES = (
    "python/ygo_eval/curry_ledger_handoff_recovery.py",
    "python/ygo_eval/curry_ledger_handoff_audit.py",
    "python/ygo_eval/history_audit.py",
    "python/ygo_eval/research.py",
    "schemas/curry-ledger-handoff-recovery-v1.schema.json",
    "schemas/audit-publication-diagnostic-v1.schema.json",
)
TOOL_FILES_V2 = (
    *TOOL_FILES,
    "schemas/curry-ledger-handoff-recovery-v2.schema.json",
)
TOOL_FILES_V3 = (
    *TOOL_FILES_V2,
    "schemas/curry-ledger-handoff-recovery-v3.schema.json",
)
TOOL_ARCHIVE_SCOPE = "recovery-entrypoints-and-primary-contracts-integrity-only"
VERIFY_IMPLEMENTATION = "current_workspace_code_revalidates_saved_evidence"
V2_OUTPUT_ROOT = Path(
    "data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26"
)
V3_OUTPUT_ROOT = Path(
    "data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26"
)
PREVIOUS_RECOVERY_ROOT = Path(
    "data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26"
)
PREVIOUS_RECOVERY_REPORT_SHA256 = "bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d"
PREVIOUS_RECOVERY_DELIVERY_SHA256 = "154d77cb4c8790cd971e19dbd17dcc8a4417df1e0f460747948e306706328e2e"
PREVIOUS_RECOVERY_V2_ROOT = Path(
    "data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26"
)
PREVIOUS_RECOVERY_V2_REPORT_SHA256 = "7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6"
PREVIOUS_RECOVERY_V2_DELIVERY_SHA256 = "c3bf0aa851b5cd6b39045ee5b8897d3c53f934de4ab31a5ec0cf1dc93fb7ccfe"
V2_SOURCE_DELTA = {
    "added": [
        "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md",
    ],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}


@dataclass(frozen=True)
class RecoveryProfile:
    """Immutable pins for one fixed evidence tree; never exposed as CLI input."""

    v5_root: Path
    output_root: Path
    baseline_root: Path
    reservation_root: Path
    historical_roots: tuple[Path, ...]
    delivery_sha256: str
    native_identity: str
    native_count: int
    native_archive_sha256: str
    native_list_sha256: str
    final_identity: str
    final_count: int
    final_archive_sha256: str
    final_list_sha256: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    observation_path: Path
    observation_sha256: str
    command_log_path: Path
    command_log_sha256: str
    metadata_relative: Path
    stdout_relative: Path
    stderr_relative: Path
    stage2_input_sha256: str
    prepared_sha256: str
    ledger_sha256: str
    reservation_id: str
    reservation_policy_id: str
    # Identity and count recorded in the V3 final-delivery `source_after_docs`
    # object. This differs from final_identity/final_count, which bind the V5
    # recovery tool's final source archive.
    delivery_source_after_docs_identity: str | None = None
    delivery_source_after_docs_file_count: int | None = None

    @property
    def source_delta(self) -> dict[str, list[str]]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
        }


PRODUCTION_PROFILE = RecoveryProfile(
    v5_root=V5_ROOT,
    output_root=OUTPUT_ROOT,
    baseline_root=Path("data/runtime/p1-curry-option-verification-native-2026-10-25"),
    reservation_root=Path("data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"),
    historical_roots=(
        Path("data/runtime/p1-curry-ledger-handoff-offline-2026-10-25"),
        Path("data/runtime/p1-curry-ledger-handoff-v2-offline-2026-10-25"),
        Path("data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25"),
        Path("data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26"),
    ),
    delivery_sha256=V5_DELIVERY_SHA256,
    native_identity="c37902c3e949fe6759df7ec0a6c30a54fa08dc3099cd638d5cb5833bbab5515f",
    native_count=576,
    native_archive_sha256=V5_NATIVE_ARCHIVE_SHA256,
    native_list_sha256=V5_NATIVE_LIST_SHA256,
    final_identity="d52244cbf36a7aa9a8e880a970dffb547ab5c2257c605ce1e85f8f54c428861a",
    final_count=577,
    final_archive_sha256=V5_FINAL_ARCHIVE_SHA256,
    final_list_sha256=V5_FINAL_LIST_SHA256,
    added=tuple(V5_SOURCE_DELTA["added"]),
    removed=tuple(V5_SOURCE_DELTA["removed"]),
    changed=tuple(V5_SOURCE_DELTA["changed"]),
    observation_path=OBSERVATION_RELATIVE,
    observation_sha256=OBSERVATION_SHA256,
    command_log_path=COMMAND_LOG_RELATIVE,
    command_log_sha256=COMMAND_LOG_SHA256,
    metadata_relative=Path("process-diagnostics/audit_saved_input_only-dbe7dea1aa144582894cafdbb48872d2.json"),
    stdout_relative=Path("process-diagnostics/audit_saved_input_only-dbe7dea1aa144582894cafdbb48872d2.stdout.bin"),
    stderr_relative=Path("process-diagnostics/audit_saved_input_only-dbe7dea1aa144582894cafdbb48872d2.stderr.bin"),
    stage2_input_sha256=STAGE2_INPUT_SHA256,
    prepared_sha256=PREPARED_SHA256,
    ledger_sha256=LEDGER_SHA256,
    reservation_id=RESERVATION_ID,
    reservation_policy_id=RESERVATION_POLICY_ID,
)

V2_PROFILE = replace(
    PRODUCTION_PROFILE,
    output_root=V2_OUTPUT_ROOT,
    added=tuple(V2_SOURCE_DELTA["added"]),
    removed=tuple(V2_SOURCE_DELTA["removed"]),
    changed=tuple(V2_SOURCE_DELTA["changed"]),
)
V3_PROFILE = replace(
    V2_PROFILE,
    output_root=V3_OUTPUT_ROOT,
    delivery_source_after_docs_identity=(
        "29e4c74081c42e8cedaff7bd90d174e3d8002dfec31e82855b830bb471f3c918"
    ),
    delivery_source_after_docs_file_count=589,
)


def _v3_reservation_input_roles() -> frozenset[str]:
    """Return the authenticated V3 reservation role set."""
    from ygo_eval import curry_ledger_handoff_audit as audit

    roles = {
        role for role in audit.V3_INPUT_ROLE_ALLOWLIST
        if role.startswith("v3_source_")
    }
    _require(len(roles) == 100
             and "v3_source_workspace_identity" in roles
             and "v3_source_confirmation_summary" not in roles,
             "recovery_v3_source_role_basis_invalid")
    return frozenset(roles)


def _archived_v3_source_roles(source: bytes) -> frozenset[str]:
    """Read the V2-pinned audit role allowlist as inert archived source."""
    import ast

    try:
        module = ast.parse(source.decode("utf-8", "strict"))
        matches = [
            node for node in module.body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name)
                and target.id == "V3_INPUT_ROLE_ALLOWLIST"
                for target in node.targets
            )
        ]
        if len(matches) != 1:
            raise ValueError("recovery_previous_v2_archived_role_basis_invalid")
        value = matches[0].value
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "frozenset" and len(value.args) == 1
                and not value.keywords):
            roles = ast.literal_eval(value.args[0])
            if (isinstance(roles, set) and roles
                    and all(isinstance(role, str) for role in roles)):
                source_roles = frozenset(
                    role for role in roles
                    if role.startswith("v3_source_")
                )
                if source_roles:
                    return source_roles
    except (SyntaxError, UnicodeDecodeError, ValueError, TypeError):
        pass
    raise ValueError("recovery_previous_v2_archived_role_basis_invalid")


@dataclass(frozen=True)
class RecoveryVersionSpec:
    """Fixed version wiring; production callers can choose only a version."""

    report_version: int
    report_kind: str
    schema_name: str
    checks: tuple[str, ...]
    tool_files: tuple[str, ...]
    profile: RecoveryProfile
    previous_recovery_root: Path | None = None
    previous_recovery_report_sha256: str | None = None
    previous_recovery_delivery_sha256: str | None = None
    previous_recovery_v2_root: Path | None = None
    previous_recovery_v2_report_sha256: str | None = None
    previous_recovery_v2_delivery_sha256: str | None = None
    diagnostic_root: Path = Path(
        "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    )
    allow_saved_workspace_identity_change: bool = False


V1_SPEC = RecoveryVersionSpec(
    report_version=1,
    report_kind="curry_ledger_handoff_recovery",
    schema_name="curry-ledger-handoff-recovery-v1.schema.json",
    checks=CHECKS,
    tool_files=TOOL_FILES,
    profile=PRODUCTION_PROFILE,
)
V2_SPEC = RecoveryVersionSpec(
    report_version=2,
    report_kind="curry_ledger_handoff_recovery_v2",
    schema_name="curry-ledger-handoff-recovery-v2.schema.json",
    checks=V2_CHECKS,
    tool_files=TOOL_FILES_V2,
    profile=V2_PROFILE,
    previous_recovery_root=PREVIOUS_RECOVERY_ROOT,
    previous_recovery_report_sha256=PREVIOUS_RECOVERY_REPORT_SHA256,
    previous_recovery_delivery_sha256=PREVIOUS_RECOVERY_DELIVERY_SHA256,
    diagnostic_root=Path(
        "target/curry-ledger-handoff-recovery-v2-tests/publication-diagnostics"
    ),
    allow_saved_workspace_identity_change=True,
)
V3_SPEC = RecoveryVersionSpec(
    report_version=3,
    report_kind="curry_ledger_handoff_recovery_v3",
    schema_name="curry-ledger-handoff-recovery-v3.schema.json",
    checks=V3_CHECKS,
    tool_files=TOOL_FILES_V3,
    profile=V3_PROFILE,
    previous_recovery_root=PREVIOUS_RECOVERY_ROOT,
    previous_recovery_report_sha256=PREVIOUS_RECOVERY_REPORT_SHA256,
    previous_recovery_delivery_sha256=PREVIOUS_RECOVERY_DELIVERY_SHA256,
    previous_recovery_v2_root=PREVIOUS_RECOVERY_V2_ROOT,
    previous_recovery_v2_report_sha256=PREVIOUS_RECOVERY_V2_REPORT_SHA256,
    previous_recovery_v2_delivery_sha256=PREVIOUS_RECOVERY_V2_DELIVERY_SHA256,
    diagnostic_root=Path(
        "target/curry-ledger-handoff-recovery-v3-tests/publication-diagnostics"
    ),
    allow_saved_workspace_identity_change=True,
)


def _version_spec(version: int) -> RecoveryVersionSpec:
    if version == 1:
        return V1_SPEC
    if version == 2:
        return V2_SPEC
    if version == 3:
        return V3_SPEC
    raise ValueError("recovery_report_version_unsupported")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _verify_tool_workspace_binding(report: dict[str, Any], workspace: dict[str, Any]) -> bool:
    """Bind the archived tool snapshot to the source used for evidence checks."""
    tool = report.get("tool") if isinstance(report, dict) else None
    _require(isinstance(tool, dict)
             and isinstance(workspace, dict)
             and isinstance(workspace.get("identity"), str)
             and tool.get("workspace_identity") == workspace["identity"],
             "recovery_tool_workspace_identity_mismatch")
    return True


def _stable_error_code(error: BaseException, fallback: str = "recovery_check_failed") -> str:
    value = str(error)
    return value if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", value) else fallback


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-version", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")


def _report_template(
    tool: dict[str, Any] | None = None,
    profile: RecoveryProfile = PRODUCTION_PROFILE,
    version_spec: RecoveryVersionSpec = V1_SPEC,
) -> dict[str, Any]:
    result = {
        "schema_version": version_spec.report_version,
        "kind": version_spec.report_kind,
        "status": "incomplete",
        "valid": False,
        "failure_checkpoint": None,
        "diagnostic": None,
        "native_calls": 0,
        "runner_process_calls": 0,
        "execution_ready": False,
        "qualifications": dict(QUALIFICATIONS),
        "tool": tool,
        "v5_source": {
            "delivery_sha256": profile.delivery_sha256,
            "native_source_identity": None,
            "native_file_count": None,
            "final_source_identity": None,
            "final_file_count": None,
            "source_delta": None,
            "formal_report_absent": None,
            "outer_cli_exit_code_claimed": None,
            "outer_cli_exit_code_authenticated": False,
            "outer_failure_reason_authenticated": False,
        },
        "checks": {name: "not_run" for name in version_spec.checks},
        "source_groups": {
            "v5_original_audit_roles": 0,
            "v5_recovery_anchors": 0,
            "curry_scope_blob_roles": 0,
            "v3_reservation_roles": 0,
        },
        "baseline": {
            "scope": SCOPE,
            "context": None,
            "manifest_sha256": None,
            "prepared_sha256": None,
            "stage1_receipt_sha256": None,
            "stage2_input_sha256": None,
            "stage2_receipt_absent": None,
        },
        "saved_process_evidence": {
            "role": "curry_ledger_handoff_audit_runner",
            "mode": "audit_saved_input_only",
            "status": None,
            "return_code": None,
            "metadata_sha256": None,
            "stdout_sha256": None,
            "stdout_bytes": None,
            "stderr_sha256": None,
            "stderr_bytes": None,
            "trace_event_count": None,
            "asset_scan_elapsed_ns": None,
            "historical_scan_time_certified": False,
        },
        "accounting": {
            "scope": SCOPE,
            "original_scope_consumed": None,
            "original_scope_completed": None,
            "original_scope_unknown": None,
            "original_scope_limit": LIMIT,
            "certified_historical_consumed_before_scope": None,
            "certified_historical_consumed_including_scope": None,
            "policy_reserved": 7,
            "planning_total": None,
            "reservation_id": None,
            "reservation_policy_id": profile.reservation_policy_id,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        },
        "inputs": [],
        "stability": {
            "first_check": "not_run",
            "recheck": "not_run",
            "input_rows_revalidation": "not_run",
            "workspace": "not_collected",
            "v5_tree": "not_collected",
            "baseline_tree": "not_collected",
            "reservation_tree": "not_collected",
            "historical_trees": "not_collected",
            "ledger_and_blobs": "not_collected",
            "stage2_receipt_absent_before": None,
            "stage2_receipt_absent_after": None,
        },
        "publication": {
            "state": "not_run",
            "failure_phase": None,
            "diagnostic_id": None,
        },
        "elapsed_seconds": 0.0,
    }
    if version_spec.report_version == 2:
        result["previous_recovery_source"] = {
            "report_sha256": version_spec.previous_recovery_report_sha256,
            "delivery_sha256": version_spec.previous_recovery_delivery_sha256,
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "source_delta": None,
            "final_source_identity": None,
            "final_file_count": None,
        }
        result["source_groups"]["previous_recovery_roles"] = 0
        result["stability"]["previous_recovery_tree"] = "not_collected"
    elif version_spec.report_version == 3:
        result["previous_recovery_source"] = {
            "report_sha256": version_spec.previous_recovery_report_sha256,
            "delivery_sha256": version_spec.previous_recovery_delivery_sha256,
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "source_delta": None,
            "final_source_identity": None,
            "final_file_count": None,
        }
        result["previous_recovery_v2_source"] = {
            "report_sha256": version_spec.previous_recovery_v2_report_sha256,
            "delivery_sha256": version_spec.previous_recovery_v2_delivery_sha256,
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "final_source_identity": None,
            "final_file_count": None,
            "v3_role_count": None,
            "workspace_identity_present": None,
            "confirmation_summary_present": None,
            "v3_role_difference": None,
        }
        result["source_groups"]["previous_recovery_v1_roles"] = 0
        result["source_groups"]["previous_recovery_v2_roles"] = 0
        result["stability"]["previous_recovery_tree"] = "not_collected"
        result["stability"]["previous_recovery_v2_tree"] = "not_collected"
    return result


def _tool_bundle(
    repo: Path, workspace_identity: str,
    tool_files: tuple[str, ...] = TOOL_FILES,
) -> tuple[bytes, bytes, dict[str, Any]]:
    files: dict[str, bytes] = {}
    for name in tool_files:
        path = safe_path(repo / name)
        files[name] = path.read_bytes()
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    identity = _sha(canonical({"files": hashes, "workspace_identity": workspace_identity}))
    listing = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_recovery_tool_file_list",
        "tool_identity": identity,
        "workspace_identity": workspace_identity,
        "files": [{"path": name, "sha256": hashes[name]} for name in sorted(hashes)],
    }
    list_raw = json.dumps(
        listing, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    archive_raw = output.getvalue()
    metadata = {
        "identity": identity,
        "workspace_identity": workspace_identity,
        "archive_scope": TOOL_ARCHIVE_SCOPE,
        "verification_implementation": VERIFY_IMPLEMENTATION,
        "archive_path": "tool-source.zip",
        "archive_sha256": _sha(archive_raw),
        "file_list_path": "tool-source-file-list.json",
        "file_list_sha256": _sha(list_raw),
        "file_count": len(files),
        "member_sha256": hashes,
    }
    return archive_raw, list_raw, metadata


def _verify_tool_bundle(
    root: Path, tool: dict[str, Any],
    tool_files: tuple[str, ...] = TOOL_FILES,
) -> dict[str, bytes]:
    _require(isinstance(tool, dict) and set(tool) == {
        "identity", "workspace_identity", "archive_scope",
        "verification_implementation", "archive_path", "archive_sha256",
        "file_list_path", "file_list_sha256", "file_count", "member_sha256",
    }, "recovery_tool_metadata_invalid")
    _require(tool.get("archive_scope") == TOOL_ARCHIVE_SCOPE
             and tool.get("verification_implementation") == VERIFY_IMPLEMENTATION
             and tool.get("archive_path") == "tool-source.zip"
             and tool.get("file_list_path") == "tool-source-file-list.json"
             and tool.get("file_count") == len(tool_files),
             "recovery_tool_metadata_invalid")
    archive_raw = safe_path(root / tool["archive_path"]).read_bytes()
    list_raw = safe_path(root / tool["file_list_path"]).read_bytes()
    _require(_sha(archive_raw) == tool["archive_sha256"]
             and _sha(list_raw) == tool["file_list_sha256"],
             "recovery_tool_bundle_hash_mismatch")
    listing = strict_json(list_raw)
    _require(isinstance(listing, dict) and set(listing) == {
        "schema_version", "kind", "tool_identity", "workspace_identity", "files",
    } and listing.get("schema_version") == 1
             and listing.get("kind") == "curry_ledger_handoff_recovery_tool_file_list"
             and listing.get("tool_identity") == tool["identity"]
             and listing.get("workspace_identity") == tool["workspace_identity"],
             "recovery_tool_file_list_invalid")
    rows = listing.get("files")
    _require(isinstance(rows, list) and len(rows) == len(tool_files),
             "recovery_tool_file_list_invalid")
    hashes: dict[str, str] = {}
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {"path", "sha256"}
                 and isinstance(row.get("path"), str) and row["path"] not in hashes
                 and HASH.fullmatch(str(row.get("sha256", ""))) is not None,
                 "recovery_tool_file_list_invalid")
        hashes[row["path"]] = row["sha256"]
    _require(tuple(sorted(hashes)) == tuple(sorted(tool_files))
             and hashes == tool["member_sha256"]
             and _sha(canonical({"files": hashes,
                                 "workspace_identity": tool["workspace_identity"]}))
             == tool["identity"], "recovery_tool_identity_invalid")
    verified: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw), "r") as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names))
                     and tuple(sorted(names)) == tuple(sorted(tool_files)),
                     "recovery_tool_archive_members_invalid")
            for name in names:
                info = archive.getinfo(name)
                file_type = (info.external_attr >> 16) & 0o170000
                _require(file_type != 0o120000, "recovery_tool_archive_link_rejected")
                payload = archive.read(name)
                _require(_sha(payload) == hashes[name],
                         "recovery_tool_member_hash_mismatch")
                verified[name] = payload
    except (zipfile.BadZipFile, KeyError, OSError):
        raise ValueError("recovery_tool_archive_invalid") from None
    return verified


def _ordered(value: Any, keys: tuple[str, ...], code: str) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == set(keys), code)
    return {key: value[key] for key in keys}


def _parse_scope_ledger(
    raw: bytes,
    *,
    blob_reader: Callable[[str, str], bytes],
    manifest: dict[str, Any],
    stage1_receipt: dict[str, Any],
    stage1_stdout: bytes,
    option_spec: Any | None = None,
) -> dict[str, Any]:
    """Authenticate the fixed seven-row Curry journal without opening it writable."""
    from ygo_eval import history_audit as history
    from ygo_eval.curry_ledger_handoff_audit import (
        _expected_curry_stage_process_output,
    )

    _require(raw and raw.endswith(b"\n"), "curry_scope_ledger_truncated")
    lines = raw.splitlines()
    _require(len(lines) == 7 and all(lines), "curry_scope_ledger_record_count_invalid")
    context = manifest.get("context")
    started_at = manifest.get("started_at")
    _require(manifest.get("scope") == SCOPE
             and manifest.get("batch_kind") == "curry-option-verification-v1"
             and type(manifest.get("limit")) is int and manifest["limit"] == LIMIT
             and type(started_at) is int and started_at >= 0
             and isinstance(context, str) and HASH.fullmatch(context),
             "curry_scope_manifest_binding_invalid")

    rows: list[dict[str, Any]] = []
    previous = ""
    expected_fields = {
        "header": ("kind", "version", "scope", "context", "limit"),
        "checkpoint": ("kind", "name", "blob", "consumed", "charged_sequence"),
        "begin": ("kind", "call_id", "request", "purpose", "reservation"),
        "complete": ("kind", "call_id", "result", "raw_hash", "normalized_hash"),
    }
    for index, line in enumerate(lines):
        row = history.strict_json(line)
        row = _ordered(row, ("sequence", "previous", "entry", "hash"),
                       "curry_scope_ledger_row_invalid")
        _require(type(row["sequence"]) is int and row["sequence"] == index
                 and row["previous"] == previous
                 and HASH.fullmatch(str(row["hash"])) is not None,
                 "curry_scope_ledger_chain_invalid")
        entry = row["entry"]
        kind = entry.get("kind") if isinstance(entry, dict) else None
        _require(kind in expected_fields, "unsupported_curry_scope_ledger_record")
        entry = _ordered(entry, expected_fields[kind],
                         "curry_scope_ledger_entry_invalid")
        expected_hash = history.digest(history.encode([index, previous, entry]))
        _require(row["hash"] == expected_hash, "curry_scope_ledger_chain_invalid")
        previous = row["hash"]
        row["entry"] = entry
        rows.append(row)

    expected_names = (
        "immutable/curry-option-verification/start",
        "immutable/curry-option-verification/assets/1",
        "immutable/curry-option-verification/intent/1",
        "immutable/curry-option-verification/evidence/1",
    )
    calls: dict[int, dict[str, Any]] = {}
    referenced: dict[str, set[str]] = {"checkpoints": set(), "results": set(), "events": set()}
    header = rows[0]["entry"]
    _require(type(header.get("version")) is int
             and type(header.get("limit")) is int and header == {
        "kind": "header", "version": 1, "scope": SCOPE,
        "context": context, "limit": LIMIT,
    }, "curry_scope_ledger_header_invalid")
    empty_prefix = history.digest(history.encode([]))
    checkpoint_specs = (
        (1, expected_names[0], 0, started_at),
        (2, expected_names[1], 0, stage1_receipt.get("assets_before")),
        (3, expected_names[2], 0, {"request": stage1_receipt.get("request"), "stage": 1}),
    )
    checkpoint_payloads: list[dict[str, Any]] = []

    def verify_checkpoint(row_index: int, name: str, consumed: int, search: Any) -> None:
        entry = rows[row_index]["entry"]
        _require(entry.get("kind") == "checkpoint"
                 and entry.get("name") == name
                 and type(entry.get("consumed")) is int
                 and entry["consumed"] == consumed,
                 "curry_scope_checkpoint_sequence_invalid")
        charged = history.sequence_id(calls)
        _require(entry.get("charged_sequence") == charged,
                 "curry_scope_checkpoint_prefix_invalid")
        blob_hash = entry.get("blob")
        _require(isinstance(blob_hash, str) and HASH.fullmatch(blob_hash),
                 "curry_scope_checkpoint_blob_invalid")
        blob_raw = blob_reader("checkpoints", blob_hash)
        _require(history.digest(blob_raw) == blob_hash,
                 "curry_scope_checkpoint_blob_hash_invalid")
        payload = history.strict_json(blob_raw)
        payload = _ordered(payload, ("search", "budget", "reservations", "charged_sequence"),
                           "curry_scope_checkpoint_payload_invalid")
        budget = payload["budget"]
        expected_budget = {
            "consumed": consumed,
            "reserved": 0,
            "completed": consumed,
            "unknown": 0,
            "abandoned": 0,
            "limit": LIMIT,
        }
        _require(isinstance(budget, dict) and set(budget) == set(expected_budget)
                 and all(type(value) is int for value in budget.values())
                 and budget == expected_budget
                 and payload["reservations"] == {}
                 and payload["charged_sequence"] == charged
                 and payload["search"] == search,
                 "curry_scope_checkpoint_payload_binding_invalid")
        referenced["checkpoints"].add(blob_hash)
        checkpoint_payloads.append(payload)

    for checkpoint_spec in checkpoint_specs:
        verify_checkpoint(*checkpoint_spec)

    request = stage1_receipt.get("request")
    receipt_result = stage1_receipt.get("result")
    _require(isinstance(request, dict) and isinstance(receipt_result, dict)
             and set(receipt_result) == {"Ok"}
             and isinstance(receipt_result.get("Ok"), dict),
             "curry_scope_parent_receipt_invalid")
    begin = rows[4]["entry"]
    request_hash = history.request_digest(request)
    _require(type(begin.get("call_id")) is int and begin == {
        "kind": "begin", "call_id": 1, "request": request_hash,
        "purpose": "probe", "reservation": None,
    }, "curry_scope_begin_binding_invalid")
    calls[1] = {
        "request": request_hash, "purpose": "probe", "normalized_hash": None,
    }
    complete = rows[5]["entry"]
    _require(complete.get("kind") == "complete"
             and type(complete.get("call_id")) is int and complete.get("call_id") == 1
             and HASH.fullmatch(str(complete.get("raw_hash", "")))
             and HASH.fullmatch(str(complete.get("normalized_hash", ""))),
             "curry_scope_complete_binding_invalid")
    result_hash = complete.get("result")
    _require(isinstance(result_hash, str) and HASH.fullmatch(result_hash),
             "curry_scope_result_blob_invalid")
    result_raw = blob_reader("results", result_hash)
    _require(history.digest(result_raw) == result_hash,
             "curry_scope_result_blob_hash_invalid")
    stored = history.strict_json(result_raw)
    stored = _ordered(stored, ("kind", "result", "event_chunks"),
                      "curry_scope_result_blob_invalid")
    _require(stored["kind"] == "duel" and isinstance(stored["result"], dict)
             and stored["result"].get("events") == []
             and isinstance(stored["event_chunks"], list)
             and len(stored["event_chunks"]) == 1,
             "curry_scope_result_blob_invalid")
    events: list[dict[str, Any]] = []
    event_hash = stored["event_chunks"][0]
    _require(isinstance(event_hash, str) and HASH.fullmatch(event_hash),
             "curry_scope_event_blob_invalid")
    event_raw = blob_reader("events", event_hash)
    _require(history.digest(event_raw) == event_hash,
             "curry_scope_event_blob_hash_invalid")
    event_chunk = history.strict_json(event_raw)
    _require(isinstance(event_chunk, list) and 0 < len(event_chunk) <= 64,
             "curry_scope_event_chunk_invalid")
    for frame in event_chunk:
        frame = _ordered(frame, ("sequence", "opcode", "raw", "supported", "fields"),
                         "curry_scope_event_frame_invalid")
        _require(type(frame["sequence"]) is int and frame["sequence"] == len(events) + 1,
                 "curry_scope_event_sequence_invalid")
        events.append(frame)
    result_value = copy.deepcopy(stored["result"])
    result_value["events"] = events
    restored = history.frozen_result(result_value)
    raw_hash = history.digest(history.encode(restored))
    normalized = copy.deepcopy(restored)
    normalized["peak_working_set_bytes"] = None
    normalized_hash = history.digest(history.encode(normalized))
    _require(raw_hash == complete["raw_hash"]
             and normalized_hash == complete["normalized_hash"]
             and restored == receipt_result["Ok"],
             "curry_scope_result_binding_invalid")
    calls[1]["normalized_hash"] = normalized_hash
    final_sequence = history.sequence_id(calls)
    final_checkpoint = rows[6]["entry"]
    verify_checkpoint(6, expected_names[3], 1, {"receipt": stage1_receipt})
    _require(final_checkpoint.get("charged_sequence") == final_sequence,
             "curry_scope_final_checkpoint_prefix_invalid")
    referenced["results"].add(result_hash)
    referenced["events"].add(event_hash)

    expected_stdout = _expected_stage1_stdout(manifest, stage1_receipt, option_spec)
    try:
        stdout_value = history.strict_json(stage1_stdout)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("curry_scope_stage1_stdout_invalid") from None
    _require(history.encode(stdout_value, sorted_keys=True)
             == history.encode(expected_stdout, sorted_keys=True),
             "curry_scope_stage1_stdout_binding_invalid")
    receipt_ledger = stage1_receipt.get("ledger")
    _require(isinstance(receipt_ledger, dict)
             and set(receipt_ledger) == {
                 "abandoned", "completed", "consumed", "limit", "reserved", "unknown",
             }
             and all(type(value) is int for value in receipt_ledger.values())
             and receipt_ledger == {
        "abandoned": 0, "completed": 1, "consumed": 1,
        "limit": LIMIT, "reserved": 0, "unknown": 0,
    } and stage1_receipt.get("charged_sequence_id") == final_sequence,
             "curry_scope_stage1_receipt_ledger_mismatch")

    return {
        "stats": {
            "consumed": 1, "completed": 1, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": LIMIT,
        },
        "ledger_records": len(rows),
        "ledger_sha256": _sha(raw),
        "charged_sequence": final_sequence,
        "request_sha256": request_hash,
        "raw_result_sha256": raw_hash,
        "normalized_result_sha256": normalized_hash,
        "event_count": len(events),
        "blob_hashes": {
            kind: sorted(values) for kind, values in referenced.items()
        },
    }


def _expected_stage1_stdout(
    manifest: dict[str, Any], receipt: dict[str, Any], option_spec: Any | None = None,
) -> dict[str, Any]:
    from ygo_eval.curry_ledger_handoff_audit import _expected_curry_stage_process_output
    if option_spec is None:
        from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE
        option_spec = OPTION_VERIFICATION_SCOPE

    return _expected_curry_stage_process_output(
        manifest, receipt, stdout_contract="verification-accounting-v1",
        option_spec=option_spec,
    )


def _read_blob(root: Path, kind: str, address: str) -> bytes:
    _require(kind in {"checkpoints", "results", "events"}
             and HASH.fullmatch(address) is not None,
             "curry_scope_blob_address_invalid")
    path = safe_path(root / "research" / "calls.jsonl.blobs" / kind / f"{address}.json")
    raw = path.read_bytes()
    _require(_sha(raw) == address, "curry_scope_blob_address_mismatch")
    return raw


def _parse_scope_ledger_from_repo(
    repo: Path, manifest: dict[str, Any], stage1_receipt: dict[str, Any],
    stage1_stdout: bytes, *, option_spec: Any | None = None,
) -> dict[str, Any]:
    from ygo_eval.curry_ledger_handoff_audit import _fixed_option_paths

    if option_spec is None:
        _root, paths = _fixed_option_paths(repo)
        research = paths["research"]
    else:
        scope_root = safe_path(repo / option_spec.output_root, file=False)
        research = scope_root / "research"
    ledger_path = safe_path(research / "calls.jsonl")
    raw = ledger_path.read_bytes()
    result = _parse_scope_ledger(
        raw,
        blob_reader=lambda kind, address: _read_blob(research.parent, kind, address),
        manifest=manifest, stage1_receipt=stage1_receipt, stage1_stdout=stage1_stdout,
        option_spec=option_spec,
    )
    blob_root = research / "calls.jsonl.blobs"
    expected = result["blob_hashes"]
    for kind in ("checkpoints", "results", "events"):
        directory = safe_path(blob_root / kind, file=False)
        members = list(directory.iterdir())
        actual = {path.name for path in members if path.is_file()}
        expected_files = {f"{address}.json" for address in expected[kind]}
        _require(actual == expected_files and len(members) == len(expected_files),
                 "curry_scope_blob_directory_contents_invalid")
        _require(all(path.is_file() and not path.is_symlink()
                     for path in members),
                 "curry_scope_blob_directory_contents_invalid")
    recovery_dir = blob_root / "recoveries"
    _require(recovery_dir.is_dir() and not any(recovery_dir.iterdir()),
             "curry_scope_recovery_blobs_unexpected")
    result["blob_directory_sha256"] = _sha(canonical(_snapshot_blob_tree(blob_root)))
    return result


def _snapshot_blob_tree(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        _require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                 "curry_scope_blob_link_rejected")
        if path.is_file():
            values[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
        elif not path.is_dir():
            raise ValueError("curry_scope_blob_entry_invalid")
    return values


def _record_file(repo: Path, role: str, path: Path, expected_sha256: str | None = None) -> dict:
    from ygo_eval.curry_ledger_handoff_audit import _record_input

    raw = safe_path(path).read_bytes()
    _require(expected_sha256 is None or _sha(raw) == expected_sha256,
             "recovery_pinned_input_hash_mismatch")
    return _record_input(repo, role, path, raw)


def _verify_v5_delivery(
    repo: Path, profile: RecoveryProfile = PRODUCTION_PROFILE,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    from ygo_eval import curry_ledger_handoff_audit as audit

    root = repo / profile.v5_root
    delivery_path = safe_path(root / "final-build/delivery.json")
    delivery_raw = delivery_path.read_bytes()
    _require(_sha(delivery_raw) == profile.delivery_sha256,
             "recovery_v5_delivery_anchor_mismatch")
    delivery = strict_json(delivery_raw)
    _require(isinstance(delivery, dict) and delivery.get("schema_version") == 1
             and delivery.get("kind") == "curry_ledger_handoff_v5_final_delivery"
             and delivery.get("status") == "incomplete_outer_audit_cli_failed"
             and type(delivery.get("native_calls")) is int
             and delivery["native_calls"] == 0,
             "recovery_v5_delivery_invalid")
    report_path = root / audit.REPORT_RELATIVE
    _require(not report_path.exists() and not report_path.is_symlink(),
             "recovery_v5_formal_report_unexpected")

    native = delivery.get("native_bundle")
    final = delivery.get("source_after_docs")
    attempt = delivery.get("audit_attempt")
    diag = delivery.get("process_diagnostics")
    _require(isinstance(native, dict) and isinstance(final, dict)
             and isinstance(attempt, dict) and isinstance(diag, dict),
             "recovery_v5_delivery_sections_invalid")
    _require(native.get("source_identity") == profile.native_identity
             and type(native.get("source_file_count")) is int
             and native["source_file_count"] == profile.native_count
             and native.get("source_archive_path") == (profile.v5_root / "source-native.zip").as_posix()
             and native.get("source_archive_sha256") == profile.native_archive_sha256
             and native.get("source_file_list_path") == (profile.v5_root / "source-native-file-list.json").as_posix()
             and native.get("source_file_list_sha256") == profile.native_list_sha256,
             "recovery_v5_native_bundle_invalid")
    _require(final.get("identity") == profile.final_identity
             and type(final.get("file_count")) is int and final["file_count"] == profile.final_count
             and final.get("archive_path") == "source-final.zip"
             and final.get("archive_sha256") == profile.final_archive_sha256
             and final.get("file_list_path") == "source-final-file-list.json"
             and final.get("file_list_sha256") == profile.final_list_sha256,
             "recovery_v5_final_source_invalid")
    _require(attempt.get("cli_exit_code") == 2
             and attempt.get("cli_diagnostic")
             == "audit-curry-ledger-handoff refused: fixed source, runner, or output check failed"
             and attempt.get("failure_checkpoint") is None
             and attempt.get("failure_checkpoint_certified") is False
             and type(attempt.get("runner_process_calls")) is int
             and attempt.get("runner_process_calls") == 1
             and attempt.get("runner_mode") == "audit_saved_input_only"
             and attempt.get("runner_exit_code") == 0
             and attempt.get("runner_read_only_audit_passed") is True
             and attempt.get("official_report_path") == (profile.v5_root / "audit-report.json").as_posix()
             and attempt.get("official_report_exists") is False
             and attempt.get("rerun_performed") is False,
             "recovery_v5_attempt_record_invalid")
    _require(diag.get("role") == "curry_ledger_handoff_audit_runner"
             and diag.get("mode") == "audit_saved_input_only"
             and type(diag.get("trace_event_count")) is int
             and diag.get("trace_event_count") == 8
             and diag.get("raw_output_preserved_before_interpretation") is True,
             "recovery_v5_process_summary_invalid")

    build_path = safe_path(root / "build-record.json")
    build_raw = build_path.read_bytes()
    _require(_sha(build_raw) == native.get("build_record_sha256"),
             "recovery_v5_build_record_hash_mismatch")
    build = strict_json(build_raw)
    source = build.get("source_before") if isinstance(build, dict) else None
    _require(isinstance(source, dict) and source == build.get("source_after")
             and source.get("identity") == native.get("source_identity")
             and len(source.get("files", {})) == profile.native_count,
             "recovery_v5_build_source_invalid")
    runner_path = safe_path(root / "native-artifacts/curry-option-validation.exe")
    runner_build = audit._verify_runner_build(
        runner_path, build_path, repo, source,
    )
    _require(runner_build.get("runner_sha256") == native.get("runner_sha256")
             and runner_build.get("build_record_identity") == native.get("build_record_identity"),
             "recovery_v5_runner_binding_invalid")
    native_listing, native_archive_raw, native_list_raw = audit._verify_source_bundle(
        root / "source-native.zip", root / "source-native-file-list.json",
        expected_identity=native["source_identity"], expected_count=profile.native_count,
    )
    _require(_sha(native_archive_raw) == profile.native_archive_sha256
             and _sha(native_list_raw) == profile.native_list_sha256,
             "recovery_v5_native_archive_binding_invalid")
    final_root = root / "final-build"
    final_listing, final_archive_raw, final_list_raw = audit._verify_source_bundle(
        final_root / "source-final.zip", final_root / "source-final-file-list.json",
        expected_identity=final["identity"], expected_count=profile.final_count,
    )
    _require(_sha(final_archive_raw) == profile.final_archive_sha256
             and _sha(final_list_raw) == profile.final_list_sha256,
             "recovery_v5_final_archive_binding_invalid")
    delta = {
        "added": sorted(set(final_listing["files"]) - set(native_listing["files"])),
        "removed": sorted(set(native_listing["files"]) - set(final_listing["files"])),
        "changed": sorted(
            name for name in set(final_listing["files"]) & set(native_listing["files"])
            if final_listing["files"][name] != native_listing["files"][name]
        ),
    }
    _require(delta == profile.source_delta,
             "recovery_v5_source_delta_invalid")
    inputs = [
        _record_file(repo, "v5_delivery", delivery_path, profile.delivery_sha256),
        _record_file(repo, "v5_observation", repo / profile.observation_path, profile.observation_sha256),
        _record_file(repo, "v5_command_log", repo / profile.command_log_path, profile.command_log_sha256),
        _record_file(repo, "v5_final_source_archive", final_root / "source-final.zip", profile.final_archive_sha256),
        _record_file(repo, "v5_final_source_file_list", final_root / "source-final-file-list.json", profile.final_list_sha256),
    ]
    return delivery, inputs, {
        "native_source_identity": native["source_identity"],
        "native_file_count": profile.native_count,
        "final_source_identity": final["identity"],
        "final_file_count": profile.final_count,
        "source_delta": delta,
        "formal_report_absent": True,
        "outer_cli_exit_code_claimed": 2,
        "outer_cli_exit_code_authenticated": False,
        "outer_failure_reason_authenticated": False,
        "native_listing": native_listing,
        "final_listing": final_listing,
        "build": build,
        "runner_build": runner_build,
    }


def _static_v1_source_delta(recovery_source: bytes) -> dict[str, list[str]]:
    """Read the old pin as data; never execute archived Python code."""
    import ast

    try:
        module = ast.parse(recovery_source.decode("utf-8"))
        for node in module.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "V5_SOURCE_DELTA"
                for target in node.targets
            ):
                value = ast.literal_eval(node.value)
                if (isinstance(value, dict) and set(value) == {"added", "removed", "changed"}
                        and all(isinstance(value[key], list)
                                and all(isinstance(item, str) for item in value[key])
                                for key in value)):
                    return value
    except (SyntaxError, UnicodeDecodeError, ValueError, TypeError):
        pass
    raise ValueError("recovery_previous_source_delta_unreadable")


def _verify_previous_recovery_failed_source(
    repo: Path, version_spec: RecoveryVersionSpec,
    profile: RecoveryProfile,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Authenticate the immutable V1 failure and its final source snapshot."""
    from ygo_eval import curry_ledger_handoff_audit as audit

    root_rel = version_spec.previous_recovery_root
    _require(root_rel is not None, "recovery_previous_source_profile_invalid")
    root = repo / root_rel
    report_path = safe_path(root / OUTPUT_NAME)
    report_raw = report_path.read_bytes()
    _require(_sha(report_raw) == version_spec.previous_recovery_report_sha256,
             "recovery_previous_report_anchor_mismatch")
    previous = strict_json(report_raw)
    tool = previous.get("tool")
    _require(isinstance(tool, dict), "recovery_previous_tool_missing")
    tool_files = _verify_tool_bundle(root, tool, TOOL_FILES)
    old_schema = tool_files.get("schemas/curry-ledger-handoff-recovery-v1.schema.json")
    _require(old_schema is not None, "recovery_previous_schema_missing")
    validate_report(
        previous, schema_raw=old_schema, profile=PRODUCTION_PROFILE,
        version_spec=V1_SPEC,
    )
    _require(previous.get("status") == "failed"
             and previous.get("valid") is False
             and previous.get("failure_checkpoint") == "v5_delivery_and_archives"
             and previous.get("diagnostic") == "recovery_v5_source_delta_invalid"
             and previous.get("inputs") == []
             and all(previous.get("checks", {}).get(name) == "not_run"
                     for name in CHECKS[1:]),
             "recovery_previous_failed_report_state_invalid")

    delivery_rel = root_rel / "final-build/delivery.json"
    delivery_path = safe_path(repo / delivery_rel)
    delivery_raw = delivery_path.read_bytes()
    _require(_sha(delivery_raw) == version_spec.previous_recovery_delivery_sha256,
             "recovery_previous_delivery_anchor_mismatch")
    delivery = strict_json(delivery_raw)
    _require(delivery.get("kind") == "curry_ledger_handoff_recovery_final_delivery"
             and delivery.get("status") == "recovery_failed_at_first_source_gate"
             and delivery.get("native_calls") == 0
             and delivery.get("runner_process_calls") == 0
             and delivery.get("recovery_report") == {
                 "path": (root_rel / OUTPUT_NAME).as_posix(),
                 "sha256": version_spec.previous_recovery_report_sha256,
                 "status": "failed",
                 "failure_checkpoint": "v5_delivery_and_archives",
                 "diagnostic": "recovery_v5_source_delta_invalid",
             }, "recovery_previous_delivery_content_invalid")
    source = delivery.get("post_docs_source")
    _require(isinstance(source, dict)
             and source.get("file_count") == 583
             and isinstance(source.get("identity"), str)
             and HASH.fullmatch(source["identity"]) is not None
             and source.get("archive_path") == (
                 root_rel / "final-build/source-native.zip"
             ).as_posix()
             and source.get("file_list_path") == (
                 root_rel / "final-build/source-native-file-list.json"
             ).as_posix(), "recovery_previous_final_source_binding_invalid")
    archive_path = safe_path(repo / PurePosixPath(source["archive_path"]))
    list_path = safe_path(repo / PurePosixPath(source["file_list_path"]))
    archive_raw = archive_path.read_bytes()
    list_raw = list_path.read_bytes()
    _require(_sha(archive_raw) == source.get("archive_sha256")
             and _sha(list_raw) == source.get("file_list_sha256"),
             "recovery_previous_final_source_hash_invalid")
    listing, _, _ = audit._verify_source_bundle(
        archive_path, list_path, expected_identity=source["identity"],
        expected_count=source["file_count"],
    )
    _require(listing.get("source_identity") == source["identity"]
             and listing.get("file_count") == 583,
             "recovery_previous_final_source_invalid")
    old_delta = _static_v1_source_delta(
        tool_files["python/ygo_eval/curry_ledger_handoff_recovery.py"],
    )
    _require(old_delta == {
        "added": ["docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md"],
        "removed": [],
        "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
    }, "recovery_previous_source_delta_not_expected")

    tool_archive_path = safe_path(root / tool["archive_path"])
    tool_list_path = safe_path(root / tool["file_list_path"])
    rows = []
    for role, path, raw in (
        ("previous_recovery_failed_report", report_path, report_raw),
        ("previous_recovery_tool_archive", tool_archive_path,
         tool_archive_path.read_bytes()),
        ("previous_recovery_tool_file_list", tool_list_path,
         tool_list_path.read_bytes()),
        ("previous_recovery_final_delivery", delivery_path, delivery_raw),
        ("previous_recovery_final_source_archive", archive_path, archive_raw),
        ("previous_recovery_final_source_file_list", list_path, list_raw),
    ):
        rows.append(audit._record_input(repo, role, path, raw))
    record = {
        "report_sha256": version_spec.previous_recovery_report_sha256,
        "delivery_sha256": version_spec.previous_recovery_delivery_sha256,
        "status": previous["status"],
        "failure_checkpoint": previous["failure_checkpoint"],
        "diagnostic": previous["diagnostic"],
        "source_delta": profile.source_delta,
        "final_source_identity": source["identity"],
        "final_file_count": source["file_count"],
    }
    return record, rows


def _verify_previous_recovery_v2_failed_source(
    repo: Path, version_spec: RecoveryVersionSpec,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Authenticate the anchored V2 failure and its 586-file final source.

    V2 had a real role-set mismatch in its V3 reservation source: the saved
    report contains workspace_identity and omits confirmation_summary.  Read
    that exact difference from the anchored report; never execute its tool ZIP.
    """
    from ygo_eval import curry_ledger_handoff_audit as audit

    root_rel = version_spec.previous_recovery_v2_root
    _require(root_rel is not None
             and version_spec.previous_recovery_v2_report_sha256 is not None
             and version_spec.previous_recovery_v2_delivery_sha256 is not None,
             "recovery_previous_v2_source_profile_invalid")
    root = safe_path(repo / root_rel, file=False)
    report_path = safe_path(root / OUTPUT_NAME)
    report_raw = report_path.read_bytes()
    _require(_sha(report_raw) == version_spec.previous_recovery_v2_report_sha256,
             "recovery_previous_v2_report_anchor_mismatch")
    previous = strict_json(report_raw)
    tool = previous.get("tool")
    _require(isinstance(tool, dict), "recovery_previous_v2_tool_missing")
    tool_files = _verify_tool_bundle(root, tool, TOOL_FILES_V2)
    old_schema = tool_files.get("schemas/curry-ledger-handoff-recovery-v2.schema.json")
    _require(old_schema is not None, "recovery_previous_v2_schema_missing")
    previous_spec = replace(
        V2_SPEC,
        previous_recovery_report_sha256=version_spec.previous_recovery_report_sha256,
        previous_recovery_delivery_sha256=version_spec.previous_recovery_delivery_sha256,
    )
    validate_report(
        previous, schema_raw=old_schema, profile=V2_PROFILE,
        version_spec=previous_spec,
    )
    _require(previous.get("status") == "failed"
             and previous.get("valid") is False
             and previous.get("failure_checkpoint") == "scope_ledger_semantics"
             and previous.get("diagnostic") == "recovery_success_input_set_incomplete"
             and previous.get("checks", {}).get("previous_recovery_failed_source") == "passed"
             and all(previous.get("checks", {}).get(name) == "passed"
                     for name in V2_CHECKS[:5])
             and previous.get("checks", {}).get(V2_CHECKS[5]) == "failed"
             and all(previous.get("checks", {}).get(name) == "not_run"
                     for name in V2_CHECKS[6:]),
             "recovery_previous_v2_failed_report_state_invalid")

    v3_roles = _v3_reservation_input_roles()
    input_rows = previous.get("inputs")
    _require(isinstance(input_rows, list) and len(input_rows) == 181,
             "recovery_previous_v2_input_set_invalid")
    actual_v3_roles = {
        row.get("role") for row in input_rows
        if isinstance(row, dict) and isinstance(row.get("role"), str)
        and row["role"].startswith("v3_source_")
    }
    _require(actual_v3_roles == v3_roles
             and "v3_source_workspace_identity" in actual_v3_roles
             and "v3_source_confirmation_summary" not in actual_v3_roles,
             "recovery_previous_v2_v3_roles_invalid")
    archived_audit_source = tool_files[
        "python/ygo_eval/curry_ledger_handoff_audit.py"
    ]
    archived_expected_v3_roles = _archived_v3_source_roles(archived_audit_source)
    _require(len(archived_expected_v3_roles) == 100
             and "v3_source_confirmation_summary" in archived_expected_v3_roles
             and "v3_source_workspace_identity" not in archived_expected_v3_roles,
             "recovery_previous_v2_archived_role_basis_invalid")
    import ast
    recovery_source = tool_files[
        "python/ygo_eval/curry_ledger_handoff_recovery.py"
    ].decode("utf-8", "strict")
    syntax = ast.parse(recovery_source)
    validator = next((node for node in ast.walk(syntax)
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "_validate_input_rows"), None)
    validator_source = ast.get_source_segment(recovery_source, validator) if validator else None
    _require(isinstance(validator_source, str)
             and "V3_INPUT_ROLE_ALLOWLIST" in validator_source
             and "181" in validator_source and "175" in validator_source,
             "recovery_previous_v2_archived_role_validation_unreadable")
    migrated_v3_roles = frozenset(
        (archived_expected_v3_roles - {"v3_source_confirmation_summary"})
        | {"v3_source_workspace_identity"}
    )
    _require(migrated_v3_roles == v3_roles,
             "recovery_previous_v2_role_migration_basis_invalid")
    role_difference = {
        "missing_from_report": sorted(archived_expected_v3_roles - actual_v3_roles),
        "unexpected_in_report": sorted(actual_v3_roles - archived_expected_v3_roles),
    }
    _require(role_difference == {
        "missing_from_report": ["v3_source_confirmation_summary"],
        "unexpected_in_report": ["v3_source_workspace_identity"],
    }, "recovery_previous_v2_role_difference_invalid")

    delivery_rel = root_rel / "final-build/delivery-final.json"
    delivery_path = safe_path(repo / delivery_rel)
    delivery_raw = delivery_path.read_bytes()
    _require(_sha(delivery_raw) == version_spec.previous_recovery_v2_delivery_sha256,
             "recovery_previous_v2_delivery_anchor_mismatch")
    delivery = strict_json(delivery_raw)
    _require(delivery.get("kind") == "curry_ledger_handoff_recovery_v2_final_delivery"
             and type(delivery.get("schema_version")) is int
             and delivery["schema_version"] == 1
             and delivery.get("recovery") == {
                 "report_path": "../recovery-report.json",
                 "report_sha256": version_spec.previous_recovery_v2_report_sha256,
                 "status": "failed",
                 "failure_checkpoint": "scope_ledger_semantics",
                 "diagnostic": "recovery_success_input_set_incomplete",
                 "verify_only_run": False,
             }
             and delivery.get("calls") == {
                 "native_calls": 0, "runner_process_calls": 0,
                 "worker_calls": 0, "ffi_calls": 0,
             }, "recovery_previous_v2_delivery_content_invalid")
    source = delivery.get("source")
    archive_rel = root_rel / "final-build/source-final.zip"
    list_rel = root_rel / "final-build/source-final-file-list.json"
    _require(isinstance(source, dict)
             and source.get("file_count") == 586
             and type(source.get("file_count")) is int
             and isinstance(source.get("identity"), str)
             and HASH.fullmatch(source["identity"]) is not None
             and source.get("head") == "8a6b2f6762131aebea6d8c0f5f61363d573f1b36"
             and source.get("archive_path") == "source-final.zip"
             and source.get("file_list_path") == "source-final-file-list.json",
             "recovery_previous_v2_final_source_binding_invalid")
    archive_path = safe_path(repo / archive_rel)
    list_path = safe_path(repo / list_rel)
    archive_raw = archive_path.read_bytes()
    list_raw = list_path.read_bytes()
    _require(_sha(archive_raw) == source.get("archive_sha256")
             and _sha(list_raw) == source.get("file_list_sha256"),
             "recovery_previous_v2_final_source_hash_invalid")
    listing, _, _ = audit._verify_source_bundle(
        archive_path, list_path, expected_identity=source["identity"],
        expected_count=586,
    )
    _require(listing.get("source_identity") == source["identity"]
             and listing.get("file_count") == 586
             and listing.get("head") == source["head"],
             "recovery_previous_v2_final_source_invalid")

    rows = []
    tool_archive_path = safe_path(root / tool["archive_path"])
    tool_list_path = safe_path(root / tool["file_list_path"])
    for role, path, raw in (
        ("previous_recovery_v2_failed_report", report_path, report_raw),
        ("previous_recovery_v2_tool_archive", tool_archive_path,
         tool_archive_path.read_bytes()),
        ("previous_recovery_v2_tool_file_list", tool_list_path,
         tool_list_path.read_bytes()),
        ("previous_recovery_v2_final_delivery", delivery_path, delivery_raw),
        ("previous_recovery_v2_final_source_archive", archive_path, archive_raw),
        ("previous_recovery_v2_final_source_file_list", list_path, list_raw),
    ):
        rows.append(audit._record_input(repo, role, path, raw))
    record = {
        "report_sha256": version_spec.previous_recovery_v2_report_sha256,
        "delivery_sha256": version_spec.previous_recovery_v2_delivery_sha256,
        "status": previous["status"],
        "failure_checkpoint": previous["failure_checkpoint"],
        "diagnostic": previous["diagnostic"],
        "final_source_identity": source["identity"],
        "final_file_count": source["file_count"],
        "v3_role_count": len(actual_v3_roles),
        "workspace_identity_present": True,
        "confirmation_summary_present": False,
        "v3_role_difference": role_difference,
    }
    return record, rows


def _saved_process(
    repo: Path, delivery: dict, manifest: dict,
    profile: RecoveryProfile = PRODUCTION_PROFILE,
) -> tuple[dict, list[dict[str, Any]]]:
    from ygo_eval import curry_ledger_handoff_audit as audit

    root = repo / profile.v5_root
    diag = delivery["process_diagnostics"]
    expected_paths = {
        "metadata_path": (profile.v5_root / profile.metadata_relative).as_posix(),
        "stdout_path": (profile.v5_root / profile.stdout_relative).as_posix(),
        "stderr_path": (profile.v5_root / profile.stderr_relative).as_posix(),
    }
    _require(diag.get("metadata_path") == expected_paths["metadata_path"]
             and diag.get("stdout_path") == expected_paths["stdout_path"]
             and diag.get("stderr_path") == expected_paths["stderr_path"],
             "recovery_v5_process_paths_invalid")
    metadata_path = safe_path(root / profile.metadata_relative)
    record_raw = metadata_path.read_bytes()
    record = strict_json(record_raw)
    _require(_sha(record_raw) == diag.get("metadata_sha256")
             and record.get("metadata_path") == profile.metadata_relative.as_posix()
             and record.get("mode") == "audit_saved_input_only"
             and record.get("runner_role") == "curry_ledger_handoff_audit_runner"
             and record.get("status") == "completed"
             and type(record.get("return_code")) is int and record["return_code"] == 0
             and record.get("error_code") is None,
             "recovery_v5_process_metadata_invalid")
    stdout_path = safe_path(root / record["stdout"]["path"])
    stderr_path = safe_path(root / record["stderr"]["path"])
    stdout = stdout_path.read_bytes()
    stderr = stderr_path.read_bytes()
    _require(_sha(stdout) == diag.get("stdout_sha256")
             and len(stdout) == diag.get("stdout_bytes")
             and _sha(stderr) == diag.get("stderr_sha256")
             and len(stderr) == diag.get("stderr_bytes"),
             "recovery_v5_process_output_hash_invalid")
    output = strict_json(stdout)
    trace = audit._trace_summary(stderr)
    _require(len(trace) == 8
             and sum(1 for row in trace if row["phase"] == "saved_input_asset_scan"
                     and row["event"] == "end") == 1,
             "recovery_v5_process_trace_invalid")
    trace_elapsed = next(
        row["elapsed_ns"] for row in trace
        if row["phase"] == "saved_input_asset_scan" and row["event"] == "end"
    )
    _require(trace_elapsed == diag.get("asset_scan_elapsed_ns"),
             "recovery_v5_process_scan_elapsed_mismatch")
    normalized_output = audit._validate_saved_input_output(
        output, context=manifest["context"],
        identity_sha256=manifest["assets"]["ordinary"]["identity"],
    )
    pseudo = {
        "baseline": {"context": manifest["context"]},
        "runner": {
            "process_capture": {
                "metadata_path": record["metadata_path"],
                "metadata_sha256": _sha(record_raw),
                "stdout_path": record["stdout"]["path"],
                "stderr_path": record["stderr"]["path"],
            },
            "return_code": record["return_code"],
            "process_status": record["status"],
            "diagnostic_sha256": _sha(canonical(record)),
            "stdout_sha256": record["stdout"]["sha256"],
            "stdout_bytes": record["stdout"]["bytes"],
            "stderr_sha256": record["stderr"]["sha256"],
            "stderr_bytes": record["stderr"]["bytes"],
            "saved_input_result": normalized_output,
            "trace": trace,
        },
    }
    rows = audit._verify_process_capture(
        pseudo, repo, require_success=True, output_root=root,
    )
    _require(type(output.get("stage")) is int and output.get("stage") == 2
             and output.get("context") == manifest["context"]
             and output.get("identity_sha256") == manifest["assets"]["ordinary"]["identity"]
             and output.get("saved_input_audit_passed") is True
             and type(output.get("native_calls")) is int
             and output.get("native_calls") == 0
             and output.get("execution_ready") is False
             and output.get("parent_receipt_valid") is True
             and output.get("request_derivation_valid") is True
             and output.get("stage_receipt_absent") is True
             and isinstance(output.get("ledger"), dict)
             and set(output["ledger"]) == {
                 "consumed", "completed", "unknown", "reserved", "abandoned", "limit",
             }
             and all(type(value) is int for value in output["ledger"].values()),
             "recovery_saved_input_output_invalid")
    return {
        "status": record["status"],
        "return_code": record["return_code"],
        "metadata_sha256": _sha(record_raw),
        "stdout_sha256": _sha(stdout),
        "stdout_bytes": len(stdout),
        "stderr_sha256": _sha(stderr),
        "stderr_bytes": len(stderr),
        "trace_event_count": len(trace),
        "asset_scan_elapsed_ns": trace_elapsed,
        "historical_scan_time_certified": False,
        "result": output,
        "trace": trace,
    }, rows


def _collect_evidence(
    repo: Path,
    *,
    source_collector: Callable[[Path], dict],
    clock: Callable[[], float],
    _sources: Any | None = None,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    profile: RecoveryProfile = PRODUCTION_PROFILE,
    version_spec: RecoveryVersionSpec = V1_SPEC,
    allow_saved_workspace_identity_change: bool = False,
    report_target: dict[str, Any] | None = None,
    on_checkpoint: Callable[[str, str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from ygo_eval import curry_ledger_handoff_audit as audit
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree
    from ygo_eval.native_curry_option_validation import (
        OPTION_VERIFICATION_SCOPE, _snapshot_curry_evidence,
    )

    baseline = repo / profile.baseline_root
    v5_root = repo / profile.v5_root
    report = report_target if report_target is not None else _report_template(
        profile=profile, version_spec=version_spec,
    )
    def mark(name: str, state: str) -> None:
        if on_checkpoint is not None:
            on_checkpoint(name, state)

    if version_spec.report_version == 3:
        mark("previous_recovery_v2_failed_source", "running")
        previous_v2_record, previous_v2_rows = _verify_previous_recovery_v2_failed_source(
            repo, version_spec,
        )
        report["previous_recovery_v2_source"] = previous_v2_record
        report["source_groups"]["previous_recovery_v2_roles"] = len(previous_v2_rows)
        report["inputs"].extend(previous_v2_rows)
        report["checks"]["previous_recovery_v2_failed_source"] = "passed"
        mark("previous_recovery_v2_failed_source", "passed")
    if version_spec.report_version in (2, 3):
        mark("previous_recovery_failed_source", "running")
        previous_record, previous_rows = _verify_previous_recovery_failed_source(
            repo, version_spec, profile,
        )
        report["previous_recovery_source"] = previous_record
        if version_spec.report_version == 2:
            report["source_groups"]["previous_recovery_roles"] = len(previous_rows)
        else:
            report["source_groups"]["previous_recovery_v1_roles"] = len(previous_rows)
        report["inputs"].extend(previous_rows)
        report["checks"]["previous_recovery_failed_source"] = "passed"
        mark("previous_recovery_failed_source", "passed")
    report["checks"]["v5_delivery_and_archives"] = "not_run"
    mark("v5_delivery_and_archives", "running")
    delivery, anchor_rows, v5_sources = _verify_v5_delivery(repo, profile)
    report["v5_source"].update({key: v5_sources[key] for key in (
        "native_source_identity", "native_file_count", "final_source_identity",
        "final_file_count", "source_delta", "formal_report_absent",
        "outer_cli_exit_code_claimed", "outer_cli_exit_code_authenticated",
        "outer_failure_reason_authenticated",
    )})
    report["inputs"].extend(anchor_rows)
    report["checks"]["v5_delivery_and_archives"] = "passed"
    mark("v5_delivery_and_archives", "passed")

    mark("historical_sources", "running")
    workspace_before = source_collector(repo)
    if not allow_saved_workspace_identity_change:
        _verify_tool_workspace_binding(report, workspace_before)
    v1 = audit._verify_v1_audit_source_v3(repo, _sources=_sources)
    v2 = audit._verify_v2_audit_source_v3(repo, _sources=_sources)
    v2_final = audit._verify_v2_final_source_v3(repo, _sources=_sources)
    v3 = audit._verify_previous_v3_failed_source(repo, _sources=_sources)
    v4 = audit._verify_previous_v4_failed_source(
        repo, version_spec=audit._version_spec(5), _sources=_sources,
    )
    report["inputs"].extend(v1["inputs"])
    report["inputs"].extend(v2["inputs"])
    report["inputs"].extend(v2_final["inputs"])
    report["inputs"].extend(v3["inputs"])
    report["inputs"].extend(v4["inputs"])
    report["checks"]["historical_sources"] = "passed"
    mark("historical_sources", "passed")

    mark("frozen_input_and_parent", "running")
    acceptance, base_delivery, acceptance_raw, base_delivery_raw = audit._verify_acceptance_delivery(
        baseline, _sources=_sources,
    )
    dual = audit._verify_final_build_chain(
        repo, baseline, acceptance, base_delivery, _sources=_sources,
    )
    fixed = audit._snapshot_fixed_sources(
        repo, baseline, mark=lambda *_args: None, _sources=_sources,
        _option_spec=_option_spec, _reservation_profile=_reservation_profile,
        _reservation_spec=_reservation_spec, _candidate_spec=_candidate_spec,
        source_collector=source_collector,
        stdout_contract="verification-accounting-v1",
        _preverified_baseline=(acceptance, base_delivery, acceptance_raw, base_delivery_raw),
    )
    _require(fixed["report_binding"]["prepared_sha256"] == profile.prepared_sha256
             and fixed["report_binding"]["stage2_input_sha256"] == profile.stage2_input_sha256,
             "recovery_pinned_saved_input_hash_mismatch")
    report["baseline"].update({
        "context": fixed["report_binding"]["context"],
        "manifest_sha256": fixed["report_binding"]["manifest_sha256"],
        "prepared_sha256": fixed["report_binding"]["prepared_sha256"],
        "stage1_receipt_sha256": fixed["report_binding"]["stage1_receipt_sha256"],
        "stage2_input_sha256": fixed["report_binding"]["stage2_input_sha256"],
        "stage2_receipt_absent": fixed["initial"]["stage2_receipt_absent"],
    })
    report["inputs"].extend(dual["inputs"])
    report["inputs"].extend(fixed["inputs"])
    report["checks"]["frozen_input_and_parent"] = "passed"
    mark("frozen_input_and_parent", "passed")

    mark("saved_process_evidence", "running")
    build = v5_sources["build"]
    runner_build = v5_sources["runner_build"]
    runner_role_map = {
        "runner": "new_runner", "build_record": "new_build_record",
        "source_archive": "new_source_archive", "source_file_list": "new_source_file_list",
    }
    report["inputs"].extend(
        {**item, "role": runner_role_map[item["role"]]}
        for item in runner_build.get("inputs", [])
    )
    process, process_rows = _saved_process(repo, delivery, fixed["manifest"], profile)
    report["saved_process_evidence"].update({key: process[key] for key in (
        "role", "mode", "status", "return_code", "metadata_sha256",
        "stdout_sha256", "stdout_bytes", "stderr_sha256", "stderr_bytes",
        "trace_event_count", "asset_scan_elapsed_ns", "historical_scan_time_certified",
    ) if key in process})
    # Role and mode are fixed in the contract, not process-provided overrides.
    report["inputs"].extend(process_rows)
    report["checks"]["saved_process_evidence"] = "passed"

    mark("scope_ledger_semantics", "running")
    option_spec = _option_spec or OPTION_VERIFICATION_SCOPE
    scope_root = repo / option_spec.output_root
    research = scope_root / "research"
    stage1_receipt = strict_json(safe_path(research / "stage-1.json").read_bytes())
    sidecar = strict_json(safe_path(scope_root / "stage-1-process-diagnostic.json").read_bytes())
    stage1_stdout = safe_path(scope_root / sidecar["stdout"]["path"]).read_bytes()
    ledger = _parse_scope_ledger_from_repo(
        repo, fixed["manifest"], stage1_receipt, stage1_stdout,
        option_spec=option_spec,
    )
    _require(ledger["ledger_sha256"] == profile.ledger_sha256,
             "recovery_pinned_scope_ledger_hash_mismatch")
    process_ledger = process["result"].get("ledger")
    expected_process_ledger = {
        "consumed": ledger["stats"]["consumed"],
        "completed": ledger["stats"]["completed"],
        "unknown": ledger["stats"]["unknown"],
        "reserved": ledger["stats"]["reserved"],
        "abandoned": ledger["stats"]["abandoned"],
        "limit": ledger["stats"]["limit"],
    }
    _require(isinstance(process_ledger, dict)
             and set(process_ledger) == set(expected_process_ledger)
             and all(type(value) is int for value in process_ledger.values())
             and process_ledger == expected_process_ledger,
             "recovery_saved_stdout_ledger_mismatch")
    report["accounting"].update({
        "original_scope_consumed": ledger["stats"]["consumed"],
        "original_scope_completed": ledger["stats"]["completed"],
        "original_scope_unknown": ledger["stats"]["unknown"],
        "original_scope_limit": ledger["stats"]["limit"],
        "certified_historical_consumed_before_scope": 32,
        "certified_historical_consumed_including_scope": 32 + ledger["stats"]["consumed"],
        "planning_total": 39 + ledger["stats"]["consumed"],
        "reservation_id": profile.reservation_id,
    })
    blob_root = research / "calls.jsonl.blobs"
    for kind, hashes in ledger["blob_hashes"].items():
        for index, blob_hash in enumerate(hashes, start=1):
            path = safe_path(blob_root / kind / f"{blob_hash}.json")
            report["inputs"].append(audit._record_input(
                repo, f"curry_scope_blob_{kind}_{index:02d}", path, path.read_bytes(),
            ))
    report["source_groups"] = {
        "v5_original_audit_roles": len(
            [row for row in report["inputs"] if row["role"] not in {
                "v5_delivery", "v5_observation", "v5_command_log",
                "v5_final_source_archive", "v5_final_source_file_list",
            } and not row["role"].startswith((
                "curry_scope_blob_", "previous_recovery_",
            ))]
        ),
        "v5_recovery_anchors": len(anchor_rows),
        "curry_scope_blob_roles": sum(len(v) for v in ledger["blob_hashes"].values()),
        "v3_reservation_roles": len([
            row for row in report["inputs"] if row["role"].startswith("v3_source_")
        ]),
    }
    if version_spec.report_version == 2:
        report["source_groups"]["previous_recovery_roles"] = sum(
            row["role"].startswith("previous_recovery_")
            for row in report["inputs"]
        )
    elif version_spec.report_version == 3:
        report["source_groups"]["previous_recovery_v1_roles"] = sum(
            row["role"].startswith("previous_recovery_")
            and not row["role"].startswith("previous_recovery_v2_")
            for row in report["inputs"]
        )
        report["source_groups"]["previous_recovery_v2_roles"] = sum(
            row["role"].startswith("previous_recovery_v2_")
            for row in report["inputs"]
        )
    _validate_input_rows(report["inputs"], success=True, version_spec=version_spec)
    expected_source_groups = {
        "v5_original_audit_roles": 164,
        "v5_recovery_anchors": 5,
        "curry_scope_blob_roles": 6,
        "v3_reservation_roles": 100,
    }
    if version_spec.report_version == 2:
        expected_source_groups["previous_recovery_roles"] = 6
    elif version_spec.report_version == 3:
        expected_source_groups["previous_recovery_v1_roles"] = 6
        expected_source_groups["previous_recovery_v2_roles"] = 6
    _require(report["source_groups"] == expected_source_groups,
             "recovery_source_group_counts_invalid")
    report["checks"]["scope_ledger_semantics"] = "passed"

    mark("input_stability", "running")
    reservation_root = repo / profile.reservation_root
    previous_roots = tuple(repo / path for path in profile.historical_roots)
    def snapshot_inputs() -> tuple[dict[str, Any], dict[str, str]]:
        """Collect stability groups independently so one unreadable path does
        not erase evidence already obtained for the remaining groups.
        """
        values: dict[str, Any] = {}
        failures: dict[str, str] = {}

        def capture(name: str, callback: Callable[[], Any]) -> None:
            try:
                values[name] = callback()
            except Exception as error:
                failures[name] = _stable_error_code(
                    error, "recovery_stability_snapshot_failed",
                )

        capture("workspace", lambda: source_collector(repo))
        capture("v5_tree", lambda: {
            "tree": _snapshot_tree(v5_root),
            "observation_sha256": _sha(safe_path(repo / profile.observation_path).read_bytes()),
            "command_log_sha256": _sha(safe_path(repo / profile.command_log_path).read_bytes()),
        })
        capture("baseline_tree", lambda: {
            "tree": _snapshot_tree(baseline),
            "evidence": _snapshot_curry_evidence(baseline),
        })
        capture("reservation_tree", lambda: _snapshot_tree(reservation_root))
        if version_spec.report_version in (2, 3):
            previous_root = repo / version_spec.previous_recovery_root
            capture("previous_recovery_tree", lambda: _snapshot_tree(previous_root))
        if version_spec.report_version == 3:
            previous_v2_root = repo / version_spec.previous_recovery_v2_root
            capture("previous_recovery_v2_tree", lambda: _snapshot_tree(previous_v2_root))

        def snapshot_history() -> list[dict[str, str]]:
            rows: list[dict[str, str]] = []
            for index, path in enumerate(previous_roots):
                rows.append({"source_index": str(index), "snapshot_sha256": _sha(canonical(_snapshot_tree(path)))})
            return rows

        capture("historical_trees", snapshot_history)
        capture("ledger_and_blobs", lambda: {
            "ledger_sha256": _sha(safe_path(research / "calls.jsonl").read_bytes()),
            "blob_tree": _snapshot_blob_tree(blob_root),
        })
        capture("stage2_receipt_absent", lambda: (
            not (research / "stage-2.json").exists()
            and not (research / "stage-2.json").is_symlink()
        ))
        return values, failures

    # The first check and recheck are separate passes. If a first read fails,
    # still attempt the second pass so a transient error is not mislabeled as
    # every source having drifted. The original failure remains the checkpoint.
    evidence_before, first_failures = snapshot_inputs()
    if ("workspace" not in first_failures
            and evidence_before.get("workspace") != workspace_before):
        first_failures["workspace"] = "recovery_workspace_changed_before_stability_snapshot"
    if first_failures:
        report["stability"]["first_check"] = "failed"
    else:
        report["stability"]["first_check"] = "passed"
    # Re-read all pinned inputs now; this catches drift during the chain walk.
    input_rows_failure: BaseException | None = None
    try:
        _verify_input_rows(repo, report["inputs"], version_spec=version_spec)
        report["stability"]["input_rows_revalidation"] = "passed"
    except Exception as error:
        input_rows_failure = error
        report["stability"]["input_rows_revalidation"] = "failed"
    evidence_after, recheck_failures = snapshot_inputs()
    report["stability"]["recheck"] = (
        "failed" if recheck_failures else "passed"
    )

    group_values = {
        "workspace": ("workspace",),
        "v5_tree": ("v5_tree",),
        "baseline_tree": ("baseline_tree",),
        "reservation_tree": ("reservation_tree",),
        "historical_trees": ("historical_trees",),
        "ledger_and_blobs": ("ledger_and_blobs",),
    }
    if version_spec.report_version in (2, 3):
        group_values["previous_recovery_tree"] = ("previous_recovery_tree",)
    if version_spec.report_version == 3:
        group_values["previous_recovery_v2_tree"] = ("previous_recovery_v2_tree",)
    recheck_drift = False
    for output_name, source_names in group_values.items():
        source_name = source_names[0]
        if source_name in first_failures:
            state = "first_check_failed"
        elif source_name in recheck_failures:
            state = "recheck_failed"
        elif evidence_before.get(source_name) != evidence_after.get(source_name):
            state = "changed"
            recheck_drift = True
        else:
            state = "consistent"
        report["stability"][output_name] = state
    before_absent = evidence_before.get("stage2_receipt_absent")
    after_absent = evidence_after.get("stage2_receipt_absent")
    report["stability"]["stage2_receipt_absent_before"] = before_absent
    report["stability"]["stage2_receipt_absent_after"] = after_absent
    if first_failures:
        raise ValueError(next(iter(first_failures.values())))
    if input_rows_failure is not None:
        raise ValueError(_stable_error_code(input_rows_failure)) from None
    if recheck_failures:
        report["stability"]["recheck"] = "failed"
        raise ValueError(next(iter(recheck_failures.values())))
    _require(before_absent is True and after_absent is True,
             "recovery_stage2_receipt_unexpected")
    _require(not recheck_drift and evidence_after == evidence_before,
             "recovery_input_stability_failed")
    report["checks"]["input_stability"] = "passed"
    report["checks"]["report_publication"] = "not_run"
    mark("saved_process_evidence", "passed")
    mark("scope_ledger_semantics", "passed")
    mark("input_stability", "passed")
    return report, {
        "evidence_before": evidence_before,
        "v5_root": v5_root,
        "baseline": baseline,
        "reservation_root": reservation_root,
        "historical_roots": previous_roots,
        "stage2_receipt": research / "stage-2.json",
        "scope_root": scope_root,
        "ledger": ledger,
        "manifest": fixed["manifest"],
        "workspace_before": workspace_before,
        "workspace_after": evidence_after.get("workspace"),
    }


def _validate_input_rows(
    rows: Any, *, success: bool, version_spec: RecoveryVersionSpec = V1_SPEC,
) -> None:
    _require(isinstance(rows, list), "recovery_input_set_invalid")
    roles: set[str] = set()
    paths: dict[str, tuple[str, int]] = {}
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {"role", "path", "sha256", "bytes"}
                 and isinstance(row.get("role"), str) and row["role"]
                 and row["role"] not in roles
                 and isinstance(row.get("path"), str) and row["path"]
                 and "\\" not in row["path"] and ":" not in row["path"]
                 and HASH.fullmatch(str(row.get("sha256", ""))) is not None
                 and type(row.get("bytes")) is int and row["bytes"] >= 0,
                 "recovery_input_record_invalid")
        roles.add(row["role"])
        previous = paths.setdefault(row["path"], (row["sha256"], row["bytes"]))
        _require(previous == (row["sha256"], row["bytes"]),
                 "recovery_input_path_alias_conflict")
    expected = _expected_input_roles(version_spec)
    # Historical source audits pin this validator as the consumer of the
    # V3_INPUT_ROLE_ALLOWLIST-derived role set and the 175/181 legacy sizes.
    if version_spec.report_version in (1, 2):
        _require(len(expected) == {1: 175, 2: 181}[version_spec.report_version],
                 "recovery_input_role_basis_invalid")
    if success:
        expected_count = {1: 175, 2: 181, 3: 187}[version_spec.report_version]
        _require(len(expected) == expected_count and roles == expected
                 and len(rows) == expected_count,
                 "recovery_success_input_set_incomplete")
    elif version_spec.report_version == 3:
        _require(roles <= expected, "recovery_failure_input_role_unexpected")


def _expected_input_roles(version_spec: RecoveryVersionSpec) -> frozenset[str]:
    """Return the version-pinned successful input role universe."""
    from ygo_eval import curry_ledger_handoff_audit as audit

    expected = set(audit.V5_REQUIRED_INPUT_ROLES)
    expected.update({
        "native_build_record", "native_cli_artifact",
        "native_runner_artifact", "native_worker_artifact",
        "v5_delivery", "v5_observation", "v5_command_log",
        "v5_final_source_archive", "v5_final_source_file_list",
    })
    if version_spec.report_version in (2, 3):
        expected.update({
            "previous_recovery_failed_report",
            "previous_recovery_tool_archive",
            "previous_recovery_tool_file_list",
            "previous_recovery_final_delivery",
            "previous_recovery_final_source_archive",
            "previous_recovery_final_source_file_list",
        })
    if version_spec.report_version == 3:
        expected.update({
            "previous_recovery_v2_failed_report",
            "previous_recovery_v2_tool_archive",
            "previous_recovery_v2_tool_file_list",
            "previous_recovery_v2_final_delivery",
            "previous_recovery_v2_final_source_archive",
            "previous_recovery_v2_final_source_file_list",
        })
        expected.update(_v3_reservation_input_roles())
    else:
        expected.update(
            role for role in audit.V3_INPUT_ROLE_ALLOWLIST
            if role.startswith("v3_source_")
        )
    expected.update(_v3_scope_blob_roles())
    return frozenset(expected)


def _v3_scope_blob_roles() -> tuple[str, ...]:
    return tuple(
        f"curry_scope_blob_{kind}_{index:02d}"
        for kind, count in (("checkpoints", 4), ("results", 1), ("events", 1))
        for index in range(1, count + 1)
    )


def _v3_failure_role_groups(
    version_spec: RecoveryVersionSpec,
) -> dict[str, frozenset[str]]:
    expected = _expected_input_roles(version_spec)
    previous_v2 = frozenset(role for role in expected if role.startswith(
        "previous_recovery_v2_"
    ))
    previous_v1 = frozenset(
        role for role in expected
        if role.startswith("previous_recovery_") and role not in previous_v2
    )
    v5_anchors = frozenset({
        "v5_delivery", "v5_observation", "v5_command_log",
        "v5_final_source_archive", "v5_final_source_file_list",
    })
    historical = frozenset(
        role for role in expected
        if role.startswith((
            "previous_v1_", "previous_v2_", "v2_final_",
            "previous_v3_", "previous_v4_",
        ))
    )
    blobs = frozenset(_v3_scope_blob_roles())
    runner_build = frozenset({
        "new_runner", "new_build_record", "new_source_archive", "new_source_file_list",
    })
    process_diagnostics = frozenset({
        "new_runner_capture_metadata", "new_runner_stdout", "new_runner_stderr",
    })
    frozen = expected - previous_v2 - previous_v1 - v5_anchors - historical - blobs \
        - runner_build - process_diagnostics
    return {
        "previous_recovery_v2_roles": previous_v2,
        "previous_recovery_v1_roles": previous_v1,
        "v5_recovery_anchors": v5_anchors,
        "historical_sources": historical,
        "frozen_input_and_parent": frozenset(frozen),
        "new_runner_build": runner_build,
        "saved_process_evidence": process_diagnostics,
        "curry_scope_blob_roles": blobs,
    }


def _validate_v3_failed_input_rows(value: dict[str, Any], version_spec: RecoveryVersionSpec) -> None:
    """Tie failed-report evidence rows to completed atomic source gates."""
    rows = value.get("inputs")
    checks = value.get("checks")
    groups = value.get("source_groups")
    _require(isinstance(rows, list), "recovery_input_set_invalid")
    _require(isinstance(checks, dict), "recovery_check_set_invalid")
    _require(isinstance(groups, dict), "recovery_source_group_set_invalid")
    observed = _v3_source_group_counts(rows)
    expected_previous_groups = {
        "previous_recovery_v1_roles": (
            6 if checks.get("previous_recovery_failed_source") == "passed" else 0
        ),
        "previous_recovery_v2_roles": (
            6 if checks.get("previous_recovery_v2_failed_source") == "passed" else 0
        ),
    }
    _require(
        all(observed[name] == count and groups.get(name) == count
            for name, count in expected_previous_groups.items()),
        "recovery_previous_source_group_rows_mismatch",
    )
    role_groups = _v3_failure_role_groups(version_spec)
    roles = {row["role"] for row in rows}
    checkpoint = value.get("failure_checkpoint")
    _require(checkpoint in version_spec.checks, "recovery_failure_checkpoint_invalid")

    exact_gates = (
        ("previous_recovery_v2_failed_source", "previous_recovery_v2_roles"),
        ("previous_recovery_failed_source", "previous_recovery_v1_roles"),
        ("v5_delivery_and_archives", "v5_recovery_anchors"),
        ("historical_sources", "historical_sources"),
        ("frozen_input_and_parent", "frozen_input_and_parent"),
    )
    for check_name, group_name in exact_gates:
        group_roles = role_groups[group_name]
        present = roles & group_roles
        if checks.get(check_name) == "passed":
            _require(present == group_roles, "recovery_failure_source_gate_rows_mismatch")
        else:
            _require(not present, "recovery_failure_input_role_unexpected")

    runner_roles = role_groups["new_runner_build"]
    runner_rows = roles & runner_roles
    saved_process_index = version_spec.checks.index("saved_process_evidence")
    checkpoint_index = version_spec.checks.index(checkpoint)
    if checks.get("saved_process_evidence") == "passed":
        _require(runner_rows == runner_roles,
                 "recovery_failure_source_gate_rows_mismatch")
    elif checkpoint_index == saved_process_index:
        _require(runner_rows in (frozenset(), runner_roles),
                 "recovery_failure_source_gate_rows_mismatch")
    else:
        _require(not runner_rows, "recovery_failure_input_role_unexpected")

    process_roles = role_groups["saved_process_evidence"]
    process_rows = roles & process_roles
    if checks.get("saved_process_evidence") == "passed":
        _require(process_rows == process_roles,
                 "recovery_failure_source_gate_rows_mismatch")
    else:
        _require(not process_rows, "recovery_failure_input_role_unexpected")

    _require(groups == observed, "recovery_failure_source_group_rows_mismatch")

    blob_order = _v3_scope_blob_roles()
    input_roles = [row["role"] for row in rows]
    blob_rows = [role for role in input_roles if role in role_groups["curry_scope_blob_roles"]]
    if checks.get("scope_ledger_semantics") == "passed":
        _require(blob_rows == list(blob_order), "recovery_failure_scope_blob_prefix_invalid")
        _require(input_roles[-len(blob_order):] == list(blob_order),
                 "recovery_failure_scope_blob_prefix_invalid")
    elif checkpoint == "scope_ledger_semantics":
        _require(blob_rows == list(blob_order[:len(blob_rows)]),
                 "recovery_failure_scope_blob_prefix_invalid")
        if blob_rows:
            _require(input_roles[-len(blob_rows):] == blob_rows,
                     "recovery_failure_scope_blob_prefix_invalid")
    else:
        _require(not blob_rows, "recovery_failure_input_role_unexpected")


def _v1_previous_source_record_valid(
    value: Any, version_spec: RecoveryVersionSpec, profile: RecoveryProfile,
) -> bool:
    return (
        isinstance(value, dict)
        and value.get("report_sha256") == version_spec.previous_recovery_report_sha256
        and value.get("delivery_sha256") == version_spec.previous_recovery_delivery_sha256
        and value.get("status") == "failed"
        and value.get("failure_checkpoint") == "v5_delivery_and_archives"
        and value.get("diagnostic") == "recovery_v5_source_delta_invalid"
        and value.get("source_delta") == profile.source_delta
        and isinstance(value.get("final_source_identity"), str)
        and HASH.fullmatch(value["final_source_identity"]) is not None
        and value.get("final_file_count") == 583
    )


def _v2_previous_source_record_valid(
    value: Any, version_spec: RecoveryVersionSpec,
) -> bool:
    return (
        isinstance(value, dict)
        and value.get("report_sha256") == version_spec.previous_recovery_v2_report_sha256
        and value.get("delivery_sha256") == version_spec.previous_recovery_v2_delivery_sha256
        and value.get("status") == "failed"
        and value.get("failure_checkpoint") == "scope_ledger_semantics"
        and value.get("diagnostic") == "recovery_success_input_set_incomplete"
        and HASH.fullmatch(str(value.get("final_source_identity", ""))) is not None
        and value.get("final_file_count") == 586
        and value.get("v3_role_count") == 100
        and value.get("workspace_identity_present") is True
        and value.get("confirmation_summary_present") is False
        and value.get("v3_role_difference") == {
            "missing_from_report": ["v3_source_confirmation_summary"],
            "unexpected_in_report": ["v3_source_workspace_identity"],
        }
    )


def _verify_input_rows(
    repo: Path, rows: list[dict[str, Any]],
    *, version_spec: RecoveryVersionSpec = V1_SPEC,
) -> None:
    from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE
    from ygo_eval.native_curry_option_validation import (
        _curry_evidence_hash, _snapshot_curry_evidence,
    )

    for row in rows:
        relative = PurePosixPath(row["path"])
        _require(not relative.is_absolute() and ".." not in relative.parts,
                 "recovery_input_path_unsafe")
        path = repo.joinpath(*relative.parts)
        if row["role"] == "v3_source_tenki_validation_directory_evidence":
            _require(relative == PurePosixPath(V3_TENKI_EVIDENCE_RELATIVE.as_posix())
                     and row["bytes"] == 0,
                     "recovery_directory_input_binding_invalid")
            found = _curry_evidence_hash(_snapshot_curry_evidence(safe_path(path, file=False)))
            size = 0
        else:
            raw = safe_path(path).read_bytes()
            found, size = _sha(raw), len(raw)
        _require(found == row["sha256"] and size == row["bytes"],
                 "recovery_input_content_changed")


def _v3_source_group_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    roles = [row["role"] for row in rows]
    recovery_anchors = {
        "v5_delivery", "v5_observation", "v5_command_log",
        "v5_final_source_archive", "v5_final_source_file_list",
    }
    return {
        "v5_original_audit_roles": sum(
            role not in recovery_anchors
            and not role.startswith(("curry_scope_blob_", "previous_recovery_"))
            for role in roles
        ),
        "v5_recovery_anchors": sum(role in recovery_anchors for role in roles),
        "curry_scope_blob_roles": sum(
            role.startswith("curry_scope_blob_") for role in roles
        ),
        "v3_reservation_roles": sum(role.startswith("v3_source_") for role in roles),
        "previous_recovery_v1_roles": sum(
            role.startswith("previous_recovery_")
            and not role.startswith("previous_recovery_v2_")
            for role in roles
        ),
        "previous_recovery_v2_roles": sum(
            role.startswith("previous_recovery_v2_") for role in roles
        ),
    }


def validate_report(
    value: Any, *, schema_path: Path | None = None, schema_raw: bytes | None = None,
    profile: RecoveryProfile = PRODUCTION_PROFILE,
    version_spec: RecoveryVersionSpec = V1_SPEC,
) -> bool:
    _require(isinstance(value, dict), "recovery_report_invalid")
    if version_spec.report_version == 3 and value.get("status") == "failed":
        _validate_input_rows(
            value.get("inputs"), success=False, version_spec=version_spec,
        )
        _validate_v3_failed_input_rows(value, version_spec)
    if value.get("status") == "incomplete":
        accounting = value.get("accounting")
        _require(isinstance(accounting, dict)
                 and all(accounting.get(name) is None for name in (
                     "original_scope_consumed", "original_scope_completed",
                     "original_scope_unknown", "certified_historical_consumed_before_scope",
                     "certified_historical_consumed_including_scope", "reservation_id",
                     "planning_total",
                 )), "recovery_incomplete_accounting_invalid")
    schema_file = schema_path or (
        Path(__file__).resolve().parents[2] / "schemas" / version_spec.schema_name
    )
    schema = strict_json(schema_raw if schema_raw is not None else schema_file.read_bytes())
    jsonschema.validate(value, schema)
    _require(value.get("native_calls") == 0
             and type(value.get("native_calls")) is int
             and value.get("runner_process_calls") == 0
             and type(value.get("runner_process_calls")) is int
             and value.get("execution_ready") is False
             and value.get("qualifications") == QUALIFICATIONS,
             "recovery_zero_call_contract_invalid")
    _validate_input_rows(
        value["inputs"], success=value["status"] == "passed",
        version_spec=version_spec,
    )
    accounting = value["accounting"]
    _require(accounting.get("scope") == SCOPE
             and accounting.get("policy_reserved") == 7
             and accounting.get("reservation_policy_id") == profile.reservation_policy_id
             and accounting.get("old_confirmation_actual_consumed") is None
             and accounting.get("actual_all_history_cumulative") is None,
             "recovery_accounting_basis_invalid")
    if value["status"] == "passed":
        _require(value.get("valid") is True
                 and isinstance(value.get("tool"), dict)
                 and value.get("failure_checkpoint") is None
                 and all(value["checks"][name] == "passed" for name in version_spec.checks)
                 and value.get("diagnostic") is None
                 and value.get("publication") == {
                     "state": "passed", "failure_phase": None, "diagnostic_id": None,
                 }
                 and accounting.get("certified_historical_consumed_before_scope") == 32
                 and accounting.get("reservation_id") == profile.reservation_id
                 and accounting.get("original_scope_consumed") == 1
                 and accounting.get("original_scope_completed") == 1
                 and accounting.get("original_scope_unknown") == 0
                 and accounting.get("original_scope_limit") == LIMIT
                 and accounting.get("certified_historical_consumed_including_scope") == 33
                 and accounting.get("planning_total") == 40,
                 "recovery_success_accounting_invalid")
        if version_spec.report_version == 3:
            expected_groups = {
                "v5_original_audit_roles": 164,
                "v5_recovery_anchors": 5,
                "curry_scope_blob_roles": 6,
                "v3_reservation_roles": 100,
                "previous_recovery_v1_roles": 6,
                "previous_recovery_v2_roles": 6,
            }
            _require(_v3_source_group_counts(value["inputs"]) == expected_groups
                     and value.get("source_groups") == expected_groups,
                     "recovery_source_group_counts_invalid")
        if version_spec.report_version in (2, 3):
            previous_source = value.get("previous_recovery_source")
            previous_check = value["checks"]["previous_recovery_failed_source"]
            previous_group = (
                "previous_recovery_roles" if version_spec.report_version == 2
                else "previous_recovery_v1_roles"
            )
            if previous_check == "passed":
                _require(value["source_groups"].get(previous_group) == 6
                         and _v1_previous_source_record_valid(
                             previous_source, version_spec, profile,
                         ), "recovery_previous_source_record_invalid")
            else:
                _require(value["source_groups"].get(previous_group) == 0
                         and isinstance(previous_source, dict)
                         and previous_source.get("report_sha256") == version_spec.previous_recovery_report_sha256
                         and previous_source.get("delivery_sha256") == version_spec.previous_recovery_delivery_sha256
                         and all(previous_source.get(name) is None for name in (
                             "status", "failure_checkpoint", "diagnostic", "source_delta",
                             "final_source_identity", "final_file_count",
                         )), "recovery_previous_source_unchecked_has_claims")
        if version_spec.report_version == 3:
            previous_v2 = value.get("previous_recovery_v2_source")
            previous_v2_check = value["checks"]["previous_recovery_v2_failed_source"]
            if previous_v2_check == "passed":
                _require(value["source_groups"].get("previous_recovery_v2_roles") == 6
                         and _v2_previous_source_record_valid(previous_v2, version_spec),
                         "recovery_previous_v2_source_record_invalid")
            else:
                _require(value["source_groups"].get("previous_recovery_v2_roles") == 0
                         and isinstance(previous_v2, dict)
                         and previous_v2.get("report_sha256") == version_spec.previous_recovery_v2_report_sha256
                         and previous_v2.get("delivery_sha256") == version_spec.previous_recovery_v2_delivery_sha256
                         and all(previous_v2.get(name) is None for name in (
                             "status", "failure_checkpoint", "diagnostic",
                             "final_source_identity", "final_file_count", "v3_role_count",
                             "workspace_identity_present", "confirmation_summary_present",
                             "v3_role_difference",
                         )), "recovery_previous_v2_source_unchecked_has_claims")
    elif value["status"] == "failed":
        checkpoint = value.get("failure_checkpoint")
        ordered_checks = [value["checks"][name] for name in version_spec.checks]
        failed_index = version_spec.checks.index(checkpoint) if checkpoint in version_spec.checks else -1
        _require(value.get("valid") is False and checkpoint in version_spec.checks
                 and value["checks"][checkpoint] == "failed"
                 and ordered_checks[:failed_index] == ["passed"] * failed_index
                 and ordered_checks[failed_index + 1:] == ["not_run"] * (len(version_spec.checks) - failed_index - 1)
                 and value.get("diagnostic") is not None
                 and value.get("publication", {}).get("state") in ("passed", "failed")
                 and all(item is None for item in (
                     accounting.get("original_scope_consumed"),
                     accounting.get("original_scope_completed"),
                     accounting.get("original_scope_unknown"),
                     accounting.get("certified_historical_consumed_before_scope"),
                     accounting.get("certified_historical_consumed_including_scope"),
                     accounting.get("reservation_id"),
                     accounting.get("planning_total"),
                 )), "recovery_failure_statistics_invalid")
        if version_spec.report_version in (2, 3):
            previous = value.get("previous_recovery_source")
            _require(isinstance(previous, dict)
                     and previous.get("report_sha256") == version_spec.previous_recovery_report_sha256
                     and previous.get("delivery_sha256") == version_spec.previous_recovery_delivery_sha256,
                     "recovery_previous_source_record_invalid")
            if value["checks"]["previous_recovery_failed_source"] == "passed":
                _require(_v1_previous_source_record_valid(previous, version_spec, profile),
                         "recovery_previous_source_record_invalid")
                group = ("previous_recovery_roles" if version_spec.report_version == 2
                         else "previous_recovery_v1_roles")
                _require(value["source_groups"].get(group) == 6,
                         "recovery_previous_source_record_invalid")
            else:
                group = ("previous_recovery_roles" if version_spec.report_version == 2
                         else "previous_recovery_v1_roles")
                _require(all(previous.get(name) is None for name in (
                    "status", "failure_checkpoint", "diagnostic", "source_delta",
                    "final_source_identity", "final_file_count",
                )) and value["source_groups"].get(group) == 0,
                    "recovery_previous_source_unchecked_has_claims")
        if version_spec.report_version == 3:
            previous_v2 = value.get("previous_recovery_v2_source")
            _require(isinstance(previous_v2, dict)
                     and previous_v2.get("report_sha256") == version_spec.previous_recovery_v2_report_sha256
                     and previous_v2.get("delivery_sha256") == version_spec.previous_recovery_v2_delivery_sha256,
                     "recovery_previous_v2_source_record_invalid")
            if value["checks"]["previous_recovery_v2_failed_source"] == "passed":
                _require(_v2_previous_source_record_valid(previous_v2, version_spec)
                         and value["source_groups"].get("previous_recovery_v2_roles") == 6,
                         "recovery_previous_v2_source_record_invalid")
            else:
                _require(all(previous_v2.get(name) is None for name in (
                    "status", "failure_checkpoint", "diagnostic",
                    "final_source_identity", "final_file_count", "v3_role_count",
                    "workspace_identity_present", "confirmation_summary_present",
                    "v3_role_difference",
                )) and value["source_groups"].get("previous_recovery_v2_roles") == 0,
                    "recovery_previous_v2_source_unchecked_has_claims")
    else:
        _require(value.get("status") == "incomplete" and value.get("valid") is False
                 and value.get("failure_checkpoint") is None
                 and value.get("diagnostic") is None
                 and value.get("tool") is None
                 and all(value["checks"][name] == "not_run" for name in version_spec.checks)
                 and all(value["source_groups"][name] == 0 for name in value["source_groups"])
                 and value["inputs"] == []
                 and all(accounting.get(name) is None for name in (
                     "original_scope_consumed", "original_scope_completed",
                     "original_scope_unknown", "certified_historical_consumed_before_scope",
                     "certified_historical_consumed_including_scope", "reservation_id",
                     "planning_total",
                 ))
                 and value.get("publication") == {
                     "state": "not_run", "failure_phase": None, "diagnostic_id": None,
                 }, "recovery_incomplete_accounting_invalid")
        if version_spec.report_version in (2, 3):
            previous = value.get("previous_recovery_source")
            _require(isinstance(previous, dict)
                     and previous.get("report_sha256") == version_spec.previous_recovery_report_sha256
                     and previous.get("delivery_sha256") == version_spec.previous_recovery_delivery_sha256
                     and all(previous.get(name) is None for name in (
                         "status", "failure_checkpoint", "diagnostic", "source_delta",
                         "final_source_identity", "final_file_count",
                     )), "recovery_previous_source_unchecked_has_claims")
        if version_spec.report_version == 3:
            previous_v2 = value.get("previous_recovery_v2_source")
            _require(isinstance(previous_v2, dict)
                     and previous_v2.get("report_sha256") == version_spec.previous_recovery_v2_report_sha256
                     and previous_v2.get("delivery_sha256") == version_spec.previous_recovery_v2_delivery_sha256
                     and all(previous_v2.get(name) is None for name in (
                         "status", "failure_checkpoint", "diagnostic",
                         "final_source_identity", "final_file_count", "v3_role_count",
                         "workspace_identity_present", "confirmation_summary_present",
                         "v3_role_difference",
                     )), "recovery_previous_v2_source_unchecked_has_claims")
    return True


def _snapshot_recovery_inputs(repo: Path, rows: list[dict[str, Any]]) -> dict[str, tuple[str, int]]:
    _verify_input_rows(repo, rows)
    return {row["role"]: (row["sha256"], row["bytes"]) for row in rows}


def _create_publication_diagnostic(
    repo: Path, *, phase: str, error: BaseException, report: dict[str, Any],
    diagnostic_id: str | None = None, error_code: str | None = None,
    output_state: str = "not_written", output_sha256: str | None = None,
    diagnostic_root: Path | None = None,
) -> str:
    """Persist private raw exception bytes and a path-free public diagnostic."""
    root = repo / (diagnostic_root or Path(
        "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    ))
    root.mkdir(parents=True, exist_ok=True)
    diagnostic_id = diagnostic_id or uuid.uuid4().hex
    raw_path = root / f"{diagnostic_id}.exception.txt"
    public_path = root / f"{diagnostic_id}.diagnostic.json"
    raw = f"{type(error).__name__}:{error}".encode("utf-8", "backslashreplace")
    public = {
        "schema_version": 1,
        "kind": "audit_publication_diagnostic",
        "diagnostic_id": diagnostic_id,
        "phase": phase,
        "error_code": error_code or {
            "report_validation": "report_validation_failed",
            "source_reconstruction": "source_reconstruction_failed",
            "exclusive_report_write": "exclusive_report_write_failed",
            "post_write_revalidation": "post_write_revalidation_failed",
        }.get(phase, "publication_failed"),
        "audit_status": report.get("status"),
        "failure_checkpoint": report.get("failure_checkpoint"),
        "candidate_sha256": _sha(canonical(report)),
        "output_state": output_state,
        "output_sha256": output_sha256,
        "raw_exception_sha256": _sha(raw),
        "raw_exception_bytes": len(raw),
        "native_calls": 0,
        "runner_process_calls": 0,
    }
    try:
        schema_path = Path(__file__).resolve().parents[2] / "schemas/audit-publication-diagnostic-v1.schema.json"
        jsonschema.validate(public, strict_json(schema_path.read_bytes()))
        with raw_path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _write_exclusive(public_path, json.dumps(
            public, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8"))
    except Exception:
        raise ValueError("publication_diagnostic_save_failed") from None
    saved = strict_json(safe_path(public_path).read_bytes())
    _require(saved == public, "publication_diagnostic_saved_mismatch")
    jsonschema.validate(saved, strict_json(schema_path.read_bytes()))
    return diagnostic_id


class RecoveryPublicationError(RuntimeError):
    def __init__(
        self, phase: str, code: str, diagnostic_id: str | None,
        output_sha256: str | None = None,
    ) -> None:
        super().__init__(code)
        self.phase = phase
        self.code = code
        self.diagnostic_id = diagnostic_id
        self.output_sha256 = output_sha256


def _publish_report(
    repo: Path, path: Path, report: dict[str, Any],
    profile: RecoveryProfile = PRODUCTION_PROFILE,
    version_spec: RecoveryVersionSpec = V1_SPEC,
    source_reconstructor: Callable[[], dict[str, Any]] | None = None,
) -> None:
    from ygo_eval.terminal_regression import immutable_write

    phase = "report_validation"
    schema_raw = None
    output_existed_before_write = path.exists() or path.is_symlink()
    report["publication"].update({
        "state": "passed", "failure_phase": None, "diagnostic_id": None,
    })
    try:
        if version_spec.report_version == 3 and report.get("status") == "passed":
            phase = "source_reconstruction"
            _require(source_reconstructor is not None,
                     "recovery_source_reconstruction_unavailable")
            rebuilt = source_reconstructor()
            _require(_publication_source_signature(rebuilt)
                     == _publication_source_signature(report),
                     "recovery_source_reconstruction_mismatch")
            phase = "report_validation"
        if isinstance(report.get("tool"), dict):
            tool_files = _verify_tool_bundle(
                path.parent, report["tool"], version_spec.tool_files,
            )
            schema_raw = tool_files.get("schemas/" + version_spec.schema_name)
            _require(schema_raw is not None, "recovery_saved_schema_missing")
        validate_report(
            report, schema_raw=schema_raw, profile=profile,
            version_spec=version_spec,
        )
        phase = "exclusive_report_write"
        immutable_write(path, report)
        phase = "post_write_revalidation"
        raw = safe_path(path).read_bytes()
        saved = strict_json(raw)
        _require(saved == report, "recovery_saved_report_mismatch")
        validate_report(
            saved, schema_raw=schema_raw, profile=profile,
            version_spec=version_spec,
        )
        if version_spec.report_version == 3 and saved.get("status") == "passed":
            phase = "post_write_revalidation"
            rebuilt = source_reconstructor() if source_reconstructor is not None else None
            _require(isinstance(rebuilt, dict)
                     and _publication_source_signature(rebuilt)
                     == _publication_source_signature(saved),
                     "recovery_post_write_source_recheck_mismatch")
    except Exception as error:
        diagnostic_id = uuid.uuid4().hex
        code = {
            "report_validation": "report_validation_failed",
            "source_reconstruction": "source_reconstruction_failed",
            "exclusive_report_write": "exclusive_report_write_failed",
            "post_write_revalidation": "post_write_revalidation_failed",
        }.get(phase, "publication_failed")
        # A publication failure must not leave an in-memory success claim for
        # callers or for the independent diagnostic. Earlier source failures
        # keep their original checkpoint and accounting-null semantics.
        if report.get("status") == "passed":
            report.update({
                "status": "failed",
                "valid": False,
                "failure_checkpoint": "report_publication",
                "diagnostic": code,
            })
            report["checks"]["report_publication"] = "failed"
            report["accounting"].update({
                "original_scope_consumed": None,
                "original_scope_completed": None,
                "original_scope_unknown": None,
                "certified_historical_consumed_before_scope": None,
                "certified_historical_consumed_including_scope": None,
                "reservation_id": None,
                "planning_total": None,
            })
        report["publication"].update({
            "state": "failed", "failure_phase": phase,
            "diagnostic_id": diagnostic_id,
        })
        output_sha256 = None
        output_state = "not_written"
        try:
            if path.is_symlink():
                output_state = "existing_preserved" if output_existed_before_write else "write_attempted_unverified"
            elif path.is_file():
                output_sha256 = _sha(path.read_bytes())
                if phase == "post_write_revalidation" and version_spec.report_version >= 3:
                    if not output_existed_before_write:
                        path.unlink()
                        output_sha256 = None
                        output_state = "not_written"
                    else:
                        output_state = "written_unverified"
                elif phase == "post_write_revalidation":
                    output_state = "written_unverified"
                elif output_existed_before_write:
                    output_state = "existing_preserved"
                else:
                    output_state = "write_attempted_unverified"
            elif path.exists() and output_existed_before_write:
                # A directory or other existing non-file target is still
                # protected by the exclusive-write rule and must be reported
                # as preserved, even though it has no single-file digest.
                output_state = "existing_preserved"
        except OSError:
            output_state = "write_attempted_unverified" if phase != "report_validation" else "not_written"
        try:
            _create_publication_diagnostic(
                repo, phase=phase, error=error, report=report,
                diagnostic_id=diagnostic_id, error_code=code,
                output_state=output_state, output_sha256=output_sha256,
                diagnostic_root=version_spec.diagnostic_root,
            )
        except Exception:
            raise RecoveryPublicationError(
                phase, "publication_diagnostic_save_failed", None, output_sha256,
            ) from None
        raise RecoveryPublicationError(
            phase, code, diagnostic_id, output_sha256,
        ) from None


def _publish_for_version(
    repo: Path, path: Path, report: dict[str, Any],
    profile: RecoveryProfile, version_spec: RecoveryVersionSpec,
    source_reconstructor: Callable[[], dict[str, Any]] | None = None,
) -> None:
    """Preserve the V1 call shape while selecting newer contracts explicitly."""
    if version_spec.report_version == 1:
        _publish_report(repo, path, report, profile)
    else:
        _publish_report(
            repo, path, report, profile, version_spec,
            source_reconstructor=source_reconstructor,
        )


def _publication_source_signature(report: dict[str, Any]) -> bytes:
    """Canonicalize only the pure source result, excluding publication state."""
    keys = (
        "tool", "v5_source", "checks", "source_groups", "baseline", "saved_process_evidence",
        "accounting", "inputs", "stability", "previous_recovery_source",
        "previous_recovery_v2_source",
    )
    selected = {key: report[key] for key in keys if key in report}
    checks = dict(selected.get("checks", {}))
    checks.pop("report_publication", None)
    selected["checks"] = checks
    return canonical(selected)


def recover(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    source_collector: Callable[[Path], dict] = stable_source,
    clock: Callable[[], float] = time.monotonic,
    _sources: Any | None = None,
    _reservation_profile: Any | None = None,
    _reservation_spec: Any | None = None,
    _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    _profile: RecoveryProfile | None = None,
    _version_spec_override: RecoveryVersionSpec | None = None,
) -> dict[str, Any]:
    repo = Path(repo or Path(__file__).resolve().parents[2]).absolute()
    baseline = Path(args.baseline_dir).absolute()
    output = Path(args.output).absolute()
    version_spec = _version_spec_override or _version_spec(
        getattr(args, "report_version", 1),
    )
    profile = _profile or version_spec.profile
    if profile != version_spec.profile:
        version_spec = replace(version_spec, profile=profile)
    expected_baseline = repo / profile.v5_root
    output_root = repo / profile.output_root
    report_path = output_root / OUTPUT_NAME
    _require(baseline == expected_baseline, "recovery_fixed_baseline_required")
    _require(output == report_path, "recovery_fixed_output_required")
    _require(not baseline.is_symlink() and not output_root.is_symlink(),
             "recovery_symlink_rejected")
    from ygo_data.identity import checked_output
    checked_output(repo, output_root)

    if args.verify_only:
        return _verify_only(
            repo, output_root, report_path, source_collector=source_collector,
            _sources=_sources, _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec, _profile=profile,
            version_spec=version_spec,
        )

    report = _report_template(profile=profile, version_spec=version_spec)
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except Exception as error:
        phase = "exclusive_report_write"
        error_code = "recovery_output_root_create_failed"
        diagnostic_id = uuid.uuid4().hex
        output_state = "existing_preserved" if output_root.exists() else "not_written"
        report.update({
            "status": "failed", "valid": False,
            "failure_checkpoint": "report_publication",
            "diagnostic": error_code,
        })
        report["checks"]["report_publication"] = "failed"
        report["publication"].update({
            "state": "failed", "failure_phase": phase,
            "diagnostic_id": diagnostic_id,
        })
        try:
            _create_publication_diagnostic(
                repo, phase=phase, error=error, report=report,
                diagnostic_id=diagnostic_id, error_code=error_code,
                output_state=output_state,
                diagnostic_root=version_spec.diagnostic_root,
            )
        except Exception:
            raise RecoveryPublicationError(
                phase, "publication_diagnostic_save_failed", None,
            ) from None
        raise RecoveryPublicationError(
            phase, error_code, diagnostic_id,
        ) from None
    checkpoint = version_spec.checks[0]
    source_before = None
    before_tree = None
    started = clock()

    def mark_checkpoint(name: str, state: str) -> None:
        nonlocal checkpoint
        checkpoint = name
        if state == "passed":
            report["checks"][name] = "passed"
        elif state == "running":
            report["checks"][name] = "not_run"

    try:
        source_before = source_collector(repo)
        archive_raw, list_raw, tool = _tool_bundle(
            repo, source_before["identity"], version_spec.tool_files,
        )
        report["tool"] = tool
        _write_exclusive(output_root / tool["archive_path"], archive_raw)
        _write_exclusive(output_root / tool["file_list_path"], list_raw)
        _verify_tool_bundle(output_root, tool, version_spec.tool_files)
        report["checks"]["report_publication"] = "not_run"
        evidence, snapshots = _collect_evidence(
            repo, source_collector=source_collector, clock=clock,
            _sources=_sources, _reservation_profile=_reservation_profile,
            _reservation_spec=_reservation_spec, _option_spec=_option_spec,
            _candidate_spec=_candidate_spec, profile=profile,
            version_spec=version_spec,
            report_target=report, on_checkpoint=mark_checkpoint,
        )
        for key in (
            "v5_source", "checks", "source_groups", "baseline", "saved_process_evidence",
            "accounting", "inputs", "stability",
        ):
            report[key] = evidence[key]
        report["tool"] = tool
        checkpoint = "report_publication"
        report["status"] = "passed"
        report["valid"] = True
        report["failure_checkpoint"] = None
        report["diagnostic"] = None
        report["checks"]["report_publication"] = "passed"
        report["publication"]["state"] = "passed"
        report["elapsed_seconds"] = round(max(0.0, clock() - started), 6)
        def reconstruct_source() -> dict[str, Any]:
            reconstruction_target = _report_template(
                profile=profile, version_spec=version_spec,
            )
            reconstruction_target["tool"] = tool
            rebuilt, _ = _collect_evidence(
                repo, source_collector=source_collector, clock=clock,
                _sources=_sources, _reservation_profile=_reservation_profile,
                _reservation_spec=_reservation_spec, _option_spec=_option_spec,
                _candidate_spec=_candidate_spec, profile=profile,
                version_spec=version_spec, report_target=reconstruction_target,
                allow_saved_workspace_identity_change=False,
            )
            return rebuilt

        _publish_for_version(
            repo, report_path, report, profile, version_spec,
            source_reconstructor=(reconstruct_source if version_spec.report_version == 3 else None),
        )
        return report
    except Exception as error:
        # _publish_report already saved an independent diagnostic before it
        # raised this exception. Do not enter the ordinary failure-report
        # path and attempt a second write over the preserved/uncertain output.
        if isinstance(error, RecoveryPublicationError):
            raise
        if report.get("status") != "passed":
            report["status"] = "failed"
            report["valid"] = False
            report["failure_checkpoint"] = checkpoint
            report["diagnostic"] = (
                str(error) if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", str(error))
                else "recovery_failed"
            )
            if checkpoint in report["checks"]:
                report["checks"][checkpoint] = "failed"
            # Never infer zero from a partial attempt: keep all scope totals null.
            report["accounting"].update({
                "original_scope_consumed": None,
                "original_scope_completed": None,
                "original_scope_unknown": None,
                "certified_historical_consumed_before_scope": None,
                "certified_historical_consumed_including_scope": None,
                "reservation_id": None,
                "planning_total": None,
            })
            if version_spec.report_version == 3:
                report["source_groups"] = _v3_source_group_counts(report["inputs"])
            report["elapsed_seconds"] = round(max(0.0, clock() - started), 6)
            try:
                _publish_for_version(repo, report_path, report, profile, version_spec)
            except Exception:
                raise
        raise


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _verify_only(
    repo: Path, output_root: Path, report_path: Path, *,
    source_collector: Callable[[Path], dict], _sources: Any | None = None,
    _reservation_profile: Any | None = None, _reservation_spec: Any | None = None,
    _option_spec: Any | None = None, _candidate_spec: Any | None = None,
    _profile: RecoveryProfile = PRODUCTION_PROFILE,
    version_spec: RecoveryVersionSpec = V1_SPEC,
) -> dict[str, Any]:
    _require(output_root.is_dir() and not output_root.is_symlink(),
             "recovery_saved_output_missing")
    output_tree_before = _tree_snapshot(output_root)
    raw = safe_path(report_path).read_bytes()
    saved = strict_json(raw)
    tool_files = _verify_tool_bundle(output_root, saved["tool"], version_spec.tool_files)
    schema_raw = tool_files.get("schemas/" + version_spec.schema_name)
    _require(schema_raw is not None, "recovery_saved_schema_missing")
    validate_report(
        saved, schema_raw=schema_raw, profile=_profile,
        version_spec=version_spec,
    )
    _require(saved.get("status") == "passed" and saved.get("valid") is True,
             "recovery_saved_report_not_successful")
    verification_report = _report_template(
        profile=_profile, version_spec=version_spec,
    )
    verification_report["tool"] = saved.get("tool")
    source_before, verification_snapshots = _collect_evidence(
        repo, source_collector=source_collector, clock=time.monotonic,
        _sources=_sources, _reservation_profile=_reservation_profile,
        _reservation_spec=_reservation_spec, _option_spec=_option_spec,
        _candidate_spec=_candidate_spec, profile=_profile,
        version_spec=version_spec,
        allow_saved_workspace_identity_change=version_spec.allow_saved_workspace_identity_change,
        report_target=verification_report,
    )
    for key in (
        "v5_source", "checks", "source_groups", "baseline", "saved_process_evidence",
        "accounting", "inputs", "stability", "previous_recovery_source",
        "previous_recovery_v2_source",
    ):
        if version_spec.report_version == 1 and key == "previous_recovery_source":
            continue
        if version_spec.report_version != 3 and key == "previous_recovery_v2_source":
            continue
        expected = source_before[key]
        if key == "checks":
            expected = dict(expected)
            expected["report_publication"] = "passed"
        _require(expected == saved[key], "recovery_saved_source_binding_mismatch")
    _verify_input_rows(repo, saved["inputs"], version_spec=version_spec)
    output_tree_after = _tree_snapshot(output_root)
    _require(output_tree_after == output_tree_before,
             "recovery_output_tree_changed_during_verify")
    verification = {
        "schema_version": version_spec.report_version,
        "kind": (
            f"curry_ledger_handoff_recovery_verification_v{version_spec.report_version}"
            if version_spec.report_version in (2, 3)
            else "curry_ledger_handoff_recovery_verification"
        ),
        "valid": True,
        "recovery_report_sha256": _sha(raw),
        "source_input_count": len(saved["inputs"]),
        "native_calls": 0,
        "runner_process_calls": 0,
        "execution_ready": False,
        "qualifications": dict(QUALIFICATIONS),
    }
    if version_spec.report_version in (2, 3):
        workspace_before = verification_snapshots.get("workspace_before")
        workspace_after = verification_snapshots.get("workspace_after")
        _require(isinstance(workspace_before, dict)
                 and isinstance(workspace_after, dict)
                 and workspace_before.get("identity") == workspace_after.get("identity"),
                 "recovery_verify_workspace_changed_during_check")
        verification.update({
            "saved_tool_workspace_identity": saved["tool"]["workspace_identity"],
            "verification_tool_identity": workspace_before["identity"],
            "verification_tool_file_count": workspace_before.get("file_count"),
            "workspace_stable_during_verification": True,
        })
    return verification


def _tree_snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        _require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                 "recovery_tree_link_rejected")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
        elif not path.is_dir():
            raise ValueError("recovery_tree_entry_invalid")
    return result


def audit_to_output(args: argparse.Namespace, **kwargs: Any) -> dict[str, Any]:
    return recover(args, **kwargs)
