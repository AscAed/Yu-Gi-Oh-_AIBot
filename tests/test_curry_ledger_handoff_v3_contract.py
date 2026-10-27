from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
import uuid

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as audit


ROOT = Path(__file__).resolve().parents[1]


def test_v3_report_has_its_own_fixed_kind_checks_and_schema():
    report = audit._report_template(None, version=3)
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    assert report["schema_version"] == 3
    assert report["kind"] == "curry_ledger_handoff_audit_v3"
    assert report["native_calls"] == 0
    assert report["execution_ready"] is False
    assert report["checks"] == {
        name: "not_run" for name in audit.AUDIT_VERSIONS[3].checks
    }
    assert audit.validate_report(report)
    jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_cli_version_is_opt_in_and_v1_remains_the_default():
    import argparse

    parser = argparse.ArgumentParser()
    audit.add_arguments(parser)
    paths = [
        "--baseline-dir", "baseline",
        "--runner", "runner.exe",
        "--build-record", "build.json",
        "--output", "report.json",
    ]

    assert parser.parse_args(paths).report_version == 1
    assert parser.parse_args([*paths, "--report-version", "3"]).report_version == 3


def test_v3_dispatch_uses_fixed_v3_workflow_spec(monkeypatch):
    captured = {}

    def dispatch(args, repo, **kwargs):
        captured["version"] = kwargs.get("_audit_version")
        captured["args"] = args
        return {"status": "synthetic"}

    monkeypatch.setattr(audit, "_run_audit_v2", dispatch)
    args = Namespace(report_version=3)

    assert audit.run_audit(args, repo=ROOT) == {"status": "synthetic"}
    assert captured == {"version": 3, "args": args}


