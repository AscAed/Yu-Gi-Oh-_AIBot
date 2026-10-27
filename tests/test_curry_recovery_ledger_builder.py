"""Smoke-test the test-owned frozen ledger writer against the real parser."""

from pathlib import Path
import json
import unittest

from support.curry_recovery_ledger import build_synthetic_first_batch_ledger
from ygo_eval.history_audit import verify_ledger


EXPECTED_CALLS = [
    ("rabbit", "execution"),
    ("rabbit", "replay"),
    ("phantom", "execution"),
    ("phantom", "replay"),
    ("tournament", "execution"),
    ("tournament", "replay"),
    ("tournament", "execution"),
    ("tournament", "execution"),
    ("tournament", "replay"),
]


class CurryRecoveryLedgerBuilderTests(unittest.TestCase):
    def test_test_owned_nine_call_ledger_matches_frozen_v1_parser(self):
        repo = Path(__file__).resolve().parents[1]
        output = repo / "target/curry-recovery-synthetic-e2e-tests/first-ledger"
        fixture = build_synthetic_first_batch_ledger(output)

        first_line = fixture.ledger_path.read_bytes().splitlines(keepends=True)[0]
        self.assertEqual(
            first_line,
            b'{"sequence":0,"previous":"","entry":{"kind":"header","version":1,"scope":"research-first-batch-v1","context":"synthetic-research-context-v1","limit":4096},"hash":"9dd972973829d9847ce524961428b8979b7017f8f0eb256fe93e3a446797bb94"}\n',
        )
        result = verify_ledger(
            fixture.ledger_path.read_bytes(), fixture.read_blob, fixture.requests
        )

        self.assertEqual(result["stats"], {
            "consumed": 9,
            "completed": 9,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": 4096,
        })
        self.assertEqual(result["ledger_records"], 37)
        self.assertEqual(len(result["checkpoints"]), 18)
        self.assertEqual(len(fixture.call_requests), 9)
        self.assertTrue(all(call["event_count"] == 1 for call in result["calls"]))
        self.assertEqual(
            [(call["case_id"], call["purpose"]) for call in result["calls"]],
            EXPECTED_CALLS,
        )
        self.assertEqual(fixture.unpaired_followup_error, {
            "code": "journal_checkpoint",
            "stage": "call_journal",
        })
        self.assertEqual(fixture.authorized_window["base_consumed"], 7)
        self.assertEqual(fixture.authorized_window["additional_calls"], 2)

        rows = [json.loads(line) for line in fixture.ledger_path.read_bytes().splitlines()]
        window_index = next(
            index for index, row in enumerate(rows)
            if row["entry"].get("name")
            == "immutable/research/authorized-window/user-resume-20261019"
        )
        call8_index = next(
            index for index, row in enumerate(rows)
            if row["entry"].get("kind") == "begin"
            and row["entry"].get("call_id") == 8
        )
        call7_complete_index = next(
            index for index, row in enumerate(rows)
            if row["entry"].get("kind") == "complete"
            and row["entry"].get("call_id") == 7
        )
        self.assertLess(call7_complete_index, window_index)
        self.assertLess(window_index, call8_index)
        self.assertEqual(sum(row["entry"].get("kind") == "begin" for row in rows), 9)
        self.assertFalse(any(
            row["entry"].get("kind") == "begin"
            and row["entry"].get("call_id") == 10
            for row in rows
        ))


if __name__ == "__main__":
    unittest.main()
