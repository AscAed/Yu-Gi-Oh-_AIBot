"""Versioned V3 recovery behavior against independently fixed expectations."""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import uuid

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_recovery as recovery
from ygo_eval import curry_ledger_handoff_audit as handoff
from tests.support.curry_ledger_handoff_v3_e2e import _write_source_bundle
from tests.support.curry_recovery_e2e import synthetic_source_identity
from tests.test_curry_ledger_handoff_recovery_public_e2e import (
    ROOT, SYNTHETIC_V5_ADDED_PATH, _build_synthetic_v5_delivery,
    _forbid_external_execution, _forbid_writable_ledger, _invoke_recovery_cli,
    _write, _write_tool_sources,
)
from tests.test_curry_ledger_handoff_recovery_v2_public_e2e import _install_synthetic_v1_failed_source


V2_RECORDED_V3_ROLES = frozenset("""
v3_source_acceptance
v3_source_authenticated_prior_v2_acceptance
v3_source_authenticated_v2_report
v3_source_confirmation_acceptance
v3_source_confirmation_delivery
v3_source_confirmation_evidence_file_001
v3_source_confirmation_evidence_file_002
v3_source_confirmation_evidence_file_003
v3_source_confirmation_evidence_file_004
v3_source_confirmation_evidence_file_005
v3_source_confirmation_evidence_file_006
v3_source_confirmation_evidence_file_007
v3_source_confirmation_evidence_file_008
v3_source_confirmation_evidence_file_009
v3_source_confirmation_evidence_file_010
v3_source_confirmation_evidence_file_011
v3_source_confirmation_evidence_file_012
v3_source_confirmation_evidence_file_013
v3_source_confirmation_evidence_file_014
v3_source_confirmation_evidence_file_015
v3_source_confirmation_evidence_file_016
v3_source_confirmation_evidence_file_017
v3_source_confirmation_evidence_file_018
v3_source_confirmation_evidence_file_019
v3_source_confirmation_evidence_file_020
v3_source_confirmation_evidence_file_021
v3_source_confirmation_evidence_file_022
v3_source_confirmation_evidence_file_023
v3_source_confirmation_evidence_file_024
v3_source_confirmation_evidence_file_025
v3_source_confirmation_evidence_file_026
v3_source_confirmation_evidence_file_027
v3_source_confirmation_evidence_file_028
v3_source_confirmation_evidence_file_029
v3_source_confirmation_evidence_file_030
v3_source_confirmation_evidence_file_031
v3_source_confirmation_evidence_file_032
v3_source_confirmation_evidence_file_033
v3_source_confirmation_evidence_file_034
v3_source_confirmation_evidence_file_035
v3_source_confirmation_evidence_file_036
v3_source_confirmation_evidence_file_037
v3_source_confirmation_evidence_file_038
v3_source_confirmation_evidence_file_039
v3_source_confirmation_evidence_file_040
v3_source_confirmation_evidence_inventory
v3_source_confirmation_manifest
v3_source_corrected_534_source_archive
v3_source_corrected_534_source_file_list
v3_source_final_source_archive
v3_source_final_source_file_list
v3_source_historical_ledger_01
v3_source_historical_ledger_02
v3_source_historical_ledger_03
v3_source_historical_ledger_04
v3_source_historical_ledger_06
v3_source_historical_ledger_07
v3_source_historical_ledger_08
v3_source_historical_ledger_09
v3_source_independent_review
v3_source_latest_delivery
v3_source_manifest_role_build_record
v3_source_manifest_role_cli
v3_source_manifest_role_identity
v3_source_manifest_role_ordinary_config
v3_source_manifest_role_runner
v3_source_manifest_role_source_archive
v3_source_manifest_role_source_file_list
v3_source_manifest_role_tournament_config
v3_source_manifest_role_window_start
v3_source_manifest_role_worker
v3_source_native_source_archive
v3_source_native_source_file_list
v3_source_normal_attempt_observation
v3_source_prepared
v3_source_previous_v1_failed_reservation_report
v3_source_previous_v1_failed_tool_archive
v3_source_previous_v1_failed_tool_file_list
v3_source_previous_v2_failed_reservation_report
v3_source_previous_v2_failed_tool_archive
v3_source_previous_v2_failed_tool_file_list
v3_source_protected_material_check
v3_source_source_archive
v3_source_source_file_list
v3_source_stage1_input
v3_source_stage1_input_seal
v3_source_stage1_request
v3_source_synthetic_public_report
v3_source_tenki_validation_acceptance
v3_source_tenki_validation_directory_evidence
v3_source_tenki_validation_ledger
v3_source_test_log_pytest-files_txt
v3_source_test_log_pytest-full-rerun_log
v3_source_test_log_pytest-full_log
v3_source_v2_audit_535_source_archive
v3_source_v2_audit_535_source_file_list
v3_source_v2_failure_acceptance
v3_source_v2_final_536_source_archive
v3_source_v2_final_536_source_file_list
v3_source_workspace_identity
""".split())


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pretty(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8") + b"\n"


def _install_synthetic_v2_failed_source(repo: Path):
    """Install an inert V2 failure with the exact recorded V3-role difference."""
    _write_tool_sources(repo, recovery.TOOL_FILES)
    v1_report_raw, v1_delivery_raw, _ = _install_synthetic_v1_failed_source(repo)
    v1_spec = replace(
        recovery.V2_SPEC,
        previous_recovery_report_sha256=_sha(v1_report_raw),
        previous_recovery_delivery_sha256=_sha(v1_delivery_raw),
    )
    v1_record, v1_rows = recovery._verify_previous_recovery_failed_source(
        repo, v1_spec, recovery.V2_PROFILE,
    )

    _write_tool_sources(repo, recovery.TOOL_FILES_V2)
    audit_source_path = repo / "python/ygo_eval/curry_ledger_handoff_audit.py"
    audit_source = audit_source_path.read_bytes()
    current_role = b"'v3_source_workspace_identity',"
    historical_role = b"'v3_source_confirmation_summary',"
    assert audit_source.count(current_role) == 1
    audit_source_path.write_bytes(audit_source.replace(current_role, historical_role))
    schema_path = repo / "schemas/curry-ledger-handoff-recovery-v2.schema.json"
    schema = json.loads(schema_path.read_bytes())
    previous_props = schema["properties"]["previous_recovery_source"]["properties"]
    previous_props["report_sha256"]["const"] = _sha(v1_report_raw)
    previous_props["delivery_sha256"]["const"] = _sha(v1_delivery_raw)
    _write(schema_path, schema)

    root = repo / recovery.PREVIOUS_RECOVERY_V2_ROOT
    root.mkdir(parents=True, exist_ok=False)
    workspace = synthetic_source_identity(repo)["identity"]
    tool_archive, tool_list, tool = recovery._tool_bundle(
        repo, workspace, recovery.TOOL_FILES_V2,
    )
    _write(root / tool["archive_path"], tool_archive)
    _write(root / tool["file_list_path"], tool_list)

    base_roles = {row["role"] for row in v1_rows}
    assert len(base_roles) == 6
    roles = sorted(base_roles | set(V2_RECORDED_V3_ROLES))
    roles.extend(f"synthetic_v2_role_{index:03d}" for index in range(75))
    assert len(roles) == 181
    payload = b"synthetic V2 failure input\n"
    rows = [{
        "role": role,
        "path": f"synthetic/v2-input-{index:03d}.bin",
        "sha256": _sha(payload),
        "bytes": len(payload),
    } for index, role in enumerate(roles)]
    report = recovery._report_template(
        tool=tool, profile=recovery.V2_PROFILE, version_spec=recovery.V2_SPEC,
    )
    report.update({
        "status": "failed", "valid": False,
        "failure_checkpoint": "scope_ledger_semantics",
        "diagnostic": "recovery_success_input_set_incomplete",
        "checks": {
            name: ("passed" if index < 5 else "failed" if index == 5 else "not_run")
            for index, name in enumerate(recovery.V2_CHECKS)
        },
        "source_groups": {
            "v5_original_audit_roles": 164,
            "v5_recovery_anchors": 5,
            "curry_scope_blob_roles": 6,
            "v3_reservation_roles": 100,
            "previous_recovery_roles": 6,
        },
        "inputs": rows,
        "previous_recovery_source": v1_record,
        "publication": {"state": "passed", "failure_phase": None,
                        "diagnostic_id": None},
    })
    report["accounting"].update({
        "original_scope_consumed": None, "original_scope_completed": None,
        "original_scope_unknown": None, "certified_historical_consumed_before_scope": None,
        "certified_historical_consumed_including_scope": None,
        "reservation_id": None, "planning_total": None,
    })
    v2_spec = replace(recovery.V2_SPEC, previous_recovery_report_sha256=_sha(v1_report_raw),
                      previous_recovery_delivery_sha256=_sha(v1_delivery_raw))
    schema_raw = schema_path.read_bytes()
    assert recovery.validate_report(
        report, schema_raw=schema_raw, profile=recovery.V2_PROFILE,
        version_spec=v2_spec,
    )
    report_raw = _pretty(report)
    _write(root / recovery.OUTPUT_NAME, report_raw)

    final_root = root / "final-build"
    members = {
        f"synthetic/v2-final-source/{index:04d}.bin":
            f"V2 final source member {index}\n".encode()
        for index in range(586)
    }
    source, archive_path, list_path = _write_source_bundle(
        final_root, members, "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
    )
    archive_path.rename(final_root / "source-final.zip")
    list_path.rename(final_root / "source-final-file-list.json")
    archive_path = final_root / "source-final.zip"
    list_path = final_root / "source-final-file-list.json"
    delivery = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_recovery_v2_final_delivery",
        "delivery_notes": {"verify_only_performed": False},
        "calls": {"native_calls": 0, "runner_process_calls": 0,
                  "worker_calls": 0, "ffi_calls": 0},
        "recovery": {
            "report_path": "../recovery-report.json",
            "report_sha256": _sha(report_raw), "status": "failed",
            "failure_checkpoint": "scope_ledger_semantics",
            "diagnostic": "recovery_success_input_set_incomplete",
            "verify_only_run": False,
        },
        "source": {
            "identity": source["identity"], "head": source["head"],
            "file_count": 586, "archive_path": "source-final.zip",
            "archive_sha256": _sha(archive_path.read_bytes()),
            "file_list_path": "source-final-file-list.json",
            "file_list_sha256": _sha(list_path.read_bytes()),
        },
    }
    delivery_raw = _pretty(delivery)
    _write(final_root / "delivery-final.json", delivery_raw)
    return _sha(v1_report_raw), _sha(v1_delivery_raw), _sha(report_raw), _sha(delivery_raw)


