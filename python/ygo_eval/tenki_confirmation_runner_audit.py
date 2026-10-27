"""Zero-call audit of the repaired Tenki confirmation runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import zipfile
from typing import Any, Callable

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source
from ygo_eval.prompt_probe_prepare import require, safe_path, strict_json
from ygo_eval.terminal_regression import immutable_write


EXPERIMENT_RELATIVE = Path("data/runtime/p1-tenki-placement-confirmation-native-2026-10-22")
DIAGNOSTICS_RELATIVE = Path("data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22")
OUTPUT_RELATIVE = Path("data/runtime/p1-tenki-runner-repair-offline-2026-10-23")
DELIVERY_SHA256 = "19ba6de5b0f7ca3bfc395d72410927e3e9137408a03e6a29f80376bcb19cee0a"
CONFIRMATION_CONTEXT = "0f55ccf433f7d0e90421cf40850e64de8c02614404ec8d6028e767dfbbbbb138"
CONFIRMATION_LEDGER_SHA256 = "5daf512e4381803663df466575f4706f083843629ae660caf8c557ebecc8bc21"
HISTORICAL_CONSUMED = 26
HISTORICAL_UNKNOWN = 0
PREFLIGHT_TIMEOUT_SECONDS = 900
RUNNER_ROLE = "tenki_placement_confirmation_runner"
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
TRACE_PHASES = (
    "input_validation",
    "shared_preflight",
    "ledger_check",
    "precharge_scan",
    "batch_call",
    "postcharge_scan",
    "receipt_save",
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _safe_file(path: Path) -> Path:
    return regular_file(_absolute(path))


def _read(path: Path, expected: str | None = None) -> tuple[bytes, str]:
    raw = _safe_file(path).read_bytes()
    found = _sha(raw)
    require(expected is None or found == expected, "pinned_input_hash_mismatch")
    return raw, found


def _read_source(path: Path, repo: Path, sources, expected: str | None = None) -> tuple[bytes, str]:
    """Read one fixed input, additionally binding it to the immutable source tree."""
    if sources is not None:
        profile_pin = sources.file_sha256(path.relative_to(repo).as_posix())
        require(expected is None or expected == profile_pin, "source_description_file_binding_mismatch")
        expected = profile_pin
    return _read(path, expected)


def _safe_error(error: BaseException) -> str:
    value = str(error)
    return value if re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value) else "offline_audit_failed"


def _signed(value: Any, kind: str) -> None:
    require(isinstance(value, dict) and value.get("kind") == kind, "signed_record_kind_mismatch")
    unsigned = {key: item for key, item in value.items() if key != "identity"}
    require(value.get("identity") == digest(canonical(unsigned)), "signed_record_identity_mismatch")


def _validate_delivery_header(delivery: Any, *, expected_context: str | None = None) -> None:
    """Check the pinned delivery's actual v1 fields; this contract has no status field."""
    pinned_context = CONFIRMATION_CONTEXT if expected_context is None else expected_context
    require(
        isinstance(delivery, dict)
        and delivery.get("schema_version") == 1
        and delivery.get("kind") == "native_tenki_placement_confirmation_delivery"
        and delivery.get("scope") == "tenki-placement-confirmation-v1"
        and delivery.get("context") == pinned_context
        and delivery.get("history_totals") == {
            "consumed": HISTORICAL_CONSUMED,
            "old_runner_availability_reverified": False,
            "unknown": HISTORICAL_UNKNOWN,
        }
        and delivery.get("native_outcome", {}).get("first_stage_diagnostic") == "runner_timeout"
        and delivery.get("native_outcome", {}).get("charged_calls") == 0
        and delivery.get("native_outcome", {}).get("unknown_consumption") == 0
        and delivery.get("window", {}).get("remaining_slots_authorized") == 0
        and delivery.get("qualifications") == FLAGS,
        "confirmation_delivery_content_mismatch",
    )


def _source_file_pin(sources, repo: Path, path: Path, fallback: str) -> str:
    """Return a fixed profile pin for a repository-relative file, if supplied."""
    return fallback if sources is None else sources.file_sha256(path.relative_to(repo).as_posix())


def _source_archive_pin(sources, role: str, repo: Path, archive_path: Path,
                        file_list_path: Path, fallback: tuple[str, str, str, int]) -> tuple[str, str, str, int]:
    """Resolve an archive pin without allowing the profile to redirect its path."""
    if sources is None:
        return fallback
    pinned = sources.archive(role)
    require(
        pinned.archive_path == archive_path.relative_to(repo).as_posix()
        and pinned.file_list_path == file_list_path.relative_to(repo).as_posix(),
        "source_description_archive_path_mismatch",
    )
    return pinned.archive_sha256, pinned.file_list_sha256, pinned.source_identity, pinned.file_count


def _historical_ledger_hashes(sources=None) -> list[str]:
    """Resolve the fixed historical ledger set from its explicit source leaf."""
    from ygo_eval.native_tenki_placement_confirmation import OLD_LEDGER_CONTRACTS

    if sources is None:
        return [contract[2] for contract in OLD_LEDGER_CONTRACTS]
    ledger_sources = sources.child("historical_ledgers")
    return [ledger_sources.file_sha256(contract[1]) for contract in OLD_LEDGER_CONTRACTS]


def _validate_identity_binding(
    manifest: dict,
    invocation: dict,
    identity_file: Any,
    identity_file_sha256: str,
) -> None:
    """Bind identity.json bytes separately from its ordinary runtime identity object."""
    require(
        isinstance(identity_file, dict)
        and identity_file.get("kind") == "workspace_identity"
        and identity_file.get("schema_version") == 1
        and identity_file.get("consistent") is True
        and identity_file.get("runtimes", {}).get("ordinary") == invocation.get("expected_identity")
        and manifest.get("input_sha256", {}).get("identity") == identity_file_sha256,
        "confirmation_workspace_identity_binding_invalid",
    )


def _validate_window_binding(manifest: dict, window: Any) -> None:
    require(
        isinstance(window, dict)
        and window.get("schema_version") == 1
        and window.get("kind") == "tenki_placement_confirmation_window_start"
        and window.get("scope") == "tenki-placement-confirmation-v1"
        and window.get("limit") == 6
        and window.get("wall_seconds") == 7200
        and window.get("started_at") == manifest.get("started_at"),
        "confirmation_window_binding_invalid",
    )


