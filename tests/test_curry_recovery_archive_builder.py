"""Test-owned source archive writer is accepted by the real read-only verifier."""

from pathlib import Path
import unittest

from support.curry_recovery_archive import build_synthetic_archive_pair
from ygo_eval import curry_input_recovery_audit as audit


class CurryRecoveryArchiveBuilderTests(unittest.TestCase):
    def test_synthetic_archive_pair_matches_authenticated_file_list_and_delta(self):
        repo = Path(__file__).resolve().parents[1]
        output = repo / "target/curry-recovery-synthetic-e2e-tests/source-archive"
        handoff = "docs/superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md"
        artifact = build_synthetic_archive_pair(
            output,
            archive_filenames=("native.zip", "final.zip"),
            file_list_filenames=("native-list.json", "final-list.json"),
            native_files={
                "TASKS.md": b"old tasks\n",
                "docs/TESTING.md": b"old test record\n",
                "python/ygo_eval/synthetic.py": b"pass\n",
            },
            differences={
                "TASKS.md": b"new tasks\n",
                "docs/TESTING.md": b"new test record\n",
                handoff: b"synthetic handoff\n",
            },
            source_head="synthetic-head-v1",
            native_file_count=3,
            final_file_count=4,
        )

        result = audit.verify_source_archive_pair(
            artifact.native_archive,
            artifact.native_file_list,
            artifact.final_archive,
            artifact.final_file_list,
            expected_native_count=3,
            expected_final_count=4,
            expected_native_archive_sha256=artifact.native_archive_sha256,
            expected_native_list_sha256=artifact.native_file_list_sha256,
            expected_native_identity=artifact.native_source_identity,
            expected_final_archive_sha256=artifact.final_archive_sha256,
            expected_final_list_sha256=artifact.final_file_list_sha256,
            expected_final_identity=artifact.final_source_identity,
            expected_head="synthetic-head-v1",
        )

        self.assertEqual(result["native_file_count"], 3)
        self.assertEqual(result["final_file_count"], 4)
        self.assertEqual(result["differences"], sorted(audit.ALLOWED_ARCHIVE_DIFFS))
        self.assertEqual(
            set(artifact.final_files),
            set(artifact.native_files) | {handoff},
        )


if __name__ == "__main__":
    unittest.main()
