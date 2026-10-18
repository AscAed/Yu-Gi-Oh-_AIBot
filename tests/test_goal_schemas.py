import copy
import json
import os
import unittest
from test_schemas import ROOT, validator


class GoalSchemas(unittest.TestCase):
    def test_goal_requests_and_nested_rejections(self):
        check = validator('plan-request-v3.schema.json')
        for fixture in sorted((ROOT / 'tests/fixtures').glob('goal-*.request.json')):
            name = fixture.name.removesuffix('.request.json')
            request = json.loads((ROOT / f'tests/fixtures/{name}.request.json').read_text(encoding="utf-8"))
            check.validate(request)
            for path, value in [(['goal', 'expr', 'unexpected'], True),
                                (['goal', 'continuation_steps'], 9)]:
                bad = copy.deepcopy(request)
                parent = bad
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                self.assertTrue(list(check.iter_errors(bad)), path)
            bad = copy.deepcopy(request)
            def first_filter(node):
                if isinstance(node, dict):
                    if 'filter' in node:
                        return node['filter']
                    for child in node.values():
                        found = first_filter(child)
                        if found is not None:
                            return found
                elif isinstance(node, list):
                    for child in node:
                        found = first_filter(child)
                        if found is not None:
                            return found
                return None
            first_filter(bad['goal']['expr'])['level'] = 'three'
            self.assertTrue(list(check.iter_errors(bad)))

    @unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in: v3 reports')
    def test_reports_have_strict_goal_branch_and_budget_shapes(self):
        check = validator('plan-result-v3.schema.json')
        for name in ['goal-rusty', 'goal-cherubini', 'goal-availability', 'goal-continuation']:
            report = json.loads((ROOT / f'data/runtime/{name}-report.json').read_text(encoding="utf-8"))
            check.validate(report)
            for path, value in [(['ledger', 'used_calls'], 'many'),
                                (['executions', 0, 'facts', 'cards', 0, 'proper_xyz'], 1),
                                (['recommendations', 0, 'evaluation', 'result'], 'verified'),
                                (['recommendations', 0, 'forged'], True)]:
                bad = copy.deepcopy(report)
                parent = bad
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                self.assertTrue(list(check.iter_errors(bad)), path)
