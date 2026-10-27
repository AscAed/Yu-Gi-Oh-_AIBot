import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_research import sample
from ygo_eval.prompt_probe_logic import derive_candidates, select_unique_activation, response_fixtures


def base():
    case = sample()
    request = json.loads((Path(__file__).parent / 'fixtures/rabbit.request.json').read_text())
    case.update(deck=request['deck'], opening_hand=request['opening_hand'])
    case['information']['opponent_resources'] = {'main': copy.deepcopy(case['deck']['main']), 'hand': []}
    return case


def prompt(index=3):
    return {'player': 0, 'opcode': 11, 'actions': [{'choice': {'kind': 'command', 'command': 5, 'index': index}, 'card_ids': [57103969], 'bytes': list(((index << 16) | 5).to_bytes(4, 'little'))}]}


class PromptProbeLogicTests(unittest.TestCase):
    def test_derivatives_are_fixed_independent_unqualified_cases(self):
        source = base(); before = copy.deepcopy(source)
        candidates = derive_candidates(source)
        self.assertEqual(source, before)
        self.assertEqual([v['target']['opcode'] for v in candidates], [13, 14, 24])
        self.assertEqual([v['case']['case_id'] for v in candidates], ['prompt-13-tenki-v1', 'prompt-14-curry-v1', 'prompt-24-collapse-v1'])
        for value in candidates:
            case = value['case']; card = value['target']['card_id']
            self.assertEqual(case['deck']['main'][0], card)
            self.assertEqual(case['opening_hand'][0], card)
            self.assertEqual(case['objective'], source['objective'])
            self.assertEqual([len(case['deck'][k]) for k in ('main','extra','side')], [40,3,0])
            self.assertEqual(case['information']['opponent_resources'], {'main': case['deck']['main'], 'hand': []})
            for key in ('execution_ready','native_reachability_verified','response_acceptance_verified'):
                self.assertIs(value[key], False)
        candidates[0]['case']['deck']['main'][1] = 99
        self.assertNotEqual(candidates[1]['case']['deck']['main'][1], 99)

    def test_invalid_base_rejected(self):
        for mutate in (lambda c: c.update(seed=True), lambda c: c.update(seed=2),
                       lambda c: c['deck']['main'].append(85138716),
                       lambda c: c['opening_hand'].__setitem__(0, 69247929),
                       lambda c: c['opening_hand'].__setitem__(1, 69247929),
                       lambda c: c['deck']['extra'].clear()):
            case = base(); mutate(case)
            with self.assertRaises(ValueError): derive_candidates(case)

    def test_selector_requires_unique_exact_action_and_valid_encoding(self):
        source = prompt(); selected = select_unique_activation(source, 57103969)
        self.assertEqual(selected, source['actions'][0]); self.assertIsNot(selected, source['actions'][0])
        for mutate in (lambda p: p.update(player=True), lambda p: p.update(opcode=13),
                       lambda p: p['actions'].clear(), lambda p: p['actions'].append(copy.deepcopy(p['actions'][0])),
                       lambda p: p['actions'][0]['bytes'].__setitem__(0, 6),
                       lambda p: p['actions'][0]['choice'].update(index=True),
                       lambda p: p['actions'][0].update(card_ids=[57103969, 57103969])):
            value = prompt(); mutate(value)
            with self.assertRaises(ValueError): select_unique_activation(value, 57103969)
        for index in (-1,65536):
            value = prompt(); value['actions'][0]['choice']['index'] = index
            with self.assertRaises(ValueError): select_unique_activation(value, 57103969)

    def test_fixtures_preserve_order_and_are_synthetic(self):
        data = response_fixtures()
        self.assertIs(data['synthetic'], True)
        self.assertIs(data['native_reachability_verified'], False)
        self.assertEqual([a['bytes'] for a in data['prompts'][0]['actions']], [[0,0,0,0],[1,0,0,0]])
        place = data['prompts'][2]
        self.assertEqual(place['mask'], 0xfffefffc)
        self.assertEqual([a['bytes'] for a in place['actions']], [[0,4,0,0,4,1],[0,4,0,1,4,0],[0,4,1,1,4,0]])
        self.assertNotEqual(data['reverse_order_example']['bytes'], place['actions'][0]['bytes'])

    def test_pure_functions_do_not_open_files_or_start_processes(self):
        case = base()
        with patch('builtins.open', side_effect=AssertionError('I/O')), patch('subprocess.Popen', side_effect=AssertionError('process')):
            derive_candidates(case); select_unique_activation(prompt(),57103969); response_fixtures()

    def test_malformed_cases_and_selector_types_fail_closed(self):
        for case in (None, {}, {'seed': True}):
            with self.assertRaises(ValueError): derive_candidates(case)
        for card in (True, 0, -1, 2**32, '57103969'):
            with self.assertRaises(ValueError): select_unique_activation(prompt(), card)
        for modify in (lambda p: p['actions'][0].update(bytes=[5,0,True,0]),
                       lambda p: p['actions'][0].update(bytes=[5,0,3,0,0]),
                       lambda p: p['actions'][0]['choice'].update(index=3.0),
                       lambda p: p.update(opcode=11.0),
                       lambda p: p.update(actions=[None])):
            value = prompt(); modify(value)
            with self.assertRaises(ValueError): select_unique_activation(value, 57103969)
        self.assertEqual(select_unique_activation(prompt(65535),57103969)['bytes'], [5,0,255,255])

    def test_fixture_returns_fresh_objects_and_reverse_data(self):
        first = response_fixtures(); original = copy.deepcopy(first)
        first['prompts'][2]['actions'][0]['choice']['zones'][0]['player'] = 9
        self.assertEqual(response_fixtures(), original)
        self.assertEqual(original['reverse_order_example']['choice']['zones'],
                         list(reversed(original['prompts'][2]['actions'][0]['choice']['zones'])))

    def test_selector_rejects_float_card_identity_and_extra_choice_fields(self):
        value = prompt(); value['actions'][0]['card_ids'] = [57103969.0]
        with self.assertRaises(ValueError): select_unique_activation(value, 57103969)
        value = prompt(); value['actions'][0]['choice']['runtime_override'] = True
        with self.assertRaises(ValueError): select_unique_activation(value, 57103969)

    def test_expected_targets_are_static_assertions_without_actual_frames(self):
        targets = [v['expected_target'] for v in derive_candidates(base())]
        self.assertEqual(targets[0], {'opcode': 13, 'player': 0, 'description': 59877851398144,
                                     'responses': [{'choice': {'kind': 'yes_no', 'yes': False}, 'bytes': [0,0,0,0]},
                                                   {'choice': {'kind': 'yes_no', 'yes': True}, 'bytes': [1,0,0,0]}]})
        self.assertEqual(targets[1], {'opcode': 14, 'player': 0, 'descriptions': [60895602409472, 60895602409473],
                                     'responses': [{'choice': {'kind': 'option', 'index': 0}, 'bytes': [0,0,0,0]},
                                                   {'choice': {'kind': 'option', 'index': 1}, 'bytes': [1,0,0,0]}]})
        self.assertEqual(targets[2], {'opcode': 24, 'player': 0, 'count': 2, 'mask_source': 'future_raw_prompt'})
