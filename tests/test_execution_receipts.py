import copy
import json
import os
import pathlib
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator

from ygo_eval.execution_receipts import (
    ReceiptValidationError,
    context_digest,
    event_digest,
    sha256,
    verify_files,
    verify_receipt_chain,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
ATTEMPT_ID = "a" * 32
FIXTURE_RECEIPT = ROOT / "tests/fixtures/w1c-execution-receipt-v1.json"
FIXTURE_REPORT = ROOT / "tests/fixtures/w1c-execution-report-v1.json"
REPORT_RAW = FIXTURE_REPORT.read_bytes()


def load_fixture_receipt():
    return json.loads(FIXTURE_RECEIPT.read_text(encoding="utf-8"))


def make_receipt(specs, *, operation_id="1" * 32, job_id="2" * 32, input_sha256="3" * 64):
    context = {
        "operation_id": operation_id,
        "job_id": job_id,
        "input_sha256": input_sha256,
        "source_bundle_identity": "4" * 64,
        "build_record_identity": "5" * 64,
        "assets": {"cli": "6" * 64, "worker": "7" * 64, "engine": "8" * 64},
    }
    context_hash = context_digest(context)
    events = []
    previous = "0" * 64
    for sequence, spec in enumerate(specs, start=1):
        if len(spec) == 2:
            event_type, payload = spec
            attempt_id = ATTEMPT_ID
        else:
            event_type, payload, attempt_id = spec
        event = {
            "sequence": sequence,
            "attempt_id": attempt_id,
            "event_type": event_type,
            "previous_sha256": previous,
            "payload": payload,
        }
        event["event_sha256"] = event_digest(context_hash, event)
        events.append(event)
        previous = event["event_sha256"]
    return {
        "schema_version": 1,
        "kind": "w1c_execution_receipt_chain",
        "context": context,
        "context_sha256": context_hash,
        "events": events,
        "consumption": {"status": "unknown", "unit": None, "count": None, "evidence_sha256": None},
    }


def complete_specs(report_raw=REPORT_RAW):
    response = b'{"worker_status":"ok"}\n'
    request = b'{"request":"synthetic"}\n'
    return [
        ("adapter_attempt", {"command_sha256": "9" * 64, "status": "started"}),
        ("worker_spawn", {"status": "spawned", "pid": 12345, "executable_sha256": "7" * 64}),
        ("protocol_request", {"status": "written", "request_sha256": sha256(request), "bytes": len(request), "input_sha256": "3" * 64}),
        ("ffi_entered", {"call_id": "b" * 32, "direction": "host_to_ocgcore", "name": "DuelProcess", "ordinal": 1}),
        ("ffi_returned", {"call_id": "b" * 32, "status": "returned", "result_sha256": "c" * 64}),
        (
            "protocol_response",
            {
                "status": "received",
                "response_sha256": sha256(response),
                "bytes": len(response),
                "exit_code": 0,
                "observation": "complete",
                "ffi_receipt_status": "complete",
            },
        ),
        (
            "report_persisted",
            {
                "status": "committed",
                "report_sha256": sha256(report_raw),
                "report_bytes": len(report_raw),
                "readback_sha256": sha256(report_raw),
            },
        ),
    ]


def reseal(receipt):
    previous = "0" * 64
    context_hash = context_digest(receipt["context"])
    receipt["context_sha256"] = context_hash
    for event in receipt["events"]:
        event["previous_sha256"] = previous
        event["event_sha256"] = event_digest(context_hash, event)
        previous = event["event_sha256"]
    return receipt


class ExecutionReceiptContractTests(unittest.TestCase):
    def test_complete_synthetic_chain_and_report_bytes_verify(self):
        receipt = load_fixture_receipt()
        result = verify_receipt_chain(receipt, REPORT_RAW, receipt["events"][-1]["event_sha256"])
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["counts"]["adapter_attempts"], 1)
        self.assertEqual(result["counts"]["worker_processes_observed"], 1)
        self.assertEqual(result["counts"]["protocol_requests_written"], 1)
        self.assertEqual(result["counts"]["ffi_entries_observed"], 1)
        self.assertEqual(result["counts"]["ffi_returns_observed"], 1)
        self.assertTrue(result["head_anchor_verified"])
        self.assertTrue(result["report_bytes_verified"])
        self.assertTrue(result["report_binding_verified"])
        self.assertFalse(result["report_origin_authenticated"])
        self.assertEqual(result["consumption"], {"status": "unknown", "unit": None, "count": None})

    def test_schema_accepts_complete_fixture_and_rejects_unknown_consumption(self):
        schema = json.loads((ROOT / "schemas/w1c-execution-receipt-chain-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        receipt = load_fixture_receipt()
        validator.validate(receipt)
        invalid = copy.deepcopy(receipt)
        invalid["consumption"]["count"] = 0
        self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(receipt)
        invalid["events"][0]["unexpected"] = True
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_spawn_failure_is_valid_but_incomplete_and_has_no_worker_counts(self):
        receipt = make_receipt(
            [
                ("adapter_attempt", {"command_sha256": "9" * 64, "status": "started"}),
                ("worker_spawn", {"status": "failed", "pid": None, "executable_sha256": None}),
            ]
        )
        result = verify_receipt_chain(receipt)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["counts"]["worker_processes_observed"], 0)
        self.assertEqual(result["counts"]["worker_spawn_failures"], 1)
        self.assertEqual(result["counts"]["protocol_requests_written"], 0)
        self.assertEqual(result["consumption"]["status"], "unknown")

    def test_one_job_can_record_multiple_sequential_completed_adapter_attempts(self):
        first_attempt = complete_specs()[:-1]
        second_attempt_id = "d" * 32
        second_call_id = "e" * 32
        second_attempt = copy.deepcopy(first_attempt)
        second_attempt[3][1]["call_id"] = second_call_id
        second_attempt[4][1]["call_id"] = second_call_id
        specs = [
            (event_type, payload, ATTEMPT_ID)
            for event_type, payload in first_attempt
        ]
        specs.extend(
            (event_type, payload, second_attempt_id)
            for event_type, payload in second_attempt
        )
        specs.append(("report_persisted", complete_specs()[-1][1], second_attempt_id))

        receipt = make_receipt(specs)
        result = verify_receipt_chain(receipt, REPORT_RAW)

        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["counts"]["adapter_attempts"], 2)
        self.assertEqual(result["counts"]["worker_processes_observed"], 2)
        self.assertEqual(result["counts"]["protocol_requests_written"], 2)
        self.assertEqual(result["counts"]["protocol_responses_received"], 2)
        self.assertEqual(result["counts"]["ffi_entries_observed"], 2)
        self.assertEqual(result["counts"]["ffi_returns_observed"], 2)

    def test_uncertain_transport_outcome_cannot_be_followed_by_another_attempt(self):
        request = b'{"request":"synthetic"}\n'
        specs = [
            ("adapter_attempt", {"command_sha256": "9" * 64, "status": "started"}, ATTEMPT_ID),
            ("worker_spawn", {"status": "spawned", "pid": 12345, "executable_sha256": "7" * 64}, ATTEMPT_ID),
            (
                "protocol_request",
                {"status": "written", "request_sha256": sha256(request), "bytes": len(request), "input_sha256": "3" * 64},
                ATTEMPT_ID,
            ),
            (
                "protocol_response",
                {
                    "status": "missing",
                    "response_sha256": None,
                    "bytes": None,
                    "exit_code": None,
                    "observation": "timeout",
                    "ffi_receipt_status": "unknown",
                },
                ATTEMPT_ID,
            ),
            ("adapter_attempt", {"command_sha256": "a" * 64, "status": "started"}, "d" * 32),
        ]

        with self.assertRaisesRegex(ReceiptValidationError, "attempt_after_incomplete_outcome"):
            verify_receipt_chain(make_receipt(specs))

    def test_terminal_report_can_record_a_committed_partial_search_after_replay_failure(self):
        request = b'{"request":"synthetic"}\n'
        specs = [
            ("adapter_attempt", {"command_sha256": "9" * 64, "status": "started"}, ATTEMPT_ID),
            ("worker_spawn", {"status": "spawned", "pid": 12345, "executable_sha256": "7" * 64}, ATTEMPT_ID),
            (
                "protocol_request",
                {"status": "written", "request_sha256": sha256(request), "bytes": len(request), "input_sha256": "3" * 64},
                ATTEMPT_ID,
            ),
            (
                "protocol_response",
                {
                    "status": "missing",
                    "response_sha256": None,
                    "bytes": None,
                    "exit_code": None,
                    "observation": "timeout",
                    "ffi_receipt_status": "unknown",
                },
                ATTEMPT_ID,
            ),
            ("report_persisted", complete_specs()[-1][1], ATTEMPT_ID),
        ]

        result = verify_receipt_chain(make_receipt(specs), REPORT_RAW)

        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["report_bytes_verified"])
        self.assertTrue(result["report_binding_verified"])
        self.assertEqual(result["attempts"][0]["protocol_response_status"], "missing")
        self.assertFalse(result["report_origin_authenticated"])

    def test_worker_exit_before_request_keeps_protocol_count_at_zero(self):
        receipt = make_receipt(
            [
                ("adapter_attempt", {"command_sha256": "9" * 64, "status": "started"}),
                ("worker_spawn", {"status": "spawned", "pid": 12345, "executable_sha256": "7" * 64}),
                ("protocol_request", {"status": "failed", "request_sha256": None, "bytes": None, "input_sha256": "3" * 64}),
            ]
        )
        result = verify_receipt_chain(receipt)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["counts"]["protocol_requests_written"], 0)
        self.assertEqual(result["report_origin_authenticated"], False)

    def test_post_request_exit_and_timeout_are_unknown_without_retry(self):
        request = b'{"request":"synthetic"}\n'
        prefix = [
            ("adapter_attempt", {"command_sha256": "9" * 64, "status": "started"}),
            ("worker_spawn", {"status": "spawned", "pid": 12345, "executable_sha256": "7" * 64}),
            ("protocol_request", {"status": "written", "request_sha256": sha256(request), "bytes": len(request), "input_sha256": "3" * 64}),
        ]
        for observation, exit_code in (("worker_exit", 101), ("worker_exit", -9), ("worker_exit", -9.0), ("timeout", None)):
            specs = prefix + [
                (
                    "protocol_response",
                    {
                        "status": "missing",
                        "response_sha256": None,
                        "bytes": None,
                        "exit_code": exit_code,
                        "observation": observation,
                        "ffi_receipt_status": "unknown",
                    },
                )
            ]
            result = verify_receipt_chain(make_receipt(specs))
            self.assertTrue(result["valid"])
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["counts"]["protocol_requests_written"], 1)
            self.assertEqual(result["counts"]["protocol_responses_received"], 0)
            self.assertEqual(result["consumption"]["status"], "unknown")

    def test_schema_integer_semantics_accept_integral_json_numbers(self):
        receipt = make_receipt(complete_specs())
        receipt["schema_version"] = 1.0
        receipt["events"][0]["sequence"] = 1.0
        receipt["events"][1]["payload"]["pid"] = 12345.0
        previous = "0" * 64
        for event in receipt["events"]:
            event["previous_sha256"] = previous
            event["event_sha256"] = event_digest(receipt["context_sha256"], event)
            previous = event["event_sha256"]

        schema = json.loads((ROOT / "schemas/w1c-execution-receipt-chain-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(receipt)
        result = verify_receipt_chain(receipt)
        self.assertTrue(result["valid"])

    def test_entered_ffi_without_return_is_reported_as_unknown(self):
        specs = complete_specs()[:4]
        specs[3] = ("ffi_entered", {"call_id": "b" * 32, "direction": "ocgcore_callback_to_host", "name": "card_reader", "ordinal": 1})
        specs.append(
            (
                "protocol_response",
                {
                    "status": "received",
                    "response_sha256": "d" * 64,
                    "bytes": 5,
                    "exit_code": 1,
                    "observation": "complete",
                    "ffi_receipt_status": "partial",
                },
            )
        )
        result = verify_receipt_chain(make_receipt(specs))
        self.assertEqual(result["observed_ffi_entries_without_return"], 1)
        self.assertIsNone(result["ffi_total_count"])
        self.assertEqual(result["counts"]["ffi_returns_observed"], 0)
        self.assertEqual(result["ffi_receipt_status"], "partial")
        self.assertEqual(result["status"], "incomplete")

    def test_outer_ffi_return_before_nested_callback_is_rejected(self):
        specs = complete_specs()[:3]
        specs.extend(
            [
                ("ffi_entered", {"call_id": "b" * 32, "direction": "host_to_ocgcore", "name": "DuelProcess", "ordinal": 1}),
                ("ffi_entered", {"call_id": "c" * 32, "direction": "ocgcore_callback_to_host", "name": "card_reader", "ordinal": 2}),
                ("ffi_returned", {"call_id": "b" * 32, "status": "returned", "result_sha256": "d" * 64}),
            ]
        )
        with self.assertRaisesRegex(ReceiptValidationError, "ffi_return_order_invalid"):
            verify_receipt_chain(make_receipt(specs))

    def test_hash_tampering_and_external_head_mismatch_fail_closed(self):
        receipt = make_receipt(complete_specs())
        tampered = copy.deepcopy(receipt)
        tampered["events"][2]["payload"]["bytes"] += 1
        with self.assertRaisesRegex(ReceiptValidationError, "event_sha256_mismatch"):
            verify_receipt_chain(tampered)
        with self.assertRaisesRegex(ReceiptValidationError, "expected_head_sha256_mismatch"):
            verify_receipt_chain(receipt, REPORT_RAW, "f" * 64)

    def test_non_string_event_type_returns_contract_error(self):
        receipt = make_receipt(complete_specs())
        receipt["events"][0]["event_type"] = []
        reseal(receipt)

        with self.assertRaisesRegex(ReceiptValidationError, "event_type_invalid"):
            verify_receipt_chain(receipt)

    def test_worker_and_protocol_input_must_match_pinned_context(self):
        worker_specs = complete_specs()
        worker_specs[1][1]["executable_sha256"] = "f" * 64
        with self.assertRaisesRegex(ReceiptValidationError, "spawned_worker_identity_mismatch"):
            verify_receipt_chain(make_receipt(worker_specs))

        request_specs = complete_specs()
        request_specs[2][1]["input_sha256"] = "e" * 64
        with self.assertRaisesRegex(ReceiptValidationError, "protocol_request_input_binding_mismatch"):
            verify_receipt_chain(make_receipt(request_specs))

    def test_duplicate_request_and_uncertain_followups_are_rejected(self):
        specs = complete_specs()
        repeated = specs[:3] + [specs[2]] + specs[3:]
        with self.assertRaisesRegex(ReceiptValidationError, "protocol_request_order_invalid"):
            verify_receipt_chain(make_receipt(repeated))

        retry = specs[:1] + [("adapter_attempt", {"command_sha256": "a" * 64, "status": "started"}, "d" * 32)]
        with self.assertRaisesRegex(ReceiptValidationError, "attempt_after_incomplete_outcome"):
            verify_receipt_chain(make_receipt(retry))

        reused_id = [
            (event_type, payload, ATTEMPT_ID)
            for event_type, payload in complete_specs()[:6]
        ]
        reused_id.append(("adapter_attempt", {"command_sha256": "a" * 64, "status": "started"}, ATTEMPT_ID))
        with self.assertRaisesRegex(ReceiptValidationError, "attempt_id_reused"):
            verify_receipt_chain(make_receipt(reused_id))

        missing_return = [item for item in specs if item[0] != "ffi_returned"]
        with self.assertRaisesRegex(ReceiptValidationError, "complete_ffi_stream_has_unreturned_call"):
            verify_receipt_chain(make_receipt(missing_return))

    def test_misbound_report_and_bad_report_hash_are_rejected(self):
        wrong_binding = json.dumps(
            {"operation_id": "f" * 32, "job_id": "2" * 32, "input_sha256": "3" * 64},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        with self.assertRaisesRegex(ReceiptValidationError, "report_operation_id_binding_mismatch"):
            verify_receipt_chain(make_receipt(complete_specs(wrong_binding)), wrong_binding)
        altered_report = REPORT_RAW.replace(b"synthetic", b"synthetix")
        with self.assertRaisesRegex(ReceiptValidationError, "report_material_sha256_mismatch"):
            verify_receipt_chain(make_receipt(complete_specs()), altered_report)

    def test_uncertain_report_persistence_does_not_become_verified(self):
        specs = complete_specs()[:-1]
        specs.append(
            (
                "report_persisted",
                {
                    "status": "unknown",
                    "report_sha256": sha256(REPORT_RAW),
                    "report_bytes": len(REPORT_RAW),
                    "readback_sha256": None,
                },
            )
        )
        result = verify_receipt_chain(make_receipt(specs))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["report_persistence_status"], "unknown")
        self.assertIsNone(result["report_bytes_verified"])
        self.assertFalse(result["report_origin_authenticated"])

    def test_known_report_write_failure_keeps_report_and_consumption_unknown(self):
        specs = complete_specs()[:-1]
        specs.append(
            (
                "report_persisted",
                {"status": "failed", "report_sha256": None, "report_bytes": None, "readback_sha256": None},
            )
        )
        result = verify_receipt_chain(make_receipt(specs))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["report_persistence_status"], "failed")
        self.assertIsNone(result["report_bytes_verified"])
        self.assertEqual(result["consumption"]["status"], "unknown")

    def test_reopen_and_cli_verification_are_deterministic(self):
        command = [
            sys.executable,
            "-m",
            "ygo_eval.execution_receipts",
            "verify",
            "--input",
            str(FIXTURE_RECEIPT),
            "--report",
            str(FIXTURE_REPORT),
        ]
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "python"), "PYTHONDONTWRITEBYTECODE": "1"}
        first_open = verify_files(FIXTURE_RECEIPT, FIXTURE_REPORT)
        second_open = verify_files(FIXTURE_RECEIPT, FIXTURE_REPORT)
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=environment, check=False)
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=environment, check=False)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(first_open, second_open)
        self.assertEqual(json.loads(first.stdout)["status"], "complete")
        self.assertTrue(json.loads(first.stdout)["report_bytes_verified"])


if __name__ == "__main__":
    unittest.main()