def _delivery_report_hash(delivery: dict, role: str) -> str | None:
    return delivery.get("reports", {}).get({
        "prepared": "prepared_sha256",
        "stage1_report": "stage1_report_sha256",
        "summary": "summary_sha256",
        "verification": "verification_sha256",
    }[role])


def _add_protected(protected: dict[Path, str], path: Path, expected: str, *, repo: Path | None = None, _sources=None) -> dict:
    if _sources is not None:
        require(repo is not None, "source_description_repo_missing")
        raw, found = _read_source(path, repo, _sources, expected)
    else:
        raw, found = _read(path, expected)
    absolute = _absolute(path)
    previous = protected.get(absolute)
    require(previous is None or previous == found, "protected_input_binding_conflict")
    protected[absolute] = found
    return {"path": absolute.as_posix(), "sha256": found, "bytes": len(raw)}


def _verify_eighth_ledger(
    experiment: Path,
    *,
    _sources=None,
    repo: Path | None = None,
) -> tuple[dict[Path, str], dict]:
    """Verify the current scope's two-line, uncharged ledger and its checkpoint blob."""
    from ygo_eval.native_tenki_placement_confirmation import _encode, _ordered_entry

    path = experiment / "research/calls.jsonl"
    if _sources is not None:
        require(repo is not None, "source_description_repo_missing")
        expected_hash = _sources.file_sha256(path.relative_to(repo).as_posix())
    else:
        expected_hash = CONFIRMATION_LEDGER_SHA256
    raw, found = _read(path, expected_hash)
    require(raw.endswith(b"\n") and not raw.endswith(b"\n\n"), "confirmation_ledger_shape_invalid")
    rows = [strict_json(line) for line in raw[:-1].split(b"\n")]
    require(len(rows) == 2, "confirmation_ledger_unexpected_records")
    previous = ""
    entries = []
    for sequence, row in enumerate(rows):
        require(
            isinstance(row, dict)
            and set(row) == {"sequence", "previous", "entry", "hash"}
            and type(row.get("sequence")) is int
            and row["sequence"] == sequence
            and row.get("previous") == previous,
            "confirmation_ledger_chain_invalid",
        )
        entry = _ordered_entry(row.get("entry"))
        calculated = _sha(_encode([sequence, previous, entry]))
        require(row.get("hash") == calculated, "confirmation_ledger_chain_hash_invalid")
        previous = calculated
        entries.append(entry)
    expected_context = (
        CONFIRMATION_CONTEXT
        if _sources is None
        else _sources.semantic_sha256("runner_confirmation_context")
    )
    require(
        entries[0] == {
            "kind": "header", "version": 1,
            "scope": "tenki-placement-confirmation-v1",
            "context": expected_context,
            "limit": 6,
        },
        "confirmation_ledger_header_mismatch",
    )
    checkpoint = entries[1]
    require(
        checkpoint.get("kind") == "checkpoint"
        and checkpoint.get("name") == "immutable/tenki-placement-confirmation/start"
        and checkpoint.get("consumed") == 0
        and checkpoint.get("charged_sequence") == _sha(_encode([])),
        "confirmation_ledger_start_checkpoint_mismatch",
    )
    blob_path = experiment / "research/calls.jsonl.blobs/checkpoints" / f"{checkpoint['blob']}.json"
    blob_expected = checkpoint["blob"]
    if _sources is not None:
        blob_raw, blob_hash = _read_source(blob_path, repo, _sources, blob_expected)
    else:
        blob_raw, blob_hash = _read(blob_path, blob_expected)
    blob = strict_json(blob_raw)
    require(
        isinstance(blob, dict)
        and blob.get("budget", {}).get("consumed") == 0
        and blob.get("budget", {}).get("completed") == 0
        and blob.get("budget", {}).get("unknown") == 0
        and blob.get("budget", {}).get("reserved") == 0
        and blob.get("budget", {}).get("abandoned") == 0
        and blob.get("charged_sequence") == checkpoint["charged_sequence"],
        "confirmation_ledger_checkpoint_blob_mismatch",
    )
    protected = {_absolute(path): found, _absolute(blob_path): blob_hash}
    return protected, {"sha256": found, "records": 2, "consumed": 0, "unknown": 0, "checkpoint_blob_sha256": blob_hash}


