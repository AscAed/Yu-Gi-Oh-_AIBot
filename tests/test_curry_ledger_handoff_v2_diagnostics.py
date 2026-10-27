from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from ygo_eval import curry_ledger_handoff_audit as audit


@pytest.fixture
def tmp_path() -> Path:
    # Pytest's shared Windows basetemp is ACL-restricted on this machine.
    # Keep synthetic evidence in the repository's ignored test area instead.
    root = Path(__file__).resolve().parents[1] / "target" / "curry-ledger-handoff-v2-tests"
    path = root / f"diagnostics-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _trace() -> bytes:
    rows = []
    for phase, event in audit.TRACE_EVENTS:
        row = {"phase": phase, "event": event}
        if event == "end":
            row["elapsed_ns"] = 11
        rows.append(json.dumps(row, separators=(",", ":")))
    return ("\n".join(rows) + "\n").encode()


def _saved_result(context: str, identity: str) -> bytes:
    value = {
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
            "consumed": 1,
            "completed": 1,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": 7,
        },
    }
    return json.dumps(value, separators=(",", ":")).encode()


def _process_record(output_root: Path, stdout: bytes, stderr: bytes, return_code: int) -> dict:
    from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

    (output_root / "process-diagnostics").mkdir(parents=True, exist_ok=True)
    record, completed = capture_process_diagnostic(
        ["synthetic-inert-runner"], cwd=output_root, evidence_root=output_root,
        mode=audit.RUNNER_MODE, timeout=900,
        runner=lambda *args, **kwargs: SimpleNamespace(
            returncode=return_code, stdout=stdout, stderr=stderr,
        ),
        runner_role=audit.RUNNER_ROLE,
    )
    assert completed is not None
    return record


@pytest.mark.parametrize(
    ("return_code", "stdout", "stderr", "expected_error"),
    [
        (7, b"{}", _trace(), "saved_input_runner_not_successful"),
        (0, b"{malformed", _trace(), None),
        (0, _saved_result("d" * 64, "e" * 64), b"invalid trace", "saved_input_trace_incomplete"),
    ],
    ids=("nonzero-exit", "malformed-stdout", "invalid-trace"),
)
def test_saved_input_capture_callback_precedes_all_output_validation(
    tmp_path: Path, return_code: int, stdout: bytes, stderr: bytes,
    expected_error: str | None,
):
    input_path = tmp_path / "stage-2-input.json"
    input_raw = b"frozen synthetic stage 2"
    input_path.write_bytes(input_raw)
    output_root = tmp_path / "audit-output"
    output_root.mkdir()
    observed: list[dict] = []
    runner_calls: list[list[str]] = []

    def process_runner(command, **kwargs):
        runner_calls.append(command)
        return SimpleNamespace(returncode=return_code, stdout=stdout, stderr=stderr)

    def on_captured(record: dict) -> None:
        # The callback must see the exact persisted record before return-code,
        # trace, or JSON validation can raise.
        assert record["mode"] == audit.RUNNER_MODE
        assert record["runner_role"] == audit.RUNNER_ROLE
        metadata_path = output_root / record["metadata_path"]
        raw_record = metadata_path.read_bytes()
        assert json.loads(raw_record) == record
        assert (output_root / record["stdout"]["path"]).read_bytes() == stdout
        assert (output_root / record["stderr"]["path"]).read_bytes() == stderr
        observed.append(json.loads(raw_record))

    call = lambda: audit._run_saved_input_audit(
        runner=tmp_path / "inert-runner.exe", input_path=input_path,
        prepared_sha256="c" * 64, context="d" * 64,
        identity_sha256="e" * 64, repo=tmp_path, output_root=output_root,
        expected_input_sha256=_sha(input_raw), process_runner=process_runner,
        on_captured=on_captured,
    )

    if expected_error == "saved_input_runner_not_successful":
        with pytest.raises(ValueError, match=expected_error):
            call()
    elif expected_error is not None:
        with pytest.raises(ValueError, match=expected_error):
            call()
    else:
        with pytest.raises((ValueError, json.JSONDecodeError)):
            call()

    assert len(runner_calls) == 1
    assert len(observed) == 1
    record = observed[0]
    assert record["return_code"] == return_code
    assert record["status"] == "completed"
    assert record["stdout"] == {
        "path": record["stdout"]["path"], "sha256": _sha(stdout), "bytes": len(stdout),
    }
    assert record["stderr"] == {
        "path": record["stderr"]["path"], "sha256": _sha(stderr), "bytes": len(stderr),
    }


