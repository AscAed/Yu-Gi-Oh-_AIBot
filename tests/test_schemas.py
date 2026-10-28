import json
import os
import pathlib
import unittest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = 'https://ygo.local/schemas/'


def validator(name):
    registry = Registry()
    schemas = {}
    for path in (ROOT / 'schemas').glob('*.json'):
        schema = json.loads(path.read_text(encoding='utf-8'))
        schema['$id'] = BASE + path.name
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        registry = registry.with_resource(BASE + path.name, Resource.from_contents(schema))
    return Draft202012Validator(schemas[name], registry=registry, format_checker=FormatChecker())


class Schemas(unittest.TestCase):
    def test_planning_request_limits_and_unknown_fields(self):
        import copy
        request = json.loads((ROOT / 'tests/fixtures/phantom.request.json').read_text())
        check = validator('plan-request.schema.json')
        check.validate(request)
        for field, value in [('max_proposals', 9), ('max_steps', 33), ('goal', 'win_probability'), ('schema_version', 2), ('hidden_policy', True)]:
            invalid = copy.deepcopy(request)
            invalid[field] = value
            self.assertTrue(list(check.iter_errors(invalid)), field)

    def test_v2_planning_and_effect_coverage(self):
        import copy
        check = validator('plan-request-v2.schema.json')
        request = json.loads((ROOT / 'tests/fixtures/break-sword.request.json').read_text())
        check.validate(request)
        invalid = copy.deepcopy(request)
        invalid['scenario'] = 'arbitrary_opponent'
        self.assertTrue(list(check.iter_errors(invalid)))
        validator('knowledge-v2.schema.json').validate(json.loads((ROOT / 'knowledge/phantom-v2.json').read_text(encoding='utf-8')))
        cases = json.loads((ROOT / 'tests/fixtures/phantom.engine-cases.json').read_text(encoding='utf-8'))['cases']
        effects = {e['id'] for c in json.loads((ROOT / 'knowledge/phantom-v2.json').read_text(encoding='utf-8'))['cards'] for e in c['effects'] if e['supported']}
        self.assertEqual({c['effect_id'] for c in cases}, effects)
        samples = json.loads((ROOT / 'tests/fixtures/phantom.fixed-hands.json').read_text())['samples']
        self.assertEqual([sum(s['group'] == group for s in samples) for group in ['positive', 'limited', 'fallback']], [8, 4, 4])
        for s in samples:
            check.validate(s['request'])

    @unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in: actual v2 report')
    def test_v2_runtime_nested_rejection(self):
        import copy
        value = json.loads((ROOT / 'data/runtime/break-sword-report.json').read_text())
        check = validator('plan-result-v2.schema.json')
        check.validate(value)
        corruptions = [
            (['analysis', 'runtime_request', 'deck'], 'garbage'),
            (['analysis', 'runtime_request', 'injected'], True),
            (['analysis', 'search', 'stats', 'engine_calls'], 'garbage'),
            (['analysis', 'search', 'lines', 0, 'decisions'], [{'nonsense': True}]),
            (['analysis', 'runtime_request', 'versions', 'initializer'], 42),
        ]
        for path, mutation in corruptions:
            invalid = copy.deepcopy(value)
            parent = invalid
            for component in path[:-1]:
                parent = parent[component]
            parent[path[-1]] = mutation
            self.assertTrue(list(check.iter_errors(invalid)), str(path))

    def test_card_and_request_fixtures(self):
        for schema, fixture in [('card.schema.json', 'cards.sample.json'), ('combo-request.schema.json', 'rabbit.request.json')]:
            validator(schema).validate(json.loads((ROOT / 'tests/fixtures' / fixture).read_text()))

    def test_deck_document_v1_accepts_partial_ordered_drafts_and_rejects_bad_ids(self):
        check = validator('deck-document-v1.schema.json')
        draft = {
            'schema_version': 1,
            'kind': 'deck_draft',
            'title': 'unfinished',
            'main': [12, 12],
            'extra': [],
            'side': [12],
        }
        check.validate(draft)
        check.validate({**draft, 'title': 'empty', 'main': [], 'extra': [], 'side': []})
        for mutation in [
            {'schema_version': 2},
            {'kind': 'deck'},
            {'main': [0]},
            {'extra': [-1]},
            {'side': [4294967296]},
            {'unexpected': True},
        ]:
            invalid = dict(draft)
            invalid.update(mutation)
            self.assertTrue(list(check.iter_errors(invalid)), mutation)

    def test_language_field_review_contract_is_non_qualifying_and_contains_no_candidate_text(self):
        from ygo_data.language_review import audit_language_fields
        check = validator('language-field-review-v1.schema.json')
        ids = list(range(1, 40))
        sources = [{'id': 'candidate', 'language': 'zh-Hans', 'version': 'fixture', 'sha256': 'a' * 64,
                    'license': {'redistribution': 'unknown'}}]
        report = audit_language_fields(ids, sources, [], {'candidate': {}})
        report['created_at'] = '2026-10-28T00:00:00+00:00'
        report['source_manifest_checked_date'] = '2026-10-19'
        report['legacy_audit_unresolved'] = []
        report['inputs'] = {'source': 'b' * 64, 'sample': 'c' * 64, 'records': 'd' * 64,
                            'cn': 'e' * 64, 'sc': 'f' * 64}
        check.validate(report)
        invalid = dict(report, qualified=True)
        self.assertTrue(list(check.iter_errors(invalid)))
        invalid = dict(report)
        invalid['candidate_text'] = 'not permitted'
        self.assertTrue(list(check.iter_errors(invalid)))
        invalid = dict(report, sample_card_ids=ids[:-1])
        self.assertTrue(list(check.iter_errors(invalid)))

    def test_first_turn_execution_checkpoint_requires_a_bound_resource_snapshot(self):
        check = validator('first-turn-execution-checkpoint-v1.schema.json')
        digest = 'a' * 64
        checkpoint = {
            'schema_version': 1,
            'kind': 'first_turn_execution_checkpoint',
            'execution_id': digest,
            'plan_id': 'plan-fixture',
            'binding': {
                'start_request_sha256': digest,
                'plan_sha256': digest,
                'catalog_sha256': digest,
                'knowledge_sha256': digest,
                'goal_sha256': digest,
                'runtime_versions_sha256': digest,
            },
            'progress': {
                'status': 'ready', 'stage': 'execution', 'step': 0,
                'start_request': {}, 'current_request': {}, 'current_prefix': {},
                'actual_resources': {
                    'turn': 1, 'turn_player': 0, 'phase': 1,
                    'lp': [8000, 8000], 'cards': [],
                },
                'trusted_prefix_request': {}, 'trusted_prefix_call': 1,
                'last_completed_request': {}, 'last_completed_result': {},
                'last_completed_error': None, 'instance_mapping': {},
                'used_selections': [], 'predictions': [], 'queries': [],
                'pending_action': None, 'pending_intent': None,
                'completed_call_ids': [1],
                'ledger': {'consumed': 1, 'reserved': 0, 'completed': 1,
                           'unknown': 0, 'limit': 7},
                'reservations': {},
                'diagnostic': None,
            },
        }
        check.validate(checkpoint)
        invalid = json.loads(json.dumps(checkpoint))
        del invalid['progress']['actual_resources']
        self.assertTrue(list(check.iter_errors(invalid)))
        invalid = json.loads(json.dumps(checkpoint))
        invalid['progress']['actual_resources']['turn_player'] = 2
        self.assertTrue(list(check.iter_errors(invalid)))

    @unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in: local snapshots/reports')
    def test_actual_snapshots_and_report(self):
        for path in (ROOT / 'data/snapshots').glob('*.json'):
            kind = path.name.split('-')[0]
            if kind in ['banlist', 'catalog']:
                validator(f'{kind}.schema.json').validate(json.loads(path.read_text()))
        validator('combo-result.schema.json').validate(json.loads((ROOT / 'data/runtime/acceptance-report.json').read_text()))
