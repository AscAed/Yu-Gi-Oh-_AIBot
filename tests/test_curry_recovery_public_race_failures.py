"""Public-audit tests for duplicate JSON and evidence changing during a run."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
import ctypes
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid
from unittest.mock import patch

from jsonschema import Draft202012Validator

from tests.support.curry_recovery_e2e import (
    build_synthetic_recovery_tree,
    synthetic_source_sampler,
)
from ygo_eval import curry_input_recovery_audit as audit
from ygo_eval.curry_input_recovery_audit import _SourceDescription


class CurryRecoveryPublicRaceFailureTests(unittest.TestCase):
    def _fixture(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        return build_synthetic_recovery_tree(scratch)

    @staticmethod
    def _replace_pin(
        sources: _SourceDescription, relative_path: str, sha256: str,
    ) -> _SourceDescription:
        files = tuple(
            replace(item, sha256=sha256) if item.relative_path == relative_path else item
            for item in sources.files
        )
        children = tuple(
            CurryRecoveryPublicRaceFailureTests._replace_pin(
                child, relative_path, sha256,
            )
            for child in sources.children
        )
        return replace(sources, files=files, children=children)

    def _run_public_audit(
        self, fixture, *, after_material=None, sources=None, write_report=None,
    ):
        repo = fixture.repo
        source_description = sources or fixture.sources
        baseline = repo / source_description.baseline_relative
        output = repo / source_description.output_relative_v2 / "audit-report.json"
        args = type("Args", (), {
            "baseline_dir": baseline,
            "output": output,
            "report_version": 2,
        })()
        processes: list[str] = []
        ledger_writes: list[str] = []
        real_popen = subprocess.Popen
        real_io_open = io.open
        real_open = open

        def forbidden_popen(command, *args, **kwargs):
            executable = command[0] if isinstance(command, (tuple, list)) else command
            processes.append(Path(os.fspath(executable)).name.lower())
            raise AssertionError("native_process_forbidden")

        def guard_ledger_open(path, mode):
            if isinstance(path, int):
                return
            candidate = Path(os.fspath(path))
            if candidate.name == "calls.jsonl" and any(flag in mode for flag in "wax+"):
                ledger_writes.append(candidate.as_posix())
                raise AssertionError("writable_ledger_forbidden")

        def guarded_io_open(path, mode="r", *args, **kwargs):
            guard_ledger_open(path, mode)
            return real_io_open(path, mode, *args, **kwargs)

        def guarded_open(path, mode="r", *args, **kwargs):
            guard_ledger_open(path, mode)
            return real_open(path, mode, *args, **kwargs)

        original_material = audit._verify_confirmation_material

        def material(*args, **kwargs):
            result = original_material(*args, **kwargs)
            if after_material is not None:
                after_material(repo, baseline, result)
            return result

        old_cwd = Path.cwd()
        try:
            os.chdir(repo)
            with ExitStack() as stack:
                stack.enter_context(patch.object(subprocess, "Popen", new=forbidden_popen))
                stack.enter_context(patch.object(io, "open", new=guarded_io_open))
                stack.enter_context(patch("builtins.open", new=guarded_open))
                if write_report is not None:
                    stack.enter_context(patch.object(audit, "_write_report", new=write_report))
                for loader in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
                    if hasattr(ctypes, loader):
                        stack.enter_context(patch.object(
                            ctypes, loader,
                            side_effect=AssertionError("ffi_forbidden"),
                        ))
                stack.enter_context(patch.object(audit, "_verify_confirmation_material", side_effect=material))
                with synthetic_source_sampler():
                    try:
                        report = audit.audit_to_output(
                            args, repo=repo, _sources=source_description,
                        )
                    finally:
                        self.assertEqual(processes, [])
                        self.assertEqual(ledger_writes, [])
        finally:
            os.chdir(old_cwd)
        self.assertEqual(json.loads(output.read_bytes()), report)
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/curry-input-recovery-audit-v2.schema.json").read_bytes())
        Draft202012Validator(schema).validate(report)
        self.assertTrue(audit.validate_report(report, _sources=source_description))
        return report

    def test_public_path_rejects_duplicate_json_key_with_matching_source_pin(self):
        fixture = self._fixture()
        relative = (Path(fixture.sources.baseline_relative) / "acceptance.json").as_posix()
        duplicate = b'{"schema_version":1,"schema_version":1}\n'
        path = fixture.repo / relative
        path.write_bytes(duplicate)
        sources = self._replace_pin(fixture.sources, relative, audit.digest(duplicate))

        report = self._run_public_audit(fixture, sources=sources)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure_checkpoint"], "acceptance_delivery_anchors")
        self.assertIn("duplicate_json_key", report["diagnostics"])
        self.assertEqual(report["native_calls"], 0)

    def test_public_path_rechecks_confirmation_directory_add_and_delete(self):
        for mutation in ("add", "delete"):
            with self.subTest(mutation=mutation):
                fixture = self._fixture()
                baseline = fixture.repo / fixture.sources.baseline_relative
                probe = baseline / "research" / "synthetic-unpinned-race.txt"
                if mutation == "delete":
                    probe.write_bytes(b"synthetic unpinned file before audit\n")

                def change_tree(_repo, _baseline, _material):
                    if mutation == "add":
                        probe.write_bytes(b"synthetic file appeared during audit\n")
                    else:
                        probe.unlink()

                report = self._run_public_audit(fixture, after_material=change_tree)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["failure_checkpoint"], "input_stability")
                self.assertIn("confirmation_material_changed_during_audit", report["diagnostics"])
                self.assertEqual(report["stability"]["confirmation_tree"], "failed")

    def test_public_path_detects_charge_ledger_appearing_during_audit(self):
        fixture = self._fixture()
        baseline = fixture.repo / fixture.sources.baseline_relative
        ledger = baseline / "research" / "calls.jsonl"
        staged = fixture.repo / "synthetic-ledger-appearance.bin"
        staged.write_bytes(b"synthetic ledger appeared after precheck\n")

        def introduce_ledger(_repo, _baseline, _material):
            os.replace(staged, ledger)

        report = self._run_public_audit(fixture, after_material=introduce_ledger)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["stability"]["ledger_absent_before"], True)
        self.assertEqual(report["stability"]["ledger_absent_after"], False)
        self.assertEqual(report["stability"]["confirmation_ledger_absence"], "failed")
        self.assertIn("confirmation_charge_ledger_unexpected", report["diagnostics"])

    def test_final_report_exclusive_write_race_preserves_existing_bytes(self):
        fixture = self._fixture()
        repo = fixture.repo
        output = repo / fixture.sources.output_relative_v2 / "audit-report.json"
        sentinel = b"created by a competing synthetic writer\n"
        original_writer = audit._write_report

        def compete(path: Path, report: dict) -> None:
            path.write_bytes(sentinel)
            original_writer(path, report)

        with self.assertRaises(FileExistsError):
            self._run_public_audit(fixture, write_report=compete)
        self.assertEqual(output.read_bytes(), sentinel)


if __name__ == "__main__":
    unittest.main()
