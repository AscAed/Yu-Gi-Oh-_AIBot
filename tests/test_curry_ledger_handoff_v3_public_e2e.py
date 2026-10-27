"""Public CLI success-path test for the synthetic Curry handoff V3 audit."""
from __future__ import annotations

import ctypes
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import uuid
from types import SimpleNamespace

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import research
from tests.support.curry_ledger_handoff_v3_e2e import (
    build_synthetic_handoff_v3_tree,
    write_synthetic_v3_runner,
)
from tests.support.curry_recovery_e2e import synthetic_source_identity


ROOT = Path(__file__).resolve().parents[1]


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
            "consumed": 1,
            "completed": 1,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": 7,
        },
    }


def _trace() -> bytes:
    rows = []
    for phase, event in handoff.TRACE_EVENTS:
        value = {"phase": phase, "event": event}
        if event == "end":
            value["elapsed_ns"] = 23
        rows.append(json.dumps(value, separators=(",", ":")))
    return ("\n".join(rows) + "\n").encode("utf-8")


def _forbid_process_and_ffi(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args, **_kwargs):
        raise AssertionError("native_process_or_ffi_forbidden_in_synthetic_e2e")

    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "call", denied)
    monkeypatch.setattr(subprocess, "check_call", denied)
    monkeypatch.setattr(subprocess, "check_output", denied)
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        if hasattr(ctypes, name):
            monkeypatch.setattr(ctypes, name, denied)


