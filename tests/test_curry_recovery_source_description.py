"""Source-description routing tests for Curry's read-only audit helpers."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
import uuid

from tests.support.curry_recovery_archive import build_synthetic_archive_pair
from tests.support.curry_recovery_e2e import build_synthetic_recovery_tree
from ygo_eval import curry_input_recovery_audit as audit
from ygo_eval import native_curry_option_validation as curry


class CurryRecoverySourceDescriptionTests(unittest.TestCase):
    def test_confirmation_baseline_reads_archives_from_asset_audit_scope(self):
        workspace = Path(__file__).resolve().parents[1]
        root = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        fixture = build_synthetic_recovery_tree(root)
        source_node = fixture.sources.child("asset_audit")
        old_scope = source_node.child("asset_audit_scope")

        historical_scope = source_node.child("historical_chain").child("curry_baseline")
        selected = curry._confirmation_archive_source_scope(source_node)

        self.assertIs(selected, old_scope)
        self.assertNotEqual(
            selected.archive("curry_native_archive").archive_path,
            historical_scope.archive("curry_native_archive").archive_path,
        )
        self.assertEqual(
            list(selected.differences("curry_baseline")),
            list(old_scope.differences("curry_baseline")),
        )
        with self.assertRaises(KeyError):
            curry._confirmation_archive_source_scope(historical_scope)

        from ygo_eval.curry_asset_binding_audit import _verify_archive

        pin = selected.archive("curry_native_archive")
        expected = {
            "archive_sha256": pin.archive_sha256,
            "file_list_sha256": pin.file_list_sha256,
            "source_identity": pin.source_identity,
            "file_count": pin.file_count,
            "head": pin.head,
        }
        archive_path = fixture.repo / pin.archive_path
        archive_path.write_bytes(archive_path.read_bytes() + b"synthetic-tamper")
        with self.assertRaisesRegex(ValueError, "pinned_input_hash_mismatch"):
            _verify_archive(
                fixture.repo, pin.archive_path, pin.file_list_path,
                expected,
            )

    def test_confirmation_baseline_rejects_swapped_or_missing_archive_source_node(self):
        workspace = Path(__file__).resolve().parents[1]
        root = workspace / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        fixture = build_synthetic_recovery_tree(root)
        asset_audit = fixture.sources.child("asset_audit")
        old_scope = asset_audit.child("asset_audit_scope")
        historical_scope = asset_audit.child("historical_chain").child("curry_baseline")

        # Both subtrees intentionally contain archive roles with the same
        # names. Re-labeling the historical node must not make its pins
        # acceptable as the old Curry archive source.
        swapped_node = replace(historical_scope, role="asset_audit_scope")
        swapped = replace(
            asset_audit,
            children=tuple(
                swapped_node if child.role == "asset_audit_scope" else child
                for child in asset_audit.children
            ),
        )
        self.assertNotEqual(
            swapped.child("asset_audit_scope").archive("curry_native_archive").archive_path,
            old_scope.archive("curry_native_archive").archive_path,
        )
        with self.assertRaises((KeyError, ValueError)):
            curry._verify_confirmation_baseline(
                fixture.repo,
                fixture.repo / fixture.sources.baseline_relative,
                _sources=swapped,
            )

        missing = replace(
            asset_audit,
            children=tuple(
                child for child in asset_audit.children
                if child.role != "asset_audit_scope"
            ),
        )
        with self.assertRaises(KeyError):
            curry._confirmation_archive_source_scope(missing)

    def test_archive_pair_accepts_expected_delta_from_source_description(self):
        root = Path(__file__).resolve().parents[1] / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        artifact = build_synthetic_archive_pair(
            root,
            archive_filenames=("native.zip", "final.zip"),
            file_list_filenames=("native-list.json", "final-list.json"),
            native_files={"source.py": b"old\n", "same.py": b"same\n"},
            differences={"source.py": b"new\n"},
            source_head="0123456789abcdef0123456789abcdef01234567",
            native_file_count=2,
            final_file_count=2,
        )

        result = audit.verify_source_archive_pair(
            artifact.native_archive,
            artifact.native_file_list,
            artifact.final_archive,
            artifact.final_file_list,
            expected_native_count=2,
            expected_final_count=2,
            expected_native_archive_sha256=artifact.native_archive_sha256,
            expected_native_list_sha256=artifact.native_file_list_sha256,
            expected_native_identity=artifact.native_source_identity,
            expected_final_archive_sha256=artifact.final_archive_sha256,
            expected_final_list_sha256=artifact.final_file_list_sha256,
            expected_final_identity=artifact.final_source_identity,
            expected_head="0123456789abcdef0123456789abcdef01234567",
            expected_differences=("source.py",),
        )

        self.assertEqual(result["differences"], ["source.py"])

    def test_nearest_source_node_wins_for_reused_archive_and_semantic_roles(self):
        child = audit._SourceDescription(
            role="nested",
            archives=(audit._PinnedArchive(
                "shared", "child.zip", "child.json", "a" * 64, "b" * 64,
                "c" * 64, 2, "synthetic-head",
            ),),
            semantic_hashes=(("codec", "d" * 64),),
            archive_differences=(("baseline", ("nested.py",)),),
        )
        root = audit._SourceDescription(
            role="root",
            archives=(audit._PinnedArchive(
                "shared", "root.zip", "root.json", "1" * 64, "2" * 64,
                "3" * 64, 2, "synthetic-head",
            ),),
            semantic_hashes=(("codec", "4" * 64),),
            archive_differences=(("baseline", ("root.py",)),),
            children=(child,),
        )

        self.assertEqual(root.archive("shared").archive_path, "root.zip")
        self.assertEqual(root.semantic_sha256("codec"), "4" * 64)
        self.assertEqual(root.differences("baseline"), ("root.py",))


if __name__ == "__main__":
    unittest.main()
