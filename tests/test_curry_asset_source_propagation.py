"""Focused tests for source-description propagation into the Curry audit tree."""
from __future__ import annotations

import copy
from pathlib import Path
import uuid
import unittest
from unittest.mock import patch

from ygo_eval import curry_asset_binding_audit as audit


class _Sources:
    def __init__(
        self,
        role: str,
        *,
        children=(),
        counts=None,
        baseline_relative=None,
        files=None,
        archives=None,
        differences=None,
    ):
        self.role = role
        self._children = {child.role: child for child in children}
        self._counts = counts or {}
        self.baseline_relative = baseline_relative
        self._files = files or {}
        self._archives = archives or {}
        self._differences = differences or {}

    def child(self, role: str):
        return self._children[role]

    def dataset_count(self, name: str) -> int:
        matches = []
        if name in self._counts:
            matches.append(self._counts[name])
        for child in self._children.values():
            try:
                matches.append(child.dataset_count(name))
            except KeyError:
                pass
        if not matches or len(set(matches)) != 1:
            raise KeyError(name)
        return matches[0]

    def file_sha256(self, relative_path: str) -> str:
        matches = []
        if relative_path in self._files:
            matches.append(self._files[relative_path])
        for child in self._children.values():
            try:
                matches.append(child.file_sha256(relative_path))
            except KeyError:
                pass
        if not matches or len(set(matches)) != 1:
            raise KeyError(relative_path)
        return matches[0]

    def archive(self, role: str):
        matches = [self._archives[role]] if role in self._archives else []
        for child in self._children.values():
            try:
                matches.append(child.archive(role))
            except KeyError:
                pass
        if len(matches) != 1:
            raise KeyError(role)
        return matches[0]

    def differences(self, name: str):
        matches = [self._differences[name]] if name in self._differences else []
        for child in self._children.values():
            try:
                matches.append(child.differences(name))
            except KeyError:
                pass
        if len(matches) != 1:
            raise KeyError(name)
        return matches[0]


class CurryAssetSourcePropagationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(audit.__file__).resolve().parents[2]
        cls.scratch_root = cls.repo_root / "target/curry-asset-source-propagation-tests"
        cls.scratch_root.mkdir(parents=True, exist_ok=True)

    def test_historical_chain_passes_nested_curry_description_to_native_verifier(self):
        ledger_sources = _Sources(
            "historical_ledgers",
            counts={
                "previous_consumed": 26,
                "previous_unknown": 0,
                "previous_ledger_count": 7,
                "confirmation_consumed": 0,
                "confirmation_unknown": 0,
                "current_consumed": 6,
                "current_unknown": 0,
                "historical_consumed": 32,
                "historical_unknown": 0,
                "historical_ledgers": 9,
            },
        )
        native_curry_sources = _Sources(
            "curry_baseline",
            children=(_Sources("validation_baseline", children=(
                _Sources("runner_confirmation", children=(
                    _Sources("placement_confirmation", children=(ledger_sources,)),
                )),
            )),),
            baseline_relative="data/runtime/p1-tenki-placement-validation-native-2026-10-23",
        )
        historical_sources = _Sources("historical_chain", children=(native_curry_sources,))
        asset_sources = _Sources("asset_audit", children=(historical_sources,))

        expected_audit = {
            "prior": {
                "delivery": {"historical_consumed": 26, "historical_unknown": 0},
                "prior": {
                    "historical_ledgers": 7,
                    "current_ledger": {"consumed": 0, "unknown": 0},
                    "historical_audit_sha256": "a" * 64,
                },
            },
            "delivery": {"ledger": {"stats": {"consumed": 6, "unknown": 0}}},
        }
        seen = {}

        def verify_curry(repo, baseline, spec=None, *, _sources=None):
            seen.update(repo=repo, baseline=baseline, spec=spec, sources=_sources)
            return expected_audit, {Path(repo) / "protected.bin": "b" * 64}

        repo = Path("synthetic-repo")
        with patch(
            "ygo_eval.native_curry_option_validation._verify_curry_baseline",
            side_effect=verify_curry,
        ):
            summary, protected = audit._verify_historical_chain(repo, _sources=asset_sources)

        self.assertIs(seen["sources"], native_curry_sources)
        self.assertEqual(seen["baseline"], repo / native_curry_sources.baseline_relative)
        self.assertEqual(summary["consumed"], ledger_sources.dataset_count("historical_consumed"))
        self.assertEqual(summary["unknown"], ledger_sources.dataset_count("historical_unknown"))
        self.assertEqual(summary["ledger_count"], ledger_sources.dataset_count("historical_ledgers"))
        self.assertIn(repo / "protected.bin", protected)

    def test_report_validation_uses_injected_anchor_archive_and_count_pins(self):
        from types import SimpleNamespace

        prefix = "data/runtime/p1-curry-option-validation-native-2026-10-23"
        anchor_paths = {
            "native_build_record": f"{prefix}/build-record.json",
            "final_build_record": f"{prefix}/final-build/build-record.json",
            "manifest": f"{prefix}/research/manifest.json",
            "prepared": f"{prefix}/research/prepared.json",
            "summary": f"{prefix}/research/summary.json",
        }
        anchors = {
            role: chr(ord("a") + index) * 64
            for index, role in enumerate(anchor_paths)
        }
        scope_sources = _Sources(
            "asset_audit_scope",
            baseline_relative=prefix,
            files={anchor_paths[role]: value for role, value in anchors.items()},
            archives={
                "curry_native_archive": SimpleNamespace(
                    role="curry_native_archive", archive_sha256="f" * 64,
                    file_list_sha256="e" * 64, source_identity="d" * 64,
                    file_count=494, head="head",
                ),
                "curry_final_archive": SimpleNamespace(
                    role="curry_final_archive", archive_sha256="c" * 64,
                    file_list_sha256="b" * 64, source_identity="a" * 64,
                    file_count=495, head="head",
                ),
            },
            differences={"curry_baseline": ("docs/TESTING.md",)},
        )
        audit_archive = SimpleNamespace(
            role="asset_audit_native_archive", source_identity="9" * 64,
        )
        history_sources = _Sources(
            "historical_chain",
            counts={
                "historical_consumed": 32,
                "historical_unknown": 0,
                "historical_ledgers": 9,
            },
        )
        sources = _Sources(
            "asset_audit",
            children=(scope_sources, history_sources),
            counts={"asset_audit_source_files": 498},
            archives={"asset_audit_native_archive": audit_archive},
        )

        report = audit._new_report()
        report["anchors"] = anchors
        report["source"].update({
            "workspace_identity": audit_archive.source_identity,
            "workspace_file_count": 498,
            "historical_consumed": 32,
            "historical_unknown": 0,
            "ledger_count": 9,
            "source_archive_differences": ["docs/TESTING.md"],
        })
        report["source_archives"] = [
            {
                "role": role,
                "sha256": pin.archive_sha256,
                "file_list_sha256": pin.file_list_sha256,
                "source_identity": pin.source_identity,
                "file_count": pin.file_count,
                "bytes": 0,
            }
            for role, pin in (
                ("native_time", scope_sources.archive("curry_native_archive")),
                ("final", scope_sources.archive("curry_final_archive")),
            )
        ]
        report["history"] = {
            "consumed": 32,
            "unknown": 0,
            "ledger_count": 9,
            "verified_without_writable_journal": True,
            "input_set_sha256": "8" * 64,
        }

        self.assertTrue(audit.validate_report(report, _sources=sources))

        forged = dict(report)
        forged["anchors"] = dict(anchors, manifest="0" * 64)
        with self.assertRaises(ValueError):
            audit.validate_report(forged, _sources=sources)

        forged = copy.deepcopy(report)
        forged["source_archives"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "audit_source_archive_pins_mismatch"):
            audit.validate_report(forged, _sources=sources)

        forged = copy.deepcopy(report)
        forged["history"]["consumed"] += 1
        with self.assertRaisesRegex(ValueError, "historical_totals_claim_invalid"):
            audit.validate_report(forged, _sources=sources)

    def test_run_audit_propagates_source_description_to_recursive_verifiers(self):
        from types import SimpleNamespace

        prefix = "data/runtime/p1-curry-option-validation-native-2026-10-23"
        anchor_paths = {
            "native_build_record": f"{prefix}/build-record.json",
            "final_build_record": f"{prefix}/final-build/build-record.json",
            "manifest": f"{prefix}/research/manifest.json",
            "prepared": f"{prefix}/research/prepared.json",
            "summary": f"{prefix}/research/summary.json",
        }
        scope_sources = _Sources(
            "asset_audit_scope",
            baseline_relative=prefix,
            files={path: "a" * 64 for path in anchor_paths.values()},
            archives={
                "curry_native_archive": SimpleNamespace(
                    archive_sha256="b" * 64, file_list_sha256="c" * 64,
                    source_identity="d" * 64, file_count=494, head="head",
                ),
                "curry_final_archive": SimpleNamespace(
                    archive_sha256="e" * 64, file_list_sha256="f" * 64,
                    source_identity="1" * 64, file_count=495, head="head",
                ),
            },
            differences={"curry_baseline": ()},
        )
        history_sources = _Sources("historical_chain", counts={
            "historical_consumed": 32,
            "historical_unknown": 0,
            "historical_ledgers": 9,
        })
        workspace_identity = "9" * 64
        sources = _Sources(
            "asset_audit",
            children=(scope_sources, history_sources),
            counts={
                "asset_audit_source_files": 0,
                "asset_audit_inputs": 0,
                "historical_material_inputs": 0,
                "historical_consumed": 32,
                "historical_unknown": 0,
                "historical_ledgers": 9,
            },
            archives={"asset_audit_native_archive": SimpleNamespace(source_identity=workspace_identity)},
        )
        baseline_result = {
            "input_records": [],
            "protected": {},
            "source_archives": [],
            "old_builds": [],
            "source_archive_differences": [],
            "old_scope": None,
            "static_root_cause": None,
            "protected_summary": None,
        }
        history = {
            "consumed": 32,
            "unknown": 0,
            "ledger_count": 9,
            "verified_without_writable_journal": True,
            "input_set_sha256": "8" * 64,
        }
        repo = self.repo_root
        fixture = self.scratch_root / f"fixture-{uuid.uuid4().hex}"
        fixture.mkdir()
        baseline = fixture / "baseline"
        baseline.mkdir()
        output_root = fixture / "output"
        output_root.mkdir()
        output_path = output_root / "audit-report.json"
        with (
            patch.object(audit, "stable_source", return_value={"identity": workspace_identity, "files": {}}),
            patch.object(audit, "_snapshot_tree", return_value={}),
            patch.object(audit, "_verify_curry_scope", return_value=baseline_result) as verify_scope,
            patch.object(audit, "_verify_historical_chain", return_value=(history, {})) as verify_history,
            patch.object(audit, "_verify_new_runner", side_effect=ValueError("audit_runner_build_binding_mismatch")),
        ):
            report = audit._run_audit(
                repo=repo,
                baseline_dir=baseline,
                runner=output_root / "runner.exe",
                build_record=output_root / "build-record.json",
                output_root=output_root,
                output_path=output_path,
                _sources=sources,
            )

        verify_scope.assert_called_once_with(repo, baseline, _sources=sources)
        verify_history.assert_called_once_with(repo, _sources=sources)
        self.assertEqual(report["source"]["historical_consumed"], 32)
        self.assertEqual(report["source"]["workspace_identity"], workspace_identity)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(output_path.is_file())

    def test_source_description_cannot_redirect_curry_scope(self):
        repo = self.scratch_root / f"fixed-scope-{uuid.uuid4().hex}"
        wrong_relative = Path("data/runtime/synthetic-alternate-curry-scope")
        wrong_baseline = repo / wrong_relative
        wrong_baseline.mkdir(parents=True)
        sources = _Sources(
            "asset_audit_scope",
            baseline_relative=wrong_relative.as_posix(),
        )

        with patch.object(
            audit, "safe_path", side_effect=ValueError("scope_validation_proceeded"),
        ) as safe_path:
            with self.assertRaisesRegex(ValueError, "fixed_curry_baseline_required"):
                audit._verify_curry_scope(repo, wrong_baseline, _sources=sources)
        safe_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
