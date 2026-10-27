import copy
import shutil
import unittest


class PlacementOracleTests(unittest.TestCase):
    def test_opcode18_oracle_enumerates_five_fixed_public_zones(self):
        from ygo_eval.native_tenki_placement import expected_place_responses

        raw = bytes([18, 0, 1]) + (0xFFFFE0FF).to_bytes(4, "little")
        self.assertEqual(expected_place_responses(raw), [[0, 8, i] for i in range(5)])

    def test_opcode18_oracle_rejects_nonfrozen_frames(self):
        from ygo_eval.native_tenki_placement import expected_place_responses

        raw = bytes([18, 0, 1]) + (0xFFFFE0FF).to_bytes(4, "little")
        for malformed in (
            raw[:-1],
            bytes([18, 1, 1]) + raw[3:],
            bytes([18, 0, 2]) + raw[3:],
            bytes([18, 0, 1]) + (0xFFFFE0FE).to_bytes(4, "little"),
        ):
            with self.subTest(frame=malformed), self.assertRaises(ValueError):
                expected_place_responses(malformed)

    def test_zone_zero_is_selected_by_coordinate_and_exact_wire_encoding(self):
        from ygo_eval.native_tenki_placement import select_zone_zero

        action = {
            "choice": {
                "kind": "place",
                "zones": [{"player": 0, "location": 8, "sequence": 0}],
            },
            "bytes": [0, 8, 0],
        }
        actions = [
            {"choice": {"kind": "place", "zones": [{"player": 0, "location": 8, "sequence": i}]}, "bytes": [0, 8, i]}
            for i in (4, 0, 2, 1, 3)
        ]
        prompt = {"id": 29, "player": 0, "opcode": 18, "actions": actions}
        self.assertEqual(select_zone_zero(prompt), action)
        prompt["actions"][-1] = copy.deepcopy(action)
        with self.assertRaises(ValueError):
            select_zone_zero(prompt)


class PlacementDerivationTests(unittest.TestCase):
    def test_stage_requests_follow_only_the_parent_public_menu(self):
        from ygo_eval.native_tenki_placement import derive_stage_request

        activation = {"prompt_id": 7, "player": 0, "choice": {"kind":"command","command":5,"index":0}}
        zone_raw = [18, 0, 1, 255, 224, 255, 255]
        place_actions = [
            {"choice":{"kind":"place","zones":[{"player":0,"location":8,"sequence":i}]},"bytes":[0,8,i]}
            for i in range(5)
        ]
        identity = {"identity":"a"*64}
        def parent_receipt(stage, request, result):
            return {
                "schema_version":1,"kind":"native_tenki_placement_stage","scope":"tenki-placement-probe-v1",
                "stage":stage,"successful":True,"request":request,"result":{"Ok":result},
                "validation":{"Ok":{"response_oracle_matches":True}},"diagnostic":None,
                "assets_before":identity,"assets_after":identity,"assets_unchanged":True,
                "ledger":{"consumed":stage,"completed":stage,"unknown":0,"reserved":0,"abandoned":0,"limit":6},
                "independent_replay_matches":True if stage in (4,6) else None,
                "proof_ready":False,"complete_action_coverage":False,"global_optimality":False,"native_probability_verified":False,
            }
        first = parent_receipt(1,{"decisions":[activation]},{
            "resolved_decisions":[activation],
            "events":[{"sequence":17,"opcode":18,"raw":zone_raw,"supported":True,"fields":{"prompt":{"id":17,"player":0,"opcode":18,"actions":place_actions}}}],
            "status":"decision_required","error":None,"coverage_gaps":[],
            "prompt":{"id":17,"player":0,"opcode":18,"actions":place_actions},
        })
        second = derive_stage_request(2, first)
        self.assertEqual(second["decisions"][-1], {"prompt_id":17,"player":0,"choice":{"kind":"place","zones":[{"player":0,"location":8,"sequence":0}]}})
        yes_no_raw = [13, 0, *59877851398144 .to_bytes(8, "little")]
        yes_no = parent_receipt(2,second,{
            "resolved_decisions":second["decisions"],
            "events":[{"sequence":19,"opcode":13,"raw":yes_no_raw,"supported":True,"fields":{"prompt":{"id":19,"player":0,"opcode":13,"actions":[
                {"choice":{"kind":"yes_no","yes":False},"bytes":[0,0,0,0]},
                {"choice":{"kind":"yes_no","yes":True},"bytes":[1,0,0,0]},
            ]}}}],
            "status":"decision_required","error":None,"coverage_gaps":[],
            "prompt":{"id":19,"player":0,"opcode":13,"actions":[
                {"choice":{"kind":"yes_no","yes":False},"bytes":[0,0,0,0]},
                {"choice":{"kind":"yes_no","yes":True},"bytes":[1,0,0,0]},
            ]},
        })
        false = derive_stage_request(3, yes_no)
        true = derive_stage_request(5, yes_no)
        self.assertFalse(false["decisions"][-1]["choice"]["yes"])
        self.assertTrue(true["decisions"][-1]["choice"]["yes"])
        false_receipt = parent_receipt(3,false,{"resolved_decisions":false["decisions"],"status":"decision_required","error":None,"coverage_gaps":[]})
        true_receipt = parent_receipt(5,true,{"resolved_decisions":true["decisions"],"status":"decision_required","error":None,"coverage_gaps":[]})
        self.assertEqual(derive_stage_request(4, false_receipt), false)
        self.assertEqual(derive_stage_request(6, true_receipt), true)
        false_receipt["successful"] = False
        with self.assertRaises(ValueError):
            derive_stage_request(4, false_receipt)

    def test_tampered_zone_or_yes_no_menu_is_rejected(self):
        from ygo_eval.native_tenki_placement import derive_stage_request

        identity = {"identity":"a"*64}
        parent = {
            "schema_version":1,"kind":"native_tenki_placement_stage","scope":"tenki-placement-probe-v1",
            "stage":1,"successful":True,"request":{"decisions":[]},
            "validation":{"Ok":{"response_oracle_matches":True}},"diagnostic":None,
            "assets_before":identity,"assets_after":identity,"assets_unchanged":True,
            "ledger":{"consumed":1,"completed":1,"unknown":0,"reserved":0,"abandoned":0,"limit":6},
            "proof_ready":False,"complete_action_coverage":False,"global_optimality":False,"native_probability_verified":False,
            "result":{"Ok":{
            "resolved_decisions":[],
            "events":[{"sequence":17,"opcode":18,"raw":[18,0,1,255,224,255,255],"supported":True,"fields":{"prompt":{"id":17,"player":0,"opcode":18,"actions":[
                {"choice":{"kind":"place","zones":[{"player":0,"location":8,"sequence":1}]},"bytes":[0,8,1]},
            ]}}}],
            "status":"decision_required","error":None,"coverage_gaps":[],
            "prompt":{"id":17,"player":0,"opcode":18,"actions":[
                {"choice":{"kind":"place","zones":[{"player":0,"location":8,"sequence":1}]},"bytes":[0,8,1]},
            ]},
        }}}
        with self.assertRaises(ValueError):
            derive_stage_request(2, parent)

    def test_summary_requires_all_six_resolved_calls_and_keeps_unknown_unknown(self):
        from ygo_eval.native_tenki_placement import summarize

        successful_stages = [{"stage":i,"successful":True,"receipt_sha256":f"{i:064x}","independent_replay_matches":True if i in (4,6) else None} for i in range(1,7)]
        stats = {"limit":6,"consumed":6,"completed":6,"unknown":0,"reserved":0,"abandoned":0}
        report = summarize("ctx", successful_stages, stats)
        self.assertTrue(report["successful"])
        self.assertEqual(report["old_consumed"], 26)
        self.assertEqual(report["cumulative_consumed"], 32)
        self.assertFalse(report["proof_ready"])
        self.assertFalse(report["complete_action_coverage"])
        self.assertFalse(report["global_optimality"])
        reordered = summarize("ctx", list(reversed(successful_stages)), stats)
        self.assertFalse(reordered["successful"])
        unknown = summarize("ctx", [], None, "stats_unavailable")
        self.assertIsNone(unknown["new_consumed"])
        self.assertIsNone(unknown["cumulative_consumed"])
        self.assertFalse(unknown["successful"])


class PlacementSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        from pathlib import Path
        import jsonschema
        schema_path = Path(__file__).resolve().parents[1] / "schemas/native-tenki-placement-probe.schema.json"
        cls.validator = jsonschema.Draft202012Validator(json.loads(schema_path.read_bytes()))

    def test_success_stage_requires_clean_result_assets_and_bound_replay(self):
        import copy
        identity = {"identity":"a"*64}
        stage = {
            "schema_version":1,"kind":"native_tenki_placement_stage","scope":"tenki-placement-probe-v1","context":"b"*64,
            "stage":4,"request":{"decisions":[]},"result":{"Ok":{
                "protocol_version":2,"status":"decision_required","events":[],"prompt":{},"checkpoint":{},"error":None,
                "versions":{},"loaded_scripts":{},"steps":[],"resolved_decisions":[],"coverage_gaps":[],
            }},
            "validation":{"Ok":{"pending_opcode":11,"raw_prompt_count":1,"response_oracle_matches":True,
                "expected_target_matches":True,"automatic_decisions_single_legal":True,"stage":4,
                "complete_action_coverage":False,"global_optimality":False}},
            "assets_before":identity,"assets_after":identity,"assets_unchanged":True,
            "independent_replay_matches":True,"ledger":{"limit":6,"consumed":4,"completed":4,"unknown":0,"reserved":0,"abandoned":0},
            "charged_sequence_id":"c"*64,"started_at":10,"window_valid_at_result":True,"successful":True,"diagnostic":None,
            "proof_ready":False,"complete_action_coverage":False,"global_optimality":False,"native_probability_verified":False,
        }
        self.validator.validate(stage)
        for mutate in (
            lambda value: value.update(assets_unchanged=False),
            lambda value: value.update(independent_replay_matches=False),
            lambda value: value.update(result={"Err":"worker error"}),
            lambda value: value.update(validation={"Err":"oracle mismatch"}),
            lambda value: value["validation"]["Ok"].update(response_oracle_matches=False),
            lambda value: value["validation"]["Ok"].update(pending_opcode=13),
            lambda value: value.update(result={"Ok":stage["result"]["Ok"],"Err":{}}),
            lambda value: value["ledger"].update(abandoned=1),
        ):
            forged = copy.deepcopy(stage)
            mutate(forged)
            with self.assertRaises(Exception):
                self.validator.validate(forged)