def test_v3_version_selects_its_fixed_contract_and_source_roles():
    spec = recovery._version_spec(3)

    assert spec.report_version == 3
    assert spec.report_kind == "curry_ledger_handoff_recovery_v3"
    assert spec.schema_name == "curry-ledger-handoff-recovery-v3.schema.json"
    assert spec.profile.output_root.as_posix() == (
        "data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26"
    )
    assert len(spec.tool_files) == 8
    schema = json.loads((ROOT / "schemas" / spec.schema_name).read_bytes())
    assert schema["properties"]["tool"]["properties"]["file_count"]["const"] == 8
    assert schema["properties"]["tool"]["properties"]["member_sha256"]["minProperties"] == 8
    assert schema["properties"]["tool"]["properties"]["member_sha256"]["maxProperties"] == 8
    assert spec.previous_recovery_report_sha256 == (
        "bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d"
    )
    assert spec.previous_recovery_v2_report_sha256 == (
        "7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6"
    )
    assert spec.previous_recovery_v2_delivery_sha256 == (
        "c3bf0aa851b5cd6b39045ee5b8897d3c53f934de4ab31a5ec0cf1dc93fb7ccfe"
    )

    roles = recovery._v3_reservation_input_roles()
    assert len(roles) == 100
    assert "v3_source_workspace_identity" in roles
    assert "v3_source_confirmation_summary" not in roles


