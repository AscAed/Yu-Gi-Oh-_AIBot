from __future__ import annotations

import json
import hashlib
import uuid
from pathlib import Path

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as audit


ROOT = Path(__file__).resolve().parents[1]


def _schema() -> dict:
    return json.loads((ROOT / "schemas/curry-ledger-handoff-audit-v2.schema.json").read_bytes())


def test_v2_incomplete_template_is_accepted_by_both_contracts():
    report = audit._report_template(None, version=2)

    assert audit.validate_report(report)
    jsonschema.Draft202012Validator(_schema()).validate(report)


def test_v2_incomplete_report_cannot_claim_a_failed_checkpoint():
    report = audit._report_template(None, version=2)
    report["status"] = "incomplete"
    report["failure_checkpoint"] = audit.V2_CHECK_NAMES[0]

    with pytest.raises(ValueError, match="curry_handoff_incomplete_checkpoint_must_be_null"):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(report)


@pytest.mark.parametrize(("field", "value"), [
    ("workspace_stable", "changed"),
    ("stage2_receipt_absent_before", "absent"),
])
def test_v2_stability_summary_matches_schema_value_types(field: str, value: object):
    report = audit._report_template(None, version=2)
    report["stability"][field] = value

    with pytest.raises(ValueError, match="curry_handoff_stability_summary_invalid"):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(report)


@pytest.mark.parametrize("unsafe_path", [
    "C:/private/stage-2-input.json",
    "../outside/stage-2-input.json",
    "data/runtime/../outside.json",
    "data\\runtime\\stage-2-input.json",
    "/absolute/stage-2-input.json",
])
def test_v2_rejects_input_paths_outside_repository_relative_posix_form(unsafe_path: str):
    report = audit._report_template(None, version=2)
    report["inputs"] = [{
        "role": "stage2_input",
        "path": unsafe_path,
        "sha256": "a" * 64,
        "bytes": 1,
    }]

    with pytest.raises(ValueError, match="curry_handoff_input_records_invalid"):
        audit.validate_report(report)


def test_v2_reports_cannot_conflict_when_one_repository_path_has_two_roles():
    report = audit._report_template(None, version=2)
    report["inputs"] = [
        {"role": "stage2_input", "path": "data/runtime/frozen.json", "sha256": "a" * 64, "bytes": 1},
        {"role": "stage2_request", "path": "data/runtime/frozen.json", "sha256": "b" * 64, "bytes": 1},
    ]

    with pytest.raises(ValueError, match="curry_handoff_input_path_conflict"):
        audit.validate_report(report)


def test_v2_reports_cannot_repeat_a_role_at_distinct_paths():
    report = audit._report_template(None, version=2)
    report["inputs"] = [
        {"role": "stage2_input", "path": "data/runtime/one.json", "sha256": "a" * 64, "bytes": 1},
        {"role": "stage2_input", "path": "data/runtime/two.json", "sha256": "b" * 64, "bytes": 1},
    ]

    with pytest.raises(ValueError, match="curry_handoff_input_roles_duplicate"):
        audit.validate_report(report)


def test_v2_schema_requires_read_only_consumption_not_a_second_charge():
    report = audit._report_template(None, version=2)
    report["status"] = "failed"
    report["failure_checkpoint"] = "saved_input_audit"
    report["checks"]["previous_failed_source"] = "passed"
    report["checks"]["acceptance_delivery"] = "passed"
    report["checks"]["dual_timepoint_sources"] = "passed"
    report["checks"]["reservation_and_history"] = "passed"
    report["checks"]["frozen_scope_inputs"] = "passed"
    report["checks"]["stage1_parent_receipt"] = "passed"
    report["checks"]["stage2_saved_intent"] = "passed"
    report["checks"]["isolated_runner_build"] = "passed"
    report["checks"]["saved_input_audit"] = "failed"
    report["accounting"]["new_consumed"] = 2
    report["accounting"]["certified_consumed_including_new"] = 34
    report["accounting"]["planning_total"] = 41
    report["accounting"]["unknown"] = 0

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(report)


