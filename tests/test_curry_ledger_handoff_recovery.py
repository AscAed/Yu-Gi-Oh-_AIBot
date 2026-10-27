"""Tests for read-only recovery of the saved V5 handoff evidence."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_recovery_module_exposes_fixed_contract_without_native_readiness():
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    report = recovery._report_template()
    assert report["schema_version"] == 1
    assert report["kind"] == "curry_ledger_handoff_recovery"
    assert report["native_calls"] == 0
    assert report["runner_process_calls"] == 0
    assert report["execution_ready"] is False
    assert report["accounting"]["old_confirmation_actual_consumed"] is None
    assert report["accounting"]["actual_all_history_cumulative"] is None
    from ygo_eval.curry_ledger_handoff_recovery import validate_report
    assert validate_report(report)


def test_scope_ledger_parser_rejects_unknown_record_kind():
    from ygo_eval import history_audit
    from ygo_eval.curry_ledger_handoff_recovery import _parse_scope_ledger

    entry = {"kind": "reserve"}
    row_hash = history_audit.digest(history_audit.encode([0, "", entry]))
    row = {"sequence": 0, "previous": "", "entry": entry, "hash": row_hash}
    raw = history_audit.encode(row) + b"\n" + b"{}\n" * 6
    with pytest.raises(ValueError, match="unsupported_curry_scope_ledger_record"):
        _parse_scope_ledger(
            raw, blob_reader=lambda *_: b"",
            manifest={"scope": "curry-option-verification-v1",
                      "batch_kind": "curry-option-verification-v1", "limit": 7,
                      "started_at": 1, "context": "a" * 64},
            stage1_receipt={},
            stage1_stdout=b"",
        )


def test_recovery_tool_archive_members_are_rehashed_from_zip():
    import zipfile

    from ygo_eval.curry_ledger_handoff_recovery import (
        TOOL_FILES, _tool_bundle, _verify_tool_bundle,
    )

    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "tool-bundle-" + uuid.uuid4().hex
    )
    repo = scratch / "repo"
    out = scratch / "out"
    for name in (
        "python/ygo_eval/curry_ledger_handoff_recovery.py",
        "python/ygo_eval/curry_ledger_handoff_audit.py",
        "python/ygo_eval/history_audit.py",
        "python/ygo_eval/research.py",
        "schemas/curry-ledger-handoff-recovery-v1.schema.json",
        "schemas/audit-publication-diagnostic-v1.schema.json",
    ):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    archive_raw, list_raw, tool = _tool_bundle(repo, "a" * 64)
    root = out
    root.mkdir()
    (root / tool["archive_path"]).write_bytes(archive_raw)
    (root / tool["file_list_path"]).write_bytes(list_raw)
    _verify_tool_bundle(root, tool)
    assert tool["archive_scope"] == "recovery-entrypoints-and-primary-contracts-integrity-only"
    assert tool["verification_implementation"] == "current_workspace_code_revalidates_saved_evidence"

    # The bundle hash and list may remain internally valid while ZIP member
    # bytes are inconsistent with the certified list; reject that substitution.
    rewritten = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as source, zipfile.ZipFile(rewritten, "w") as target:
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == TOOL_FILES[0]:
                contents += b"tamper"
            target.writestr(item, contents)
    tampered = rewritten.getvalue()
    listing = json.loads(list_raw)
    tool = {**tool, "archive_sha256": hashlib.sha256(tampered).hexdigest()}
    (root / tool["archive_path"]).write_bytes(tampered)
    with pytest.raises(ValueError, match="recovery_tool_member_hash_mismatch"):
        _verify_tool_bundle(root, tool)


def test_report_collision_saves_diagnostic_and_downgrades_success():
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "publication-collision-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    report = recovery._report_template()
    report["tool"] = _install_test_tool_bundle(scratch)
    report.update({
        "status": "passed",
        "valid": True,
        "failure_checkpoint": None,
        "diagnostic": None,
    })
    report["checks"] = {name: "passed" for name in recovery.CHECKS}
    report["source_groups"] = {
        "v5_original_audit_roles": 164,
        "v5_recovery_anchors": 5,
        "curry_scope_blob_roles": 6,
        "v3_reservation_roles": 100,
    }
    report["accounting"].update({
        "original_scope_consumed": 1,
        "original_scope_completed": 1,
        "original_scope_unknown": 0,
        "certified_historical_consumed_before_scope": 32,
        "certified_historical_consumed_including_scope": 33,
        "planning_total": 40,
        "reservation_id": recovery.RESERVATION_ID,
    })
    roles = sorted(_expected_input_roles())
    report["inputs"] = [
        {"role": role, "path": f"synthetic/{index:03d}.bin",
         "sha256": "f" * 64, "bytes": 0}
        for index, role in enumerate(roles)
    ]
    target = scratch / "recovery-report.json"
    target.write_bytes(b"preserve existing report\n")

    with pytest.raises(recovery.RecoveryPublicationError) as error:
        recovery._publish_report(scratch, target, report)

    assert error.value.phase == "exclusive_report_write"
    assert target.read_bytes() == b"preserve existing report\n"
    assert report["status"] == "failed"
    assert report["failure_checkpoint"] == "report_publication"
    assert report["checks"]["report_publication"] == "failed"
    assert report["accounting"]["original_scope_consumed"] is None
    diagnostic_root = scratch / "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    public = json.loads((diagnostic_root / f"{error.value.diagnostic_id}.diagnostic.json").read_bytes())
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas/audit-publication-diagnostic-v1.schema.json").read_bytes())
    jsonschema.validate(public, schema)


def test_publication_directory_collision_is_reported_as_preserved():
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "publication-directory-collision-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    report = recovery._report_template()
    report["tool"] = _install_test_tool_bundle(scratch)
    report.update({
        "status": "passed", "valid": True,
        "failure_checkpoint": None, "diagnostic": None,
    })
    report["checks"] = {name: "passed" for name in recovery.CHECKS}
    report["source_groups"] = {
        "v5_original_audit_roles": 164, "v5_recovery_anchors": 5,
        "curry_scope_blob_roles": 6, "v3_reservation_roles": 100,
    }
    report["accounting"].update({
        "original_scope_consumed": 1, "original_scope_completed": 1,
        "original_scope_unknown": 0,
        "certified_historical_consumed_before_scope": 32,
        "certified_historical_consumed_including_scope": 33,
        "planning_total": 40, "reservation_id": recovery.RESERVATION_ID,
    })
    report["inputs"] = [
        {"role": role, "path": f"synthetic/{index:03d}.bin",
         "sha256": "f" * 64, "bytes": 0}
        for index, role in enumerate(sorted(_expected_input_roles()))
    ]
    target = scratch / "recovery-report.json"
    target.mkdir()

    with pytest.raises(recovery.RecoveryPublicationError) as error:
        recovery._publish_report(scratch, target, report)

    assert error.value.phase == "exclusive_report_write"
    diagnostic_root = scratch / "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    public = json.loads((diagnostic_root / f"{error.value.diagnostic_id}.diagnostic.json").read_bytes())
    assert public["output_state"] == "existing_preserved"
    assert public["output_sha256"] is None


def test_output_root_creation_failure_saves_separate_diagnostic(monkeypatch):
    from dataclasses import replace
    from ygo_data import identity
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "output-root-create-failure-" + uuid.uuid4().hex
    )
    repo = scratch / "repo"
    repo.mkdir(parents=True, exist_ok=False)
    output_root = repo / "target/fixed-recovery-output"
    output_root.mkdir(parents=True)
    sentinel = output_root / "preserve.bin"
    sentinel.write_bytes(b"existing root stays untouched")
    profile = replace(
        recovery.PRODUCTION_PROFILE,
        v5_root=Path("baseline"),
        output_root=Path("target/fixed-recovery-output"),
    )
    args = type("Args", (), {
        "baseline_dir": repo / "baseline",
        "output": output_root / recovery.OUTPUT_NAME,
        "verify_only": False,
    })()
    monkeypatch.setattr(identity, "checked_output", lambda *_args: None)

    with pytest.raises(recovery.RecoveryPublicationError) as error:
        recovery.recover(
            args, repo, source_collector=lambda _: {"identity": "a" * 64},
            _profile=profile,
        )

    assert error.value.phase == "exclusive_report_write"
    assert sentinel.read_bytes() == b"existing root stays untouched"
    diagnostic_root = repo / "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    public = json.loads(
        (diagnostic_root / f"{error.value.diagnostic_id}.diagnostic.json").read_bytes()
    )
    assert public["output_state"] == "existing_preserved"
    assert public["output_sha256"] is None


def test_tool_bundle_must_match_workspace_identity_at_collection_start():
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    report = {"tool": {"workspace_identity": "a" * 64}}
    assert recovery._verify_tool_workspace_binding(report, {"identity": "a" * 64})
    with pytest.raises(ValueError, match="recovery_tool_workspace_identity_mismatch"):
        recovery._verify_tool_workspace_binding(report, {"identity": "b" * 64})


def test_v2_profile_pins_the_actual_v5_source_delta_independently():
    """The V2 fixture is an independent golden, not derived from a prod pin."""
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    expected = {
        "added": [
            "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md",
        ],
        "removed": [],
        "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
    }
    assert recovery.V2_PROFILE.source_delta == expected


def test_recovery_cli_accepts_explicit_v2_report_version():
    import argparse

    from ygo_eval import curry_ledger_handoff_recovery as recovery

    parser = argparse.ArgumentParser()
    recovery.add_arguments(parser)
    parsed = parser.parse_args([
        "--report-version", "2",
        "--baseline-dir", "baseline",
        "--output", "output.json",
    ])
    assert parsed.report_version == 2


def test_recover_does_not_retry_after_publication_diagnostic(monkeypatch):
    from dataclasses import replace

    from ygo_eval import curry_ledger_handoff_recovery as recovery

    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "recover-publication-failure-" + uuid.uuid4().hex
    )
    repo = scratch / "repo"
    repo.mkdir(parents=True, exist_ok=False)
    profile = replace(
        recovery.PRODUCTION_PROFILE,
        v5_root=Path("baseline"),
        output_root=Path("recovery"),
    )
    args = type("Args", (), {
        "baseline_dir": repo / "baseline",
        "output": repo / "recovery/recovery-report.json",
        "verify_only": False,
    })()
    calls = 0

    monkeypatch.setattr(recovery, "_tool_bundle", lambda *_: (
        b"zip", b"list", {"archive_path": "tool.zip", "file_list_path": "tool.json"}
    ))
    monkeypatch.setattr(recovery, "_verify_tool_bundle", lambda *_: {})
    monkeypatch.setattr(recovery, "_collect_evidence", lambda *_args, **_kwargs: ({
        "v5_source": {}, "checks": {name: "passed" for name in recovery.CHECKS},
        "source_groups": {}, "baseline": {}, "saved_process_evidence": {},
        "accounting": {}, "inputs": [], "stability": {},
    }, {}))

    def fail_publish(_repo, _path, report, _profile):
        nonlocal calls
        calls += 1
        report.update({
            "status": "failed", "valid": False,
            "failure_checkpoint": "report_publication",
            "diagnostic": "post_write_revalidation_failed",
        })
        raise recovery.RecoveryPublicationError(
            "post_write_revalidation", "post_write_revalidation_failed", "diag-id"
        )

    monkeypatch.setattr(recovery, "_publish_report", fail_publish)

    with pytest.raises(recovery.RecoveryPublicationError) as error:
        recovery.recover(
            args, repo, source_collector=lambda _: {"identity": "a" * 64},
            _profile=profile,
        )

    assert error.value.phase == "post_write_revalidation"
    assert calls == 1


def test_incomplete_report_cannot_claim_unverified_accounting():
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    report = recovery._report_template()
    report["accounting"].update({
        "original_scope_consumed": 1,
        "certified_historical_consumed_before_scope": 32,
        "certified_historical_consumed_including_scope": 33,
        "reservation_id": recovery.RESERVATION_ID,
        "planning_total": 40,
    })

    with pytest.raises(ValueError, match="recovery_incomplete_accounting_invalid"):
        recovery.validate_report(report)


def test_first_stability_failure_can_be_reported_when_recheck_is_consistent():
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    report = recovery._report_template()
    report.update({
        "status": "failed",
        "valid": False,
        "failure_checkpoint": "input_stability",
        "diagnostic": "recovery_stability_snapshot_failed",
    })
    report["checks"].update({
        "v5_delivery_and_archives": "passed",
        "historical_sources": "passed",
        "frozen_input_and_parent": "passed",
        "saved_process_evidence": "passed",
        "scope_ledger_semantics": "passed",
        "input_stability": "failed",
    })
    report["stability"].update({
        "first_check": "failed",
        "recheck": "passed",
        "workspace": "first_check_failed",
        "v5_tree": "consistent",
        "baseline_tree": "consistent",
        "reservation_tree": "consistent",
        "historical_trees": "consistent",
        "ledger_and_blobs": "consistent",
        "stage2_receipt_absent_before": True,
        "stage2_receipt_absent_after": True,
    })
    report["publication"].update({
        "state": "failed",
        "failure_phase": "report_validation",
        "diagnostic_id": "a" * 32,
    })

    assert recovery.validate_report(report)


def test_post_write_revalidation_failure_records_unverified_output_hash(monkeypatch):
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "post-write-revalidation-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    report = recovery._report_template()
    report["tool"] = _install_test_tool_bundle(scratch)
    report.update({
        "status": "passed",
        "valid": True,
        "failure_checkpoint": None,
        "diagnostic": None,
    })
    report["checks"] = {name: "passed" for name in recovery.CHECKS}
    report["source_groups"] = {
        "v5_original_audit_roles": 164,
        "v5_recovery_anchors": 5,
        "curry_scope_blob_roles": 6,
        "v3_reservation_roles": 100,
    }
    report["accounting"].update({
        "original_scope_consumed": 1,
        "original_scope_completed": 1,
        "original_scope_unknown": 0,
        "certified_historical_consumed_before_scope": 32,
        "certified_historical_consumed_including_scope": 33,
        "planning_total": 40,
        "reservation_id": recovery.RESERVATION_ID,
    })
    report["inputs"] = [
        {"role": role, "path": f"synthetic/{index:03d}.bin",
         "sha256": "f" * 64, "bytes": 0}
        for index, role in enumerate(sorted(_expected_input_roles()))
    ]
    target = scratch / "recovery-report.json"
    original_safe_path = recovery.safe_path
    failed_once = False

    def fail_readback_once(path, *args, **kwargs):
        nonlocal failed_once
        if Path(path) == target and not failed_once:
            failed_once = True
            raise OSError("synthetic post-write readback failure")
        return original_safe_path(path, *args, **kwargs)

    monkeypatch.setattr(recovery, "safe_path", fail_readback_once)
    with pytest.raises(recovery.RecoveryPublicationError) as error:
        recovery._publish_report(scratch, target, report)

    assert error.value.phase == "post_write_revalidation"
    saved = json.loads(target.read_bytes())
    assert saved["status"] == "passed"  # immutable bytes are preserved
    assert report["status"] == "failed"  # caller never receives success
    assert error.value.output_sha256 == hashlib.sha256(target.read_bytes()).hexdigest()
    diagnostic_root = scratch / "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    public = json.loads((diagnostic_root / f"{error.value.diagnostic_id}.diagnostic.json").read_bytes())
    assert public["output_state"] == "written_unverified"
    assert public["output_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    schema = json.loads((ROOT / "schemas/audit-publication-diagnostic-v1.schema.json").read_bytes())
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(public, schema)


def _expected_input_roles():
    from ygo_eval import curry_ledger_handoff_audit as audit

    expected = set(audit.V5_REQUIRED_INPUT_ROLES)
    expected.update({
        "native_build_record", "native_cli_artifact", "native_runner_artifact",
        "native_worker_artifact", "v5_delivery", "v5_observation", "v5_command_log",
        "v5_final_source_archive", "v5_final_source_file_list",
    })
    expected.update(role for role in audit.V3_INPUT_ROLE_ALLOWLIST if role.startswith("v3_source_"))
    expected.update({
        f"curry_scope_blob_{kind}_{index:02d}"
        for kind, count in (("checkpoints", 4), ("results", 1), ("events", 1))
        for index in range(1, count + 1)
    })
    return expected


def _install_test_tool_bundle(root: Path) -> dict:
    from ygo_eval.curry_ledger_handoff_recovery import (
        TOOL_FILES, _tool_bundle, _write_exclusive,
    )

    source_root = ROOT
    for name in TOOL_FILES:
        source = source_root / name
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    archive_raw, listing_raw, metadata = _tool_bundle(root, "a" * 64)
    _write_exclusive(root / metadata["archive_path"], archive_raw)
    _write_exclusive(root / metadata["file_list_path"], listing_raw)
    return metadata