def _verify_confirmation_baseline(repo: Path, baseline_dir: Path,
                                 protection_scope: str | None = None, *, _sources=None) -> dict:
    """Authenticate the pinned delivery, archives, build, reports, request, and all eight ledgers."""
    from ygo_eval.native_tenki_placement_confirmation import (
        FINAL_ARCHIVE_SHA256,
        FINAL_LIST_SHA256,
        FINAL_SOURCE,
        OLD_LEDGER_CONTRACTS,
        _diagnostic_hash,
        _validate_manifest,
    )
    from ygo_eval.tenki_placement_diagnostics import _verify_archive

    experiment = repo / EXPERIMENT_RELATIVE
    require(_absolute(baseline_dir) == _absolute(experiment), "fixed_confirmation_baseline_required")
    source_before = stable_source(repo)
    protected: dict[Path, str] = {}
    records: list[dict] = []

    historical_consumed = HISTORICAL_CONSUMED if _sources is None else _sources.dataset_count("historical_consumed")
    require(historical_consumed == HISTORICAL_CONSUMED, "source_description_historical_total_mismatch")
    expected_context = (
        CONFIRMATION_CONTEXT
        if _sources is None
        else _sources.semantic_sha256("runner_confirmation_context")
    )

    delivery_path = experiment / "final-build/delivery.json"
    delivery_raw, delivery_hash = _read(
        delivery_path,
        _source_file_pin(_sources, repo, delivery_path, DELIVERY_SHA256),
    )
    delivery = strict_json(delivery_raw)
    _validate_delivery_header(delivery, expected_context=expected_context)
    records.append({"role": "confirmation_delivery", "path": delivery_path.relative_to(repo).as_posix(), "sha256": delivery_hash, "bytes": len(delivery_raw)})
    protected[_absolute(delivery_path)] = delivery_hash

    # Recompute and validate the final source archive and the native-time archive.
    final_source = delivery.get("final_source", {})
    final_archive_path = experiment / "final-build" / "source-native.zip"
    final_list_path = experiment / "final-build" / "source-native-file-list.json"
    final_archive_pin = _source_archive_pin(
        _sources,
        "runner_final_archive",
        repo,
        final_archive_path,
        final_list_path,
        (FINAL_ARCHIVE_SHA256, FINAL_LIST_SHA256, FINAL_SOURCE, 511),
    )
    require(
        final_source.get("identity") == final_archive_pin[2]
        and final_source.get("file_count") == final_archive_pin[3]
        and final_source.get("archive_sha256") == final_archive_pin[0]
        and final_source.get("file_list_sha256") == final_archive_pin[1],
        "confirmation_final_source_anchor_mismatch",
    )
    final_audit = _verify_archive(
        experiment / "final-build", "source-native.zip", "source-native-file-list.json",
        *final_archive_pin,
    )
    native_time = delivery.get("native_time", {})
    native_archive_path = experiment / "source-native.zip"
    native_list_path = experiment / "source-native-file-list.json"
    native_archive_pin = _source_archive_pin(
        _sources,
        "runner_native_archive",
        repo,
        native_archive_path,
        native_list_path,
        (
            native_time.get("source_archive_sha256"),
            native_time.get("source_file_list_sha256"),
            native_time.get("source_identity"),
            native_time.get("source_file_count"),
        ),
    )
    native_audit = _verify_archive(
        experiment, "source-native.zip", "source-native-file-list.json",
        *native_archive_pin,
    )
    for role, path, sha in (
        ("final_source_archive", experiment / "final-build" / final_source["archive"], final_source["archive_sha256"]),
        ("final_source_file_list", experiment / "final-build" / final_source["file_list"], final_source["file_list_sha256"]),
        ("native_source_archive", experiment / "source-native.zip", native_time["source_archive_sha256"]),
        ("native_source_file_list", experiment / "source-native-file-list.json", native_time["source_file_list_sha256"]),
    ):
        item = _add_protected(protected, path, sha, repo=repo, _sources=_sources)
        records.append({"role": role, "path": path.relative_to(repo).as_posix(), "sha256": item["sha256"], "bytes": item["bytes"]})

    final_identity_path = experiment / "final-build/source-identity.json"
    identity_raw, identity_hash = _read_source(
        final_identity_path, repo, _sources, final_source.get("identity_file_sha256")
    )
    source_identity = strict_json(identity_raw)
    require(source_identity.get("identity") == final_source.get("identity"), "confirmation_source_identity_mismatch")
    protected[_absolute(final_identity_path)] = identity_hash
    records.append({"role": "final_source_identity", "path": final_identity_path.relative_to(repo).as_posix(), "sha256": identity_hash, "bytes": len(identity_raw)})

    # Verify both build records and the original native artifacts against their linked hashes.
    final_build = delivery.get("final_build", {})
    final_build_path = experiment / "final-build/build-record.json"
    final_build_raw, final_build_hash = _read_source(
        final_build_path, repo, _sources, final_build.get("record_sha256")
    )
    final_build_value = strict_json(final_build_raw)
    _signed(final_build_value, "build_record")
    require(
        final_build_value.get("identity") == final_build.get("identity")
        and final_build_value.get("status") == "recorded"
        and final_build_value.get("source_before") == final_build_value.get("source_after")
        and final_build_value.get("source_before", {}).get("identity") == final_source.get("identity")
        and final_build_value.get("reproducible_build_proven") is False,
        "confirmation_final_build_record_mismatch",
    )
    protected[_absolute(final_build_path)] = final_build_hash
    records.append({"role": "final_build_record", "path": final_build_path.relative_to(repo).as_posix(), "sha256": final_build_hash, "bytes": len(final_build_raw)})
    for role, artifact in final_build.get("artifacts", {}).items():
        relative = artifact.get("relative_path") if isinstance(artifact, dict) else None
        expected = artifact.get("sha256") if isinstance(artifact, dict) else None
        require(isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts, "confirmation_final_artifact_path_invalid")
        item = _add_protected(
            protected, experiment / "final-build" / relative, expected,
            repo=repo, _sources=_sources,
        )
        require(final_build_value.get("artifacts", {}).get(role) == item["sha256"], "confirmation_final_artifact_build_mismatch")
        records.append({"role": f"final_{role}_artifact", "path": (experiment / "final-build" / relative).relative_to(repo).as_posix(), "sha256": item["sha256"], "bytes": item["bytes"]})

    original_build_path = experiment / "build-record.json"
    original_build_raw, original_build_hash = _read_source(
        original_build_path, repo, _sources, native_time.get("build_record_sha256")
    )
    original_build = strict_json(original_build_raw)
    _signed(original_build, "build_record")
    require(
        original_build.get("identity") == native_time.get("build_record_identity")
        and original_build.get("status") == "recorded"
        and original_build.get("source_before", {}).get("identity") == native_time.get("source_identity")
        and original_build.get("source_after") == original_build.get("source_before")
        and original_build.get("reproducible_build_proven") is False,
        "confirmation_native_build_record_mismatch",
    )
    protected[_absolute(original_build_path)] = original_build_hash
    records.append({"role": "native_build_record", "path": original_build_path.relative_to(repo).as_posix(), "sha256": original_build_hash, "bytes": len(original_build_raw)})
    for role, expected in native_time.get("artifact_sha256", {}).items():
        path = experiment / "native-artifacts" / ("tenki-placement-probe.exe" if role == "runner" else "ygo-engine-worker.exe" if role == "worker" else "ygo-cli.exe")
        item = _add_protected(protected, path, expected, repo=repo, _sources=_sources)
        require(original_build.get("artifacts", {}).get(role) == expected, "confirmation_native_artifact_build_mismatch")
        records.append({"role": f"native_{role}_artifact", "path": path.relative_to(repo).as_posix(), "sha256": item["sha256"], "bytes": item["bytes"]})

    # The original stage-one request and input are bound by the frozen manifest and seal.
    research = experiment / "research"
    manifest_path = research / "manifest.json"
    manifest_raw, manifest_hash = _read_source(manifest_path, repo, _sources)
    manifest = strict_json(manifest_raw)
    _validate_manifest(manifest)
    require(
        manifest.get("context") == delivery.get("context") == expected_context,
        "confirmation_manifest_delivery_context_mismatch",
    )
    protected[_absolute(manifest_path)] = manifest_hash
    request_path = research / "stage-1-request.json"
    request_raw, request_hash = _read_source(request_path, repo, _sources)
    request = strict_json(request_raw)
    require(
        request == manifest.get("request")
        and digest(canonical(request)) == manifest.get("stage1_request_sha256")
        and manifest.get("stage1_request_sha256") == (
            "fac2455f2b2876bc9f28666252bdc8326dcd16cf95c63335230f2d49eac9a134"
            if _sources is None else _sources.semantic_sha256("runner_stage1_request")
        ),
        "confirmation_stage1_request_mismatch",
    )
    protected[_absolute(request_path)] = request_hash
    input_path = research / "stage-1-input.json"
    input_raw, input_hash = _read_source(input_path, repo, _sources)
    invocation = strict_json(input_raw)
    require(
        invocation.get("context") == manifest.get("context")
        and invocation.get("stage") == 1
        and invocation.get("batch_kind") == "tenki-placement-confirmation-v1"
        and invocation.get("request") == request
        and invocation.get("ledger") == str(research / "calls.jsonl")
        and invocation.get("output") == str(research / "stage-1.json")
        and invocation.get("expected_identity", {}).get("identity") == native_time.get("ordinary_asset_identity"),
        "confirmation_stage1_input_binding_mismatch",
    )
    protected[_absolute(input_path)] = input_hash
    identity_path = experiment / "identity.json"
    identity_raw, identity_hash = _read_source(
        identity_path, repo, _sources, manifest.get("input_sha256", {}).get("identity")
    )
    identity_file = strict_json(identity_raw)
    _validate_identity_binding(manifest, invocation, identity_file, identity_hash)
    protected[_absolute(identity_path)] = identity_hash
    records.append({
        "role": "workspace_identity",
        "path": identity_path.relative_to(repo).as_posix(),
        "sha256": identity_hash,
        "bytes": len(identity_raw),
    })

    window_path = experiment / "window-start.json"
    window_raw, window_hash = _read_source(
        window_path, repo, _sources, manifest.get("input_sha256", {}).get("window_start")
    )
    window = strict_json(window_raw)
    _validate_window_binding(manifest, window)
    protected[_absolute(window_path)] = window_hash
    records.append({
        "role": "window_start",
        "path": window_path.relative_to(repo).as_posix(),
        "sha256": window_hash,
        "bytes": len(window_raw),
    })
    seal_path = research / "stage-1-input-seal.json"
    seal_raw, seal_hash = _read_source(seal_path, repo, _sources)
    seal = strict_json(seal_raw)
    require(
        seal == {
            "schema_version": 1,
            "kind": "tenki_placement_confirmation_stage_input_seal",
            "context": manifest["context"],
            "stage": 1,
            "input_sha256": input_hash,
        },
        "confirmation_stage1_input_seal_mismatch",
    )
    protected[_absolute(seal_path)] = seal_hash
    require(
        manifest.get("input_sha256", {}).get("runner") == native_time.get("artifact_sha256", {}).get("runner"),
        "confirmation_manifest_input_hash_mismatch",
    )
    records.extend([
        {"role": "confirmation_manifest", "path": manifest_path.relative_to(repo).as_posix(), "sha256": manifest_hash, "bytes": len(manifest_raw)},
        {"role": "stage1_request", "path": request_path.relative_to(repo).as_posix(), "sha256": request_hash, "bytes": len(request_raw)},
        {"role": "stage1_input", "path": input_path.relative_to(repo).as_posix(), "sha256": input_hash, "bytes": len(input_raw)},
        {"role": "stage1_input_seal", "path": seal_path.relative_to(repo).as_posix(), "sha256": seal_hash, "bytes": len(seal_raw)},
    ])

    report_paths = (
        ("prepared", research / "prepared.json"),
        ("stage1_report", research / "stage-1-report.json"),
        ("summary", research / "summary.json"),
        ("verification", research / "verification.json"),
    )
    for role, path in report_paths:
        expected_hash = _delivery_report_hash(delivery, role)
        require(isinstance(expected_hash, str), "confirmation_delivery_report_hash_missing")
        raw, found = _read_source(path, repo, _sources, expected_hash)
        value = strict_json(raw)
        require(value.get("context") == manifest["context"], f"confirmation_{role}_context_mismatch")
        protected[_absolute(path)] = found
        records.append({"role": role, "path": path.relative_to(repo).as_posix(), "sha256": found, "bytes": len(raw)})
    prepared = strict_json(_safe_file(research / "prepared.json").read_bytes())
    stage_report = strict_json(_safe_file(research / "stage-1-report.json").read_bytes())
    summary = strict_json(_safe_file(research / "summary.json").read_bytes())
    verification = strict_json(_safe_file(research / "verification.json").read_bytes())
    require(
        prepared.get("prepared") is True and prepared.get("native_calls") == 0
        and prepared.get("stage1_input_sha256") == input_hash
        and stage_report.get("successful") is False and stage_report.get("diagnostic") == "runner_timeout"
        and stage_report.get("receipt_sha256") is None
        and summary.get("successful") is False and summary.get("diagnostic") == "runner_timeout"
        and verification.get("valid") is False and verification.get("diagnostic") == "incomplete_stage_receipts"
        and delivery.get("reports", {}).get("stage1_report_sha256") == _sha(_safe_file(research / "stage-1-report.json").read_bytes())
        and delivery.get("reports", {}).get("summary_sha256") == _sha(_safe_file(research / "summary.json").read_bytes())
        and delivery.get("reports", {}).get("verification_sha256") == _sha(_safe_file(research / "verification.json").read_bytes()),
        "confirmation_failure_reports_mismatch",
    )

    # Preserve and verify the original process diagnostic and all eight ledgers.
    diagnostic_root_record_path = experiment / "stage-1-process-diagnostic.json"
    diag_root_raw, diag_root_hash = _read_source(diagnostic_root_record_path, repo, _sources)
    diag_root = strict_json(diag_root_raw)
    from ygo_eval.native_tenki_placement_confirmation import _diagnostic_hash
    require(
        diag_root.get("status") == "timeout"
        and diag_root.get("error_code") == "runner_timeout"
        and diag_root.get("stdout", {}).get("sha256") == delivery.get("native_outcome", {}).get("stdout_sha256")
        and diag_root.get("stderr", {}).get("sha256") == delivery.get("native_outcome", {}).get("stderr_sha256")
        and _diagnostic_hash(experiment, diag_root) == stage_report.get("diagnostic_sha256"),
        "confirmation_original_process_diagnostic_mismatch",
    )
    protected[_absolute(diagnostic_root_record_path)] = diag_root_hash
    records.append({"role": "original_process_diagnostic", "path": diagnostic_root_record_path.relative_to(repo).as_posix(), "sha256": diag_root_hash, "bytes": len(diag_root_raw)})

    historical_ledger_hashes = _historical_ledger_hashes(_sources)
    require(len(historical_ledger_hashes) == len(OLD_LEDGER_CONTRACTS), "historical_ledger_count_mismatch")
    for contract, expected_hash in zip(OLD_LEDGER_CONTRACTS, historical_ledger_hashes):
        path = repo / contract[1]
        item = _add_protected(protected, path, expected_hash)
        records.append({"role": f"historical_ledger_{contract[0]}", "path": path.relative_to(repo).as_posix(), "sha256": item["sha256"], "bytes": item["bytes"]})
    current_ledger_protected, current_ledger = _verify_eighth_ledger(
        experiment, _sources=_sources, repo=repo
    )
    protected.update(current_ledger_protected)
    for path, value in current_ledger_protected.items():
        records.append({"role": "confirmation_ledger" if path.name == "calls.jsonl" else "confirmation_ledger_checkpoint", "path": path.relative_to(repo).as_posix(), "sha256": value, "bytes": path.stat().st_size})
    require(
        len(OLD_LEDGER_CONTRACTS) + 1 == 8
        and delivery.get("historical_ledgers") and len(delivery["historical_ledgers"]) == 7
        and delivery.get("new_ledger", {}).get("sha256") == current_ledger["sha256"]
        and delivery.get("new_ledger", {}).get("record_count") == current_ledger["records"]
        and delivery.get("new_ledger", {}).get("consumed") == current_ledger["consumed"] == 0
        and delivery.get("new_ledger", {}).get("unknown") == current_ledger["unknown"] == 0,
        "eight_ledger_evidence_mismatch",
    )

    # Also bind the prior diagnostics chain and its protected bytes, without starting any saved runner.
    from ygo_eval.native_tenki_placement_confirmation import _verify_history
    historical_audit, historical_protected, historical_sources = _verify_history(
        repo, repo / DIAGNOSTICS_RELATIVE, protection_scope,
        _sources=None if _sources is None else _sources.child("placement_confirmation"),
    )
    require(historical_audit.get("old_consumed") == HISTORICAL_CONSUMED and historical_audit.get("unknown") == HISTORICAL_UNKNOWN, "historical_chain_mismatch")
    require(
        sum(item.get("stats", {}).get("consumed", -1) for item in historical_audit.get("ledgers", [])) == HISTORICAL_CONSUMED
        and sum(item.get("stats", {}).get("unknown", -1) for item in historical_audit.get("ledgers", [])) == HISTORICAL_UNKNOWN,
        "historical_consumption_total_mismatch",
    )
    for path, found in historical_protected.items():
        protected[path] = found
    source_after = stable_source(repo)
    require(source_before == source_after, "workspace_source_changed_during_baseline_audit")
    _verify_protected(protected)
    return {
        "delivery_sha256": delivery_hash,
        "context": delivery["context"],
        "source_identity": final_source["identity"],
        "workspace_identity": source_after["identity"],
        "protected": protected,
        "input_records": records,
        "historical_ledgers": 7,
        "current_ledger": current_ledger,
        "historical_audit_sha256": historical_audit.get("input_set_sha256"),
        "prior_history_source_identity": historical_sources.get("source_identity"),
        "request": request,
        "request_sha256": manifest["stage1_request_sha256"],
        "input_path": input_path,
        "input_sha256": input_hash,
        "expected_identity": invocation["expected_identity"],
        "stage1_report_diagnostic": stage_report["diagnostic"],
        "source_archives": [
            {"role": "native_time", "sha256": native_audit["archive_sha256"], "file_list_sha256": native_audit["file_list_sha256"], "file_count": native_audit["file_count"]},
            {"role": "final", "sha256": final_audit["archive_sha256"], "file_list_sha256": final_audit["file_list_sha256"], "file_count": final_audit["file_count"]},
        ],
    }