def test_v3_input_records_hash_the_pinned_evidence_directory_as_a_directory():
    from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE
    from ygo_eval.native_curry_option_validation import (
        _curry_evidence_hash, _snapshot_curry_evidence,
    )

    repo = ROOT / "target/curry-ledger-handoff-v2-tests" / f"directory-good-{uuid.uuid4().hex}"
    repo.mkdir(parents=True)
    reservation_root = repo / "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"
    reservation_root.mkdir(parents=True)
    (reservation_root / "delivery").mkdir()
    (reservation_root / "delivery/acceptance.json").write_bytes(b"synthetic acceptance")
    evidence_root = repo / V3_TENKI_EVIDENCE_RELATIVE
    (evidence_root / "research").mkdir(parents=True)
    (evidence_root / "process-diagnostics").mkdir()
    (evidence_root / "research/calls.jsonl").write_bytes(b"synthetic directory evidence")

    rows = []
    required_roles = [
        f"historical_ledger_{index:02d}" for index in (1, 2, 3, 4, 6, 7, 8, 9)
    ]
    for index in range(100):
        if index == 0:
            relative = V3_TENKI_EVIDENCE_RELATIVE.as_posix()
            rows.append({
                "role": "tenki_validation_directory_evidence", "path": relative,
                "sha256": _curry_evidence_hash(_snapshot_curry_evidence(evidence_root)),
                "bytes": 0,
            })
            continue
        role = (
            required_roles[index - 1] if index <= 8
            else "tenki_validation_ledger" if index == 9
            else f"synthetic_pin_{index:03d}"
        )
        relative = f"synthetic/pin-{index:03d}.bin"
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = f"pin-{index}".encode()
        path.write_bytes(raw)
        rows.append({
            "role": role, "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        })
    report = {
        "status": "passed", "schema_version": 3,
        "kind": "curry_consumption_reservation_v3", "inputs": rows,
    }
    (reservation_root / "reservation.json").write_text(json.dumps(report), encoding="utf-8")

    records = audit._v3_source_input_records(repo, reservation_root)

    directory_record = next(
        row for row in records
        if row["role"] == "v3_source_tenki_validation_directory_evidence"
    )
    assert directory_record == {
        "role": "v3_source_tenki_validation_directory_evidence",
        "path": V3_TENKI_EVIDENCE_RELATIVE.as_posix(),
        "sha256": rows[0]["sha256"], "bytes": 0,
    }


def test_v3_source_contract_requires_the_special_tenki_ledger_pin():
    assert "v3_source_tenki_validation_ledger" in audit.V3_SOURCE_REQUIRED_ROLES
    schema = _schema()

    def walk(node):
        if isinstance(node, dict):
            yield node
            for child in node.values():
                yield from walk(child)
        elif isinstance(node, list):
            for child in node:
                yield from walk(child)

    assert any(node.get("const") == "v3_source_tenki_validation_ledger"
               for node in walk(schema))


def test_v2_schema_limits_fixed_input_roles_and_v3_source_count():
    schema = _schema()

    def walk(node):
        if isinstance(node, dict):
            yield node
            for child in node.values():
                yield from walk(child)
        elif isinstance(node, list):
            for child in node:
                yield from walk(child)

    role_constraints = []
    v3_count_constraint = False
    for node in walk(schema):
        inputs = node.get("properties", {}).get("inputs", {})
        contains = inputs.get("contains") if isinstance(inputs, dict) else None
        if not isinstance(contains, dict):
            continue
        role = contains.get("properties", {}).get("role", {})
        if "const" in role:
            role_constraints.append(inputs)
        if role.get("pattern") == "^v3_source_":
            v3_count_constraint = (
                inputs.get("minContains") == audit.V3_SOURCE_INPUT_COUNT
                and inputs.get("maxContains") == audit.V3_SOURCE_INPUT_COUNT
            )

    assert role_constraints
    assert all(inputs.get("minContains") == inputs.get("maxContains") == 1
               for inputs in role_constraints)
    assert v3_count_constraint


def test_v3_directory_evidence_rejects_changed_member():
    from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE
    from ygo_eval.native_curry_option_validation import (
        _curry_evidence_hash, _snapshot_curry_evidence,
    )

    repo = ROOT / "target/curry-ledger-handoff-v2-tests" / f"directory-drift-{uuid.uuid4().hex}"
    repo.mkdir(parents=True)
    reservation_root = repo / "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"
    reservation_root.mkdir(parents=True)
    (reservation_root / "delivery").mkdir()
    (reservation_root / "delivery/acceptance.json").write_bytes(b"acceptance")
    evidence_root = repo / V3_TENKI_EVIDENCE_RELATIVE
    (evidence_root / "research").mkdir(parents=True)
    (evidence_root / "process-diagnostics").mkdir()
    (evidence_root / "research/calls.jsonl").write_bytes(b"before")

    rows = []
    for index in range(100):
        if index == 0:
            rows.append({
                "role": "tenki_validation_directory_evidence",
                "path": V3_TENKI_EVIDENCE_RELATIVE.as_posix(),
                "sha256": _curry_evidence_hash(_snapshot_curry_evidence(evidence_root)),
                "bytes": 0,
            })
            continue
        relative = f"synthetic/pin-{index:03d}.bin"
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = f"pin-{index}".encode()
        path.write_bytes(raw)
        role = (
            f"historical_ledger_{index:02d}" if index <= 8
            else "tenki_validation_ledger" if index == 9
            else f"synthetic_pin_{index:03d}"
        )
        rows.append({
            "role": role, "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        })
    (reservation_root / "reservation.json").write_text(json.dumps({
        "status": "passed", "schema_version": 3,
        "kind": "curry_consumption_reservation_v3", "inputs": rows,
    }), encoding="utf-8")
    (evidence_root / "research/calls.jsonl").write_bytes(b"after")

    with pytest.raises(ValueError, match="curry_handoff_v3_source_directory_mismatch"):
        audit._v3_source_input_records(repo, reservation_root)


def test_v2_recheck_failure_is_scoped_to_the_material_that_failed(monkeypatch):
    values = {
        "workspace": {"identity": "w"},
        "previous_failure_tree": {"tree": "p"},
        "baseline_tree": {"tree": "b"},
        "reservation_tree": {"tree": "r"},
        "ledger": "ledger-hash",
        "runner_build": {"tree": "build"},
        "process_diagnostics": {"tree": "diagnostics"},
        "stage2_receipt_absent": True,
    }
    before = dict(values)
    names = tuple(name for name in values if name != "stage2_receipt_absent")

    def sample(*, only_names=None, **_kwargs):
        assert only_names is not None
        name = next(iter(only_names))
        if name == "baseline_tree":
            raise OSError("synthetic single-source recheck failure")
        return {name: values[name]}

    monkeypatch.setattr(audit, "_collect_v2_samples", sample)
    statuses = audit._v2_recheck_statuses(
        before=before,
        repo=ROOT,
        baseline=ROOT / "synthetic-baseline",
        output_root=ROOT / "synthetic-output",
        previous_root=ROOT / "synthetic-previous",
        reservation_root=ROOT / "synthetic-reservation",
        source_collector=lambda _path: values["workspace"],
        stage2_receipt=ROOT / "synthetic-stage2.json",
        ledger_path=ROOT / "synthetic-ledger.jsonl",
    )

    assert statuses == {
        **{name: ("recheck_failed" if name == "baseline_tree" else "consistent")
           for name in names},
            "process_diagnostics": "consistent",
        "stage2_receipt_absent": True,
    }
