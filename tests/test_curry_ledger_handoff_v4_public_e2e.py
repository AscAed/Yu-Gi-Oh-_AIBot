"""Public CLI success path for the synthetic Curry handoff V4 audit."""
from __future__ import annotations

import ctypes
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from types import SimpleNamespace

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import research
from tests.support.curry_ledger_handoff_v4_e2e import (
    V4_STAGE1_STDOUT,
    build_synthetic_handoff_v4_tree,
    stage1_stdout_bytes,
)
from tests.support.curry_ledger_handoff_v3_e2e import write_synthetic_v4_runner
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
            "consumed": 1, "completed": 1, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 7,
        },
    }


def _trace() -> bytes:
    rows = []
    for phase, event in handoff.TRACE_EVENTS:
        row = {"phase": phase, "event": event}
        if event == "end":
            row["elapsed_ns"] = 23
        rows.append(json.dumps(row, separators=(",", ":")))
    return ("\n".join(rows) + "\n").encode("utf-8")


def _forbid_process_and_ffi(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args, **_kwargs):
        raise AssertionError("native_process_or_ffi_forbidden_in_synthetic_e2e")

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, denied)
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        if hasattr(ctypes, name):
            monkeypatch.setattr(ctypes, name, denied)


def _forbid_writable_ledger(monkeypatch: pytest.MonkeyPatch, ledger_path: Path) -> None:
    target = ledger_path.resolve()
    original_open = Path.open

    def guarded_open(self, mode="r", *args, **kwargs):
        if self.resolve() == target and any(flag in mode for flag in ("w", "a", "x", "+")):
            raise AssertionError("writable_journal_forbidden_in_synthetic_audit")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def _synthetic_bound_v4_schema(report: dict) -> dict:
    """Validate source hashes by shape; production code still pins real files."""
    schema_path = ROOT / handoff.AUDIT_VERSIONS[4].schema_path
    schema = json.loads(schema_path.read_bytes())
    previous_schema = schema["properties"]["previous_v3_failed_source"]["properties"]
    fixed_production_pins = {
        "V4_PREVIOUS_V3_REPORT_SHA256": "b0c8aa022a02b00ad546a37d04890a36c14eeeb29082447aef4def35b6fe10bf",
        "V4_PREVIOUS_V3_DELIVERY_SHA256": "444b3e3f24152969bb210e1b607b21cc0475469578a6222c6105b57ac0b74911",
        "V4_PREVIOUS_V3_BUILD_RECORD_SHA256": "b87073c899124942148c623fe1f26e412172f10f38dd1d1009a897bb3f5e08b7",
        "V4_PREVIOUS_V3_RUNNER_SHA256": "6f6cc47b090525f49fe4c443a91a0a63889d4b4284a1bad3b38d65086f2a7c44",
        "V4_PREVIOUS_V3_ARCHIVE_SHA256": "80366616585ca58e59fac4fbabc793c66ce90bd0611e5da3558bff5c66255deb",
        "V4_PREVIOUS_V3_LIST_SHA256": "7d05667aed55f0c1b03c0be0073afb3f45a2236bde5471975cceeecd48d5964c",
        "V4_PREVIOUS_V3_FINAL_ARCHIVE_SHA256": "23206ba24d4c2607239048fdba1e3060197f868f830cb1b4de6c5d8c77a8e8d8",
        "V4_PREVIOUS_V3_FINAL_LIST_SHA256": "b93a61b80295f4c3c18a2f1e537de55ffa3e0deb9f0bbbb473b1f9bb8089f08d",
    }
    for name, expected in fixed_production_pins.items():
        assert getattr(handoff, name) == expected
    hash_def = schema["$defs"]["hash"]
    nullable_hash_def = schema["$defs"]["nullableHash"]
    assert hash_def.get("pattern") == "^[a-f0-9]{64}$"
    assert nullable_hash_def["oneOf"] == [
        {"type": "null"}, {"$ref": "#/$defs/hash"},
    ]
    for field in (
        "report_sha256", "delivery_sha256", "runner_sha256",
        "build_record_sha256", "source_archive_sha256", "source_file_list_sha256",
        "final_delivery_sha256", "final_source_archive_sha256",
        "final_source_file_list_sha256",
    ):
        assert previous_schema[field].get("$ref") in (
            "#/$defs/hash", "#/$defs/nullableHash",
        )
        digest = report["previous_v3_failed_source"][field]
        assert isinstance(digest, str) and len(digest) == 64
        assert all(character in "0123456789abcdef" for character in digest)
    return schema