class BaselineTransitionTests(unittest.TestCase):
    def test_old_stage_one_hash_remains_pinned(self):
        from ygo_eval.native_tenki_placement import OLD_STAGE1_SHA256

        self.assertEqual(OLD_STAGE1_SHA256, "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76")

    def test_old_stage_one_hash_matches_the_sealed_pause_acceptance(self):
        import hashlib
        from pathlib import Path
        from ygo_eval.native_tenki_placement import BASELINE_RELATIVE, OLD_STAGE1_SHA256, PAUSE_ACCEPTANCE_SHA256
        from ygo_eval.prompt_probe_prepare import strict_json

        repo = Path(__file__).resolve().parents[1]
        try:
            (repo / BASELINE_RELATIVE).lstat()
        except FileNotFoundError:
            self.skipTest("historical placement baseline is not present")
        acceptance_bytes = (repo / BASELINE_RELATIVE / "pause-acceptance.json").read_bytes()
        self.assertEqual(hashlib.sha256(acceptance_bytes).hexdigest(), PAUSE_ACCEPTANCE_SHA256)
        acceptance = strict_json(acceptance_bytes)
        self.assertEqual(OLD_STAGE1_SHA256, acceptance["evidence"]["research/stage-1.json"]["sha256"])

    def test_sealed_slot_count_requires_exact_integer_four(self):
        from ygo_eval.native_tenki_placement import _has_sealed_slots

        self.assertTrue(_has_sealed_slots(4))
        for value in (True, False, 3, 4.0, "4", None):
            with self.subTest(value=value):
                self.assertFalse(_has_sealed_slots(value))

    def _payload(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_NEW_SHA256,
            TRANSITION_OLD_SHA256,
            TRANSITION_RELATIVE_PATH,
        )

        return {
            "schema_version": 1,
            "kind": "tenki_placement_baseline_transition",
            "scope": "tenki-placement-probe-v1",
            "baseline": {
                "before_sha256": "a" * 64,
                "pause_acceptance_sha256": "b" * 64,
                "paused_delivery_checkpoint_sha256": "4" * 64,
                "recovery_acceptance_sha256": "c" * 64,
                "recovery_checkpoint_sha256": "d" * 64,
                "source_archive_sha256": "e" * 64,
                "source_file_list_sha256": "f" * 64,
                "source_identity": "1" * 64,
                "source_file_count": 390,
                "historical_ledgers": [{"role": f"ledger-{n}", "path": f"data/runtime/ledger-{n}.jsonl", "sha256": f"{n:x}" * 64, "consumed": 1, "unknown": 0} for n in range(1, 7)],
                "protected_file_count": 366,
                "matched_protected_count": 365,
            },
            "migration": {
                "path": TRANSITION_RELATIVE_PATH.as_posix(),
                "old_sha256": TRANSITION_OLD_SHA256,
                "observed_sha256": TRANSITION_NEW_SHA256,
                "old_protection_check": "failed",
                "current_file_history": "unknown",
                "effective_protection_mapping": "migrated_for_this_scope",
            },
            "audit_tool": {"source_identity": "2" * 64, "module_sha256": "3" * 64},
            "claims": {
                "old_protection_check_passed": False,
                "binary_provenance_verified": False,
                "historical_reexecution_verified": False,
                "future_protection_mapping_migrated": True,
            },
            "input_sha256": {
                "before": "a" * 64,
                "pause_acceptance": "b" * 64,
                "paused_delivery_checkpoint": "4" * 64,
                "recovery_acceptance": "c" * 64,
                "recovery_checkpoint": "d" * 64,
                "protected_map": "4" * 64,
                "source_archive": "e" * 64,
                "source_file_list": "f" * 64,
                "audit_tool_source": "2" * 64,
                "audit_tool_module": "3" * 64,
                **{f"ledger_ledger-{n}": f"{n:x}" * 64 for n in range(1, 7)},
            },
        }

    def test_exact_migration_is_scoped_and_requires_recomputed_payload(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_NEW_SHA256,
            TRANSITION_OLD_SHA256,
            _seal_transition,
            _effective_protected_map,
        )

        protected = {
            "target/debug/ygo-engine-worker.exe": TRANSITION_OLD_SHA256,
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        actual = {
            "target/debug/ygo-engine-worker.exe": TRANSITION_NEW_SHA256,
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        expected = _seal_transition(self._payload())
        self.assertEqual(_effective_protected_map(protected, actual, expected, expected), actual)
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(protected, actual, None, expected)

    def test_v2_migration_accepts_only_the_new_exact_worker_hash(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_OLD_SHA256,
            TRANSITION_RELATIVE_PATH,
            TRANSITION_V2_NEW_SHA256,
            _seal_transition,
            _effective_protected_map,
        )

        payload = self._payload()
        payload["schema_version"] = 2
        payload["migration"]["observed_sha256"] = TRANSITION_V2_NEW_SHA256
        expected = _seal_transition(payload)
        protected = {
            TRANSITION_RELATIVE_PATH.as_posix(): TRANSITION_OLD_SHA256,
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        actual = {
            TRANSITION_RELATIVE_PATH.as_posix(): TRANSITION_V2_NEW_SHA256,
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        self.assertEqual(_effective_protected_map(protected, actual, expected, expected), actual)

        v1 = _seal_transition(self._payload())
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(protected, actual, v1, v1)
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(
                protected,
                {**actual, TRANSITION_RELATIVE_PATH.as_posix(): "0" * 64},
                expected,
                expected,
            )

    def test_curry_scope_allows_only_the_archived_recover_codec_delta(self):
        from ygo_eval.native_tenki_placement import (
            CURRY_SCOPE_PROTECTED_SOURCE_CHANGE,
            TRANSITION_OLD_SHA256,
            TRANSITION_V2_NEW_SHA256,
            TRANSITION_RELATIVE_PATH,
            _effective_protected_map,
            _seal_transition,
        )

        change = CURRY_SCOPE_PROTECTED_SOURCE_CHANGE
        protected = {
            TRANSITION_RELATIVE_PATH.as_posix(): TRANSITION_OLD_SHA256,
            change["path"]: change["old_sha256"],
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        actual = {
            TRANSITION_RELATIVE_PATH.as_posix(): TRANSITION_V2_NEW_SHA256,
            change["path"]: change["new_sha256"],
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        payload = self._payload()
        payload["schema_version"] = 2
        payload["migration"]["observed_sha256"] = TRANSITION_V2_NEW_SHA256
        transition = _seal_transition(payload)

        self.assertEqual(
            _effective_protected_map(protected, actual, transition, transition,
                                     protection_scope=change["scope"]),
            actual,
        )
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(protected, actual, transition, transition)
        forged = dict(actual, **{change["path"]: "0" * 64})
        with self.assertRaisesRegex(ValueError, "protected_source_change_hash_mismatch"):
            _effective_protected_map(
                protected, forged, transition, transition,
                protection_scope=change["scope"],
            )
        already_migrated_worker = {
            **protected,
            TRANSITION_RELATIVE_PATH.as_posix(): TRANSITION_V2_NEW_SHA256,
        }
        same_worker_actual = {
            **actual,
            TRANSITION_RELATIVE_PATH.as_posix(): TRANSITION_V2_NEW_SHA256,
        }
        with self.assertRaisesRegex(ValueError, "baseline_transition_input_mismatch"):
            _effective_protected_map(
                already_migrated_worker,
                same_worker_actual,
                None,
                None,
                protection_scope=change["scope"],
            )
        with self.assertRaisesRegex(ValueError, "protected_source_scope_unsupported"):
            _effective_protected_map(
                protected, actual, transition, transition,
                protection_scope="another-scope",
            )

    def test_strict_audit_rejects_protected_drift_before_old_runner_checks(self):
        from pathlib import Path
        from unittest.mock import patch
        import ygo_eval.native_tenki_placement as placement

        repo = Path(__file__).resolve().parents[1]
        baseline = repo / placement.BASELINE_RELATIVE
        try:
            baseline.lstat()
        except FileNotFoundError:
            self.skipTest("historical placement baseline is not present")
        with (
            patch.object(placement.subprocess, "run", side_effect=AssertionError("must reject before runner")) as run,
            patch.object(placement, "_transition_payload_from_current", side_effect=AssertionError("strict mode must not construct migration payload")) as capture,
        ):
            with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
                placement.audit_baseline(baseline, repo)
        run.assert_not_called()
        capture.assert_not_called()

    def test_strict_map_accepts_only_exact_unchanged_hashes(self):
        from ygo_eval.native_tenki_placement import _effective_protected_map

        protected = {f"protected/{index}.bin": f"{index:064x}" for index in range(1, 367)}
        self.assertEqual(_effective_protected_map(protected, dict(protected), None, None), protected)
        changed = dict(protected)
        changed["protected/366.bin"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(protected, changed, None, None)

    def test_transition_rejects_second_mismatch_and_forged_record(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_NEW_SHA256,
            TRANSITION_OLD_SHA256,
            _seal_transition,
            _effective_protected_map,
        )

        protected = {
            "target/debug/ygo-engine-worker.exe": TRANSITION_OLD_SHA256,
            "data/runtime/old-ledger.jsonl": "a" * 64,
        }
        expected = _seal_transition(self._payload())
        actual = {
            "target/debug/ygo-engine-worker.exe": TRANSITION_NEW_SHA256,
            "data/runtime/old-ledger.jsonl": "b" * 64,
        }
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(protected, actual, expected, expected)
        forged = copy.deepcopy(expected)
        forged["migration"]["observed_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "baseline_transition_input_mismatch"):
            _effective_protected_map(protected, {
                "target/debug/ygo-engine-worker.exe": TRANSITION_NEW_SHA256,
                "data/runtime/old-ledger.jsonl": "a" * 64,
            }, forged, expected)

    def test_transition_rejects_unapproved_single_worker_hash(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_OLD_SHA256,
            _seal_transition,
            _effective_protected_map,
        )

        protected = {"target/debug/ygo-engine-worker.exe": TRANSITION_OLD_SHA256}
        expected = _seal_transition(self._payload())
        with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
            _effective_protected_map(
                protected,
                {"target/debug/ygo-engine-worker.exe": "9" * 64},
                expected,
                expected,
            )

    def test_transition_document_rejects_duplicate_json_keys(self):
        from ygo_eval.prompt_probe_prepare import strict_json

        with self.assertRaises(ValueError):
            strict_json(b'{"scope":"one","scope":"two"}')

    def test_transition_capture_selects_fixed_hash_for_report_version(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_V1_NEW_SHA256,
            TRANSITION_V2_NEW_SHA256,
            _transition_target_hash,
        )

        self.assertEqual(_transition_target_hash(1), TRANSITION_V1_NEW_SHA256)
        self.assertEqual(_transition_target_hash(2), TRANSITION_V2_NEW_SHA256)
        for version in (0, 3, True, "2"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                _transition_target_hash(version)

    def test_capture_rejects_input_drift_between_two_passes(self):
        from unittest.mock import patch
        import ygo_eval.native_tenki_placement as placement

        first = self._payload()
        second = copy.deepcopy(first)
        second["baseline"]["before_sha256"] = "9" * 64
        with patch.object(placement, "_transition_capture_once", side_effect=[first, second]):
            with self.assertRaisesRegex(ValueError, "baseline_transition_inputs_changed_during_capture"):
                placement._transition_payload_from_current(None, None)

    def test_historical_tool_override_changes_only_tool_identity_and_hashes(self):
        from ygo_eval.native_tenki_placement import _transition_payload_with_tool_override

        current = self._payload()
        override = copy.deepcopy(current)
        override["audit_tool"] = {"source_identity": "9" * 64, "module_sha256": "8" * 64}
        override["input_sha256"]["audit_tool_source"] = "9" * 64
        override["input_sha256"]["audit_tool_module"] = "8" * 64
        self.assertEqual(_transition_payload_with_tool_override(current, override), override)

        forged = copy.deepcopy(override)
        forged["baseline"]["before_sha256"] = "7" * 64
        with self.assertRaisesRegex(ValueError, "baseline_transition_override_invalid"):
            _transition_payload_with_tool_override(current, forged)
        malformed = copy.deepcopy(override)
        malformed["audit_tool"]["module_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "baseline_transition_override_invalid"):
            _transition_payload_with_tool_override(current, malformed)

    def test_effective_map_uses_summaries_without_path_and_keeps_migrated_hash(self):
        from ygo_eval.native_tenki_placement import (
            TRANSITION_NEW_SHA256,
            _runtime_protected_map,
        )

        protected = {"target/debug/ygo-engine-worker.exe": TRANSITION_NEW_SHA256}
        summaries = [
            {"role": f"ledger-{n}", "sha256": f"{n:x}" * 64, "consumed": n, "unknown": 0}
            for n in range(1, 7)
        ]
        self.assertEqual(_runtime_protected_map(protected, summaries), protected)

    def test_transition_output_is_exclusive(self):
        from pathlib import Path
        from ygo_eval.native_tenki_placement import _require_new_transition_output

        path = Path(__file__).resolve().parent / ".baseline-transition-output-test.json"
        self.assertFalse(path.exists())
        try:
            _require_new_transition_output(path)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "baseline_transition_output_exists"):
                _require_new_transition_output(path)
        finally:
            path.unlink(missing_ok=True)

    def test_baseline_transition_schema_is_versioned_and_narrow(self):
        import json
        from pathlib import Path
        import jsonschema

        path = Path(__file__).resolve().parents[1] / "schemas/tenki-placement-baseline-transition.schema.json"
        schema = json.loads(path.read_bytes())
        validator = jsonschema.Draft202012Validator(schema)
        from ygo_eval.native_tenki_placement import _seal_transition

        report = _seal_transition(self._payload())
        validator.validate(report)
        report["migration"]["path"] = "target/debug/other.exe"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(report)

    def test_v2_schema_is_distinct_and_binds_only_the_current_hash(self):
        import copy
        import json
        from pathlib import Path
        import jsonschema
        from ygo_eval.native_tenki_placement import TRANSITION_V2_NEW_SHA256, _seal_transition

        payload = self._payload()
        payload["schema_version"] = 2
        payload["migration"]["observed_sha256"] = TRANSITION_V2_NEW_SHA256
        report = _seal_transition(payload)
        schema_dir = Path(__file__).resolve().parents[1] / "schemas"
        v1 = json.loads((schema_dir / "tenki-placement-baseline-transition.schema.json").read_bytes())
        schema = json.loads((schema_dir / "tenki-placement-baseline-transition-v2.schema.json").read_bytes())
        self.assertEqual(v1["properties"]["schema_version"]["const"], 1)
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(report)
        for mutate in (
            lambda value: value.update(schema_version=1),
            lambda value: value["migration"].update(observed_sha256="be6aae6ec2d03ae3293f2954fb84be211483bd9c5b57e4ac3b546b7239db9eba"),
        ):
            forged = copy.deepcopy(report)
            mutate(forged)
            with self.assertRaises(jsonschema.ValidationError):
                validator.validate(forged)

    def test_transition_cli_advertises_explicit_version_selection(self):
        import subprocess
        import sys
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "-m", "ygo_eval.research", "prepare-tenki-baseline-transition", "--help"],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--report-version", completed.stdout)

class PlacementSchemaRemainingTests(PlacementSchemaTests):
    def test_audit_snapshot_rejects_protected_input_or_source_drift(self):
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import _verify_audit_snapshot, sha

        path = Path(__file__).resolve().parent / (".tenki-audit-snapshot-" + uuid.uuid4().hex)
        path.write_bytes(b"original")
        try:
            with patch("ygo_eval.native_tenki_placement.stable_source", return_value={"identity": "a" * 64}):
                _verify_audit_snapshot({path: sha(path)}, {"identity": "a" * 64}, path.parent)
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "baseline_input_changed_during_audit"):
                    _verify_audit_snapshot({path: "0" * 64}, {"identity": "a" * 64}, path.parent)
                with self.assertRaisesRegex(ValueError, "baseline_source_changed_during_audit"):
                    _verify_audit_snapshot({path: sha(path)}, {"identity": "b" * 64}, path.parent)
        finally:
            path.unlink()

    def test_failure_stage_and_unknown_summary_remain_representable(self):
        import copy
        from ygo_eval.native_tenki_placement import summarize
        identity = {"identity":"a"*64}
        failure = {
            "schema_version":1,"kind":"native_tenki_placement_stage","scope":"tenki-placement-probe-v1","context":"b"*64,
            "stage":1,"request":{"decisions":[]},"result":{"Err":{"code":"worker","stage":"run","message":"failed"}},
            "validation":{"Err":"engine_or_journal_error"},"assets_before":identity,"assets_after":None,"assets_unchanged":False,
            "independent_replay_matches":None,"ledger":{"limit":6,"consumed":1,"completed":1,"unknown":0,"reserved":0,"abandoned":0},
            "charged_sequence_id":"c"*64,"started_at":10,"window_valid_at_result":True,"successful":False,"diagnostic":"engine_or_journal_error",
            "proof_ready":False,"complete_action_coverage":False,"global_optimality":False,"native_probability_verified":False,
        }
        self.validator.validate(failure)
        unknown = summarize("b"*64, [], None, "stats_unavailable")
        self.validator.validate(unknown)
        self.assertIsNone(unknown["new_consumed"])
        self.assertIsNone(unknown["cumulative_consumed"])

    def test_expired_prepare_only_is_rejected_without_creating_request(self):
        import time
        import uuid
        from pathlib import Path
        from ygo_eval.native_tenki_placement import run_stages

        temporary = Path(__file__).resolve().parent / (".tenki-expired-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        try:
            manifest = {"context": "b" * 64, "started_at": int(time.time()) - 7201}
            with self.assertRaisesRegex(ValueError, "experiment_window_expired"):
                run_stages("unused-runner", output, manifest, {"decisions": []}, {}, lambda: None, prepare_only=True)
        finally:
            shutil.rmtree(temporary)

    def test_unexpired_prepare_only_saves_only_stage_one_without_runner(self):
        import time
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import run_stages

        temporary = Path(__file__).resolve().parent / (".tenki-prepare-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        try:
            manifest = {"context": "b" * 64, "started_at": int(time.time())}
            with patch("ygo_eval.native_tenki_placement.subprocess.run") as run:
                report = run_stages("unused-runner", output, manifest, {"decisions": []}, {}, lambda: None, prepare_only=True)
            run.assert_not_called()
            self.assertTrue(report["prepared"])
            self.assertEqual(report["native_calls"], 0)
            self.assertTrue((output / "stage-1-request.json").is_file())
            self.assertTrue((output / "stage-1-input.json").is_file())
            self.assertFalse((output / "stage-2-request.json").exists())
            self.assertFalse((output / "calls.jsonl").exists())
        finally:
            shutil.rmtree(temporary)

    def test_expired_saved_receipt_runs_only_readonly_verification(self):
        import json
        import time
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import SCOPE, run_stages
        from ygo_eval.native_tenki_placement import sha

        temporary = Path(__file__).resolve().parent / (".tenki-expired-receipt-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"frozen runner")
        calls = []
        try:
            context = "b" * 64
            request = {"decisions": []}
            manifest = {"context": context, "started_at": int(time.time()) - 7201, "runner_sha256": sha(runner)}
            (output / "calls.jsonl").write_bytes(b"")
            receipt = {
                "schema_version": 1,
                "kind": "native_tenki_placement_stage",
                "scope": SCOPE,
                "context": context,
                "stage": 1,
                "request": request,
                "successful": False,
                "diagnostic": "engine_or_journal_error",
                "ledger": {"consumed": 1, "completed": 1, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": 6},
                "charged_sequence_id": "c" * 64,
                "window_valid_at_result": True,
                "independent_replay_matches": None,
                "proof_ready": False,
                "complete_action_coverage": False,
                "global_optimality": False,
                "native_probability_verified": False,
            }
            (output / "stage-1.json").write_text(json.dumps(receipt), encoding="utf-8")
            def run_stub(command, **kwargs):
                calls.append(command)
                if command[-1] == "--verify-recorded":
                    return type("Result", (), {"returncode": 1, "stdout": json.dumps({
                        "verified_recorded": True, "native_calls": 0, "successful": False,
                        "ledger": {"consumed": 1, "completed": 1, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": 6},
                    }).encode()})()
                return type("Result", (), {"returncode": 0, "stdout": json.dumps({
                    "native_calls": 0,
                    "ledger": {"consumed": 1, "completed": 1, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": 6},
                }).encode()})()
            with patch("ygo_eval.native_tenki_placement.subprocess.run", side_effect=run_stub):
                report = run_stages(runner, output, manifest, request, {}, lambda: None)
            self.assertEqual([command[-1] for command in calls], ["--verify-recorded", "--stats"])
            self.assertFalse(report["successful"])
            self.assertEqual(report["new_consumed"], 1)
        finally:
            shutil.rmtree(temporary)

    def test_preflight_failure_is_saved_as_summary_without_charging(self):
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import run_stages

        temporary = Path(__file__).resolve().parent / (".tenki-preflight-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        try:
            manifest = {"context": "b" * 64, "started_at": 10}
            def frozen_inputs_changed():
                raise ValueError("workspace_source_changed")
            with patch("ygo_eval.native_tenki_placement.subprocess.run") as run:
                report = run_stages("unused-runner", output, manifest, {"decisions": []}, {}, frozen_inputs_changed)
            run.assert_not_called()
            self.assertFalse(report["successful"])
            self.assertEqual(report["diagnostic"], "frozen_input_changed")
            self.assertIsNone(report["new_consumed"])
            self.assertIsNone(report["ledger"])
            self.assertTrue((output / "summary.json").is_file())
        finally:
            shutil.rmtree(temporary)

    def test_preflight_failure_reads_stats_from_last_saved_input(self):
        import json
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import sha, run_stages
        from ygo_data.identity import canonical

        temporary = Path(__file__).resolve().parent / (".tenki-stats-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"frozen runner")
        calls = []
        try:
            (output / "calls.jsonl").write_bytes(b"ledger-present")
            saved_input = output / "stage-1-input.json"
            request = {"decisions": []}
            invocation = {
                "context": "b" * 64,
                "ledger": str(output / "calls.jsonl"),
                "output": str(output / "stage-1.json"),
                "stage": 1,
                "request": request,
                "expected_identity": {},
                "started_at": 10,
            }
            saved_input.write_bytes(canonical(invocation))
            (output / "stage-1-request.json").write_bytes(canonical(request))
            (output / "stage-1-input-seal.json").write_bytes(canonical({
                "schema_version": 1,
                "kind": "tenki_placement_stage_input_seal",
                "context": "b" * 64,
                "stage": 1,
                "input_sha256": sha(saved_input),
            }))
            manifest = {"context": "b" * 64, "started_at": 10, "runner_sha256": sha(runner)}
            def frozen_inputs_changed():
                raise ValueError("workspace_source_changed")
            def run_stub(command, **kwargs):
                calls.append(command)
                return type("Result", (), {"returncode": 0, "stdout": json.dumps({
                    "native_calls": 0,
                    "ledger": {"consumed": 2, "completed": 2, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": 6},
                }).encode()})()
            with patch("ygo_eval.native_tenki_placement.subprocess.run", side_effect=run_stub):
                report = run_stages(runner, output, manifest, {"decisions": []}, {}, frozen_inputs_changed)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][-1], "--stats")
            self.assertEqual(Path(calls[0][1]), saved_input)
            self.assertEqual(report["new_consumed"], 2)
            self.assertFalse(report["successful"])
        finally:
            shutil.rmtree(temporary)

    def test_preflight_failure_does_not_run_replaced_runner_for_stats(self):
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import run_stages

        temporary = Path(__file__).resolve().parent / (".tenki-replaced-runner-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"replacement runner")
        try:
            (output / "calls.jsonl").write_bytes(b"ledger-present")
            saved_input = output / "stage-1-input.json"
            saved_input.write_text('{"stage":1}', encoding="utf-8")
            (output / "stage-1-input-seal.json").write_text("{}", encoding="utf-8")
            manifest = {"context": "b" * 64, "started_at": 10, "runner_sha256": "1" * 64}

            def frozen_inputs_changed():
                raise ValueError("frozen_build_or_identity_input_changed")

            with patch("ygo_eval.native_tenki_placement.subprocess.run") as run:
                report = run_stages(runner, output, manifest, {"decisions": []}, {}, frozen_inputs_changed)

            run.assert_not_called()
            self.assertIsNone(report["new_consumed"])
            self.assertEqual(report["diagnostic"], "frozen_input_changed")
        finally:
            shutil.rmtree(temporary)

    def test_preflight_failure_does_not_run_stats_for_changed_saved_input(self):
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_data.identity import canonical
        from ygo_eval.native_tenki_placement import run_stages, sha

        temporary = Path(__file__).resolve().parent / (".tenki-changed-input-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"frozen runner")
        try:
            (output / "calls.jsonl").write_bytes(b"ledger-present")
            request = {"decisions": []}
            invocation = {
                "context": "b" * 64,
                "ledger": str(output / "calls.jsonl"),
                "output": str(output / "stage-1.json"),
                "stage": 1,
                "request": request,
                "expected_identity": {},
                "started_at": 10,
            }
            input_path = output / "stage-1-input.json"
            input_path.write_bytes(canonical(invocation))
            (output / "stage-1-request.json").write_bytes(canonical(request))
            (output / "stage-1-input-seal.json").write_bytes(canonical({
                "schema_version": 1, "kind": "tenki_placement_stage_input_seal",
                "context": "b" * 64, "stage": 1, "input_sha256": sha(input_path),
            }))
            input_path.write_bytes(canonical({**invocation, "request": {"decisions": [{"tampered": True}]}}))
            manifest = {"context": "b" * 64, "started_at": 10, "runner_sha256": sha(runner)}

            def frozen_inputs_changed():
                raise ValueError("workspace_source_changed")

            with patch("ygo_eval.native_tenki_placement.subprocess.run") as run:
                report = run_stages(runner, output, manifest, request, {}, frozen_inputs_changed)

            run.assert_not_called()
            self.assertIsNone(report["new_consumed"])
        finally:
            shutil.rmtree(temporary)

    def test_runner_drift_after_partial_stats_makes_consumption_unknown(self):
        import json
        import time
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import run_stages, sha

        temporary = Path(__file__).resolve().parent / (".tenki-stats-drift-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"trusted runner")
        calls = []
        check_count = 0
        try:
            manifest = {"context": "b" * 64, "started_at": int(time.time()), "runner_sha256": sha(runner)}

            def unchanged():
                nonlocal check_count
                check_count += 1
                if check_count > 1:
                    raise ValueError("frozen_build_or_identity_input_changed")

            def run_stub(command, **kwargs):
                calls.append(command)
                if command[-1] != "--stats":
                    (output / "calls.jsonl").write_bytes(b"possibly charged")
                    runner.write_bytes(b"replaced runner")
                return type("Result", (), {"returncode": 0, "stdout": json.dumps({
                    "native_calls": 1,
                    "ledger": {"consumed": 1, "completed": 1, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": 6},
                }).encode()})()

            with patch("ygo_eval.native_tenki_placement.subprocess.run", side_effect=run_stub):
                report = run_stages(runner, output, manifest, {"decisions": []}, {}, unchanged)

            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0][-1], "--stats")
            self.assertIsNone(report["new_consumed"])
            self.assertIsNone(report["ledger"])
            self.assertEqual(report["diagnostic"], "frozen_input_changed")
        finally:
            shutil.rmtree(temporary)

    def test_expired_missing_receipt_only_reads_stats_and_does_not_charge(self):
        import json
        import time
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.native_tenki_placement import sha, run_stages
        from ygo_data.identity import canonical

        temporary = Path(__file__).resolve().parent / (".tenki-expired-missing-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"frozen runner")
        calls = []
        try:
            (output / "calls.jsonl").write_bytes(b"ledger-present")
            manifest = {"context": "b" * 64, "started_at": int(time.time()) - 7201, "runner_sha256": sha(runner)}

            def run_stub(command, **kwargs):
                calls.append(command)
                return type("Result", (), {"returncode": 0, "stdout": json.dumps({
                    "native_calls": 0,
                    "ledger": {"consumed": 0, "completed": 0, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": 6},
                }).encode()})()

            with patch("ygo_eval.native_tenki_placement.subprocess.run", side_effect=run_stub):
                report = run_stages(runner, output, manifest, {"decisions": []}, {}, lambda: None)

            self.assertEqual([command[-1] for command in calls], ["--stats"])
            self.assertFalse((output / "stage-1.json").exists())
            self.assertEqual(report["new_consumed"], 0)
            self.assertEqual(report["diagnostic"], "window_exhausted_before_new_call")
        finally:
            shutil.rmtree(temporary)

    def test_all_six_saved_receipts_after_expiry_use_only_readonly_verification(self):
        import json
        import time
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from ygo_data.identity import canonical
        from ygo_eval.native_tenki_placement import (
            LIMIT, SCOPE, YES_NO_DESCRIPTION, derive_stage_request, run_stages, sha,
        )

        temporary = Path(__file__).resolve().parent / (".tenki-six-recovery-" + uuid.uuid4().hex)
        output = temporary / "research"
        temporary.mkdir()
        output.mkdir()
        runner = temporary / "runner.exe"
        runner.write_bytes(b"frozen runner")
        calls = []
        context = "b" * 64
        started_at = int(time.time()) - 7201
        identity = {"identity": "a" * 64}
        request1 = {"decisions": []}
        place_prompt = {
            "id": 31, "opcode": 18, "player": 0,
            "actions": [
                {"choice": {"kind": "place", "zones": [{"player": 0, "location": 8, "sequence": sequence}]}, "bytes": [0, 8, sequence]}
                for sequence in range(5)
            ],
        }
        raw18 = [18, 0, 1, 255, 224, 255, 255]
        yes_no_prompt = {
            "id": 32, "opcode": 13, "player": 0,
            "actions": [
                {"choice": {"kind": "yes_no", "yes": False}, "bytes": [0, 0, 0, 0]},
                {"choice": {"kind": "yes_no", "yes": True}, "bytes": [1, 0, 0, 0]},
            ],
        }
        raw13 = [13, 0, *YES_NO_DESCRIPTION.to_bytes(8, "little")]

        def result(request, prompt=None, raw=None):
            events = [] if prompt is None else [{
                "sequence": prompt["id"], "opcode": prompt["opcode"], "raw": raw,
                "supported": True, "fields": {"prompt": prompt},
            }]
            return {"Ok": {
                "status": "decision_required", "error": None, "coverage_gaps": [],
                "resolved_decisions": request["decisions"], "prompt": prompt, "events": events,
            }}

        requests = {1: request1}
        receipt_data = {}
        first_result = result(request1, place_prompt, raw18)
        for stage in range(1, LIMIT + 1):
            if stage == 1:
                request = request1
                stage_result = first_result
            elif stage == 2:
                request = derive_stage_request(stage, receipt_data[1])
                stage_result = result(request, yes_no_prompt, raw13)
            elif stage in (3, 4):
                request = derive_stage_request(stage, receipt_data[stage - 1])
                stage_result = result(request)
            elif stage == 5:
                request = derive_stage_request(stage, receipt_data[2])
                stage_result = result(request)
            else:
                request = derive_stage_request(stage, receipt_data[5])
                stage_result = result(request)
            requests[stage] = request
            receipt_data[stage] = {
                "schema_version": 1, "kind": "native_tenki_placement_stage", "scope": SCOPE,
                "context": context, "stage": stage, "request": request,
                "result": stage_result, "validation": {"Ok": {"response_oracle_matches": True}},
                "assets_before": identity, "assets_after": identity, "assets_unchanged": True,
                "independent_replay_matches": True if stage in (4, 6) else None,
                "ledger": {"consumed": stage, "completed": stage, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": LIMIT},
                "charged_sequence_id": f"{stage:064x}", "started_at": started_at,
                "window_valid_at_result": True, "successful": True, "diagnostic": None,
                "proof_ready": False, "complete_action_coverage": False,
                "global_optimality": False, "native_probability_verified": False,
            }
            (output / f"stage-{stage}.json").write_bytes(canonical(receipt_data[stage]))

        try:
            (output / "calls.jsonl").write_bytes(b"six completed calls")
            manifest = {"context": context, "started_at": started_at, "runner_sha256": sha(runner)}

            def run_stub(command, **kwargs):
                calls.append(command)
                return type("Result", (), {"returncode": 0, "stdout": json.dumps({
                    "verified_recorded": True, "native_calls": 0, "successful": True,
                    "ledger": {"consumed": 6, "completed": 6, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": LIMIT},
                }).encode()})()

            with patch("ygo_eval.native_tenki_placement.subprocess.run", side_effect=run_stub):
                report = run_stages(runner, output, manifest, request1, identity, lambda: None)

            self.assertEqual(len(calls), 6)
            self.assertTrue(all(command[-1] == "--verify-recorded" for command in calls))
            self.assertTrue(report["successful"])
            self.assertEqual(report["new_consumed"], 6)
        finally:
            shutil.rmtree(temporary)

    def test_summary_success_requires_all_six_ordered_successes_and_replays(self):
        import copy
        from ygo_eval.native_tenki_placement import summarize
        stages = [{"stage":n,"successful":True,"receipt_sha256":f"{n:064x}","independent_replay_matches":True if n in (4,6) else None} for n in range(1,7)]
        stats = {"limit":6,"consumed":6,"completed":6,"unknown":0,"reserved":0,"abandoned":0}
        summary = summarize("b"*64, stages, stats)
        self.validator.validate(summary)
        for mutate in (
            lambda value: value["stages"].reverse(),
            lambda value: value["stages"][2].update(successful=False),
            lambda value: value["stages"][5].update(independent_replay_matches=False),
        ):
            forged = copy.deepcopy(summary)
            mutate(forged)
            with self.assertRaises(Exception):
                self.validator.validate(forged)


if __name__ == "__main__":
    unittest.main()
