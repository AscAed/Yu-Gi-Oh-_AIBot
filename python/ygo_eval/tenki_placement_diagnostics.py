"""Offline, read-only diagnostics for the frozen Tenki placement stage 1."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import zipfile
from datetime import datetime, timezone

from ygo_data.identity import canonical, digest, stable_source
from ygo_eval.native_tenki_placement import (
    BASELINE_RELATIVE,
    OLD_STAGE1_SHA256,
    OLD_STAGE2_REQUEST_SHA256,
    OLD_STAGE2_SHA256,
    OUTPUT_ROOT_RELATIVE,
    TRANSITION_FILE_PATH,
    _transition_payload_from_current,
    collect_baseline_bytes,
    strict_json,
)
from ygo_eval.prompt_probe_prepare import require, safe_path


DIAGNOSTICS_RELATIVE = Path("data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22")
EXPERIMENT_DELIVERY_SHA256 = "566045e6f0de3d18c33acc75caed1b5f3602e3b748b70e497a5b0d9cd5649228"
EXPERIMENT_ADDENDUM_SHA256 = "82e58d949e2276b97c9a95992585fadc57a450da7078141dc2cafb7bcd752a5c"
EXPERIMENT_DETAILS_SHA256 = "7b2baeca0ec0b01157ea4d129e7f49aa697b8108a23a7a1bd2d137cacf94818f"
NATIVE_SOURCE_ARCHIVE_SHA256 = "4ab49ab6b1fe4545681729ec1243de76151d3c1b64f15a5d3bb3b7adf2b809bb"
NATIVE_SOURCE_FILE_LIST_SHA256 = "90f6a24b9a57a5f1d61e4a0d29406653d10f9e6f3325ff51c21a0de352f10e12"
FINAL_SOURCE_ARCHIVE_SHA256 = "63f8e2126cebb5f098384ce10fa55eca4ccf781077b00afd0614c6e3db24f21c"
FINAL_SOURCE_FILE_LIST_SHA256 = "7ddd10c87af3b5f33bc41797031c0a8cf3e547a63e47e8e8f767b8b68e7d0abf"
MANIFEST_SHA256 = "623dbd1e806ffd931dba8f70f3cff2a7c2aa8e07b01902d0db43fb10592898f9"
PREPARED_SHA256 = "6b9f81dd13e19c08ad2ffd7357b535939ddeabf82f607cb818a7f5eb18107626"
STAGE1_REQUEST_SHA256 = "e6b111354986fc1e0237c7a001d0b7dc233af59e9653bfca6e0176a60767c53e"
STAGE1_INPUT_SHA256 = "61277129f00905d5a96c007a0a568e3758ce4d8f691c2b7d3eecc87fb3b8adb3"
STAGE1_SEAL_SHA256 = "e89602db2ac31228e4ca6338bbce1068a806d058e86f13548c239b9a95dc4b04"
PLACEMENT_LEDGER_SHA256 = "0c274d01a40bb1f225409346b8d2f377fe84246f5bb367672ebcf25d74760767"
PLACEMENT_SUMMARY_SHA256 = "e466dd498a7495313b790fec075d01d676368cb73a1030f0c8bbe98399c8446d"
PLACEMENT_CONTEXT = "773bafe50501dd0e093b7396d24bb2198a94503212a31d6407bdcfad8f7b1d37"
HISTORICAL_NATIVE_SOURCE = "ebd4d89356b32398a492d900ff9b604e7b03f072d5f24142300e19ba23bf2287"
HISTORICAL_NATIVE_BUILD = "383009b322790c73e51c0269c4407d9c094d3df8019fbe68f6c03de71e8df1e2"
HISTORICAL_NATIVE_RUNNER_SHA256 = "e7a71e508af12779129756b9f95e47562dde1ef8954fc17df7c4486ea70364bc"
WRONG_ARCHIVED_STAGE1_LITERAL = "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7601bbedce5ceaf76"
CORRECT_STAGE1_LITERAL = "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76"
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}


class DiagnosticPersistenceError(OSError):
    """Raised when raw process output could not be immutably preserved."""


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _output_bytes(value) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8", "surrogatepass")
    raise TypeError("subprocess output must be bytes")


def capture_process_diagnostic(
    command, cwd, evidence_root, *, mode, timeout, runner=None,
    runner_role="tenki_placement_audit_runner",
):
    """Run one process, save raw output first, then return its safe metadata."""
    allowed_modes = {
        "normal", "verify_recorded", "stats", "preflight_only",
        "audit_saved_input_only",
    }
    require(mode in allowed_modes, "process_diagnostic_mode_invalid")
    require(
        isinstance(runner_role, str)
        and re.fullmatch(r"[a-z][a-z0-9_]{1,80}", runner_role) is not None,
        "process_diagnostic_role_invalid",
    )
    runner = runner or subprocess.run
    evidence_root = Path(evidence_root).absolute()
    nonce = uuid.uuid4().hex
    relative_stem = Path("process-diagnostics") / f"{mode}-{nonce}"
    completed = None
    stdout = b""
    stderr = b""
    status = "completed"
    return_code = None
    error_code = None
    try:
        completed = runner(command, cwd=cwd, capture_output=True, timeout=timeout, check=False)
        stdout = _output_bytes(getattr(completed, "stdout", None))
        stderr = _output_bytes(getattr(completed, "stderr", None))
        return_code = getattr(completed, "returncode", None)
    except subprocess.TimeoutExpired as error:
        status = "timeout"
        error_code = "runner_timeout"
        stdout = _output_bytes(error.stdout if error.stdout is not None else error.output)
        stderr = _output_bytes(error.stderr)
    except OSError:
        status = "launch_failed"
        error_code = "runner_start_failed"
    except Exception:
        status = "launch_failed"
        error_code = "runner_launch_exception"

    stdout_path = evidence_root / relative_stem.with_suffix(".stdout.bin")
    stderr_path = evidence_root / relative_stem.with_suffix(".stderr.bin")
    metadata_path = evidence_root / relative_stem.with_suffix(".json")
    record = {
        "mode": mode,
        "runner_role": runner_role,
        "status": status,
        "return_code": return_code,
        "error_code": error_code,
        "stdout": {
            "path": stdout_path.relative_to(evidence_root).as_posix(),
            "sha256": digest(stdout),
            "bytes": len(stdout),
        },
        "stderr": {
            "path": stderr_path.relative_to(evidence_root).as_posix(),
            "sha256": digest(stderr),
            "bytes": len(stderr),
        },
        "metadata_path": metadata_path.relative_to(evidence_root).as_posix(),
    }
    try:
        _write_exclusive(stdout_path, stdout)
        _write_exclusive(stderr_path, stderr)
        _write_exclusive(metadata_path, json.dumps(record, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    except OSError as error:
        raise DiagnosticPersistenceError("process diagnostic persistence failed") from error
    return record, completed


def add_arguments(parser):
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _absolute(path) -> Path:
    return Path(os.path.abspath(path))


def _read(path: Path, expected: str | None = None) -> tuple[bytes, str]:
    path = safe_path(path)
    raw = path.read_bytes()
    found = _sha(raw)
    require(expected is None or found == expected, "pinned_diagnostic_input_mismatch")
    return raw, found


def _signed(value, kind):
    require(isinstance(value, dict) and value.get("kind") == kind, "diagnostic_record_kind_mismatch")
    unsigned = {key: item for key, item in value.items() if key != "identity"}
    require(value.get("identity") == digest(canonical(unsigned)), "diagnostic_record_identity_mismatch")


def _archive_file_count(listing: dict) -> int:
    files = listing.get("files") if isinstance(listing, dict) else None
    require(isinstance(files, dict), "source_archive_file_list_mismatch")
    if "file_count" in listing and "archived_files" in listing:
        require(listing["file_count"] == listing["archived_files"], "source_archive_file_list_mismatch")
    declared = listing.get("file_count", listing.get("archived_files"))
    require(type(declared) is int and declared == len(files), "source_archive_file_list_mismatch")
    return declared


def _verify_archive(root: Path, archive_relative: str, list_relative: str, archive_hash: str, list_hash: str, source_identity: str, file_count: int):
    archive_path = root / archive_relative
    listing_path = root / list_relative
    file_list_raw, _ = _read(listing_path, list_hash)
    archive_raw, archive_actual = _read(archive_path, archive_hash)
    listing = strict_json(file_list_raw)
    files = listing.get("files")
    listing_file_count = _archive_file_count(listing)
    require(
        listing.get("source_identity") == source_identity
        and listing_file_count == file_count
        and isinstance(files, dict)
        and len(files) == file_count,
        "source_archive_file_list_mismatch",
    )
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        require(len(members) == len(set(members)) and set(members) == set(files), "source_archive_membership_mismatch")
        for name, expected_hash in files.items():
            require(_sha(archive.read(name)) == expected_hash, "source_archive_member_hash_mismatch")
        old_rust = archive.read("crates/ygo-engine-adapter/src/tenki_placement_probe.rs").decode("utf-8")
        audit_module_path = "python/ygo_eval/native_tenki_placement.py"
        require(audit_module_path in files, "historical_audit_module_missing")
        archived_audit_tool_sha256 = _sha(archive.read(audit_module_path))
    rust_match = re.search(r'const OLD_STAGE1_SHA256: &str\s*=\s*"([^"]+)";', old_rust)
    require(rust_match is not None, "historical_archived_anchor_missing")
    return {
        "archive_sha256": archive_actual,
        "file_list_sha256": list_hash,
        "source_identity": source_identity,
        "file_count": file_count,
        "archived_rust": old_rust,
        "archived_rust_literal": rust_match.group(1),
        "archived_audit_tool_sha256": archived_audit_tool_sha256,
        "archive_bytes": len(archive_raw),
    }


def _tree_snapshot(root: Path, relative: str) -> dict[str, dict[str, int | str]]:
    base = root / relative
    require(base.is_dir(), "diagnostic_input_directory_missing")
    snapshot = {}
    for path in sorted(base.rglob("*")):
        if path.is_dir():
            safe_path(path, file=False)
            snapshot[path.relative_to(root).as_posix()] = {"kind": "directory"}
            continue
        safe_path(path)
        raw = path.read_bytes()
        snapshot[path.relative_to(root).as_posix()] = {"sha256": _sha(raw), "bytes": len(raw)}
    return snapshot


def _verify_experiment_delivery(repo: Path, experiment: Path, *, _sources=None) -> tuple[dict, dict, dict]:
    delivery_path = experiment / "final-build/delivery.json"
    delivery_expected = EXPERIMENT_DELIVERY_SHA256 if _sources is None else _sources.file_sha256(delivery_path.relative_to(repo).as_posix())
    delivery_raw, delivery_hash = _read(delivery_path, delivery_expected)
    delivery = strict_json(delivery_raw)
    addendum_path = experiment / "final-build/delivery-addendum.json"
    addendum_expected = EXPERIMENT_ADDENDUM_SHA256 if _sources is None else _sources.file_sha256(addendum_path.relative_to(repo).as_posix())
    addendum_raw, addendum_hash = _read(addendum_path, addendum_expected)
    addendum = strict_json(addendum_raw)
    details_path = experiment / "verification/test-exclusion-details.json"
    details_expected = EXPERIMENT_DETAILS_SHA256 if _sources is None else _sources.file_sha256(details_path.relative_to(repo).as_posix())
    details_raw, details_hash = _read(details_path, details_expected)
    details = strict_json(details_raw)
    result_hashes = _placement_result_hashes(repo, experiment, _sources)
    historical_consumed = (
        26 if _sources is None else _sources.dataset_count("historical_consumed")
    )
    python_skipped = 7 if _sources is None else _sources.dataset_count("placement_python_skipped")
    rust_ignored = 36 if _sources is None else _sources.dataset_count("placement_rust_ignored")
    examples_ignored = 0 if _sources is None else _sources.dataset_count("placement_examples_ignored")
    require(
        delivery.get("kind") == "tenki_placement_final_delivery"
        and delivery.get("status") == "offline_delivery_complete_native_probe_failed_before_charge"
        and delivery.get("native_result", {}).get("new_consumed") == 0
        and delivery.get("native_result", {}).get("unknown_consumption") == 0
        and delivery.get("native_result", {}).get("cumulative_consumed") == historical_consumed
        and delivery.get("native_result", {}).get("ledger_sha256") == result_hashes["ledger"]
        and delivery.get("native_result", {}).get("summary_sha256") == result_hashes["summary"],
        "placement_delivery_anchor_mismatch",
    )
    require(
        addendum.get("kind") == "tenki_placement_delivery_addendum"
        and addendum.get("base_delivery") == "delivery.json"
        and addendum.get("base_delivery_sha256") == delivery_hash
        and addendum.get("supplement", {}).get("sha256") == details_hash
        and addendum.get("supplement", {}).get("python_skipped") == python_skipped
        and addendum.get("supplement", {}).get("rust_ignored") == rust_ignored
        and addendum.get("supplement", {}).get("examples_ignored") == examples_ignored
        and details.get("kind") == "test_exclusion_details"
        and details.get("python", {}).get("skipped") == python_skipped
        and len(details.get("python", {}).get("items", [])) == python_skipped
        and details.get("rust_workspace_serial", {}).get("ignored") == rust_ignored
        and len(details.get("rust_workspace_serial", {}).get("items", [])) == rust_ignored
        and details.get("adapter_examples", {}).get("ignored") == examples_ignored
        and details.get("native_asset_opt_in") == "not_run"
        and details.get("doctor") == "not_run"
        and details.get("48_hand_evaluation") == "not_run",
        "placement_delivery_addendum_mismatch",
    )
    require(addendum_hash == addendum_expected, "placement_delivery_addendum_mismatch")
    return delivery, addendum, [
        {
            "role": role,
            "path": path.relative_to(repo).as_posix(),
            "sha256": found,
            "bytes": path.stat().st_size,
        }
        for role, path, found in (
            ("delivery", experiment / "final-build/delivery.json", delivery_hash),
            ("delivery_addendum", experiment / "final-build/delivery-addendum.json", addendum_hash),
            ("exclusion_details", details_path, details_hash),
        )
    ]


def _parse_placement_documents(raw_documents: dict[str, bytes]) -> dict[str, dict]:
    """Parse JSON records while leaving JSONL and ZIP evidence as raw bytes."""
    require(isinstance(raw_documents, dict), "placement_documents_invalid")
    raw_only = {"ledger", "native_source_archive", "final_source_archive"}
    return {
        name: strict_json(raw)
        for name, raw in raw_documents.items()
        if name not in raw_only
    }


def _placement_context_hash(_sources=None) -> str:
    """Resolve the context from a test/source description, preserving production pins."""
    value = PLACEMENT_CONTEXT if _sources is None else _sources.semantic_sha256("placement_context")
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None,
            "placement_context_hash_invalid")
    return value


def _placement_result_hashes(repo: Path, experiment: Path, _sources=None) -> dict[str, str]:
    """Return authenticated result-file hashes without conflating context identity."""
    if _sources is None:
        return {
            "ledger": PLACEMENT_LEDGER_SHA256,
            "summary": PLACEMENT_SUMMARY_SHA256,
        }
    return {
        name: _sources.file_sha256((experiment / "research" / filename).relative_to(repo).as_posix())
        for name, filename in (("ledger", "calls.jsonl"), ("summary", "summary.json"))
    }


def _ordinary_runtime_identity(workspace_identity: dict) -> dict:
    """Return the exact ordinary asset identity carried by the stage input."""
    require(isinstance(workspace_identity, dict), "placement_ordinary_identity_missing")
    runtimes = workspace_identity.get("runtimes")
    ordinary = runtimes.get("ordinary") if isinstance(runtimes, dict) else None
    require(isinstance(ordinary, dict), "placement_ordinary_identity_missing")
    return ordinary


def _validate_historical_native_build(manifest: dict, native_build: dict, *, _sources=None) -> bool:
    source_before = native_build.get("source_before") if isinstance(native_build, dict) else None
    if _sources is None:
        source_identity = HISTORICAL_NATIVE_SOURCE
        build_identity = HISTORICAL_NATIVE_BUILD
        runner_sha256 = HISTORICAL_NATIVE_RUNNER_SHA256
    else:
        source_identity = _sources.archive("placement_history_archive").source_identity
        build_identity = _sources.semantic_sha256("placement_historical_build")
        runner_sha256 = _sources.semantic_sha256("placement_historical_runner")
    require(
        isinstance(manifest, dict)
        and isinstance(native_build, dict)
        and native_build.get("identity") == build_identity
        and isinstance(source_before, dict)
        and source_before.get("identity") == source_identity
        and native_build.get("source_after") == source_before
        and native_build.get("artifacts", {}).get("runner") == runner_sha256
        and manifest.get("build_identity") == build_identity
        and manifest.get("runner_sha256") == runner_sha256
        and manifest.get("worker_sha256") == native_build.get("artifacts", {}).get("worker"),
        "historical_native_build_binding_mismatch",
    )
    return True


def _validate_placement_inputs(repo: Path, experiment: Path, delivery: dict, mark_check=None, *, _sources=None) -> tuple[dict, dict, list[dict]]:
    research = experiment / "research"
    paths = {
        "manifest": research / "manifest.json",
        "prepared": research / "prepared.json",
        "request": research / "stage-1-request.json",
        "input": research / "stage-1-input.json",
        "seal": research / "stage-1-input-seal.json",
        "summary": research / "summary.json",
        "ledger": research / "calls.jsonl",
        "identity": experiment / "identity.json",
        "native_build_record": experiment / "build-record.json",
        "native_source_archive": experiment / "source-native.zip",
        "native_source_file_list": experiment / "source-native-file-list.json",
        "final_source_archive": experiment / "final-build/source-final.zip",
        "final_source_file_list": experiment / "final-build/source-final-file-list.json",
        "final_build_record": experiment / "final-build/final-build-record.json",
        "baseline_transition": experiment / "baseline-transition.json",
    }
    check_for = {
        "manifest": "manifest",
        "prepared": "manifest",
        "request": "request",
        "input": "input",
        "seal": "seal",
        "summary": "ledger",
        "ledger": "ledger",
        "identity": "identity",
        "native_build_record": "identity",
        "native_source_archive": "historical_archive",
        "native_source_file_list": "historical_archive",
        "final_source_archive": "historical_archive",
        "final_source_file_list": "historical_archive",
        "final_build_record": "identity",
        "baseline_transition": "historical_archive",
    }
    raw = {}
    for name, path in paths.items():
        if mark_check is not None:
            mark_check(check_for[name])
        expected = None if _sources is None else _sources.file_sha256(path.relative_to(repo).as_posix())
        raw[name] = _read(path, expected)[0]
    hashes = {name: _sha(value) for name, value in raw.items()}
    fixed_hashes = (
        ("manifest", MANIFEST_SHA256),
        ("prepared", PREPARED_SHA256),
        ("request", STAGE1_REQUEST_SHA256),
        ("input", STAGE1_INPUT_SHA256),
        ("seal", STAGE1_SEAL_SHA256),
        ("ledger", PLACEMENT_LEDGER_SHA256),
        ("summary", PLACEMENT_SUMMARY_SHA256),
    )
    for name, fixed_hash in fixed_hashes:
        expected_hash = fixed_hash if _sources is None else _sources.file_sha256(paths[name].relative_to(repo).as_posix())
        if mark_check is not None:
            mark_check(check_for[name])
        require(hashes[name] == expected_hash, f"placement_{'ledger_summary' if name == 'summary' else name}_hash_mismatch")
    for name in paths:
        if name != "ledger" and mark_check is not None:
            mark_check(check_for[name])
    parsed = _parse_placement_documents(raw)
    context_hash = _placement_context_hash(_sources)
    historical_build_identity = (
        HISTORICAL_NATIVE_BUILD
        if _sources is None
        else _sources.semantic_sha256("placement_historical_build")
    )
    manifest = parsed["manifest"]
    prepared = parsed["prepared"]
    request = parsed["request"]
    invocation = parsed["input"]
    seal = parsed["seal"]
    identity = parsed["identity"]
    native_build = parsed["native_build_record"]
    final_build = parsed["final_build_record"]
    summary = parsed["summary"]
    transition = parsed["baseline_transition"]
    if mark_check is not None:
        mark_check("identity")
    _signed(identity, "workspace_identity")
    _signed(native_build, "build_record")
    _signed(final_build, "build_record")
    if mark_check is not None:
        mark_check("manifest")
    require(
        manifest.get("schema_version") == 1
        and manifest.get("kind") == "native_tenki_placement_manifest"
        and manifest.get("scope") == "tenki-placement-probe-v1"
        and manifest.get("context") == context_hash
        and manifest.get("source_identity") == (
            HISTORICAL_NATIVE_SOURCE if _sources is None else _sources.archive("placement_history_archive").source_identity
        )
        and manifest.get("build_identity") == (
            HISTORICAL_NATIVE_BUILD if _sources is None else _sources.semantic_sha256("placement_historical_build")
        )
        and manifest.get("old_consumed") == (
            26 if _sources is None else _sources.dataset_count("historical_consumed")
        )
        and manifest.get("old_stage1_sha256") == CORRECT_STAGE1_LITERAL
        and manifest.get("old_stage2_request_sha256") == OLD_STAGE2_REQUEST_SHA256
        and manifest.get("old_stage2_sha256") == OLD_STAGE2_SHA256
        and manifest.get("stage1_request_sha256") == digest(canonical(request))
        and manifest.get("input_sha256", {}).get("baseline_transition") == hashes["baseline_transition"]
        and manifest.get("input_sha256", {}).get("build_record") == hashes["native_build_record"]
        and manifest.get("input_sha256", {}).get("identity") == hashes["identity"]
        and manifest.get("input_sha256", {}).get("window_start") == _sha((experiment / "window-start.json").read_bytes())
        and digest(canonical({key: value for key, value in manifest.items() if key != "context"})) == context_hash,
        "placement_manifest_binding_mismatch",
    )
    if mark_check is not None:
        mark_check("input")
    require(
        invocation.get("schema_version") is None
        and invocation.get("context") == context_hash
        and invocation.get("stage") == 1
        and invocation.get("started_at") == manifest.get("started_at")
        and invocation.get("request") == request
        and Path(invocation.get("ledger", "")).absolute() == (research / "calls.jsonl").absolute()
        and Path(invocation.get("output", "")).absolute() == (research / "stage-1.json").absolute()
        and invocation.get("expected_identity") == _ordinary_runtime_identity(identity),
        "placement_stage1_input_binding_mismatch",
    )
    if mark_check is not None:
        mark_check("seal")
    require(
        seal == {
            "schema_version": 1,
            "kind": "tenki_placement_stage_input_seal",
            "context": context_hash,
            "stage": 1,
            "input_sha256": hashes["input"],
        },
        "placement_seal_binding_mismatch",
    )
    if mark_check is not None:
        mark_check("request")
    require(
        request.get("protocol_version") == 2
        and request.get("decisions") == [{"prompt_id": 7, "player": 0, "choice": {"kind": "command", "command": 5, "index": 0}}]
        and request.get("engine", {}).get("worker_path") == str((experiment / "native-artifacts/ygo-engine-worker.exe").absolute()),
        "placement_request_binding_mismatch",
    )
    if mark_check is not None:
        mark_check("manifest")
    require(
        prepared.get("kind") == "native_tenki_placement_prepared"
        and prepared.get("context") == context_hash
        and prepared.get("native_calls") == 0
        and prepared.get("first_stage_request_sha256") == digest(canonical(request)),
        "placement_preparation_binding_mismatch",
    )
    if mark_check is not None:
        mark_check("ledger")
    require(
        summary.get("kind") == "native_tenki_placement_summary"
        and summary.get("diagnostic") == "runner_failed"
        and summary.get("stages") == []
        and summary.get("new_consumed") == 0
        and summary.get("ledger", {}).get("unknown") == 0,
        "placement_failure_summary_mismatch",
    )
    if mark_check is not None:
        mark_check("historical_archive")
    require(
        transition.get("schema_version") == 2
        and transition.get("scope") == "tenki-placement-probe-v1"
        and transition.get("migration", {}).get("current_file_history") == "unknown"
        and transition.get("claims", {}).get("binary_provenance_verified") is False,
        "placement_transition_mismatch",
    )

    native_record_identity = native_build.get("identity")
    if mark_check is not None:
        mark_check("identity")
    require(native_record_identity == historical_build_identity, "historical_native_build_binding_mismatch")
    _validate_historical_native_build(manifest, native_build, _sources=_sources)
    final_record = delivery["final_build"]
    if mark_check is not None:
        mark_check("identity")
    require(
        final_build.get("identity") == final_record.get("record_identity")
        and final_build.get("source_before", {}).get("identity") == final_record.get("source_before_identity")
        and final_build.get("source_after", {}).get("identity") == final_record.get("source_after_identity")
        and final_build.get("status") == "recorded"
        and final_build.get("reproducible_build_proven") is False,
        "final_build_record_binding_mismatch",
    )

    if mark_check is not None:
        mark_check("historical_archive")
    history_archive_pin = None if _sources is None else _sources.archive("placement_history_archive")
    if history_archive_pin is not None:
        require(
            history_archive_pin.archive_path == paths["native_source_archive"].relative_to(repo).as_posix()
            and history_archive_pin.file_list_path == paths["native_source_file_list"].relative_to(repo).as_posix(),
            "source_description_archive_path_mismatch",
        )
    native_archive_values = (
        (NATIVE_SOURCE_ARCHIVE_SHA256, NATIVE_SOURCE_FILE_LIST_SHA256, HISTORICAL_NATIVE_SOURCE, 401)
        if history_archive_pin is None else
        (history_archive_pin.archive_sha256, history_archive_pin.file_list_sha256,
         history_archive_pin.source_identity, history_archive_pin.file_count)
    )
    native_archive = _verify_archive(
        experiment,
        "source-native.zip",
        "source-native-file-list.json",
        *native_archive_values,
    )
    final_archive = _verify_archive(
        experiment / "final-build",
        "source-final.zip",
        "source-final-file-list.json",
        FINAL_SOURCE_ARCHIVE_SHA256 if _sources is None else _sources.file_sha256(paths["final_source_archive"].relative_to(repo).as_posix()),
        FINAL_SOURCE_FILE_LIST_SHA256 if _sources is None else _sources.file_sha256(paths["final_source_file_list"].relative_to(repo).as_posix()),
        delivery["final_source"]["identity"],
        delivery["final_source"]["file_count"],
    )
    rust_match = re.search(r'const OLD_STAGE1_SHA256: &str\s*=\s*"([^"]+)";', native_archive["archived_rust"])
    require(rust_match is not None and rust_match.group(1) == WRONG_ARCHIVED_STAGE1_LITERAL, "historical_archived_anchor_mismatch")
    require(transition.get("identity") == digest(canonical({key: value for key, value in transition.items() if key != "identity"})), "placement_transition_identity_mismatch")

    input_records = []
    for name, path in paths.items():
        input_records.append({
            "role": name,
            "path": path.relative_to(repo).as_posix(),
            "sha256": hashes[name],
            "bytes": len(raw[name]),
        })
    delivery_inputs = (
        ("delivery", experiment / "final-build/delivery.json", EXPERIMENT_DELIVERY_SHA256),
        ("delivery_addendum", experiment / "final-build/delivery-addendum.json", EXPERIMENT_ADDENDUM_SHA256),
        ("exclusion_details", experiment / "verification/test-exclusion-details.json", EXPERIMENT_DETAILS_SHA256),
    )
    for role, path, fixed_hash in delivery_inputs:
        relative = path.relative_to(repo).as_posix()
        expected_hash = fixed_hash if _sources is None else _sources.file_sha256(relative)
        input_records.append({
            "role": role,
            "path": relative,
            "sha256": expected_hash,
            "bytes": path.stat().st_size,
        })
    return manifest, invocation, input_records


def _safe_error(error) -> str:
    value = str(error)
    return value if re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value) else "offline_preflight_failed"


def _preflight_output_matches(value, context: str, expected_identity: str) -> bool:
    return (
        isinstance(value, dict)
        and value.get("preflight_passed") is True
        and type(value.get("native_calls")) is int
        and value.get("native_calls") == 0
        and type(value.get("stage")) is int
        and value.get("stage") == 1
        and value.get("context") == context
        and value.get("identity_sha256") == expected_identity
    )


def _deduplicate_input_records(records: list[dict]) -> list[dict]:
    """Keep one record per role/path while rejecting conflicting observations."""
    unique = []
    by_key = {}
    for item in records:
        require(isinstance(item, dict), "diagnostic_input_record_invalid")
        key = (item.get("role"), item.get("path"))
        previous = by_key.get(key)
        if previous is None:
            by_key[key] = item
            unique.append(item)
        else:
              require(canonical(previous) == canonical(item), "diagnostic_input_record_conflict")
    return unique


def _report(args, repo: Path) -> dict:
    start = time.monotonic()
    checks = {
        "baseline_acceptance": "not_run",
        "historical_archive": "not_run",
        "manifest": "not_run",
        "request": "not_run",
        "input": "not_run",
        "seal": "not_run",
        "ledger": "not_run",
        "identity": "not_run",
        "preflight_process": "not_run",
    }
    process_record = None
    invocation = None
    diagnostic = None
    source_before = None
    source_after = None
    input_records = []
    protected_inputs = {}
    experiment_snapshot = {}
    baseline_snapshot = {}
    asset_scan_time = None
    asset_identity_match = None
    input_drift = {
        "workspace_source_unchanged": None,
        "baseline_tree_unchanged": None,
        "experiment_tree_unchanged": None,
        "protected_inputs_unchanged": None,
    }
    output = _absolute(args.output)
    current_check = "baseline_acceptance"
    def mark_check(name):
        nonlocal current_check
        current_check = name

    try:
        baseline = _absolute(args.baseline_dir)
        experiment = _absolute(args.experiment_dir)
        expected_baseline = repo / BASELINE_RELATIVE
        expected_experiment = repo / OUTPUT_ROOT_RELATIVE
        offline_root = repo / DIAGNOSTICS_RELATIVE
        expected_runner = offline_root / "native-artifacts/tenki-placement-probe.exe"
        expected_build = offline_root / "build-record.json"
        expected_output = offline_root / "preflight-report.json"
        require(baseline == expected_baseline and experiment == expected_experiment, "frozen_diagnostic_directory_required")
        require(_absolute(args.runner) == expected_runner and _absolute(args.build_record) == expected_build and output == expected_output, "fixed_diagnostic_output_paths_required")
        require(offline_root.is_dir(), "diagnostic_output_directory_missing")
        safe_path(offline_root, file=False)
        require(not output.exists() and not output.is_symlink(), "diagnostic_output_exists")
        baseline_snapshot = _tree_snapshot(baseline, ".")
        experiment_snapshot = _tree_snapshot(experiment, ".")
        for role, directory, snapshot in (
            ("baseline_directory_manifest", baseline, baseline_snapshot),
            ("experiment_directory_manifest", experiment, experiment_snapshot),
        ):
            encoded_snapshot = canonical(snapshot)
            input_records.append({
                "role": role,
                "path": directory.relative_to(repo).as_posix(),
                "sha256": digest(encoded_snapshot),
                "bytes": len(encoded_snapshot),
            })
        source_before = stable_source(repo)
        delivery, _addendum, delivery_records = _verify_experiment_delivery(repo, experiment)
        checks["baseline_acceptance"] = "passed"

        current_check = "historical_archive"
        transition = experiment / TRANSITION_FILE_PATH.name
        native_archive = _verify_archive(
            experiment,
            "source-native.zip",
            "source-native-file-list.json",
            NATIVE_SOURCE_ARCHIVE_SHA256,
            NATIVE_SOURCE_FILE_LIST_SHA256,
            HISTORICAL_NATIVE_SOURCE,
            401,
        )
        require(
            native_archive["archived_rust_literal"] == WRONG_ARCHIVED_STAGE1_LITERAL
            and len(native_archive["archived_rust_literal"]) == 66,
            "historical_archived_anchor_mismatch",
        )
        transition_payload = _transition_payload_from_current(baseline, repo, 2)
        historical_module_hash = native_archive["archived_audit_tool_sha256"]
        transition_payload["audit_tool"] = {
            "source_identity": HISTORICAL_NATIVE_SOURCE,
            "module_sha256": historical_module_hash,
        }
        transition_payload["input_sha256"]["audit_tool_source"] = HISTORICAL_NATIVE_SOURCE
        transition_payload["input_sha256"]["audit_tool_module"] = historical_module_hash
        _baseline_report, protected_inputs = collect_baseline_bytes(
            baseline,
            repo,
            transition_path=transition,
            report_version=2,
            transition_payload_override=transition_payload,
        )
        checks["historical_archive"] = "passed"
        current_check = "manifest"
        manifest, invocation, placement_inputs = _validate_placement_inputs(repo, experiment, delivery, mark_check)
        input_records.extend(delivery_records)
        input_records.extend(placement_inputs)
        input_records.extend(
            {"role": "protected_history", "path": path.relative_to(repo).as_posix(), "sha256": expected, "bytes": path.stat().st_size}
            for path, expected in protected_inputs.items()
        )
        checks["manifest"] = checks["request"] = checks["input"] = checks["seal"] = checks["ledger"] = "passed"

        current_check = "input"
        input_drift["experiment_tree_unchanged"] = _tree_snapshot(experiment, ".") == experiment_snapshot
        require(input_drift["experiment_tree_unchanged"], "placement_evidence_changed_during_capture")
        input_drift["baseline_tree_unchanged"] = _tree_snapshot(baseline, ".") == baseline_snapshot
        require(input_drift["baseline_tree_unchanged"], "historical_directory_changed_during_capture")

        current_check = "identity"
        runner = _absolute(args.runner)
        build_path = _absolute(args.build_record)
        runner_raw, runner_hash = _read(runner)
        build_raw, build_hash = _read(build_path)
        build_record = strict_json(build_raw)
        _signed(build_record, "build_record")
        current_source = stable_source(repo)
        require(
            build_record.get("status") == "recorded"
            and build_record.get("source_before") == current_source
            and build_record.get("source_after") == current_source
            and build_record.get("reproducible_build_proven") is False
            and build_record.get("artifacts", {}).get("runner") == runner_hash,
            "audit_build_identity_mismatch",
        )
        checks["identity"] = "passed"
        protected_before = {path: _sha(safe_path(path).read_bytes()) for path in protected_inputs}

        current_check = "preflight_process"
        input_path = experiment / "research/stage-1-input.json"
        command = [str(runner), str(input_path), "--input-sha", STAGE1_INPUT_SHA256, "--preflight-only"]
        asset_scan_time = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        process_record, completed = capture_process_diagnostic(
            command,
            repo,
            offline_root,
            mode="preflight_only",
            timeout=900,
        )
        if process_record["status"] != "completed":
            diagnostic = process_record["error_code"] or "runner_process_failed"
        elif completed is None or completed.returncode != 0:
            diagnostic = "runner_nonzero_exit"
        else:
            try:
                runner_output = strict_json(completed.stdout)
            except (ValueError, TypeError, UnicodeDecodeError):
                runner_output = None
                diagnostic = "runner_invalid_json"
            if isinstance(runner_output, dict):
                if _preflight_output_matches(
                    runner_output,
                    manifest.get("context"),
                    invocation.get("expected_identity", {}).get("identity"),
                ):
                    checks["preflight_process"] = "passed"
                    asset_identity_match = True
                else:
                    asset_identity_match = False
                    diagnostic = "runner_preflight_result_mismatch"
        input_drift["workspace_source_unchanged"] = stable_source(repo) == current_source
        require(input_drift["workspace_source_unchanged"], "workspace_source_changed_during_preflight")
        input_drift["experiment_tree_unchanged"] = _tree_snapshot(experiment, ".") == experiment_snapshot
        require(input_drift["experiment_tree_unchanged"], "placement_evidence_changed_during_preflight")
        input_drift["baseline_tree_unchanged"] = _tree_snapshot(baseline, ".") == baseline_snapshot
        require(input_drift["baseline_tree_unchanged"], "historical_directory_changed_during_preflight")
        input_drift["protected_inputs_unchanged"] = {path: _sha(safe_path(path).read_bytes()) for path in protected_inputs} == protected_before
        require(input_drift["protected_inputs_unchanged"], "baseline_evidence_changed_during_preflight")
        source_after = stable_source(repo)
        require(source_after == source_before, "workspace_source_changed_during_preflight")
    except DiagnosticPersistenceError:
        diagnostic = "diagnostic_persistence_failed"
        raise
    except (ValueError, OSError, KeyError, TypeError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        diagnostic = _safe_error(error)
        failed_check = current_check
        if diagnostic.startswith("placement_manifest"):
            failed_check = "manifest"
        elif diagnostic.startswith("placement_prepared") or diagnostic.startswith("placement_preparation"):
            failed_check = "manifest"
        elif diagnostic.startswith("placement_request") or diagnostic == "placement_stage1_seal_or_request_mismatch":
            failed_check = "request"
        elif diagnostic.startswith("placement_stage1_input") or diagnostic.startswith("placement_input"):
            failed_check = "input"
        elif diagnostic.startswith("placement_seal"):
            failed_check = "seal"
        elif diagnostic.startswith("placement_ledger") or diagnostic.startswith("placement_failure_summary"):
            failed_check = "ledger"
        elif (
            diagnostic.startswith("historical_archived_anchor")
            or diagnostic.startswith("historical_native_build")
            or diagnostic.startswith("placement_transition")
            or diagnostic.startswith("source_archive")
        ):
            failed_check = "historical_archive"
        elif diagnostic.startswith("final_build_record") or diagnostic == "audit_build_identity_mismatch":
            failed_check = "identity"
        elif diagnostic.startswith("placement_evidence_changed") or diagnostic.startswith("historical_directory_changed"):
            failed_check = "input"
        checks[failed_check] = "failed"

    if process_record is not None and process_record["status"] == "completed" and process_record["return_code"] != 0:
        diagnostic = diagnostic or "runner_nonzero_exit"
    if process_record is not None and checks["preflight_process"] == "not_run":
        checks["preflight_process"] = "failed"
    if diagnostic is None and checks["preflight_process"] != "passed":
        diagnostic = "runner_preflight_not_completed"
    success = diagnostic is None and all(value == "passed" for value in checks.values())
    elapsed = round(time.monotonic() - start, 3)
    source_identity = source_after.get("identity") if source_after else source_before.get("identity") if source_before else None
    source_section = {
        "historical_native": HISTORICAL_NATIVE_SOURCE,
        "native_build": HISTORICAL_NATIVE_BUILD,
        "historical_runner_sha256": HISTORICAL_NATIVE_RUNNER_SHA256,
        "audit_source": source_identity or "0" * 64,
        "audit_build": "0" * 64,
        "audit_runner_sha256": "0" * 64,
    }
    try:
        if args.build_record.exists():
            build_record = strict_json(args.build_record.read_bytes())
            source_section["audit_build"] = build_record.get("identity", "0" * 64)
            source_section["audit_runner_sha256"] = build_record.get("artifacts", {}).get("runner", "0" * 64)
    except (OSError, ValueError, TypeError):
        pass
    anchor = {
        "archived_rust_literal": WRONG_ARCHIVED_STAGE1_LITERAL,
        "actual_stage1_sha256": CORRECT_STAGE1_LITERAL,
        "python_anchor_sha256": OLD_STAGE1_SHA256,
        "repaired_rust_anchor_sha256": CORRECT_STAGE1_LITERAL,
        "historical_stderr": "not_saved",
    }
    input_records = _deduplicate_input_records(input_records)
    inputs_for_hash = sorted(
        ({"path": item["path"], "sha256": item["sha256"]} for item in input_records),
        key=lambda item: item["path"],
    )
    if process_record is not None:
        metadata_path = repo / DIAGNOSTICS_RELATIVE / process_record["metadata_path"]
        if metadata_path.is_file():
            process_record["metadata_bytes"] = metadata_path.stat().st_size
    report = {
        "schema_version": 1,
        "kind": "tenki_placement_diagnostics",
        "operation": "stage1_preflight_audit",
        "status": "passed" if success else "failed",
        "native_calls": 0,
        "execution_ready": False,
        "source_identity": source_section,
        "historical_anchor": anchor,
        "historical_claims": {
            "old_binary_provenance_verified": False,
            "historical_reexecution_verified": False,
            "historical_stderr_recovered": False,
        },
        "inputs": input_records,
        "asset_scan": {
            "time_utc": asset_scan_time,
            "expected_identity_sha256": (
                invocation.get("expected_identity", {}).get("identity")
                if isinstance(invocation, dict)
                else "0" * 64
            ),
            "identity_match": asset_identity_match,
        },
        "input_drift": input_drift,
        "checks": checks,
        "process_diagnostic": process_record,
        "diagnostic": diagnostic,
        "input_snapshot_sha256": digest(canonical(inputs_for_hash)),
        "input_count": len(input_records),
        "evidence_bytes": sum(item.get("bytes", 0) for item in input_records)
        + (
            process_record["stdout"]["bytes"]
            + process_record["stderr"]["bytes"]
            + process_record.get("metadata_bytes", 0)
            if process_record
            else 0
        ),
        "elapsed_seconds": elapsed,
        **FLAGS,
    }
    return report


def audit_tenki_placement_preflight(args, repo=None):
    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    output = _absolute(args.output)
    report = _report(args, repo)
    _validate_report(report, repo)
    raw = json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    try:
        _write_exclusive(output, raw)
    except OSError as error:
        raise DiagnosticPersistenceError("preflight report persistence failed") from error
    return report


def _validate_report(report: dict, repo: Path) -> None:
    """Apply the contract's stable runtime invariants without a jsonschema dependency."""
    expected_keys = {
        "schema_version", "kind", "operation", "status", "native_calls", "execution_ready",
        "source_identity", "historical_anchor", "historical_claims", "inputs", "asset_scan",
        "input_drift", "checks", "process_diagnostic", "diagnostic", "input_snapshot_sha256",
        "input_count", "evidence_bytes", "elapsed_seconds", *FLAGS.keys(),
    }
    require(isinstance(report, dict) and set(report) == expected_keys, "diagnostic_report_fields_invalid")
    require(type(report.get("schema_version")) is int and report.get("schema_version") == 1, "diagnostic_report_schema_version_invalid")
    require(report.get("kind") == "tenki_placement_diagnostics", "diagnostic_report_kind_invalid")
    require(report.get("operation") == "stage1_preflight_audit", "diagnostic_report_operation_invalid")
    require(report.get("status") in ("passed", "failed"), "diagnostic_report_status_invalid")
    require(type(report.get("native_calls")) is int and report.get("native_calls") == 0 and report.get("execution_ready") is False, "diagnostic_report_qualification_invalid")
    diagnostic = report.get("diagnostic")
    require(
        diagnostic is None or (isinstance(diagnostic, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,90}", diagnostic) is not None),
        "diagnostic_report_diagnostic_invalid",
    )
    require(all(report.get(flag) is False for flag in FLAGS), "diagnostic_report_qualification_invalid")
    identity = report.get("source_identity")
    require(
        isinstance(identity, dict)
        and set(identity) == {
            "historical_native", "native_build", "historical_runner_sha256", "audit_source", "audit_build", "audit_runner_sha256"
        }
        and all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in identity.values()),
        "diagnostic_report_identity_invalid",
    )
    anchor = report.get("historical_anchor")
    require(
        isinstance(anchor, dict)
        and anchor.get("archived_rust_literal") == WRONG_ARCHIVED_STAGE1_LITERAL
        and len(anchor["archived_rust_literal"]) == 66
        and anchor.get("actual_stage1_sha256") == CORRECT_STAGE1_LITERAL
        and anchor.get("python_anchor_sha256") == OLD_STAGE1_SHA256
        and anchor.get("repaired_rust_anchor_sha256") == CORRECT_STAGE1_LITERAL
        and anchor.get("historical_stderr") == "not_saved",
        "diagnostic_report_anchor_invalid",
    )
    require(
        report.get("historical_claims") == {
            "old_binary_provenance_verified": False,
            "historical_reexecution_verified": False,
            "historical_stderr_recovered": False,
        },
        "diagnostic_report_historical_claims_invalid",
    )
    scan = report.get("asset_scan")
    require(
        isinstance(scan, dict)
        and set(scan) == {"time_utc", "expected_identity_sha256", "identity_match"}
        and (scan["time_utc"] is None or isinstance(scan["time_utc"], str))
        and re.fullmatch(r"[a-f0-9]{64}", scan.get("expected_identity_sha256", "")) is not None
        and (scan["identity_match"] is None or type(scan["identity_match"]) is bool),
        "diagnostic_report_asset_scan_invalid",
    )
    drift = report.get("input_drift")
    require(
        isinstance(drift, dict)
        and set(drift) == {
            "workspace_source_unchanged", "baseline_tree_unchanged", "experiment_tree_unchanged", "protected_inputs_unchanged"
        }
        and all(value is None or type(value) is bool for value in drift.values()),
        "diagnostic_report_input_drift_invalid",
    )
    require(isinstance(report.get("inputs"), list), "diagnostic_report_inputs_invalid")
    require(type(report.get("input_count")) is int and report.get("input_count") == len(report["inputs"]), "diagnostic_report_input_count_invalid")
    seen_inputs = set()
    for item in report["inputs"]:
        require(
            isinstance(item, dict)
            and set(item) == {"role", "path", "sha256", "bytes"}
            and isinstance(item["role"], str)
            and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item["role"]) is not None
            and isinstance(item["path"], str) and bool(item["path"])
            and not Path(item["path"]).is_absolute()
            and "\\" not in item["path"]
            and ":" not in item["path"]
            and ".." not in Path(item["path"]).parts
            and re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) is not None
            and type(item["bytes"]) is int
            and item["bytes"] >= 0,
            "diagnostic_report_input_entry_invalid",
        )
        key = (item["role"], item["path"])
        require(key not in seen_inputs, "diagnostic_report_duplicate_input")
        seen_inputs.add(key)
    require(
        isinstance(report.get("checks"), dict)
        and set(report["checks"]) == {
            "baseline_acceptance", "historical_archive", "manifest", "request", "input", "seal", "ledger", "identity", "preflight_process"
        }
        and all(value in ("passed", "failed", "not_run") for value in report["checks"].values()),
        "diagnostic_report_checks_invalid",
    )
    inputs_for_hash = sorted(
        ({"path": item["path"], "sha256": item["sha256"]} for item in report["inputs"]),
        key=lambda item: item["path"],
    )
    require(
        re.fullmatch(r"[a-f0-9]{64}", report.get("input_snapshot_sha256", "")) is not None
        and report["input_snapshot_sha256"] == digest(canonical(inputs_for_hash)),
        "diagnostic_report_hash_invalid",
    )
    process_record = report.get("process_diagnostic")
    if process_record is not None:
        require(
            isinstance(process_record, dict)
            and set(process_record) == {"mode", "runner_role", "status", "return_code", "error_code", "stdout", "stderr", "metadata_path", "metadata_bytes"}
            and process_record.get("mode") == "preflight_only"
            and process_record.get("runner_role") == "tenki_placement_audit_runner",
            "diagnostic_process_mode_invalid",
        )
        process_status = process_record.get("status")
        return_code = process_record.get("return_code")
        error_code = process_record.get("error_code")
        require(
            (process_status == "completed" and type(return_code) is int and error_code is None)
            or (process_status == "timeout" and return_code is None and error_code == "runner_timeout")
            or (process_status == "launch_failed" and return_code is None and error_code in {"runner_start_failed", "runner_launch_exception"}),
            "diagnostic_process_return_status_mismatch",
        )
        evidence_root = repo / DIAGNOSTICS_RELATIVE
        for stream in ("stdout", "stderr"):
            value = process_record.get(stream)
            require(
                isinstance(value, dict)
                and isinstance(value.get("path"), str)
                and not Path(value["path"]).is_absolute()
                and value["path"].startswith("process-diagnostics/")
                and "\\" not in value["path"]
                and ":" not in value["path"]
                and ".." not in Path(value["path"]).parts
                and re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", "")) is not None
                and type(value.get("bytes")) is int
                and value["bytes"] >= 0,
                "diagnostic_process_stream_invalid",
            )
            raw = _read(evidence_root / value["path"])[0]
            require(len(raw) == value["bytes"] and _sha(raw) == value["sha256"], "diagnostic_process_stream_hash_mismatch")
        require(
            isinstance(process_record.get("metadata_path"), str)
            and not Path(process_record["metadata_path"]).is_absolute()
            and process_record["metadata_path"].startswith("process-diagnostics/")
            and "\\" not in process_record["metadata_path"]
            and ":" not in process_record["metadata_path"]
            and ".." not in Path(process_record["metadata_path"]).parts
            and type(process_record.get("metadata_bytes", 0)) is int
            and process_record.get("metadata_bytes", 0) >= 0,
            "diagnostic_process_metadata_invalid",
        )
        metadata_raw = _read(evidence_root / process_record["metadata_path"])[0]
        metadata = strict_json(metadata_raw)
        metadata_expected = {key: value for key, value in process_record.items() if key != "metadata_bytes"}
        require(
            len(metadata_raw) == process_record["metadata_bytes"] and metadata == metadata_expected,
            "diagnostic_process_metadata_mismatch",
        )
    if report["checks"]["preflight_process"] == "passed":
        require(
            process_record is not None
            and process_record.get("status") == "completed"
            and process_record.get("return_code") == 0
            and type(process_record.get("return_code")) is int,
            "diagnostic_process_success_mismatch",
        )
    require(
        type(report.get("evidence_bytes")) is int
        and report["evidence_bytes"] >= 0
        and isinstance(report.get("elapsed_seconds"), (int, float))
        and type(report.get("elapsed_seconds")) is not bool
        and math.isfinite(report["elapsed_seconds"])
        and report["elapsed_seconds"] >= 0,
        "diagnostic_report_measurement_invalid",
    )
    expected_evidence_bytes = sum(item["bytes"] for item in report["inputs"])
    if process_record is not None:
        expected_evidence_bytes += (
            process_record["stdout"]["bytes"]
            + process_record["stderr"]["bytes"]
            + process_record["metadata_bytes"]
        )
    require(report["evidence_bytes"] == expected_evidence_bytes, "diagnostic_report_evidence_size_mismatch")
    if report["status"] == "passed":
        require(report["asset_scan"]["identity_match"] is True, "diagnostic_report_asset_match_required")
    require(
        (report.get("status") == "passed")
        is (report.get("diagnostic") is None and all(value == "passed" for value in report["checks"].values())),
        "diagnostic_report_status_mismatch",
    )