def _invoke_public_v4_audit(monkeypatch, capsys, tree):
    repo = tree.repo
    runner, _source = write_synthetic_v4_runner(repo)
    output_root = repo / handoff.V4_OUTPUT_RELATIVE
    argv = [
        "research", "audit-curry-ledger-handoff", "--report-version", "4",
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
            (repo / handoff.BASELINE_RELATIVE / "research/manifest.json").read_bytes()
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
    return exit_code, captured, process_calls, audit_exceptions, runner, output_root


def test_public_research_cli_runs_complete_synthetic_v4_audit(monkeypatch, capsys):
    scratch = ROOT / "target/curry-ledger-handoff-v4-tests" / ("public-cli-" + uuid.uuid4().hex)
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v4_tree(scratch / "synthetic")
    repo = tree.repo
    output_root = repo / handoff.V4_OUTPUT_RELATIVE
    ledger_before = tree.ledger_path.read_bytes()
    baseline_root = repo / handoff.BASELINE_RELATIVE
    # The actual process artifact names are pinned in the sidecar. Check the
    # exact golden bytes through that authenticated metadata instead of a
    # guessed path. Only the reservation ID varies with the generated V3
    # source tree; the remaining fourteen-field shape and values are local
    # hand-written oracle data.
    expected_stdout = stage1_stdout_bytes(tree.option_spec)
    sidecar = json.loads((baseline_root / "stage-1-process-diagnostic.json").read_bytes())
    stdout_path = baseline_root / sidecar["stdout"]["path"]
    assert stdout_path.read_bytes() == expected_stdout
    assert json.loads(stdout_path.read_bytes()) == {
        **V4_STAGE1_STDOUT,
        "reservation_id": tree.option_spec.reservation_id,
    }

    exit_code, captured, process_calls, audit_exceptions, runner, output_root = (
        _invoke_public_v4_audit(monkeypatch, capsys, tree)
    )
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
    assert report["checks"] == {name: "passed" for name in handoff.V4_CHECK_NAMES}
    assert report["native_calls"] == 0
    assert report["execution_ready"] is False
    assert report["accounting"] == {
        "scope": "curry-option-verification-v1",
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
    roles = [item["role"] for item in report["inputs"]]
    assert len(roles) == 156
    assert len(roles) == len(set(roles))
    assert len([role for role in roles if role.startswith("v3_source_")]) == 100
    assert handoff.V4_PREVIOUS_V3_INPUT_ROLES <= set(roles)
    assert handoff.V4_STAGE1_DIAGNOSTIC_INPUT_ROLES <= set(roles)
    assert report["previous_v3_failed_source"]["status"] == "failed"
    assert report["previous_v3_failed_source"]["failure_checkpoint"] == "stage1_parent_receipt"
    assert report["previous_v3_failed_source"]["diagnostic"] == (
        "curry_saved_stage_process_output_invalid"
    )
    assert report["previous_v3_failed_source"]["file_count"] == 563
    assert report["previous_v3_failed_source"]["final_file_count"] == 564
    assert report["previous_v3_failed_source"]["source_delta"] == handoff.V4_ALLOWED_SOURCE_DELTA
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

    schema = _synthetic_bound_v4_schema(report)
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
    assert json.loads((output_root / handoff.REPORT_RELATIVE).read_bytes()) == report
    assert tree.ledger_path.read_bytes() == ledger_before
    assert not tree.stage2_receipt_path.exists()


def test_v4_rejects_authenticated_stage1_stdout_mutation_before_saved_input_process(
    monkeypatch, capsys,
):
    scratch = ROOT / "target/curry-ledger-handoff-v4-tests" / ("stdout-mutation-" + uuid.uuid4().hex)
    scratch.mkdir(parents=True, exist_ok=False)
    bad_stdout = lambda option_spec: stage1_stdout_bytes(
        option_spec, overrides={"planning_total": 41},
    )
    tree = build_synthetic_handoff_v4_tree(
        scratch / "synthetic", stage1_stdout=bad_stdout,
    )
    baseline_root = tree.repo / handoff.BASELINE_RELATIVE
    sidecar = json.loads((baseline_root / "stage-1-process-diagnostic.json").read_bytes())
    stdout_path = baseline_root / sidecar["stdout"]["path"]
    raw_stdout = stdout_path.read_bytes()
    assert raw_stdout == bad_stdout(tree.option_spec)
    assert json.loads(raw_stdout)["planning_total"] == 41

    exit_code, captured, process_calls, audit_exceptions, _runner, output_root = (
        _invoke_public_v4_audit(monkeypatch, capsys, tree)
    )
    assert exit_code != 0
    report = json.loads(captured.out)
    assert report["status"] == "failed"
    assert report["failure_checkpoint"] == "stage1_parent_receipt"
    assert report["diagnostic"] == "curry_saved_stage_process_output_invalid"
    assert process_calls == []
    assert not audit_exceptions
    schema = _synthetic_bound_v4_schema(report)
    jsonschema.Draft202012Validator(schema).validate(report)
    assert handoff.validate_report(
        report, _sources=tree.sources, repo=tree.repo,
        source_collector=synthetic_source_identity,
        _reservation_profile=tree.reservation_profile,
        _reservation_spec=tree.reservation_spec,
        _option_spec=tree.option_spec,
        _candidate_spec=tree.candidate_spec,
    )
    saved = output_root / handoff.REPORT_RELATIVE
    assert saved.is_file()
    assert json.loads(saved.read_bytes()) == report
