from __future__ import annotations

import hashlib
import shutil
import unittest
from pathlib import Path
import uuid

from ygo_eval.native_tenki_placement_confirmation import (
    _audit_one_ledger,
    _encode,
    _ordered_entry,
)


class _PinnedSources:
    def __init__(self, path: str, sha256: str):
        self.path = path
        self.sha256 = sha256

    def file_sha256(self, relative_path: str) -> str:
        if relative_path != self.path:
            raise KeyError("missing_test_pin")
        return self.sha256


class RecursiveSourceDescriptionTests(unittest.TestCase):
    def test_ledger_uses_description_pin_instead_of_production_hash(self):
        relative = "research/calls.jsonl"
        entry = {
            "kind": "header",
            "version": 1,
            "scope": "synthetic-scope",
            "context": "synthetic-context",
            "limit": 1,
        }
        row = {
            "sequence": 0,
            "previous": "",
            "entry": _ordered_entry(entry),
        }
        row["hash"] = hashlib.sha256(_encode([0, "", row["entry"]])).hexdigest()
        raw = _encode(row) + b"\n"
        expected_hash = hashlib.sha256(raw).hexdigest()
        contract = (
            "synthetic", relative, "0" * 64, 0, "synthetic-scope",
            "synthetic-context", 1,
        )

        repository = Path(__file__).resolve().parents[1]
        repo = repository / "target/curry-recovery-synthetic-e2e-tests/ledger-source-pin" / uuid.uuid4().hex
        ledger = repo / relative
        try:
            ledger.parent.mkdir(parents=True)
            ledger.write_bytes(raw)
            blob_root = ledger.with_name(ledger.name + ".blobs")
            for name in ("results", "events", "checkpoints", "recoveries"):
                (blob_root / name).mkdir(parents=True)

            result = _audit_one_ledger(
                repo,
                contract,
                _sources=_PinnedSources(relative, expected_hash),
            )
        finally:
            if repo.exists():
                shutil.rmtree(repo)
        self.assertEqual(result["sha256"], expected_hash)
        self.assertEqual(result["stats"]["consumed"], 0)


if __name__ == "__main__":
    unittest.main()
