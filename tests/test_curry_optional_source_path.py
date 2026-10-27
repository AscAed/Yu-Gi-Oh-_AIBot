from __future__ import annotations

from pathlib import Path
import uuid
import unittest
from unittest.mock import patch

from ygo_eval import curry_asset_binding_audit as audit


class CurryOptionalSourcePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(audit.__file__).resolve().parents[2]
        cls.scratch = cls.workspace / "target/curry-optional-source-path-tests"
        cls.scratch.mkdir(parents=True, exist_ok=True)

    def test_missing_file_is_allowed_when_its_parent_is_a_safe_directory(self):
        repo = self.scratch / uuid.uuid4().hex
        relative = "data/runtime/scope/research/calls.jsonl"
        expected = repo / relative
        expected.parent.mkdir(parents=True)

        actual = audit._source_optional_file_path(repo, relative)

        self.assertEqual(actual, expected)
        self.assertTrue(actual.parent.is_dir())
        self.assertFalse(actual.exists())

    def test_missing_file_is_rejected_when_its_parent_does_not_exist(self):
        repo = self.scratch / uuid.uuid4().hex
        repo.mkdir()

        with self.assertRaises(FileNotFoundError):
            audit._source_optional_file_path(
                repo, "data/runtime/scope/research/calls.jsonl",
            )

    def test_symlink_parent_is_rejected(self):
        repo = self.scratch / uuid.uuid4().hex
        repo.mkdir()
        actual_parent = repo / "actual"
        actual_parent.mkdir()
        link_parent = repo / "linked"
        try:
            link_parent.symlink_to(actual_parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink unavailable: {type(exc).__name__}")

        with self.assertRaisesRegex(ValueError, "linked_path_rejected"):
            audit._source_optional_file_path(repo, "linked/calls.jsonl")

    def test_unsafe_parent_is_rejected(self):
        repo = self.scratch / uuid.uuid4().hex
        repo.mkdir()

        with self.assertRaisesRegex(ValueError, "asset_audit_source_path_invalid"):
            audit._source_optional_file_path(repo, "../outside/calls.jsonl")

    def test_parent_validation_rejects_a_reparse_path_reported_by_safe_path(self):
        repo = self.scratch / uuid.uuid4().hex
        repo.mkdir()

        with patch.object(
            audit, "safe_path", side_effect=ValueError("linked_path_rejected"),
        ) as safe_path:
            with self.assertRaisesRegex(ValueError, "linked_path_rejected"):
                audit._source_optional_file_path(repo, "linked/calls.jsonl")

        safe_path.assert_called_once_with(repo / "linked", file=False)


if __name__ == "__main__":
    unittest.main()
