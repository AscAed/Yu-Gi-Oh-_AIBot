"""Offline, fixed-source preparation for the Ground Collapse opcode 24 probe.

This module reads frozen files and read-only SQLite data only.  It has no
runner, worker, FFI, journal-opening, or native-execution path.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import zipfile
from typing import Any, Callable

from ygo_data.identity import canonical, source_identity, stable_source
from ygo_eval.ground_collapse_protocol import (
    audit_ground_collapse_fixed_selection,
    audit_opcode18_fixed_zone_selection,
    canonical_zone_pairs,
    parse_field_disabled,
    parse_hint_zone,
    parse_opcode24,
    zone_response_bytes,
)
from ygo_eval.prompt_probe_logic import derive_candidates
from ygo_eval.prompt_probe_prepare import encode, safe_path, strict_json


OUTPUT_ROOT = Path("data/runtime/p1-ground-collapse-preparation-offline-2026-10-27")
OUTPUT_FILE = "preparation.json"
PUBLICATION_DIAGNOSTIC_FILE = "publication-diagnostic.json"
BASELINE_ROOT = Path("data/runtime/p1-curry-option-revalidation-native-2026-10-26")
PREPARATION_ACCEPTANCE = Path("data/runtime/p1-prompt-probes-offline-2026-10-21/acceptance.json")
PREPARATION_REPORT = Path("data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/report.json")
PREPARATION_CASES = Path("data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json")
FROZEN_CASES = Path("data/runtime/baseline-2026-10-19/research/frozen-cases.json")
CORE_SOURCE = Path("data/tmp/ocgcore-source")

CORE_PINS = {
    "libduel.cpp": "4b31e3247555b6548bcd2588e944a971d6f3032da0ed12f963235275aeef3e5a",
    "processor.cpp": "d051d6a006baa9ad4a590d4bcc185bff112e3ed7df256ff25cd8c0ff7beaf085",
    "ocgapi_constants.h": "191315f0c37bdc2fc086dee457bfc8ebb10b27cb1f063d26d5776465f9dbc4aa",
    "effect_constants.h": "6d14bc8ba1a1aa955815266fcb3db8b49ebf8174385bfd885a881f899c7041c6",
    "playerop.cpp": "a9ff2c499476f70afb4afa9d3880a0070bcd54f4baf9f116cd9e79f7107c9e97",
    "field.cpp": "9b6aa4916a8e2f7e95cab570be886e22751c197b320f15acdf1fa7de3c5dadfd",
}
SCRIPT_PINS = {
    "official/c90502999.lua": "67d95d32e1b6023c41516b0f15657af60121aa5b072dc85bb273fc1280912497",
}
SCRIPT_MANIFEST_PINS = {
    "official/c57103969.lua": "f616f84335cdc031435b491d078cb6b49660959075d6e95307f143f354bd2f65",
    "official/c58074572.lua": "df0569217bb3659ed774d21a158c86bb9aec65bca7f5725f03df97b479c5f9ac",
    "official/c90502999.lua": SCRIPT_PINS["official/c90502999.lua"],
    "utility.lua": "ace5e7811d8e9863ba0604cf7d90747e4ee010e11d30c4e1ebca29e82a5cb13c",
}
OLD_PROMPT_ACCEPTANCE_SHA256 = "0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7"
OLD_PROMPT_REPORT_SHA256 = "22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073"
OLD_PROMPT_CASES_SHA256 = "235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022"
FROZEN_CASES_SHA256 = "de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879"
OLD_COLLAPSE_CASE_SHA256 = "ccf3143c589472dc3ea48f2ef1fcf0216f64a55cd5365e2762a26745c036e52b"
CURRY_DELIVERY_SHA256 = "75598ee09563b02f897d8109f3088e57aa0da134f3dbbf987f5215012acd7731"
CURRY_NATIVE_ARCHIVE_SHA256 = "44b88010f9d589fe94005153f9ed456b65416df29f120ed1aa4267298060d03c"
CURRY_NATIVE_FILE_LIST_SHA256 = "c0d0067eb51e4aba5bd85324c7fa3f5cda2909114059b03325cf500c51f58744"
CURRY_NATIVE_IDENTITY = "cb9d709e728366dae890258e71e00586ea360b4438662495c2988050aa11f5d0"
CURRY_FINAL_ARCHIVE_SHA256 = "28cda2407c2fc75901fdabc219e80504ae9380533c6c7172ff58af1005c48fc0"
CURRY_FINAL_FILE_LIST_SHA256 = "c51b010a2d3c243b103fc6f26048f387cf6dc182f5f32f89831bd32df240502e"
CURRY_FINAL_IDENTITY = "adba6c80fc67c90cd25ede4af76fe8a4a363a874802b3e0d7ed99e1d03eaac9b"
CURRY_LEDGER_SHA256 = "aca9d113d148955905c8d65f681cc198b4015103b8fc7917ec6b04763a61143f"
CURRY_SUMMARY_SHA256 = "fcc3d1aebe8b97f6c954a56593c86461afd7b71613669e47c6c8e1ba0e0d9098"
ALLOWED_SOURCE_DIFFS = (
    "TASKS.md",
    "docs/INDEX.md",
    "docs/TESTING.md",
    "docs/superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md",
)
TOOL_FILES = (
    ".gitignore",
    "crates/ygo-engine-adapter/src/codec.rs",
    "crates/ygo-engine-adapter/tests/protocol.rs",
    "python/ygo_eval/ground_collapse_preparation.py",
    "python/ygo_eval/ground_collapse_protocol.py",
    "python/ygo_eval/prompt_probe_logic.py",
    "python/ygo_eval/prompt_probe_prepare.py",
    "python/ygo_eval/research.py",
    "schemas/ground-collapse-preparation-v1.schema.json",
    "tests/test_ground_collapse_preparation.py",
    "tests/test_ground_collapse_protocol.py",
)
QUALIFICATIONS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}


def _fixed_selection_rules() -> dict[str, Any]:
    return {
        "activation": "unique player-0 idle command-5 activation for card 90502999",
        "opcode18": {"unique_coordinate": {"player": 0, "location": 8, "sequence": 0},
                     "response_bytes": [0, 8, 0], "menu_order_assumption": False},
        "opcode24": {"ordered_zones": [
            {"player": 1, "location": 4, "sequence": 0},
            {"player": 1, "location": 4, "sequence": 1}],
            "response_bytes": [1, 4, 0, 1, 4, 1],
            "stop_on_missing_duplicate_or_unavailable": True,
            "no_reselection": True},
    }


EMPTY_FUTURE_NATIVE_BINDING = {
    "worker_sha256": None,
    "native_request_sha256": None,
    "actual_prompt_ids": None,
    "new_scope": None,
    "new_budget": None,
}


@dataclass(frozen=True, slots=True)
class GroundCollapseRevalidationSource:
    """Immutable test/source pins threaded into the existing recursive gates.

    Production construction remains fixed below.  Tests may provide a distinct
    synthetic source description, but it contains only paths, hashes, specs and
    source nodes; it cannot replace validators or report their results.
    """

    scope_spec: Any
    recovery_profile: Any
    recovery_version_spec: Any
    recovery_sources: Any | None
    reservation_profile: Any | None
    reservation_spec: Any | None
    reservation_sources: Any | None
    option_verification_spec: Any
    candidate_spec: Any
    recovery_delivery_workspace_identity: str
    recovery_delivery_workspace_file_count: int


@dataclass(frozen=True, slots=True)
class PreparationProfile:
    output_root: Path = OUTPUT_ROOT
    baseline_root: Path = BASELINE_ROOT
    acceptance_path: Path = PREPARATION_ACCEPTANCE
    preparation_report_path: Path = PREPARATION_REPORT
    preparation_cases_path: Path = PREPARATION_CASES
    frozen_cases_path: Path = FROZEN_CASES
    core_source_path: Path = CORE_SOURCE
    acceptance_sha256: str = OLD_PROMPT_ACCEPTANCE_SHA256
    preparation_report_sha256: str = OLD_PROMPT_REPORT_SHA256
    preparation_cases_sha256: str = OLD_PROMPT_CASES_SHA256
    frozen_cases_sha256: str = FROZEN_CASES_SHA256
    collapse_case_sha256: str = OLD_COLLAPSE_CASE_SHA256
    curry_delivery_sha256: str = CURRY_DELIVERY_SHA256
    native_archive_sha256: str = CURRY_NATIVE_ARCHIVE_SHA256
    native_file_list_sha256: str = CURRY_NATIVE_FILE_LIST_SHA256
    native_identity: str = CURRY_NATIVE_IDENTITY
    final_archive_sha256: str = CURRY_FINAL_ARCHIVE_SHA256
    final_file_list_sha256: str = CURRY_FINAL_FILE_LIST_SHA256
    final_identity: str = CURRY_FINAL_IDENTITY
    ledger_sha256: str = CURRY_LEDGER_SHA256
    summary_sha256: str = CURRY_SUMMARY_SHA256
    native_build_record_sha256: str = "e69857f8ba1179be09718b7584f255f67d7cb45b837f35af8f6804e7d0e8eadc"
    native_build_record_identity: str = "098981a0821f41d9a0cc609945555e2f8a9e0fe5c57016eeb7cc54057812b79b"
    core_pins: tuple[tuple[str, str], ...] = tuple(CORE_PINS.items())
    script_manifest_pins: tuple[tuple[str, str], ...] = tuple(SCRIPT_MANIFEST_PINS.items())
    target_script_pins: tuple[tuple[str, str], ...] = tuple(SCRIPT_PINS.items())
    source_diff: tuple[str, ...] = ALLOWED_SOURCE_DIFFS
    candidate_id: str = "prompt-24-collapse-v1"
    candidate_card_id: int = 90502999
    prior_certified_consumed: int = 40
    policy_reserved: int = 7
    planning_total: int = 47
    tool_files: tuple[str, ...] = TOOL_FILES
    revalidation_source: GroundCollapseRevalidationSource | None = None


PRODUCTION_PROFILE = PreparationProfile()


class PreparationError(ValueError):
    def __init__(self, code: str, role: str | None = None):
        self.code = code
        self.role = role
        super().__init__(code)


def _publication_diagnostic(error: PreparationError, *, checkpoint_override: str | None = None) -> dict[str, Any]:
    """Return a path-free diagnostic for failures before report publication."""
    role = error.role if isinstance(error.role, str) else None
    if (role is None or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*", role)
            or any(part == ".." for part in role.split("/"))):
        role = "preparation"
    if role == "tool_source" or error.code.startswith("tool_source"):
        resolved_checkpoint = "tool_bundle_capture"
    elif role == "tool_bundle":
        resolved_checkpoint = "tool_bundle_publication"
    elif role in {"preparation", "output", "tool_member"}:
        resolved_checkpoint = "report_publication"
    else:
        resolved_checkpoint = "source_checks"
    code = error.code if re.fullmatch(r"[a-z0-9_]+", error.code) else "preparation_failed"
    return {
        "schema_version": 1,
        "kind": "ground_collapse_preparation_publication_diagnostic_v1",
        "checkpoint": checkpoint_override or resolved_checkpoint,
        "code": code,
        "role": role,
        "native_calls": 0,
        "runner_process_calls": 0,
        "worker_calls": 0,
        "ffi_calls": 0,
        "execution_ready": False,
    }


def _save_publication_diagnostic(output: Path, error: PreparationError) -> None:
    diagnostic = _publication_diagnostic(error)
    _validate_publication_diagnostic(diagnostic)
    try:
        _write_exclusive(output / PUBLICATION_DIAGNOSTIC_FILE, encode(diagnostic))
    except PreparationError:
        raise PreparationError("publication_diagnostic_save_failed", "report_publication") from None


def _validate_publication_diagnostic(diagnostic: dict[str, Any]) -> None:
    required = {"schema_version", "kind", "checkpoint", "code", "role", "native_calls",
                "runner_process_calls", "worker_calls", "ffi_calls", "execution_ready"}
    if (not isinstance(diagnostic, dict) or set(diagnostic) != required
            or type(diagnostic.get("schema_version")) is not int
            or diagnostic.get("schema_version") != 1
            or diagnostic.get("kind") != "ground_collapse_preparation_publication_diagnostic_v1"
            or diagnostic.get("checkpoint") not in {
                "output_root_creation", "tool_bundle_capture", "tool_bundle_publication",
                "source_checks", "report_publication"
            }
            or not isinstance(diagnostic.get("code"), str)
            or not re.fullmatch(r"[a-z0-9_]+", diagnostic["code"])
            or not isinstance(diagnostic.get("role"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*", diagnostic["role"])
            or any(type(diagnostic.get(key)) is not int or diagnostic[key] != 0
                   for key in ("native_calls", "runner_process_calls", "worker_calls", "ffi_calls"))
            or diagnostic.get("execution_ready") is not False):
        raise PreparationError("publication_diagnostic_invalid", "report_publication")


class _Capture:
    def __init__(self) -> None:
        self.files: dict[Path, str] = {}
        self.role_hashes: dict[str, str] = {}
        self.role_bytes: dict[str, bytes] = {}
        self.directories: dict[str, dict[str, Any]] = {}
        self.protected: dict[Path, str] = {}

    def read(self, role: str, path: Path, expected: str | None = None) -> bytes:
        if role in self.role_hashes:
            raise PreparationError("duplicate_input_role", role)
        try:
            safe = safe_path(path)
            raw = safe.read_bytes()
        except (OSError, ValueError):
            code = "core_source_file_missing" if role.startswith("core/") else "source_file_unavailable"
            raise PreparationError(code, role) from None
        found = sha256(raw)
        if expected is not None and found != expected:
            raise PreparationError("source_hash_mismatch", role)
        absolute = Path(os.path.abspath(path))
        prior = self.files.get(absolute)
        if prior is not None and prior != found:
            raise PreparationError("input_changed_during_read", role)
        self.files[absolute] = found
        self.role_hashes[role] = found
        if role in {f"latest_curry_stage_request_{stage}" for stage in range(1, 8)}:
            self.role_bytes[role] = raw
        return raw

    def directory(self, role: str, path: Path) -> dict[str, Any]:
        if role in self.directories:
            raise PreparationError("duplicate_directory_role", role)
        try:
            safe = safe_path(path, file=False)
            entries = _directory_snapshot(safe)
        except (OSError, ValueError):
            raise PreparationError("source_directory_unavailable", role) from None
        self.directories[role] = {
            "sha256": sha256(encode(entries)),
            "entry_count": len(entries),
            "_entries": entries,
            "_path": safe,
        }
        return self.directories[role]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _strict_json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool/int equality coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_json_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def strict_json(raw: bytes | str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PreparationError("duplicate_json_key")
            result[key] = value
        return result

    def bad_constant(_value):
        raise PreparationError("nonfinite_json_number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        raise PreparationError("invalid_json") from None


def _directory_snapshot(path: Path) -> list[dict[str, Any]]:
    path = Path(os.path.abspath(path))
    safe_path(path, file=False)
    entries: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*"), key=lambda child: child.relative_to(path).as_posix()):
        try:
            info = item.lstat()
        except OSError:
            raise PreparationError("source_directory_read_failed") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PreparationError("linked_source_rejected")
        relative = item.relative_to(path).as_posix()
        if stat.S_ISDIR(info.st_mode):
            entries.append({"path": relative, "kind": "directory"})
        elif stat.S_ISREG(info.st_mode):
            raw = item.read_bytes()
            entries.append({"path": relative, "kind": "file", "bytes": len(raw), "sha256": sha256(raw)})
        else:
            raise PreparationError("unsupported_source_entry")
    return entries


def _canonical_tree_hash(entries: list[dict[str, Any]]) -> str:
    return sha256(encode(entries))


def _relative_input(repo: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise PreparationError("unsafe_fixed_source_path")
    return repo / relative


def _snapshot_record_map(records: list[dict[str, Any]]) -> dict[str, str]:
    return {entry["path"]: entry["sha256"] for entry in records if entry.get("kind") == "file"}


def _verify_source_archive(
    capture: _Capture,
    root: Path,
    archive_rel: Path,
    list_rel: Path,
    expected_archive_sha: str,
    expected_list_sha: str,
    expected_identity: str,
    expected_count: int,
    expected_head: str,
    role: str,
) -> dict[str, Any]:
    list_raw = capture.read(f"{role}_file_list", root / list_rel, expected_list_sha)
    archive_raw = capture.read(f"{role}_archive", root / archive_rel, expected_archive_sha)
    listing = strict_json(list_raw)
    files = listing.get("files") if isinstance(listing, dict) else None
    if (not isinstance(files, dict) or listing.get("kind") != "workspace_source_archive"
            or listing.get("schema_version") != 1 or listing.get("file_count") != expected_count
            or len(files) != expected_count or listing.get("source_identity") != expected_identity
            or listing.get("head") != expected_head
            or sha256(canonical({"head": expected_head, "files": files})) != expected_identity):
        raise PreparationError("source_archive_file_list_invalid", role)
    try:
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(archive_raw)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(files):
                raise PreparationError("source_archive_membership_invalid", role)
            for name, expected in files.items():
                path_name = Path(name) if isinstance(name, str) else Path(".")
                if (not isinstance(name, str) or path_name.is_absolute() or ".." in path_name.parts
                        or "\\" in name or ":" in name or not isinstance(expected, str)
                        or not re.fullmatch(r"[a-f0-9]{64}", expected)):
                    raise PreparationError("source_archive_member_pin_invalid", role)
                if sha256(archive.read(name)) != expected:
                    raise PreparationError("source_archive_member_hash_mismatch", role)
    except (OSError, zipfile.BadZipFile, KeyError):
        raise PreparationError("source_archive_invalid", role) from None
    return {"file_count": expected_count, "source_identity": expected_identity,
            "archive_sha256": expected_archive_sha, "file_list_sha256": expected_list_sha}


def _verify_signed_build(raw: bytes, expected_sha: str, expected_identity: str,
                         expected_source_identity: str, role: str) -> dict[str, Any]:
    if sha256(raw) != expected_sha:
        raise PreparationError("build_record_hash_mismatch", role)
    record = strict_json(raw)
    unsigned = {key: value for key, value in record.items() if key != "identity"}
    if (record.get("kind") != "build_record" or record.get("status") != "recorded"
            or record.get("identity") != sha256(canonical(unsigned))
            or record.get("identity") != expected_identity
            or record.get("source_before") != record.get("source_after")
            or record.get("source_before", {}).get("identity") != expected_source_identity):
        raise PreparationError("build_record_invalid", role)
    return record


def _verify_curry_scope_delivery(capture: _Capture, repo: Path, profile: PreparationProfile) -> dict[str, Any]:
    root = repo / profile.baseline_root
    root_snapshot = capture.directory("latest_curry_delivery_tree", root)
    delivery_raw = capture.read("latest_curry_delivery", root / "final-build/delivery-final.json",
                                profile.curry_delivery_sha256)
    delivery = strict_json(delivery_raw)
    accounting = delivery.get("accounting", {})
    native_execution = delivery.get("native_execution", {})
    revalidation_source = profile.revalidation_source or _production_revalidation_source()
    reservation_id = revalidation_source.scope_spec.reservation_id
    reservation_policy_id = revalidation_source.scope_spec.reservation_policy_id
    if (delivery.get("kind") != "native_curry_option_revalidation_final_delivery"
            or delivery.get("status") != "passed"
            or delivery.get("scope") != "curry-option-revalidation-v1"
            or accounting != {
                "actual_all_history_cumulative": None,
                "certified_consumed_including_new": 40,
                "certified_historical_consumed_before_scope": 33,
                "new_scope_consumed": 7,
                "old_confirmation_actual_consumed": None,
                "planning_base": 40,
                "planning_total": 47,
                "policy_reserved": 7,
                "reservation_id": reservation_id,
                "reservation_policy_id": reservation_policy_id,
            }
            or native_execution.get("native_calls") != 7
            or native_execution.get("consumed") != 7
            or native_execution.get("completed") != 7
            or native_execution.get("unknown") != 0
            or len(delivery.get("stage_receipts", [])) != 7):
        raise PreparationError("latest_curry_delivery_content_invalid", "latest_curry_delivery")

    native_archive = _verify_source_archive(
        capture, root, Path("source-native.zip"), Path("source-native-file-list.json"),
        profile.native_archive_sha256, profile.native_file_list_sha256,
        profile.native_identity, 593, "8a6b2f6762131aebea6d8c0f5f61363d573f1b36", "curry_native_source",
    )
    final_archive = _verify_source_archive(
        capture, root / "final-build", Path("source-final/source-native.zip"),
        Path("source-final/source-native-file-list.json"), profile.final_archive_sha256,
        profile.final_file_list_sha256, profile.final_identity, 594,
        "8a6b2f6762131aebea6d8c0f5f61363d573f1b36", "curry_final_source",
    )
    final_source = delivery.get("final_source", {})
    if (final_source.get("workspace_identity") != profile.final_identity
            or final_source.get("file_count") != 594
            or final_source.get("changed_paths_vs_native_source") != list(profile.source_diff)
            or final_source.get("source_archive_sha256") != profile.final_archive_sha256
            or final_source.get("source_file_list_sha256") != profile.final_file_list_sha256):
        raise PreparationError("latest_curry_source_binding_invalid", "curry_final_source")

    final_build = delivery.get("final_build", {})
    build_records = (
        ("curry_native_build", Path("build-record.json"), profile.native_build_record_sha256,
         profile.native_build_record_identity,
         profile.native_identity),
        ("curry_final_cli_worker_build", Path("final-build/build-record-cli-worker.json"),
         final_build.get("build_record_cli_worker", {}).get("sha256"),
         final_build.get("build_record_cli_worker", {}).get("identity"), profile.final_identity),
        ("curry_final_runner_build", Path("final-build/build-record-runner.json"),
         final_build.get("build_record_runner", {}).get("sha256"),
         final_build.get("build_record_runner", {}).get("identity"), profile.final_identity),
    )
    for role, relative, expected_sha, expected_identity, expected_source in build_records:
        if not isinstance(expected_sha, str) or not isinstance(expected_identity, str):
            raise PreparationError("delivery_build_binding_missing", role)
        raw = capture.read(role, root / relative, expected_sha)
        record = _verify_signed_build(raw, expected_sha, expected_identity, expected_source, role)
        if record.get("source_before", {}).get("identity") != expected_source:
            raise PreparationError("build_source_identity_mismatch", role)

    artifact_specs = final_build.get("artifacts", {})
    if set(artifact_specs) != {"runner", "cli", "worker"}:
        raise PreparationError("delivery_artifact_binding_invalid", "final_build")
    artifact_names = {"runner": "curry-option-revalidation.exe", "cli": "ygo-cli.exe",
                      "worker": "ygo-engine-worker.exe"}
    for artifact_role, metadata in artifact_specs.items():
        relative = Path(metadata.get("path", ""))
        expected = metadata.get("sha256")
        if (relative != Path("artifacts") / artifact_names[artifact_role]
                or type(metadata.get("bytes")) is not int or not isinstance(expected, str)):
            raise PreparationError("delivery_artifact_binding_invalid", artifact_role)
        artifact = capture.read(f"curry_artifact_{artifact_role}", root / "final-build" / relative, expected)
        if len(artifact) != metadata["bytes"]:
            raise PreparationError("delivery_artifact_length_invalid", artifact_role)

    research = root / "research"
    summary_raw = capture.read("latest_curry_summary", research / "summary.json", profile.summary_sha256)
    summary = strict_json(summary_raw)
    if (summary.get("kind") != "native_curry_option_revalidation_summary"
            or summary.get("scope") != "curry-option-revalidation-v1"
            or summary.get("successful") is not True
            or summary.get("new_consumed") != 7
            or summary.get("ledger", {}).get("completed") != 7
            or summary.get("ledger", {}).get("unknown") != 0
            or len(summary.get("stages", [])) != 7):
        raise PreparationError("latest_curry_summary_invalid", "latest_curry_summary")

    for item in delivery["stage_receipts"]:
        stage = item.get("stage")
        if type(stage) is not int or not 1 <= stage <= 7 or item.get("successful") is not True:
            raise PreparationError("latest_curry_stage_binding_invalid", "stage_receipt")
        raw = capture.read(f"latest_curry_stage_{stage}_receipt", research / f"stage-{stage}.json",
                           item.get("receipt_sha256"))
        receipt = strict_json(raw)
        if (receipt.get("stage") != stage or receipt.get("successful") is not True
                or receipt.get("scope") != "curry-option-revalidation-v1"):
            raise PreparationError("latest_curry_stage_receipt_invalid", f"stage_{stage}")
        for sidecar_role, filename, digest_value in (
            ("stage_report", f"stage-{stage}-report.json", None),
            ("stage_request", f"stage-{stage}-request.json", None),
            ("stage_input", f"stage-{stage}-input.json", None),
            ("stage_seal", f"stage-{stage}-input-seal.json", None),
        ):
            capture.read(f"latest_curry_{sidecar_role}_{stage}", research / filename)

    ledger_meta = delivery.get("original_call_journal", {})
    ledger_path = research / "calls.jsonl"
    ledger_raw = capture.read("latest_curry_ledger", ledger_path, profile.ledger_sha256)
    if (ledger_meta.get("path") != "../research/calls.jsonl"
            or ledger_meta.get("sha256") != profile.ledger_sha256
            or ledger_meta.get("records") != 37 or ledger_meta.get("bytes") != len(ledger_raw)
            or ledger_meta.get("record_kinds") != {"begin": 7, "checkpoint": 22, "complete": 7, "header": 1}):
        raise PreparationError("latest_curry_ledger_summary_invalid", "latest_curry_ledger")
    _verify_option_revalidation_ledger(capture, root, ledger_raw, summary)
    blobs_root = ledger_path.with_name(ledger_path.name + ".blobs")
    capture.directory("latest_curry_ledger_blobs_tree", blobs_root)
    if root_snapshot is None:
        raise PreparationError("latest_curry_delivery_tree_missing", "latest_curry_delivery_tree")
    return {"delivery_sha256": profile.curry_delivery_sha256,
            "native_source": native_archive, "final_source": final_archive,
            "ledger_records": 37, "scope_consumed": 7, "scope_unknown": 0,
            # These totals come from the fully matched final-delivery accounting
            # above (after the seven Curry calls), while the recursive baseline
            # verifier separately certifies the pre-scope 33/40 basis.
            "certified_consumed": accounting["certified_consumed_including_new"],
            "policy_reserved": accounting["policy_reserved"],
            "planning_total": accounting["planning_total"]}


def _verify_option_revalidation_ledger(capture: _Capture, root: Path, raw: bytes, summary: dict[str, Any]) -> None:
    from ygo_eval.native_curry_option_validation import PARENT_STAGE

    records = [strict_json(line) for line in raw.splitlines() if line]
    if len(records) != 37:
        raise PreparationError("latest_curry_ledger_record_count_invalid", "latest_curry_ledger")
    previous = ""
    kinds: Counter[str] = Counter()
    calls: dict[int, dict[str, Any]] = {}
    try:
        requested = {
            stage: strict_json(capture.role_bytes[f"latest_curry_stage_request_{stage}"])
            for stage in range(1, 8)
        }
    except KeyError:
        raise PreparationError("latest_curry_stage_request_not_captured", "latest_curry_stage_request") from None
    for sequence, record in enumerate(records):
        entry = record.get("entry")
        if (record.get("sequence") != sequence or record.get("previous") != previous
                or not isinstance(entry, dict) or record.get("hash") != sha256(
                    json.dumps([sequence, previous, entry], ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8"))):
            raise PreparationError("latest_curry_ledger_hash_chain_invalid", "latest_curry_ledger")
        previous = record["hash"]
        kind = entry.get("kind")
        kinds[kind] += 1
        if sequence == 0:
            if entry != {"kind": "header", "version": 1, "scope": "curry-option-revalidation-v1",
                         "context": summary.get("context"), "limit": 7}:
                raise PreparationError("latest_curry_ledger_header_invalid", "latest_curry_ledger")
        elif kind == "begin":
            stage = entry.get("call_id")
            if type(stage) is not int or not 1 <= stage <= 7 or stage in calls:
                raise PreparationError("latest_curry_ledger_call_invalid", "latest_curry_ledger")
            purposes = {1: "probe", 2: "probe", 3: "probe", 4: "execution", 5: "replay", 6: "execution", 7: "replay"}
            request_value = dict(requested[stage])
            request_value.pop("engine", None)
            if (entry.get("purpose") != purposes[stage]
                    or entry.get("request") != sha256(canonical(request_value))):
                raise PreparationError("latest_curry_ledger_call_binding_invalid", f"stage_{stage}")
            calls[stage] = {"begin": sequence, "entry": entry, "complete": False}
        elif kind == "complete":
            stage = entry.get("call_id")
            if stage not in calls or calls[stage]["complete"]:
                raise PreparationError("latest_curry_ledger_completion_invalid", "latest_curry_ledger")
            calls[stage]["complete"] = True
            result_hash = entry.get("result")
            result_path = root / "research/calls.jsonl.blobs/results" / f"{result_hash}.json"
            result_raw = capture.read(f"latest_curry_result_blob_{stage}", result_path, result_hash)
            result_doc = strict_json(result_raw)
            for index, event_hash in enumerate(result_doc.get("event_chunks", [])):
                event_path = root / "research/calls.jsonl.blobs/events" / f"{event_hash}.json"
                capture.read(f"latest_curry_event_blob_{stage}_{index}", event_path, event_hash)
        elif kind == "checkpoint":
            name = entry.get("name")
            blob = entry.get("blob")
            if not isinstance(name, str) or not name.startswith("immutable/curry-option-revalidation/"):
                raise PreparationError("latest_curry_ledger_checkpoint_invalid", "latest_curry_ledger")
            if not isinstance(blob, str) or not re.fullmatch(r"[a-f0-9]{64}", blob):
                raise PreparationError("latest_curry_ledger_checkpoint_blob_invalid", "latest_curry_ledger")
            path = root / "research/calls.jsonl.blobs/checkpoints" / f"{blob}.json"
            capture.read(f"latest_curry_checkpoint_blob_{sequence}", path, blob)
        else:
            raise PreparationError("latest_curry_ledger_record_unknown", "latest_curry_ledger")
    if (kinds != Counter({"header": 1, "checkpoint": 22, "begin": 7, "complete": 7})
            or set(calls) != set(range(1, 8)) or not all(item["complete"] for item in calls.values())):
        raise PreparationError("latest_curry_ledger_state_invalid", "latest_curry_ledger")


def _verify_old_prompt_preparation(capture: _Capture, repo: Path, profile: PreparationProfile) -> dict[str, Any]:
    from ygo_eval.research import validate_sources

    acceptance_path = repo / profile.acceptance_path
    report_path = repo / profile.preparation_report_path
    prepared_path = repo / profile.preparation_cases_path
    cases_path = repo / profile.frozen_cases_path
    acceptance_raw = capture.read("prompt_preparation_acceptance", acceptance_path, profile.acceptance_sha256)
    report_raw = capture.read("prompt_preparation_report", report_path, profile.preparation_report_sha256)
    prepared_raw = capture.read("prompt_prepared_cases", prepared_path, profile.preparation_cases_sha256)
    cases_raw = capture.read("frozen_rabbit_cases", cases_path, profile.frozen_cases_sha256)
    acceptance = strict_json(acceptance_raw)
    report = strict_json(report_raw)
    prepared = strict_json(prepared_raw)
    frozen = strict_json(cases_raw)

    evidence = acceptance.get("evidence")
    if (acceptance.get("schema_version") != 1 or acceptance.get("kind") != "prompt_probe_offline_delivery_acceptance"
            or acceptance.get("paused") is not True or acceptance.get("new_native_calls") != 0
            or acceptance.get("new_ffi_queries") != 0 or acceptance.get("cumulative_consumed") != 24
            or acceptance.get("unknown") != 0 or not isinstance(evidence, dict)
            or len(evidence) != 37):
        raise PreparationError("prompt_preparation_acceptance_invalid", "prompt_preparation_acceptance")
    prompt_root = repo / "data/runtime/p1-prompt-probes-offline-2026-10-21"
    capture.directory("prompt_preparation_tree", prompt_root)
    for relative, metadata in evidence.items():
        rel = Path(relative)
        if (not isinstance(relative, str) or rel.is_absolute() or ".." in rel.parts
                or "\\" in relative or not isinstance(metadata, dict)):
            raise PreparationError("prompt_preparation_evidence_path_invalid", "prompt_preparation_acceptance")
        try:
            evidence_raw = capture.read("prompt_evidence_" + re.sub(r"[^a-zA-Z0-9_]", "_", relative),
                                        prompt_root / rel, metadata.get("sha256"))
        except PreparationError:
            raise
        if len(evidence_raw) != metadata.get("bytes"):
            raise PreparationError("prompt_preparation_evidence_length_mismatch", relative.replace("/", "_"))
    if (report.get("kind") != "prompt_probe_preparation" or report.get("preparation_successful") is not True
            or report.get("native_calls") != 0 or report.get("execution_ready") is not False
            or prepared.get("kind") != "static_prompt_probe_candidates"
            or prepared.get("execution_ready") is not False or len(prepared.get("candidates", [])) != 3):
        raise PreparationError("prompt_preparation_content_invalid", "prompt_prepared_cases")
    rabbits = [item for item in frozen.get("cases", []) if item.get("case", {}).get("case_id") == "rabbit"]
    if len(rabbits) != 1:
        raise PreparationError("unique_rabbit_case_required", "frozen_rabbit_cases")
    base = rabbits[0]
    candidates = derive_candidates(base["case"])
    frozen_candidate = next((item for item in prepared["candidates"]
                             if item.get("case", {}).get("case_id") == profile.candidate_id), None)
    derived_candidate = next((item for item in candidates
                              if item.get("case", {}).get("case_id") == profile.candidate_id), None)
    if frozen_candidate is None or derived_candidate is None:
        raise PreparationError("ground_collapse_candidate_missing", "prompt_prepared_cases")
    case_hash = sha256(encode(frozen_candidate["case"]))
    base_request_hash = sha256(encode(base["request"]))
    if (case_hash != profile.collapse_case_sha256
            or frozen_candidate.get("case") != derived_candidate.get("case")
            or frozen_candidate.get("target") != {"opcode": 24, "card_id": 90502999, "name": "collapse"}
            or frozen_candidate.get("selector") != {
                "card_id": profile.candidate_card_id, "command": 5, "opcode": 11,
                "player": 0, "unique": True,
            }
            or frozen_candidate.get("expected_target") != {
                "count": 2, "mask_source": "future_raw_prompt", "opcode": 24, "player": 0,
            }
            or frozen_candidate.get("source_legality_validated") is not True
            or frozen_candidate.get("request_derivation", {}).get("base_request_sha256") != base_request_hash
            or frozen_candidate.get("status") != "static_prepared"
            or frozen_candidate.get("formal_release_status") != "unknown"
            or frozen_candidate.get("execution_ready") is not False):
        raise PreparationError("ground_collapse_candidate_binding_invalid", "prompt_prepared_cases")
    request = base["request"]
    candidate_case = derived_candidate["case"]
    candidate_request = json.loads(json.dumps(request))
    candidate_request["deck"] = candidate_case["deck"]
    candidate_request["opening_hand"] = candidate_case["opening_hand"]
    candidate_request["seed"] = candidate_case["seed"]
    candidate_request["decisions"] = []
    validate_sources(candidate_case, candidate_request, Path(base["banlist_path"]))
    if (candidate_case["seed"] != 1 or [len(candidate_case["deck"][key]) for key in ("main", "extra", "side")] != [40, 3, 0]
            or candidate_case["deck"]["main"].count(90502999) != 1
            or candidate_case["opening_hand"].count(90502999) != 1
            or candidate_case["information"]["opponent_resources"] != {"main": candidate_case["deck"]["main"], "hand": []}):
        raise PreparationError("ground_collapse_candidate_semantics_invalid", "prompt_prepared_cases")
    return {"case": candidate_case, "request": candidate_request, "case_sha256": case_hash,
            "base_request_sha256": base_request_hash, "candidate_id": profile.candidate_id,
            "candidate_card_id": profile.candidate_card_id,
            "banlist_path": Path(base["banlist_path"]),
            "main_extra_side_counts": [40, 3, 0], "opening_hand_count": 5,
            "seed": 1, "opponent_resources_synced": True, "formal_release_status": "unknown"}


def _verify_runtime_and_core(
    capture: _Capture, candidate: dict[str, Any], core_source: Path,
    profile: PreparationProfile,
) -> dict[str, Any]:
    from ygo_eval.research import validate_sources

    request = candidate["request"]
    case = candidate["case"]
    engine = request["engine"]
    for key, role in (("ocgcore_path", "runtime_dll"), ("catalog_path", "runtime_cdb"),
                      ("script_manifest_path", "runtime_script_manifest"),
                      ("engine_manifest_path", "runtime_engine_manifest")):
        capture.read(role, Path(engine[key]))
    banlist = Path(candidate["banlist_path"])
    capture.read("runtime_banlist", banlist, case["rules"]["banlist_sha256"])
    validate_sources(case, request, banlist)

    manifest_path = Path(engine["script_manifest_path"])
    manifest = strict_json(capture.read("runtime_script_manifest_reparsed", manifest_path))
    scripts_root = Path(engine["scripts_path"])
    capture.directory("runtime_scripts_tree", scripts_root)
    for name, expected in profile.script_manifest_pins:
        if manifest.get(name) != expected:
            raise PreparationError("script_manifest_pin_mismatch", "script_manifest/" + name.replace("/", "_"))
    script_text = capture.read("ground_collapse_script", scripts_root / "official/c90502999.lua",
                               dict(profile.target_script_pins)["official/c90502999.lua"])
    if b"Duel.SelectDisableField" not in script_text or b"Duel.Hint(HINT_ZONE" not in script_text:
        raise PreparationError("ground_collapse_script_semantics_mismatch", "script/official/c90502999.lua")

    core_source = Path(os.path.abspath(core_source))
    capture.directory("frozen_core_tree", core_source)
    core_bytes: dict[str, bytes] = {}
    for name, expected in profile.core_pins:
        core_bytes[name] = capture.read("core/" + name, core_source / name, expected)
    if (b"SelectDisableField" not in core_bytes["libduel.cpp"]
            or b"MSG_FIELD_DISABLED" not in core_bytes["processor.cpp"]
            or b"HINT_ZONE" not in core_bytes["ocgapi_constants.h"]
            or b"MSG_SELECT_PLACE" not in core_bytes["ocgapi_constants.h"]):
        raise PreparationError("frozen_core_semantics_mismatch", "core/source")
    catalog = Path(engine["catalog_path"])
    try:
        with closing(sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT alias,type,ot FROM datas WHERE id=?", (profile.candidate_card_id,)).fetchone()
    except (OSError, sqlite3.Error):
        raise PreparationError("candidate_cdb_read_failed", "runtime_cdb") from None
    if row is None or not (row[2] & 1):
        raise PreparationError("candidate_cdb_card_unavailable", "runtime_cdb")
    return {"script_sha256": dict(profile.target_script_pins)["official/c90502999.lua"],
            "script_static_api": ["Duel.SelectDisableField", "Duel.Hint(HINT_ZONE,tp,dis)"],
            "core_files": {name: digest for name, digest in profile.core_pins},
            "core_semantics": {"SelectDisableField": True, "MSG_FIELD_DISABLED": True,
                               "HINT_ZONE": True, "MSG_SELECT_PLACE": True},
            "candidate_catalog": {"card_id": profile.candidate_card_id, "alias": row[0],
                                  "type": row[1], "ot": row[2],
                                  "banlist_and_alias_limits_validated": True,
                                  "formal_release_status": "unknown"}}


def _synthetic_protocol_vectors() -> dict[str, Any]:
    raw18 = bytes([18, 0, 1, 255, 224, 255, 255])
    mask18 = int.from_bytes(raw18[3:7], "little")
    zones18 = [
        {"player": player, "location": location, "sequence": sequence}
        for player in range(2) for location in (4, 8)
        for sequence in range(7 if location == 4 else 8)
        if not mask18 & (1 << (sequence + (8 if location == 8 else 0) + player * 16))
    ]
    actions18 = [{"choice": {"kind": "place", "zones": [zone]}, "card_ids": [],
                  "bytes": [zone["player"], zone["location"], zone["sequence"]]}
                 for zone in zones18]
    prompt18 = {"opcode": 18, "player": 0, "actions": actions18}
    audit18 = audit_opcode18_fixed_zone_selection(
        raw18, prompt18, {"player": 0, "location": 8, "sequence": 0}, [0, 8, 0],
    )

    raw24 = bytes([24, 0, 2, 224, 255, 224, 255])
    mask24 = parse_opcode24(raw24)["disabled_mask"]
    actions24 = []
    for pair in canonical_zone_pairs(mask24):
        actions24.append({"choice": {"kind": "place", "zones": pair}, "card_ids": [],
                         "bytes": zone_response_bytes(pair)})
    prompt24 = {"opcode": 24, "player": 0, "actions": actions24}
    selected = [
        {"player": 1, "location": 4, "sequence": 0},
        {"player": 1, "location": 4, "sequence": 1},
    ]
    hint = bytes([2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0])
    disabled = bytes([56, 0, 0, 3, 0])
    audit24 = audit_ground_collapse_fixed_selection(
        raw24, prompt24, selected, [1, 4, 0, 1, 4, 1], hint, disabled,
    )
    return {
        "classification": "synthetic_only",
        "opcode18": {"raw_hex": raw18.hex(), "mask": mask18, "actions": len(actions18),
                     "audit": audit18},
        "opcode24": {"raw_hex": raw24.hex(), "disabled_mask": mask24,
                     "canonical_pairs": len(actions24), "ordered_encodings": len(actions24) * 2,
                     "selected_zones": selected, "response_bytes": [1, 4, 0, 1, 4, 1],
                     "hint_zone_hex": hint.hex(), "hint_value": parse_hint_zone(hint)["value"],
                     "field_disabled_hex": disabled.hex(), "field_disabled_mask": parse_field_disabled(disabled),
                     "audit": audit24},
        "synthetic_expected": {
            "opcode24_raw": [24, 0, 2, 224, 255, 224, 255],
            "synthetic_disabled_mask": 0xFFE0FFE0,
            "canonical_pairs": 45,
            "ordered_encodings": 90,
            "response_bytes": [1, 4, 0, 1, 4, 1],
            "hint_zone": [2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            "field_disabled": [56, 0, 0, 3, 0],
            "selected_mask": 0x00030000,
        },
        "native_observation": {
            "actual_opcode18_raw_frame": None,
            "actual_opcode24_raw_frame": None,
            "actual_disabled_mask": None,
            "actual_prompt_ids": None,
            "actual_followup_sequence": None,
            "native_reachability_verified": False,
            "native_response_acceptance_verified": False,
            "reverse_order_acceptance_verified": False,
        },
    }


def _check_tool_bundle(
    repo: Path, profile: PreparationProfile, *,
    source_collector: Callable[[Path], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], bytes, bytes]:
    files: dict[str, str] = {}
    contents: dict[str, bytes] = {}
    for name in profile.tool_files:
        try:
            path = safe_path(repo / name)
            raw = path.read_bytes()
        except (OSError, ValueError):
            raise PreparationError("tool_source_unavailable", name.replace("/", "_")) from None
        files[name] = sha256(raw)
        contents[name] = raw
    workspace = (source_collector or source_identity)(repo)
    listing = {
        "schema_version": 1,
        "kind": "ground_collapse_preparation_tool_file_list",
        "files": files,
        "file_count": len(files),
        "workspace_identity": workspace["identity"],
        "workspace_file_count": len(workspace["files"]),
    }
    list_raw = encode(listing)
    import io
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in profile.tool_files:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, contents[name])
    return listing, list_raw, stream.getvalue()


def _verify_saved_tool_bundle(output: Path, report: dict[str, Any], profile: PreparationProfile) -> dict[str, Any]:
    list_path = safe_path(output / "source-native-file-list.json")
    archive_path = safe_path(output / "source-native.zip")
    listing_raw = list_path.read_bytes()
    archive_raw = archive_path.read_bytes()
    listing = strict_json(listing_raw)
    bundle = report.get("tool_bundle")
    if (not isinstance(bundle, dict) or sha256(listing_raw) != bundle.get("file_list_sha256")
            or sha256(archive_raw) != bundle.get("archive_sha256")
            or type(listing.get("schema_version")) is not int or listing.get("schema_version") != 1
            or listing.get("kind") != "ground_collapse_preparation_tool_file_list"
            or type(listing.get("file_count")) is not int
            or listing.get("file_count") != len(profile.tool_files)
            or bundle.get("file_count") != listing.get("file_count")
            or listing.get("workspace_identity") != bundle.get("source_identity")
            or type(listing.get("workspace_file_count")) is not int
            or listing.get("workspace_file_count") != report.get("tool_identity", {}).get("workspace_file_count")
            or set(listing.get("files", {})) != set(profile.tool_files)):
        raise PreparationError("saved_tool_bundle_binding_invalid", "tool_bundle")
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(archive_raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise PreparationError("saved_tool_bundle_duplicate_member", "tool_bundle")
        if set(names) != set(listing["files"]):
            raise PreparationError("saved_tool_bundle_membership_invalid", "tool_bundle")
        for name, expected in listing["files"].items():
            if sha256(archive.read(name)) != expected:
                raise PreparationError("saved_tool_bundle_member_invalid", name.replace("/", "_"))
    return listing


_SUCCESS_CHECKS = (
    ("latest_curry_delivery", "latest_curry_delivery"),
    ("historical_sources", "historical_sources"),
    ("frozen_candidate", "prompt_prepared_cases"),
    ("runtime_assets_and_core", "core/source"),
    ("input_stability", "all_inputs"),
    ("tool_source_stability", "tool_source"),
)


def _required_success_input_roles() -> frozenset[str]:
    required = {
        "latest_curry_delivery", "latest_curry_summary", "latest_curry_ledger",
        "curry_native_source_file_list", "curry_native_source_archive",
        "curry_final_source_file_list", "curry_final_source_archive",
        "curry_native_build", "curry_final_cli_worker_build", "curry_final_runner_build",
        "curry_artifact_runner", "curry_artifact_cli", "curry_artifact_worker",
        "prompt_preparation_acceptance", "prompt_preparation_report",
        "prompt_prepared_cases", "frozen_rabbit_cases",
        "runtime_dll", "runtime_cdb", "runtime_script_manifest",
        "runtime_engine_manifest", "runtime_banlist", "runtime_script_manifest_reparsed",
        "ground_collapse_script",
        *(f"core/{name}" for name in (
            "libduel.cpp", "processor.cpp", "ocgapi_constants.h",
            "effect_constants.h", "playerop.cpp", "field.cpp",
        )),
    }
    for stage in range(1, 8):
        required.update({
            f"latest_curry_stage_{stage}_receipt",
            f"latest_curry_stage_report_{stage}",
            f"latest_curry_stage_request_{stage}",
            f"latest_curry_stage_input_{stage}",
            f"latest_curry_stage_seal_{stage}",
            f"latest_curry_result_blob_{stage}",
        })
    return frozenset(required)


def _validate_success_sources(value: Any, profile: PreparationProfile) -> None:
    if not isinstance(value, dict) or set(value) != {
        "latest_curry", "historical_certified_consumed", "historical_policy_reserved",
        "historical_planning_base", "historical_protection", "script", "core",
    }:
        raise PreparationError("report_success_sources_invalid")
    latest = value["latest_curry"]
    if not isinstance(latest, dict) or set(latest) != {
        "delivery_sha256", "native_source", "final_source", "ledger_records",
        "scope_consumed", "scope_unknown", "certified_consumed",
        "policy_reserved", "planning_total",
    }:
        raise PreparationError("report_latest_curry_source_invalid")
    if (latest["delivery_sha256"] != profile.curry_delivery_sha256
            or any(type(latest[key]) is not int for key in (
                "ledger_records", "scope_consumed", "scope_unknown",
                "certified_consumed", "policy_reserved", "planning_total"))
            or latest["ledger_records"] != 37 or latest["scope_consumed"] != 7
            or latest["scope_unknown"] != 0
            or latest["certified_consumed"] != profile.prior_certified_consumed
            or latest["policy_reserved"] != profile.policy_reserved
            or latest["planning_total"] != profile.planning_total):
        raise PreparationError("report_latest_curry_source_invalid")
    for key, count, identity, archive_sha, list_sha in (
        ("native_source", 593, profile.native_identity, profile.native_archive_sha256,
         profile.native_file_list_sha256),
        ("final_source", 594, profile.final_identity, profile.final_archive_sha256,
         profile.final_file_list_sha256),
    ):
        source = latest[key]
        if (not isinstance(source, dict)
                or set(source) != {"file_count", "source_identity", "archive_sha256", "file_list_sha256"}
                or type(source.get("file_count")) is not int
                or source.get("file_count") != count
                or source.get("source_identity") != identity
                or source.get("archive_sha256") != archive_sha
                or source.get("file_list_sha256") != list_sha):
            raise PreparationError("report_latest_curry_source_invalid")
    if (type(value["historical_certified_consumed"]) is not int
            or value["historical_certified_consumed"] != profile.prior_certified_consumed
            or type(value["historical_policy_reserved"]) is not int
            or value["historical_policy_reserved"] != profile.policy_reserved
            or type(value["historical_planning_base"]) is not int
            or value["historical_planning_base"] != profile.planning_total):
        raise PreparationError("report_historical_accounting_invalid")
    protection = value["historical_protection"]
    if (not isinstance(protection, dict) or set(protection) != {"entry_count", "mapping_sha256"}
            or type(protection.get("entry_count")) is not int or protection["entry_count"] < 1
            or not _is_sha256(protection.get("mapping_sha256"))):
        raise PreparationError("report_historical_protection_invalid")
    script = value["script"]
    if (not isinstance(script, dict) or set(script) != {"sha256", "static_api"}
            or script.get("sha256") != dict(profile.target_script_pins)["official/c90502999.lua"]
            or not _strict_json_equal(
                script.get("static_api"),
                ["Duel.SelectDisableField", "Duel.Hint(HINT_ZONE,tp,dis)"],
            )):
        raise PreparationError("report_script_source_invalid")
    core = value["core"]
    expected_core_semantics = {
        "SelectDisableField": True, "MSG_FIELD_DISABLED": True,
        "HINT_ZONE": True, "MSG_SELECT_PLACE": True,
    }
    if (not isinstance(core, dict) or set(core) != {"files", "semantics"}
            or not _strict_json_equal(core.get("files"), dict(profile.core_pins))
            or not _strict_json_equal(core.get("semantics"), expected_core_semantics)):
        raise PreparationError("report_core_source_invalid")


def _validate_success_evidence(report: dict[str, Any], profile: PreparationProfile) -> None:
    checks = report.get("checks")
    expected_checks = [
        {"checkpoint": checkpoint, "status": "passed", "code": None, "role": role}
        for checkpoint, role in _SUCCESS_CHECKS
    ]
    if checks != expected_checks:
        raise PreparationError("report_success_checks_invalid")

    inputs = report.get("input_sha256")
    required = _required_success_input_roles()
    if (not isinstance(inputs, dict) or not required <= set(inputs)
            or any(not isinstance(role, str) or not role or not _is_sha256(digest)
                   for role, digest in inputs.items())):
        raise PreparationError("report_success_inputs_invalid")
    checkpoint_roles = [role for role in inputs if role.startswith("latest_curry_checkpoint_blob_")]
    if len(checkpoint_roles) != 22:
        raise PreparationError("report_checkpoint_input_roles_invalid")

    directories = report.get("input_directories")
    required_directories = {
        "latest_curry_delivery_tree", "latest_curry_ledger_blobs_tree",
        "prompt_preparation_tree", "runtime_scripts_tree", "frozen_core_tree",
    }
    if (not isinstance(directories, dict) or set(directories) != required_directories
            or any(not isinstance(item, dict) or set(item) != {"sha256", "entry_count"}
                   or not _is_sha256(item.get("sha256"))
                   or type(item.get("entry_count")) is not int or item["entry_count"] < 0
                   for item in directories.values())):
        raise PreparationError("report_success_directories_invalid")
    _validate_success_sources(report.get("sources"), profile)


def validate_report(
    report: dict[str, Any], *, schema: dict[str, Any] | None = None,
    profile: PreparationProfile = PRODUCTION_PROFILE,
) -> None:
    required = {
        "schema_version", "kind", "status", "preparation_successful", "source_unchanged",
        "native_calls", "runner_process_calls", "worker_calls", "ffi_calls", "execution_ready",
        "candidate", "selection_rules", "protocol_vectors", "input_sha256", "input_directories",
        "tool_bundle", "tool_identity", "sources", "checks", "diagnostics", "accounting",
        "native_reachability_verified", "response_acceptance_verified", "proof_ready",
        "complete_action_coverage", "global_optimality", "native_probability_verified",
        "future_native_binding",
    }
    if not isinstance(report, dict) or set(report) != required:
        raise PreparationError("report_fields_invalid")
    bundle = report.get("tool_bundle")
    tool_identity = report.get("tool_identity")
    if (not isinstance(bundle, dict) or set(bundle) != {
                "file_count", "archive_sha256", "file_list_sha256", "source_identity"}
            or type(bundle.get("file_count")) is not int
            or bundle["file_count"] != len(profile.tool_files)
            or not _is_sha256(bundle.get("archive_sha256"))
            or not _is_sha256(bundle.get("file_list_sha256"))
            or not isinstance(tool_identity, dict)
            or bundle.get("source_identity") != tool_identity.get("workspace_identity")):
        raise PreparationError("report_tool_identity_binding_invalid")
    if (set(tool_identity) != {"algorithm", "workspace_identity", "workspace_file_count", "workspace_identity_status"}
            or tool_identity.get("algorithm") != "ground-collapse-preparation-tool-bundle-v1"
            or not _is_sha256(tool_identity.get("workspace_identity"))
            or type(tool_identity.get("workspace_file_count")) is not int
            or tool_identity["workspace_file_count"] < 0
            or tool_identity.get("workspace_identity_status") != "historical_capture_metadata_not_reauthenticated"):
        raise PreparationError("report_tool_identity_binding_invalid")
    if not _strict_json_equal(report.get("future_native_binding"), EMPTY_FUTURE_NATIVE_BINDING):
        raise PreparationError("future_native_binding_invalid")
    if not _strict_json_equal(report.get("selection_rules"), _fixed_selection_rules()):
        raise PreparationError("selection_rules_invalid")
    if type(report.get("status")) is not str or report.get("status") not in {"passed", "failed"}:
        raise PreparationError("report_status_invalid")
    passed = report.get("status") == "passed"
    if (type(report.get("schema_version")) is not int or report.get("schema_version") != 1
            or report.get("kind") != "ground_collapse_preparation_v1"
            or report.get("preparation_successful") is not passed
            or type(report.get("native_calls")) is not int or report["native_calls"] != 0
            or type(report.get("runner_process_calls")) is not int or report["runner_process_calls"] != 0
            or type(report.get("worker_calls")) is not int or report["worker_calls"] != 0
            or type(report.get("ffi_calls")) is not int or report["ffi_calls"] != 0
            or report.get("execution_ready") is not False
            or any(report.get(key) is not False for key in (
                "native_reachability_verified", "response_acceptance_verified", *QUALIFICATIONS))):
        raise PreparationError("report_qualification_invalid")
    if not isinstance(report.get("accounting"), dict):
        raise PreparationError("report_accounting_invalid")
    if passed:
        _validate_success_evidence(report, profile)
        candidate = report.get("candidate")
        if (report.get("source_unchanged") is not True or report.get("diagnostics") != []
                or not isinstance(candidate, dict)
                or set(candidate) != {
                    "case_id", "card_id", "case_sha256", "base_request_sha256",
                    "main_extra_side_counts", "opening_hand_count", "seed",
                    "opponent_resources_synced", "formal_release_status",
                    "source_legality_validated", "catalog",
                }
                or candidate.get("case_id") != "prompt-24-collapse-v1"
                or type(candidate.get("card_id")) is not int
                or candidate.get("card_id") != 90502999
                or not _strict_json_equal(candidate.get("main_extra_side_counts"), [40, 3, 0])
                or type(candidate.get("opening_hand_count")) is not int
                or candidate.get("opening_hand_count") != 5
                or type(candidate.get("seed")) is not int
                or candidate.get("seed") != 1
                or candidate.get("opponent_resources_synced") is not True
                or candidate.get("formal_release_status") != "unknown"
                or candidate.get("source_legality_validated") is not True
            or not isinstance(candidate.get("catalog"), dict)
            or set(candidate.get("catalog", {})) != {
                "card_id", "alias", "type", "ot", "banlist_and_alias_limits_validated",
                "formal_release_status",
            }
            or type(candidate["catalog"].get("card_id")) is not int
            or candidate["catalog"].get("card_id") != profile.candidate_card_id
            or type(candidate["catalog"].get("alias")) is not int
            or type(candidate["catalog"].get("type")) is not int
            or type(candidate["catalog"].get("ot")) is not int
            or candidate["catalog"].get("banlist_and_alias_limits_validated") is not True
            or candidate["catalog"].get("formal_release_status") != "unknown"
                or not _is_sha256(candidate.get("case_sha256"))
                or not _is_sha256(candidate.get("base_request_sha256"))
                or not _strict_json_equal(report.get("protocol_vectors"), _synthetic_protocol_vectors())
                or not _strict_json_equal(report.get("accounting"), {
                "certified_consumed": profile.prior_certified_consumed,
                "policy_reserved": profile.policy_reserved,
                "planning_total": profile.planning_total,
                    "old_confirmation_actual_consumed": None, "actual_all_history_cumulative": None,
                })):
            raise PreparationError("report_success_binding_invalid")
    else:
        if not isinstance(report.get("diagnostics"), list) or not 1 <= len(report["diagnostics"]) <= 2:
            raise PreparationError("report_failure_diagnostic_invalid")
        if any(report["accounting"].get(key) is not None
               for key in ("certified_consumed", "policy_reserved", "planning_total")):
            raise PreparationError("report_failure_accounting_invalid")
    if schema is not None:
        try:
            import jsonschema
            jsonschema.Draft202012Validator(schema).validate(report)
        except ImportError:
            # Publishing or verifying a report without its pinned schema
            # validator would silently weaken the v1 contract. Fail closed.
            raise PreparationError("report_schema_validator_unavailable") from None
        except Exception as error:
            raise PreparationError("report_schema_invalid") from error


def _report_base(profile: PreparationProfile, tool_bundle: dict[str, Any], capture: _Capture,
                 workspace: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "ground_collapse_preparation_v1",
        "status": "failed",
        "preparation_successful": False,
        "source_unchanged": False,
        "native_calls": 0,
        "runner_process_calls": 0,
        "worker_calls": 0,
        "ffi_calls": 0,
        "execution_ready": False,
        "future_native_binding": dict(EMPTY_FUTURE_NATIVE_BINDING),
        "candidate": None,
        "selection_rules": _fixed_selection_rules(),
        "protocol_vectors": {},
        "input_sha256": dict(sorted(capture.role_hashes.items())),
        "input_directories": {
            name: {"sha256": item["sha256"], "entry_count": item["entry_count"]}
            for name, item in sorted(capture.directories.items())
        },
        "tool_bundle": tool_bundle,
        "tool_identity": {"algorithm": "ground-collapse-preparation-tool-bundle-v1",
                          "workspace_identity": workspace.get("identity"),
                          "workspace_file_count": len(workspace.get("files", {})),
                          "workspace_identity_status": "historical_capture_metadata_not_reauthenticated"},
        "sources": None,
        "checks": [],
        "diagnostics": [],
        "accounting": {"certified_consumed": None, "policy_reserved": None,
                       "planning_total": None, "old_confirmation_actual_consumed": None,
                       "actual_all_history_cumulative": None},
        "native_reachability_verified": False,
        "response_acceptance_verified": False,
        **QUALIFICATIONS,
    }


def _check(capture: _Capture, checks: list[dict[str, Any]], checkpoint: str, fn: Callable[[], Any], role: str | None = None):
    try:
        value = fn()
    except PreparationError as error:
        checks.append({"checkpoint": checkpoint, "status": "failed", "code": error.code,
                       "role": error.role or role})
        raise
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        code = "source_check_failed"
        checks.append({"checkpoint": checkpoint, "status": "failed", "code": code, "role": role})
        raise PreparationError(code, role) from None
    checks.append({"checkpoint": checkpoint, "status": "passed", "code": None, "role": role})
    return value


def _capture_stability(capture: _Capture, repo: Path, source_before: dict[str, Any],
                       source_collector: Callable[[Path], dict[str, Any]], *,
                       protected_hasher: Callable[[Path], str] | None = None) -> None:
    try:
        if source_collector(repo) != source_before:
            raise PreparationError("tool_source_changed_during_preparation", "tool_source")
        for path, expected in capture.files.items():
            if sha256(safe_path(path).read_bytes()) != expected:
                raise PreparationError("input_changed_during_preparation", "captured_input")
        for role, item in capture.directories.items():
            if _directory_snapshot(item["_path"]) != item["_entries"]:
                raise PreparationError("source_directory_changed", role)
        if capture.protected:
            from ygo_eval.native_curry_option_validation import _option_revalidation_protected_hash
            for path, expected in capture.protected.items():
                found = (protected_hasher or (lambda item: _option_revalidation_protected_hash(item, repo)))(path)
                if found != expected:
                    raise PreparationError("historical_protected_input_changed", "historical_materials")
    except PreparationError:
        raise
    except (OSError, ValueError):
        raise PreparationError("input_changed_during_preparation") from None


def _run_sources(repo: Path, args: argparse.Namespace, profile: PreparationProfile,
                 *, source_collector: Callable[[Path], dict[str, Any]]) -> tuple[dict[str, Any], _Capture]:
    from ygo_eval.native_curry_option_validation import (
        _option_revalidation_protected_hash, _verify_option_revalidation_baseline,
    )
    revalidation_source = profile.revalidation_source or _production_revalidation_source()
    source_before = source_collector(repo)
    listing, list_raw, archive_raw = _check_tool_bundle_without_output(
        repo, profile, source_collector=source_collector,
    )
    bundle = {"file_count": listing["file_count"], "archive_sha256": sha256(archive_raw),
              "file_list_sha256": sha256(list_raw), "source_identity": listing["workspace_identity"]}
    capture = _Capture()
    checks: list[dict[str, Any]] = []
    workspace = source_collector(repo)
    if workspace != source_before:
        raise PreparationError("tool_source_changed_during_preparation", "tool_source")
    report = _report_base(profile, bundle, capture, workspace)

    try:
        latest = _check(capture, checks, "latest_curry_delivery", lambda:
                        _verify_curry_scope_delivery(capture, repo, profile), "latest_curry_delivery")
        _baseline_info, protected = _check(
            capture, checks, "historical_sources", lambda:
            _verify_option_revalidation_baseline(
                repo, repo / revalidation_source.scope_spec.baseline_root,
                source_collector=source_collector,
                _source_description=revalidation_source,
            ),
            "historical_sources",
        )
        # Carry the independently returned historical map into the final stability
        # pass. Hashing is read-only; the helper itself never opens a writable journal.
        capture.protected = protected
        candidate = _check(capture, checks, "frozen_candidate", lambda:
                           _verify_old_prompt_preparation(capture, repo, profile),
                           "prompt_prepared_cases")
        runtime = _check(capture, checks, "runtime_assets_and_core", lambda:
                         _verify_runtime_and_core(capture, candidate, args.core_source, profile),
                         "core/source")
        report["candidate"] = {
            "case_id": candidate["candidate_id"], "card_id": candidate["candidate_card_id"],
            "case_sha256": candidate["case_sha256"], "base_request_sha256": candidate["base_request_sha256"],
            "main_extra_side_counts": candidate["main_extra_side_counts"],
            "opening_hand_count": candidate["opening_hand_count"], "seed": candidate["seed"],
            "opponent_resources_synced": candidate["opponent_resources_synced"],
            "formal_release_status": candidate["formal_release_status"],
            "source_legality_validated": True,
            "catalog": runtime["candidate_catalog"],
        }
        report["protocol_vectors"] = _synthetic_protocol_vectors()
        report["sources"] = {
            "latest_curry": latest,
            "historical_certified_consumed": latest["certified_consumed"],
            "historical_policy_reserved": latest["policy_reserved"],
            "historical_planning_base": latest["planning_total"],
            "historical_protection": {
                "entry_count": len(protected),
                "mapping_sha256": sha256(encode(sorted((str(path), value) for path, value in protected.items()))),
            },
            "script": {"sha256": runtime["script_sha256"], "static_api": runtime["script_static_api"]},
            "core": {"files": runtime["core_files"], "semantics": runtime["core_semantics"]},
        }
        report["checks"] = checks
        _check(capture, checks, "input_stability", lambda:
               _capture_stability(
                   capture, repo, source_before, source_collector,
                   protected_hasher=lambda path: _option_revalidation_protected_hash(
                       path, repo, _source_description=revalidation_source,
                   ),
               ), "all_inputs")
        report["checks"] = checks
        report["accounting"] = {
            "certified_consumed": profile.prior_certified_consumed,
            "policy_reserved": profile.policy_reserved,
            "planning_total": profile.planning_total,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        }
        report["source_unchanged"] = True
        report["status"] = "passed"
        report["preparation_successful"] = True
        return report, capture
    except PreparationError as error:
        if not checks or checks[-1].get("status") != "failed":
            checks.append({"checkpoint": "preparation", "status": "failed",
                           "code": error.code, "role": error.role})
        report["checks"] = checks
        report["diagnostics"] = [{"checkpoint": checks[-1]["checkpoint"],
                                   "code": error.code, "role": error.role}]
        try:
            _capture_stability(
                capture, repo, source_before, source_collector,
                protected_hasher=lambda path: _option_revalidation_protected_hash(
                    path, repo, _source_description=revalidation_source,
                ),
            )
            report["source_unchanged"] = True
        except PreparationError as stability_error:
            report["source_unchanged"] = False
            report["diagnostics"].append({"checkpoint": "input_stability", "code": stability_error.code,
                                          "role": stability_error.role})
        report["input_sha256"] = dict(sorted(capture.role_hashes.items()))
        report["input_directories"] = {
            name: {"sha256": item["sha256"], "entry_count": item["entry_count"]}
            for name, item in sorted(capture.directories.items()) if "sha256" in item
        }
        report["checks"] = checks
        return report, capture


def _check_tool_bundle_without_output(
    repo: Path, profile: PreparationProfile, *,
    source_collector: Callable[[Path], dict[str, Any]] | None = None,
):
    listing, list_raw, archive_raw = _check_tool_bundle(
        repo, profile, source_collector=source_collector,
    )
    return listing, list_raw, archive_raw


def _write_exclusive(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise PreparationError("output_already_exists", path.name) from None
    except OSError:
        raise PreparationError("output_save_failed", path.name) from None


def _load_schema(repo: Path) -> dict[str, Any]:
    path = repo / "schemas/ground-collapse-preparation-v1.schema.json"
    return strict_json(safe_path(path).read_bytes())


def prepare_ground_collapse_probe(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    source_collector: Callable[[Path], dict[str, Any]] | None = None,
    profile: PreparationProfile | None = None,
) -> dict[str, Any]:
    """Run fixed-source offline preparation or read-only verification."""
    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    profile = profile or _source_description()
    collector = source_collector or stable_source
    output_argument = Path(os.path.abspath(args.output))
    expected_output = Path(os.path.abspath(repo / profile.output_root))
    expected_report = expected_output / OUTPUT_FILE
    if output_argument == expected_report:
        output = expected_output
    elif output_argument == expected_output:
        output = expected_output
    else:
        raise PreparationError("fixed_output_required", "output")
    expected_sources = (
        ("baseline_dir", repo / profile.baseline_root),
        ("preparation", repo / profile.preparation_cases_path),
        ("cases", repo / profile.frozen_cases_path),
        ("core_source", repo / profile.core_source_path),
    )
    for attr, expected in expected_sources:
        supplied = Path(os.path.abspath(getattr(args, attr)))
        if supplied != Path(os.path.abspath(expected)):
            raise PreparationError("fixed_source_path_required", attr)

    verify_only = bool(getattr(args, "verify_only", False))
    if verify_only:
        return _verify_only(args, repo, output, profile, collector)

    for ancestor in [*reversed(output.parents), output]:
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise PreparationError("linked_output_rejected", "output")
    if output.exists():
        raise PreparationError("output_already_exists", "output")
    ignored_lines = safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    if not any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime")
               for line in ignored_lines) or not output.is_relative_to(repo / "data/runtime"):
        raise PreparationError("fixed_output_must_be_ignored", "output")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError:
        error = PreparationError("output_root_create_failed", "output")
        sidecar = output.with_name(output.name + ".publication-diagnostic.json")
        try:
            _write_exclusive(sidecar, encode(_publication_diagnostic(error, checkpoint_override="output_root_creation")))
        except PreparationError:
            raise PreparationError("publication_diagnostic_save_failed", "report_publication") from None
        raise error from None
    try:
        source_before = collector(repo)
        listing, list_raw, archive_raw = _check_tool_bundle(
            repo, profile, source_collector=collector,
        )
        bundle = {"file_count": listing["file_count"], "archive_sha256": sha256(archive_raw),
                  "file_list_sha256": sha256(list_raw), "source_identity": listing["workspace_identity"]}
        _write_exclusive(output / "source-native.zip", archive_raw)
        _write_exclusive(output / "source-native-file-list.json", list_raw)

        # The pipeline owns all comparisons and validation.  This second collector
        # call is a stability anchor only; it does not spawn an engine process.
        report, capture = _run_sources(repo, args, profile, source_collector=collector)
        # The tool bundle is fixed to the same bytes captured before the source walk.
        if (sha256((output / "source-native.zip").read_bytes()) != bundle["archive_sha256"]
                or sha256((output / "source-native-file-list.json").read_bytes()) != bundle["file_list_sha256"]):
            report["status"] = "failed"
            report["preparation_successful"] = False
            report["diagnostics"] = [{"checkpoint": "tool_bundle_publication",
                                       "code": "saved_tool_bundle_changed", "role": "tool_bundle"}]
            report["accounting"] = {"certified_consumed": None, "policy_reserved": None, "planning_total": None,
                                    "old_confirmation_actual_consumed": None, "actual_all_history_cumulative": None}
        report["tool_bundle"] = bundle
        report["tool_identity"] = {"algorithm": "ground-collapse-preparation-tool-bundle-v1",
                                   "workspace_identity": listing["workspace_identity"],
                                   "workspace_file_count": listing["workspace_file_count"],
                                   "workspace_identity_status": "historical_capture_metadata_not_reauthenticated"}
        report["input_sha256"] = dict(sorted(capture.role_hashes.items()))
        report["input_directories"] = {
            name: {"sha256": item["sha256"], "entry_count": item["entry_count"]}
            for name, item in sorted(capture.directories.items()) if "sha256" in item
        }
        if report["preparation_successful"]:
            if collector(repo) != source_before:
                report["status"] = "failed"
                report["preparation_successful"] = False
                report["source_unchanged"] = False
                report["diagnostics"] = [{"checkpoint": "tool_source_stability", "code": "tool_source_changed_during_preparation", "role": "tool_source"}]
                report["accounting"] = {"certified_consumed": None, "policy_reserved": None, "planning_total": None,
                                        "old_confirmation_actual_consumed": None, "actual_all_history_cumulative": None}
            else:
                report["checks"].append({"checkpoint": "tool_source_stability", "status": "passed", "code": None, "role": "tool_source"})
        validate_report(report, schema=_load_schema(repo), profile=profile)
        _write_exclusive(output / OUTPUT_FILE, encode(report))
        return report
    except PreparationError as error:
        if not (output / PUBLICATION_DIAGNOSTIC_FILE).exists():
            _save_publication_diagnostic(output, error)
        raise
    except Exception:
        error = PreparationError("preparation_failed", "report_publication")
        if not (output / PUBLICATION_DIAGNOSTIC_FILE).exists():
            _save_publication_diagnostic(output, error)
        raise error from None


def _verify_only(args: argparse.Namespace, repo: Path, output: Path, profile: PreparationProfile,
                 collector: Callable[[Path], dict[str, Any]]) -> dict[str, Any]:
    if not output.is_dir() or output.is_symlink():
        raise PreparationError("saved_output_missing", "output")
    report_raw = safe_path(output / OUTPUT_FILE).read_bytes()
    report = strict_json(report_raw)
    validate_report(report, schema=_load_schema(repo), profile=profile)
    listing = _verify_saved_tool_bundle(output, report, profile)
    current_listing, _current_list_raw, _current_archive_raw = _check_tool_bundle(
        repo, profile, source_collector=collector,
    )
    if (current_listing.get("file_count") != listing.get("file_count")
            or current_listing.get("files") != listing.get("files")):
        raise PreparationError("saved_tool_bundle_fixed_source_mismatch", "tool_bundle")
    source_before = collector(repo)
    recomputed, capture = _run_sources(repo, args, profile, source_collector=collector)
    recomputed["input_sha256"] = dict(sorted(capture.role_hashes.items()))
    recomputed["input_directories"] = {
        name: {"sha256": item["sha256"], "entry_count": item["entry_count"]}
        for name, item in sorted(capture.directories.items()) if "sha256" in item
    }
    # The saved archive/list authenticate the historical whole-workspace capture.
    # The current bundle check above verifies every pinned tool member; later
    # documentation-only edits may change the whole-workspace identity and its
    # sidecar hash without changing the preparation tool implementation.
    recomputed["tool_bundle"] = report["tool_bundle"]
    recomputed["tool_identity"] = report["tool_identity"]
    if collector(repo) != source_before:
        raise PreparationError("verification_tool_source_changed", "tool_source")
    if recomputed.get("status") == "passed":
        recomputed["checks"].append({"checkpoint": "tool_source_stability", "status": "passed",
                                      "code": None, "role": "tool_source"})
    if (recomputed.get("status") != report.get("status")
            or recomputed.get("source_unchanged") != report.get("source_unchanged")
            or recomputed.get("candidate") != report.get("candidate")
            or recomputed.get("selection_rules") != report.get("selection_rules")
            or recomputed.get("protocol_vectors") != report.get("protocol_vectors")
            or recomputed.get("sources") != report.get("sources")
            or recomputed.get("checks") != report.get("checks")
            or recomputed.get("accounting") != report.get("accounting")
            or recomputed.get("tool_bundle") != report.get("tool_bundle")
            or recomputed.get("diagnostics") != report.get("diagnostics")
            or recomputed.get("input_sha256") != report.get("input_sha256")
            or recomputed.get("input_directories") != report.get("input_directories")):
        raise PreparationError("saved_report_source_binding_invalid", "preparation")
    return {
        "schema_version": 1,
        "kind": "ground_collapse_preparation_verification_v1",
        "valid": True,
        "preparation_successful": report["preparation_successful"],
        "native_calls": 0,
        "runner_process_calls": 0,
        "worker_calls": 0,
        "ffi_calls": 0,
        "tool_bundle_file_count": listing["file_count"],
        "source_inputs_verified": len(capture.role_hashes),
        "source_directories_verified": len(report["input_directories"]),
        "diagnostics": [],
        "qualifications": dict(QUALIFICATIONS),
    }


def _source_description() -> PreparationProfile:
    """Return production-fixed source pins; tests may replace this data factory."""
    return replace(PRODUCTION_PROFILE, revalidation_source=_production_revalidation_source())


def _production_revalidation_source() -> GroundCollapseRevalidationSource:
    from ygo_eval.curry_ledger_handoff_recovery import V3_PROFILE, V3_SPEC
    from ygo_eval.native_curry_option_validation import (
        CURRY_SCOPE, OPTION_REVALIDATION_SCOPE, OPTION_VERIFICATION_SCOPE,
    )

    return GroundCollapseRevalidationSource(
        scope_spec=OPTION_REVALIDATION_SCOPE,
        recovery_profile=V3_PROFILE,
        recovery_version_spec=V3_SPEC,
        recovery_sources=None,
        reservation_profile=None,
        reservation_spec=None,
        reservation_sources=None,
        option_verification_spec=OPTION_VERIFICATION_SCOPE,
        candidate_spec=CURRY_SCOPE,
        recovery_delivery_workspace_identity=(
            V3_PROFILE.delivery_source_after_docs_identity
        ),
        recovery_delivery_workspace_file_count=(
            V3_PROFILE.delivery_source_after_docs_file_count
        ),
    )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    for flag in ("baseline-dir", "preparation", "cases", "core-source", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
