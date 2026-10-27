from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
import shutil
import sys
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from tests.support.curry_reservation_e2e import (
    _forbid_native_activity,
    build_synthetic_v1_failed_attempt,
    build_synthetic_reservation_tree,
)
from tests.support.curry_recovery_e2e import synthetic_source_identity
from ygo_eval import curry_consumption_reservation as reservation
from ygo_eval.research import main


class CurryConsumptionReservationDispatchTests(unittest.TestCase):
    def test_failed_report_cannot_claim_unverified_historical_consumption(self):
        workspace = Path(__file__).resolve().parents[1]
        schema = json.loads((workspace / "schemas/curry-consumption-reservation-v1.schema.json").read_bytes())
        for status in ("failed", "incomplete"):
            with self.subTest(status=status):
                report = reservation._new_report()
                report["status"] = status
                report["failure_checkpoint"] = "old_confirmation_scope"
                report["historical_ledgers"] = {
                    "ledger_count": 9,
                    "consumed": 32,
                    "unknown": 0,
                    "verified_by_anchored_read_only_protection": True,
                }
                report["planning_basis"]["certified_historical_consumed"] = 32
                with self.assertRaises(ValueError):
                    reservation.verify_report_bytes(reservation._pretty(report))
                self.assertTrue(list(Draft202012Validator(schema).iter_errors(report)))

    def test_fixed_source_tampering_stops_at_the_pinned_checkpoint(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-consumption-reservation-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_reservation_tree(scratch)
        repo, profile = fixture.repo, fixture.profile
        output_root = repo / profile.output_relative
        output = output_root / "reservation.json"
        common = [
            "research",
            "prepare-curry-consumption-reservation",
            "--baseline-dir", str(repo / profile.baseline_relative),
            "--output", str(output),
        ]
        cases = (
            (
                profile.baseline_relative / "final-build/delivery.json",
                "latest_delivery_chain",
                "real_v2_report",
            ),
            (
                profile.v2_report_relative,
                "real_v2_report",
                "old_confirmation_scope",
            ),
            (
                profile.confirmation_relative / "research/manifest.json",
                "old_confirmation_scope",
                "historical_ledgers",
            ),
            (
                None,
                "historical_ledgers",
                None,
            ),
        )
        ledger_path = next(
            path for path in repo.rglob("calls.jsonl")
            if path.is_file() and path != repo / profile.confirmation_relative / "research/calls.jsonl"
        )

        for relative, expected_checkpoint, first_unrun in cases:
            with self.subTest(checkpoint=expected_checkpoint):
                path = ledger_path if relative is None else repo / relative
                original = path.read_bytes()
                path.write_bytes(original + b"\n# deliberate reservation audit tamper\n")
                try:
                    with (
                        patch.object(sys, "argv", common),
                        patch.object(reservation, "_repo_root", return_value=repo),
                        patch.object(reservation, "_production_profile", return_value=profile),
                        patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
                        contextlib.redirect_stdout(io.StringIO()) as stdout,
                        _forbid_native_activity(),
                    ):
                        self.assertEqual(main(), 1)
                    failed = json.loads(stdout.getvalue())
                    self.assertEqual(failed["status"], "failed")
                    self.assertEqual(failed["failure_checkpoint"], expected_checkpoint)
                    self.assertEqual(failed["native_calls"], 0)
                    self.assertFalse(failed["execution_ready"])
                    self.assertIsNone(failed["historical_ledgers"]["consumed"])
                    self.assertIsNone(failed["planning_basis"]["certified_historical_consumed"])
                    self.assertIsNone(failed["planning_basis"]["planned_total"])
                    self.assertEqual(failed["old_scope"]["actual_new_consumed"], None)
                    self.assertEqual(failed["old_scope"]["actual_cumulative_consumed"], None)
                    self.assertEqual(failed["old_scope"]["actual_unknown"], None)
                    if first_unrun is not None:
                        self.assertEqual(failed["checks"][first_unrun], "not_run")
                    schema = json.loads((workspace / "schemas/curry-consumption-reservation-v1.schema.json").read_bytes())
                    Draft202012Validator(schema, format_checker=FormatChecker()).validate(failed)
                    self.assertTrue(output.is_file())
                    self.assertFalse((repo / profile.confirmation_relative / "research/calls.jsonl").exists())
                finally:
                    path.write_bytes(original)
                    if output_root.exists():
                        shutil.rmtree(output_root)

    def test_complete_synthetic_public_cli_reservation_and_read_only_verification(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-consumption-reservation-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_reservation_tree(scratch)
        repo = fixture.repo
        profile = fixture.profile
        output = repo / profile.output_relative / "reservation.json"
        common = [
            "research",
            "prepare-curry-consumption-reservation",
            "--baseline-dir", str(repo / profile.baseline_relative),
            "--output", str(output),
        ]

        def invoke(extra=()):
            with (
                patch.object(sys, "argv", common + list(extra)),
                patch.object(reservation, "_repo_root", return_value=repo),
                patch.object(reservation, "_production_profile", return_value=profile),
                patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
                _forbid_native_activity(),
            ):
                code = main()
            return code, stdout.getvalue()

        code, stdout = invoke()
        self.assertEqual(code, 0, stdout)
        report = json.loads(stdout)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["native_calls"], 0)
        self.assertFalse(report["execution_ready"])
        self.assertEqual(report["historical_ledgers"], {
            "ledger_count": 9,
            "consumed": 32,
            "unknown": 0,
            "verified_by_anchored_read_only_protection": True,
        })
        self.assertIsNone(report["old_scope"]["actual_new_consumed"])
        self.assertIsNone(report["old_scope"]["actual_cumulative_consumed"])
        self.assertIsNone(report["old_scope"]["actual_unknown"])
        self.assertEqual(report["reservation"]["requested_calls"], 7)
        self.assertEqual(report["planning_basis"], {
            "certified_historical_consumed": 32,
            "risk_reserve_calls": 7,
            "planned_total": 39,
            "actual_all_history_cumulative": None,
        })
        manifest_sha = report["old_scope"]["manifest_sha256"]
        context = report["old_scope"]["context"]
        independently_expected = hashlib.sha256(reservation._canonical({
            "scope": "curry-option-confirmation-v1",
            "manifest_sha256": manifest_sha,
            "context": context,
            "policy_id": "curry-unknown-reserve-seven-v1",
            "reserved_calls": 7,
        })).hexdigest()
        self.assertEqual(report["reservation"]["reservation_id"], independently_expected)
        self.assertEqual(report["reservation"]["duplicate_count"], 1)
        schema = json.loads((workspace / "schemas/curry-consumption-reservation-v1.schema.json").read_bytes())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
        saved_before = output.read_bytes()

        for mutate, schema_rejects in (
            (lambda value: value["planning_basis"].update({"planned_total": 32}), True),
            (lambda value: value["planning_basis"].update({"risk_reserve_calls": 39}), True),
            (lambda value: value["old_scope"].update({"actual_new_consumed": 0}), True),
            (lambda value: value["reservation"].update({"duplicate_count": 2}), True),
            (lambda value: value["reservation"].update({"reservation_id": "0" * 64}), False),
            (lambda value: value["old_scope"].update({"manifest_sha256": None}), True),
            (lambda value: value["old_scope"].update({"context": None}), True),
        ):
            with self.subTest(mutate=mutate):
                changed = json.loads(saved_before)
                mutate(changed)
                with self.assertRaises(ValueError):
                    reservation.verify_report_bytes(reservation._pretty(changed))
                schema_errors = list(Draft202012Validator(schema).iter_errors(changed))
                self.assertEqual(bool(schema_errors), schema_rejects)
        with self.assertRaises(ValueError):
            reservation.verify_report_bytes(b'{"schema_version":1,"schema_version":1}')

        verify_code, verify_stdout = invoke(["--verify-only"])
        self.assertEqual(verify_code, 0, verify_stdout)
        verification = json.loads(verify_stdout)
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["reservation_id"], independently_expected)
        self.assertEqual(output.read_bytes(), saved_before)

        unexpected_source = repo / profile.confirmation_relative / "research/unlisted-stage.json"
        unexpected_source.write_bytes(b"unlisted source material")
        extra_code, extra_stdout = invoke(["--verify-only"])
        self.assertEqual(extra_code, 2, extra_stdout)
        self.assertEqual(output.read_bytes(), saved_before)
        unexpected_source.unlink()

        changed_tool_identity = json.loads(saved_before)
        changed_tool_identity["tool"]["workspace_identity"] = "0" * 64
        output.write_bytes(reservation._pretty(changed_tool_identity))
        with self.assertRaises(ValueError):
            reservation._verify_saved(
                type("Args", (), {"verify_only": True})(), repo, profile,
                output.parent, output,
            )
        output.write_bytes(saved_before)

        # A report cannot claim stable sources if its rechecked stability
        # evidence was rewritten after recording.
        tampered = json.loads(saved_before)
        tampered["stability"]["baseline_tree"] = "failed"
        output.write_bytes(reservation._pretty(tampered))
        with self.assertRaises(Exception):
            reservation._verify_saved(
                type("Args", (), {"verify_only": True})(), repo, profile,
                output.parent, output,
            )

    def test_output_collision_and_extra_files_are_rejected_without_overwrite(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-consumption-reservation-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_reservation_tree(scratch)
        repo, profile = fixture.repo, fixture.profile
        output = repo / profile.output_relative / "reservation.json"
        common = ["research", "prepare-curry-consumption-reservation", "--baseline-dir", str(repo / profile.baseline_relative), "--output", str(output)]
        with (
            patch.object(sys, "argv", common),
            patch.object(reservation, "_repo_root", return_value=repo),
            patch.object(reservation, "_production_profile", return_value=profile),
            patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            _forbid_native_activity(),
        ):
            self.assertEqual(main(), 0, stdout.getvalue())
        original = output.read_bytes()
        (output.parent / "unexpected.bin").write_bytes(b"do not accept extra material")
        with (
            patch.object(sys, "argv", common + ["--verify-only"]),
            patch.object(reservation, "_repo_root", return_value=repo),
            patch.object(reservation, "_production_profile", return_value=profile),
            patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            _forbid_native_activity(),
        ):
            self.assertEqual(main(), 2)
        self.assertIn("refused", stdout.getvalue())
        self.assertEqual(output.read_bytes(), original)

        # The failed second prepare must not replace the already saved report.
        with (
            patch.object(sys, "argv", common),
            patch.object(reservation, "_repo_root", return_value=repo),
            patch.object(reservation, "_production_profile", return_value=profile),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            _forbid_native_activity(),
        ):
            self.assertEqual(main(), 2)
        self.assertEqual(output.read_bytes(), original)

    def test_public_cli_dispatches_fixed_prepare_and_verify_modes(self):
        common = [
            "research",
            "prepare-curry-consumption-reservation",
            "--baseline-dir",
            "baseline",
            "--output",
            "output",
        ]
        for suffix, result, expected_exit in (
            ([], {"status": "passed", "native_calls": 0}, 0),
            (["--verify-only"], {"valid": True, "native_calls": 0}, 0),
        ):
            with self.subTest(suffix=suffix):
                argv = common + suffix
                with patch.object(sys, "argv", argv), patch(
                    "ygo_eval.curry_consumption_reservation.audit_to_output",
                    return_value=result,
                ) as run, contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(), expected_exit)
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0].verify_only, "--verify-only" in suffix)
                self.assertIn('"native_calls": 0', output.getvalue())

    def test_public_cli_selects_independent_v2_report_without_changing_v1_default(self):
        common = [
            "research",
            "prepare-curry-consumption-reservation",
            "--baseline-dir",
            "baseline",
            "--output",
            "output",
        ]
        for suffix, expected in (([], 1), (["--report-version", "2"], 2)):
            with self.subTest(suffix=suffix):
                with (
                    patch.object(sys, "argv", common + suffix),
                    patch(
                        "ygo_eval.curry_consumption_reservation.audit_to_output",
                        return_value={"status": "passed", "native_calls": 0},
                    ) as run,
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    self.assertEqual(main(), 0, output.getvalue())
                self.assertEqual(run.call_args.args[0].report_version, expected)

    def test_reservation_versions_have_separate_fixed_outputs_and_tool_member_sets(self):
        v1 = reservation._version_spec(1)
        v2 = reservation._version_spec(2)
        self.assertEqual(v1.output_relative, reservation.OUTPUT_RELATIVE)
        self.assertEqual(v1.tool_files, reservation._TOOL_FILES)
        self.assertEqual(v1.kind, "curry_consumption_reservation")
        self.assertEqual(v2.output_relative.as_posix(), "data/runtime/p1-curry-consumption-reservation-v2-offline-2026-10-25")
        self.assertEqual(v2.kind, "curry_consumption_reservation_v2")
        self.assertIn("previous_failed_attempt", v2.checks)
        self.assertEqual(len(v2.tool_files), len(v1.tool_files) + 1)
        self.assertIn("schemas/curry-consumption-reservation-v2.schema.json", v2.tool_files)

    def test_public_cli_recovers_from_synthetic_v1_failure_and_verifies_v2_without_calls(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-consumption-reservation-v2-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_reservation_tree(scratch)
        repo, profile = fixture.repo, fixture.profile
        legacy = build_synthetic_v1_failed_attempt(repo, profile)
        v1_report = json.loads(legacy.read_bytes())
        self.assertEqual(v1_report["failure_checkpoint"], "latest_delivery_chain")
        self.assertEqual(v1_report["diagnostics"], ["delivery_anchor_mismatch"])
        self.assertFalse(v1_report["reservation"]["recorded"])
        self.assertIsNone(v1_report["planning_basis"]["planned_total"])

        output_relative = Path("data/runtime/p1-curry-consumption-reservation-v2-offline-2026-10-25")
        output = repo / output_relative / "reservation.json"
        base_spec = reservation._version_spec
        v2_spec = replace(
            base_spec(2),
            output_relative=output_relative,
            previous_failure_relative=legacy.relative_to(repo),
            previous_failure_sha256=hashlib.sha256(legacy.read_bytes()).hexdigest(),
        )
        selected_spec = v2_spec
        common = [
            "research", "prepare-curry-consumption-reservation",
            "--report-version", "2",
            "--baseline-dir", str(repo / profile.baseline_relative),
            "--output", str(output),
        ]

        def invoke(extra=()):
            command = common[:-1] + [str(repo / selected_spec.output_relative / "reservation.json")] + list(extra)
            failures = []
            audited = reservation.audit_to_output

            def capture_failure(args):
                try:
                    return audited(args)
                except Exception as error:
                    failures.append(error)
                    raise

            with (
                patch.object(sys, "argv", command),
                patch.object(reservation, "_repo_root", return_value=repo),
                patch.object(reservation, "_production_profile", return_value=profile),
                patch.object(reservation, "_version_spec", side_effect=lambda version: selected_spec if version == 2 else base_spec(version)),
                patch.object(reservation, "audit_to_output", side_effect=capture_failure),
                patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
                _forbid_native_activity(),
            ):
                code = main()
            return code, stdout.getvalue(), failures

        # A corrupted tool archive is rejected at the first V2 checkpoint and
        # the later business-source gates remain untouched.
        old_tool_archive = legacy.parent / v1_report["tool"]["archive_path"]
        original_old_tool_archive = old_tool_archive.read_bytes()
        old_tool_archive.write_bytes(original_old_tool_archive + b"tamper")
        rejected_relative = output_relative.parent / "p1-curry-consumption-reservation-v2-prior-failure-rejected-tests"
        selected_spec = replace(v2_spec, output_relative=rejected_relative)
        rejected_output = repo / rejected_relative / "reservation.json"
        rejected_code, rejected_stdout, rejected_errors = invoke()
        self.assertEqual(rejected_code, 1, rejected_stdout + repr(rejected_errors))
        rejected = json.loads(rejected_stdout)
        self.assertEqual(rejected["failure_checkpoint"], "previous_failed_attempt")
        self.assertEqual(rejected["checks"]["previous_failed_attempt"], "failed")
        self.assertEqual(rejected["checks"]["latest_delivery_chain"], "not_run")
        self.assertIsNone(rejected["historical_ledgers"]["consumed"])
        self.assertIsNone(rejected["planning_basis"]["planned_total"])
        rejected_schema = json.loads((workspace / "schemas/curry-consumption-reservation-v2.schema.json").read_bytes())
        Draft202012Validator(rejected_schema, format_checker=FormatChecker()).validate(rejected)
        self.assertTrue(rejected_output.is_file())
        old_tool_archive.write_bytes(original_old_tool_archive)

        old_tool_list = legacy.parent / v1_report["tool"]["file_list_path"]
        original_old_tool_list = old_tool_list.read_bytes()
        old_tool_list.write_bytes(original_old_tool_list + b"tamper")
        list_rejected_relative = output_relative.parent / "p1-curry-consumption-reservation-v2-prior-list-rejected-tests"
        selected_spec = replace(v2_spec, output_relative=list_rejected_relative)
        list_code, list_stdout, _ = invoke()
        self.assertEqual(list_code, 1, list_stdout)
        list_report = json.loads(list_stdout)
        self.assertEqual(list_report["failure_checkpoint"], "previous_failed_attempt")
        self.assertEqual(list_report["checks"]["latest_delivery_chain"], "not_run")
        old_tool_list.write_bytes(original_old_tool_list)

        # Once the v1 failure is restored, the same public path proceeds to the
        # original business gates; a damaged delivery cannot be substituted.
        delivery_path = repo / profile.baseline_relative / "final-build/delivery.json"
        original_delivery = delivery_path.read_bytes()
        delivery_path.write_bytes(original_delivery + b"tamper")
        business_rejected_relative = output_relative.parent / "p1-curry-consumption-reservation-v2-business-rejected-tests"
        selected_spec = replace(v2_spec, output_relative=business_rejected_relative)
        business_code, business_stdout, _ = invoke()
        self.assertEqual(business_code, 1, business_stdout)
        business_report = json.loads(business_stdout)
        self.assertEqual(business_report["failure_checkpoint"], "latest_delivery_chain")
        self.assertEqual(business_report["checks"]["previous_failed_attempt"], "passed")
        self.assertEqual(business_report["checks"]["real_v2_report"], "not_run")
        delivery_path.write_bytes(original_delivery)
        selected_spec = v2_spec

        code, stdout, _ = invoke()
        self.assertEqual(code, 0, stdout)
        report = json.loads(stdout)
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["kind"], "curry_consumption_reservation_v2")
        self.assertTrue(report["checks"]["previous_failed_attempt"] == "passed")
        self.assertEqual(
            report["previous_failed_attempt"]["archived_bad_acceptance_constant"],
            reservation.ARCHIVED_BAD_ACCEPTANCE_CONSTANT,
        )
        self.assertIsNone(report["previous_failed_attempt"]["historical_actual_exit_code"])
        self.assertEqual(report["reservation"]["requested_calls"], 7)
        self.assertEqual(report["planning_basis"]["planned_total"], 39)
        self.assertIsNone(report["planning_basis"]["actual_all_history_cumulative"])
        self.assertEqual(report["native_calls"], 0)
        self.assertEqual(report["historical_ledgers"]["consumed"], 32)
        self.assertIsNone(report["old_scope"]["actual_new_consumed"])
        expected_id = hashlib.sha256(reservation._canonical({
            "scope": reservation.CONFIRMATION_SCOPE,
            "manifest_sha256": report["old_scope"]["manifest_sha256"],
            "context": report["old_scope"]["context"],
            "policy_id": reservation.POLICY_ID,
            "reserved_calls": 7,
        })).hexdigest()
        self.assertEqual(report["reservation"]["reservation_id"], expected_id)
        schema = json.loads((workspace / "schemas/curry-consumption-reservation-v2.schema.json").read_bytes())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
        for mutate, expected_error in (
            (lambda value: value.update({"inputs": []}), "reservation_success_inputs_missing"),
            (lambda value: value["reservation"].update({"requested_calls": 39}), None),
            (lambda value: value["reservation"].update({"duplicate_count": 2}), None),
            (lambda value: value["old_scope"].update({"actual_new_consumed": 0}), None),
            (lambda value: value["planning_basis"].update({"planned_total": 32}), None),
            (lambda value: value["planning_basis"].update({"actual_all_history_cumulative": 39}), None),
            (lambda value: value["previous_failed_attempt"].update({"status": "passed"}), None),
        ):
            changed = json.loads(reservation._pretty(report))
            mutate(changed)
            with patch.object(reservation, "_version_spec", return_value=selected_spec):
                if expected_error is None:
                    with self.assertRaises(ValueError):
                        reservation.verify_report_bytes(reservation._pretty(changed))
                else:
                    with self.assertRaisesRegex(ValueError, expected_error):
                        reservation.verify_report_bytes(reservation._pretty(changed))
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(changed)))
        original = output.read_bytes()
        verification_code, verification_stdout, verification_errors = invoke(["--verify-only"])
        self.assertEqual(verification_code, 0, verification_stdout)
        verification = json.loads(verification_stdout)
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["schema_version"], 2)
        self.assertEqual(verification["reservation_id"], report["reservation"]["reservation_id"])
        self.assertEqual(output.read_bytes(), original)

        with self.assertRaises(ValueError):
            reservation.verify_report_bytes(b'{"schema_version":2,"schema_version":2}')
        unexpected = output.parent / "unexpected.bin"
        unexpected.write_bytes(b"unlisted v2 output material")
        unexpected_code, unexpected_stdout, _ = invoke(["--verify-only"])
        self.assertEqual(unexpected_code, 2, unexpected_stdout)
        self.assertEqual(output.read_bytes(), original)
        unexpected.unlink()

        # Verification rebinds the prior failed report and refuses any drift,
        # without changing the recorded V2 artifact.
        original_legacy_report = legacy.read_bytes()
        legacy.write_bytes(original_legacy_report + b"tamper")
        changed_code, changed_stdout, _ = invoke(["--verify-only"])
        self.assertEqual(changed_code, 2, changed_stdout)
        self.assertEqual(output.read_bytes(), original)
        legacy.write_bytes(original_legacy_report)

    def test_public_cli_sanitizes_source_failures(self):
        argv = [
            "research",
            "prepare-curry-consumption-reservation",
            "--baseline-dir",
            "D:\\private\\history",
            "--output",
            "output",
        ]
        with patch.object(sys, "argv", argv), patch(
            "ygo_eval.curry_consumption_reservation.audit_to_output",
            side_effect=ValueError("D:\\private\\history"),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
        self.assertNotIn("private", output.getvalue())

    def test_fixed_production_profile_keeps_anchored_values(self):
        profile = reservation._production_profile()
        self.assertEqual(profile.baseline_relative, reservation.BASELINE_RELATIVE)
        self.assertEqual(profile.output_relative, reservation.OUTPUT_RELATIVE)
        self.assertEqual(
            profile.acceptance_sha256,
            "f6f5a88664252f9fb0f7d94c7251dba2e8859fbf1d19e9a45396070efce84835",
        )
        self.assertEqual(profile.confirmation_input_count, 43)
        self.assertEqual(profile.confirmation_evidence_count, 40)
        self.assertEqual(profile.confirmation_evidence_bytes, 60_054_498)
        self.assertEqual(profile.confirmation_context, reservation.CONFIRMATION_CONTEXT)
        self.assertEqual(dict(profile.test_log_hashes), {
            "pytest-files.txt": "8dd3c844cbe3da37cc0b01713baed01acb49f44b85979af982b4dd9cb8f7817e",
            "pytest-full-rerun.log": "39f42e9865a4dbadf3a673b5d99178c28aad359aa8b726644a8ce5eaf449db26",
            "pytest-full.log": "2d63562b0b30675f0f50393ba0bea5b806825755814a5a7a6f4dc6219d611028",
        })

    def test_output_parent_symlink_is_rejected_before_writing(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-consumption-reservation-tests" / uuid.uuid4().hex
        repo = scratch / "repo"
        outside = scratch / "outside"
        repo.mkdir(parents=True, exist_ok=False)
        outside.mkdir()
        (repo / ".gitignore").write_text("data/runtime\n", encoding="utf-8")
        (repo / "data").mkdir()
        try:
            os.symlink(outside, repo / "data/runtime", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation is unavailable on this Windows configuration")
        profile = replace(
            reservation._production_profile(),
            baseline_relative=Path("data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24"),
            output_relative=Path("data/runtime/p1-curry-consumption-reservation-offline-2026-10-24"),
        )
        args = type("Args", (), {
            "baseline_dir": repo / profile.baseline_relative,
            "output": repo / profile.output_relative / "reservation.json",
        })()
        with self.assertRaisesRegex(ValueError, "linked_path_rejected"):
            reservation._validate_locations(args, repo, profile)
        self.assertEqual(list(outside.iterdir()), [])

    def test_output_parent_link_guard_runs_before_creation_even_without_symlink_support(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-consumption-reservation-tests" / uuid.uuid4().hex
        repo = scratch / "repo"
        repo.mkdir(parents=True, exist_ok=False)
        (repo / ".gitignore").write_text("data/runtime\n", encoding="utf-8")
        profile = replace(
            reservation._production_profile(),
            baseline_relative=Path("data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24"),
            output_relative=Path("data/runtime/p1-curry-consumption-reservation-offline-2026-10-24"),
        )
        args = type("Args", (), {
            "baseline_dir": repo / profile.baseline_relative,
            "output": repo / profile.output_relative / "reservation.json",
        })()
        real_safe_path = reservation.safe_path
        checked = []

        def reject_parent(path, *, file=False):
            checked.append(Path(path))
            if Path(path) == repo / "data/runtime":
                raise ValueError("linked_path_rejected")
            return real_safe_path(path, file=file)

        with patch.object(reservation, "safe_path", side_effect=reject_parent):
            with self.assertRaisesRegex(ValueError, "linked_path_rejected"):
                reservation._validate_locations(args, repo, profile)
        self.assertIn(repo / "data/runtime", checked)
        self.assertFalse((repo / profile.output_relative).exists())


if __name__ == "__main__":
    unittest.main()