def test_exact_process_diagnostic_set_accepts_capture_outputs(tmp_path: Path):
    output_root = tmp_path / "audit-output"
    output_root.mkdir()
    record = _process_record(output_root, b"{}", _trace(), 0)

    audit._require_exact_process_diagnostic_set(output_root, record)


def test_exact_process_diagnostic_set_rejects_unexpected_json_sidecar(tmp_path: Path):
    output_root = tmp_path / "audit-output"
    output_root.mkdir()
    record = _process_record(output_root, b"{}", _trace(), 0)
    unexpected = output_root / "process-diagnostics" / "unrelated.json"
    unexpected.write_text('{"status":"completed"}', encoding="utf-8")

    with pytest.raises(ValueError, match="saved_input_unexpected_diagnostic_sidecar"):
        audit._require_exact_process_diagnostic_set(output_root, record)


def _report_bound_to_capture(repo: Path, output_root: Path, record: dict) -> dict:
    capture = audit._report_template(None, version=2)
    stdout_raw = (output_root / record["stdout"]["path"]).read_bytes()
    stderr_raw = (output_root / record["stderr"]["path"]).read_bytes()
    metadata_raw = (output_root / record["metadata_path"]).read_bytes()
    capture["runner"].update({
        "return_code": record["return_code"],
        "process_status": record["status"],
        "diagnostic_sha256": _sha(audit.canonical(record)),
        "stdout_sha256": _sha(stdout_raw),
        "stdout_bytes": len(stdout_raw),
        "stderr_sha256": _sha(stderr_raw),
        "stderr_bytes": len(stderr_raw),
    })
    capture["runner"]["process_capture"].update({
        "metadata_path": record["metadata_path"],
        "metadata_sha256": _sha(metadata_raw),
        "stdout_path": record["stdout"]["path"],
        "stderr_path": record["stderr"]["path"],
    })
    return capture


def test_report_revalidation_authenticates_raw_process_diagnostic_bytes(tmp_path: Path):
    repo = tmp_path / "repo"
    output_root = repo / audit.V2_OUTPUT_RELATIVE
    output_root.mkdir(parents=True)
    record = _process_record(output_root, b"not-json", _trace(), 3)
    report = _report_bound_to_capture(repo, output_root, record)

    assert audit.validate_report(report, repo=repo)

    stdout_path = output_root / record["stdout"]["path"]
    stdout_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="curry_handoff_process_capture_content_mismatch"):
        audit.validate_report(report, repo=repo)


def test_v2_rechecks_include_the_persisted_process_diagnostics_tree(monkeypatch):
    values = {
        "workspace": {"identity": "w"},
        "previous_failure_tree": "previous",
        "baseline_tree": "baseline",
        "reservation_tree": "reservation",
        "ledger": "ledger",
        "runner_build": "build",
        "process_diagnostics": {"tree": "diagnostics"},
        "stage2_receipt_absent": True,
    }

    def sample(*, only_names=None, **_kwargs):
        name = next(iter(only_names))
        return {name: values[name]}

    monkeypatch.setattr(audit, "_collect_v2_samples", sample)
    workspace = Path(__file__).resolve().parents[1]
    statuses = audit._v2_recheck_statuses(
        before=dict(values), repo=workspace,
        baseline=workspace / "synthetic-baseline",
        output_root=workspace / "synthetic-output",
        previous_root=workspace / "synthetic-previous",
        reservation_root=workspace / "synthetic-reservation",
        source_collector=lambda _path: values["workspace"],
        stage2_receipt=workspace / "synthetic-stage2.json",
        ledger_path=workspace / "synthetic-ledger.jsonl",
    )

    assert statuses["process_diagnostics"] == "consistent"