def _verify_protected(protected: dict[Path, str]) -> bool:
    for path, expected in protected.items():
        _read(path, expected)
    return True


def _capture_process_files(
    *,
    output_root: Path,
    repo: Path,
    process_record: dict,
    protected: dict[Path, str],
) -> tuple[dict, list[dict]]:
    """Re-open the just-written raw sidecars, check their metadata, and pin them."""
    records = []
    saved = {}
    for role, relative_path, expected_hash, expected_bytes in (
        ("runner_process_metadata", process_record.get("metadata_path"), None, None),
        ("runner_stdout", process_record.get("stdout", {}).get("path"), process_record.get("stdout", {}).get("sha256"), process_record.get("stdout", {}).get("bytes")),
        ("runner_stderr", process_record.get("stderr", {}).get("path"), process_record.get("stderr", {}).get("sha256"), process_record.get("stderr", {}).get("bytes")),
    ):
        require(
            isinstance(relative_path, str)
            and not Path(relative_path).is_absolute()
            and "\\" not in relative_path
            and ":" not in relative_path
            and ".." not in Path(relative_path).parts
            and relative_path.startswith("process-diagnostics/"),
            "runner_diagnostic_path_invalid",
        )
        path = safe_path(output_root / relative_path)
        raw, found = _read(path, expected_hash)
        require(expected_bytes is None or len(raw) == expected_bytes, "runner_diagnostic_length_mismatch")
        if role == "runner_process_metadata":
            metadata = strict_json(raw)
            require(metadata == process_record, "runner_diagnostic_metadata_mismatch")
            saved["metadata_sha256"] = found
            saved["metadata_bytes"] = len(raw)
        absolute = _absolute(path)
        previous = protected.get(absolute)
        require(previous is None or previous == found, "protected_input_binding_conflict")
        protected[absolute] = found
        records.append({
            "role": role,
            "path": path.relative_to(repo).as_posix(),
            "sha256": found,
            "bytes": len(raw),
        })
        saved[role] = {"path": relative_path, "sha256": found, "bytes": len(raw), "raw": raw}
    return saved, records


