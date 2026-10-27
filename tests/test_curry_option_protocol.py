import unittest

from ygo_eval.curry_option_protocol import validate_curry_option_result


DESCRIPTIONS = (60_895_602_409_472, 60_895_602_409_473)


def _event(sequence, raw, fields):
    return {
        "sequence": sequence,
        "opcode": raw[0],
        "supported": True,
        "raw": list(raw),
        "fields": fields,
    }


def _option_event(sequence=7):
    raw = bytes([14, 0, 2]) + b"".join(value.to_bytes(8, "little") for value in DESCRIPTIONS)
    prompt = {
        "id": sequence,
        "opcode": 14,
        "player": 0,
        "actions": [
            {"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]},
            {"choice": {"kind": "option", "index": 1}, "bytes": [1, 0, 0, 0]},
        ],
    }
    return _event(sequence, raw, {"prompt": prompt})


def _recover_event(player, amount=200, sequence=8):
    raw = bytes([92, player]) + amount.to_bytes(4, "little")
    return _event(sequence, raw, {"player": player, "amount": amount})


def _decision(option, prompt_id=7):
    return {"prompt_id": prompt_id, "player": 0,
            "choice": {"kind": "option", "index": option}}


def _checkpoint(lp):
    return {"lp": lp}


def _empty_chain_event(sequence=9, *, spec=0, forced=0):
    # opcode, player, protocol spec byte, forced byte, two u32 timing values,
    # and a u32 candidate count.
    raw = bytes([16, 1, spec, forced]) + bytes(8) + bytes(4)
    return _event(sequence, raw, {})


class CurryOptionProtocolTests(unittest.TestCase):
    def test_validates_option_zero_recover_and_life_points(self):
        prompt = _option_event()
        recover = _recover_event(0)
        audit = validate_curry_option_result(
            prompt, _decision(0), [prompt, recover], _checkpoint([8200, 8000])
        )
        self.assertEqual(audit["selected_option"], 0)
        self.assertEqual(audit["response_bytes"], [0, 0, 0, 0])
        self.assertEqual(audit["recover_player"], 0)
        self.assertEqual(audit["recover_amount"], 200)

    def test_validates_option_one_recover_and_life_points(self):
        prompt = _option_event()
        recover = _recover_event(1)
        audit = validate_curry_option_result(
            prompt, _decision(1), [prompt, recover], _checkpoint([8000, 8200])
        )
        self.assertEqual(audit["selected_option"], 1)
        self.assertEqual(audit["response_bytes"], [1, 0, 0, 0])
        self.assertEqual(audit["recover_player"], 1)

    def test_rejects_truncated_or_trailing_opcode14_frame(self):
        for raw in (_option_event()["raw"][:-1], _option_event()["raw"] + [0]):
            frame = _option_event()
            frame["raw"] = raw
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                validate_curry_option_result(
                    frame, _decision(0), [frame, _recover_event(0)], _checkpoint([8200, 8000])
                )

    def test_rejects_reordered_descriptions(self):
        frame = _option_event()
        frame["raw"] = [14, 0, 2] + list(DESCRIPTIONS[1].to_bytes(8, "little")) + list(DESCRIPTIONS[0].to_bytes(8, "little"))
        with self.assertRaises(ValueError):
            validate_curry_option_result(
                frame, _decision(0), [frame, _recover_event(0)], _checkpoint([8200, 8000])
            )

    def test_rejects_duplicate_or_incomplete_response_set(self):
        for actions in (
            [
                {"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]},
                {"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]},
            ],
            [{"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]}],
        ):
            frame = _option_event()
            frame["fields"]["prompt"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                validate_curry_option_result(
                    frame, _decision(0), [frame, _recover_event(0)], _checkpoint([8200, 8000])
                )

    def test_rejects_wrong_option_decision(self):
        decision = _decision(1)
        decision["choice"]["index"] = 2
        with self.assertRaises(ValueError):
            validate_curry_option_result(
                _option_event(), decision, [_option_event(), _recover_event(0)], _checkpoint([8200, 8000])
            )

    def test_rejects_wrong_recover_player_or_amount(self):
        for recover in (_recover_event(1), _recover_event(2), _recover_event(0, 199)):
            with self.subTest(recover=recover), self.assertRaises(ValueError):
                validate_curry_option_result(
                    _option_event(), _decision(0), [_option_event(), recover], _checkpoint([8200, 8000])
                )

    def test_rejects_truncated_or_trailing_recover_frame(self):
        for raw in (_recover_event(0)["raw"][:-1], _recover_event(0)["raw"] + [0]):
            recover = _recover_event(0)
            recover["raw"] = raw
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                validate_curry_option_result(
                    _option_event(), _decision(0), [_option_event(), recover], _checkpoint([8200, 8000])
                )

    def test_rejects_reordered_option_responses(self):
        frame = _option_event()
        frame["fields"]["prompt"]["actions"].reverse()
        with self.assertRaises(ValueError):
            validate_curry_option_result(
                frame, _decision(0), [frame, _recover_event(0)], _checkpoint([8200, 8000])
            )

    def test_rejects_missing_or_duplicate_recover(self):
        prompt = _option_event()
        recover = _recover_event(0)
        for events in ([prompt], [prompt, recover, _recover_event(0, sequence=9)]):
            with self.subTest(count=sum(event["opcode"] == 92 for event in events)), self.assertRaises(ValueError):
                validate_curry_option_result(prompt, _decision(0), events, _checkpoint([8200, 8000]))

    def test_rejects_checkpoint_life_point_mismatch(self):
        with self.assertRaises(ValueError):
            validate_curry_option_result(
                _option_event(), _decision(0), [_option_event(), _recover_event(0)], _checkpoint([8000, 8200])
            )

    def test_rejects_nonempty_or_forced_chain_prompt(self):
        prompt = _option_event()
        # MSG_SELECT_CHAIN: player, forced flag, two u32 fields, candidate count.
        for raw in (
            bytes([16, 1, 0, 0]) + bytes(8) + (1).to_bytes(4, "little"),
            bytes([16, 1, 0, 1]) + bytes(8) + bytes(4),
        ):
            chain = _event(9, raw, {})
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_curry_option_result(
                    prompt, _decision(0), [prompt, _recover_event(0), chain], _checkpoint([8200, 8000])
                )

    def test_accepts_an_empty_nonforced_chain_window(self):
        prompt = _option_event()
        chain = _empty_chain_event(spec=0)
        audit = validate_curry_option_result(
            prompt, _decision(0), [prompt, _recover_event(0), chain], _checkpoint([8200, 8000])
        )
        self.assertEqual(audit["recover_amount"], 200)

    def test_rejects_nonzero_special_chain_count(self):
        prompt = _option_event()
        chain = _empty_chain_event(spec=1)
        with self.assertRaises(ValueError):
            validate_curry_option_result(
                prompt, _decision(0), [prompt, _recover_event(0), chain], _checkpoint([8200, 8000])
            )

    def test_rejects_recover_after_or_out_of_order_from_pending_prompt(self):
        prompt = _option_event(sequence=12)
        recover = _recover_event(0, sequence=20)
        pending = _event(14, bytes([11]), {})
        with self.assertRaises(ValueError):
            validate_curry_option_result(
                prompt,
                _decision(0, prompt_id=12),
                [prompt, recover, pending],
                _checkpoint([8200, 8000]),
                pending_event=pending,
            )

    def test_rejects_truncated_or_inconsistent_chain_frame(self):
        prompt = _option_event()
        valid = _empty_chain_event()
        for raw in (valid["raw"][:-1], valid["raw"] + [0]):
            chain = _event(9, raw, {})
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                validate_curry_option_result(
                    prompt, _decision(0), [prompt, _recover_event(0), chain], _checkpoint([8200, 8000])
                )


if __name__ == "__main__":
    unittest.main()