def test_v3_archived_v2_role_allowlist_is_parsed_as_inert_source():
    archived = b"""
V3_INPUT_ROLE_ALLOWLIST = frozenset({
    'manifest',
    'v3_source_confirmation_summary',
    'v3_source_acceptance',
})
raise RuntimeError('must not execute archived source')
"""

    assert recovery._archived_v3_source_roles(archived) == frozenset({
        "v3_source_confirmation_summary", "v3_source_acceptance",
    })
    with pytest.raises(ValueError, match="recovery_previous_v2_archived_role_basis_invalid"):
        recovery._archived_v3_source_roles(
            b"V3_INPUT_ROLE_ALLOWLIST = frozenset(load_roles())\n"
        )

    with pytest.raises(ValueError, match="recovery_previous_v2_archived_role_basis_invalid"):
        recovery._archived_v3_source_roles(b"""
V3_INPUT_ROLE_ALLOWLIST = frozenset({'v3_source_first'})
V3_INPUT_ROLE_ALLOWLIST = frozenset({'v3_source_second'})
""")


def test_v2_verify_allows_saved_workspace_identity_after_document_handoff():
    assert recovery.V2_SPEC.allow_saved_workspace_identity_change is True
    assert recovery.V1_SPEC.allow_saved_workspace_identity_change is False


def test_v3_cli_and_report_template_keep_v1_v2_contracts_separate():
    parser = argparse.ArgumentParser()
    recovery.add_arguments(parser)
    args = parser.parse_args([
        "--report-version", "3", "--baseline-dir", "baseline", "--output", "out",
    ])
    assert args.report_version == 3

    report = recovery._report_template(version_spec=recovery._version_spec(3))
    assert report["checks"]["previous_recovery_v2_failed_source"] == "not_run"
    assert report["source_groups"]["previous_recovery_v1_roles"] == 0
    assert report["source_groups"]["previous_recovery_v2_roles"] == 0
    assert report["previous_recovery_v2_source"]["status"] is None


def test_v3_incomplete_report_is_accepted_by_its_own_schema():
    spec = recovery._version_spec(3)
    report = recovery._report_template(version_spec=spec)

    assert recovery.validate_report(report, version_spec=spec)


def test_failed_v3_report_rejects_unverified_previous_source_rows():
    spec = recovery._version_spec(3)
    report = recovery._report_template(version_spec=spec)
    report.update({
        "status": "failed",
        "valid": False,
        "failure_checkpoint": spec.checks[0],
        "diagnostic": "recovery_previous_v2_source_anchor_invalid",
        "checks": {
            name: ("failed" if index == 0 else "not_run")
            for index, name in enumerate(spec.checks)
        },
        "publication": {"state": "passed", "failure_phase": None,
                        "diagnostic_id": None},
    })
    report["inputs"] = [{
        "role": "previous_recovery_v2_failed_report",
        "path": "saved/v2-report.json",
        "sha256": "a" * 64,
        "bytes": 1,
    }]

    schema = json.loads((ROOT / "schemas" / spec.schema_name).read_bytes())
    with pytest.raises(ValueError, match="recovery_previous_source_group_rows_mismatch"):
        recovery.validate_report(report, version_spec=spec)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)

    report["inputs"] = [{
        "role": "v3_source_workspace_identity",
        "path": "saved/workspace-identity.json",
        "sha256": "b" * 64,
        "bytes": 2,
    }]
    report["source_groups"]["v3_reservation_roles"] = 1
    with pytest.raises(ValueError, match="recovery_failure_input_role_unexpected"):
        recovery.validate_report(report, version_spec=spec)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)

    report["inputs"] = [{
        "role": "unrelated_unverified_source",
        "path": "saved/unrelated.json",
        "sha256": "c" * 64,
        "bytes": 3,
    }]
    with pytest.raises(ValueError, match="recovery_failure_input_role_unexpected"):
        recovery.validate_report(report, version_spec=spec)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)

    report["inputs"] = []
    report["source_groups"]["v5_original_audit_roles"] = 1
    with pytest.raises(ValueError, match="recovery_failure_source_group_rows_mismatch"):
        recovery.validate_report(report, version_spec=spec)


