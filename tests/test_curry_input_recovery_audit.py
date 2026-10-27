"""Synthetic-only tests for the Curry frozen-input recovery audit."""
from __future__ import annotations

import hashlib
import json
import shutil
import stat
import unittest
import zipfile
from pathlib import Path
import uuid
from contextlib import contextmanager
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_data.identity import canonical, digest
from ygo_eval import curry_input_recovery_audit as audit
from ygo_eval import native_curry_option_validation as curry


class CurryInputRecoveryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]
        cls.schema = json.loads(
            (cls.repo / "schemas/curry-input-recovery-audit-v1.schema.json").read_bytes()
        )
        cls.schema_v2 = json.loads(
            (cls.repo / "schemas/curry-input-recovery-audit-v2.schema.json").read_bytes()
        )
        cls.diagnostic_schema = json.loads(
            (cls.repo / "schemas/curry-input-recovery-diagnostic-v1.schema.json").read_bytes()
        )

    @contextmanager
    def _temporary_root(self):
        parent = self.repo / "target/curry-input-recovery-tests/python-synthetic"
        parent.mkdir(parents=True, exist_ok=True)
        root = parent / uuid.uuid4().hex
        root.mkdir(exist_ok=False)
        try:
            yield root
        finally:
            shutil.rmtree(root)

    def test_audit_recomputes_semantic_roles_and_separates_raw_protection(self):
        with self._temporary_root() as root:
            base = {"case_id": "rabbit", "request": {"seed": 1}}
            candidate = {"case_id": "prompt-14-curry-v1", "deck": [1, 2]}
            container = root / "cases.json"
            container.write_bytes(canonical({"cases": [base, candidate, {"case_id": "other"}]}))
            files = {"base_request": container, "candidate_case": container}
            expected = {
                "base_request": hashlib.sha256(curry._case_encode(base)).hexdigest(),
                "candidate_case": hashlib.sha256(curry._case_encode(candidate)).hexdigest(),
            }

            result = audit.audit_hash_role_semantics(files, {
                "base_request": base,
                "candidate_case": candidate,
            }, expected)

            self.assertEqual(result["repaired_gate_passed"], True)
            self.assertEqual(
                [item["role"] for item in result["legacy_raw_mismatches"]],
                ["base_request", "candidate_case"],
            )
            self.assertEqual(
                result["raw_file_sha256"][container.resolve().as_posix()],
                hashlib.sha256(container.read_bytes()).hexdigest(),
            )
            self.assertNotEqual(
                result["semantic_sha256"]["base_request"],
                result["raw_file_sha256"][container.resolve().as_posix()],
            )

    def test_source_archive_pair_accepts_only_the_three_document_changes(self):
        with self._temporary_root() as root:
            native_archive, native_list = self._archive(root, "native", {
                "TASKS.md": b"old tasks",
                "docs/TESTING.md": b"old testing",
            })
            final_archive, final_list = self._archive(root, "final", {
                "TASKS.md": b"new tasks",
                "docs/TESTING.md": b"new testing",
                audit.CONFIRMATION_HANDOFF_RELATIVE.as_posix(): b"handoff",
            })
            native_listing = json.loads(native_list.read_bytes())
            final_listing = json.loads(final_list.read_bytes())

            result = audit.verify_source_archive_pair(
                native_archive, native_list, final_archive, final_list,
                expected_native_count=2, expected_final_count=3,
                expected_native_archive_sha256=hashlib.sha256(native_archive.read_bytes()).hexdigest(),
                expected_native_list_sha256=hashlib.sha256(native_list.read_bytes()).hexdigest(),
                expected_native_identity=native_listing["source_identity"],
                expected_final_archive_sha256=hashlib.sha256(final_archive.read_bytes()).hexdigest(),
                expected_final_list_sha256=hashlib.sha256(final_list.read_bytes()).hexdigest(),
                expected_final_identity=final_listing["source_identity"],
                expected_head="synthetic-head",
            )

            self.assertEqual(result["differences"], sorted(audit.ALLOWED_ARCHIVE_DIFFS))
            self.assertEqual(result["native_file_count"], 2)
            self.assertEqual(result["final_file_count"], 3)
            (root / "extra.txt").write_bytes(b"extra")
            with zipfile.ZipFile(final_archive, "w") as archive:
                archive.writestr("extra.txt", b"extra")
            with self.assertRaisesRegex(ValueError, "source_archive_membership_invalid"):
                audit.verify_source_archive_pair(
                    native_archive, native_list, final_archive, final_list,
                    expected_native_count=2, expected_final_count=3,
                    expected_native_archive_sha256=hashlib.sha256(native_archive.read_bytes()).hexdigest(),
                    expected_native_list_sha256=hashlib.sha256(native_list.read_bytes()).hexdigest(),
                    expected_native_identity=native_listing["source_identity"],
                    expected_final_archive_sha256=hashlib.sha256(final_archive.read_bytes()).hexdigest(),
                    expected_final_list_sha256=hashlib.sha256(final_list.read_bytes()).hexdigest(),
                    expected_final_identity=final_listing["source_identity"],
                    expected_head="synthetic-head",
                )

    def test_archived_source_member_hashes_are_derived_from_authenticated_file_list(self):
        native_hashes = {
            audit.NATIVE_SOURCE_PATH: "a" * 64,
            audit.RESEARCH_SOURCE_PATH: "b" * 64,
        }
        native_bytes = {audit.NATIVE_SOURCE_PATH: b"native module", audit.RESEARCH_SOURCE_PATH: b"research module"}
        native_hashes = {name: hashlib.sha256(value).hexdigest() for name, value in native_bytes.items()}

        result = audit.verify_archived_refusal_source_members(native_hashes, native_bytes)

        self.assertEqual({item["role"] for item in result}, {"native_module", "research_module"})
        self.assertTrue(all(item["status"] == "passed" for item in result))
        swapped = {
            audit.NATIVE_SOURCE_PATH: native_hashes[audit.RESEARCH_SOURCE_PATH],
            audit.RESEARCH_SOURCE_PATH: native_hashes[audit.NATIVE_SOURCE_PATH],
        }
        records = []
        with self.assertRaisesRegex(ValueError, "archived_source_member_hash_mismatch"):
            audit.verify_archived_refusal_source_members(swapped, native_bytes, records)
        self.assertEqual(records[0]["status"], "failed")

    def test_manifest_role_records_protect_raw_container_bytes(self):
        with self._temporary_root() as root:
            base = {"case_id": "rabbit", "request": {"seed": 1}}
            candidate = {"case_id": "prompt-14-curry-v1", "deck": [1, 2]}
            container = root / "cases.json"
            container.write_bytes(canonical({"cases": [base, candidate, {"case_id": "other"}]}))
            result = audit.audit_hash_role_semantics(
                {"base_request": container, "candidate_case": container},
                {"base_request": base, "candidate_case": candidate},
                {role: hashlib.sha256(curry._case_encode(value)).hexdigest()
                 for role, value in (("base_request", base), ("candidate_case", candidate))},
            )

            records = audit.manifest_role_input_records(root, {
                "base_request": container, "candidate_case": container,
            }, result["raw_file_sha256"])

            raw_hash = hashlib.sha256(container.read_bytes()).hexdigest()
            self.assertEqual([record["sha256"] for record in records], [raw_hash, raw_hash])
            self.assertNotEqual(records[0]["sha256"], result["semantic_sha256"]["base_request"])

    def test_v2_report_exit_codes_are_unknown_until_each_source_is_verified(self):
        report = audit.new_report(report_version=2)
        self.assertIsNone(report["historical_exit_observation"]["observation_exit_code"])
        self.assertIsNone(report["historical_exit_observation"]["archived_refusal_branch_return_code"])
        self.assertFalse(report["historical_exit_observation"]["historical_exit_code_certified"])
        self.assertEqual(report["schema_version"], 2)
        self.assertTrue(audit.validate_report(report))
        Draft202012Validator(self.schema_v2).validate(report)

        report["historical_exit_observation"]["observation_exit_code"] = 1
        with self.assertRaisesRegex(ValueError, "historical_exit_observation_checkpoint_mismatch"):
            audit.validate_report(report)
        with self.assertRaises(Exception):
            Draft202012Validator(self.schema_v2).validate(report)
        report["checks"]["acceptance_delivery_anchors"] = "passed"
        with self.assertRaisesRegex(ValueError, "historical_exit_observation_checkpoint_mismatch"):
            audit.validate_report(report)
        with self.assertRaises(Exception):
            Draft202012Validator(self.schema_v2).validate(report)
        report["checks"]["evidence_inventory"] = "passed"
        self.assertTrue(audit.validate_report(report))
        report["historical_exit_observation"]["archived_refusal_branch_return_code"] = 2
        with self.assertRaisesRegex(ValueError, "historical_exit_observation_checkpoint_mismatch"):
            audit.validate_report(report)
        with self.assertRaises(Exception):
            Draft202012Validator(self.schema_v2).validate(report)
        report["checks"]["source_archives"] = "passed"
        self.assertTrue(audit.validate_report(report))

    def test_confirmation_source_baseline_uses_asset_audit_root(self):
        from ygo_eval.native_curry_option_validation import CONFIRMATION_SCOPE

        source_root = audit._confirmation_source_baseline(self.repo)
        self.assertEqual(source_root, (self.repo / CONFIRMATION_SCOPE.baseline_root).resolve())
        self.assertNotEqual(source_root, self.repo / CONFIRMATION_SCOPE.output_root)

    def test_production_source_description_preserves_fixed_audit_pins(self):
        """The immutable source catalog must describe, not execute, the fixed pins."""
        from ygo_eval.native_curry_option_validation import PINNED_INPUT_SHA256

        sources = audit._production_source_description()
        baseline = "data/runtime/p1-curry-option-confirmation-native-2026-10-24"

        described_files = {
            item.relative_path: item.sha256
            for item in sources.files
        }
        self.assertEqual(described_files, {
            f"{baseline}/acceptance.json": audit.ACCEPTANCE_SHA256,
            f"{baseline}/final-build/delivery.json": audit.DELIVERY_SHA256,
            f"{baseline}/evidence-inventory.json": audit.INVENTORY_SHA256,
            **{f"{baseline}/{path}": sha256 for path, sha256 in audit._CONFIRMATION_INVENTORY_PINS},
        })
        self.assertEqual(len(audit._CONFIRMATION_INVENTORY_PINS), 40)

        self.assertEqual(
            sources.file_sha256("data/runtime/p1-curry-option-confirmation-native-2026-10-24/acceptance.json"),
            audit.ACCEPTANCE_SHA256,
        )
        self.assertEqual(
            sources.archive("confirmation_native_archive").archive_sha256,
            audit.NATIVE_ARCHIVE_SHA256,
        )
        self.assertEqual(
            sources.semantic_sha256("base_request"),
            PINNED_INPUT_SHA256["base_request"],
        )
        self.assertEqual(
            sources.semantic_sha256("candidate_case"),
            PINNED_INPUT_SHA256["candidate_case"],
        )
        self.assertEqual(
            sources.differences("confirmation"),
            tuple(sorted(audit.ALLOWED_ARCHIVE_DIFFS)),
        )
        self.assertEqual(
            sources.dataset_count("historical_ledgers"),
            audit.HISTORICAL_LEDGER_COUNT,
        )
        self.assertFalse(hasattr(sources, "valid"))
        self.assertFalse(hasattr(sources, "checks"))

    def test_production_source_description_matches_local_inventory(self):
        baseline = "data/runtime/p1-curry-option-confirmation-native-2026-10-24"
        baseline_path = self.repo / baseline
        try:
            baseline_path.lstat()
        except FileNotFoundError:
            self.skipTest("historical evidence baseline is not present")
        self.assertTrue(stat.S_ISDIR(baseline_path.stat().st_mode), "baseline must be a directory")
        inventory_path = baseline_path / "evidence-inventory.json"
        inventory_stat = inventory_path.lstat()
        self.assertTrue(stat.S_ISREG(inventory_stat.st_mode), "inventory must be a regular file")
        inventory_bytes = inventory_path.read_bytes()
        self.assertEqual(hashlib.sha256(inventory_bytes).hexdigest(), audit.INVENTORY_SHA256)
        inventory = json.loads(inventory_bytes)
        sources = audit._production_source_description()
        described_files = {item.relative_path: item.sha256 for item in sources.files}
        self.assertEqual(described_files, {
            f"{baseline}/acceptance.json": audit.ACCEPTANCE_SHA256,
            f"{baseline}/final-build/delivery.json": audit.DELIVERY_SHA256,
            f"{baseline}/evidence-inventory.json": audit.INVENTORY_SHA256,
            **{f"{baseline}/{item['path']}": item["sha256"] for item in inventory["entries"]},
        })
        self.assertEqual(len(inventory["entries"]), 40)
        self.assertEqual(audit._CONFIRMATION_INVENTORY_PINS, tuple(
            (item["path"], item["sha256"]) for item in inventory["entries"]
        ))

    def test_confirmation_manifest_pins_follow_private_source_description(self):
        """Synthetic public sources must reach the existing manifest validator."""
        from ygo_eval.native_curry_option_validation import (
            CONFIRMATION_INPUT_ROLES,
            CONFIRMATION_SCOPE,
            HISTORICAL_SOURCE_TRANSITION,
        )

        static = audit._SourceDescription(
            role="static_preparation",
            files=tuple(
                audit._PinnedFile(role, path, hashlib.sha256(role.encode()).hexdigest())
                for role, path in (
                    ("preparation", "synthetic/preparation.json"),
                    ("preparation_report", "synthetic/preparation-report.json"),
                    ("preparation_acceptance", "synthetic/preparation-acceptance.json"),
                    ("operations_source", "synthetic/operations.cpp"),
                    ("adapter_codec", "synthetic/codec.rs"),
                )
            ),
            semantic_hashes=(
                ("base_request", "1" * 64),
                ("candidate_case", "2" * 64),
            ),
        )
        asset = audit._SourceDescription(
            role="asset_audit",
            files=(
                audit._PinnedFile("asset_audit_delivery", "synthetic/delivery.json", "3" * 64),
                audit._PinnedFile("asset_audit_audit", "synthetic/audit.json", "4" * 64),
            ),
        )
        sources = audit._SourceDescription(
            role="confirmation", children=(static, asset),
        )
        request = {"protocol_version": 2, "seed": 1, "decisions": [], "engine": {}}
        pins = {
            "preparation": static.file_sha256("synthetic/preparation.json"),
            "preparation_report": static.file_sha256("synthetic/preparation-report.json"),
            "preparation_acceptance": static.file_sha256("synthetic/preparation-acceptance.json"),
            "candidate_case": static.semantic_sha256("candidate_case"),
            "base_request": static.semantic_sha256("base_request"),
            "operations_source": static.file_sha256("synthetic/operations.cpp"),
            "adapter_codec": static.file_sha256("synthetic/codec.rs"),
            "baseline_delivery": asset.file_sha256("synthetic/delivery.json"),
            "baseline_audit": asset.file_sha256("synthetic/audit.json"),
        }
        pins.update({role: "f" * 64 for role in CONFIRMATION_INPUT_ROLES if role not in pins})
        manifest = {
            "schema_version": 1,
            "kind": "native_curry_option_confirmation_manifest",
            "scope": CONFIRMATION_SCOPE.scope,
            "batch_kind": CONFIRMATION_SCOPE.batch_kind,
            "started_at": 1,
            "limit": CONFIRMATION_SCOPE.limit,
            "planned_calls": CONFIRMATION_SCOPE.limit,
            "wall_seconds": CONFIRMATION_SCOPE.wall_seconds,
            "old_consumed": CONFIRMATION_SCOPE.old_consumed,
            "baseline_audit_sha256": "4" * 64,
            "baseline_delivery_sha256": "3" * 64,
            "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
            "historical_source_transition": HISTORICAL_SOURCE_TRANSITION,
            "request": request,
            "stage1_request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
            "source": {}, "build": {}, "assets": {}, "input_sha256": pins,
            **curry.FLAGS,
        }
        manifest["context"] = hashlib.sha256(canonical(manifest)).hexdigest()

        with self.assertRaisesRegex(ValueError, "curry_manifest_binding_invalid"):
            curry.validate_curry_report(manifest, spec=CONFIRMATION_SCOPE)
        self.assertTrue(curry.validate_curry_report(
            manifest, spec=CONFIRMATION_SCOPE, _sources=sources,
        ))

    def test_nested_source_descriptions_keep_counts_scoped_to_the_nearest_node(self):
        leaf = audit._SourceDescription(
            role="historical_prefix", dataset_counts=(("historical_consumed", 26),),
        )
        root = audit._SourceDescription(
            role="complete_history",
            dataset_counts=(("historical_consumed", 32),),
            children=(leaf,),
        )

        self.assertEqual(root.dataset_count("historical_consumed"), 32)
        self.assertEqual(root.child("historical_prefix").dataset_count("historical_consumed"), 26)

    def test_v2_failure_cleanup_rechecks_collected_sources_without_replacing_primary_checkpoint(self):
        with self._temporary_root() as root:
            baseline = root / "confirmation"
            baseline.mkdir()
            (baseline / "research").mkdir()
            source = {"head": "synthetic", "identity": "a" * 64, "files": {}}
            report = audit.new_report(report_version=2)
            report["status"] = "failed"
            report["failure_checkpoint"] = "source_archives"
            report["checks"]["acceptance_delivery_anchors"] = "passed"
            report["checks"]["evidence_inventory"] = "passed"
            report["checks"]["source_archives"] = "failed"

            with patch("ygo_data.identity.stable_source", return_value=source):
                audit._finish_v2_stability(
                    root, baseline, report, source, audit._snapshot_tree(baseline),
                )

            self.assertEqual(report["failure_checkpoint"], "source_archives")
            self.assertEqual(report["checks"]["source_archives"], "failed")
            self.assertEqual(report["stability"]["source_identity"], "passed")
            self.assertEqual(report["stability"]["confirmation_tree"], "passed")
            self.assertIsNone(report["confirmation_scope"]["new_consumed"])
            self.assertFalse((baseline / "research/calls.jsonl").exists())

    def test_v2_protected_scan_failure_is_not_misreported_as_not_collected(self):
        with self._temporary_root() as root:
            baseline = root / "confirmation"
            baseline.mkdir()
            protected = root / "protected.bin"
            protected.write_bytes(b"protected")
            report = audit.new_report(report_version=2)
            report["status"] = "failed"
            report["failure_checkpoint"] = "old_material_protection"
            report["checks"].update({
                "acceptance_delivery_anchors": "passed",
                "evidence_inventory": "passed",
                "source_archives": "passed",
                "frozen_input_binding": "passed",
                "historical_ledgers": "passed",
                "old_material_protection": "failed",
            })
            report["historical_exit_observation"].update({
                "observation_exit_code": 1,
                "archived_refusal_branch_return_code": 2,
            })
            report["_private_protected_expected"] = {protected: "0" * 64}
            report["_private_protected_material_status"] = "failed"
            source = {"head": "synthetic", "identity": "a" * 64, "files": {}}

            with patch("ygo_data.identity.stable_source", return_value=source):
                audit._finish_v2_stability(root, baseline, report, source, audit._snapshot_tree(baseline))

            self.assertEqual(report["failure_checkpoint"], "old_material_protection")
            self.assertEqual(report["stability"]["protected_material"], "failed")
            self.assertIn("historical_protected_input_changed", report["diagnostics"])
            report.pop("_private_protected_expected")
            report.pop("_private_protected_material_status")
            self.assertTrue(audit.validate_report(report))
            Draft202012Validator(self.schema_v2).validate(report)

    def test_v2_success_report_binds_each_source_member_and_unknown_native_exit(self):
        report = audit.new_report(report_version=2)
        report["status"] = "passed"
        report["tool_identity"] = {"head": "synthetic-head", "identity": "d" * 64, "file_count": 3}
        report["historical"] = {
            "consumed": 32, "unknown": 0, "ledger_count": 9,
            "verified_without_writable_journal": True, "input_set_sha256": "a" * 64,
        }
        report["confirmation_scope"]["prepared"] = True
        report["hash_mismatch"] = {
            "legacy_comparison": "raw_container_file_sha256",
            "manifest_role_hashing": "canonical_extracted_object_sha256",
            "first_legacy_mismatch_role": "base_request",
            "legacy_raw_mismatches": [
                {"role": role, "expected_object_sha256": "a" * 64,
                 "container_file_sha256": "b" * 64, "actual_object_sha256": "a" * 64}
                for role in ("base_request", "candidate_case")
            ],
            "semantic_sha256": {"base_request": "a" * 64, "candidate_case": "a" * 64},
            "container_file_sha256": {"base_request": "b" * 64, "candidate_case": "b" * 64},
            "repaired_shared_gate_passed": True, "old_confirmation_report_rewritten": False,
        }
        report["source_archives"] = [
            {"archive_sha256": "a" * 64, "archive_bytes": 1,
             "file_list_sha256": "b" * 64, "source_identity": "c" * 64,
             "file_count": 1, "role": role}
            for role in ("native_time", "final")
        ]
        report["source_archive_differences"] = sorted(audit.ALLOWED_ARCHIVE_DIFFS)
        report["checks"] = {name: "passed" for name in audit.CHECK_NAMES}
        report["historical_exit_observation"].update({
            "observation_exit_code": 1,
            "archived_refusal_branch_return_code": 2,
        })
        report["archived_source_members"] = [
            {"role": "native_module", "path": audit.NATIVE_SOURCE_PATH,
             "expected_sha256": "a" * 64, "actual_sha256": "a" * 64, "status": "passed"},
            {"role": "research_module", "path": audit.RESEARCH_SOURCE_PATH,
             "expected_sha256": "b" * 64, "actual_sha256": "b" * 64, "status": "passed"},
        ]
        report["stability"] = {
            "source_identity": "passed", "confirmation_tree": "passed",
            "protected_material": "passed", "confirmation_ledger_absence": "passed",
            "ledger_absent_before": True, "ledger_absent_after": True,
        }

        self.assertTrue(audit.validate_report(report))
        Draft202012Validator(self.schema_v2).validate(report)
        for mutation in ("swapped_path", "different_hash"):
            forged = json.loads(json.dumps(report))
            if mutation == "swapped_path":
                forged["archived_source_members"][0]["path"] = audit.RESEARCH_SOURCE_PATH
            else:
                forged["archived_source_members"][0]["actual_sha256"] = "f" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit.validate_report(forged)

    def test_v2_failure_report_requires_checkpoint_and_records_best_effort_stability(self):
        report = audit.new_report(report_version=2)
        report["status"] = "failed"
        report["failure_checkpoint"] = "source_archives"
        report["checks"]["acceptance_delivery_anchors"] = "passed"
        report["checks"]["evidence_inventory"] = "passed"
        report["checks"]["source_archives"] = "failed"
        report["historical_exit_observation"]["observation_exit_code"] = 1
        report["diagnostics"] = ["archived_refusal_source_hash_mismatch"]
        report["stability"]["source_identity"] = "passed"
        report["stability"]["confirmation_tree"] = "passed"

        self.assertTrue(audit.validate_report(report))
        Draft202012Validator(self.schema_v2).validate(report)
        forged = json.loads(json.dumps(report))
        forged["checks"]["frozen_input_binding"] = "passed"
        with self.assertRaisesRegex(ValueError, "audit_v2_failure_progression_invalid"):
            audit.validate_report(forged)

    def test_v2_inventory_failure_saves_report_after_anchor_checkpoint(self):
        from ygo_eval.native_curry_option_validation import CONFIRMATION_SCOPE

        with self._temporary_root() as root:
            baseline = root / "data/runtime/p1-curry-option-confirmation-native-2026-10-24"
            (baseline / "research").mkdir(parents=True)
            (baseline / "final-build").mkdir()
            expected_accounting = {
                "cumulative_consumed": None,
                "historical_consumed": 32,
                "historical_unknown": 0,
                "new_consumed": None,
                "new_unknown": None,
                "status": "unknown_without_authenticated_ledger",
            }
            qualification = {
                "complete_action_coverage": False,
                "global_optimality": False,
                "issuance_evidence": "unknown",
                "native_probability_verified": False,
                "proof_ready": False,
                "successful": False,
            }
            acceptance = {
                "schema_version": 1,
                "kind": "native_curry_option_confirmation_acceptance",
                "scope": CONFIRMATION_SCOPE.scope,
                "status": "partial",
                "accounting": expected_accounting,
                "qualification": qualification,
            }
            delivery = {
                "schema_version": 1,
                "kind": "native_curry_option_confirmation_delivery",
                "status": "partial_stopped_before_authenticated_stage",
                "accounting": expected_accounting,
                "qualification": qualification,
                "scope": {
                    "id": CONFIRMATION_SCOPE.scope,
                    "request_limit": 7,
                    "wall_seconds_limit": 7200,
                },
                "prepared": {"prepared": True, "execution_ready": True, "native_calls": 0},
                "verification": {"valid": False},
                "normal_attempt": {
                    "exit_code": 1,
                    "worker_request_consumption": None,
                    "authenticated_ledger_present": False,
                },
            }
            observation = {
                "kind": "curry_option_confirmation_normal_attempt_observation",
                "exit_code": 1,
                "worker_request_consumption": None,
                "normal_process_diagnostic_present": False,
                "raw_process_output_saved": False,
            }
            acceptance_raw = canonical(acceptance)
            delivery_raw = canonical(delivery)
            (baseline / "acceptance.json").write_bytes(acceptance_raw)
            (baseline / "final-build/delivery.json").write_bytes(delivery_raw)
            (baseline / "research/normal-attempt-observation.json").write_bytes(canonical(observation))
            report_path = root / "audit-report.json"

            with (
                patch.object(audit, "ACCEPTANCE_SHA256", hashlib.sha256(acceptance_raw).hexdigest()),
                patch.object(audit, "DELIVERY_SHA256", hashlib.sha256(delivery_raw).hexdigest()),
                patch.object(audit, "_verify_evidence_inventory", side_effect=ValueError("evidence_inventory_contract_mismatch")),
                patch("ygo_data.identity.stable_source", return_value={
                    "head": "synthetic-head", "identity": "a" * 64, "files": {"marker": "b" * 64},
                }),
            ):
                report = audit._run_audit(root, baseline, root, report_path, report_version=2)

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failure_checkpoint"], "evidence_inventory")
            self.assertEqual(report["checks"]["acceptance_delivery_anchors"], "passed")
            self.assertEqual(report["checks"]["evidence_inventory"], "failed")
            self.assertIsNone(report["historical_exit_observation"]["observation_exit_code"])
            self.assertIsNone(report["historical_exit_observation"]["archived_refusal_branch_return_code"])
            self.assertTrue(report_path.is_file())
            saved = json.loads(report_path.read_bytes())
            self.assertEqual(saved, report)
            Draft202012Validator(self.schema_v2).validate(saved)

    def test_failure_report_keeps_unknown_consumption_and_never_claims_execution_ready(self):
        report = audit.new_report()
        report["status"] = "failed"
        report["failure_checkpoint"] = "frozen_input_binding"
        report["diagnostics"] = ["frozen_input_rejected"]
        report["checks"]["frozen_input_binding"] = "failed"

        self.assertTrue(audit.validate_report(report))
        Draft202012Validator(self.schema).validate(report)
        self.assertEqual(report["native_calls"], 0)
        self.assertFalse(report["execution_ready"])
        self.assertIsNone(report["historical"]["consumed"])
        self.assertIsNone(report["historical"]["unknown"])
        self.assertEqual(report["confirmation_scope"]["new_consumed"], None)
        self.assertEqual(report["confirmation_scope"]["new_unknown"], None)

    def test_failure_report_requires_checkpoint_to_match_failed_check(self):
        report = audit.new_report()
        report["status"] = "failed"
        report["failure_checkpoint"] = "historical_ledgers"
        report["checks"]["historical_ledgers"] = "passed"
        report["diagnostics"] = ["historical_ledger_totals_mismatch"]
        with self.assertRaisesRegex(ValueError, "audit_failure_checkpoint_inconsistent"):
            audit.validate_report(report)

    def test_audit_never_turns_historical_prepared_state_into_execution_authority(self):
        report = audit.new_report()
        report["confirmation_scope"]["prepared"] = True
        report["confirmation_scope"]["execution_ready"] = True
        with self.assertRaisesRegex(ValueError, "confirmation_consumption_must_remain_unknown"):
            audit.validate_report(report)

    def test_success_report_schema_keeps_native_scope_unready(self):
        report = audit.new_report()
        report["status"] = "passed"
        report["tool_identity"] = {"head": "synthetic-head", "identity": "d" * 64, "file_count": 1}
        report["historical"] = {
            "consumed": 32,
            "unknown": 0,
            "ledger_count": 9,
            "verified_without_writable_journal": True,
            "input_set_sha256": "a" * 64,
        }
        report["confirmation_scope"]["prepared"] = True
        report["hash_mismatch"] = {
            "legacy_comparison": "raw_container_file_sha256",
            "manifest_role_hashing": "canonical_extracted_object_sha256",
            "first_legacy_mismatch_role": "base_request",
            "legacy_raw_mismatches": [
                {"role": role, "expected_object_sha256": "a" * 64,
                 "container_file_sha256": "b" * 64, "actual_object_sha256": "a" * 64}
                for role in ("base_request", "candidate_case")
            ],
            "semantic_sha256": {"base_request": "a" * 64, "candidate_case": "a" * 64},
            "container_file_sha256": {"base_request": "b" * 64, "candidate_case": "b" * 64},
            "repaired_shared_gate_passed": True,
            "old_confirmation_report_rewritten": False,
        }
        report["source_archives"] = [
            {"archive_sha256": "a" * 64, "archive_bytes": 1,
             "file_list_sha256": "b" * 64, "source_identity": "c" * 64,
             "file_count": 1, "role": role}
            for role in ("native_time", "final")
        ]
        report["source_archive_differences"] = sorted(audit.ALLOWED_ARCHIVE_DIFFS)
        report["checks"] = {name: "passed" for name in audit.CHECK_NAMES}

        self.assertTrue(audit.validate_report(report))
        Draft202012Validator(self.schema).validate(report)

    def test_pre_stage_refusal_diagnostic_is_path_free_and_schema_valid(self):
        with self._temporary_root() as root:
            (root / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
            mismatch = curry.CurryFrozenInputMismatch("base_request", "a" * 64, "b" * 64)
            path, expected = curry._save_pre_stage_refusal_diagnostic(
                root, mismatch, curry.CONFIRMATION_SCOPE,
            )
            raw = path.read_bytes()
            value = json.loads(raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            self.assertTrue(curry._validate_pre_stage_refusal_diagnostic(value))
            Draft202012Validator(self.diagnostic_schema).validate(value)
            self.assertEqual(value["role"], "base_request")
            self.assertNotIn(str(root).encode(), raw)
            self.assertFalse((root / "data/runtime/p1-curry-option-confirmation-native-2026-10-24/research/calls.jsonl").exists())

    def test_diagnostic_save_failure_is_fail_closed(self):
        with self._temporary_root() as root:
            (root / ".gitignore").write_text("# no protected output rule\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "curry_refusal_diagnostic_save_failed"):
                curry._save_pre_stage_refusal_diagnostic(
                    root, ValueError("stable failure"), curry.CONFIRMATION_SCOPE,
                )

    @staticmethod
    def _archive(root: Path, role: str, contents: dict[str, bytes]):
        archive_path = root / f"{role}.zip"
        listing_path = root / f"{role}.json"
        files = {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()}
        head = "synthetic-head"
        identity = digest(canonical({"head": head, "files": files}))
        listing = {
            "schema_version": 1,
            "kind": "workspace_source_archive",
            "head": head,
            "file_count": len(files),
            "source_identity": identity,
            "files": files,
        }
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in contents.items():
                archive.writestr(name, value)
        listing_path.write_bytes(canonical(listing))
        return archive_path, listing_path


if __name__ == "__main__":
    unittest.main()
