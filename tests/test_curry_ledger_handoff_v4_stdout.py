from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as audit

ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return {
        "scope": "curry-option-verification-v1",
        "batch_kind": "curry-option-verification-v1",
        "reservation_id": "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63",
        "reservation_policy_id": "curry-unknown-reserve-seven-v1",
        "certified_historical_consumed": 32,
        "policy_reserved": 7,
        "planning_base": 39,
    }


def _receipt(*, settled: bool = True) -> dict:
    return {
        "ledger": {
            "abandoned": 0,
            "completed": 1,
            "consumed": 1,
            "limit": 7,
            "reserved": 0,
            "unknown": 0 if settled else 1,
        }
    }


def test_legacy_stage_stdout_contract_stays_three_fields():
    assert audit._expected_curry_stage_process_output(_manifest(), _receipt()) == {
        "successful": True,
        "native_calls": 1,
        "ledger": _receipt()["ledger"],
    }


def test_verification_accounting_stdout_contract_matches_rust_golden_shape():
    expected = {
        "actual_all_history_cumulative": None,
        "certified_consumed_including_new": 33,
        "certified_historical_consumed": 32,
        "ledger": {
            "abandoned": 0,
            "completed": 1,
            "consumed": 1,
            "limit": 7,
            "reserved": 0,
            "unknown": 0,
        },
        "native_calls": 1,
        "new_consumed": 1,
        "old_confirmation_actual_consumed": None,
        "planning_base": 39,
        "planning_total": 40,
        "policy_reserved": 7,
        "reservation_id": "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63",
        "reservation_policy_id": "curry-unknown-reserve-seven-v1",
        "successful": True,
        "unknown": 0,
    }
    assert audit._expected_curry_stage_process_output(
        _manifest(), _receipt(), stdout_contract="verification-accounting-v1",
    ) == expected


def test_unsettled_verification_accounting_keeps_derived_totals_unknown():
    actual = audit._expected_curry_stage_process_output(
        _manifest(), _receipt(settled=False),
        stdout_contract="verification-accounting-v1",
    )
    assert actual["new_consumed"] is None
    assert actual["certified_consumed_including_new"] is None
    assert actual["planning_total"] is None
    assert actual["unknown"] == 1


def test_verification_accounting_contract_rejects_wrong_scope():
    manifest = _manifest()
    manifest["scope"] = "curry-option-validation-v1"
    try:
        audit._expected_curry_stage_process_output(
            manifest, _receipt(), stdout_contract="verification-accounting-v1",
        )
    except ValueError as error:
        assert str(error) == "curry_handoff_stage_stdout_contract_scope_invalid"
    else:
        raise AssertionError("verification accounting accepted a different scope")


@pytest.mark.parametrize("mutate", [
    lambda value: value.pop("unknown"),
    lambda value: value.update(extra=1),
    lambda value: value.update(policy_reserved=True),
    lambda value: value.update(certified_historical_consumed=32.0),
    lambda value: value.update(new_consumed=True),
    lambda value: value.update(old_confirmation_actual_consumed=0),
    lambda value: value.update(reservation_id="0" * 64),
])
def test_verification_stdout_comparison_rejects_nonexact_fields_and_types(mutate):
    import copy

    expected = audit._expected_curry_stage_process_output(
        _manifest(), _receipt(), stdout_contract="verification-accounting-v1",
    )
    candidate = copy.deepcopy(expected)
    mutate(candidate)
    from ygo_eval.native_curry_option_validation import _strict_equal

    assert not _strict_equal(candidate, expected)


def test_v4_failure_template_is_schema_valid_before_source_gate():
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v4.schema.json").read_bytes()
    )
    validator = jsonschema.Draft202012Validator(schema)
    report = audit._report_template(None, 4)
    report.update({
        "status": "failed",
        "failure_checkpoint": "previous_v3_failed_source",
        "diagnostic": "source_missing",
    })
    report["checks"]["previous_v3_failed_source"] = "failed"
    validator.validate(report)
    assert audit.validate_report(report)