def test_v3_failed_scope_rows_are_a_fixed_prefix_of_scope_blobs():
    spec = recovery._version_spec(3)
    report = recovery._report_template(version_spec=spec)
    report.update({
        "status": "failed",
        "valid": False,
        "failure_checkpoint": "scope_ledger_semantics",
        "diagnostic": "recovery_scope_blob_unavailable",
        "checks": {
            name: ("passed" if index < spec.checks.index("scope_ledger_semantics")
                   else "failed" if name == "scope_ledger_semantics" else "not_run")
            for index, name in enumerate(spec.checks)
        },
        "publication": {"state": "passed", "failure_phase": None,
                        "diagnostic_id": None},
    })
    # This failure shape carries the earlier authenticated rows, then a blob
    # that skips the first item in the ledger's fixed six-role append order.
    roles = recovery._expected_input_roles(spec)
    prefix = sorted(role for role in roles if not role.startswith("curry_scope_blob_"))
    report["inputs"] = [
        {"role": role, "path": f"saved/{index:03}.bin", "sha256": f"{index:064x}",
         "bytes": index}
        for index, role in enumerate(prefix)
    ]
    report["inputs"].append({
        "role": "curry_scope_blob_results_01",
        "path": "saved/blob.bin", "sha256": "f" * 64, "bytes": 1,
    })
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])
    with pytest.raises(ValueError, match="recovery_failure_scope_blob_prefix_invalid"):
        recovery._validate_v3_failed_input_rows(report, spec)

    report["inputs"] = [
        {"role": role, "path": f"saved/{index:03}.bin", "sha256": f"{index:064x}",
         "bytes": index}
        for index, role in enumerate(prefix)
    ]
    blob_order = recovery._v3_scope_blob_roles()
    report["inputs"].extend({
        "role": role,
        "path": f"saved/blob-{index}.bin",
        "sha256": f"{500 + index:064x}",
        "bytes": index,
    } for index, role in enumerate(blob_order[:2]))
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])
    recovery._validate_v3_failed_input_rows(report, spec)

    report["inputs"][-2]["role"] = blob_order[1]
    report["inputs"][-1]["role"] = blob_order[0]
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])
    with pytest.raises(ValueError, match="recovery_failure_scope_blob_prefix_invalid"):
        recovery._validate_v3_failed_input_rows(report, spec)


def test_v3_failed_scope_blob_prefix_must_be_the_input_suffix():
    spec = recovery.V3_SPEC
    report = recovery._report_template(version_spec=spec)
    report.update({
        "status": "failed",
        "valid": False,
        "failure_checkpoint": "scope_ledger_semantics",
        "diagnostic": "recovery_scope_blob_unavailable",
        "checks": {
            name: ("passed" if index < spec.checks.index("scope_ledger_semantics")
                   else "failed" if name == "scope_ledger_semantics" else "not_run")
            for index, name in enumerate(spec.checks)
        },
    })
    roles = recovery._expected_input_roles(spec)
    non_blob = sorted(role for role in roles if not role.startswith("curry_scope_blob_"))
    blob_order = recovery._v3_scope_blob_roles()
    report["inputs"] = [
        {"role": role, "path": f"saved/{index:03}.bin", "sha256": f"{index + 1:064x}",
         "bytes": index}
        for index, role in enumerate(non_blob)
    ]
    report["inputs"].extend({
        "role": role,
        "path": f"saved/blob-{index}.bin",
        "sha256": f"{500 + index:064x}",
        "bytes": index,
    } for index, role in enumerate(blob_order[:2]))
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])
    validator = jsonschema.Draft202012Validator(json.loads(
        (ROOT / "schemas/curry-ledger-handoff-recovery-v3.schema.json").read_bytes()
    ))
    validator.validate(report)

    # A non-blob role appended after the blob records breaks the fixed suffix.
    moved_index = next(
        index for index, row in enumerate(report["inputs"])
        if row["role"] == non_blob[-1]
    )
    moved = report["inputs"].pop(moved_index)
    report["inputs"].append(moved)
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])
    with pytest.raises(ValueError, match="recovery_failure_scope_blob_prefix_invalid"):
        recovery._validate_v3_failed_input_rows(report, spec)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(report)


def test_current_v3_reservation_allowlist_uses_authenticated_workspace_identity():
    roles = {role for role in handoff.V3_INPUT_ROLE_ALLOWLIST
             if role.startswith("v3_source_")}

    assert len(roles) == 100
    assert "v3_source_workspace_identity" in roles
    assert "v3_source_confirmation_summary" not in roles


def test_current_v3_audit_schemas_use_authenticated_workspace_identity():
    for version in (3, 4, 5):
        schema = json.loads((
            ROOT / f"schemas/curry-ledger-handoff-audit-v{version}.schema.json"
        ).read_bytes())
        roles = {
            role for role in schema["$defs"]["input"]["properties"]["role"]["enum"]
            if role.startswith("v3_source_")
        }
        assert len(roles) == 100
        assert "v3_source_workspace_identity" in roles
        assert "v3_source_confirmation_summary" not in roles


