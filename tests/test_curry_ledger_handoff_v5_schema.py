"""Schema-only regression coverage for V5 ordered failure gates."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ygo_eval import curry_ledger_handoff_audit as handoff


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/curry-ledger-handoff-audit-v5.schema.json"
V5_CHECK_NAMES = (
    "bundle_layout",
    "previous_v4_failed_source",
    "previous_v3_failed_source",
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


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _checkpoint_schema(checkpoint: str) -> dict:
    schema = _schema()
    branches = [
        branch
        for branch in schema["allOf"]
        if branch.get("if", {}).get("properties", {})
        .get("failure_checkpoint", {}).get("const") == checkpoint
    ]
    assert len(branches) == 1, f"expected one schema branch for {checkpoint}"
    return {"allOf": branches}


def _failed_checkpoint_fragment(checkpoint: str) -> dict:
    index = V5_CHECK_NAMES.index(checkpoint)
    checks = {name: "passed" for name in V5_CHECK_NAMES[:index]}
    checks[checkpoint] = "failed"
    checks.update({name: "not_run" for name in V5_CHECK_NAMES[index + 1:]})
    return {
        "status": "failed",
        "failure_checkpoint": checkpoint,
        "checks": checks,
        "runner": {"process_attempted": False},
    }


def test_v5_schema_meta_and_check_order():
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["checks"]["required"] == list(V5_CHECK_NAMES)
    assert schema["properties"]["failure_checkpoint"]["oneOf"][1]["enum"] == list(
        V5_CHECK_NAMES
    )


@pytest.mark.parametrize(
    ("checkpoint", "later_checkpoint"),
    [
        ("bundle_layout", "previous_v4_failed_source"),
        ("previous_v4_failed_source", "previous_v3_failed_source"),
    ],
)
def test_v5_early_failure_rejects_a_later_passed_check(
    checkpoint: str, later_checkpoint: str,
):
    validator = Draft202012Validator(_checkpoint_schema(checkpoint))
    valid = _failed_checkpoint_fragment(checkpoint)
    assert validator.is_valid(valid)

    invalid = deepcopy(valid)
    invalid["checks"][later_checkpoint] = "passed"
    assert not validator.is_valid(invalid)


@pytest.mark.parametrize(
    "checkpoint",
    ["bundle_layout", "previous_v4_failed_source"],
)
def test_v5_early_failure_requires_runner_not_attempted(checkpoint: str):
    validator = Draft202012Validator(_checkpoint_schema(checkpoint))
    valid = _failed_checkpoint_fragment(checkpoint)
    assert validator.is_valid(valid)

    invalid = deepcopy(valid)
    invalid["runner"]["process_attempted"] = True
    assert not validator.is_valid(invalid)


def test_v5_previous_v4_failure_requires_bundle_layout_passed():
    validator = Draft202012Validator(_checkpoint_schema("previous_v4_failed_source"))
    valid = _failed_checkpoint_fragment("previous_v4_failed_source")
    assert validator.is_valid(valid)

    invalid = deepcopy(valid)
    invalid["checks"]["bundle_layout"] = "not_run"
    assert not validator.is_valid(invalid)


def test_v5_previous_v4_derived_artifacts_allow_null_or_hash_but_keep_anchors_fixed():
    schema = _schema()
    properties = schema["properties"]["previous_v4_failed_source"]["properties"]
    for field in ("report_sha256", "delivery_sha256", "final_delivery_sha256"):
        assert properties[field] == {"$ref": "#/$defs/hash"}

    derived_roles = (
        "runner_sha256",
        "build_record_sha256",
        "source_archive_sha256",
        "source_file_list_sha256",
        "final_source_archive_sha256",
        "final_source_file_list_sha256",
    )
    for role in derived_roles:
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

    # JSON Schema validates shape; the production Python verifier binds these
    # three fields to the fixed V4 source anchors before accepting a report.
    report = handoff._report_template(None, 5)
    report["previous_v4_failed_source"]["report_sha256"] = "a" * 64
    report["previous_v4_failed_source"]["delivery_sha256"] = "b" * 64
    report["previous_v4_failed_source"]["final_delivery_sha256"] = "b" * 64
    assert Draft202012Validator(schema).is_valid(report)
    with pytest.raises(ValueError, match="curry_handoff_previous_v4_source_fields_invalid"):
        handoff.validate_report(report)


def test_v5_input_role_enum_includes_all_eight_v4_source_roles():
    schema = _schema()
    role_values = set(schema["$defs"]["input"]["properties"]["role"]["enum"])
    assert {
        "previous_v4_report",
        "previous_v4_build_record",
        "previous_v4_runner",
        "previous_v4_source_archive",
        "previous_v4_source_file_list",
        "previous_v4_final_delivery",
        "previous_v4_final_source_archive",
        "previous_v4_final_source_file_list",
    } <= role_values


def test_v5_success_schema_requires_authenticated_v4_source_claims():
    schema = _schema()
    success_branches = [
        branch
        for branch in schema["allOf"]
        if branch.get("if", {}).get("properties", {}).get("status", {}).get("const")
        == "passed"
    ]
    assert len(success_branches) == 1
    validator = Draft202012Validator({"$defs": schema["$defs"], "allOf": success_branches})
    source = {
        "report_sha256": "a" * 64,
        "delivery_sha256": "b" * 64,
        "final_delivery_sha256": "b" * 64,
        "status": "failed",
        "failure_checkpoint": "previous_v3_failed_source",
        "diagnostic": "curry_handoff_build_root_contents_invalid",
        "runner_sha256": "c" * 64,
        "build_record_sha256": "d" * 64,
        "source_archive_sha256": "e" * 64,
        "source_file_list_sha256": "f" * 64,
        "final_source_archive_sha256": "1" * 64,
        "final_source_file_list_sha256": "2" * 64,
        "report_tool_identity": None,
        "report_input_count": 0,
        "source_identity": "3" * 64,
        "file_count": 568,
        "final_source_identity": "4" * 64,
        "final_file_count": 569,
        "source_delta": {
            "added": ["docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md"],
            "removed": [],
            "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
        },
    }
    assert validator.is_valid({"status": "passed", "previous_v4_failed_source": source})

    for field, value in (
        ("status", None),
        ("source_identity", None),
        ("file_count", None),
        ("report_input_count", False),
        ("source_delta", None),
    ):
        invalid_source = deepcopy(source)
        invalid_source[field] = value
        assert not validator.is_valid({
            "status": "passed",
            "previous_v4_failed_source": invalid_source,
        })


def test_v5_python_contract_rejects_boolean_as_zero_v4_report_input_count():
    report = handoff._report_template(None, 5)
    report["previous_v4_failed_source"]["report_input_count"] = False
    with pytest.raises(
        ValueError,
        match="curry_handoff_previous_v4_source_fields_invalid",
    ):
        handoff.validate_report(report)
