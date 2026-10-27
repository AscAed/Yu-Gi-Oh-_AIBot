"""Public V2 recovery flow against an inert, test-owned evidence tree."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import uuid

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_recovery as recovery
from tests.support.curry_ledger_handoff_v3_e2e import _write_source_bundle
from tests.support.curry_recovery_e2e import synthetic_source_identity
from tests.test_curry_ledger_handoff_recovery_public_e2e import (
    ROOT,
    SYNTHETIC_V5_ADDED_PATH,
    _build_synthetic_v5_delivery,
    _forbid_external_execution,
    _forbid_writable_ledger,
    _invoke_recovery_cli,
    _upgrade_stage1_receipt,
    _write_tool_sources,
    _write,
)
from tests.support.curry_ledger_handoff_v5_e2e import build_synthetic_handoff_v5_tree
from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import native_curry_option_validation as curry


SYNTHETIC_V1_WRONG_ADDED_PATH = (
    "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md"
)
SYNTHETIC_V5_DELTA = {
    "added": [SYNTHETIC_V5_ADDED_PATH],
    "removed": [],
    "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pretty(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8") + b"\n"


def _install_synthetic_v1_failed_source(repo: Path) -> tuple[bytes, bytes, dict]:
    """Create the anchored V1 first-gate failure plus a distinct 583-file source."""
    root = repo / recovery.PREVIOUS_RECOVERY_ROOT
    root.mkdir(parents=True, exist_ok=False)
    workspace_identity = synthetic_source_identity(repo)["identity"]
    archive_raw, list_raw, tool = recovery._tool_bundle(
        repo, workspace_identity, recovery.TOOL_FILES,
    )
    _write(root / tool["archive_path"], archive_raw)
    _write(root / tool["file_list_path"], list_raw)

    report = recovery._report_template(tool=tool)
    report.update({
        "status": "failed",
        "valid": False,
        "failure_checkpoint": "v5_delivery_and_archives",
        "diagnostic": "recovery_v5_source_delta_invalid",
    })
    report["checks"] = {
        name: "failed" if index == 0 else "not_run"
        for index, name in enumerate(recovery.CHECKS)
    }
    report["publication"] = {
        "state": "passed", "failure_phase": None, "diagnostic_id": None,
    }
    assert recovery.validate_report(report, profile=recovery.PRODUCTION_PROFILE,
                                    version_spec=recovery.V1_SPEC)
    report_raw = _pretty(report)
    _write(root / recovery.OUTPUT_NAME, report_raw)

    final_root = root / "final-build"
    members = {
        f"synthetic/v1-final-source/{index:04d}.bin":
            f"V1 final source member {index}\n".encode()
        for index in range(583)
    }
    source, archive_path, listing_path = _write_source_bundle(
        final_root, members, "synthetic-v1-final-source-head",
    )
    target_archive = final_root / "source-native.zip"
    target_listing = final_root / "source-native-file-list.json"
    if archive_path != target_archive:
        archive_path.rename(target_archive)
    if listing_path != target_listing:
        listing_path.rename(target_listing)
    archive_path = target_archive
    listing_path = target_listing

    report_relative = (recovery.PREVIOUS_RECOVERY_ROOT / recovery.OUTPUT_NAME).as_posix()
    archive_relative = (
        recovery.PREVIOUS_RECOVERY_ROOT / "final-build/source-native.zip"
    ).as_posix()
    list_relative = (
        recovery.PREVIOUS_RECOVERY_ROOT / "final-build/source-native-file-list.json"
    ).as_posix()
    delivery = {
        "kind": "curry_ledger_handoff_recovery_final_delivery",
        "status": "recovery_failed_at_first_source_gate",
        "native_calls": 0,
        "runner_process_calls": 0,
        "recovery_report": {
            "path": report_relative,
            "sha256": _sha(report_raw),
            "status": "failed",
            "failure_checkpoint": "v5_delivery_and_archives",
            "diagnostic": "recovery_v5_source_delta_invalid",
        },
        "post_docs_source": {
            "identity": source["identity"],
            "file_count": 583,
            "archive_path": archive_relative,
            "archive_sha256": _sha(archive_path.read_bytes()),
            "file_list_path": list_relative,
            "file_list_sha256": _sha(listing_path.read_bytes()),
        },
    }
    delivery_raw = _pretty(delivery)
    _write(final_root / "delivery.json", delivery_raw)
    return report_raw, delivery_raw, delivery


def test_public_v2_recovery_and_verify_after_workspace_docs_change(
    monkeypatch: pytest.MonkeyPatch, capsys,
):
    scratch = ROOT / "target/curry-ledger-handoff-recovery-v2-tests" / (
        "public-v2-success-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v5_tree(scratch / "synthetic")
    repo = tree.repo
    _write_tool_sources(repo, recovery.TOOL_FILES_V2)

    profile = replace(
        recovery.V2_PROFILE,
        v5_root=handoff.V5_OUTPUT_RELATIVE,
        output_root=Path("data/runtime/p1-curry-ledger-handoff-recovery-v2-tests") / uuid.uuid4().hex,
        stage2_input_sha256=_sha(tree.stage2_input_path.read_bytes()),
        prepared_sha256=_sha((tree.stage2_input_path.parent / "prepared.json").read_bytes()),
        reservation_id=curry.OPTION_VERIFICATION_SCOPE.reservation_id,
        reservation_policy_id=curry.OPTION_VERIFICATION_SCOPE.reservation_policy_id,
        added=(SYNTHETIC_V5_ADDED_PATH,),
        removed=(),
        changed=("TASKS.md", "docs/INDEX.md", "docs/TESTING.md"),
    )
    assert profile.source_delta == SYNTHETIC_V5_DELTA

    _upgrade_stage1_receipt(tree)
    _install_synthetic_v1_failed_source(repo)
    previous_root = repo / recovery.PREVIOUS_RECOVERY_ROOT
    previous_report_raw = (previous_root / recovery.OUTPUT_NAME).read_bytes()
    previous_delivery_raw = (previous_root / "final-build/delivery.json").read_bytes()
    # The private synthetic profile must carry its own authenticated anchors;
    # production schema constants remain untouched in the checkout.
    v2_schema_path = repo / "schemas/curry-ledger-handoff-recovery-v2.schema.json"
    v2_schema = json.loads(v2_schema_path.read_bytes())
    previous_schema = v2_schema["properties"]["previous_recovery_source"]["properties"]
    previous_schema["report_sha256"]["const"] = _sha(previous_report_raw)
    previous_schema["delivery_sha256"]["const"] = _sha(previous_delivery_raw)
    _write(v2_schema_path, v2_schema)
    artifacts = _build_synthetic_v5_delivery(
        tree, profile,
        added_path=SYNTHETIC_V5_ADDED_PATH,
        tool_files=recovery.TOOL_FILES_V2,
        schema_overrides={"schemas/curry-ledger-handoff-recovery-v2.schema.json": v2_schema},
    )
    profile = replace(
        profile,
        native_identity=artifacts["native_source"]["identity"],
        native_count=len(artifacts["native_source"]["files"]),
        native_archive_sha256=_sha(artifacts["native_archive"].read_bytes()),
        native_list_sha256=_sha(artifacts["native_listing"].read_bytes()),
        final_identity=artifacts["final_source"]["identity"],
        final_count=len(artifacts["final_source"]["files"]),
        final_archive_sha256=_sha(artifacts["final_archive"].read_bytes()),
        final_list_sha256=_sha(artifacts["final_list"].read_bytes()),
        delivery_sha256=_sha(artifacts["delivery_raw"]),
        observation_sha256=_sha(artifacts["observation"]),
        command_log_sha256=_sha(artifacts["command_log"]),
        ledger_sha256=_sha(tree.ledger_path.read_bytes()),
    )
    version_spec = replace(
        recovery.V2_SPEC,
        profile=profile,
        previous_recovery_report_sha256=_sha(previous_report_raw),
        previous_recovery_delivery_sha256=_sha(previous_delivery_raw),
    )

    _forbid_external_execution(monkeypatch)
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)
    result = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, profile,
        verify_only=False, report_version=2, version_spec=version_spec,
    )
    assert result["status"] == "passed" and result["valid"] is True
    assert result["checks"] == {name: "passed" for name in version_spec.checks}
    assert result["source_groups"]["previous_recovery_roles"] == 6
    assert len(result["inputs"]) == 181
    assert result["accounting"]["original_scope_consumed"] == 1
    assert result["accounting"]["original_scope_completed"] == 1
    assert result["accounting"]["original_scope_unknown"] == 0
    assert result["accounting"]["certified_historical_consumed_including_scope"] == 33
    assert result["accounting"]["planning_total"] == 40
    assert result["accounting"]["old_confirmation_actual_consumed"] is None
    assert result["accounting"]["actual_all_history_cumulative"] is None
    # V1's 583-file delivery and V5's 577-file source are different snapshots.
    assert result["previous_recovery_source"]["final_source_identity"] != profile.final_identity
    report_path = repo / profile.output_root / recovery.OUTPUT_NAME
    saved_tool_files = recovery._verify_tool_bundle(
        report_path.parent, result["tool"], recovery.TOOL_FILES_V2,
    )
    jsonschema.Draft202012Validator(
        json.loads(saved_tool_files["schemas/curry-ledger-handoff-recovery-v2.schema.json"])
    ).validate(result)
    saved_report = report_path.read_bytes()
    v2_tree_before = recovery._tree_snapshot(report_path.parent)
    v1_tree_before = recovery._tree_snapshot(previous_root)
    ledger_before = tree.ledger_path.read_bytes()
    for relative in ("TASKS.md", "docs/INDEX.md", "docs/TESTING.md"):
        path = repo / relative
        path.write_bytes(path.read_bytes() + b"post-report documentation edit\n")

    verified = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, profile,
        verify_only=True, report_version=2, version_spec=version_spec,
    )
    assert verified["valid"] is True
    assert verified["native_calls"] == 0 and verified["runner_process_calls"] == 0
    assert verified["saved_tool_workspace_identity"] == result["tool"]["workspace_identity"]
    assert verified["verification_tool_identity"] != result["tool"]["workspace_identity"]
    assert report_path.read_bytes() == saved_report
    assert recovery._tree_snapshot(report_path.parent) == v2_tree_before
    assert recovery._tree_snapshot(previous_root) == v1_tree_before
    assert tree.ledger_path.read_bytes() == ledger_before
    assert not tree.stage2_receipt_path.exists()


def test_v2_first_gate_binds_v1_failure_and_rejects_report_drift():
    scratch = ROOT / "target/curry-ledger-handoff-recovery-v2-tests" / (
        "v2-first-gate-" + uuid.uuid4().hex
    )
    repo = scratch / "repo"
    repo.mkdir(parents=True, exist_ok=False)
    _write_tool_sources(repo, recovery.TOOL_FILES_V2)
    report_raw, delivery_raw, _ = _install_synthetic_v1_failed_source(repo)
    spec = replace(
        recovery.V2_SPEC,
        previous_recovery_report_sha256=_sha(report_raw),
        previous_recovery_delivery_sha256=_sha(delivery_raw),
    )

    record, rows = recovery._verify_previous_recovery_failed_source(
        repo, spec, recovery.V2_PROFILE,
    )
    assert len(rows) == 6
    assert record["source_delta"] == SYNTHETIC_V5_DELTA
    assert record["final_file_count"] == 583
    assert record["final_source_identity"] != recovery.V2_PROFILE.final_identity

    report_path = repo / recovery.PREVIOUS_RECOVERY_ROOT / recovery.OUTPUT_NAME
    report_path.write_bytes(report_raw + b"tampered after the pinned failure")
    with pytest.raises(ValueError, match="recovery_previous_report_anchor_mismatch"):
        recovery._verify_previous_recovery_failed_source(
            repo, spec, recovery.V2_PROFILE,
        )
