from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as audit


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _scratch() -> Path:
    root = Path(__file__).resolve().parents[1] / "target/curry-ledger-handoff-tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def _fixed_root(repo: Path) -> tuple[Path, Path, Path, argparse.Namespace]:
    (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
    baseline = repo / audit.BASELINE_RELATIVE
    baseline.mkdir(parents=True)
    root = repo / audit.OUTPUT_RELATIVE
    artifacts = root / "native-artifacts"
    artifacts.mkdir(parents=True)
    runner = artifacts / audit.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic inert runner bytes")
    (root / audit.BUILD_RECORD_RELATIVE).write_bytes(b"synthetic build record")
    (root / audit.SOURCE_ARCHIVE_RELATIVE).write_bytes(b"synthetic source archive")
    (root / audit.SOURCE_FILE_LIST_RELATIVE).write_bytes(b"synthetic source list")
    args = argparse.Namespace(
        baseline_dir=baseline,
        runner=runner,
        build_record=root / audit.BUILD_RECORD_RELATIVE,
        output=root / audit.REPORT_RELATIVE,
    )
    return baseline, root, runner, args


def _orchestration_snapshot(repo: Path) -> dict:
    stage2_input = repo / "synthetic-stage-2-input.json"
    input_raw = b"synthetic authenticated stage-2 input"
    stage2_input.write_bytes(input_raw)
    context, identity = "a" * 64, "b" * 64
    hashes = [str(index) * 64 for index in range(1, 7)]
    return {
        "report_binding": {
            "acceptance_sha256": audit.ACCEPTANCE_SHA256,
            "delivery_sha256": audit.DELIVERY_SHA256,
            "context": context,
            "manifest_sha256": hashes[0], "prepared_sha256": hashes[1],
            "stage1_receipt_sha256": hashes[2],
            "stage2_input_sha256": _sha(input_raw),
            "stage2_request_sha256": hashes[3],
        },
        "inputs": [],
        "protected": {},
        "initial": {
            "workspace": {"identity": "workspace"},
            "baseline_tree": "baseline", "baseline_evidence": "evidence",
            "reservation_tree": "reservation", "stage2_receipt_absent": True,
        },
        "stage2_input": stage2_input,
        "manifest": {"context": context, "assets": {"ordinary": {"identity": identity}}},
        "prepared_sha256": hashes[4],
    }


def _runner_build_result() -> dict:
    return {
        "runner_sha256": "6" * 64,
        "build_record_sha256": "7" * 64,
        "build_record_identity": "8" * 64,
        "source_identity": "9" * 64,
        "source_file_count": 1,
        "inputs": [],
    }


def _passed_stability(**kwargs) -> dict:
    return {
        "workspace_stable": "passed", "baseline_stable": "passed",
        "reservation_stable": "passed", "ledger_stable": "passed",
        "runner_build_stable": "passed", "stage2_receipt_absent_before": True,
        "stage2_receipt_absent_after": True,
    }


def _schema_validate_report(report: dict) -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas/curry-ledger-handoff-audit-v1.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema_path.read_bytes())).validate(report)


def _saved_result(context: str, identity: str) -> dict:
    return {
        "saved_input_audit_passed": True,
        "native_calls": 0,
        "execution_ready": False,
        "stage": 2,
        "context": context,
        "identity_sha256": identity,
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": {
            "consumed": 1, "completed": 1, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 7,
        },
    }


def _trace() -> bytes:
    rows = []
    for phase, event in audit.TRACE_EVENTS:
        row = {"phase": phase, "event": event}
        if event == "end":
            row["elapsed_ns"] = 17
        rows.append(json.dumps(row, separators=(",", ":")))
    return ("\n".join(rows) + "\n").encode()


def test_saved_input_result_is_fixed_and_rejects_false_zero_call_claims():
    identity, context = "a" * 64, "b" * 64
    value = _saved_result(context, identity)
    assert audit._validate_saved_input_output(
        value, context=context, identity_sha256=identity,
    )["ledger"]["consumed"] == 1
    value["native_calls"] = 1
    with pytest.raises(ValueError, match="saved_input_output_binding_invalid"):
        audit._validate_saved_input_output(value, context=context, identity_sha256=identity)


