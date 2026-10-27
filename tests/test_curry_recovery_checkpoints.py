"""Public-path failure progression tests for the Curry recovery audit.

The fixtures are synthetic and inert. They are kept below ignored ``target/``
so these tests never depend on or modify the real historical evidence tree.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import ctypes
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_eval import curry_asset_binding_audit
from ygo_eval import curry_input_recovery_audit as audit
from ygo_eval import native_curry_option_validation as curry
from tests.support.curry_recovery_e2e import (
    build_synthetic_recovery_tree,
    synthetic_source_sampler,
)


CHECKPOINTS = (
    "acceptance_delivery_anchors",
    "evidence_inventory",
    "source_archives",
    "frozen_input_binding",
    "historical_ledgers",
    "old_material_protection",
    "input_stability",
)


class CurryRecoveryCheckpointPublicPathTests(unittest.TestCase):
    """Run one fresh synthetic public audit per failing gate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = Path(__file__).resolve().parents[1]
        cls.scratch = cls.workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        cls.scratch.mkdir(parents=True, exist_ok=False)
        cls.seed = build_synthetic_recovery_tree(cls.scratch / "seed")
        cls.schema = json.loads(
            (cls.workspace / "schemas/curry-input-recovery-audit-v2.schema.json").read_bytes()
        )

    def test_each_v2_checkpoint_failure_is_saved_and_stops_the_public_audit(self) -> None:
        """Every failure is emitted through audit_to_output and validates as v2."""
        for checkpoint in CHECKPOINTS:
            with self.subTest(checkpoint=checkpoint):
                report, saved, calls, process_names, ledger_write_attempts, sources, fixture_ledger_mutations = self._run_failure(checkpoint)

                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["failure_checkpoint"], checkpoint)
                self.assertEqual(report["native_calls"], 0)
                self.assertFalse(report["execution_ready"])
                self.assertEqual(report["process_actions"], {
                    "runner_started": False,
                    "worker_started": False,
                    "ffi_called": False,
                    "writable_ledger_opened": False,
                })
                self.assertEqual(saved, report)
                self.assertTrue(audit.validate_report(report, _sources=sources))
                Draft202012Validator(self.schema).validate(saved)

                target_index = CHECKPOINTS.index(checkpoint)
                checks = report["checks"]
                self.assertEqual(set(checks), set(CHECKPOINTS))
                for prior in CHECKPOINTS[:target_index]:
                    self.assertEqual(checks[prior], "passed", (checkpoint, prior, checks))
                self.assertEqual(checks[checkpoint], "failed")
                for later in CHECKPOINTS[target_index + 1:]:
                    self.assertEqual(checks[later], "not_run", (checkpoint, later, checks))

                stability = report["stability"]
                self.assertEqual(stability["source_identity"], "passed")
                self.assertEqual(stability["confirmation_tree"], "passed")
                self.assertTrue(stability["ledger_absent_before"])
                self.assertTrue(stability["ledger_absent_after"])
                self.assertEqual(stability["confirmation_ledger_absence"], "passed")
                if checkpoint in {"old_material_protection", "input_stability"}:
                    self.assertEqual(stability["protected_material"], "failed")
                else:
                    self.assertEqual(stability["protected_material"], "not_collected")

                # Later verifier boundaries must not be entered after the
                # selected gate rejects its input.
                self._assert_later_gates_not_called(checkpoint, calls)
                self.assertEqual(ledger_write_attempts, [])
                if checkpoint == "historical_ledgers":
                    self.assertEqual(len(fixture_ledger_mutations), 1)
                    self.assertTrue(fixture_ledger_mutations[0].endswith("calls.jsonl"))
                else:
                    self.assertEqual(fixture_ledger_mutations, [])
                self.assertEqual(process_names, [])

    def test_existing_output_root_is_rejected_without_overwriting_or_native_activity(self) -> None:
        """An existing public output path is preserved before any audit work begins."""
        repo = self.scratch / "case-existing-output"
        shutil.copytree(self.seed.repo, repo)
        baseline = repo / self.seed.sources.baseline_relative
        output_root = repo / self.seed.sources.output_relative_v2
        output_root.mkdir(parents=True, exist_ok=False)
        sentinel = output_root / "audit-report.json"
        sentinel_bytes = b"existing-synthetic-output-must-remain-byte-identical\n"
        sentinel.write_bytes(sentinel_bytes)
        args = type("Args", (), {
            "baseline_dir": baseline,
            "output": sentinel,
            "report_version": 2,
        })()
        processes: list[str] = []
        ledger_writes: list[str] = []

        with self._forbid_native_activity(processes, ledger_writes):
            with self.assertRaisesRegex(ValueError, "recovery_output_root_exists"):
                audit.audit_to_output(args, repo=repo, _sources=self.seed.sources)

        self.assertEqual(sentinel.read_bytes(), sentinel_bytes)
        self.assertEqual(processes, [])
        self.assertEqual(ledger_writes, [])

    def _run_failure(self, checkpoint: str):
        case_root = self.scratch / f"case-{checkpoint}"
        fixture = build_synthetic_recovery_tree(case_root)
        repo = fixture.repo
        sources = fixture.sources
        baseline = repo / sources.baseline_relative
        output = repo / sources.output_relative_v2 / "audit-report.json"
        self._apply_fixture_mutation(checkpoint, repo, baseline)

        calls = {
            "acceptance_delivery_anchors": 0,
            "evidence_inventory": 0,
            "source_archives": 0,
            "frozen_input_binding": 0,
            "historical_ledgers": 0,
            "old_material_protection": 0,
            "input_stability": 0,
        }
        process_names: list[str] = []
        ledger_write_attempts: list[str] = []
        allowed_fixture_ledger_writes: set[Path] = set()
        fixture_ledger_mutations: list[str] = []
        args = type("Args", (), {
            "baseline_dir": baseline,
            "output": output,
            "report_version": 2,
        })()

        with self._forbid_native_activity(
            process_names, ledger_write_attempts,
            allowed_fixture_ledger_writes, fixture_ledger_mutations,
        ):
            with synthetic_source_sampler():
                with self._observe_gates(
                    checkpoint, repo, baseline, calls, allowed_fixture_ledger_writes,
                ):
                    old_cwd = Path.cwd()
                    try:
                        os.chdir(repo)
                        report = audit.audit_to_output(
                            args, repo=repo, _sources=sources,
                        )
                    finally:
                        os.chdir(old_cwd)

        self.assertTrue(output.is_file(), f"public audit did not save {checkpoint} report")
        saved = json.loads(output.read_bytes())
        return (report, saved, calls, process_names, ledger_write_attempts, sources,
                fixture_ledger_mutations)

    def _apply_fixture_mutation(self, checkpoint: str, repo: Path, baseline: Path) -> None:
        """Corrupt exactly one freshly copied synthetic fixture input."""
        paths = {
            "acceptance_delivery_anchors": baseline / "acceptance.json",
            "evidence_inventory": baseline / "evidence-inventory.json",
            "source_archives": baseline / "source-native.zip",
            "frozen_input_binding": baseline / "research/manifest.json",
        }
        if checkpoint in paths:
            path = paths[checkpoint]
            raw = path.read_bytes()
            if checkpoint == "frozen_input_binding":
                manifest = json.loads(raw)
                manifest["context"] = "f" * 64
                path.write_bytes(json.dumps(
                    manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ).encode("utf-8"))
            else:
                path.write_bytes(raw + b"\nsynthetic-corruption")

    @contextmanager
    def _observe_gates(
        self, checkpoint: str, repo: Path, baseline: Path, calls: dict[str, int],
        allowed_fixture_ledger_writes: set[Path],
    ):
        """Wrap real verifier boundaries; only inject the two timing-sensitive mutations."""
        with ExitStack() as stack:
            original_material = audit._verify_confirmation_material

            def material(*args, **kwargs):
                calls["acceptance_delivery_anchors"] += 1
                if checkpoint == "frozen_input_binding":
                    # The corrupted context is rejected inside the public
                    # frozen-input phase before deeper asset verification.
                    calls["frozen_input_binding"] += 1
                result = original_material(*args, **kwargs)
                if checkpoint == "input_stability":
                    protected_map = result["_private_protected"]
                    self._mutate_protected_fixture_file(protected_map, baseline)
                return result

            stack.enter_context(patch.object(
                audit, "_verify_confirmation_material", side_effect=material,
            ))

            original_inventory = audit._verify_evidence_inventory

            def inventory(*args, **kwargs):
                calls["evidence_inventory"] += 1
                return original_inventory(*args, **kwargs)

            stack.enter_context(patch.object(audit, "_verify_evidence_inventory", side_effect=inventory))

            original_archives = audit.verify_source_archive_pair

            def archives(*args, **kwargs):
                calls["source_archives"] += 1
                return original_archives(*args, **kwargs)

            stack.enter_context(patch.object(audit, "verify_source_archive_pair", side_effect=archives))

            original_confirmation_baseline = curry._verify_confirmation_baseline

            def confirmation_baseline(*args, **kwargs):
                result = original_confirmation_baseline(*args, **kwargs)
                if checkpoint == "historical_ledgers":
                    # Corrupt the second chain link only after the nested
                    # source/protection verification has completed. The
                    # public historical-ledger verifier must then reject it.
                    allowed_fixture_ledger_writes.add(
                        repo / "data/runtime/baseline-2026-10-19/research/calls.jsonl",
                    )
                    self._corrupt_nonfirst_ledger_previous(repo)
                return result

            stack.enter_context(patch.object(
                curry, "_verify_confirmation_baseline", side_effect=confirmation_baseline,
            ))

            original_preparation = curry.verify_curry_preparation

            def preparation(*args, **kwargs):
                calls["frozen_input_binding"] += 1
                return original_preparation(*args, **kwargs)

            stack.enter_context(patch.object(curry, "verify_curry_preparation", side_effect=preparation))

            original_historical = curry_asset_binding_audit._verify_historical_chain

            def historical(*args, **kwargs):
                calls["historical_ledgers"] += 1
                return original_historical(*args, **kwargs)

            stack.enter_context(patch.object(
                curry_asset_binding_audit, "_verify_historical_chain", side_effect=historical,
            ))

            original_protected_hash = curry._confirmation_protected_hash

            def protected_hash(path, root):
                calls["input_stability"] += 1
                return original_protected_hash(path, root)

            stack.enter_context(patch.object(
                curry, "_confirmation_protected_hash", side_effect=protected_hash,
            ))

            original_protected = audit._protected_records

            def protected(root: Path, expected: dict[Path, str]):
                calls["old_material_protection"] += 1
                if checkpoint == "old_material_protection":
                    self._mutate_protected_fixture_file(expected, baseline)
                return original_protected(root, expected)

            stack.enter_context(patch.object(audit, "_protected_records", side_effect=protected))

            yield

    @staticmethod
    def _mutate_protected_fixture_file(protected: dict[Path, str], baseline: Path) -> None:
        candidates = sorted(
            path for path in protected
            if path.is_file()
            and path.name.lower() in {"ygo-engine-worker.exe", "curry-option-validation.exe"}
            and not path.is_relative_to(baseline)
        )
        if not candidates:
            candidates = sorted(
                path for path in protected
                if path.is_file() and path.name != "calls.jsonl"
                and not path.is_relative_to(baseline)
            )
        if not candidates:
            raise AssertionError("synthetic_protected_file_missing")
        path = candidates[0]
        path.write_bytes(path.read_bytes() + b"\nsynthetic-protection-drift")

    @staticmethod
    def _corrupt_nonfirst_ledger_previous(repo: Path) -> None:
        ledger = repo / "data/runtime/baseline-2026-10-19/research/calls.jsonl"
        lines = ledger.read_bytes().splitlines()
        if len(lines) < 2:
            raise AssertionError("synthetic_ledger_requires_multiple_rows")
        row = json.loads(lines[1])
        row["previous"] = "f" * 64
        lines[1] = json.dumps(
            row, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        ledger.write_bytes(b"\n".join(lines) + b"\n")

    def _assert_later_gates_not_called(self, checkpoint: str, calls: dict[str, int]) -> None:
        index = CHECKPOINTS.index(checkpoint)
        stage_key = {
            "evidence_inventory": "evidence_inventory",
            "source_archives": "source_archives",
            "frozen_input_binding": "frozen_input_binding",
            "historical_ledgers": "historical_ledgers",
            "old_material_protection": "old_material_protection",
        }
        for later in CHECKPOINTS[index + 1:]:
            key = stage_key.get(later)
            if key is not None:
                # The input-stability boundary is the audit's own final sweep,
                # not a separately invoked verifier function.
                assert calls[key] == 0, (checkpoint, later, calls)
        self.assertGreater(
            calls.get(checkpoint, 0), 0,
            f"target verifier boundary was not entered: {checkpoint}; {calls}",
        )

    @staticmethod
    @contextmanager
    def _forbid_native_activity(
        process_names: list[str], ledger_write_attempts: list[str],
        allowed_fixture_ledger_writes: set[Path] | None = None,
        fixture_ledger_mutations: list[str] | None = None,
    ):
        if allowed_fixture_ledger_writes is None:
            allowed_fixture_ledger_writes = set()
        if fixture_ledger_mutations is None:
            fixture_ledger_mutations = []

        def guarded_popen(command, *args, **kwargs):
            executable = command[0] if isinstance(command, (list, tuple)) else command
            name = Path(os.fspath(executable)).name.lower()
            process_names.append(name)
            raise AssertionError("process_forbidden_in_synthetic_audit")

        def allowed_fixture_write(path: Path) -> bool:
            absolute = path.absolute()
            if absolute not in allowed_fixture_ledger_writes:
                return False
            allowed_fixture_ledger_writes.remove(absolute)
            fixture_ledger_mutations.append(absolute.as_posix())
            return True

        real_io_open = io.open

        def guarded_io_open(file, mode="r", *args, **kwargs):
            # subprocess.Popen opens its inherited pipe descriptors through
            # io.open using integer file descriptors. They are unrelated to
            # filesystem writes, so leave them to the original implementation.
            if isinstance(file, int):
                return real_io_open(file, mode, *args, **kwargs)
            path = Path(os.fspath(file))
            if path.name == "calls.jsonl" and any(flag in mode for flag in "wax+"):
                if not allowed_fixture_write(path):
                    ledger_write_attempts.append(path.as_posix())
                    raise AssertionError("writable_ledger_open_forbidden_in_synthetic_audit")
            return real_io_open(file, mode, *args, **kwargs)

        real_builtin_open = open

        def guarded_builtin_open(file, mode="r", *args, **kwargs):
            if isinstance(file, int):
                return real_builtin_open(file, mode, *args, **kwargs)
            path = Path(os.fspath(file))
            if path.name == "calls.jsonl" and any(flag in mode for flag in "wax+"):
                if not allowed_fixture_write(path):
                    ledger_write_attempts.append(path.as_posix())
                    raise AssertionError("writable_ledger_open_forbidden_in_synthetic_audit")
            return real_builtin_open(file, mode, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch.object(subprocess, "Popen", new=guarded_popen))
            stack.enter_context(patch.object(io, "open", new=guarded_io_open))
            stack.enter_context(patch("builtins.open", new=guarded_builtin_open))
            for loader in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
                if hasattr(ctypes, loader):
                    stack.enter_context(patch.object(
                        ctypes, loader, side_effect=AssertionError("FFI_forbidden"),
                    ))
            yield


if __name__ == "__main__":
    unittest.main()
