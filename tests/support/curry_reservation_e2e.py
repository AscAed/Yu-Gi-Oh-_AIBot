"""Independent synthetic source tree for the reservation public-CLI tests."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import zipfile
import zipfile

from ygo_eval import curry_consumption_reservation as reservation
from ygo_eval import curry_input_recovery_audit as recovery
from tests.support.curry_recovery_e2e import (
    build_synthetic_recovery_tree,
    synthetic_source_identity,
    synthetic_source_sampler,
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _pretty(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _forbid_native_activity():
    from contextlib import ExitStack, contextmanager
    import ctypes
    import subprocess
    from unittest.mock import patch

    @contextmanager
    def guard():
        def denied(*_args, **_kwargs):
            raise AssertionError("native_activity_forbidden_in_reservation_test")

        with ExitStack() as stack:
            stack.enter_context(patch.object(subprocess, "Popen", side_effect=denied))
            for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
                if hasattr(ctypes, name):
                    stack.enter_context(patch.object(ctypes, name, side_effect=denied))
            yield
    return guard()


def _write(root: Path, relative: str | Path, raw: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def build_synthetic_reservation_tree(root: Path):
    """Build a valid synthetic old audit, history pins, delivery, and profile."""
    from types import SimpleNamespace

    fixture = build_synthetic_recovery_tree(root / "recovery-source")
    repo = fixture.repo
    v2_relative = Path(fixture.sources.output_relative_v2) / "audit-report.json"
    v2_output = repo / v2_relative
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        with _forbid_native_activity(), synthetic_source_sampler():
            v2_report = recovery.audit_to_output(
                SimpleNamespace(
                    baseline_dir=fixture.baseline,
                    output=v2_output,
                    report_version=2,
                ),
                repo=repo,
                _sources=fixture.sources,
            )
    finally:
        os.chdir(old_cwd)

    v2_raw = v2_output.read_bytes()
    evidence_inventory = json.loads((fixture.baseline / "evidence-inventory.json").read_bytes())
    confirmation_relative = Path(fixture.sources.baseline_relative)
    prefix = confirmation_relative.as_posix() + "/"
    confirmation_manifest = json.loads(
        (repo / confirmation_relative / "research/manifest.json").read_bytes()
    )
    summary_relative = confirmation_relative / "research/summary.json"
    summary_raw = _pretty({
        "kind": "native_curry_option_confirmation_summary",
        "scope": "curry-option-confirmation-v1",
        "context": confirmation_manifest["context"],
        "successful": False,
        "new_consumed": None,
        "cumulative_consumed": None,
        "unknown": None,
    })
    _write(repo, summary_relative, summary_raw)
    v2_report["inputs"].append({
        "role": "confirmation_summary",
        "path": summary_relative.as_posix(),
        "sha256": _sha(summary_raw),
        "bytes": len(summary_raw),
    })
    confirmation_rows = [
        row for row in v2_report["inputs"] if row["path"].startswith(prefix)
    ]
    confirmation_paths = {row["path"][len(prefix):] for row in confirmation_rows}
    # Preserve the two authenticated archive pairs even when an earlier
    # synthetic V2 failure report stopped before publishing their input rows.
    confirmation_paths.update({
        "source-native.zip",
        "source-native-file-list.json",
        "final-build/source-native.zip",
        "final-build/source-native-file-list.json",
    })
    confirmation_root = repo / confirmation_relative
    # The old audit fixture carries three non-inventory build helpers which are
    # intentionally outside its authenticated file inventory. The reservation
    # profile models the authenticated input set, so leave exactly that set.
    for path in tuple(confirmation_root.rglob("*")):
        if path.is_file() and path.relative_to(confirmation_root).as_posix() not in confirmation_paths:
            path.unlink()

    ledger_rows = [
        row for row in v2_report["inputs"]
        if "/research/" in row["path"] and row["path"].endswith("calls.jsonl")
    ]
    if len(ledger_rows) != 8:
        raise AssertionError(f"expected eight synthetic call ledgers, found {len(ledger_rows)}")
    extra_ledger_relative = Path("data/runtime/synthetic-reservation-history/research/calls.jsonl")
    extra_ledger_raw = b"synthetic ninth certified ledger pin\n"
    _write(repo, extra_ledger_relative, extra_ledger_raw)
    v2_report["inputs"].append({
        "role": "historical_material_synthetic_reservation_ninth_ledger",
        "path": extra_ledger_relative.as_posix(),
        "sha256": _sha(extra_ledger_raw),
        "bytes": len(extra_ledger_raw),
    })
    v2_raw = _canonical(v2_report)
    v2_output.write_bytes(v2_raw)
    v2_sha = _sha(v2_raw)
    v2_acceptance = next(
        row for row in v2_report["inputs"]
        if row["role"] == "confirmation_acceptance"
    )

    baseline_relative = Path("data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24")
    output_relative = Path("data/runtime/p1-curry-consumption-reservation-offline-2026-10-24")
    baseline = repo / baseline_relative
    (baseline / "final-build").mkdir(parents=True, exist_ok=False)
    acceptance = {
        "schema_version": 1,
        "kind": "curry_recovery_synthetic_e2e_acceptance",
        "native_calls": 0,
        "execution_ready": False,
        "public_audit_report": {"sha256": v2_sha},
        "historical_boundary": {
            "certified_consumed": 32,
            "certified_ledger_count": 9,
            "certified_unknown": 0,
            "curry_confirmation_cumulative_consumed": None,
            "curry_confirmation_new_consumed": None,
            "curry_confirmation_unknown": None,
            "historical_acceptance_sha256": v2_acceptance["sha256"],
            "historical_v2_report_sha256": v2_sha,
            "sealed_unconsumed_slots": 7,
        },
        "qualifications": dict(reservation._QUALIFICATIONS),
    }
    review = {
        "schema_version": 1,
        "kind": "curry_recovery_synthetic_e2e_independent_review",
        "result": "passed",
        "native_calls": 0,
        "real_audit_run": False,
        "public_cli_bypass_found": False,
    }
    protected = {
        "schema_version": 1,
        "kind": "curry_recovery_synthetic_e2e_protected_material_check",
        "mode": "read_only_hash_check_only",
        "native_calls": 0,
        "historical_ledger_count": 9,
        "historical_consumed": 32,
        "historical_unknown": 0,
        "old_curry_confirmation_ledger": {
            "consumption": None,
            "path": (confirmation_relative / "research/calls.jsonl").as_posix(),
            "state": "still_absent",
        },
        "authenticated_historical_ledgers": [
            {
                "path": row["path"],
                "expected_sha256": row["sha256"],
                "actual_sha256": row["sha256"],
                "passed": True,
            }
            for row in ledger_rows + [{
                "path": extra_ledger_relative.as_posix(),
                "sha256": _sha(extra_ledger_raw),
            }]
        ],
    }
    public_report = json.loads(v2_raw)
    fixed_files = {
        "acceptance.json": _pretty(acceptance),
        "independent-review.json": _pretty(review),
        "protected-material-check.json": _pretty(protected),
        "synthetic-success-report.json": v2_raw,
    }
    hashes = {name: _sha(raw) for name, raw in fixed_files.items()}
    for name, raw in fixed_files.items():
        _write(baseline, name, raw)

    test_log_bytes = {
        "pytest-files.txt": b"synthetic explicit test file list\n",
        "pytest-full-rerun.log": b"synthetic pytest rerun evidence\n",
        "pytest-full.log": b"synthetic pytest evidence\n",
    }
    test_log_hashes = tuple((name, _sha(raw)) for name, raw in sorted(test_log_bytes.items()))
    for name, raw in test_log_bytes.items():
        _write(baseline, name, raw)

    source_head = "0123456789abcdef0123456789abcdef01234567"
    source_members = {
        "synthetic/module.py": b"# inert synthetic module\n",
        "synthetic/schema.json": b"{\"synthetic\":true}\n",
        "synthetic/source.txt": b"reservation source fixture\n",
    }
    source_hashes = {name: _sha(raw) for name, raw in sorted(source_members.items())}
    source_identity = _sha(_canonical({"head": source_head, "files": source_hashes}))
    source_list = {
        "schema_version": 1,
        "kind": "curry_synthetic_e2e_final_source_file_list",
        "file_count": len(source_members),
        "present_file_count": len(source_members),
        "source_identity": source_identity,
        "entries": [
            {"path": name, "sha256": source_hashes[name], "state": "present"}
            for name in sorted(source_members)
        ],
    }
    source_list_raw = _pretty(source_list)
    source_zip_buffer = io.BytesIO()
    with zipfile.ZipFile(source_zip_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(source_members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    source_zip_raw = source_zip_buffer.getvalue()
    source_archive_sha = _sha(source_zip_raw)
    source_list_sha = _sha(source_list_raw)
    _write(baseline, "final-build/source-native.zip", source_zip_raw)
    _write(baseline, "final-build/source-file-list.json", source_list_raw)

    delivery = {
        "schema_version": 1,
        "kind": "curry_recovery_synthetic_e2e_final_delivery",
        "source_identity": source_identity,
        "source_file_count": len(source_members),
        "native_calls": 0,
        "execution_ready": False,
        "qualifications": dict(reservation._QUALIFICATIONS),
        "acceptance_sha256": hashes["acceptance.json"],
        "independent_review_sha256": hashes["independent-review.json"],
        "protected_material_check_sha256": hashes["protected-material-check.json"],
        "synthetic_report_sha256": hashes["synthetic-success-report.json"],
        "source_archive": {
            "file_count": len(source_members),
            "file_list_path": "final-build/source-file-list.json",
            "file_list_sha256": source_list_sha,
            "path": "final-build/source-native.zip",
            "present_file_count": len(source_members),
            "sha256": source_archive_sha,
        },
        "test_logs": dict(test_log_hashes),
        "python_tests": {"elapsed_seconds": 497.48, "files": 59, "passed": 461, "skipped": 8, "subtests": 130},
        "rust_cargo": {"changed_this_batch": False, "previous_certified_file_count": 159, "previous_checks_reused": True},
    }
    delivery_raw = _pretty(delivery)
    _write(baseline, "final-build/delivery.json", delivery_raw)

    workspace = Path(__file__).resolve().parents[2]
    for name in reservation._V2_TOOL_FILES:
        _write(repo, name, (workspace / name).read_bytes())
    profile = reservation._Profile(
        baseline_relative=baseline_relative,
        v2_report_relative=v2_relative,
        confirmation_relative=confirmation_relative,
        output_relative=output_relative,
        delivery_sha256=_sha(delivery_raw),
        v2_report_sha256=v2_sha,
        acceptance_sha256=hashes["acceptance.json"],
        review_sha256=hashes["independent-review.json"],
        protection_sha256=hashes["protected-material-check.json"],
        synthetic_report_sha256=hashes["synthetic-success-report.json"],
        archive_sha256=source_archive_sha,
        file_list_sha256=source_list_sha,
        source_identity=source_identity,
        source_head=source_head,
        source_file_count=len(source_members),
        confirmation_context=confirmation_manifest["context"],
        confirmation_input_count=len(confirmation_paths),
        confirmation_evidence_count=evidence_inventory["entry_count"],
        confirmation_evidence_bytes=evidence_inventory["accessible_file_bytes"],
        test_log_hashes=test_log_hashes,
        v2_acceptance_sha256=v2_acceptance["sha256"],
        v2_acceptance_relative=Path(v2_acceptance["path"]),
    )
    return SimpleNamespace(fixture=fixture, repo=repo, profile=profile)


def build_synthetic_v1_failed_attempt(repo: Path, profile) -> Path:
    """Use the public v1 CLI to create an inert, pinned failure fixture."""
    import contextlib
    import io
    import sys
    from dataclasses import replace
    from unittest.mock import patch

    from ygo_eval.research import main

    workspace = Path(__file__).resolve().parents[2]
    output = repo / profile.output_relative / reservation.REPORT_NAME
    original_tool_bundle = reservation._tool_bundle
    workspace_identity = "a" * 64
    archive_raw, list_raw, metadata = original_tool_bundle(
        repo, workspace_identity, reservation._TOOL_FILES,
    )
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    module_name = "python/ygo_eval/curry_consumption_reservation.py"
    module = members[module_name]
    correct = f'ACCEPTANCE_SHA256 = "{reservation.ACCEPTANCE_SHA256}"'.encode("ascii")
    buggy = f'ACCEPTANCE_SHA256 = "{reservation.ARCHIVED_BAD_ACCEPTANCE_CONSTANT}"'.encode("ascii")
    if correct not in module:
        raise AssertionError("synthetic_v1_source_constant_missing")
    members[module_name] = module.replace(correct, buggy, 1)
    member_hashes = {name: _sha(raw) for name, raw in sorted(members.items())}
    tool_identity = _sha(_canonical({"files": member_hashes, "workspace_identity": workspace_identity}))
    listing = {
        "schema_version": 1,
        "kind": "curry_consumption_reservation_tool_file_list",
        "tool_identity": tool_identity,
        "workspace_identity": workspace_identity,
        "files": [{"path": name, "sha256": member_hashes[name]} for name in sorted(member_hashes)],
    }
    listing_raw = _pretty(listing)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, members[name])
    buggy_archive = buffer.getvalue()
    metadata = {
        **metadata,
        "identity": tool_identity,
        "archive_sha256": _sha(buggy_archive),
        "file_list_sha256": _sha(listing_raw),
        "member_sha256": member_hashes,
    }
    # A valid delivery file with one pinned reference mismatch reproduces the
    # historical stable diagnostic without relying on an invalid file hash.
    bad_profile = replace(profile, review_sha256="0" * 64)
    argv = [
        "research", "prepare-curry-consumption-reservation",
        "--baseline-dir", str(repo / profile.baseline_relative),
        "--output", str(output),
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(reservation, "_repo_root", return_value=repo),
        patch.object(reservation, "_production_profile", return_value=bad_profile),
        patch.object(reservation, "_tool_bundle", return_value=(buggy_archive, listing_raw, metadata)),
        patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
        contextlib.redirect_stdout(io.StringIO()) as stdout,
    ):
        code = main()
    if code != 1:
        raise AssertionError(f"synthetic_v1_failure_not_created:{code}:{stdout.getvalue()}")
    report = json.loads(stdout.getvalue())
    if report.get("failure_checkpoint") != "latest_delivery_chain" or report.get("diagnostics") != ["delivery_anchor_mismatch"]:
        raise AssertionError(f"synthetic_v1_failure_contract_mismatch:{stdout.getvalue()}")
    return output