def test_v3_saved_process_failure_schema_accepts_precollected_runner_build_rows():
    spec = recovery.V3_SPEC
    profile = recovery.V3_PROFILE
    tool = {
        "identity": "a" * 64,
        "workspace_identity": "b" * 64,
        "archive_scope": recovery.TOOL_ARCHIVE_SCOPE,
        "verification_implementation": recovery.VERIFY_IMPLEMENTATION,
        "archive_path": "tool-source.zip",
        "archive_sha256": "c" * 64,
        "file_list_path": "tool-source-file-list.json",
        "file_list_sha256": "d" * 64,
        "file_count": 8,
        "member_sha256": {f"member-{index}": f"{index + 1:064x}"
                          for index in range(8)},
    }
    report = recovery._report_template(tool=tool, profile=profile, version_spec=spec)
    report.update({
        "status": "failed",
        "failure_checkpoint": "saved_process_evidence",
        "diagnostic": "recovery_saved_process_output_invalid",
        "checks": {
            name: ("passed" if index < spec.checks.index("saved_process_evidence")
                   else "failed" if name == "saved_process_evidence" else "not_run")
            for index, name in enumerate(spec.checks)
        },
        "v5_source": {
            "delivery_sha256": profile.delivery_sha256,
            "native_source_identity": "1" * 64,
            "native_file_count": profile.native_count,
            "final_source_identity": "2" * 64,
            "final_file_count": profile.final_count,
            "source_delta": profile.source_delta,
            "formal_report_absent": True,
            "outer_cli_exit_code_claimed": 2,
            "outer_cli_exit_code_authenticated": False,
            "outer_failure_reason_authenticated": False,
        },
        "baseline": {
            "scope": recovery.SCOPE,
            "context": "3" * 64,
            "manifest_sha256": "4" * 64,
            "prepared_sha256": profile.prepared_sha256,
            "stage1_receipt_sha256": "5" * 64,
            "stage2_input_sha256": profile.stage2_input_sha256,
            "stage2_receipt_absent": True,
        },
        "previous_recovery_source": {
            "report_sha256": spec.previous_recovery_report_sha256,
            "delivery_sha256": spec.previous_recovery_delivery_sha256,
            "status": "failed",
            "failure_checkpoint": "v5_delivery_and_archives",
            "diagnostic": "recovery_v5_source_delta_invalid",
            "source_delta": profile.source_delta,
            "final_source_identity": "6" * 64,
            "final_file_count": 583,
        },
        "previous_recovery_v2_source": {
            "report_sha256": spec.previous_recovery_v2_report_sha256,
            "delivery_sha256": spec.previous_recovery_v2_delivery_sha256,
            "status": "failed",
            "failure_checkpoint": "scope_ledger_semantics",
            "diagnostic": "recovery_success_input_set_incomplete",
            "final_source_identity": "7" * 64,
            "final_file_count": 586,
            "v3_role_count": 100,
            "workspace_identity_present": True,
            "confirmation_summary_present": False,
            "v3_role_difference": {
                "missing_from_report": ["v3_source_confirmation_summary"],
                "unexpected_in_report": ["v3_source_workspace_identity"],
            },
        },
    })
    expected = recovery._expected_input_roles(spec)
    roles = expected - set(recovery._v3_scope_blob_roles()) - {
        "new_runner_capture_metadata", "new_runner_stdout", "new_runner_stderr",
    }
    report["inputs"] = [{
        "role": role,
        "path": f"saved/{index:03}.bin",
        "sha256": f"{index + 1:064x}",
        "bytes": index,
    } for index, role in enumerate(sorted(roles))]
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])
    report["publication"] = {"state": "passed", "failure_phase": None,
                             "diagnostic_id": None}

    validator = jsonschema.Draft202012Validator(
        json.loads((ROOT / "schemas/curry-ledger-handoff-recovery-v3.schema.json").read_bytes())
    )
    assert recovery.validate_report(report, profile=profile, version_spec=spec)
    validator.validate(report)

    partial = copy.deepcopy(report)
    partial["inputs"] = [
        row for row in partial["inputs"] if row["role"] != "new_runner"
    ]
    partial["source_groups"] = recovery._v3_source_group_counts(partial["inputs"])
    with pytest.raises(ValueError, match="recovery_failure_source_gate_rows_mismatch"):
        recovery.validate_report(partial, profile=profile, version_spec=spec)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(partial)


def test_v3_failure_publication_recounts_groups_from_collected_rows(monkeypatch):
    scratch = ROOT / "target/curry-ledger-handoff-recovery-v3-tests" / (
        "failure-group-recount-" + uuid.uuid4().hex
    )
    repo = scratch / "repo"
    (repo / recovery.V3_PROFILE.v5_root).mkdir(parents=True, exist_ok=False)
    spec = recovery.V3_SPEC
    profile = recovery.V3_PROFILE
    _write_tool_sources(repo, recovery.TOOL_FILES_V3)
    role_groups = recovery._v3_failure_role_groups(spec)

    def fake_collect(_repo, *, report_target, on_checkpoint, **_kwargs):
        previous = report_target["previous_recovery_source"]
        previous.update({
            "status": "failed",
            "failure_checkpoint": "v5_delivery_and_archives",
            "diagnostic": "recovery_v5_source_delta_invalid",
            "source_delta": profile.source_delta,
            "final_source_identity": "a" * 64,
            "final_file_count": 583,
        })
        previous_v2 = report_target["previous_recovery_v2_source"]
        previous_v2.update({
            "status": "failed",
            "failure_checkpoint": "scope_ledger_semantics",
            "diagnostic": "recovery_success_input_set_incomplete",
            "final_source_identity": "b" * 64,
            "final_file_count": 586,
            "v3_role_count": 100,
            "workspace_identity_present": True,
            "confirmation_summary_present": False,
            "v3_role_difference": {
                "missing_from_report": ["v3_source_confirmation_summary"],
                "unexpected_in_report": ["v3_source_workspace_identity"],
            },
        })
        for check in (
            "previous_recovery_v2_failed_source",
            "previous_recovery_failed_source",
            "v5_delivery_and_archives",
        ):
            on_checkpoint(check, "passed")
        for group_name in (
            "previous_recovery_v2_roles", "previous_recovery_v1_roles",
            "v5_recovery_anchors",
        ):
            for index, role in enumerate(sorted(role_groups[group_name])):
                report_target["inputs"].append({
                    "role": role,
                    "path": f"synthetic/{group_name}/{index}.bin",
                    "sha256": f"{index + 1:064x}",
                    "bytes": index + 1,
                })
        on_checkpoint("historical_sources", "running")
        raise ValueError("recovery_synthetic_historical_source_failure")

    monkeypatch.setattr(recovery, "_collect_evidence", fake_collect)
    args = argparse.Namespace(
        baseline_dir=repo / profile.v5_root,
        output=repo / profile.output_root / recovery.OUTPUT_NAME,
        verify_only=False,
        report_version=3,
    )
    with pytest.raises(ValueError, match="recovery_synthetic_historical_source_failure"):
        recovery.recover(
            args, repo=repo, source_collector=synthetic_source_identity,
            clock=lambda: 12.0, _profile=profile, _version_spec_override=spec,
        )

    saved = json.loads(args.output.read_bytes())
    assert saved["failure_checkpoint"] == "historical_sources"
    assert saved["checks"]["historical_sources"] == "failed"
    assert saved["source_groups"] == recovery._v3_source_group_counts(saved["inputs"])
    assert saved["source_groups"]["previous_recovery_v2_roles"] == 6
    assert saved["source_groups"]["previous_recovery_v1_roles"] == 6
    assert saved["source_groups"]["v5_recovery_anchors"] == 5
    assert saved["source_groups"]["v3_reservation_roles"] == 0
    assert saved["accounting"]["original_scope_consumed"] is None