def test_runner_raw_output_is_saved_before_invalid_json_is_parsed():
    scratch = _scratch()
    input_path = scratch / "stage-2-input.json"
    input_path.write_bytes(b"frozen input")
    output_root = scratch / "output"
    output_root.mkdir()
    (output_root / "process-diagnostics").mkdir()
    stderr = _trace()
    calls = []

    def fake_runner(command, *, cwd, capture_output, timeout, check):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=b"{invalid", stderr=stderr)

    with pytest.raises((ValueError, json.JSONDecodeError)):
        audit._run_saved_input_audit(
            runner=scratch / "runner.exe", input_path=input_path,
            prepared_sha256="c" * 64, context="d" * 64,
            identity_sha256="e" * 64, repo=scratch, output_root=output_root,
            expected_input_sha256=_sha(b"frozen input"),
            process_runner=fake_runner,
        )

    assert len(calls) == 1
    assert calls[0][-2:] == ["--audit-saved-input-only", "--trace-stderr"]
    files = list((output_root / "process-diagnostics").iterdir())
    assert len(files) == 3
    metadata = json.loads(next(path for path in files if path.suffix == ".json").read_bytes())
    raw_out = (output_root / metadata["stdout"]["path"]).read_bytes()
    raw_err = (output_root / metadata["stderr"]["path"]).read_bytes()
    assert raw_out == b"{invalid"
    assert raw_err == stderr
    assert not (scratch / "calls.jsonl").exists()


def test_saved_input_mode_accepts_only_fixed_runner_json_and_trace():
    scratch = _scratch()
    input_path = scratch / "stage-2-input.json"
    input_path.write_bytes(b"frozen input")
    output_root = scratch / "output"
    output_root.mkdir()
    (output_root / "process-diagnostics").mkdir()
    context, identity = "d" * 64, "e" * 64
    payload = json.dumps(_saved_result(context, identity), separators=(",", ":")).encode()

    def fake_runner(command, **kwargs):
        assert "--audit-saved-input-only" in command
        assert "--trace-stderr" in command
        return SimpleNamespace(returncode=0, stdout=payload, stderr=_trace())

    result, details = audit._run_saved_input_audit(
        runner=scratch / "runner.exe", input_path=input_path,
        prepared_sha256="c" * 64, context=context, identity_sha256=identity,
        repo=scratch, output_root=output_root,
        expected_input_sha256=_sha(b"frozen input"), process_runner=fake_runner,
    )
    assert result["ledger"] == _saved_result(context, identity)["ledger"]
    assert [item["phase"] for item in details["trace"] if item["event"] == "start"] == [
        "input_validation", "parent_request_check", "saved_input_asset_scan", "ledger_check",
    ]


def test_saved_input_digest_mismatch_refuses_before_process_start():
    scratch = _scratch()
    input_path = scratch / "stage-2-input.json"
    input_path.write_bytes(b"changed after source audit")
    output_root = scratch / "output"
    output_root.mkdir()
    (output_root / "process-diagnostics").mkdir()
    calls = []
    with pytest.raises(ValueError, match="saved_input_changed_before_runner_start"):
        audit._run_saved_input_audit(
            runner=scratch / "runner.exe", input_path=input_path,
            prepared_sha256="c" * 64, context="d" * 64,
            identity_sha256="e" * 64, repo=scratch, output_root=output_root,
            expected_input_sha256=_sha(b"authenticated original"),
            process_runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
    assert calls == []
    assert list((output_root / "process-diagnostics").iterdir()) == []
    assert not (scratch / "calls.jsonl").exists()


def test_fixed_build_root_allows_only_frozen_build_materials_and_no_outputs():
    repo = _scratch()
    _, root, _, args = _fixed_root(repo)
    assert audit.validate_cli_paths(args, repo)[1] == root
    (root / "unexpected.txt").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="curry_handoff_build_root_contents_invalid"):
        audit.validate_cli_paths(args, repo)