def _verify_new_runner(args: argparse.Namespace, repo: Path) -> dict:
    root = repo / OUTPUT_RELATIVE
    expected_runner = root / "native-artifacts/tenki-placement-probe.exe"
    expected_build = root / "build-record.json"
    runner = _absolute(args.runner)
    build_path = _absolute(args.build_record)
    require(runner == expected_runner and build_path == expected_build, "fixed_audit_build_paths_required")
    runner_raw, runner_sha = _read(runner)
    build_raw, build_sha = _read(build_path)
    build = strict_json(build_raw)
    _signed(build, "build_record")
    source = stable_source(repo)
    require(
        build.get("status") == "recorded"
        and build.get("source_before") == source
        and build.get("source_after") == source
        and build.get("reproducible_build_proven") is False
        and build.get("artifacts", {}).get("runner") == runner_sha,
        "audit_runner_build_binding_mismatch",
    )
    return {
        "runner_sha256": runner_sha,
        "runner_bytes": len(runner_raw),
        "build_record_sha256": build_sha,
        "build_record_identity": build["identity"],
        "source_identity": source["identity"],
        "source_file_count": len(source["files"]),
    }


def _trace_summary(stderr: bytes) -> tuple[list[dict], str | None]:
    if not stderr:
        return [], "runner_trace_missing"
    summary = []
    expected = (
        ("input_validation", "start"),
        ("input_validation", "end"),
        ("shared_preflight", "start"),
        ("shared_preflight", "end"),
    )
    try:
        lines = stderr.decode("utf-8").splitlines()
        require(bool(lines), "runner_trace_missing")
        require(len(lines) <= len(expected), "runner_trace_invalid")
        for index, line in enumerate(lines):
            item = strict_json(line.encode("utf-8"))
            require(isinstance(item, dict), "runner_trace_event_invalid")
            phase = item.get("phase")
            event = item.get("event")
            require((phase, event) == expected[index], "runner_trace_order_invalid")
            if event == "start":
                require(set(item) == {"phase", "event"}, "runner_trace_event_invalid")
                clean = {"phase": phase, "event": event}
            else:
                require(set(item) == {"phase", "event", "elapsed_ns"}, "runner_trace_event_invalid")
                elapsed = item.get("elapsed_ns")
                require(type(elapsed) is int and elapsed >= 0, "runner_trace_duration_invalid")
                clean = {"phase": phase, "event": event, "elapsed_ns": elapsed}
            summary.append(clean)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return [], "runner_trace_invalid"
    if len(summary) != len(expected):
        return summary, "runner_trace_incomplete"
    return summary, None