def test_v3_reservation_rows_belong_to_frozen_input_gate_not_historical_gate():
    groups = recovery._v3_failure_role_groups(recovery.V3_SPEC)
    reservation_roles = {
        role for role in recovery._expected_input_roles(recovery.V3_SPEC)
        if role.startswith("v3_source_")
    }

    assert len(reservation_roles) == 100
    assert not (groups["historical_sources"] & reservation_roles)
    assert groups["frozen_input_and_parent"] & reservation_roles == reservation_roles


def test_v3_schema_places_reservation_rows_under_frozen_input_gate():
    spec = recovery.V3_SPEC
    groups = recovery._v3_failure_role_groups(spec)
    report = recovery._report_template(version_spec=spec)
    failed_gate = "frozen_input_and_parent"
    failed_index = spec.checks.index(failed_gate)
    report.update({
        "status": "failed",
        "valid": False,
        "failure_checkpoint": failed_gate,
        "diagnostic": "recovery_saved_adapter_codec_hash_mismatch",
        "checks": {
            name: ("passed" if index < failed_index else
                   "failed" if index == failed_index else "not_run")
            for index, name in enumerate(spec.checks)
        },
        "publication": {"state": "passed", "failure_phase": None,
                        "diagnostic_id": None},
    })
    role_groups = (
        "previous_recovery_v2_roles", "previous_recovery_v1_roles",
        "v5_recovery_anchors", "historical_sources",
    )
    roles = [role for group in role_groups for role in sorted(groups[group])]
    report["inputs"] = [{
        "role": role,
        "path": f"saved/{index:03}.bin",
        "sha256": f"{index + 1:064x}",
        "bytes": index + 1,
    } for index, role in enumerate(roles)]
    report["source_groups"] = recovery._v3_source_group_counts(report["inputs"])

    schema = json.loads((ROOT / "schemas" / spec.schema_name).read_bytes())
    jsonschema.Draft202012Validator(schema).validate(report)

    historical_rule = schema["allOf"][9]["then"]["properties"]["inputs"]["allOf"][0]
    frozen_rule = schema["allOf"][11]["then"]["properties"]["inputs"]["allOf"][0]
    assert (
        set(historical_rule["contains"]["properties"]["role"]["enum"])
        == groups["historical_sources"]
    )
    assert historical_rule["minContains"] == historical_rule["maxContains"] == 29
    assert (
        set(frozen_rule["contains"]["properties"]["role"]["enum"])
        == groups["frozen_input_and_parent"]
    )
    assert frozen_rule["minContains"] == frozen_rule["maxContains"] == 128


def test_v3_authenticates_v2_report_roles_and_real_delivery_shape():
    scratch = ROOT / "target/curry-ledger-handoff-recovery-v3-tests" / (
        "v2-source-" + uuid.uuid4().hex
    )
    repo = scratch / "repo"
    repo.mkdir(parents=True, exist_ok=False)
    v1_report_sha, v1_delivery_sha, v2_report_sha, v2_delivery_sha = (
        _install_synthetic_v2_failed_source(repo)
    )
    spec = replace(
        recovery.V3_SPEC,
        previous_recovery_report_sha256=v1_report_sha,
        previous_recovery_delivery_sha256=v1_delivery_sha,
        previous_recovery_v2_report_sha256=v2_report_sha,
        previous_recovery_v2_delivery_sha256=v2_delivery_sha,
    )

    record, rows = recovery._verify_previous_recovery_v2_failed_source(repo, spec)

    assert len(rows) == 6
    assert {row["role"] for row in rows} == {
        "previous_recovery_v2_failed_report",
        "previous_recovery_v2_tool_archive",
        "previous_recovery_v2_tool_file_list",
        "previous_recovery_v2_final_delivery",
        "previous_recovery_v2_final_source_archive",
        "previous_recovery_v2_final_source_file_list",
    }
    assert record["v3_role_count"] == 100
    assert record["workspace_identity_present"] is True
    assert record["confirmation_summary_present"] is False
    assert record["v3_role_difference"] == {
        "missing_from_report": ["v3_source_confirmation_summary"],
        "unexpected_in_report": ["v3_source_workspace_identity"],
    }

    delivery = repo / recovery.PREVIOUS_RECOVERY_V2_ROOT / "final-build/delivery-final.json"
    delivery.write_bytes(delivery.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="recovery_previous_v2_delivery_anchor_mismatch"):
        recovery._verify_previous_recovery_v2_failed_source(repo, spec)


