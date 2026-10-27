"""Wire-contract tests for the isolated Curry option validation scope."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from ygo_eval.native_curry_option_validation import HISTORICAL_SOURCE_TRANSITION


REPO = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO / "schemas" / "native-curry-option-validation.schema.json"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _stats(consumed: int, *, unknown: int = 0, completed: int | None = None) -> dict:
    return {
        "consumed": consumed,
        "completed": consumed - unknown if completed is None else completed,
        "unknown": unknown,
        "reserved": 0,
        "abandoned": 0,
        "limit": 7,
    }


def _stage_summary(stage: int, *, successful: bool = True,
                   unknown: int = 0) -> dict:
    replay = stage in (5, 7)
    return {
        "stage": stage,
        "successful": successful,
        "native_calls": 1,
        "diagnostic": None if successful else "stage_failed",
        "receipt_sha256": f"{stage:064x}" if successful else None,
        "diagnostic_sha256": HASH_A,
        "independent_replay_matches": True if replay and successful else None,
        "ledger": _stats(stage, unknown=unknown),
    }


def _success_summary() -> dict:
    return {
        "schema_version": 1,
        "kind": "native_curry_option_validation_summary",
        "scope": "curry-option-validation-v1",
        "context": HASH_A,
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
        "successful": True,
        "old_consumed": 32,
        "new_consumed": 7,
        "cumulative_consumed": 39,
        "unknown": 0,
        "ledger": _stats(7),
        "stages": [_stage_summary(stage) for stage in range(1, 8)],
        "diagnostic": None,
    }


def _validate(document: dict) -> None:
    Draft202012Validator(_schema()).validate(document)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class NativeCurryOptionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = Draft202012Validator(_schema())
        cls.validator.check_schema(_schema())

    def test_manifest_and_prepared_documents_are_scope_bound(self):
        manifest = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_manifest",
            "scope": "curry-option-validation-v1",
            "batch_kind": "curry-option-validation-v1",
            "context": HASH_A,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "started_at": 1_798_000_000,
            "limit": 7,
            "planned_calls": 7,
            "wall_seconds": 7200,
            "old_consumed": 32,
            "baseline_acceptance_sha256": "242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9",
            "baseline_delivery_sha256": "7c46a4a790c56dea2daf77478c5a33654ee20bb3bd3179bdfb57ebf74cc21061",
            "input_sha256": {
                "preparation": "235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022",
                "preparation_report": "22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073",
                "preparation_acceptance": "0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7",
                "candidate_case": "71aa1e51edf74b3b4b572d61cbdaf7b25414ebc6fba745c72b1e82fe18e5a23c",
                "base_request": "d25d2e79a58728221111d9007f5890b3e99be2bdcf4a8aee1a17554d59da91bb",
                "operations_source": "b46cf0d53825cb662af319a7382015b555422aa11903067445c994c4b0c8a990",
                "adapter_codec": HISTORICAL_SOURCE_TRANSITION["current_sha256"],
                "runner": HASH_A,
                "worker": HASH_B,
                "cli": HASH_C,
                "build_record": HASH_A,
                "identity": HASH_B,
                "window_start": HASH_C,
                "source_archive": HASH_A,
                "source_file_list": HASH_B,
                "ordinary_config": HASH_C,
                "tournament_config": HASH_A,
                "banlist": HASH_B,
                "core_source": HASH_C,
                "baseline_delivery": HASH_A,
            },
            "source": {"identity": "frozen"},
            "historical_source_transition": HISTORICAL_SOURCE_TRANSITION,
            "build": {"runner": HASH_A},
            "assets": {"ordinary": HASH_B},
            "stage1_request_sha256": HASH_C,
            "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
            "request": {"protocol_version": 2, "seed": 1, "decisions": []},
        }
        prepared = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_prepared",
            "scope": "curry-option-validation-v1",
            "context": HASH_A,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "prepared": True,
            "execution_ready": True,
            "native_calls": 0,
            "planned_calls": 7,
            "manifest_sha256": HASH_B,
            "stage1_request_sha256": HASH_C,
            "stage1_input_sha256": HASH_A,
            "preflight_diagnostic_sha256": HASH_B,
            "diagnostics": [],
        }
        self.validator.validate(manifest)
        missing_batch_kind = copy.deepcopy(manifest)
        missing_batch_kind.pop("batch_kind")
        self.assertTrue(list(self.validator.iter_errors(missing_batch_kind)))
        self.validator.validate(prepared)

        for doc, mutate in (
            (manifest, lambda d: d.update(limit=8)),
            (manifest, lambda d: d["input_sha256"].pop("operations_source")),
            (manifest, lambda d: d["input_sha256"].update(adapter_codec=HASH_A)),
            (manifest, lambda d: d["historical_source_transition"].update(current_sha256=HASH_A)),
            (prepared, lambda d: d.update(native_calls=1)),
            (prepared, lambda d: d.update(proof_ready=True)),
            (prepared, lambda d: d.update(prepared=False, execution_ready=True)),
        ):
            forged = copy.deepcopy(doc)
            mutate(forged)
            self.assertTrue(list(self.validator.iter_errors(forged)))

    def test_stage_receipts_cover_each_slot_and_bind_replay_stages(self):
        for stage in range(1, 8):
            replay = stage in (5, 7)
            receipt = {
                "schema_version": 1,
                "kind": "native_curry_option_validation_stage",
                "scope": "curry-option-validation-v1",
                "context": HASH_A,
                "proof_ready": False,
                "complete_action_coverage": False,
                "global_optimality": False,
                "native_probability_verified": False,
                "stage": stage,
                "request": {"decisions": []},
                "successful": True,
                "diagnostic": None,
                "assets_unchanged": True,
                "assets_before": {"ordinary": HASH_B},
                "assets_after": {"ordinary": HASH_B},
                "window_valid_at_result": True,
                "validation": {"response_oracle_matches": True},
                "result": {"status": "decision_required"},
                "independent_replay_matches": True if replay else None,
                "ledger": _stats(stage),
            }
            self.validator.validate(receipt)

        forged = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_stage",
            "scope": "curry-option-validation-v1",
            "context": HASH_A,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "stage": 5,
            "request": {},
            "successful": True,
            "diagnostic": None,
            "assets_unchanged": True,
            "assets_before": {},
            "assets_after": {},
            "window_valid_at_result": True,
            "validation": {},
            "result": {},
            "independent_replay_matches": None,
            "ledger": _stats(5),
        }
        self.assertTrue(list(self.validator.iter_errors(forged)))

        out_of_range = copy.deepcopy(forged)
        out_of_range.update(stage=8, independent_replay_matches=None)
        self.assertTrue(list(self.validator.iter_errors(out_of_range)))

    def test_summary_success_requires_all_seven_completed_and_no_unknown_consumption(self):
        good = _success_summary()
        self.validator.validate(good)

        invalids = []
        missing_stage = copy.deepcopy(good)
        missing_stage["stages"].pop()
        invalids.append(missing_stage)

        incomplete = copy.deepcopy(good)
        incomplete["ledger"] = _stats(7, unknown=1)
        incomplete["stages"][6]["ledger"] = _stats(7, unknown=1)
        incomplete.update(new_consumed=7, cumulative_consumed=39, unknown=1)
        invalids.append(incomplete)

        bad_replay = copy.deepcopy(good)
        bad_replay["stages"][4]["independent_replay_matches"] = None
        invalids.append(bad_replay)

        forged_qualification = copy.deepcopy(good)
        forged_qualification["global_optimality"] = True
        invalids.append(forged_qualification)

        wrong_order = copy.deepcopy(good)
        wrong_order["stages"][1], wrong_order["stages"][2] = (
            wrong_order["stages"][2], wrong_order["stages"][1]
        )
        invalids.append(wrong_order)

        for forged in invalids:
            with self.subTest(forged=forged):
                self.assertTrue(list(self.validator.iter_errors(forged)))

    def test_partial_failure_and_unknown_consumption_remain_reportable(self):
        partial = _success_summary()
        partial.update(
            successful=False,
            new_consumed=2,
            cumulative_consumed=34,
            unknown=1,
            ledger=_stats(2, unknown=1),
            stages=[_stage_summary(1), _stage_summary(2, successful=False, unknown=1)],
            diagnostic="ledger_contains_unknown_consumption",
        )
        self.validator.validate(partial)

        unknown = copy.deepcopy(partial)
        unknown.update(new_consumed=None, cumulative_consumed=None, unknown=None, ledger=None)
        unknown["stages"][1]["ledger"] = None
        unknown["stages"][1]["native_calls"] = None
        self.validator.validate(unknown)

        self.assertTrue(list(self.validator.iter_errors({**partial, "successful": True})))

    def test_verification_success_is_zero_call_and_requires_all_receipts(self):
        stages = [_stage_summary(stage) for stage in range(1, 8)]
        verification = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_verification",
            "scope": "curry-option-validation-v1",
            "context": HASH_A,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "valid": True,
            "native_calls": 0,
            "old_consumed": 32,
            "new_consumed": 7,
            "cumulative_consumed": 39,
            "unknown": 0,
            "ledger": _stats(7),
            "stages": stages,
            "prepared_sha256": HASH_B,
            "verification_diagnostic_sha256": [HASH_C] * 7,
            "diagnostic": None,
        }
        self.validator.validate(verification)

        for mutation in (
            lambda value: value.update(native_calls=1),
            lambda value: value.update(unknown=1, ledger=_stats(7, unknown=1)),
            lambda value: value.update(proof_ready=True),
        ):
            forged = copy.deepcopy(verification)
            mutation(forged)
            self.assertTrue(list(self.validator.iter_errors(forged)))

        partial = copy.deepcopy(verification)
        partial.update(valid=False, new_consumed=6, cumulative_consumed=38,
                       ledger=_stats(6), stages=stages[:6],
                       verification_diagnostic_sha256=[HASH_C] * 6,
                       diagnostic="saved_validation_incomplete_or_invalid")
        self.validator.validate(partial)

        for mutation in (
            lambda value: value.update(new_consumed=5),
            lambda value: value.update(cumulative_consumed=37),
            lambda value: value.update(unknown=1),
            lambda value: value.update(verification_diagnostic_sha256=[HASH_C] * 5),
            lambda value: value.update(diagnostic=None),
        ):
            forged = copy.deepcopy(partial)
            mutation(forged)
            with self.subTest(forged=forged):
                self.assertTrue(list(self.validator.iter_errors(forged)))


if __name__ == "__main__":
    unittest.main()
