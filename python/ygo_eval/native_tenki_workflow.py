"""Private scope-parameterized runner and stage workflow primitives.

The confirmation and validation scopes provide their own fixed policies and
receipt validators while sharing this orchestration core.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import math
from pathlib import Path
import subprocess
import time
import uuid
import hashlib
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class WorkflowSpec:
    scope: str
    limit: int
    wall_seconds: int
    worker_timeout_seconds: int
    runner_role: str
    stage_kind: str
    stage_report_kind: str
    input_seal_kind: str
    trace_stderr: bool = False
    timeout_error_prefix: str = "workflow"


def process_diagnostic_sha256(root: Path, record: dict, *, runner_role: str,
                              safe_file: Callable[[Path], Path],
                              strict_json: Callable[[bytes], Any]) -> str:
    if (not isinstance(record, dict) or record.get("runner_role") != runner_role
            or not isinstance(record.get("metadata_path"), str)
            or not isinstance(record.get("stdout"), dict)
            or not isinstance(record.get("stderr"), dict)):
        raise ValueError("process_diagnostic_metadata_invalid")
    metadata_path = safe_file(root / record["metadata_path"])
    metadata = metadata_path.read_bytes()
    if strict_json(metadata) != record:
        raise ValueError("process_diagnostic_metadata_mismatch")
    for channel in ("stdout", "stderr"):
        item = record[channel]
        relative = item.get("path")
        if (not isinstance(relative, str) or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or type(item.get("bytes")) is not int or item["bytes"] < 0):
            raise ValueError("process_diagnostic_output_path_invalid")
        output = safe_file(root / relative).read_bytes()
        if len(output) != item["bytes"] or hashlib.sha256(output).hexdigest() != item.get("sha256"):
            raise ValueError("process_diagnostic_output_hash_mismatch")
    return hashlib.sha256(metadata).hexdigest()


def normal_runner_timeout(started_at: Any, *, wall_seconds: int,
                          worker_timeout_seconds: int, now: float | None = None,
                          error_prefix: str = "workflow") -> float:
    if type(started_at) is not int or started_at < 0:
        raise ValueError(f"{error_prefix}_window_start_invalid")
    current = time.time() if now is None else now
    if (not isinstance(current, (int, float)) or type(current) is bool
            or not math.isfinite(current)):
        raise ValueError(f"{error_prefix}_window_clock_invalid")
    deadline = started_at + wall_seconds
    if current < started_at:
        raise ValueError(f"{error_prefix}_window_clock_before_start")
    if current + worker_timeout_seconds >= deadline:
        raise ValueError(f"{error_prefix}_window_insufficient_time")
    return float(deadline - current)


def capture_runner_process(*, runner: Path, input_path: Path, repo: Path, root: Path,
                           mode: str, runner_role: str, input_sha256: str,
                           prepared_hash: str | None = None, timeout: float,
                           trace_stderr: bool = False,
                           process_runner: Callable[..., Any] | None = None):
    """Run one runner mode and persist raw process streams before parsing them."""
    from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

    command = [str(runner), str(input_path), "--input-sha", input_sha256]
    if mode == "preflight_only":
        command.append("--preflight-only")
    elif mode == "verify_recorded":
        command.append("--verify-recorded")
    elif mode == "stats":
        command.append("--stats")
    elif mode == "normal":
        if prepared_hash is None:
            raise ValueError("workflow_prepared_report_hash_required")
        command.extend(["--prepared-sha256", prepared_hash])
    else:
        raise ValueError("workflow_runner_mode_invalid")
    if mode in ("normal", "preflight_only") and trace_stderr:
        command.append("--trace-stderr")
    if mode == "normal" and (not isinstance(timeout, (int, float))
                              or type(timeout) is bool or not math.isfinite(timeout)
                              or timeout <= 0):
        raise ValueError("workflow_window_timeout_required")
    record, completed = capture_process_diagnostic(
        command,
        repo,
        root,
        mode=mode,
        timeout=timeout,
        runner=process_runner or subprocess.run,
        runner_role=runner_role,
    )
    return record, completed


def run_six_stage_workflow(
    *, spec: WorkflowSpec, root: Path, output: Path, runner: Path, repo: Path,
    manifest: dict, prepared_hash: str, stage1_request: dict,
    expected_identity: dict, source: dict, protected: dict[Path, str],
    frozen_files: dict[Path, str], parent_stage: dict[int, int],
    derive_request: Callable[[int, dict], dict],
    save_stage_files: Callable[[Path, str, int, dict, dict, int], tuple[Path, Path]],
    invocation_for_stage: Callable[[str, Path, int, dict, dict, int], dict],
    verify_stage_intent: Callable[[Path, int, dict, dict, int], None],
    read_receipt: Callable[[Path], dict | None],
    run_process: Callable[..., tuple[dict, Any, str]],
    read_stats: Callable[[Path], tuple[dict | None, dict, str]],
    valid_stats: Callable[[Any], bool],
    missing_ledger_stats: Callable[..., dict | None],
    verify_basic_receipt: Callable[[dict, dict, str, int], None],
    validate_stage_receipt: Callable[[dict, dict, str, int, dict], Any],
    stage_report: Callable[..., dict],
    validate_report: Callable[[dict, Path], Any],
    summarize: Callable[..., dict],
    diagnostic_hash: Callable[[Path, dict], str],
    save_orchestration_diagnostic: Callable[[Path, int, str], str],
    assert_unchanged: Callable[[Path, dict, dict[Path, str]], None],
    safe_file: Callable[[Path], Path],
    immutable_write: Callable[[Path, Any], None],
    sha256: Callable[[bytes], str],
    process_exit_succeeded: Callable[[Any], bool],
    strict_json: Callable[[bytes], Any],
    unique_token: Callable[[], str] = lambda: uuid.uuid4().hex,
    clock: Callable[[], float] = time.time,
    error_types: tuple[type[BaseException], ...] = (Exception,),
) -> dict:
    """Run/recover the fixed six-stage chain using caller-owned contracts.

    File names and control flow are shared; scope-specific derivation, receipt
    validation, diagnostics, and summary contracts remain injected and fixed by
    each caller.
    """
    context = manifest["context"]
    started_at = manifest["started_at"]
    stage_reports: list[dict] = []
    diagnostic = None
    stats: dict | None = None
    last_input: Path | None = None
    normal_attempted = False

    def unchanged() -> None:
        assert_unchanged(repo, source, protected)
        for path, expected in frozen_files.items():
            if sha256(safe_file(path).read_bytes()) != expected:
                raise ValueError("workflow_frozen_file_changed")

    def reconcile_stats(input_path: Path) -> dict | None:
        nonlocal stats
        if not (output / "calls.jsonl").exists():
            stats = missing_ledger_stats(normal_attempted=normal_attempted)
            return stats
        value, process_record, _process_hash = read_stats(input_path)
        immutable_write(root / "process-diagnostics" / f"stats-{unique_token()}.json", process_record)
        stats = value if value is not None and valid_stats(value) else None
        return stats

    for stage in range(1, spec.limit + 1):
        receipt_path = output / f"stage-{stage}.json"
        report_path = output / f"stage-{stage}-report.json"
        input_path = output / f"stage-{stage}-input.json"
        process_sidecar = root / f"stage-{stage}-process-diagnostic.json"
        last_input = input_path
        stage_reason = None
        process_record = None
        process_hash = None
        calls_for_stage: int | None = None
        receipt = None
        try:
            unchanged()
            if stage == 1:
                request = copy.deepcopy(stage1_request)
            else:
                parent_path = output / f"stage-{parent_stage[stage]}.json"
                parent_receipt = strict_json(safe_file(parent_path).read_bytes())
                request = derive_request(stage, parent_receipt)
            save_stage_files(output, context, stage, request, expected_identity, started_at)
            invocation = strict_json(safe_file(input_path).read_bytes())
            if invocation != invocation_for_stage(context, output, stage, request,
                                                   expected_identity, started_at):
                raise ValueError("workflow_stage_intent_binding_invalid")
            verify_stage_intent(input_path, stage, request, expected_identity, started_at)

            receipt = read_receipt(receipt_path)
            if receipt is not None:
                process_record, completed, process_hash = run_process(
                    runner, input_path, repo, root, "verify_recorded"
                )
                verification_path = root / "process-diagnostics" / f"verify-recorded-stage-{stage}-{unique_token()}.json"
                immutable_write(verification_path, process_record)
                stdout_value = strict_json(completed.stdout) if completed is not None and process_record.get("status") == "completed" else None
                if not (isinstance(stdout_value, dict)
                        and stdout_value.get("verified_recorded") is True
                        and process_exit_succeeded(completed)
                        and stdout_value.get("native_calls") == 0):
                    raise ValueError("workflow_recorded_receipt_verification_failed")
                if report_path.exists():
                    saved_report = strict_json(safe_file(report_path).read_bytes())
                    if saved_report.get("receipt_sha256") != sha256(safe_file(receipt_path).read_bytes()):
                        raise ValueError("workflow_saved_stage_report_mismatch")
                    if not process_sidecar.exists():
                        raise ValueError("workflow_saved_stage_diagnostic_missing")
                    process_record = strict_json(safe_file(process_sidecar).read_bytes())
                    process_hash = diagnostic_hash(root, process_record)
                    if process_hash != saved_report["diagnostic_sha256"]:
                        raise ValueError("workflow_saved_stage_diagnostic_mismatch")
                    report = saved_report
                else:
                    if not process_sidecar.exists():
                        immutable_write(process_sidecar, process_record)
                    report = None
                calls_for_stage = 0
            else:
                before = reconcile_stats(input_path)
                if before is None or before.get("unknown") != 0 or before.get("reserved") != 0:
                    stage_reason = "ledger_consumption_unknown"
                elif before.get("consumed") != stage - 1 or before.get("completed") != stage - 1:
                    stage_reason = "ledger_prefix_not_ready"
                else:
                    try:
                        process_timeout = normal_runner_timeout(
                            started_at,
                            wall_seconds=spec.wall_seconds,
                            worker_timeout_seconds=spec.worker_timeout_seconds,
                            now=clock(),
                            error_prefix=spec.timeout_error_prefix,
                        )
                    except ValueError as error:
                        stage_reason = str(error)
                    else:
                        normal_attempted = True
                        process_record, completed, process_hash = run_process(
                            runner, input_path, repo, root, "normal",
                            prepared_hash=prepared_hash, timeout=process_timeout,
                        )
                        immutable_write(process_sidecar, process_record)
                        try:
                            runner_output = strict_json(completed.stdout) if completed is not None and process_record.get("status") == "completed" else None
                        except (ValueError, UnicodeDecodeError):
                            runner_output = None
                        receipt = read_receipt(receipt_path)
                        after = runner_output.get("ledger") if isinstance(runner_output, dict) else None
                        if not valid_stats(after):
                            after = reconcile_stats(input_path)
                        if valid_stats(before) and valid_stats(after):
                            delta = after["consumed"] - before["consumed"]
                            calls_for_stage = delta if delta in (0, 1) else None
                        if process_record.get("status") != "completed" or completed is None:
                            stage_reason = process_record.get("error_code") or "runner_process_incomplete"
                        elif not isinstance(runner_output, dict) or not process_exit_succeeded(completed):
                            stage_reason = "runner_output_invalid_or_nonzero"
                        elif runner_output.get("successful") is not True:
                            stage_reason = "stage_unsuccessful"

            if receipt is not None:
                verify_basic_receipt(receipt, request, context, stage)
                if receipt.get("successful") is not True:
                    stage_reason = stage_reason or receipt.get("diagnostic") or "stage_receipt_unsuccessful"
                elif stage_reason is None:
                    validate_stage_receipt(receipt, request, context, stage, expected_identity)
            else:
                stage_reason = stage_reason or "stage_receipt_unavailable"

            if process_record is None:
                stage_reason = stage_reason or "process_diagnostic_unavailable"
                process_hash = sha256(b"")
            if not report_path.exists():
                report = stage_report(context, stage, receipt, receipt_path,
                                      process_hash or sha256(b""), calls_for_stage,
                                      stage_reason, stats)
                validate_report(report, repo)
                immutable_write(report_path, report)
            else:
                report = strict_json(safe_file(report_path).read_bytes())
                validate_report(report, repo)
            stage_reports.append(report)
            unchanged()
            if stage_reason is not None or report.get("successful") is not True:
                diagnostic = stage_reason or report.get("diagnostic") or "stage_not_successful"
                break
        except error_types as error:
            diagnostic = str(error) if str(error).isidentifier() else "stage_or_frozen_input_validation_failed"
            if not report_path.exists():
                record = process_record if isinstance(process_record, dict) else None
                digest_value = process_hash or (diagnostic_hash(root, record) if record else save_orchestration_diagnostic(output, stage, diagnostic))
                report = stage_report(context, stage, receipt, receipt_path,
                                      digest_value, calls_for_stage, diagnostic, stats)
                try:
                    validate_report(report, repo)
                    immutable_write(report_path, report)
                    stage_reports.append(report)
                except (ValueError, OSError, TypeError):
                    pass
            break

    if output.joinpath("calls.jsonl").exists() and last_input is not None and runner.exists():
        try:
            stats_value, process_record, _process_hash = read_stats(last_input)
            immutable_write(root / "process-diagnostics" / f"final-stats-{unique_token()}.json", process_record)
            stats = stats_value if valid_stats(stats_value) else None
        except (ValueError, OSError, subprocess.SubprocessError, TypeError):
            stats = None
    elif normal_attempted:
        stats = None
    elif stats is None:
        stats = {"consumed": 0, "completed": 0, "unknown": 0, "reserved": 0,
                 "abandoned": 0, "limit": spec.limit}
    if stats is None and diagnostic is None:
        diagnostic = "final_ledger_statistics_unknown"
    summaries = [{key: report.get(key) for key in (
        "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
        "diagnostic_sha256", "independent_replay_matches", "ledger",
    )} for report in stage_reports]
    summary = summarize(context, summaries, stats, diagnostic)
    validate_report(summary, repo)
    immutable_write(output / "summary.json", summary)
    return summary
