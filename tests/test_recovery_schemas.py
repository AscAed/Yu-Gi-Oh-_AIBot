import copy
import json
import os
import unittest
from test_schemas import ROOT, validator


class RecoverySchemas(unittest.TestCase):
    def test_controlled_response_request_rejects_other_cards_and_budgets(self):
        q = json.loads((ROOT / 'tests/fixtures/ash-recovery.request.json').read_text())
        check = validator('plan-request-v4.schema.json')
        check.validate(q)
        for path, value in [(['schema_version'], 5), (['interruption', 'occurrence'], 2),
                            (['interruption', 'policy'], 'arbitrary'),
                            (['interruption', 'opponent_hand'], [97268402]),
                            (['analysis', 'search', 'node_budget'], 513)]:
            bad = copy.deepcopy(q)
            parent = bad
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            self.assertTrue(list(check.iter_errors(bad)), path)

    @unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in v4 report')
    def test_report_rejects_forged_shapes(self):
        r = json.loads((ROOT / 'data/runtime/ash-recovery-report.json').read_text())
        check = validator('plan-result-v4.schema.json')
        check.validate(r)
        for path, value in [(['interrupted', 'state', 'normal_left'], 'unused'),
                            (['interrupted', 'runtime', 'protocol_version'], 3),
                            (['recovery', 'context', 'unexpected'], True),
                            (['interrupted', 'replay_verified'], False)]:
            bad = copy.deepcopy(r)
            parent = bad
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            self.assertTrue(list(check.iter_errors(bad)), path)
