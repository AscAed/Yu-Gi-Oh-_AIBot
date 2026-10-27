"""Fixed offline Ground Collapse preparation source and report gates."""
from __future__ import annotations

import json
import hashlib
import copy
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
import uuid
from contextlib import closing
from unittest.mock import patch
from jsonschema import Draft202012Validator, ValidationError

from ygo_data.identity import source_identity
from ygo_eval.ground_collapse_preparation import (
    EMPTY_FUTURE_NATIVE_BINDING,
    PreparationError,
    PRODUCTION_PROFILE,
    _fixed_selection_rules,
    _run_sources,
    _check_tool_bundle,
    _report_base,
    _synthetic_protocol_vectors,
    _verify_saved_tool_bundle,
    _verify_only,
    _verify_old_prompt_preparation,
    _verify_runtime_and_core,
    _Capture,
    _validate_publication_diagnostic,
    encode,
    prepare_ground_collapse_probe,
    sha256,
    strict_json,
    validate_report,
)
from ygo_eval.prompt_probe_logic import derive_candidates


def _workspace_metadata(listing: dict) -> dict:
    # The tool listing pins only the selected source members; report metadata
    # also carries the full workspace count captured at the same time.
    return {
        "identity": listing["workspace_identity"],
        "files": {str(index): None for index in range(listing["workspace_file_count"])},
    }


def _synthetic_tool_bundle(profile, identity="a" * 64) -> dict:
    return {
        "file_count": len(profile.tool_files),
        "archive_sha256": "c" * 64,
        "file_list_sha256": "d" * 64,
        "source_identity": identity,
    }