def test_v3_python_and_schema_reject_wrong_v2_final_source_delta():
    report = audit._report_template(None, version=3)
    report["v2_final_source"]["source_delta"] = {
        "added": [], "removed": [], "changed": ["python/ygo_eval/unrelated.py"],
    }
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError, match="curry_handoff_v2_final_source_fields_invalid"):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_rejects_a_forged_passed_report_with_no_evidence():
    report = audit._report_template(None, version=3)
    report["status"] = "passed"
    report["checks"] = {name: "passed" for name in audit.V3_CHECK_NAMES}
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_validator_checks_process_sidecars_on_failed_reports():
    import hashlib

    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("capture-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    diagnostics = repo / audit.V3_OUTPUT_RELATIVE / "process-diagnostics"
    diagnostics.mkdir(parents=True)
    stdout_path = "process-diagnostics/audit_saved_input_only-test.stdout.bin"
    stderr_path = "process-diagnostics/audit_saved_input_only-test.stderr.bin"
    metadata_path = "process-diagnostics/audit_saved_input_only-test.json"
    stdout_raw, stderr_raw = b"partial output\xff", b"timeout trace\n"
    stdout_file = repo / audit.V3_OUTPUT_RELATIVE / stdout_path
    stderr_file = repo / audit.V3_OUTPUT_RELATIVE / stderr_path
    metadata_file = repo / audit.V3_OUTPUT_RELATIVE / metadata_path
    stdout_file.write_bytes(stdout_raw)
    stderr_file.write_bytes(stderr_raw)
    record = {
        "mode": audit.RUNNER_MODE,
        "runner_role": audit.RUNNER_ROLE,
        "status": "timeout",
        "return_code": None,
        "error_code": "runner_timeout",
        "stdout": {"path": stdout_path, "sha256": hashlib.sha256(stdout_raw).hexdigest(),
                   "bytes": len(stdout_raw)},
        "stderr": {"path": stderr_path, "sha256": hashlib.sha256(stderr_raw).hexdigest(),
                   "bytes": len(stderr_raw)},
        "metadata_path": metadata_path,
    }
    metadata_raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    metadata_file.write_bytes(metadata_raw)
    _set_failed_checkpoint(report, "saved_input_audit", "saved_input_runner_not_successful")
    runner = report["runner"]
    runner.update({
        "process_attempted": True,
        "return_code": None,
        "process_error_code": "runner_timeout",
        "process_status": "timeout",
        "diagnostic_sha256": audit._sha(audit.canonical(record)),
        "stdout_sha256": record["stdout"]["sha256"],
        "stdout_bytes": len(stdout_raw),
        "stderr_sha256": record["stderr"]["sha256"],
        "stderr_bytes": len(stderr_raw),
        "process_capture": {
            "metadata_path": metadata_path,
            "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        },
    })
    report["inputs"].extend(
        audit._record_input(repo, role, path, raw)
        for role, path, raw in (
            ("new_runner_capture_metadata", metadata_file, metadata_raw),
            ("new_runner_stdout", stdout_file, stdout_raw),
            ("new_runner_stderr", stderr_file, stderr_raw),
        )
    )

    assert audit.validate_report(report, repo=repo)
    stdout_file.write_bytes(b"tampered partial output")
    with pytest.raises(ValueError, match="curry_handoff_process_capture_content_mismatch"):
        audit.validate_report(report, repo=repo)
    stdout_file.write_bytes(stdout_raw)
    (diagnostics / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="saved_input_unexpected_diagnostic_sidecar"):
        audit.validate_report(report, repo=repo)


def _v3_failed_at_saved_input_audit(diagnostic: str) -> dict:
    report = audit._report_template(None, version=3)
    report["status"] = "failed"
    report["failure_checkpoint"] = "saved_input_audit"
    report["checks"].update({
        name: "passed" for name in audit.V3_CHECK_NAMES[:-2]
    })
    report["checks"]["saved_input_audit"] = "failed"
    report["stability"]["stage2_receipt_absent_before"] = True
    report["diagnostic"] = diagnostic
    return report


def _attach_v3_process_capture(
    report: dict, repo: Path, *, status: str = "timeout",
    stdout_raw: bytes = b"partial output\xff", stderr_raw: bytes = b"timeout trace\n",
    completed_return_code: int = 0,
) -> None:
    import hashlib

    diagnostics = repo / audit.V3_OUTPUT_RELATIVE / "process-diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    stdout_path = f"process-diagnostics/audit_saved_input_only-{token}.stdout.bin"
    stderr_path = f"process-diagnostics/audit_saved_input_only-{token}.stderr.bin"
    metadata_path = f"process-diagnostics/audit_saved_input_only-{token}.json"
    (diagnostics / Path(stdout_path).name).write_bytes(stdout_raw)
    (diagnostics / Path(stderr_path).name).write_bytes(stderr_raw)
    return_code = completed_return_code if status == "completed" else None
    error_code = {
        "completed": None,
        "timeout": "runner_timeout",
        "launch_failed": "runner_start_failed",
    }[status]
    record = {
        "mode": audit.RUNNER_MODE,
        "runner_role": audit.RUNNER_ROLE,
        "status": status,
        "return_code": return_code,
        "error_code": error_code,
        "stdout": {"path": stdout_path, "sha256": hashlib.sha256(stdout_raw).hexdigest(),
                   "bytes": len(stdout_raw)},
        "stderr": {"path": stderr_path, "sha256": hashlib.sha256(stderr_raw).hexdigest(),
                   "bytes": len(stderr_raw)},
        "metadata_path": metadata_path,
    }
    metadata_raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    (diagnostics / Path(metadata_path).name).write_bytes(metadata_raw)
    runner = report["runner"]
    runner.update({
        "process_attempted": True,
        "return_code": return_code,
        "process_error_code": error_code,
        "process_status": status,
        "diagnostic_sha256": audit._sha(audit.canonical(record)),
        "stdout_sha256": record["stdout"]["sha256"],
        "stdout_bytes": len(stdout_raw),
        "stderr_sha256": record["stderr"]["sha256"],
        "stderr_bytes": len(stderr_raw),
        "process_capture": {
            "metadata_path": metadata_path,
            "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        },
    })
    report["inputs"].extend(
        audit._record_input(repo, role, diagnostics / Path(path).name, raw)
        for role, path, raw in (
            ("new_runner_capture_metadata", metadata_path, metadata_raw),
            ("new_runner_stdout", stdout_path, stdout_raw),
            ("new_runner_stderr", stderr_path, stderr_raw),
        )
    )


@pytest.mark.parametrize(
    ("status", "completed_return_code", "wrong_diagnostic"),
    (
        ("timeout", 0, "runner_timeout"),
        ("launch_failed", 0, "runner_start_failed"),
        ("completed", 7, "audit_failed"),
    ),
)
def test_v3_saved_input_transport_failure_requires_wrapper_diagnostic(
    status: str, completed_return_code: int, wrong_diagnostic: str,
):
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / (
        "transport-diagnostic-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    _set_failed_checkpoint(report, "saved_input_audit", "saved_input_runner_not_successful")
    _attach_v3_process_capture(
        report, repo, status=status, completed_return_code=completed_return_code,
    )
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )
    assert audit.validate_report(report, repo=repo)
    jsonschema.Draft202012Validator(schema).validate(report)

    report["diagnostic"] = wrong_diagnostic
    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def _set_failed_checkpoint(report: dict, checkpoint: str, diagnostic: str) -> None:
    report["status"] = "failed"
    report["failure_checkpoint"] = checkpoint
    index = audit.AUDIT_VERSIONS[3].checks.index(checkpoint)
    report["checks"] = {
        name: ("passed" if offset < index else "failed" if offset == index else "not_run")
        for offset, name in enumerate(audit.AUDIT_VERSIONS[3].checks)
    }
    if index > audit.AUDIT_VERSIONS[3].checks.index("frozen_scope_inputs"):
        report["stability"]["stage2_receipt_absent_before"] = True
    report["diagnostic"] = diagnostic


@pytest.mark.parametrize("diagnostic", (
    "runner_timeout",
    "runner_start_failed",
    "saved_input_runner_not_successful",
    "saved_input_process_output_binding_invalid",
    "saved_input_trace_incomplete",
    "saved_input_output_binding_invalid",
))
def test_v3_rejects_process_failure_without_process_capture(diagnostic: str):
    report = _v3_failed_at_saved_input_audit(diagnostic)
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_accepts_prelaunch_failure_without_process_capture():
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    for diagnostic in (
        "curry_handoff_expected_identity_invalid",
        "saved_input_changed_before_runner_start",
        "saved_input_input_preflight_failed",
        "saved_input_diagnostic_directory_prelaunch_failed",
    ):
        report = _v3_failed_at_saved_input_audit(diagnostic)
        assert audit.validate_report(report)
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_prelaunch_input_read_error_is_stable_and_never_starts_runner():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / (
        "input-preflight-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    attempted = []
    started = []

    with pytest.raises(ValueError, match="saved_input_input_preflight_failed"):
        audit._run_saved_input_audit(
            runner=repo / "runner.exe",
            input_path=repo / "missing-input.json",
            prepared_sha256="a" * 64,
            context="b" * 64,
            identity_sha256="c" * 64,
            repo=repo,
            output_root=repo / "out",
            expected_input_sha256="d" * 64,
            process_runner=lambda *args, **kwargs: started.append(True),
            stable_prelaunch_diagnostics=True,
            on_attempted=lambda: attempted.append(True),
        )

    assert attempted == []
    assert started == []


def test_v3_diagnostic_directory_creation_failure_uses_fixed_prelaunch_code(monkeypatch):
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / (
        "diagnostic-mkdir-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    original_mkdir = Path.mkdir

    def fail_diagnostic_mkdir(path, *args, **kwargs):
        if path.name == "process-diagnostics":
            raise OSError("local path must not enter the report")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_diagnostic_mkdir)
    with pytest.raises(
        ValueError,
        match="saved_input_diagnostic_directory_prelaunch_failed",
    ):
        audit._create_process_diagnostics_dir(
            repo / "v3-output", audit_version=3,
        )
    with pytest.raises(OSError):
        audit._create_process_diagnostics_dir(
            repo / "v2-output", audit_version=2,
        )


def test_v4_diagnostic_directory_creation_failure_uses_fixed_prelaunch_code(monkeypatch):
    repo = ROOT / "target/curry-ledger-handoff-v4-tests" / (
        "diagnostic-mkdir-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    original_mkdir = Path.mkdir

    def fail_diagnostic_mkdir(path, *args, **kwargs):
        if path.name == "process-diagnostics":
            raise OSError("local path must not enter the report")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_diagnostic_mkdir)
    with pytest.raises(
        ValueError,
        match="saved_input_diagnostic_directory_prelaunch_failed",
    ):
        audit._create_process_diagnostics_dir(
            repo / "v4-output", audit_version=4,
        )


def test_v3_rejects_generic_audit_failure_as_prelaunch_diagnostic():
    report = _v3_failed_at_saved_input_audit("audit_failed")
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_rejects_process_attempt_before_saved_input_checkpoint():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("early-attempt-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    _set_failed_checkpoint(report, "previous_failed_sources", "audit_failed")
    _attach_v3_process_capture(report, repo)
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_rejects_process_sidecar_roles_without_attempt():
    report = _v3_failed_at_saved_input_audit(
        "curry_handoff_expected_identity_invalid",
    )
    report["inputs"] = [
        {"role": role, "path": f"process-diagnostics/{role}.bin", "sha256": "a" * 64,
         "bytes": 0}
        for role in ("new_runner_capture_metadata", "new_runner_stdout", "new_runner_stderr")
    ]
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_rejects_orphan_process_diagnostic_directory_without_attempt():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("orphan-capture-" + uuid.uuid4().hex)
    diagnostics = repo / audit.V3_OUTPUT_RELATIVE / "process-diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=False)
    (diagnostics / "orphan.bin").write_bytes(b"unbound")
    report = _v3_failed_at_saved_input_audit(
        "curry_handoff_expected_identity_invalid",
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)


def test_v3_rejects_process_input_rows_that_do_not_match_captured_sidecars():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("capture-rows-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    _attach_v3_process_capture(report, repo)
    row = next(item for item in report["inputs"] if item["role"] == "new_runner_stdout")
    row["sha256"] = "f" * 64

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)


def test_v3_input_stability_failure_requires_successful_process_capture():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("stability-failure-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    _set_failed_checkpoint(report, "input_stability", "curry_handoff_input_stability_failed")
    report["runner"]["saved_input_result"] = {
        "saved_input_audit_passed": True,
        "stage": 2,
        "context": "a" * 64,
        "identity_sha256": "b" * 64,
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": {"consumed": 1, "completed": 1, "unknown": 0, "reserved": 0,
                   "abandoned": 0, "limit": 7},
    }
    report["accounting"].update({
        "new_consumed": 1, "certified_consumed_including_new": 33,
        "planning_total": 40, "unknown": 0,
    })
    _attach_v3_process_capture(report, repo)
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_failed_saved_input_audit_cannot_claim_a_saved_result():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("failed-result-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = _v3_failed_at_saved_input_audit("saved_input_runner_not_successful")
    _attach_v3_process_capture(report, repo)
    report["runner"]["saved_input_result"] = {
        "saved_input_audit_passed": True,
        "stage": 2,
        "context": "a" * 64,
        "identity_sha256": "b" * 64,
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": {"consumed": 1, "completed": 1, "unknown": 0,
                   "reserved": 0, "abandoned": 0, "limit": 7},
    }
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_rejects_incomplete_report_after_process_attempt():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("incomplete-attempt-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    _attach_v3_process_capture(report, repo)
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_requires_each_process_sidecar_role_exactly_once():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("duplicate-sidecar-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = _v3_failed_at_saved_input_audit("saved_input_runner_not_successful")
    _attach_v3_process_capture(report, repo)
    stdout_row = next(row for row in report["inputs"] if row["role"] == "new_runner_stdout")
    report["inputs"].append({
        **stdout_row,
        "path": "process-diagnostics/second.stdout.bin",
        "sha256": "1" * 64,
    })
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


@pytest.mark.parametrize("mutation", ("unknown_state", "missing_key"))
def test_v3_stability_rechecks_reject_unknown_or_missing_states(mutation: str):
    report = audit._report_template(None, version=3)
    if mutation == "unknown_state":
        report["stability_rechecks"]["workspace"] = "future_state"
    else:
        del report["stability_rechecks"]["workspace"]
    report["stability"]["workspace_stable"] = "failed"
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_locks_accounting_when_input_stability_fails():
    report = _v3_failed_at_saved_input_audit("curry_handoff_input_stability_failed")
    _set_failed_checkpoint(report, "input_stability", "curry_handoff_input_stability_failed")
    result = {
        "saved_input_audit_passed": True,
        "stage": 2,
        "context": "a" * 64,
        "identity_sha256": "b" * 64,
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": {"consumed": 1, "completed": 1, "unknown": 0,
                   "reserved": 0, "abandoned": 0, "limit": 7},
    }
    report["runner"].update({
        "process_attempted": True,
        "return_code": 0,
        "process_status": "completed",
        "diagnostic_sha256": "c" * 64,
        "stdout_sha256": "d" * 64,
        "stdout_bytes": 1,
        "stderr_sha256": "e" * 64,
        "stderr_bytes": 0,
        "saved_input_result": result,
        "process_capture": {
            "metadata_path": "process-diagnostics/meta.json",
            "metadata_sha256": "f" * 64,
            "stdout_path": "process-diagnostics/out.bin",
            "stderr_path": "process-diagnostics/err.bin",
        },
    })
    report["accounting"].update({
        "new_consumed": 2,
        "certified_consumed_including_new": 34,
        "planning_total": 41,
        "unknown": 0,
    })
    report["stability_rechecks"]["runner_build"] = "changed"
    report["stability"]["runner_build_stable"] = "failed"
    report["inputs"] = [
        {"role": role, "path": f"process-diagnostics/{name}", "sha256": digest,
         "bytes": 0}
        for role, name, digest in (
            ("new_runner_capture_metadata", "meta.json", "f" * 64),
            ("new_runner_stdout", "out.bin", "d" * 64),
            ("new_runner_stderr", "err.bin", "e" * 64),
        )
    ]
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


@pytest.mark.parametrize("checkpoint", ("previous_failed_sources", None))
def test_v3_schema_keeps_accounting_unknown_before_saved_input_audit(checkpoint):
    report = audit._report_template(None, version=3)
    if checkpoint is None:
        report["status"] = "incomplete"
        report["failure_checkpoint"] = None
    else:
        _set_failed_checkpoint(report, checkpoint, "audit_failed")
    report["accounting"].update({
        "new_consumed": 0,
        "certified_consumed_including_new": 32,
        "planning_total": 39,
        "unknown": 0,
    })
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_attempted_runner_cannot_use_a_prelaunch_diagnostic():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / (
        "attempted-prelaunch-diagnostic-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    report = _v3_failed_at_saved_input_audit("saved_input_runner_not_successful")
    _attach_v3_process_capture(report, repo)
    report["diagnostic"] = "curry_handoff_expected_identity_invalid"
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_failed_report_requires_a_stable_diagnostic():
    report = audit._report_template(None, version=3)
    _set_failed_checkpoint(report, "previous_failed_sources", "audit_failed")
    report["diagnostic"] = None
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_process_capture_rejects_invalid_status_return_error_tuple():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / (
        "capture-status-tuple-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    report = _v3_failed_at_saved_input_audit("saved_input_runner_not_successful")
    _attach_v3_process_capture(report, repo)
    runner = report["runner"]
    metadata_path = repo / audit.V3_OUTPUT_RELATIVE / runner["process_capture"]["metadata_path"]
    record = json.loads(metadata_path.read_bytes())
    record["return_code"] = 0
    record["error_code"] = None
    metadata_raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    metadata_path.write_bytes(metadata_raw)
    runner["return_code"] = 0
    runner["process_error_code"] = None
    runner["diagnostic_sha256"] = audit._sha(audit.canonical(record))
    runner["process_capture"]["metadata_sha256"] = audit._sha(metadata_raw)
    row = next(row for row in report["inputs"]
               if row["role"] == "new_runner_capture_metadata")
    row["sha256"] = audit._sha(metadata_raw)
    row["bytes"] = len(metadata_raw)
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_rejects_duplicate_input_role_rows():
    report = audit._report_template(None, version=3)
    report["inputs"] = [
        {"role": "acceptance", "path": "a.json", "sha256": "a" * 64, "bytes": 1},
        {"role": "acceptance", "path": "b.json", "sha256": "b" * 64, "bytes": 2},
    ]
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_rejects_unknown_input_roles():
    report = audit._report_template(None, version=3)
    report["inputs"] = [
        {"role": "unrecognized_role", "path": "a.json", "sha256": "a" * 64, "bytes": 1},
    ]
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_rejects_failed_checks_in_an_incomplete_report():
    report = audit._report_template(None, version=3)
    report["status"] = "incomplete"
    names = audit.AUDIT_VERSIONS[3].checks
    report["checks"].update({names[0]: "passed", names[1]: "failed"})
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_schema_requires_process_result_when_saved_input_check_passed():
    report = audit._report_template(None, version=3)
    report["status"] = "incomplete"
    names = audit.AUDIT_VERSIONS[3].checks
    for name in names[:names.index("saved_input_audit") + 1]:
        report["checks"][name] = "passed"
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_frozen_scope_pass_requires_initial_stage2_receipt_absent():
    report = audit._report_template(None, version=3)
    _set_failed_checkpoint(report, "stage2_saved_intent", "stage2_saved_intent_invalid")
    report["stability"]["stage2_receipt_absent_before"] = False
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


@pytest.mark.parametrize("field", ("return_code", "stdout_bytes", "stderr_bytes"))
def test_v3_process_capture_rejects_bool_integer_summary_fields(field):
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / (
        "capture-bool-int-" + field + "-" + uuid.uuid4().hex
    )
    repo.mkdir(parents=True, exist_ok=False)
    report = _v3_failed_at_saved_input_audit("saved_input_result_invalid")
    _attach_v3_process_capture(
        report, repo, status="completed", stdout_raw=b"x", stderr_raw=b"y",
    )
    report["runner"][field] = False if field == "return_code" else True

    with pytest.raises(ValueError, match="curry_handoff_process_capture_content_mismatch"):
        audit.validate_report(report, repo=repo)


def test_v3_rejects_missing_capture_input_roles_even_when_sidecars_exist():
    repo = ROOT / "target/curry-ledger-handoff-v3-tests" / ("missing-capture-rows-" + uuid.uuid4().hex)
    repo.mkdir(parents=True, exist_ok=False)
    report = audit._report_template(None, version=3)
    _attach_v3_process_capture(report, repo)
    report["inputs"].pop()

    with pytest.raises(ValueError):
        audit.validate_report(report, repo=repo)


def test_v3_rejects_process_attempt_without_complete_capture():
    report = _v3_failed_at_saved_input_audit("runner_timeout")
    report["runner"]["process_attempted"] = True
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    with pytest.raises(ValueError):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)


def test_v3_attempt_tracking_does_not_change_v2_report_contract():
    runner = audit._report_template(None, version=2)["runner"]
    assert "process_attempted" not in runner
    assert "process_error_code" not in runner


def test_v3_stability_summary_must_match_recheck_state():
    report = audit._report_template(None, version=3)
    report["stability_rechecks"]["process_diagnostics"] = "changed"
    report["stability"]["process_diagnostics_stable"] = "failed"
    schema = json.loads(
        (ROOT / "schemas/curry-ledger-handoff-audit-v3.schema.json").read_bytes()
    )

    assert audit.validate_report(report)
    jsonschema.Draft202012Validator(schema).validate(report)
    report["stability"]["process_diagnostics_stable"] = "passed"
    with pytest.raises(ValueError, match="curry_handoff_stability_recheck_mismatch"):
        audit.validate_report(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)