def test_acceptance_accounting_uses_the_frozen_policy_reserve_field(monkeypatch):
    from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE

    acceptance = {
        "kind": "curry_option_verification_final_acceptance",
        "scope": {
            "id": OPTION_VERIFICATION_SCOPE.scope,
            "limit": 7,
            "wall_seconds": 7200,
            "worker_timeout_ms": 30000,
            "execution_order": "serial",
        },
        "status": "partial_failed",
        "accounting": {
            "certified_historical_consumed": 32,
            "policy_reserve": 7,
            "planning_base": 39,
            "new_consumed": 1,
            "certified_consumed_including_new": 33,
            "planning_total": 40,
            "unknown": 0,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        },
        "native_result": {
            "stage_1": {"passed": True, "charged": True},
            "stage_2": {
                "passed": False, "charged": False,
                "runner_return_code": 2,
                "diagnostic": "runner_output_invalid_or_nonzero",
            },
            "native_calls_total": 1,
            "unknown_consumption": 0,
        },
        "qualifications": {flag: False for flag in audit.QUALIFICATIONS},
    }
    acceptance_raw = json.dumps(acceptance, separators=(",", ":")).encode()
    acceptance_sha = _sha(acceptance_raw)
    delivery = {
        "kind": "curry_option_verification_delivery",
        "scope": OPTION_VERIFICATION_SCOPE.scope,
        "status": "partial_failed",
        "acceptance": {
            "path": (audit.BASELINE_RELATIVE / audit.ACCEPTANCE_RELATIVE).as_posix(),
            "sha256": acceptance_sha,
            "bytes": len(acceptance_raw),
        },
    }
    delivery_raw = json.dumps(delivery, separators=(",", ":")).encode()
    monkeypatch.setattr(audit, "ACCEPTANCE_SHA256", acceptance_sha)
    monkeypatch.setattr(audit, "DELIVERY_SHA256", _sha(delivery_raw))

    def read(path, expected=None):
        raw = acceptance_raw if path.name == "acceptance.json" else delivery_raw
        assert expected in (None, _sha(raw))
        return raw, _sha(raw)

    monkeypatch.setattr(audit, "_read", read)
    parsed, _, _, _ = audit._verify_acceptance_delivery(Path("synthetic-baseline"))
    assert parsed["accounting"]["policy_reserve"] == 7


def test_fixed_option_paths_uses_the_saved_verification_runner_name():
    repo = Path(__file__).resolve().parents[1]
    root, paths = audit._fixed_option_paths(repo)
    assert paths["runner"] == root / "native-artifacts/curry-option-verification.exe"


def test_previous_v1_bundle_uses_verification_runner_while_new_runner_uses_validation_name():
    repo = Path(__file__).resolve().parents[1]

    assert audit.RUNNER_RELATIVE == Path("native-artifacts/curry-option-validation.exe")
    assert audit.PREVIOUS_V1_RUNNER_RELATIVE == Path(
        "native-artifacts/curry-option-verification.exe"
    )
    assert audit._previous_v1_runner_path(repo / audit.OUTPUT_RELATIVE) == (
        repo / audit.OUTPUT_RELATIVE / "native-artifacts/curry-option-verification.exe"
    )


