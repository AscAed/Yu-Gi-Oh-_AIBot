"""Read-only lineage gate tests for Curry option revalidation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ygo_eval.curry_ledger_handoff_recovery as recovery
import ygo_eval.native_curry_option_validation as curry
from ygo_data.identity import canonical


class CurryOptionRevalidationBaselineTests(unittest.TestCase):
    def test_production_source_separates_v3_delivery_identity_from_archive_identity(self):
        source = curry._production_option_revalidation_source()

        self.assertEqual(
            source.recovery_delivery_workspace_identity,
            "29e4c74081c42e8cedaff7bd90d174e3d8002dfec31e82855b830bb471f3c918",
        )
        self.assertEqual(source.recovery_delivery_workspace_file_count, 589)
        self.assertNotEqual(
            source.recovery_delivery_workspace_identity,
            source.recovery_profile.final_identity,
        )

    def test_v3_recovery_is_verified_with_its_v3_source_profile(self):
        repo = Path.cwd()
        baseline_root = Path("synthetic-v3-root")
        baseline = repo / baseline_root
        report = {
            "status": "passed",
            "valid": True,
            "native_calls": 0,
            "runner_process_calls": 0,
            "accounting": {
                "certified_historical_consumed_including_scope": 33,
                "planning_total": 40,
            },
        }
        report_raw = json.dumps(report, sort_keys=True).encode("utf-8")
        delivery = {
            "kind": "curry_ledger_handoff_recovery_v3_final_delivery",
            "status": "passed",
            "report": {
                "sha256": hashlib.sha256(report_raw).hexdigest(),
                "path": "../recovery-report.json",
            },
            "source_after_docs": {
                "workspace_identity": "29e4c74081c42e8cedaff7bd90d174e3d8002dfec31e82855b830bb471f3c918",
                "file_count": 589,
            },
        }
        delivery_raw = json.dumps(delivery, sort_keys=True).encode("utf-8")
        raw_by_name = {
            "recovery-report.json": report_raw,
            "delivery-final.json": delivery_raw,
        }
        actual_spec = replace(
            curry.OPTION_REVALIDATION_SCOPE,
            baseline_root=baseline_root,
            baseline_recovery_sha256=hashlib.sha256(report_raw).hexdigest(),
            delivery_sha256=hashlib.sha256(delivery_raw).hexdigest(),
        )
        source = {"identity": "stable"}
        reservation_info = {
            "reservation_id": actual_spec.reservation_id,
            "policy_id": actual_spec.reservation_policy_id,
            "certified_historical_consumed": 32,
            "planning_base": 39,
        }
        observed = {}
        tree = {"stable": "tree-snapshot"}

        def verify_only(*args, **kwargs):
            observed.update(kwargs)
            return {
                "valid": True,
                "native_calls": 0,
                "runner_process_calls": 0,
            }

        def protected_hash(path, root):
            path = Path(path)
            if path == root / baseline_root:
                return hashlib.sha256(canonical(tree)).hexdigest()
            raw = raw_by_name[path.name]
            return hashlib.sha256(raw).hexdigest()

        def read_only_path(path):
            raw = raw_by_name[Path(path).name]
            return SimpleNamespace(read_bytes=lambda: raw)

        with (
            patch.object(curry, "OPTION_REVALIDATION_SCOPE", actual_spec),
            patch.object(curry, "safe_path", side_effect=read_only_path),
            patch.object(recovery, "_tree_snapshot", return_value=tree),
            patch.object(recovery, "_verify_only", side_effect=verify_only),
            patch.object(
                curry, "_verify_option_verification_baseline",
                return_value=(reservation_info, {}),
            ),
            patch.object(
                curry, "_option_revalidation_protected_hash",
                side_effect=protected_hash,
            ),
        ):
            info, protected = curry._verify_option_revalidation_baseline(
                repo, baseline, source_collector=lambda _repo: source,
            )

        self.assertIs(observed.get("_profile"), recovery.V3_PROFILE)
        self.assertEqual(
            recovery.V3_PROFILE.source_delta,
            {
                "added": [
                    "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md",
                ],
                "removed": [],
                "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
            },
        )
        self.assertEqual(info["certified_historical_consumed"], 33)
        self.assertIn(baseline, protected)


if __name__ == "__main__":
    unittest.main()