def _fixed_v2_paths(repo: Path) -> tuple[Path, argparse.Namespace]:
    (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
    baseline = repo / audit.BASELINE_RELATIVE
    baseline.mkdir(parents=True)
    root = repo / audit.V2_OUTPUT_RELATIVE
    artifacts = root / "native-artifacts"
    artifacts.mkdir(parents=True)
    runner = artifacts / audit.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic inert V2 runner")
    (root / audit.BUILD_RECORD_RELATIVE).write_bytes(b"synthetic build record")
    (root / audit.SOURCE_ARCHIVE_RELATIVE).write_bytes(b"synthetic inert source zip")
    (root / audit.SOURCE_FILE_LIST_RELATIVE).write_bytes(b"synthetic source list")
    args = argparse.Namespace(
        baseline_dir=baseline,
        runner=runner,
        build_record=root / audit.BUILD_RECORD_RELATIVE,
        output=root / audit.REPORT_RELATIVE,
        report_version=2,
    )
    return baseline, args


@pytest.mark.parametrize(
    ("return_code", "stdout", "stderr"),
    [
        (9, b"{}", _trace()),
        (0, b"{bad json", _trace()),
        (0, _saved_result("a" * 64, "b" * 64), b"bad trace"),
    ],
    ids=("outer-report-nonzero", "outer-report-malformed-json", "outer-report-invalid-trace"),
)
def test_v2_failure_report_uses_the_current_capture_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    return_code: int, stdout: bytes, stderr: bytes,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    baseline, args = _fixed_v2_paths(repo)
    output_root = repo / audit.V2_OUTPUT_RELATIVE
    input_path = baseline / "research" / "stage-2-input.json"
    input_path.parent.mkdir(parents=True)
    input_raw = b"authenticated synthetic stage 2"
    input_path.write_bytes(input_raw)
    context, identity = "a" * 64, "b" * 64
    stage2_receipt = baseline / "research" / "stage-2.json"
    reservation_root = repo / "synthetic-reservation"
    ledger_path = baseline / "research" / "calls.jsonl"
    previous_root = repo / audit.OUTPUT_RELATIVE
    previous_root.mkdir(parents=True)

    samples = {
        "workspace": {"head": "synthetic", "identity": "c" * 64, "files": {"x": "d" * 64}},
        "previous_failure_tree": "previous-tree",
        "baseline_tree": "baseline-tree",
        "reservation_tree": "reservation-tree",
        "runner_build": "runner-build",
        "process_diagnostics": "initial-diagnostics-tree",
        "stage2_receipt_absent": True,
        "ledger": _sha(b"synthetic ledger"),
    }
    monkeypatch.setattr(audit, "_collect_v2_samples", lambda **kwargs: dict(samples))
    monkeypatch.setattr(
        audit,
        "_verify_previous_failed_attempt",
        lambda *_args, **_kwargs: {
            "root": previous_root,
            "inputs": [],
            "record": {
                "report_sha256": audit.PREVIOUS_V1_REPORT_SHA256,
                "status": "failed",
                "failure_checkpoint": "acceptance_delivery",
                "diagnostic": "curry_handoff_acceptance_accounting_invalid",
                "runner_sha256": "1" * 64,
                "build_record_sha256": "2" * 64,
                "source_archive_sha256": "3" * 64,
                "source_file_list_sha256": "4" * 64,
            },
        },
    )
    acceptance = {
        "native_result": {"stage_2": {"runner_return_code": 2}},
    }
    monkeypatch.setattr(
        audit,
        "_verify_acceptance_delivery",
        lambda *_args, **_kwargs: (acceptance, {}, b"acceptance", b"delivery"),
    )
    chain_record = {
        "native_source_identity": "5" * 64,
        "native_file_count": 544,
        "final_source_identity": "6" * 64,
        "final_file_count": 545,
        "source_delta": audit.ALLOWED_SOURCE_DELTA,
        "parent_view_retained": True,
        "parent_lock_path": "crates/ygo-engine-adapter/examples/curry-option-validation.rs",
        "archived_static_return_code": 2,
        "historical_actual_exit_code": None,
    }
    monkeypatch.setattr(
        audit,
        "_verify_final_build_chain",
        lambda *_args, **_kwargs: {
            "record": chain_record,
            "inputs": [],
            "reservation_root": reservation_root,
            "stage2_receipt": stage2_receipt,
            "ledger_path": ledger_path,
        },
    )

    def fake_snapshot(_repo, _baseline, *, mark, **kwargs):
        mark("reservation_and_history", True)
        mark("frozen_scope_inputs", True)
        mark("stage1_parent_receipt", True)
        mark("stage2_saved_intent", True)
        return {
            "report_binding": {
                "acceptance_sha256": audit.ACCEPTANCE_SHA256,
                "delivery_sha256": audit.DELIVERY_SHA256,
                "context": context,
                "manifest_sha256": "8" * 64,
                "prepared_sha256": "9" * 64,
                "stage1_receipt_sha256": "a" * 64,
                "stage2_input_sha256": _sha(input_raw),
                "stage2_request_sha256": "b" * 64,
            },
            "inputs": [],
            "protected": {},
            "initial": {
                "workspace": samples["workspace"],
                "baseline_tree": samples["baseline_tree"],
                "baseline_evidence": "evidence",
                "reservation_tree": samples["reservation_tree"],
                "stage2_receipt_absent": True,
            },
            "stage2_input": input_path,
            "manifest": {"context": context, "assets": {"ordinary": {"identity": identity}}},
            "prepared_sha256": "c" * 64,
        }

    monkeypatch.setattr(audit, "_snapshot_fixed_sources", fake_snapshot)
    rechecks = {
        name: "consistent" for name in (
            "workspace", "previous_failure_tree", "baseline_tree", "reservation_tree",
            "ledger", "runner_build", "process_diagnostics",
        )
    }
    rechecks["stage2_receipt_absent"] = True
    monkeypatch.setattr(audit, "_v2_recheck_statuses", lambda **kwargs: dict(rechecks))

    process_calls: list[list[str]] = []

    def process_runner(command, **kwargs):
        process_calls.append(command)
        return SimpleNamespace(returncode=return_code, stdout=stdout, stderr=stderr)

    report = audit.run_audit(
        args,
        repo=repo,
        process_runner=process_runner,
        runner_build_verifier=lambda *_args: {
            "runner_sha256": "d" * 64,
            "build_record_sha256": "e" * 64,
            "build_record_identity": "f" * 64,
            "source_identity": "0" * 64,
            "source_file_count": 1,
            "inputs": [],
        },
        source_collector=lambda _repo: samples["workspace"],
        clock=lambda: 100.0,
    )

    assert len(process_calls) == 1
    assert report["status"] == "failed"
    assert report["failure_checkpoint"] == "saved_input_audit"
    runner = report["runner"]
    assert runner["return_code"] == return_code
    assert runner["process_status"] == "completed"
    assert runner["stdout_sha256"] == _sha(stdout)
    assert runner["stdout_bytes"] == len(stdout)
    assert runner["stderr_sha256"] == _sha(stderr)
    assert runner["stderr_bytes"] == len(stderr)
    assert runner["diagnostic_sha256"] is not None
    assert list((output_root / "process-diagnostics").glob("*.json"))
    assert audit.validate_report(report)
