"""Synthetic pipeline tests: patched source pins never grant native evidence."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from test_coverage_language import temporary_directory
from test_information_route_projection import fixture
from test_schemas import validator
from ygo_data.identity import canonical
from ygo_eval import information_route as route


class RoutePipelineTests(unittest.TestCase):
    def run_case(self, folder, evaluator=None, drift=False, bad_route=False,
                 terminal_sample=False, bad_queries=False):
        folder = Path(folder)
        events, public, decisions, resolved = fixture()
        if bad_route:
            events.append({'raw': [99], 'opcode': 99})
        cdb = folder / 'cards.cdb'
        with closing(sqlite3.connect(cdb)) as database:
            database.execute('CREATE TABLE datas(id INTEGER,type INTEGER)')
            database.execute('INSERT INTO datas VALUES(123,33)')
            database.commit()
        runner = folder / 'pure-runner'
        runner.write_bytes(b'synthetic-pure-runner-not-executable')
        versions = {'cdb_sha256': route.hashed(cdb.read_bytes())}
        request = {'deck': {'main': [123] * 5, 'extra': [], 'side': []},
                   'opening_hand': [123] * 5, 'seed': 1, 'versions': versions,
                   'protocol_version': 2, 'engine': {
                       'ocgcore_path': 'synthetic-core', 'catalog_path': 'synthetic-cdb',
                       'script_manifest_path': 'synthetic-scripts', 'timeout_ms': 30000}}
        case = {'rules': {'region': 'OCG', 'version': 'synthetic'},
                'assets': {'cdb_sha256': versions['cdb_sha256']}}
        frozen = {'cases': [{'case': case, 'request': copy.deepcopy(request)}]}
        frozen_input = {'case_sha256': route.hashed(canonical(case)),
                        'request_sha256': route.hashed(canonical(request)),
                        'rules': case['rules'], 'assets': case['assets']}
        request['decisions'] = decisions
        queries = [{'controller': player, 'location': 4, 'sequence': slot,
                    'flags': 11, 'raw': [], 'sha256': route.hashed(b''), 'error': None}
                   for player in (0, 1) for slot in range(7)]
        run = {'events': events, 'resolved_decisions': resolved,
               'protocol_version': 2, 'versions': versions,
               'terminal_observation': {'queries': queries, 'capture_query_count': 14}}
        native = {'request': request, 'runs': [{'Ok': copy.deepcopy(run)} for _ in range(2)]}
        if bad_queries:
            native['runs'][0]['Ok']['terminal_observation']['queries'].pop()
        parent = {'public': public, 'frozen_input': frozen_input}
        parent_raw = canonical(parent)
        documents = {
            'parent-contract': parent_raw,
            'parent-acceptance': canonical({
                'tools_verified': True, 'observation_profile_verified': True,
                'policy_samples_consistent': True,
                'evidence': {'contract.json': {'sha256': route.hashed(parent_raw)}}}),
            'terminal-shuffle-end': canonical(native), 'frozen-input': canonical(frozen),
            'source-request': canonical({'input': {'request': request},
                                         'request_sha256': route.hashed(canonical(request))}),
            'core-processor': b'synthetic-static-source',
            'core-constants': b'synthetic-static-constants'}
        pins = {role: route.hashed(raw) for role, raw in documents.items()}
        contract = {'schema_version': 1, 'kind': 'information-route-study',
                    'study_id': 'rabbit-shuffle-end-information-v1',
                    'observation_profile': 'rabbit-shuffle-end-observation-v1',
                    'seed_role': 'reproduction_only', 'fixed_actions': [8, 7],
                    'frozen_input': frozen_input, 'public': public,
                    **{flag: False for flag in route.FLAGS},
                    'evidence': [{'role': role, 'sha256': pin,
                                  'category': route.ORIGINS[role][0],
                                  'scope': route.ORIGINS[role][1]}
                                 for role, pin in pins.items()]}
        contract_path, samples_path, output = [folder / name for name in
                                               ('contract.json', 'samples.json', 'output.json')]
        contract_path.write_bytes(canonical(contract))
        samples = {'schema_version': 1, 'kind': 'information-policy-samples', 'samples': [{
            'policy_id': 'synthetic-policy',
            'observation_id': 'terminal-shuffle-end/run0/view' + ('2' if terminal_sample else '0'),
            'distribution': [{'bytes': [7, 0, 0, 0], 'numerator': 1, 'denominator': 1}]}]}
        samples_path.write_bytes(canonical(samples))
        evidence = []
        for role, raw in documents.items():
            path = folder / (role + '.json')
            path.write_bytes(raw)
            evidence.append(role + '=' + str(path))
        source = {'identity': '0' * 64}
        default = {'evaluations': [{'binding_valid': True, 'snapshot_count': 0,
                                    'utility': 0, 'termination': 'terminal_boundary_bound',
                                    'diagnostics': []} for _ in range(2)]}
        with patch.object(route, 'PINS', pins), \
                patch.object(route, 'CDB_PIN', versions['cdb_sha256']), \
                patch.object(route, 'RUNNER_PIN', route.hashed(runner.read_bytes())), \
                patch.object(route, 'validate_parent', return_value=parent), \
                patch.object(route, 'checked_output', side_effect=lambda _, path: Path(path)), \
                patch.object(route, 'stable_source', side_effect=[source, {'identity': '1' * 64} if drift else source]), \
                patch.object(route, 'run_runner', side_effect=evaluator if isinstance(evaluator, Exception) else None,
                             return_value=default if evaluator is None else evaluator) as process, \
                patch('subprocess.Popen', side_effect=AssertionError('worker forbidden')):
            report = route.audit_information_route(contract_path, samples_path, evidence,
                                                    cdb, runner, output)
        validator('information-route-audit.schema.json').validate(report)
        self.assertEqual(report, json.loads(output.read_bytes()))
        self.assertEqual(report['native_calls'], 0)
        return report, process.call_count

    def test_synthetic_positive_pipeline_runs_only_pure_evaluator(self):
        with temporary_directory() as folder:
            report, calls = self.run_case(folder)
        self.assertTrue(report['successful'])
        self.assertEqual(calls, 1)
        self.assertEqual(len(report['observations']), 6)
        self.assertTrue(all(report['layers'].values()))

    def test_failed_evaluator_preserves_views_without_zero(self):
        for reply in (ValueError('synthetic_evaluator_failure'), {},
                      {'evaluations': [{'binding_valid': False}] * 2},
                      {'evaluations': [{'binding_valid': True, 'snapshot_count': 1,
                                        'utility': 1, 'termination': 'terminal_boundary_bound',
                                        'diagnostics': []}] * 2}):
            with self.subTest(reply=reply), temporary_directory() as folder:
                report, calls = self.run_case(folder, evaluator=reply)
            self.assertFalse(report['successful'])
            self.assertEqual(calls, 1)
            self.assertEqual(len(report['observations']), 6)
            for record in report['observations'].values():
                if record['kind'] == 'terminal':
                    self.assertIsNone(record['view']['normal_count'])
                    self.assertIsNone(record['view']['normal_utility'])

    def test_invalid_route_stops_before_evaluator(self):
        with temporary_directory() as folder:
            report, calls = self.run_case(folder, bad_route=True)
        self.assertFalse(report['successful'])
        self.assertEqual(calls, 0)
        self.assertEqual(len(report['observations']), 4)

    def test_missing_query_never_reaches_evaluator_or_assigns_zero(self):
        with temporary_directory() as folder:
            report, calls = self.run_case(folder, bad_queries=True)
        self.assertFalse(report['successful'])
        self.assertEqual(calls, 0)
        self.assertEqual(len(report['observations']), 6)
        for record in report['observations'].values():
            if record['kind'] == 'terminal':
                self.assertIsNone(record['view']['normal_count'])
                self.assertIsNone(record['view']['normal_utility'])

    def test_terminal_action_sample_rejected_after_valid_binding(self):
        with temporary_directory() as folder:
            report, calls = self.run_case(folder, terminal_sample=True)
        self.assertFalse(report['successful'])
        self.assertEqual(calls, 1)
        self.assertTrue(report['layers']['binding'])
        self.assertIn({'reason': 'terminal_policy_sample_forbidden'}, report['diagnostics'])

    def test_post_evaluation_drift_revokes_bound_values(self):
        with temporary_directory() as folder:
            report, calls = self.run_case(folder, drift=True)
        self.assertFalse(report['successful'])
        self.assertEqual(calls, 1)
        self.assertFalse(any(report['layers'].values()))
        self.assertEqual(report['terminal_evaluations'], [])
        for observation in report['observations'].values():
            if observation['kind'] == 'terminal':
                self.assertIsNone(observation['view']['normal_utility'])
