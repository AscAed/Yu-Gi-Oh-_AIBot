"""Focused compatibility checks for reusable synthetic Curry stage-1 evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import unittest
import uuid

from tests.support.curry_recovery_e2e import (
    _encode_ledger,
    _ordered_test_ledger_entry,
    _synthetic_generic_ledger,
)
from tests.test_native_curry_option_validation import IDENTITY, _receipt
from ygo_eval.native_curry_option_validation import validate_curry_stage_receipt


_TEMP_BASE = Path(__file__).resolve().parents[1] / "target/curry-ledger-handoff-v2-tests/stage1-fixture"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class CurryStage1FixtureCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        _TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.root = _TEMP_BASE / f"run-{uuid.uuid4().hex}"
        self.root.mkdir(exist_ok=False)

    def tearDown(self) -> None:
        if self.root.parent != _TEMP_BASE:
            raise AssertionError("synthetic test cleanup escaped its fixed target directory")
        shutil.rmtree(self.root)

    def test_stage1_receipt_fixture_passes_production_validator(self) -> None:
        request = {"decisions": []}
        receipt = _receipt(1, request, resolved=[])

        auto_tail = validate_curry_stage_receipt(
            receipt,
            request,
            "a" * 64,
            1,
            IDENTITY,
        )

        self.assertEqual(auto_tail, [])
        self.assertEqual(receipt["result"]["Ok"]["status"], "decision_required")
        self.assertEqual(receipt["result"]["Ok"]["prompt"]["opcode"], 11)

    def test_generic_one_call_ledger_has_rust_journal_wire_shape(self) -> None:
        scope = "curry-option-verification-v1"
        context = "c" * 64
        ledger = self.root / "calls.jsonl"
        (request_hash,) = _synthetic_generic_ledger(
            ledger,
            scope,
            context,
            count=1,
            limit=7,
            role="curry-stage-1",
        )

        rows = [json.loads(line) for line in ledger.read_bytes().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["entry"], {
            "kind": "header",
            "version": 1,
            "scope": scope,
            "context": context,
            "limit": 7,
        })
        self.assertEqual(rows[1]["entry"]["kind"], "begin")
        self.assertEqual(rows[1]["entry"]["request"], request_hash)
        self.assertEqual(rows[1]["entry"]["purpose"], "execution")
        self.assertEqual(rows[2]["entry"]["kind"], "complete")

        previous = ""
        for sequence, row in enumerate(rows):
            self.assertEqual(row["sequence"], sequence)
            self.assertEqual(row["previous"], previous)
            expected = _sha(_encode_ledger([
                sequence,
                previous,
                _ordered_test_ledger_entry(row["entry"]),
            ]))
            self.assertEqual(row["hash"], expected)
            previous = expected

        blob_root = ledger.with_name(ledger.name + ".blobs")
        result_hash = rows[2]["entry"]["result"]
        result_blob = blob_root / "results" / f"{result_hash}.json"
        result_record = json.loads(result_blob.read_bytes())
        event_hash = result_record["event_chunks"][0]
        event_blob = blob_root / "events" / f"{event_hash}.json"
        self.assertEqual(_sha(result_blob.read_bytes()), result_hash)
        self.assertEqual(_sha(event_blob.read_bytes()), event_hash)
        self.assertEqual(result_record["kind"], "duel")
        self.assertEqual(result_record["result"]["events"], [])


if __name__ == "__main__":
    unittest.main()
