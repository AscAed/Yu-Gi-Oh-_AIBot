"""End-to-end synthetic coverage for the public Curry recovery audit path."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import ctypes
import hashlib
import io
import json
import os
import subprocess
import unittest
from pathlib import Path
import uuid
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_eval import curry_input_recovery_audit as audit
from tests.support.curry_recovery_e2e import (
    build_synthetic_recovery_tree,
    synthetic_source_sampler,
)


@contextmanager
def _forbid_native_activity(processes: list[str], ledger_writes: list[str]):
    def guarded_popen(command, *args, **kwargs):
        executable = command[0] if isinstance(command, (tuple, list)) else command
        name = Path(os.fspath(executable)).name.lower()
        processes.append(name)
        raise AssertionError("process_forbidden_in_synthetic_audit")

    real_io_open = io.open
    real_builtin_open = open

    def check_open(file, mode):
        if isinstance(file, int):
            return
        path = Path(os.fspath(file))
        if path.name == "calls.jsonl" and any(flag in mode for flag in "wax+"):
            ledger_writes.append(path.as_posix())
            raise AssertionError("writable_ledger_forbidden_in_synthetic_audit")

    def guarded_io_open(file, mode="r", *args, **kwargs):
        check_open(file, mode)
        return real_io_open(file, mode, *args, **kwargs)

    def guarded_builtin_open(file, mode="r", *args, **kwargs):
        check_open(file, mode)
        return real_builtin_open(file, mode, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(subprocess, "Popen", new=guarded_popen))
        stack.enter_context(patch.object(io, "open", new=guarded_io_open))
        stack.enter_context(patch("builtins.open", new=guarded_builtin_open))
        for loader in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
            if hasattr(ctypes, loader):
                stack.enter_context(patch.object(
                    ctypes, loader,
                    side_effect=AssertionError("FFI_forbidden_in_synthetic_audit"),
                ))
        yield


class CurryRecoveryPublicAuditE2ETests(unittest.TestCase):
    def test_prompt_source_files_remain_equal_to_their_pinned_hashes(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_recovery_tree(scratch)
        from ygo_eval.native_tenki_placement_confirmation import PROMPT_BASELINE_RELATIVE

        wanted = {
            (PROMPT_BASELINE_RELATIVE / "research/stage-1.json").as_posix(),
            (PROMPT_BASELINE_RELATIVE / "research/stage-2-request.json").as_posix(),
        }
        pins = {}

        def visit(description):
            for pin in description.files:
                if pin.relative_path in wanted:
                    pins[pin.relative_path] = pin.sha256
            for child in description.children:
                visit(child)

        visit(fixture.sources)
        self.assertEqual(set(pins), wanted)
        for relative, expected in pins.items():
            actual = hashlib.sha256((fixture.repo / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_public_audit_to_output_verifies_complete_synthetic_source_tree(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        try:
            fixture = build_synthetic_recovery_tree(scratch)
            repo = fixture.repo
            args = type("Args", (), {
                "baseline_dir": repo / fixture.sources.baseline_relative,
                "output": repo / fixture.sources.output_relative_v2 / "audit-report.json",
                "report_version": 2,
            })()

            old_cwd = Path.cwd()
            processes: list[str] = []
            ledger_writes: list[str] = []
            try:
                # The verifier's fixed default preparation-report paths are
                # cwd-relative, as they are in the production CLI invocation.
                os.chdir(repo)
                with _forbid_native_activity(processes, ledger_writes):
                    with synthetic_source_sampler():
                        report = audit.audit_to_output(
                            args, repo=repo, _sources=fixture.sources,
                        )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(processes, [])
            self.assertEqual(ledger_writes, [])

            self.assertEqual(
                report["status"], "passed",
                f"checkpoint={report.get('failure_checkpoint')}; "
                f"diagnostics={report.get('diagnostics')}",
            )
            self.assertEqual(report["failure_checkpoint"], None)
            self.assertEqual(report["native_calls"], 0)
            self.assertFalse(report["execution_ready"])
            self.assertEqual(report["process_actions"], {
                "runner_started": False,
                "worker_started": False,
                "ffi_called": False,
                "writable_ledger_opened": False,
            })
            self.assertEqual(report["historical"], {
                "consumed": 32,
                "unknown": 0,
                "ledger_count": 9,
                "verified_without_writable_journal": True,
                "input_set_sha256": report["historical"]["input_set_sha256"],
            })
            self.assertEqual(
                report["confirmation_scope"]["new_consumed"], None,
            )
            self.assertEqual(report["confirmation_scope"], {
                "scope": "curry-option-confirmation-v1",
                "prepared": True,
                "execution_ready": False,
                "new_consumed": None,
                "cumulative_consumed": None,
                "new_unknown": None,
                "unconsumed_slots_sealed": 7,
                "native_validation_passed": False,
            })
            self.assertEqual(set(report["checks"]), set(audit.CHECK_NAMES))
            self.assertTrue(all(value == "passed" for value in report["checks"].values()))
            self.assertEqual(report["qualifications"], audit.FLAGS)
            self.assertEqual(report["historical_exit_observation"], {
                "observation_exit_code": 1,
                "archived_refusal_branch_return_code": 2,
                "historical_exit_code_certified": False,
                "raw_normal_stdout_stderr_saved": False,
            })
            mismatch = report["hash_mismatch"]
            self.assertEqual(mismatch["manifest_role_hashing"],
                             "canonical_extracted_object_sha256")
            self.assertTrue(mismatch["repaired_shared_gate_passed"])
            self.assertEqual(
                [item["role"] for item in mismatch["legacy_raw_mismatches"]],
                ["base_request", "candidate_case"],
            )
            for item in mismatch["legacy_raw_mismatches"]:
                self.assertEqual(item["expected_object_sha256"], item["actual_object_sha256"])
                self.assertNotEqual(item["container_file_sha256"], item["actual_object_sha256"])
            self.assertEqual(len(report["source_archives"]), 2)
            self.assertEqual(report["source_archive_differences"], [
                "TASKS.md",
                "docs/TESTING.md",
                "docs/superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md",
            ])
            self.assertEqual(len(report["archived_source_members"]), 2)
            self.assertTrue(all(item["status"] == "passed"
                                for item in report["archived_source_members"]))
            saved = json.loads(args.output.read_bytes())
            self.assertEqual(saved, report)
            schema = json.loads(
                (workspace / "schemas/curry-input-recovery-audit-v2.schema.json").read_bytes()
            )
            Draft202012Validator(schema).validate(saved)
            self.assertEqual(args.output.read_bytes(), audit.canonical(report))
        finally:
            # The generated material lives only under ignored target/.
            pass


if __name__ == "__main__":
    unittest.main()
