"""V5 adds a clean fixed bundle before retrying the saved-input audit."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ygo_eval import curry_ledger_handoff_audit as handoff


def test_v5_is_a_fixed_audit_version_with_its_own_root_and_gate_order():
    assert 5 in handoff.AUDIT_VERSIONS
    spec = handoff.AUDIT_VERSIONS[5]
    assert spec.kind == "curry_ledger_handoff_audit_v5"
    assert spec.output_root.as_posix() == (
        "data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26"
    )
    assert spec.stdout_contract == "verification-accounting-v1"
    assert spec.checks[:2] == ("bundle_layout", "previous_v4_failed_source")
    assert spec.source_layers == (
        "previous_v1", "previous_v2", "v2_final", "previous_v3", "previous_v4",
    )
    assert spec.required_input_roles == handoff.V5_REQUIRED_INPUT_ROLES
    assert spec.input_count == 164
    assert spec.captures_process_diagnostics is True
    assert spec.tracks_process_attempt is True
    assert spec.process_input_roles == handoff.V3_PROCESS_INPUT_ROLES
    assert spec.source_root(Path("repo"), "previous_v4") == (
        Path("repo") / handoff.V4_OUTPUT_RELATIVE
    )


def test_v5_report_template_binds_v4_source_and_stability():
    report = handoff._report_template(None, 5)
    assert "previous_v4_failed_source" in report
    assert report["stability"]["previous_v4_failure_stable"] == "not_checked"
    assert report["stability_rechecks"]["previous_v4_failure_tree"] == "not_collected"
    assert report["accounting"]["scope"] == "curry-option-verification-v1"


def test_v5_template_keeps_derived_v4_hashes_unknown_until_the_source_gate():
    class Sources:
        def child(self, _name):
            return self

        @staticmethod
        def file_sha256_role(role):
            import hashlib
            return hashlib.sha256(role.encode("ascii")).hexdigest()

    report = handoff._report_template(None, 5, _sources=Sources())
    previous = report["previous_v4_failed_source"]
    assert previous["report_sha256"] == Sources.file_sha256_role("previous_v4_report")
    assert previous["delivery_sha256"] == Sources.file_sha256_role(
        "previous_v4_final_delivery",
    )
    for field in (
        "runner_sha256", "build_record_sha256", "source_archive_sha256",
        "source_file_list_sha256", "final_source_archive_sha256",
        "final_source_file_list_sha256",
    ):
        assert previous[field] is None


def test_v4_spec_does_not_accept_v5_only_roles():
    report = handoff._report_template(None, 4)
    report["inputs"].append({
        "role": "previous_v4_report",
        "path": "data/runtime/v4/audit-report.json",
        "sha256": "a" * 64,
        "bytes": 1,
    })
    with pytest.raises(ValueError, match="curry_handoff_input_records_invalid"):
        handoff.validate_report(report)


def test_v2_process_capture_compatibility_is_explicit_in_version_spec():
    legacy_capture = handoff.AUDIT_VERSIONS[2]
    assert legacy_capture.captures_process_diagnostics is True
    assert legacy_capture.tracks_process_attempt is False
    assert legacy_capture.process_input_roles == handoff.V3_PROCESS_INPUT_ROLES
    assert handoff.AUDIT_VERSIONS[1].captures_process_diagnostics is False


def test_v5_schema_is_separate_and_requires_the_164_role_contract():
    schema_path = Path(__file__).resolve().parents[1] / "schemas/curry-ledger-handoff-audit-v5.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"] == {"const": 5}
    assert schema["properties"]["kind"] == {"const": "curry_ledger_handoff_audit_v5"}
    assert schema["properties"]["checks"]["required"] == list(handoff.V5_CHECK_NAMES)
    passed = next(
        item["then"] for item in schema["allOf"]
        if item.get("if", {}).get("properties", {}).get("status", {}).get("const") == "passed"
    )
    assert passed["properties"]["inputs"]["minItems"] == 164
    assert passed["properties"]["inputs"]["maxItems"] == 164


def test_v5_previous_v4_schema_separates_anchors_from_derived_artifacts():
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas/curry-ledger-handoff-audit-v5.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]["previous_v4_failed_source"]["properties"]

    assert properties["report_sha256"] == {"$ref": "#/$defs/hash"}
    assert properties["delivery_sha256"] == {"$ref": "#/$defs/hash"}
    assert properties["final_delivery_sha256"] == properties["delivery_sha256"]

    for role in (
        "runner_sha256",
        "build_record_sha256",
        "source_archive_sha256",
        "source_file_list_sha256",
        "final_source_archive_sha256",
        "final_source_file_list_sha256",
    ):
        assert properties[role] == {"$ref": "#/$defs/nullableHash"}

    nullable_role_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "required": ["sha256"],
        "properties": {"sha256": {"$ref": "#/$defs/nullableHash"}},
    }
    validator = Draft202012Validator(nullable_role_schema)
    assert validator.is_valid({"sha256": None})
    assert validator.is_valid({"sha256": "a" * 64})
    assert not validator.is_valid({"sha256": "not-a-hash"})