def test_previous_v1_source_verifier_reads_and_binds_the_old_verification_runner():
    """Exercise the historical bundle path, not just its path helper."""
    import io
    import zipfile

    from ygo_eval.curry_input_recovery_audit import _PinnedFile, _SourceDescription
    from ygo_data.identity import canonical

    repo = _scratch()
    previous = repo / audit.OUTPUT_RELATIVE
    artifacts = previous / "native-artifacts"
    artifacts.mkdir(parents=True)
    old_runner = artifacts / "curry-option-verification.exe"
    old_runner.write_bytes(b"inert historical verification runner")
    # The V2 runner uses this different name. If the verifier selects it by
    # mistake, the fixed source pin below makes the test fail before success.
    (artifacts / "curry-option-validation.exe").write_bytes(b"decoy new validation runner")

    report = audit._report_template(None)
    report.update({
        "status": "failed",
        "failure_checkpoint": "acceptance_delivery",
        "diagnostic": "curry_handoff_acceptance_accounting_invalid",
    })
    report["checks"]["acceptance_delivery"] = "failed"

    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    archived_lock = (
        b"fn normal() {\n"
        b"    let _parent_view = verify_parent_request(&input, root)?;\n"
        b"    CurryOptionBatch::open(root)?;\n"
        b"}\n"
    )
    file_hashes = {lock_path: _sha(archived_lock)}
    head = "synthetic-head"
    identity = _sha(canonical({"head": head, "files": file_hashes}))
    report["tool_identity"] = {"head": head, "identity": identity, "file_count": 1}
    report_raw = canonical(report)
    (previous / audit.REPORT_RELATIVE).write_bytes(report_raw)
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(lock_path, archived_lock)
    archive_raw = archive_buffer.getvalue()
    file_list_raw = canonical({
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": head,
        "source_identity": identity,
        "file_count": 1,
        "files": file_hashes,
    })
    (previous / audit.SOURCE_ARCHIVE_RELATIVE).write_bytes(archive_raw)
    (previous / audit.SOURCE_FILE_LIST_RELATIVE).write_bytes(file_list_raw)

    source_before = {"head": head, "identity": identity, "files": file_hashes}
    build = {
        "kind": "build_record",
        "status": "recorded",
        "reproducible_build_proven": False,
        "source_before": source_before,
        "source_after": source_before,
        "artifacts": {
            "runner": _sha(old_runner.read_bytes()),
            "source_archive": _sha(archive_raw),
            "source_file_list": _sha(file_list_raw),
        },
    }
    build["identity"] = _sha(canonical(build))
    build_raw = canonical(build)
    (previous / audit.BUILD_RECORD_RELATIVE).write_bytes(build_raw)

    pins = _SourceDescription(
        role="previous_failed_attempt",
        files=(
            _PinnedFile("previous_v1_report", audit.REPORT_RELATIVE.as_posix(), _sha(report_raw)),
            _PinnedFile("previous_v1_build_record", audit.BUILD_RECORD_RELATIVE.as_posix(), _sha(build_raw)),
            _PinnedFile("previous_v1_runner", audit.PREVIOUS_V1_RUNNER_RELATIVE.as_posix(), _sha(old_runner.read_bytes())),
            _PinnedFile("previous_v1_source_archive", audit.SOURCE_ARCHIVE_RELATIVE.as_posix(), _sha(archive_raw)),
            _PinnedFile("previous_v1_source_file_list", audit.SOURCE_FILE_LIST_RELATIVE.as_posix(), _sha(file_list_raw)),
        ),
        dataset_counts=(("previous_source_file_count", 1),),
    )
    sources = _SourceDescription(role="root", children=(pins,))

    verified = audit._verify_previous_failed_attempt(repo, _sources=sources)
    assert verified["record"]["runner_sha256"] == _sha(b"inert historical verification runner")
    assert next(item for item in verified["inputs"] if item["role"] == "previous_v1_runner")["path"].endswith(
        "/native-artifacts/curry-option-verification.exe"
    )

    old_runner.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="pinned_source_hash_mismatch"):
        audit._verify_previous_failed_attempt(repo, _sources=sources)