def _output_matches(value: Any, baseline: dict) -> bool:
    return (
        isinstance(value, dict)
        and value.get("preflight_passed") is True
        and type(value.get("native_calls")) is int
        and value.get("native_calls") == 0
        and type(value.get("stage")) is int
        and value.get("stage") == 1
        and value.get("context") == baseline["context"]
        and value.get("identity_sha256") == baseline["expected_identity"].get("identity")
    )


def _parsed_result(value: Any, context: str, expected_identity: str) -> dict:
    baseline = {"context": context, "expected_identity": {"identity": expected_identity}}
    return {
        "preflight_passed": value.get("preflight_passed") is True if isinstance(value, dict) else False,
        "native_calls": value.get("native_calls") if isinstance(value, dict) else None,
        "stage": value.get("stage") if isinstance(value, dict) else None,
        "context": value.get("context") if isinstance(value, dict) else None,
        "identity_sha256": value.get("identity_sha256") if isinstance(value, dict) else None,
        "matches_expected": _output_matches(value, baseline),
    }


def _validate_process_artifacts(value: dict, repo: Path, artifact_root: Path) -> None:
    process = value.get("process")
    require(isinstance(process, dict), "audit_passed_process_missing")
    require(
        process.get("mode") == "preflight_only"
        and process.get("runner_role") == RUNNER_ROLE
        and process.get("status") == "completed"
        and process.get("return_code") == 0
        and process.get("error_code") is None,
        "audit_passed_process_invalid",
    )
    sidecars = {}
    for role, record in (
        ("metadata", {
            "path": process.get("metadata_path"),
            "sha256": process.get("metadata_sha256"),
            "bytes": process.get("metadata_bytes"),
        }),
        ("stdout", process.get("stdout")),
        ("stderr", process.get("stderr")),
    ):
        require(isinstance(record, dict), "audit_process_sidecar_missing")
        relative = record.get("path")
        require(
            isinstance(relative, str)
            and not Path(relative).is_absolute()
            and "\\" not in relative
            and ":" not in relative
            and ".." not in Path(relative).parts
            and relative.startswith("process-diagnostics/"),
            "audit_process_sidecar_path_invalid",
        )
        path = safe_path(artifact_root / relative)
        raw, found = _read(path, record.get("sha256"))
        require(len(raw) == record.get("bytes"), "audit_process_sidecar_length_mismatch")
        sidecars[role] = raw
    metadata = strict_json(sidecars["metadata"])
    require(
        metadata == {
            "mode": process["mode"],
            "runner_role": process["runner_role"],
            "status": process["status"],
            "return_code": process["return_code"],
            "error_code": process["error_code"],
            "stdout": process["stdout"],
            "stderr": process["stderr"],
            "metadata_path": process["metadata_path"],
        },
        "audit_process_metadata_binding_invalid",
    )
    trace, trace_error = _trace_summary(sidecars["stderr"])
    require(trace == process.get("trace") and trace_error is None, "audit_process_trace_binding_invalid")
    parsed_output = strict_json(sidecars["stdout"])
    input_record = next(
        (record for record in value.get("inputs", []) if record.get("role") == "stage1_input"),
        None,
    )
    require(isinstance(input_record, dict), "audit_stage1_input_record_missing")
    input_path = safe_path(repo / input_record["path"])
    input_raw, input_hash = _read(input_path, input_record.get("sha256"))
    require(len(input_raw) == input_record.get("bytes"), "audit_stage1_input_length_invalid")
    invocation = strict_json(input_raw)
    summary = _parsed_result(
        parsed_output,
        invocation.get("context"),
        invocation.get("expected_identity", {}).get("identity"),
    )
    require(process.get("parsed_result") == summary and summary["matches_expected"], "audit_parsed_result_binding_invalid")


