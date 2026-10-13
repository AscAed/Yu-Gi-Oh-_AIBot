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

    def test_card_and_request_fixtures(self):
        for schema, fixture in [('card.schema.json', 'cards.sample.json'), ('combo-request.schema.json', 'rabbit.request.json')]:
            validator(schema).validate(json.loads((ROOT / 'tests/fixtures' / fixture).read_text()))

    @unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in: local snapshots/reports')
    def test_actual_snapshots_and_report(self):
        for path in (ROOT / 'data/snapshots').glob('*.json'):
            kind = path.name.split('-')[0]
            if kind in ['banlist', 'catalog']:
                validator(f'{kind}.schema.json').validate(json.loads(path.read_text()))
        validator('combo-result.schema.json').validate(json.loads((ROOT / 'data/runtime/acceptance-report.json').read_text()))