@pytest.mark.parametrize("accounting_override", [
    {"policy_reserved": 7},
    {"policy_reserve": None},
])
def test_acceptance_rejects_missing_policy_reserve_without_alias_fallback(
    monkeypatch, accounting_override,
):
    from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE

    acceptance = {
        "kind": "curry_option_verification_final_acceptance",
        "scope": {
            "id": OPTION_VERIFICATION_SCOPE.scope,
            "limit": 7, "wall_seconds": 7200, "worker_timeout_ms": 30000,
            "execution_order": "serial",
        },
        "status": "partial_failed",
        "accounting": {
            "certified_historical_consumed": 32,
            "policy_reserve": 7,
            "planning_base": 39,
            "new_consumed": 1,
            "certified_consumed_including_new": 33,
            "planning_total": 40,
            "unknown": 0,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        },
        "native_result": {
            "stage_1": {"passed": True, "charged": True},
            "stage_2": {
                "passed": False, "charged": False,
                "runner_return_code": 2,
                "diagnostic": "runner_output_invalid_or_nonzero",
            },
            "native_calls_total": 1,
            "unknown_consumption": 0,
        },
        "qualifications": {flag: False for flag in audit.QUALIFICATIONS},
    }
    accounting = acceptance["accounting"]
    accounting.pop("policy_reserve")
    accounting.update(accounting_override)
    acceptance_raw = json.dumps(acceptance, separators=(",", ":")).encode()
    delivery = {
        "kind": "curry_option_verification_delivery",
        "scope": OPTION_VERIFICATION_SCOPE.scope,
        "status": "partial_failed",
        "acceptance": {
            "path": (audit.BASELINE_RELATIVE / audit.ACCEPTANCE_RELATIVE).as_posix(),
            "sha256": _sha(acceptance_raw),
            "bytes": len(acceptance_raw),
        },
    }
    delivery_raw = json.dumps(delivery, separators=(",", ":")).encode()
    monkeypatch.setattr(audit, "ACCEPTANCE_SHA256", _sha(acceptance_raw))
    monkeypatch.setattr(audit, "DELIVERY_SHA256", _sha(delivery_raw))

    def read(path, expected=None):
        raw = acceptance_raw if path.name == "acceptance.json" else delivery_raw
        assert expected == _sha(raw)
        return raw, _sha(raw)

    monkeypatch.setattr(audit, "_read", read)
    with pytest.raises(ValueError, match="curry_handoff_acceptance_accounting_invalid"):
        audit._verify_acceptance_delivery(Path("synthetic-baseline"))


def test_existing_report_collision_is_rejected_without_overwrite():
    repo = _scratch()
    _, root, _, args = _fixed_root(repo)
    report_path = root / audit.REPORT_RELATIVE
    report_path.write_bytes(b"preserve this report")
    with pytest.raises(ValueError, match="curry_handoff_output_already_exists"):
        audit.validate_cli_paths(args, repo)
    assert report_path.read_bytes() == b"preserve this report"


def test_publication_reports_source_reconstruction_phase(monkeypatch):
    repo = _scratch()
    target = repo / "target/report.json"

    def reject_source_reconstruction(*_args, **_kwargs):
        raise audit.ReportSourceReconstructionError(
            ValueError("synthetic source graph mismatch"),
        )

    monkeypatch.setattr(audit, "validate_report", reject_source_reconstruction)
    with pytest.raises(audit.AuditPublicationError) as error:
        audit._save_report(target, _successful_report(), repo=repo)

    assert error.value.phase == "source_reconstruction"
    assert error.value.code == "source_reconstruction_failed"
    diagnostic_root = repo / "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    public = json.loads(
        (diagnostic_root / f"{error.value.diagnostic_id}.diagnostic.json").read_bytes()
    )
    assert public["phase"] == "source_reconstruction"