class GroundCollapsePreparationContractTests(unittest.TestCase):
    def test_capture_retains_only_stage_requests_needed_for_ledger_revalidation(self):
        repo = Path(__file__).resolve().parents[1]
        capture = _Capture()
        request = repo / "target/ground-collapse-preparation-tests/capture-request.json"
        asset = repo / "target/ground-collapse-preparation-tests/capture-large-asset.bin"
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_bytes(b'{"request":1}')
        asset.write_bytes(b"synthetic asset")

        capture.read("latest_curry_stage_request_1", request)
        capture.read("cdb", asset)

        self.assertEqual(capture.role_bytes["latest_curry_stage_request_1"], b'{"request":1}')
        self.assertNotIn("cdb", capture.role_bytes)

    def test_publication_diagnostic_rejects_boolean_schema_version(self):
        diagnostic = {
            "schema_version": True,
            "kind": "ground_collapse_preparation_publication_diagnostic_v1",
            "checkpoint": "report_publication",
            "code": "synthetic_failure",
            "role": "report",
            "native_calls": 0,
            "runner_process_calls": 0,
            "worker_calls": 0,
            "ffi_calls": 0,
            "execution_ready": False,
        }
        with self.assertRaisesRegex(PreparationError, "publication_diagnostic_invalid"):
            _validate_publication_diagnostic(diagnostic)

    def test_failure_report_with_non_object_accounting_is_rejected_cleanly(self):
        report = _report_base(
            PRODUCTION_PROFILE,
            _synthetic_tool_bundle(PRODUCTION_PROFILE),
            _Capture(),
            {"identity": "a" * 64, "files": {}},
        )
        report["diagnostics"] = [{"checkpoint": "source_checks", "code": "synthetic_failure",
                                  "role": "source"}]
        report["accounting"] = None
        with self.assertRaisesRegex(PreparationError, "report_accounting_invalid"):
            validate_report(report, schema=None)

    def test_schema_validation_fails_closed_when_optional_validator_is_unavailable(self):
        import builtins

        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/ground-collapse-preparation-v1.schema.json").read_bytes())
        report = _report_base(PRODUCTION_PROFILE, _synthetic_tool_bundle(PRODUCTION_PROFILE), _Capture(),
                              {"identity": "a" * 64, "files": {}})
        report["diagnostics"] = [{"checkpoint": "", "code": "", "role": "bad role/path"}]
        real_import = builtins.__import__

        def import_without_jsonschema(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("synthetic optional dependency absence")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_jsonschema):
            with self.assertRaisesRegex(PreparationError, "report_schema_validator_unavailable"):
                validate_report(report, schema=schema)

    def test_tool_bundle_uses_the_supplied_source_collector(self):
        repo = Path(__file__).resolve().parents[1] / "target/ground-collapse-preparation-tests" / f"collector-{uuid.uuid4().hex}"
        repo.mkdir(parents=True)
        (repo / "tool.py").write_bytes(b"synthetic tool\n")
        profile = replace(PRODUCTION_PROFILE, tool_files=("tool.py",))
        identity = {"identity": "f" * 64, "files": {"tool.py": hashlib.sha256(b"synthetic tool\n").hexdigest()}}
        listing, _list_raw, _archive_raw = _check_tool_bundle(
            repo, profile, source_collector=lambda _repo: identity,
        )
        self.assertEqual(listing["workspace_identity"], identity["identity"])

    def test_schema_rejects_unrecognized_protocol_vector_claims(self):
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/ground-collapse-preparation-v1.schema.json").read_bytes())
        vectors_schema = schema["properties"]["protocol_vectors"]
        self.assertTrue(Draft202012Validator(vectors_schema).is_valid(_synthetic_protocol_vectors()))
        self.assertFalse(Draft202012Validator(vectors_schema).is_valid({"unverified_claim": True}))

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
            strict_json(b'{"x":1,"x":2}')

    def test_production_profile_has_fixed_candidate_and_six_core_pins(self):
        self.assertEqual(PRODUCTION_PROFILE.candidate_id, "prompt-24-collapse-v1")
        self.assertEqual(PRODUCTION_PROFILE.candidate_card_id, 90502999)
        self.assertEqual(len(PRODUCTION_PROFILE.core_pins), 6)
        self.assertEqual(PRODUCTION_PROFILE.prior_certified_consumed, 40)
        self.assertEqual(PRODUCTION_PROFILE.policy_reserved, 7)
        self.assertEqual(PRODUCTION_PROFILE.planning_total, 47)

    def test_report_schema_and_python_validator_reject_execution_qualification(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "ground-collapse-preparation-v1.schema.json"
        schema = json.loads(schema_path.read_bytes())
        self.assertEqual(schema["properties"]["kind"]["const"], "ground_collapse_preparation_v1")
        report = {
            "schema_version": 1,
            "kind": "ground_collapse_preparation_v1",
            "status": "failed",
            "preparation_successful": False,
            "source_unchanged": False,
            "native_calls": 0,
            "runner_process_calls": 0,
            "worker_calls": 0,
            "ffi_calls": 0,
            "execution_ready": False,
            "selection_rules": _fixed_selection_rules(),
            "protocol_vectors": {},
            "input_directories": {},
            "tool_identity": {"algorithm": "ground-collapse-preparation-tool-bundle-v1",
                              "workspace_identity": "0" * 64, "workspace_file_count": 0,
                              "workspace_identity_status": "historical_capture_metadata_not_reauthenticated"},
            "sources": None,
            "native_reachability_verified": False,
            "response_acceptance_verified": False,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "future_native_binding": dict(EMPTY_FUTURE_NATIVE_BINDING),
            "candidate": None,
            "input_sha256": {},
            "tool_bundle": {"archive_sha256": "0" * 64, "file_list_sha256": "0" * 64,
                            "source_identity": "0" * 64, "file_count": 11},
            "checks": [],
            "diagnostics": [{"checkpoint": "sources", "code": "core_source_file_missing", "role": "core/libduel.cpp"}],
            "accounting": {
                "certified_consumed": None,
                "policy_reserved": None,
                "planning_total": None,
                "old_confirmation_actual_consumed": None,
                "actual_all_history_cumulative": None,
            },
        }
        validate_report(report, schema=schema)
        report["execution_ready"] = True
        with self.assertRaises(ValueError):
            validate_report(report, schema=schema)

    def test_public_cli_exposes_fixed_ground_collapse_preparation_command(self):
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "ygo_eval.research", "prepare-ground-collapse-probe", "--help"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--core-source", result.stdout)
        self.assertIn("--verify-only", result.stdout)

    def test_tool_bundle_uses_shared_read_only_source_identity(self):
        repo = Path(__file__).resolve().parents[1]
        listing, list_raw, archive_raw = _check_tool_bundle(repo, PRODUCTION_PROFILE)
        self.assertEqual(listing["file_count"], len(PRODUCTION_PROFILE.tool_files))
        self.assertEqual(listing["kind"], "ground_collapse_preparation_tool_file_list")
        self.assertTrue(listing["workspace_identity"])
        self.assertTrue(list_raw)
        self.assertTrue(archive_raw)

    def test_report_base_reserves_source_summary_and_strict_failure_diagnostic(self):
        report = _report_base(PRODUCTION_PROFILE, _synthetic_tool_bundle(PRODUCTION_PROFILE), _Capture(),
                              {"identity": "a" * 64, "files": {}})
        self.assertIn("sources", report)
        self.assertEqual(report["future_native_binding"], {
            "worker_sha256": None,
            "native_request_sha256": None,
            "actual_prompt_ids": None,
            "new_scope": None,
            "new_budget": None,
        })
        report["diagnostics"] = [{"checkpoint": "historical_sources", "code": "source_unavailable",
                                  "role": "historical_sources"}]
        validate_report(report)

    def test_report_validator_rejects_future_native_binding_and_selection_rule_drift(self):
        report = _report_base(PRODUCTION_PROFILE, _synthetic_tool_bundle(PRODUCTION_PROFILE), _Capture(),
                              {"identity": "a" * 64, "files": {}})
        report["diagnostics"] = [{"checkpoint": "historical_sources", "code": "source_unavailable",
                                  "role": "historical_sources"}]
        validate_report(report)

        report["future_native_binding"]["worker_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "future_native_binding"):
            validate_report(report)

        report = _report_base(PRODUCTION_PROFILE, _synthetic_tool_bundle(PRODUCTION_PROFILE), _Capture(),
                              {"identity": "a" * 64, "files": {}})
        report["diagnostics"] = [{"checkpoint": "historical_sources", "code": "source_unavailable",
                                  "role": "historical_sources"}]
        report["selection_rules"]["opcode24"]["ordered_zones"].reverse()
        with self.assertRaisesRegex(ValueError, "selection_rules"):
            validate_report(report)

    def test_successful_report_zero_call_verify_reconstructs_tool_source_check(self):
        repo = Path(__file__).resolve().parents[1]
        profile = PRODUCTION_PROFILE
        listing, list_raw, archive_raw = _check_tool_bundle(repo, profile)
        bundle = {"file_count": listing["file_count"], "archive_sha256": hashlib.sha256(archive_raw).hexdigest(),
                  "file_list_sha256": hashlib.sha256(list_raw).hexdigest(),
                  "source_identity": listing["workspace_identity"]}
        report = _report_with_success_evidence(profile, bundle, _Capture(), _workspace_metadata(listing))
        schema = json.loads((repo / "schemas/ground-collapse-preparation-v1.schema.json").read_bytes())
        validate_report(report, schema=schema)
        original_vectors = report["protocol_vectors"]
        report["protocol_vectors"] = {}
        with self.assertRaisesRegex(PreparationError, "report_success_binding_invalid"):
            validate_report(report, schema=schema)
        report["protocol_vectors"] = original_vectors
        validate_report(report, schema=schema)
        scratch_root = repo / "target/ground-collapse-preparation-tests"
        output = scratch_root / f"saved-verify-{uuid.uuid4().hex}"
        output.mkdir()
        (output / "source-native-file-list.json").write_bytes(list_raw)
        (output / "source-native.zip").write_bytes(archive_raw)
        (output / "preparation.json").write_bytes(encode(report))

        recomputed = dict(report)
        recomputed["checks"] = report["checks"][:-1]
        recomputed_capture = _Capture()
        recomputed_capture.role_hashes = dict(report["input_sha256"])
        recomputed_capture.directories = {
            name: dict(item) for name, item in report["input_directories"].items()
        }
        with patch("ygo_eval.ground_collapse_preparation._run_sources",
                   return_value=(recomputed, recomputed_capture)):
            verification = _verify_only(
                type("Args", (), {})(), repo, output, profile,
                lambda _root: {"identity": listing["workspace_identity"], "files": listing["files"]},
            )
        self.assertTrue(verification["valid"])

    def test_successful_report_verify_allows_workspace_docs_to_change_without_tool_member_drift(self):
        repo = Path(__file__).resolve().parents[1]
        profile = PRODUCTION_PROFILE
        listing, list_raw, archive_raw = _check_tool_bundle(repo, profile)
        bundle = {"file_count": listing["file_count"], "archive_sha256": hashlib.sha256(archive_raw).hexdigest(),
                  "file_list_sha256": hashlib.sha256(list_raw).hexdigest(),
                  "source_identity": listing["workspace_identity"]}
        report = _report_with_success_evidence(profile, bundle, _Capture(), _workspace_metadata(listing))
        scratch_root = repo / "target/ground-collapse-preparation-tests"
        output = scratch_root / f"saved-doc-drift-{uuid.uuid4().hex}"
        output.mkdir(parents=True)
        (output / "source-native-file-list.json").write_bytes(list_raw)
        (output / "source-native.zip").write_bytes(archive_raw)
        (output / "preparation.json").write_bytes(encode(report))

        # This models documentation-only drift: the whole-workspace identity and
        # file-list sidecar change, while every pinned tool member stays identical.
        current_workspace = {
            "identity": "f" * 64,
            "files": dict(listing["files"]),
        }
        current_listing, current_list_raw, current_archive_raw = _check_tool_bundle(
            repo, profile, source_collector=lambda _root: current_workspace,
        )
        recomputed = copy.deepcopy(report)
        recomputed["checks"] = report["checks"][:-1]
        recomputed["tool_bundle"] = {
            "file_count": current_listing["file_count"],
            "archive_sha256": sha256(current_archive_raw),
            "file_list_sha256": sha256(current_list_raw),
            "source_identity": current_listing["workspace_identity"],
        }
        recomputed["tool_identity"] = _workspace_metadata(current_listing)
        recomputed_capture = _Capture()
        recomputed_capture.role_hashes = dict(report["input_sha256"])
        recomputed_capture.directories = {
            name: dict(item) for name, item in report["input_directories"].items()
        }
        with patch("ygo_eval.ground_collapse_preparation._run_sources",
                   return_value=(recomputed, recomputed_capture)):
            verification = _verify_only(
                type("Args", (), {})(), repo, output, profile,
                lambda _root: current_workspace,
            )
        self.assertTrue(verification["valid"])

    def test_failure_after_history_gate_remains_schema_valid_and_unsettled(self):
        repo = Path(__file__).resolve().parents[1]
        profile = PRODUCTION_PROFILE
        workspace = source_identity(repo)
        listing = {"file_count": len(profile.tool_files), "workspace_identity": workspace["identity"],
                   "workspace_file_count": len(workspace["files"])}
        failure = PreparationError("ground_collapse_candidate_missing", "prompt_prepared_cases")
        with (
            patch("ygo_eval.ground_collapse_preparation._check_tool_bundle_without_output",
                  return_value=(listing, b"synthetic list", b"synthetic archive")),
            patch("ygo_eval.ground_collapse_preparation._verify_curry_scope_delivery",
                  return_value={"delivery_sha256": "a" * 64}),
            patch("ygo_eval.native_curry_option_validation._verify_option_revalidation_baseline",
                  return_value=({"certified_historical_consumed": 40, "policy_reserved": 7,
                                "planning_base": 47}, {})),
            patch("ygo_eval.ground_collapse_preparation._verify_old_prompt_preparation",
                  side_effect=failure),
        ):
            report, _capture = _run_sources(
                repo, Namespace(core_source=repo / "unused"), profile,
                source_collector=lambda root: source_identity(root),
            )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["diagnostics"][0]["checkpoint"], "frozen_candidate")
        self.assertEqual(report["accounting"], {
            "certified_consumed": None, "policy_reserved": None, "planning_total": None,
            "old_confirmation_actual_consumed": None, "actual_all_history_cumulative": None,
        })
        validate_report(report)

    def test_pre_report_failure_saves_independent_publication_diagnostic(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch_root = workspace / "target/ground-collapse-preparation-tests"
        scratch = scratch_root / f"publication-failure-{uuid.uuid4().hex}"
        repo = scratch / "repo"
        repo.mkdir(parents=True)
        (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
        profile = replace(
            PRODUCTION_PROFILE,
            output_root=Path("data/runtime/p1-ground-collapse-fixture"),
            baseline_root=Path("data/runtime/synthetic-baseline"),
            preparation_cases_path=Path("data/runtime/synthetic-prepared.json"),
            frozen_cases_path=Path("data/runtime/synthetic-cases.json"),
            core_source_path=Path("data/runtime/synthetic-core"),
        )
        args = Namespace(
            output=repo / profile.output_root,
            baseline_dir=repo / profile.baseline_root,
            preparation=repo / profile.preparation_cases_path,
            cases=repo / profile.frozen_cases_path,
            core_source=repo / profile.core_source_path,
            verify_only=False,
        )
        with patch("ygo_eval.ground_collapse_preparation._check_tool_bundle",
                   side_effect=PreparationError("tool_source_unavailable", "tool_member")):
            with self.assertRaisesRegex(PreparationError, "tool_source_unavailable"):
                prepare_ground_collapse_probe(
                    args, repo=repo, profile=profile,
                    source_collector=lambda _root: {"identity": "a" * 64, "files": {}}
                )
        diagnostic_path = args.output / "publication-diagnostic.json"
        self.assertTrue(diagnostic_path.is_file())
        diagnostic = json.loads(diagnostic_path.read_bytes())
        self.assertEqual(diagnostic["kind"], "ground_collapse_preparation_publication_diagnostic_v1")
        self.assertEqual(diagnostic["checkpoint"], "tool_bundle_capture")
        self.assertEqual(diagnostic["code"], "tool_source_unavailable")
        self.assertEqual(diagnostic["native_calls"], 0)
        self.assertEqual(diagnostic["worker_calls"], 0)
        self.assertFalse(diagnostic["execution_ready"])

    def test_output_root_creation_failure_saves_sibling_diagnostic(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch_root = workspace / "target/ground-collapse-preparation-tests"
        scratch = scratch_root / f"output-root-failure-{uuid.uuid4().hex}"
        repo = scratch / "repo"
        repo.mkdir(parents=True)
        (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
        profile = replace(
            PRODUCTION_PROFILE,
            output_root=Path("data/runtime/p1-ground-collapse-fixture"),
            baseline_root=Path("data/runtime/synthetic-baseline"),
            preparation_cases_path=Path("data/runtime/synthetic-prepared.json"),
            frozen_cases_path=Path("data/runtime/synthetic-cases.json"),
            core_source_path=Path("data/runtime/synthetic-core"),
        )
        output = (repo / profile.output_root).resolve()
        output.parent.mkdir(parents=True)
        args = Namespace(
            output=output,
            baseline_dir=repo / profile.baseline_root,
            preparation=repo / profile.preparation_cases_path,
            cases=repo / profile.frozen_cases_path,
            core_source=repo / profile.core_source_path,
            verify_only=False,
        )
        original_mkdir = Path.mkdir

        def fail_only_output_root(path, *args, **kwargs):
            if path.resolve() == output:
                raise PermissionError("synthetic denied")
            return original_mkdir(path, *args, **kwargs)

        with patch("pathlib.Path.mkdir", new=fail_only_output_root):
            with self.assertRaisesRegex(PreparationError, "output_root_create_failed"):
                prepare_ground_collapse_probe(
                    args, repo=repo, profile=profile,
                    source_collector=lambda _root: {"identity": "a" * 64, "files": {}},
                )
        diagnostic_path = output.with_name(output.name + ".publication-diagnostic.json")
        diagnostic = json.loads(diagnostic_path.read_bytes())
        self.assertEqual(diagnostic["checkpoint"], "output_root_creation")
        self.assertEqual(diagnostic["code"], "output_root_create_failed")

    def test_verify_rejects_saved_bundle_that_does_not_match_fixed_tool_sources(self):
        repo = Path(__file__).resolve().parents[1]
        profile = PRODUCTION_PROFILE
        listing, list_raw, archive_raw = _check_tool_bundle(repo, profile)
        bundle = {"file_count": listing["file_count"], "archive_sha256": hashlib.sha256(archive_raw).hexdigest(),
                  "file_list_sha256": hashlib.sha256(list_raw).hexdigest(),
                  "source_identity": listing["workspace_identity"]}
        report = _report_with_success_evidence(profile, bundle, _Capture(), _workspace_metadata(listing))

        # Keep every saved bundle self-consistent while changing one fixed tool
        # member. A verifier must bind the archived member map back to the
        # current fixed source set, not merely validate the archive against itself.
        changed_member = profile.tool_files[-1]
        altered_bytes = b"synthetic altered tool member\n"
        altered_files = dict(listing["files"])
        altered_files[changed_member] = hashlib.sha256(altered_bytes).hexdigest()
        altered_listing = dict(listing, files=altered_files)
        altered_list_raw = encode(altered_listing)
        from io import BytesIO
        import zipfile
        with zipfile.ZipFile(BytesIO(archive_raw)) as original_archive:
            original_members = {name: original_archive.read(name) for name in profile.tool_files}
        archive_stream = BytesIO()
        with zipfile.ZipFile(archive_stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in profile.tool_files:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(name, altered_bytes if name == changed_member else original_members[name])
        altered_archive = archive_stream.getvalue()
        report["tool_bundle"] = {
            "file_count": len(profile.tool_files),
            "archive_sha256": hashlib.sha256(altered_archive).hexdigest(),
            "file_list_sha256": hashlib.sha256(altered_list_raw).hexdigest(),
            "source_identity": listing["workspace_identity"],
        }
        report["tool_identity"]["workspace_identity"] = listing["workspace_identity"]
        validate_report(report)

        output = repo / "target/ground-collapse-preparation-tests" / f"bundle-verify-{uuid.uuid4().hex}"
        output.mkdir(parents=True)
        (output / "source-native-file-list.json").write_bytes(altered_list_raw)
        (output / "source-native.zip").write_bytes(altered_archive)
        (output / "preparation.json").write_bytes(encode(report))
        with patch("ygo_eval.ground_collapse_preparation._run_sources",
                   return_value=(dict(report), _Capture())):
            with self.assertRaisesRegex(PreparationError, "saved_tool_bundle_fixed_source_mismatch"):
                _verify_only(
                    type("Args", (), {})(), repo, output, profile,
                    lambda _root: {"identity": listing["workspace_identity"], "files": listing["files"]},
                )

    def test_saved_tool_bundle_rejects_duplicate_zip_member_names(self):
        from io import BytesIO
        import zipfile

        repo = Path(__file__).resolve().parents[1]
        profile = PRODUCTION_PROFILE
        listing, list_raw, archive_raw = _check_tool_bundle(repo, profile)
        with zipfile.ZipFile(BytesIO(archive_raw)) as original:
            members = {name: original.read(name) for name in profile.tool_files}
        stream = BytesIO()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in profile.tool_files:
                    archive.writestr(name, members[name])
                archive.writestr(profile.tool_files[0], members[profile.tool_files[0]])
        duplicate_archive = stream.getvalue()
        output = repo / "target/ground-collapse-preparation-tests" / f"duplicate-bundle-{uuid.uuid4().hex}"
        output.mkdir(parents=True)
        (output / "source-native-file-list.json").write_bytes(list_raw)
        (output / "source-native.zip").write_bytes(duplicate_archive)
        report = _report_base(PRODUCTION_PROFILE, {
            "file_count": len(profile.tool_files),
            "archive_sha256": hashlib.sha256(duplicate_archive).hexdigest(),
            "file_list_sha256": hashlib.sha256(list_raw).hexdigest(),
            "source_identity": listing["workspace_identity"],
        }, _Capture(), _workspace_metadata(listing))
        with self.assertRaisesRegex(PreparationError, "saved_tool_bundle_duplicate_member"):
            _verify_saved_tool_bundle(output, report, profile)

    def test_synthetic_protocol_vectors_match_hand_written_ground_collapse_golden(self):
        vectors = _synthetic_protocol_vectors()
        expected = {
            "opcode24_raw": [24, 0, 2, 224, 255, 224, 255],
            "synthetic_disabled_mask": 0xFFE0FFE0,
            "canonical_pairs": 45,
            "ordered_encodings": 90,
            "response_bytes": [1, 4, 0, 1, 4, 1],
            "hint_zone": [2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            "field_disabled": [56, 0, 0, 3, 0],
            "selected_mask": 0x00030000,
        }
        self.assertEqual(vectors["synthetic_expected"], expected)
        self.assertEqual(vectors["opcode24"]["audit"]["available_zones"], 10)
        self.assertEqual(vectors["opcode24"]["audit"]["canonical_menu_pairs"], 45)
        self.assertEqual(vectors["opcode24"]["audit"]["selected_mask"], 0x00030000)
        self.assertFalse(vectors["native_observation"]["native_response_acceptance_verified"])


def _scratch_gate_root() -> Path:
    """All gate fixtures stay below the ignored synthetic-test target tree."""
    repo = Path(__file__).resolve().parents[1]
    root = repo / "target/ground-collapse-preparation-tests" / f"gates-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _gate_fixture(root: Path):
    """Construct one fully synthetic Rabbit source set and derived collapse candidate."""
    import copy

    from test_research import sample

    runtime = root / "runtime"
    runtime.mkdir()
    scripts = runtime / "scripts"
    (scripts / "official").mkdir(parents=True)
    core = root / "core"
    core.mkdir()
    banlist = root / "banlist.json"
    dll = runtime / "core.dll"
    engine_manifest = runtime / "engine-manifest.json"
    catalog = runtime / "cards.cdb"
    script_manifest = runtime / "script-manifest.json"

    base_case = sample()
    base_case["case_id"] = "rabbit"
    base_case["purpose"] = "proof_input"
    main = list(range(1, 41))
    main[0] = 85138716
    main[5] = 69247929
    main[6] = 69247929
    base_case["deck"] = {"main": main, "extra": [1001, 1002, 1003], "side": []}
    base_case["opening_hand"] = [85138716, 2, 3, 4, 5]
    base_case["information"]["opponent_resources"] = {"main": list(main), "hand": []}
    base_case["seed"] = 1

    dll.write_bytes(b"synthetic non-executable core identity")
    engine_manifest.write_bytes(b"synthetic engine manifest")
    banlist.write_bytes(encode({"region": "OCG", "version": base_case["rules"]["version"], "limits": {}}))
    target_script = scripts / "official/c90502999.lua"
    target_script.write_bytes(b"Duel.SelectDisableField(...)\nDuel.Hint(HINT_ZONE,tp,dis)\n")
    for name in ("utility.lua", "official/c57103969.lua", "official/c58074572.lua"):
        path = scripts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("-- synthetic " + name).encode("utf-8"))

    # A read-only SQLite catalog with synthetic OCG rows and a proper extra-deck type.
    with closing(sqlite3.connect(catalog)) as db:
        db.execute("CREATE TABLE datas (id INTEGER, alias INTEGER, type INTEGER, ot INTEGER)")
        all_codes = set(main + [1001, 1002, 1003, 90502999])
        db.executemany(
            "INSERT INTO datas VALUES (?,0,?,1)",
            [(code, 0x2000 if code in (1001, 1002, 1003) else 1) for code in sorted(all_codes)],
        )
        db.commit()

    script_hashes = {
        name: sha256((scripts / name).read_bytes())
        for name in ("utility.lua", "official/c57103969.lua", "official/c58074572.lua", "official/c90502999.lua")
    }
    script_manifest.write_bytes(encode(script_hashes))
    base_case["rules"]["banlist_sha256"] = sha256(banlist.read_bytes())
    base_case["assets"] = {
        "engine_sha256": sha256(dll.read_bytes()),
        "cdb_sha256": sha256(catalog.read_bytes()),
        "scripts_sha256": sha256(script_manifest.read_bytes()),
    }
    base_request = {
        "engine": {
            "worker_path": str(runtime / "worker-never-started.exe"),
            "ocgcore_path": str(dll),
            "catalog_path": str(catalog),
            "scripts_path": str(scripts),
            "script_manifest_path": str(script_manifest),
            "engine_manifest_path": str(engine_manifest),
            "timeout_ms": 30000,
        },
        "versions": {"rules": "ocg-mr5", **base_case["assets"]},
        "deck": copy.deepcopy(base_case["deck"]),
        "opening_hand": copy.deepcopy(base_case["opening_hand"]),
        "seed": 1,
        "decisions": [],
    }
    derived = derive_candidates(base_case)
    collapse = next(item for item in derived if item["case"]["case_id"] == "prompt-24-collapse-v1")
    # The frozen prepared-cases artifact adds preparation-stage assertions to
    # each pure derivation before saving it.
    for item in derived:
        item.update({
            "source_legality_validated": True,
            "status": "static_prepared",
            "formal_release_status": "unknown",
            "execution_ready": False,
        })
        item["request_derivation"].update(base_request_sha256=sha256(encode(base_request)))
    candidate_json = {"kind": "static_prompt_probe_candidates", "execution_ready": False,
                      "candidates": derived}
    source_cases = {"cases": [{"case": base_case, "request": base_request, "banlist_path": str(banlist)}]}
    acceptance = {
        "schema_version": 1,
        "kind": "prompt_probe_offline_delivery_acceptance",
        "paused": True,
        "new_native_calls": 0,
        "new_ffi_queries": 0,
        "cumulative_consumed": 24,
        "unknown": 0,
        "evidence": {},
    }
    prompt_root = root / "data/runtime/p1-prompt-probes-offline-2026-10-21"
    prompt_root.mkdir(parents=True)
    for index in range(37):
        rel = Path("evidence") / f"evidence-{index:02d}.bin"
        path = prompt_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = f"synthetic acceptance evidence {index}".encode()
        path.write_bytes(raw)
        acceptance["evidence"][rel.as_posix()] = {"bytes": len(raw), "sha256": sha256(raw)}

    acceptance_path = root / "acceptance.json"
    report_path = root / "preparation-report.json"
    prepared_path = root / "prepared-cases.json"
    frozen_path = root / "frozen-cases.json"
    acceptance_path.write_bytes(encode(acceptance))
    report_path.write_bytes(encode({"kind": "prompt_probe_preparation", "preparation_successful": True,
                                    "native_calls": 0, "execution_ready": False}))
    prepared_path.write_bytes(encode(candidate_json))
    frozen_path.write_bytes(encode(source_cases))

    profile = replace(
        PRODUCTION_PROFILE,
        acceptance_path=Path("acceptance.json"),
        preparation_report_path=Path("preparation-report.json"),
        preparation_cases_path=Path("prepared-cases.json"),
        frozen_cases_path=Path("frozen-cases.json"),
        acceptance_sha256=sha256(acceptance_path.read_bytes()),
        preparation_report_sha256=sha256(report_path.read_bytes()),
        preparation_cases_sha256=sha256(prepared_path.read_bytes()),
        frozen_cases_sha256=sha256(frozen_path.read_bytes()),
        collapse_case_sha256=sha256(encode(collapse["case"])),
    )
    candidate = _verify_old_prompt_preparation(_Capture(), root, profile)
    return root, profile, candidate, {
        "base_case": base_case,
        "base_request": base_request,
        "banlist": banlist,
        "catalog": catalog,
        "dll": dll,
        "engine_manifest": engine_manifest,
        "script_manifest": script_manifest,
        "scripts": scripts,
        "target_script": target_script,
        "core": core,
    }


class GroundCollapseFrozenCandidateGateTests(unittest.TestCase):
    def test_synthetic_frozen_candidate_gate_accepts_exact_40_3_0_seed_and_opponent_sync(self):
        root = _scratch_gate_root()
        try:
            _root, _profile, candidate, _paths = _gate_fixture(root)
            case = candidate["case"]
            self.assertEqual([len(case["deck"][key]) for key in ("main", "extra", "side")], [40, 3, 0])
            self.assertEqual(len(case["opening_hand"]), 5)
            self.assertEqual(case["seed"], 1)
            self.assertEqual(case["deck"]["main"].count(90502999), 1)
            self.assertEqual(case["opening_hand"].count(90502999), 1)
            self.assertEqual(case["information"]["opponent_resources"],
                             {"main": case["deck"]["main"], "hand": []})
            self.assertEqual(candidate["request"]["opening_hand"], case["opening_hand"])
            self.assertEqual(candidate["request"]["deck"], case["deck"])
        finally:
            shutil.rmtree(root)

    def test_frozen_candidate_gate_rejects_changed_prepared_deck_hand_or_opponent_declaration(self):
        mutations = (
            ("deck", lambda item: item["case"]["deck"]["main"].__setitem__(1, 90502999)),
            ("hand", lambda item: item["case"]["opening_hand"].__setitem__(1, 90502999)),
            ("opponent", lambda item: item["case"]["information"].__setitem__(
                "opponent_resources", {"main": [1] * 40, "hand": []})),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                root = _scratch_gate_root()
                try:
                    _root, profile, _candidate, _paths = _gate_fixture(root)
                    prepared_path = root / "prepared-cases.json"
                    prepared = strict_json(prepared_path.read_bytes())
                    item = next(entry for entry in prepared["candidates"]
                                if entry["case"]["case_id"] == "prompt-24-collapse-v1")
                    mutate(item)
                    prepared_path.write_bytes(encode(prepared))
                    changed = replace(profile,
                                      preparation_cases_sha256=sha256(prepared_path.read_bytes()),
                                      collapse_case_sha256=sha256(encode(item["case"])))
                    with self.assertRaisesRegex(PreparationError, "ground_collapse_candidate_binding_invalid"):
                        _verify_old_prompt_preparation(_Capture(), root, changed)
                finally:
                    shutil.rmtree(root)

    def test_frozen_base_seed_and_hand_mutations_fail_before_candidate_acceptance(self):
        for name, mutate in (
            ("seed", lambda case: case.__setitem__("seed", 2)),
            ("hand_not_in_deck", lambda case: case["opening_hand"].__setitem__(1, 999999)),
        ):
            with self.subTest(name=name):
                root = _scratch_gate_root()
                try:
                    _root, profile, _candidate, _paths = _gate_fixture(root)
                    frozen_path = root / "frozen-cases.json"
                    frozen = strict_json(frozen_path.read_bytes())
                    mutate(frozen["cases"][0]["case"])
                    frozen_path.write_bytes(encode(frozen))
                    changed = replace(profile, frozen_cases_sha256=sha256(frozen_path.read_bytes()))
                    with self.assertRaises((ValueError, PreparationError)):
                        _verify_old_prompt_preparation(_Capture(), root, changed)
                finally:
                    shutil.rmtree(root)


def _runtime_gate_fixture(root: Path):
    _root, _profile, candidate, paths = _gate_fixture(root)
    from ygo_eval.ground_collapse_preparation import _verify_runtime_and_core

    # Use fixture-owned pins, independently derived from synthetic bytes.
    target_bytes = b"Duel.SelectDisableField(...)\nDuel.Hint(HINT_ZONE,tp,dis)\n"
    target_hash = sha256(target_bytes)
    script_pins = {}
    for name in ("utility.lua", "official/c57103969.lua", "official/c58074572.lua"):
        script_pins[name] = sha256((paths["scripts"] / name).read_bytes())
    script_pins["official/c90502999.lua"] = target_hash
    profile = replace(
        _profile,
        target_script_pins=(("official/c90502999.lua", target_hash),),
        script_manifest_pins=tuple(script_pins.items()),
        core_pins=tuple((name, sha256(content)) for name, content in {
            "libduel.cpp": b"synthetic SelectDisableField implementation",
            "processor.cpp": b"synthetic MSG_FIELD_DISABLED implementation",
            "ocgapi_constants.h": b"HINT_ZONE MSG_SELECT_PLACE",
            "effect_constants.h": b"synthetic effect constants",
            "playerop.cpp": b"synthetic player operations",
            "field.cpp": b"synthetic field implementation",
        }.items()),
    )
    core_content = {
        "libduel.cpp": b"synthetic SelectDisableField implementation",
        "processor.cpp": b"synthetic MSG_FIELD_DISABLED implementation",
        "ocgapi_constants.h": b"HINT_ZONE MSG_SELECT_PLACE",
        "effect_constants.h": b"synthetic effect constants",
        "playerop.cpp": b"synthetic player operations",
        "field.cpp": b"synthetic field implementation",
    }
    for name, raw in core_content.items():
        (paths["core"] / name).write_bytes(raw)
    request = candidate["request"]
    return _Capture(), candidate, paths["core"], profile, paths


def _complete_success_report(profile=PRODUCTION_PROFILE):
    """Build a successful synthetic report for standalone validator tests."""
    workspace = {"identity": "a" * 64, "files": {"synthetic.py": "b" * 64}}
    report = _report_base(
        profile,
        {
            "file_count": len(profile.tool_files),
            "archive_sha256": "c" * 64,
            "file_list_sha256": "d" * 64,
            "source_identity": workspace["identity"],
        },
        _Capture(),
        workspace,
    )
    report.update({
        "status": "passed",
        "preparation_successful": True,
        "source_unchanged": True,
        "candidate": {
            "case_id": "prompt-24-collapse-v1",
            "card_id": 90502999,
            "case_sha256": "e" * 64,
            "base_request_sha256": "f" * 64,
            "main_extra_side_counts": [40, 3, 0],
            "opening_hand_count": 5,
            "seed": 1,
            "opponent_resources_synced": True,
            "formal_release_status": "unknown",
            "source_legality_validated": True,
            "catalog": {
                "card_id": 90502999,
                "alias": 0,
                "type": 1,
                "ot": 1,
                "banlist_and_alias_limits_validated": True,
                "formal_release_status": "unknown",
            },
        },
        "protocol_vectors": _synthetic_protocol_vectors(),
        "sources": {
            "latest_curry": {
                "delivery_sha256": profile.curry_delivery_sha256,
                "native_source": {
                    "file_count": 593,
                    "source_identity": profile.native_identity,
                    "archive_sha256": profile.native_archive_sha256,
                    "file_list_sha256": profile.native_file_list_sha256,
                },
                "final_source": {
                    "file_count": 594,
                    "source_identity": profile.final_identity,
                    "archive_sha256": profile.final_archive_sha256,
                    "file_list_sha256": profile.final_file_list_sha256,
                },
                "ledger_records": 37,
                "scope_consumed": 7,
                "scope_unknown": 0,
                "certified_consumed": profile.prior_certified_consumed,
                "policy_reserved": profile.policy_reserved,
                "planning_total": profile.planning_total,
            },
            "historical_certified_consumed": profile.prior_certified_consumed,
            "historical_policy_reserved": profile.policy_reserved,
            "historical_planning_base": profile.planning_total,
            "historical_protection": {"entry_count": 1, "mapping_sha256": "1" * 64},
            "script": {
                "sha256": dict(profile.target_script_pins)["official/c90502999.lua"],
                "static_api": ["Duel.SelectDisableField", "Duel.Hint(HINT_ZONE,tp,dis)"],
            },
            "core": {
                "files": dict(profile.core_pins),
                "semantics": {
                    "SelectDisableField": True,
                    "MSG_FIELD_DISABLED": True,
                    "HINT_ZONE": True,
                    "MSG_SELECT_PLACE": True,
                },
            },
        },
        "checks": [
            {"checkpoint": checkpoint, "status": "passed", "code": None, "role": role}
            for checkpoint, role in (
                ("latest_curry_delivery", "latest_curry_delivery"),
                ("historical_sources", "historical_sources"),
                ("frozen_candidate", "prompt_prepared_cases"),
                ("runtime_assets_and_core", "core/source"),
                ("input_stability", "all_inputs"),
                ("tool_source_stability", "tool_source"),
            )
        ],
        "input_sha256": {
            role: "2" * 64
            for role in (
                "latest_curry_delivery", "latest_curry_summary", "latest_curry_ledger",
                "curry_native_source_file_list", "curry_native_source_archive",
                "curry_final_source_file_list", "curry_final_source_archive",
                "curry_native_build", "curry_final_cli_worker_build", "curry_final_runner_build",
                "curry_artifact_runner", "curry_artifact_cli", "curry_artifact_worker",
                "prompt_preparation_acceptance", "prompt_preparation_report", "prompt_prepared_cases",
                "frozen_rabbit_cases", "runtime_dll", "runtime_cdb", "runtime_script_manifest",
                "runtime_engine_manifest", "runtime_banlist", "runtime_script_manifest_reparsed",
                "ground_collapse_script", "core/libduel.cpp", "core/processor.cpp",
                "core/ocgapi_constants.h", "core/effect_constants.h", "core/playerop.cpp",
                "core/field.cpp",
                *(f"latest_curry_stage_{stage}_receipt" for stage in range(1, 8)),
                *(f"latest_curry_stage_{suffix}_{stage}" for stage in range(1, 8)
                  for suffix in ("report", "request", "input", "seal")),
                *(f"latest_curry_result_blob_{stage}" for stage in range(1, 8)),
                *(f"latest_curry_checkpoint_blob_{index}" for index in range(22)),
            )
        },
        "input_directories": {
            name: {"sha256": "3" * 64, "entry_count": 0}
            for name in (
                "latest_curry_delivery_tree", "latest_curry_ledger_blobs_tree",
                "prompt_preparation_tree", "runtime_scripts_tree", "frozen_core_tree",
            )
        },
        "accounting": {
            "certified_consumed": profile.prior_certified_consumed,
            "policy_reserved": profile.policy_reserved,
            "planning_total": profile.planning_total,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        },
    })
    return report


def _report_with_success_evidence(profile, bundle, capture, workspace):
    """Bind complete synthetic success evidence to a caller-owned bundle."""
    report = _report_base(profile, bundle, capture, workspace)
    complete = _complete_success_report(profile)
    for key, value in complete.items():
        if key not in {"tool_bundle", "tool_identity"}:
            report[key] = copy.deepcopy(value)
    return report


class GroundCollapseSuccessEvidenceValidationTests(unittest.TestCase):
    def test_success_report_rejects_missing_source_input_or_checkpoint_evidence_without_schema(self):
        import copy

        complete = _complete_success_report()
        validate_report(complete, schema=None)

        mutations = (
            ("sources", lambda report: report.__setitem__("sources", None), "report_success_sources_invalid"),
            ("input_role", lambda report: report["input_sha256"].pop("runtime_cdb"), "report_success_inputs_invalid"),
            ("checkpoint_role", lambda report: report["input_sha256"].pop("latest_curry_checkpoint_blob_0"),
             "report_checkpoint_input_roles_invalid"),
            ("input_directories", lambda report: report.__setitem__("input_directories", {}),
             "report_success_directories_invalid"),
            ("checks", lambda report: report.__setitem__("checks", []), "report_success_checks_invalid"),
        )
        for name, mutate, expected_code in mutations:
            with self.subTest(name=name):
                report = copy.deepcopy(complete)
                mutate(report)
                with self.assertRaisesRegex(PreparationError, expected_code):
                    validate_report(report, schema=None)

    def test_success_report_rejects_bool_as_integer_without_schema(self):
        import copy

        mutations = (
            ("seed", lambda report: report["candidate"].__setitem__("seed", True),
             "report_success_binding_invalid"),
            ("count_item", lambda report: report["candidate"].__setitem__(
                "main_extra_side_counts", [40, 3, False]), "report_success_binding_invalid"),
            ("accounting", lambda report: report["accounting"].__setitem__(
                "certified_consumed", True), "report_success_binding_invalid"),
            ("scope_unknown", lambda report: report["sources"]["latest_curry"].__setitem__(
                "scope_unknown", False), "report_latest_curry_source_invalid"),
        )
        for name, mutate, expected in mutations:
            with self.subTest(name=name):
                report = copy.deepcopy(_complete_success_report())
                mutate(report)
                with self.assertRaisesRegex(PreparationError, expected):
                    validate_report(report, schema=None)

    def test_success_report_rejects_empty_historical_protection_without_schema(self):
        import copy

        report = copy.deepcopy(_complete_success_report())
        report["sources"]["historical_protection"]["entry_count"] = 0
        with self.assertRaisesRegex(PreparationError, "report_historical_protection_invalid"):
            validate_report(report, schema=None)

    def test_success_report_schema_rejects_empty_historical_protection(self):
        import copy

        report = copy.deepcopy(_complete_success_report())
        report["sources"]["historical_protection"]["entry_count"] = 0
        schema_path = Path(__file__).resolve().parents[1] / "schemas/ground-collapse-preparation-v1.schema.json"
        schema = json.loads(schema_path.read_bytes())
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(report)


class GroundCollapseCaptureTests(unittest.TestCase):
    def test_directory_capture_returns_the_snapshot_consumed_by_delivery_validation(self):
        root = _scratch_gate_root()
        try:
            source_tree = root / "source"
            source_tree.mkdir()
            (source_tree / "artifact.bin").write_bytes(b"synthetic inert artifact")
            capture = _Capture()
            result = capture.directory("delivery", source_tree)
            self.assertIsNotNone(result)
            self.assertEqual(result, capture.directories["delivery"])
            self.assertEqual(result["entry_count"], 1)
        finally:
            shutil.rmtree(root)

    def test_saved_bundle_rejects_tampered_report_file_count_against_valid_listing(self):
        import io
        import zipfile

        root = _scratch_gate_root()
        try:
            profile = replace(PRODUCTION_PROFILE, tool_files=("synthetic/tool-a.py", "synthetic/tool-b.py"))
            output = root / "saved"
            output.mkdir()
            members = {
                "synthetic/tool-a.py": b"synthetic tool a\n",
                "synthetic/tool-b.py": b"synthetic tool b\n",
            }
            files = {name: sha256(raw) for name, raw in members.items()}
            listing = {
                "schema_version": 1,
                "kind": "ground_collapse_preparation_tool_file_list",
                "files": files,
                "file_count": len(profile.tool_files),
                "workspace_identity": "a" * 64,
                "workspace_file_count": 1,
            }
            list_raw = encode(listing)
            archive_stream = io.BytesIO()
            with zipfile.ZipFile(archive_stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in members.items():
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, raw)
            archive_raw = archive_stream.getvalue()
            (output / "source-native-file-list.json").write_bytes(list_raw)
            (output / "source-native.zip").write_bytes(archive_raw)

            bundle = {
                "file_count": len(profile.tool_files),
                "archive_sha256": sha256(archive_raw),
                "file_list_sha256": sha256(list_raw),
                "source_identity": listing["workspace_identity"],
            }
            report = _report_base(
                profile, bundle, _Capture(),
                {"identity": listing["workspace_identity"], "files": {"synthetic.py": "b" * 64}},
            )
            self.assertEqual(_verify_saved_tool_bundle(output, report, profile), listing)

            report["tool_bundle"]["file_count"] += 1
            with self.assertRaisesRegex(PreparationError, "saved_tool_bundle_binding_invalid"):
                _verify_saved_tool_bundle(output, report, profile)
        finally:
            shutil.rmtree(root)


class GroundCollapseRuntimeAndCoreGateTests(unittest.TestCase):
    def test_synthetic_runtime_core_gate_accepts_independent_cdb_script_and_core_pins(self):
        from ygo_eval.ground_collapse_preparation import _verify_runtime_and_core

        root = _scratch_gate_root()
        try:
            capture, candidate, core, profile, _paths = _runtime_gate_fixture(root)
            result = _verify_runtime_and_core(capture, candidate, core, profile)
            self.assertEqual(result["candidate_catalog"]["card_id"], 90502999)
            self.assertEqual(result["candidate_catalog"]["ot"], 1)
            self.assertEqual(result["core_semantics"], {
                "SelectDisableField": True, "MSG_FIELD_DISABLED": True,
                "HINT_ZONE": True, "MSG_SELECT_PLACE": True,
            })
            self.assertEqual(result["script_static_api"], ["Duel.SelectDisableField", "Duel.Hint(HINT_ZONE,tp,dis)"])
        finally:
            shutil.rmtree(root)

    def test_runtime_gate_rejects_cdb_and_frozen_core_content_drift(self):
        for role in ("runtime_cdb", "core/libduel.cpp"):
            with self.subTest(role=role):
                root = _scratch_gate_root()
                try:
                    capture, candidate, core, profile, paths = _runtime_gate_fixture(root)
                    if role == "runtime_cdb":
                        paths["catalog"].write_bytes(paths["catalog"].read_bytes() + b"\0")
                        with self.assertRaisesRegex(ValueError, "catalog_path changed"):
                            _verify_runtime_and_core(capture, candidate, core, profile)
                    else:
                        path = core / "libduel.cpp"
                        path.write_bytes(b"changed SelectDisableField bytes")
                        with self.assertRaisesRegex(PreparationError, "source_hash_mismatch"):
                            _verify_runtime_and_core(capture, candidate, core, profile)
                finally:
                    shutil.rmtree(root)

    def test_runtime_gate_rejects_manifest_pin_drift_after_runtime_binding_is_updated(self):
        root = _scratch_gate_root()
        try:
            capture, candidate, core, profile, paths = _runtime_gate_fixture(root)
            manifest = strict_json(paths["script_manifest"].read_bytes())
            manifest["official/c90502999.lua"] = "f" * 64
            paths["script_manifest"].write_bytes(encode(manifest))
            candidate["case"]["assets"]["scripts_sha256"] = sha256(paths["script_manifest"].read_bytes())
            candidate["request"]["versions"]["scripts_sha256"] = candidate["case"]["assets"]["scripts_sha256"]
            with self.assertRaisesRegex(PreparationError, "script_manifest_pin_mismatch"):
                _verify_runtime_and_core(capture, candidate, core, profile)
        finally:
            shutil.rmtree(root)

    def test_runtime_gate_rejects_candidate_deck_seed_hand_and_opponent_resource_mismatch(self):
        mutations = (
            ("deck", lambda case, request: case["deck"]["main"].pop()),
            ("hand", lambda case, request: case["opening_hand"].__setitem__(1, 999999)),
            ("opponent", lambda case, request: case["information"].__setitem__(
                "opponent_resources", {"main": [999999] * 40, "hand": []})),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                root = _scratch_gate_root()
                try:
                    capture, candidate, core, profile, _paths = _runtime_gate_fixture(root)
                    mutate(candidate["case"], candidate["request"])
                    candidate["request"]["deck"] = candidate["case"]["deck"]
                    candidate["request"]["opening_hand"] = candidate["case"]["opening_hand"]
                    candidate["request"]["seed"] = candidate["case"]["seed"]
                    with self.assertRaises((ValueError, PreparationError)):
                        _verify_runtime_and_core(capture, candidate, core, profile)
                finally:
                    shutil.rmtree(root)

    def test_runtime_gate_rejects_script_bytes_without_frozen_api_source(self):
        root = _scratch_gate_root()
        try:
            capture, candidate, core, profile, paths = _runtime_gate_fixture(root)
            replacement = b"synthetic script with no disable-field or zone hint API"
            paths["target_script"].write_bytes(replacement)
            digest = sha256(replacement)
            manifest = strict_json(paths["script_manifest"].read_bytes())
            manifest["official/c90502999.lua"] = digest
            paths["script_manifest"].write_bytes(encode(manifest))
            candidate["case"]["assets"]["scripts_sha256"] = sha256(paths["script_manifest"].read_bytes())
            candidate["request"]["versions"]["scripts_sha256"] = candidate["case"]["assets"]["scripts_sha256"]
            profile = replace(
                profile,
                target_script_pins=(("official/c90502999.lua", digest),),
                script_manifest_pins=tuple(manifest.items()),
            )
            with self.assertRaisesRegex(PreparationError, "ground_collapse_script_semantics_mismatch"):
                _verify_runtime_and_core(capture, candidate, core, profile)
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
