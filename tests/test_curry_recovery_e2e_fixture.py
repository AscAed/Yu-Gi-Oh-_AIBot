"""Structural checks for the test-owned public audit source tree."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
import uuid

from tests.support.curry_recovery_e2e import build_synthetic_recovery_tree
from tests.support.curry_recovery_e2e import _canonical, _sha


def _child(description, role):
    return next(item for item in description.children if item.role == role)


class CurryRecoverySyntheticFixtureTests(unittest.TestCase):
    def test_test_owned_canonical_hash_matches_handwritten_golden_bytes(self):
        # Keep one deliberately handwritten codec/hash vector so a shared
        # change to the fixture encoder and production verifier cannot make
        # every generated expectation move together unnoticed.
        expected_bytes = b'{"a":1,"z":"golden"}'
        expected_sha256 = "d8bb8b8dcdd3117a89ca45f29fd4b9cc465d4f5e463fd5fdf48666d8d054ded8"
        self.assertEqual(_canonical({"z": "golden", "a": 1}), expected_bytes)
        self.assertEqual(_sha(expected_bytes), expected_sha256)

    def test_prompt_baseline_fixture_contains_pinned_recovery_material(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_recovery_tree(scratch)
        asset_audit = _child(fixture.sources, "asset_audit")
        history = _child(asset_audit, "historical_chain")
        curry_baseline = _child(history, "curry_baseline")
        validation = _child(curry_baseline, "validation_baseline")
        runner = _child(validation, "runner_confirmation")
        placement = _child(runner, "placement_confirmation")
        baseline = _child(placement, "baseline")

        self.assertEqual(baseline.baseline_relative,
                         "data/runtime/p1-tenki-probe-native-2026-10-21")
        self.assertEqual(baseline.dataset_count("protected_file_count"), 366)
        self.assertEqual(baseline.dataset_count("pause_evidence_count"), 61)
        self.assertEqual(baseline.dataset_count("recovery_evidence_count"), 16)
        archive = baseline.archive("baseline_archive")
        self.assertEqual(archive.file_count, 390)
        self.assertTrue((fixture.repo / archive.archive_path).is_file())
        self.assertTrue((fixture.repo / archive.file_list_path).is_file())

    def test_outer_validation_delivery_is_a_complete_synthetic_child_source(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        scratch.mkdir(parents=True, exist_ok=False)
        fixture = build_synthetic_recovery_tree(scratch)
        asset_audit = _child(fixture.sources, "asset_audit")
        history = _child(asset_audit, "historical_chain")
        curry_baseline = _child(history, "curry_baseline")
        validation = _child(curry_baseline, "validation_baseline")

        # This must exist as inert generated evidence before the real recursive
        # validator enters the outer six-stage Curry history node.
        outer = curry_baseline
        root = fixture.repo / outer.baseline_relative
        self.assertEqual(
            outer.baseline_relative,
            "data/runtime/p1-tenki-placement-validation-native-2026-10-23",
        )
        self.assertTrue((root / "acceptance.json").is_file())
        self.assertTrue((root / "final-build/delivery.json").is_file())
        self.assertTrue((root / "research/manifest.json").is_file())
        self.assertTrue((root / "research/prepared.json").is_file())
        self.assertTrue((root / "research/verification.json").is_file())
        self.assertEqual(outer.archive("curry_native_archive").file_count, 683)
        self.assertEqual(outer.archive("curry_final_archive").file_count, 684)
        self.assertEqual(outer.dataset_count("historical_consumed"), 32)
        self.assertEqual(outer.dataset_count("historical_unknown"), 0)
        self.assertEqual(outer.dataset_count("historical_ledgers"), 9)
        self.assertEqual(
            {child.role for child in outer.children},
            {"validation_baseline"},
        )
        self.assertEqual(
            {child.role for child in history.children},
            {"curry_baseline", "historical_ledgers"},
        )
        self.assertIn("static_preparation", {
            child.role for child in fixture.sources.children
        })
        self.assertTrue((root / "research/calls.jsonl").is_file())
        self.assertTrue((root / "research/summary.json").is_file())
        self.assertTrue((root / "research/verification.json").is_file())
        self.assertEqual(
            json.loads((root / "research/summary.json").read_bytes())["successful"],
            True,
        )
        self.assertEqual(
            validation.baseline_relative,
            "data/runtime/p1-tenki-runner-repair-offline-2026-10-23",
        )


if __name__ == "__main__":
    unittest.main()
