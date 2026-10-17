import copy
import json
import os
import unittest

from test_schemas import ROOT, validator


class FirstTurnSchemas(unittest.TestCase):
    def test_native_ash_branch_requires_its_own_focus_and_scoped_recipe(self):
        check = validator('first-turn-cases.schema.json')
        suite = json.loads((ROOT / 'tests/fixtures/tournament-2026.rules-ash.json').read_text(encoding='utf-8'))
        check.validate(suite)
        for field, value in [('focus', None), ('kind', 'claimed_verified'),
                             ('scope', 'tournament_sample')]:
            changed = copy.deepcopy(suite)
            changed['cases'][0][field] = value
            self.assertTrue(list(check.iter_errors(changed)), field)

    def test_observable_counterexamples_and_delayed_boundary_have_distinct_contracts(self):
        check = validator('first-turn-cases.schema.json')
        suite = json.loads((ROOT / 'tests/fixtures/tournament-2026.rules-resource.json').read_text(encoding='utf-8'))
        for kind in ['continuous_negative', 'delayed', 'delayed_negative']:
            changed = copy.deepcopy(suite)
            changed['cases'][0]['kind'] = kind
            if kind.startswith('delayed'):
                changed['cases'][0]['observation'] = 'own_main_window'
                self.assertTrue(list(check.iter_errors(changed)))
                changed['cases'][0]['observation'] = 'end_phase_complete'
            check.validate(changed)

    def test_native_cases_require_explicit_scope_and_strict_assertions(self):
        check = validator('first-turn-cases.schema.json')
        suite = json.loads((ROOT / 'tests/fixtures/tournament-2026.rules-resource.json').read_text(encoding='utf-8'))
        check.validate(suite)
        for path, value in [(['cases', 0, 'scope'], 'tournament_sample'),
                            (['cases', 0, 'focus'], None),
                            (['cases', 0, 'assertions', 0, 'count'], -1),
                            (['cases', 0, 'decisions', 0, 'player'], 2),
                            (['cases', 0, 'assertions', 0, 'verified'], True),
                            (['cases', 0, 'opening_hand'], [83566725])]:
            changed = copy.deepcopy(suite)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            self.assertTrue(list(check.iter_errors(changed)), path)

    def test_report_has_strict_provenance_call_and_binding_references(self):
        check = validator('first-turn-verification.schema.json')
        report_path = os.environ.get('YGO_FIRST_TURN_REPORT', 'tests/fixtures/tournament-2026.rules-resource.contract.json')
        report = json.loads((ROOT / report_path).read_text(encoding='utf-8'))
        check.validate(report)
        for path, value in [(['asset_group_id'], 'forged'),
                            (['cases', 0, 'ledger', 'consumed'], 513),
                            (['cases', 0, 'replay_calls', 0], 0),
                            (['cases', 0, 'runtime_request', 'protocol_version'], 5),
                            (['cases', 0, 'runtime_request', 'first_turn', 'certified'], True),
                            (['cases', 0, 'binding', 'source', 'sequence'], 'first')]:
            changed = copy.deepcopy(report)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            self.assertTrue(list(check.iter_errors(changed)), path)