def test_post_write_source_reconstruction_failure_reports_written_candidate(monkeypatch):
    repo = _scratch()
    target = repo / "target/report.json"
    calls = 0

    def reject_only_after_write(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise audit.ReportSourceReconstructionError(
                ValueError("synthetic post-write source graph mismatch"),
            )

    monkeypatch.setattr(audit, "validate_report", reject_only_after_write)
    with pytest.raises(audit.AuditPublicationError) as error:
        audit._save_report(target, _successful_report(), repo=repo)

    assert calls == 2
    assert target.is_file()
    output_sha256 = _sha(target.read_bytes())
    diagnostic_root = repo / "target/curry-ledger-handoff-recovery-tests/publication-diagnostics"
    public = json.loads(
        (diagnostic_root / f"{error.value.diagnostic_id}.diagnostic.json").read_bytes()
    )
    assert error.value.phase == "source_reconstruction"
    assert public["phase"] == "source_reconstruction"
    assert public["output_state"] == "written_unverified"
    assert public["output_sha256"] == output_sha256


def _successful_report() -> dict:
    context, identity = "a" * 64, "b" * 64
    report = audit._report_template({
        "head": "synthetic-head", "identity": "c" * 64, "files": {"x": "d" * 64},
    })
    report.update({"status": "passed", "failure_checkpoint": None})
    report["checks"] = {name: "passed" for name in audit.CHECK_NAMES}
    report["baseline"].update({
        "acceptance_sha256": "e" * 64, "delivery_sha256": "f" * 64,
        "context": context, "manifest_sha256": "1" * 64,
        "prepared_sha256": "2" * 64, "stage1_receipt_sha256": "3" * 64,
        "stage2_input_sha256": "4" * 64, "stage2_request_sha256": "5" * 64,
    })
    report["accounting"].update({
        "new_consumed": 1, "certified_consumed_including_new": 33,
        "planning_total": 40, "unknown": 0,
    })
    report["historical_failure"].update({
        "stage1_passed": True, "stage2_failed": True,
        "stage2_diagnostic": "runner_output_invalid_or_nonzero",
    })
    report["runner"].update({
        "sha256": "6" * 64, "build_record_sha256": "7" * 64,
        "build_record_identity": "8" * 64, "source_identity": "9" * 64,
        "source_file_count": 1, "return_code": 0, "process_status": "completed",
        "diagnostic_sha256": "a" * 64, "stdout_sha256": "b" * 64,
        "stdout_bytes": 100, "stderr_sha256": "c" * 64, "stderr_bytes": 200,
        "trace": audit._trace_summary(_trace()),
        "saved_input_result": {
            "saved_input_audit_passed": True, "stage": 2, "context": context,
            "identity_sha256": identity, "parent_receipt_valid": True,
            "request_derivation_valid": True, "stage_receipt_absent": True,
            "ledger": {"consumed": 1, "completed": 1, "unknown": 0,
                       "reserved": 0, "abandoned": 0, "limit": 7},
        },
    })
    report["stability"] = {
        "workspace_stable": "passed", "baseline_stable": "passed",
        "reservation_stable": "passed", "ledger_stable": "passed",
        "runner_build_stable": "passed", "stage2_receipt_absent_before": True,
        "stage2_receipt_absent_after": True,
    }
    return report


def test_success_report_passes_local_contract_and_published_schema():
    report = _successful_report()
    assert audit.validate_report(report)
    _schema_validate_report(report)

    forged = json.loads(json.dumps(report))
    forged["accounting"]["new_consumed"] = 39
    with pytest.raises(ValueError, match="curry_handoff_accounting_saved_input_mismatch"):
        audit.validate_report(forged)


def test_failed_and_incomplete_reports_enforce_checkpoint_and_accounting_states():
    failed = audit._report_template(None)
    failed.update({"status": "failed", "failure_checkpoint": "saved_input_audit"})
    failed["checks"].update({
        "acceptance_delivery": "passed", "reservation_and_history": "passed",
        "frozen_scope_inputs": "passed", "stage1_parent_receipt": "passed",
        "stage2_saved_intent": "passed", "isolated_runner_build": "passed",
        "saved_input_audit": "failed",
    })
    assert audit.validate_report(failed)
    _schema_validate_report(failed)

    forged = json.loads(json.dumps(failed))
    forged["accounting"]["new_consumed"] = 0
    with pytest.raises(ValueError, match="curry_handoff_accounting_stats_partially_known"):
        audit.validate_report(forged)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validate_report(forged)
    forged = json.loads(json.dumps(failed))
    forged["checks"]["stage2_saved_intent"] = "not_run"
    with pytest.raises(ValueError, match="curry_handoff_failed_checkpoint_checks_inconsistent"):
        audit.validate_report(forged)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validate_report(forged)

    incomplete = audit._report_template(None)
    assert audit.validate_report(incomplete)
    _schema_validate_report(incomplete)
    incomplete["accounting"]["planning_total"] = 39
    with pytest.raises(ValueError, match="curry_handoff_accounting_stats_partially_known"):
        audit.validate_report(incomplete)


def test_run_audit_saved_input_toctou_failure_occurs_before_process_and_saves_report(monkeypatch):
    repo = _scratch() / "synthetic-repo"
    repo.mkdir()
    baseline, output_root, _, args = _fixed_root(repo)
    snapshot = _orchestration_snapshot(repo)
    process_calls = []
    monkeypatch.setattr(audit, "_snapshot_fixed_sources",
                        lambda _repo, _baseline, *, mark: snapshot)

    def mutate_input_after_snapshot(runner, build_record, _repo):
        snapshot["stage2_input"].write_bytes(b"changed after authenticated snapshot")
        return _runner_build_result()

    report = audit.run_audit(
        args, repo=repo,
        runner_build_verifier=mutate_input_after_snapshot,
        stability_verifier=_passed_stability,
        source_collector=lambda _repo: {"head": "synthetic", "identity": "d" * 64,
                                        "files": {"x": "e" * 64}},
        process_runner=lambda *call, **kwargs: process_calls.append((call, kwargs)),
        clock=lambda: 10.0,
    )

    assert report["status"] == "failed"
    assert report["failure_checkpoint"] == "saved_input_audit"
    assert report["checks"]["saved_input_audit"] == "failed"
    assert all(report["accounting"][key] is None for key in (
        "new_consumed", "certified_consumed_including_new", "planning_total", "unknown",
    ))
    assert process_calls == []
    assert report["diagnostic"] == "saved_input_changed_before_runner_start"
    assert audit.validate_report(report)
    _schema_validate_report(report)
    assert (output_root / audit.REPORT_RELATIVE).is_file()
    assert not (baseline / "research/calls.jsonl").exists()
    assert list((output_root / "process-diagnostics").iterdir()) == []


def test_run_audit_orchestration_saves_raw_diagnostics_and_valid_success_report(monkeypatch):
    repo = _scratch() / "synthetic-repo"
    repo.mkdir()
    baseline, output_root, runner, args = _fixed_root(repo)
    snapshot = _orchestration_snapshot(repo)
    commands = []
    context = snapshot["manifest"]["context"]
    identity = snapshot["manifest"]["assets"]["ordinary"]["identity"]
    stdout = json.dumps(_saved_result(context, identity), separators=(",", ":")).encode()
    stderr = _trace()
    # This isolates the orchestration boundary; it is not a full source-tree audit test.
    monkeypatch.setattr(audit, "_snapshot_fixed_sources",
                        lambda _repo, _baseline, *, mark: snapshot)

    def fake_process(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    report = audit.run_audit(
        args, repo=repo,
        runner_build_verifier=lambda *args: _runner_build_result(),
        stability_verifier=_passed_stability,
        source_collector=lambda _repo: {"head": "synthetic", "identity": "d" * 64,
                                        "files": {"x": "e" * 64}},
        process_runner=fake_process,
        clock=lambda: 10.0,
    )

    assert report["status"] == "passed"
    assert report["checks"] == {name: "passed" for name in audit.CHECK_NAMES}
    assert report["accounting"]["new_consumed"] == 1
    assert len(commands) == 1
    assert commands[0][0] == str(runner)
    assert commands[0][commands[0].index("--input-sha") + 1] == snapshot["report_binding"]["stage2_input_sha256"]
    assert report["runner"]["role"] == audit.RUNNER_ROLE
    assert report["runner"]["mode"] == audit.RUNNER_MODE
    assert audit.validate_report(report)
    _schema_validate_report(report)

    files = list((output_root / "process-diagnostics").iterdir())
    assert len(files) == 3
    metadata = json.loads(next(path for path in files if path.suffix == ".json").read_bytes())
    assert (output_root / metadata["stdout"]["path"]).read_bytes() == stdout
    assert (output_root / metadata["stderr"]["path"]).read_bytes() == stderr
    assert not (baseline / "research/calls.jsonl").exists()


def test_stability_marks_frozen_runner_build_drift(monkeypatch):
    import ygo_eval.curry_asset_binding_audit as asset_audit
    import ygo_eval.curry_consumption_reservation as reservation
    import ygo_eval.native_curry_option_validation as option_validation

    repo = _scratch()
    _, root, _, _ = _fixed_root(repo)
    initial_build = audit._build_material_snapshot(root)
    (root / audit.BUILD_RECORD_RELATIVE).write_bytes(b"changed build record")

    monkeypatch.setattr(asset_audit, "_snapshot_tree", lambda path: "baseline")
    monkeypatch.setattr(reservation, "_snapshot_tree", lambda path: "reservation")
    monkeypatch.setattr(option_validation, "_snapshot_curry_evidence", lambda path: "evidence")
    monkeypatch.setattr(option_validation, "_assert_option_verification_protected", lambda pins, root: None)
    initial = {
        "workspace": {"identity": "workspace"}, "baseline_tree": "baseline",
        "baseline_evidence": "evidence", "reservation_tree": "reservation",
        "stage2_receipt_absent": True, "build_materials": initial_build,
    }
    stability = audit._verify_stability(
        repo=repo, baseline=repo / audit.BASELINE_RELATIVE, output_root=root,
        initial=initial, protected={}, stage2_receipt=repo / "missing-stage-2.json",
        source_collector=lambda path: {"identity": "workspace"},
    )
    assert stability["runner_build_stable"] == "failed"


def test_public_cli_dispatches_fixed_audit_command(monkeypatch, capsys):
    import ygo_eval.research as research

    output = Path(audit.OUTPUT_RELATIVE / audit.REPORT_RELATIVE)
    arguments = [
        "research", "audit-curry-ledger-handoff",
        "--baseline-dir", audit.BASELINE_RELATIVE.as_posix(),
        "--runner", (audit.OUTPUT_RELATIVE / audit.RUNNER_RELATIVE).as_posix(),
        "--build-record", (audit.OUTPUT_RELATIVE / audit.BUILD_RECORD_RELATIVE).as_posix(),
        "--output", output.as_posix(),
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    seen = {}
    report = {"status": "failed", "native_calls": 0}

    def fake_run(args):
        seen.update(vars(args))
        return report

    monkeypatch.setattr(audit, "run_audit", fake_run)
    assert research.main() == 1
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == report
    assert seen["command"] == "audit-curry-ledger-handoff"
    assert seen["runner"] == Path(audit.OUTPUT_RELATIVE / audit.RUNNER_RELATIVE)


def test_early_source_identity_failure_saves_schema_valid_report_without_runner():
    repo = _scratch() / "synthetic-repo"
    repo.mkdir()
    baseline, output_root, runner, args = _fixed_root(repo)
    runner_calls = []

    def source_fails(_repo):
        raise ValueError("synthetic_source_capture_failed")

    report = audit.run_audit(
        args, repo=repo, source_collector=source_fails,
        process_runner=lambda *a, **k: runner_calls.append((a, k)),
    )
    assert report["status"] == "failed"
    assert report["failure_checkpoint"] == "acceptance_delivery"
    assert not runner_calls
    assert (output_root / audit.REPORT_RELATIVE).is_file()
    assert audit.validate_report(report)
    schema_path = Path(__file__).resolve().parents[1] / "schemas/curry-ledger-handoff-audit-v1.schema.json"
    schema = json.loads(schema_path.read_bytes())
    jsonschema.Draft202012Validator(schema).validate(report)
    assert not (baseline / "research/calls.jsonl").exists()