def test_public_v3_recovery_and_verify_after_document_changes(monkeypatch, capsys):
    from tests.support.curry_ledger_handoff_v5_e2e import build_synthetic_handoff_v5_tree
    from ygo_eval import curry_ledger_handoff_audit as handoff
    from ygo_eval import native_curry_option_validation as curry

    scratch = ROOT / "target/curry-ledger-handoff-recovery-v3-tests" / (
        "public-v3-success-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v5_tree(scratch / "synthetic")
    repo = tree.repo
    v3_reservation = json.loads((
        repo / recovery.V3_PROFILE.reservation_root / "reservation.json"
    ).read_bytes())
    v3_source_roles = {row["role"] for row in v3_reservation["inputs"]}
    assert "workspace_identity" in v3_source_roles
    assert "confirmation_summary" not in v3_source_roles
    _write_tool_sources(repo, recovery.TOOL_FILES_V3)
    profile = replace(
        recovery.V3_PROFILE,
        v5_root=handoff.V5_OUTPUT_RELATIVE,
        output_root=Path("data/runtime/p1-curry-ledger-handoff-recovery-v3-tests") / uuid.uuid4().hex,
        stage2_input_sha256=_sha(tree.stage2_input_path.read_bytes()),
        prepared_sha256=_sha((tree.stage2_input_path.parent / "prepared.json").read_bytes()),
        reservation_id=curry.OPTION_VERIFICATION_SCOPE.reservation_id,
        reservation_policy_id=curry.OPTION_VERIFICATION_SCOPE.reservation_policy_id,
        added=(SYNTHETIC_V5_ADDED_PATH,), removed=(),
        changed=("TASKS.md", "docs/INDEX.md", "docs/TESTING.md"),
    )
    tree.stage2_input_path.parent  # Keep the frozen request fixture visible in this test.
    from tests.test_curry_ledger_handoff_recovery_v2_public_e2e import _upgrade_stage1_receipt
    _upgrade_stage1_receipt(tree)
    v1_report_sha, v1_delivery_sha, v2_report_sha, v2_delivery_sha = (
        _install_synthetic_v2_failed_source(repo)
    )

    # The V3 tool bundle carries this test's fixed V1/V2 source anchors.
    _write_tool_sources(repo, recovery.TOOL_FILES_V3)
    v3_schema_path = repo / "schemas/curry-ledger-handoff-recovery-v3.schema.json"
    v3_schema = json.loads(v3_schema_path.read_bytes())
    v1_props = v3_schema["properties"]["previous_recovery_source"]["properties"]
    v1_props["report_sha256"]["const"] = v1_report_sha
    v1_props["delivery_sha256"]["const"] = v1_delivery_sha
    v2_props = v3_schema["properties"]["previous_recovery_v2_source"]["properties"]
    v2_props["report_sha256"]["const"] = v2_report_sha
    v2_props["delivery_sha256"]["const"] = v2_delivery_sha
    _write(v3_schema_path, v3_schema)
    artifacts = _build_synthetic_v5_delivery(
        tree, profile, added_path=SYNTHETIC_V5_ADDED_PATH,
        tool_files=recovery.TOOL_FILES_V3,
        schema_overrides={"schemas/curry-ledger-handoff-recovery-v3.schema.json": v3_schema},
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
        recovery.V3_SPEC, profile=profile,
        previous_recovery_report_sha256=v1_report_sha,
        previous_recovery_delivery_sha256=v1_delivery_sha,
        previous_recovery_v2_report_sha256=v2_report_sha,
        previous_recovery_v2_delivery_sha256=v2_delivery_sha,
    )

    _forbid_external_execution(monkeypatch)
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)
    result = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, profile,
        verify_only=False, report_version=3, version_spec=version_spec,
    )
    assert result["status"] == "passed" and result["valid"] is True
    assert result["checks"] == {name: "passed" for name in version_spec.checks}
    assert result["source_groups"]["previous_recovery_v1_roles"] == 6
    assert result["source_groups"]["previous_recovery_v2_roles"] == 6
    assert result["source_groups"]["v5_original_audit_roles"] == 164
    assert result["source_groups"]["v5_recovery_anchors"] == 5
    assert result["source_groups"]["curry_scope_blob_roles"] == 6
    assert result["source_groups"]["v3_reservation_roles"] == 100
    assert len(result["inputs"]) == 187
    assert result["previous_recovery_v2_source"]["v3_role_difference"] == {
        "missing_from_report": ["v3_source_confirmation_summary"],
        "unexpected_in_report": ["v3_source_workspace_identity"],
    }
    assert result["accounting"]["original_scope_consumed"] == 1
    assert result["accounting"]["original_scope_completed"] == 1
    assert result["accounting"]["original_scope_unknown"] == 0
    assert result["accounting"]["certified_historical_consumed_including_scope"] == 33
    assert result["accounting"]["planning_total"] == 40
    assert result["accounting"]["old_confirmation_actual_consumed"] is None
    assert result["accounting"]["actual_all_history_cumulative"] is None

    report_path = repo / profile.output_root / recovery.OUTPUT_NAME
    report_raw = report_path.read_bytes()
    tool_files = recovery._verify_tool_bundle(
        report_path.parent, result["tool"], recovery.TOOL_FILES_V3,
    )
    jsonschema.Draft202012Validator(
        json.loads(tool_files["schemas/curry-ledger-handoff-recovery-v3.schema.json"])
    ).validate(result)
    for group, expected in {
        "v5_original_audit_roles": 164,
        "v5_recovery_anchors": 5,
        "curry_scope_blob_roles": 6,
        "v3_reservation_roles": 100,
        "previous_recovery_v1_roles": 6,
        "previous_recovery_v2_roles": 6,
    }.items():
        tampered = json.loads(json.dumps(result))
        tampered["source_groups"][group] = expected + 1
        with pytest.raises((ValueError, jsonschema.ValidationError)):
            recovery.validate_report(tampered, version_spec=version_spec, profile=profile)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(
                json.loads(tool_files[
                    "schemas/curry-ledger-handoff-recovery-v3.schema.json"
                ])
            ).validate(tampered)
    v1_tree = recovery._tree_snapshot(repo / recovery.PREVIOUS_RECOVERY_ROOT)
    v2_tree = recovery._tree_snapshot(repo / recovery.PREVIOUS_RECOVERY_V2_ROOT)
    v3_tree = recovery._tree_snapshot(report_path.parent)
    ledger_raw = tree.ledger_path.read_bytes()
    for relative in ("TASKS.md", "docs/INDEX.md", "docs/TESTING.md"):
        path = repo / relative
        path.write_bytes(path.read_bytes() + b"post-report documentation edit\n")

    verified = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, profile,
        verify_only=True, report_version=3, version_spec=version_spec,
    )
    assert verified["valid"] is True
    assert verified["source_input_count"] == 187
    assert verified["saved_tool_workspace_identity"] == result["tool"]["workspace_identity"]
    assert verified["verification_tool_identity"] != result["tool"]["workspace_identity"]
    assert report_path.read_bytes() == report_raw
    assert recovery._tree_snapshot(repo / recovery.PREVIOUS_RECOVERY_ROOT) == v1_tree
    assert recovery._tree_snapshot(repo / recovery.PREVIOUS_RECOVERY_V2_ROOT) == v2_tree
    assert recovery._tree_snapshot(report_path.parent) == v3_tree
    assert tree.ledger_path.read_bytes() == ledger_raw
    assert not tree.stage2_receipt_path.exists()


