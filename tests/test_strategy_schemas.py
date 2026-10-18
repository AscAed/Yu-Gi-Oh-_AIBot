import copy
import json
import os
import unittest
from test_schemas import ROOT, validator


class StrategySchemas(unittest.TestCase):
    def test_fixed_matrix_request_and_negative_policies(self):
        q = json.loads((ROOT / 'tests/fixtures/ash-strategy.request.json').read_text())
        check = validator('plan-request-v5.schema.json')
        check.validate(q)
        for key, value in [('max_strategies', 3), ('total_budget', 8193),
                           ('policies', q['policies'][:-1]), ('schema_version', 4)]:
            bad = copy.deepcopy(q)
            bad[key] = value
            self.assertTrue(list(check.iter_errors(bad)), key)
        bad = copy.deepcopy(q)
        bad['opponent']['effect_id'] = '58699500:mill'
        self.assertTrue(list(check.iter_errors(bad)))

    @unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in full strategy report')
    def test_actual_matrix_and_strict_score_shapes(self):
        report = json.loads((ROOT / 'data/runtime/ash-strategy-report.json').read_text())
        check = validator('plan-result-v5.schema.json')
        check.validate(report)
        score_schema = check.schema['properties']['strategies']['items']['properties']['cells']['items']['properties']['outcome']['anyOf'][1]['properties']['score']
        score_check = check.evolve(schema=score_schema)
        score = report['strategies'][0]['cells'][0]['outcome']['score']
        for key, value in [('goal', 'yes'), ('main_resources', -1),
                           ('verification_decisions', 'cheap'), ('fabricated', True)]:
            bad = dict(score)
            bad[key] = value
            self.assertTrue(list(score_check.iter_errors(bad)), key)
