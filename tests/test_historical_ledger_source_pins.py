from __future__ import annotations

import unittest
import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch
import uuid

from ygo_eval import native_tenki_placement_confirmation as placement
from ygo_eval import tenki_confirmation_runner_audit as runner_audit


class _HistoricalLedgerLeaf:
    def __init__(self, pins: dict[str, str], *, counts=None):
        self.pins = pins
        self.counts = counts or {"ledger_count": 7, "consumed": 26}
        self.paths: list[str] = []

    def file_sha256(self, relative_path: str) -> str:
        self.paths.append(relative_path)
        return self.pins[relative_path]

    def dataset_count(self, name: str) -> int:
        return self.counts[name]


class _AuditSources:
    def __init__(self, ledger_leaf: _HistoricalLedgerLeaf):
        self.ledger_leaf = ledger_leaf
        self.children: list[str] = []

    def child(self, role: str) -> _HistoricalLedgerLeaf:
        self.children.append(role)
        if role != "historical_ledgers":
            raise KeyError(role)
        return self.ledger_leaf


class _ConfirmationSources:
    def __init__(self, pins: dict[str, str], context: str):
        self.pins = pins
        self.context = context

    def file_sha256(self, relative_path: str) -> str:
        return self.pins[relative_path]

    def semantic_sha256(self, role: str) -> str:
        if role != "runner_confirmation_context":
            raise KeyError(role)
        return self.context


class HistoricalLedgerSourcePinTests(unittest.TestCase):
    def setUp(self):
        self.contracts = placement.OLD_LEDGER_CONTRACTS
        self.paths = [contract[1] for contract in self.contracts]
        self.pins = {
            path: f"{index + 1:064x}"
            for index, path in enumerate(self.paths)
        }

    def test_confirmation_runner_resolves_hashes_from_fixed_ledger_leaf(self):
        leaf = _HistoricalLedgerLeaf(self.pins)
        sources = _AuditSources(leaf)

        expected = runner_audit._historical_ledger_hashes(sources)

        self.assertEqual(sources.children, ["historical_ledgers"])
        self.assertEqual(leaf.paths, self.paths)
        self.assertEqual(expected, [self.pins[path] for path in self.paths])

    def test_confirmation_runner_without_sources_keeps_fixed_hashes(self):
        expected = runner_audit._historical_ledger_hashes(None)

        self.assertEqual(expected, [contract[2] for contract in self.contracts])

    def test_eighth_confirmation_ledger_uses_source_description_hash(self):
        context = "synthetic-confirmation-context"
        charged_sequence = placement._sha(placement._encode([]))
        checkpoint_raw = placement._encode({
            "budget": {
                "consumed": 0,
                "completed": 0,
                "unknown": 0,
                "reserved": 0,
                "abandoned": 0,
                "limit": 6,
            },
            "charged_sequence": charged_sequence,
            "reservations": {},
            "search": {},
        })
        checkpoint_hash = hashlib.sha256(checkpoint_raw).hexdigest()
        entries = [
            {
                "kind": "header",
                "version": 1,
                "scope": "tenki-placement-confirmation-v1",
                "context": context,
                "limit": 6,
            },
            {
                "kind": "checkpoint",
                "name": "immutable/tenki-placement-confirmation/start",
                "consumed": 0,
                "charged_sequence": charged_sequence,
                "blob": checkpoint_hash,
            },
        ]
        rows = []
        previous = ""
        for sequence, entry in enumerate(entries):
            ordered = placement._ordered_entry(entry)
            record_hash = placement._sha(
                placement._encode([sequence, previous, ordered])
            )
            rows.append({
                "sequence": sequence,
                "previous": previous,
                "entry": ordered,
                "hash": record_hash,
            })
            previous = record_hash
        ledger_raw = b"".join(placement._encode(row) + b"\n" for row in rows)

        repo = Path(__file__).resolve().parents[1]
        experiment = repo / "target/curry-recovery-synthetic-e2e-tests" / uuid.uuid4().hex
        ledger_path = experiment / "research/calls.jsonl"
        checkpoint_path = (
            experiment / "research/calls.jsonl.blobs/checkpoints" / f"{checkpoint_hash}.json"
        )
        try:
            ledger_path.parent.mkdir(parents=True)
            checkpoint_path.parent.mkdir(parents=True)
            ledger_path.write_bytes(ledger_raw)
            checkpoint_path.write_bytes(checkpoint_raw)
            sources = _ConfirmationSources({
                ledger_path.relative_to(repo).as_posix(): hashlib.sha256(ledger_raw).hexdigest(),
                checkpoint_path.relative_to(repo).as_posix(): checkpoint_hash,
            }, context)

            protected, summary = runner_audit._verify_eighth_ledger(
                experiment,
                _sources=sources,
                repo=repo,
            )
        finally:
            if experiment.exists():
                shutil.rmtree(experiment)

        self.assertEqual(summary["sha256"], hashlib.sha256(ledger_raw).hexdigest())
        self.assertEqual(summary["records"], 2)
        self.assertEqual(summary["consumed"], 0)
        self.assertEqual(summary["unknown"], 0)
        self.assertEqual(len(protected), 2)

    def test_placement_scope_uses_source_hashes_for_audit_and_history_binding(self):
        leaf = _HistoricalLedgerLeaf(self.pins)

        expected = placement._old_ledger_expected_hashes(leaf)
        matched = placement._old_ledger_hashes_match(
            [{"sha256": value} for value in expected], leaf,
        )

        self.assertTrue(matched)
        self.assertEqual(leaf.paths, self.paths * 2)
        self.assertNotEqual(expected, [contract[2] for contract in self.contracts])

    def test_placement_ledger_audit_passes_source_hashes_to_each_fixed_ledger(self):
        leaf = _HistoricalLedgerLeaf(self.pins, counts={
            "ledger_count": len(self.contracts),
            "consumed": sum(contract[3] for contract in self.contracts),
            **{
                f"ledger_{contract[0]}_consumed": contract[3]
                for contract in self.contracts
            },
        })
        seen = []

        def audit_synthetic_ledger(_repo, contract, *, _sources=None):
            seen.append((contract, _sources))
            return {
                "sha256": contract[2],
                "stats": {"consumed": contract[3], "unknown": 0},
            }

        with patch.object(
            placement, "_audit_one_ledger", side_effect=audit_synthetic_ledger,
        ):
            results = placement._audit_old_ledgers(Path("synthetic-repo"), _sources=leaf)

        self.assertEqual([item[0][1] for item in seen], self.paths)
        self.assertEqual([item[0][2] for item in seen], [self.pins[path] for path in self.paths])
        self.assertTrue(all(item[1] is leaf for item in seen))
        self.assertEqual([item["sha256"] for item in results], [self.pins[path] for path in self.paths])
        self.assertEqual(leaf.paths, self.paths)

    def test_missing_source_ledger_pin_does_not_fall_back_to_production_hash(self):
        leaf = _HistoricalLedgerLeaf({})

        with self.assertRaises(KeyError):
            placement._old_ledger_expected_hashes(leaf)

    def test_placement_scope_without_sources_keeps_fixed_hashes(self):
        self.assertEqual(
            placement._old_ledger_expected_hashes(None),
            tuple(contract[2] for contract in self.contracts),
        )
        self.assertTrue(placement._old_ledger_hashes_match(
            [{"sha256": contract[2]} for contract in self.contracts], None,
        ))


if __name__ == "__main__":
    unittest.main()