def test_synthetic_v3_reservation_keeps_summary_as_evidence_role():
    from tests.support import curry_reservation_v3_e2e as fixture_support
    from ygo_eval import curry_consumption_reservation as reservation

    scratch = ROOT / "target/curry-ledger-handoff-recovery-v3-tests" / (
        "summary-role-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    base = fixture_support.build_synthetic_reservation_tree(scratch / "base")
    profile, _, _ = fixture_support._prepare_v3_business_sources(
        base.repo, base.profile, reservation._version_spec(3),
    )
    summary_rel = (profile.confirmation_relative / "research/summary.json").as_posix()
    summary_path = base.repo / summary_rel
    assert summary_path.is_file()
    v2_report = json.loads((base.repo / profile.v2_report_relative).read_bytes())
    rows = [row for row in v2_report["inputs"] if row["path"] == summary_rel]
    assert len(rows) == 1
    assert rows[0]["role"].startswith("confirmation_evidence_file_")
    inventory = json.loads(
        (base.repo / profile.confirmation_relative / "evidence-inventory.json").read_bytes()
    )
    entry = next(
        item for item in inventory["entries"]
        if item["path"] == "research/summary.json"
    )
    assert rows[0]["sha256"] == entry["sha256"]
    assert rows[0]["bytes"] == entry["bytes"]




def test_v3_publication_reconstruction_binds_tool_to_current_workspace(monkeypatch):
    scratch = ROOT / "target/curry-ledger-handoff-recovery-v3-tests" / (
        "publication-workspace-drift-" + uuid.uuid4().hex
    )
    output_root = scratch / "output"
    profile = replace(
        recovery.V3_PROFILE,
        output_root=output_root.relative_to(ROOT),
    )
    spec = replace(
        recovery.V3_SPEC,
        profile=profile,
        diagnostic_root=(scratch / "diagnostics").relative_to(ROOT),
    )
    args = argparse.Namespace(
        baseline_dir=str(ROOT / profile.v5_root),
        output=str(output_root / recovery.OUTPUT_NAME),
        report_version=3,
        verify_only=False,
    )
    identities = iter(("a" * 64, "a" * 64, "b" * 64))
    identity_change_policy = object()
    collect_policies = []

    def source_collector(_repo):
        return {"identity": next(identities), "files": {}}

    evidence_keys = (
        "v5_source", "checks", "source_groups", "baseline",
        "saved_process_evidence", "accounting", "inputs", "stability",
        "previous_recovery_source", "previous_recovery_v2_source",
    )

    def collect(_repo, *, source_collector, report_target,
                allow_saved_workspace_identity_change=identity_change_policy,
                **_kwargs):
        collect_policies.append(allow_saved_workspace_identity_change)
        workspace = source_collector(_repo)
        allow_identity_change = (
            False if allow_saved_workspace_identity_change is identity_change_policy
            else allow_saved_workspace_identity_change
        )
        if not allow_identity_change:
            recovery._verify_tool_workspace_binding(report_target, workspace)
        return ({key: copy.deepcopy(report_target[key]) for key in evidence_keys}, {})

    def publish(_repo, _path, _report, _profile, _spec, *, source_reconstructor=None):
        assert source_reconstructor is not None
        try:
            source_reconstructor()
        except ValueError as error:
            raise recovery.RecoveryPublicationError(
                "source_reconstruction", "source_reconstruction_failed", "synthetic-diagnostic",
            ) from error
        pytest.fail("publication reconstruction accepted a changed workspace identity")

    monkeypatch.setattr(recovery, "_collect_evidence", collect)
    monkeypatch.setattr(recovery, "_publish_for_version", publish)

    with pytest.raises(recovery.RecoveryPublicationError) as error:
        recovery.recover(args, repo=ROOT, source_collector=source_collector,
                         _profile=profile, _version_spec_override=spec)
    assert error.value.phase == "source_reconstruction"
    assert error.value.code == "source_reconstruction_failed"
    assert collect_policies == [identity_change_policy, False]


def test_publication_source_signature_binds_tool_identity():
    report = recovery._report_template(version_spec=recovery.V3_SPEC)
    report["tool"] = {
        "identity": "a" * 64,
        "workspace_identity": "b" * 64,
    }
    original_signature = recovery._publication_source_signature(report)

    changed = copy.deepcopy(report)
    changed["tool"]["workspace_identity"] = "c" * 64

    assert recovery._publication_source_signature(changed) != original_signature