def _forbid_writable_ledger(monkeypatch: pytest.MonkeyPatch, ledger_path: Path) -> None:
    ledger_path = ledger_path.resolve()
    original_open = Path.open

    def guarded_open(self, mode="r", *args, **kwargs):
        if self.resolve() == ledger_path and any(flag in mode for flag in ("w", "a", "x", "+")):
            raise AssertionError("writable_journal_forbidden_in_synthetic_audit")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_public_research_cli_runs_complete_synthetic_v3_audit(monkeypatch, capsys):
    scratch = ROOT / "target/curry-ledger-handoff-v3-tests" / ("public-cli-" + uuid.uuid4().hex)
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v3_tree(scratch / "synthetic")
    repo = tree.repo
    runner, source = write_synthetic_v3_runner(repo)
    output_root = repo / handoff.V3_OUTPUT_RELATIVE
    ledger_before = tree.ledger_path.read_bytes()
    argv = [
        "research", "audit-curry-ledger-handoff", "--report-version", "3",
        "--baseline-dir", str(repo / handoff.BASELINE_RELATIVE),
        "--runner", str(runner),
        "--build-record", str(output_root / handoff.BUILD_RECORD_RELATIVE),
        "--output", str(output_root / handoff.REPORT_RELATIVE),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    real_run_audit = handoff.run_audit
    process_calls: list[tuple[list[str], dict]] = []
    audit_exceptions: list[str] = []
    clock_values = iter((100.0, 100.5))

    def fake_process(command, **kwargs):
        process_calls.append((list(command), dict(kwargs)))
        manifest = json.loads(
            (repo / "data/runtime/p1-curry-option-verification-native-2026-10-25"
             / "research/manifest.json").read_bytes()
        )
        stdout = json.dumps(
            _saved_result(manifest["context"], manifest["assets"]["ordinary"]["identity"]),
            separators=(",", ":"),
        ).encode("utf-8")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=_trace())

    def injected_run_audit(args):
        try:
            return real_run_audit(
                args, repo=repo, process_runner=fake_process,
                source_collector=synthetic_source_identity,
                clock=lambda: next(clock_values),
                _sources=tree.sources,
                _reservation_profile=tree.reservation_profile,
                _reservation_spec=tree.reservation_spec,
                _option_spec=tree.option_spec,
                _candidate_spec=tree.candidate_spec,
            )
        except Exception as error:
            audit_exceptions.append(f"{type(error).__name__}:{error}")
            raise

    monkeypatch.setattr(handoff, "run_audit", injected_run_audit)
    _forbid_process_and_ffi(monkeypatch)
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)

    exit_code = research.main()
    captured = capsys.readouterr()
    if exit_code != 0:
        saved = output_root / handoff.REPORT_RELATIVE
        saved_text = saved.read_text(encoding="utf-8") if saved.is_file() else "<no report saved>"
        pytest.fail(
            f"public_cli_exit={exit_code}; stdout={captured.out!r}; "
            f"stderr={captured.err!r}; audit_exceptions={audit_exceptions!r}; "
            f"saved_report={saved_text}"
        )
    report = json.loads(captured.out)
    assert report["status"] == "passed"
    assert report["checks"] == {name: "passed" for name in handoff.V3_CHECK_NAMES}
    assert report["native_calls"] == 0
    assert report["execution_ready"] is False
    assert report["accounting"] == {
        "certified_historical_consumed": 32,
        "policy_reserved": 7,
        "planning_base": 39,
        "new_consumed": 1,
        "certified_consumed_including_new": 33,
        "planning_total": 40,
        "unknown": 0,
        "old_confirmation_actual_consumed": None,
        "actual_all_history_cumulative": None,
    }
    assert len([row for row in report["inputs"] if row["role"].startswith("v3_source_")]) == 100
    assert report["previous_failed_attempt"]["status"] == "failed"
    assert report["previous_v2_failed_attempt"]["failure_checkpoint"] == "previous_failed_source"
    assert report["v2_final_source"]["source_delta"] == handoff.ALLOWED_V2_SOURCE_DELTA
    assert len(process_calls) == 1
    command, kwargs = process_calls[0]
    assert command[0] == str(runner)
    assert command[command.index("--input-sha") + 1] == hashlib.sha256(
        tree.stage2_input_path.read_bytes()
    ).hexdigest()
    assert command[command.index("--prepared-sha256") + 1] == hashlib.sha256(
        (tree.stage2_input_path.parent / "prepared.json").read_bytes()
    ).hexdigest()
    assert "--audit-saved-input-only" in command and "--trace-stderr" in command
    assert kwargs["timeout"] == 900 and kwargs["check"] is False

    schema = json.loads((ROOT / handoff.AUDIT_VERSIONS[3].schema_path).read_bytes())
    schema_validator = jsonschema.Draft202012Validator(schema)
    schema_validator.validate(report)
    assert handoff.validate_report(
        report, _sources=tree.sources, repo=repo,
        source_collector=synthetic_source_identity,
        _reservation_profile=tree.reservation_profile,
        _reservation_spec=tree.reservation_spec,
        _option_spec=tree.option_spec,
        _candidate_spec=tree.candidate_spec,
    )
    invalid_successes = []
    empty_inputs = json.loads(json.dumps(report))
    empty_inputs["inputs"] = []
    invalid_successes.append(empty_inputs)
    wrong_accounting = json.loads(json.dumps(report))
    wrong_accounting["accounting"]["planning_total"] = 999
    invalid_successes.append(wrong_accounting)
    success_with_diagnostic = json.loads(json.dumps(report))
    success_with_diagnostic["diagnostic"] = "audit_failed"
    invalid_successes.append(success_with_diagnostic)
    duplicate_role = json.loads(json.dumps(report))
    duplicate_role["inputs"][-1]["role"] = duplicate_role["inputs"][0]["role"]
    invalid_successes.append(duplicate_role)
    unexplained_stability_failure = json.loads(json.dumps(report))
    unexplained_stability_failure["status"] = "failed"
    unexplained_stability_failure["failure_checkpoint"] = "input_stability"
    unexplained_stability_failure["checks"]["input_stability"] = "failed"
    unexplained_stability_failure["diagnostic"] = "curry_handoff_input_stability_failed"
    invalid_successes.append(unexplained_stability_failure)
    for invalid in invalid_successes:
        with pytest.raises(jsonschema.ValidationError):
            schema_validator.validate(invalid)
        with pytest.raises(ValueError):
            handoff.validate_report(
                invalid, _sources=tree.sources, repo=repo,
                source_collector=synthetic_source_identity,
                _reservation_profile=tree.reservation_profile,
                _reservation_spec=tree.reservation_spec,
                _option_spec=tree.option_spec,
                _candidate_spec=tree.candidate_spec,
            )

    explained_stability_failure = json.loads(json.dumps(report))
    explained_stability_failure["status"] = "failed"
    explained_stability_failure["failure_checkpoint"] = "input_stability"
    explained_stability_failure["checks"]["input_stability"] = "failed"
    explained_stability_failure["diagnostic"] = "curry_handoff_runner_build_unstable"
    explained_stability_failure["stability_rechecks"]["runner_build"] = "changed"
    explained_stability_failure["stability"]["runner_build_stable"] = "failed"
    schema_validator.validate(explained_stability_failure)
    assert handoff.validate_report(
        explained_stability_failure, _sources=tree.sources, repo=repo,
        source_collector=synthetic_source_identity,
        _reservation_profile=tree.reservation_profile,
        _reservation_spec=tree.reservation_spec,
        _option_spec=tree.option_spec,
        _candidate_spec=tree.candidate_spec,
    )

    v1_root = repo / handoff.OUTPUT_RELATIVE
    v2_root = repo / handoff.V2_OUTPUT_RELATIVE
    assert v1_root != v2_root
    assert handoff._previous_v1_audit_runner_path(v1_root) == (
        v1_root / "native-artifacts/curry-option-validation.exe"
    )
    assert v2_root / handoff.RUNNER_RELATIVE == (
        v2_root / "native-artifacts/curry-option-validation.exe"
    )
    v1_decoy = v1_root / "native-artifacts/curry-option-verification.exe"
    v1_decoy.write_bytes(b"wrong-root decoy; inert\n")
    actual_v1_runner = v1_root / handoff.PREVIOUS_V1_RUNNER_RELATIVE_CORRECT
    actual_v1_bytes = actual_v1_runner.read_bytes()
    assert handoff._verify_v1_audit_source_v3(
        repo, _sources=tree.sources,
    )["record"]["runner_sha256"] == hashlib.sha256(actual_v1_bytes).hexdigest()
    actual_v1_runner.unlink()
    try:
        with pytest.raises(FileNotFoundError):
            handoff._verify_v1_audit_source_v3(repo, _sources=tree.sources)
    finally:
        actual_v1_runner.write_bytes(actual_v1_bytes)

    actual_v2_runner = v2_root / handoff.RUNNER_RELATIVE
    actual_v2_bytes = actual_v2_runner.read_bytes()
    v2_decoy = v2_root / "native-artifacts/curry-option-verification.exe"
    v2_decoy.write_bytes(b"wrong V2 runner name; inert\n")
    assert handoff._verify_v2_audit_source_v3(
        repo, _sources=tree.sources,
    )["record"]["runner_sha256"] == hashlib.sha256(actual_v2_bytes).hexdigest()
    v2_report_path = v2_root / handoff.REPORT_RELATIVE
    original_v2_report = v2_report_path.read_bytes()
    v2_node = tree.sources.child("previous_v2_failed_attempt")
    for field, invalid_value in (("status", "passed"),
                                 ("failure_checkpoint", "acceptance_delivery")):
        invalid_v2 = json.loads(original_v2_report)
        invalid_v2[field] = invalid_value
        invalid_raw = json.dumps(
            invalid_v2, ensure_ascii=False, sort_keys=True, indent=2,
        ).encode("utf-8") + b"\n"
        v2_report_path.write_bytes(invalid_raw)
        altered_node = replace(v2_node, files=tuple(
            replace(pin, sha256=hashlib.sha256(invalid_raw).hexdigest())
            if pin.role == "previous_v2_report" else pin
            for pin in v2_node.files
        ))
        altered_sources = replace(
            tree.sources,
            children=tuple(altered_node if child.role == "previous_v2_failed_attempt"
                           else child for child in tree.sources.children),
        )
        with pytest.raises(ValueError, match="curry_handoff_v2_failure_binding_invalid"):
            handoff._verify_v2_audit_source_v3(repo, _sources=altered_sources)
        v2_report_path.write_bytes(original_v2_report)
    actual_v2_runner.unlink()
    try:
        with pytest.raises(FileNotFoundError):
            handoff._verify_v2_audit_source_v3(repo, _sources=tree.sources)
    finally:
        actual_v2_runner.write_bytes(actual_v2_bytes)
    saved = json.loads((output_root / handoff.REPORT_RELATIVE).read_bytes())
    assert saved == report
    assert tree.ledger_path.read_bytes() == ledger_before
    assert not tree.stage2_receipt_path.exists()
    assert len(list((output_root / "process-diagnostics").iterdir())) == 3