def validate_report(
    value: dict,
    repo: Path | None = None,
    artifact_root: Path | None = None,
) -> bool:
    require(isinstance(value, dict) and value.get("schema_version") == 1, "audit_report_schema_version_invalid")
    require(value.get("kind") == "tenki_runner_offline_audit", "audit_report_kind_invalid")
    require(value.get("native_calls") == 0 and value.get("execution_ready") is False, "audit_report_execution_qualification_invalid")
    require(all(value.get(key) is False for key in FLAGS), "research_qualification_must_remain_false")
    require(value.get("status") in {"passed", "failed", "incomplete"}, "audit_report_status_invalid")
    require(isinstance(value.get("checks"), dict) and isinstance(value.get("inputs"), list), "audit_report_shape_invalid")
    expected_checks = {
        "delivery_and_history", "source_archives", "frozen_request_and_seal",
        "eight_ledgers", "isolated_runner_build", "read_only_preflight",
        "input_stability", "trace",
    }
    require(
        set(value["checks"]) == expected_checks
        and all(state in {"not_run", "passed", "failed"} for state in value["checks"].values()),
        "audit_report_checks_invalid",
    )
    require(isinstance(value.get("source_archives"), list), "audit_report_archives_invalid")
    for item in value["inputs"]:
        path = item.get("path") if isinstance(item, dict) else None
        require(
            isinstance(path, str)
            and not Path(path).is_absolute()
            and "\\" not in path
            and ":" not in path
            and ".." not in Path(path).parts,
            "audit_report_input_path_invalid",
        )
    require(value.get("original_native_diagnostic") == "runner_timeout", "audit_original_native_diagnostic_invalid")
    require(value.get("source", {}).get("runner_role") == RUNNER_ROLE, "audit_report_runner_role_invalid")
    require(value.get("process") is None or isinstance(value.get("process"), dict), "audit_report_process_invalid")
    require(value.get("diagnostic") is None or re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value["diagnostic"]) is not None, "audit_report_diagnostic_invalid")
    if value.get("status") == "passed":
        require(
            value.get("diagnostic") is None
            and all(state == "passed" for state in value["checks"].values())
            and len(value["inputs"]) >= 1
            and {item.get("role") for item in value.get("source_archives", [])} == {"native_time", "final"}
            and isinstance(value.get("process"), dict),
            "audit_report_success_claim_invalid",
        )
        require(repo is not None, "passed_report_requires_artifact_validation")
        _validate_process_artifacts(value, Path(repo).absolute(), _absolute(artifact_root or Path(repo).absolute() / OUTPUT_RELATIVE))
    if repo is not None:
        schema_path = Path(repo).absolute() / "schemas/tenki-runner-offline-audit-v1.schema.json"
        require(schema_path.is_file(), "audit_report_schema_missing")
    return True


def _run_audit(
    *,
    repo: Path,
    baseline_dir: Path,
    runner: Path,
    build_record: Path,
    output_root: Path,
    output_path: Path,
    process_runner: Callable[..., Any] | None = None,
    baseline_verifier: Callable[[Path, Path], dict] | None = None,
) -> dict:
    from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic, DiagnosticPersistenceError

    started = time.monotonic()
    checks = {
        "delivery_and_history": "not_run",
        "source_archives": "not_run",
        "frozen_request_and_seal": "not_run",
        "eight_ledgers": "not_run",
        "isolated_runner_build": "not_run",
        "read_only_preflight": "not_run",
        "input_stability": "not_run",
        "trace": "not_run",
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "tenki_runner_offline_audit",
        "status": "incomplete",
        "baseline_anchor_sha256": DELIVERY_SHA256,
        "native_calls": 0,
        "execution_ready": False,
        "original_native_diagnostic": "runner_timeout",
        "checks": checks,
        "inputs": [],
        "source_archives": [],
        "source": {"runner_role": RUNNER_ROLE},
        "process": None,
        "diagnostic": None,
        **FLAGS,
    }
    protected: dict[Path, str] = {}
    source_before = None
    baseline = None
    process_record = None
    current = "delivery_and_history"
    try:
        source_before = stable_source(repo)
        verify = baseline_verifier or _verify_confirmation_baseline
        baseline = verify(repo, baseline_dir)
        protected.update(baseline["protected"])
        report["inputs"] = baseline["input_records"]
        report["source_archives"] = baseline["source_archives"]
        report["source"].update({
            "workspace_identity": source_before["identity"],
            "workspace_file_count": len(source_before["files"]),
            "baseline_source_identity": baseline["source_identity"],
            "historical_consumed": HISTORICAL_CONSUMED,
            "historical_unknown": HISTORICAL_UNKNOWN,
            "ledger_count": 8,
            "confirmation_consumed": 0,
            "runner_role": RUNNER_ROLE,
        })
        checks["delivery_and_history"] = "passed"
        checks["source_archives"] = "passed"
        checks["frozen_request_and_seal"] = "passed"
        checks["eight_ledgers"] = "passed"
        current = "isolated_runner_build"
        build = _verify_new_runner(argparse.Namespace(runner=runner, build_record=build_record), repo)
        report["source"].update(build)
        for role, path, sha, size in (
            ("isolated_runner", runner, build["runner_sha256"], build["runner_bytes"]),
            ("isolated_build_record", build_record, build["build_record_sha256"], build_record.stat().st_size),
        ):
            _read(path, sha)
            protected[_absolute(path)] = sha
            report["inputs"].append({
                "role": role,
                "path": path.relative_to(repo).as_posix(),
                "sha256": sha,
                "bytes": size,
            })
        checks["isolated_runner_build"] = "passed"

        _verify_protected(protected)
        before_hashes = dict(protected)
        current = "read_only_preflight"
        input_path = baseline["input_path"]
        invocation_hash = _sha(_safe_file(input_path).read_bytes())
        require(invocation_hash == baseline["input_sha256"], "stage1_input_changed_before_preflight")
        command = [
            str(_absolute(runner)), str(_absolute(input_path)),
            "--input-sha", invocation_hash,
            "--preflight-only", "--trace-stderr",
        ]
        diagnostic_root = output_root
        process_record, completed = capture_process_diagnostic(
            command,
            repo,
            diagnostic_root,
            mode="preflight_only",
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
            runner=process_runner,
            runner_role=RUNNER_ROLE,
        )
        # Raw stdout/stderr and metadata have been exclusively saved by the helper before parsing.
        captured, diagnostic_inputs = _capture_process_files(
            output_root=diagnostic_root,
            repo=repo,
            process_record=process_record,
            protected=protected,
        )
        report["inputs"].extend(diagnostic_inputs)
        report["process"] = {
            "mode": "preflight_only",
            "runner_role": RUNNER_ROLE,
            "status": process_record["status"],
            "return_code": process_record["return_code"],
            "error_code": process_record["error_code"],
            "metadata_path": process_record["metadata_path"],
            "metadata_sha256": captured["metadata_sha256"],
            "metadata_bytes": captured["metadata_bytes"],
            "stdout": process_record["stdout"],
            "stderr": process_record["stderr"],
            "timeout_seconds": PREFLIGHT_TIMEOUT_SECONDS,
        }
        stdout = _safe_file(diagnostic_root / process_record["stdout"]["path"]).read_bytes()
        stderr = _safe_file(diagnostic_root / process_record["stderr"]["path"]).read_bytes()
        trace, trace_error = _trace_summary(stderr)
        report["process"]["trace"] = trace
        checks["trace"] = "passed" if trace_error is None else "failed"
        if process_record["status"] != "completed":
            report["diagnostic"] = process_record.get("error_code") or "runner_process_failed"
        elif completed is None or completed.returncode != 0:
            report["diagnostic"] = "runner_nonzero_exit"
        else:
            try:
                parsed = strict_json(stdout)
            except (ValueError, TypeError, UnicodeDecodeError):
                parsed = None
                report["diagnostic"] = "runner_invalid_json"
            if parsed is not None:
                report["process"]["parsed_result"] = _parsed_result(
                    parsed, baseline["context"], baseline["expected_identity"].get("identity")
                )
                if not _output_matches(parsed, baseline):
                    report["diagnostic"] = "runner_preflight_result_mismatch"
                elif trace_error:
                    report["diagnostic"] = trace_error
                else:
                    checks["read_only_preflight"] = "passed"

        current = "input_stability"
        _verify_protected(before_hashes)
        _verify_protected(protected)
        require(_sha(_safe_file(input_path).read_bytes()) == invocation_hash, "stage1_input_changed_during_preflight")
        require(stable_source(repo) == source_before, "workspace_source_changed_during_preflight")
        checks["input_stability"] = "passed"
        if report["diagnostic"] is None and all(state == "passed" for state in checks.values()):
            report["status"] = "passed"
        else:
            report["status"] = "failed"
            if report["diagnostic"] is None:
                report["diagnostic"] = "offline_audit_checks_incomplete"
    except DiagnosticPersistenceError:
        report["status"] = "failed"
        report["diagnostic"] = "diagnostic_persistence_failed"
    except (ValueError, OSError, KeyError, TypeError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        report["status"] = "failed"
        report["diagnostic"] = _safe_error(error)
        checks[current] = "failed"
        # Before any worker process is permitted, a failure can stop cleanly with no process record.
    except Exception:
        # Do not serialize exception text: library errors can include user-specific absolute paths.
        report["status"] = "failed"
        report["diagnostic"] = "offline_audit_unexpected_failure"
        checks[current] = "failed"
    report["elapsed_seconds"] = round(time.monotonic() - started, 6)
    report["input_set_sha256"] = digest(canonical([
        {"path": path.relative_to(repo).as_posix(), "sha256": value}
        for path, value in sorted(protected.items(), key=lambda pair: pair[0].as_posix())
        if path.is_relative_to(repo)
    ])) if protected else None
    validate_report(report, repo=repo, artifact_root=output_root)
    immutable_write(output_path, report)
    return report


def run_audit(args: argparse.Namespace, repo: Path | None = None, process_runner: Callable[..., Any] | None = None) -> dict:
    """Run the fixed, isolated, zero-native-call audit and save its report exclusively."""
    repo = _absolute(repo or Path(__file__).resolve().parents[2])
    output_root = repo / OUTPUT_RELATIVE
    baseline = _absolute(args.baseline_dir)
    runner = _absolute(args.runner)
    build_record = _absolute(args.build_record)
    output_path = _absolute(args.output)
    require(baseline == _absolute(repo / EXPERIMENT_RELATIVE), "fixed_confirmation_baseline_required")
    require(runner == _absolute(output_root / "native-artifacts/tenki-placement-probe.exe"), "fixed_audit_runner_path_required")
    require(build_record == _absolute(output_root / "build-record.json"), "fixed_audit_build_record_path_required")
    require(output_path == _absolute(output_root / "audit-report.json"), "fixed_audit_output_path_required")
    safe_path(output_root, file=False)
    checked_output(repo, output_path)
    require(not output_path.exists() and not output_path.is_symlink(), "audit_output_already_exists")
    return _run_audit(
        repo=repo,
        baseline_dir=baseline,
        runner=runner,
        build_record=build_record,
        output_root=output_root,
        output_path=output_path,
        process_runner=process_runner,
    )
