import copy
import json
import pathlib
import unittest
from ygo_data.cli import validate_cards

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DataContract(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'tests/fixtures/cards.sample.json').read_text())

    def test_kind_and_numeric_contract_rejects_incomplete_data(self):
        self.assertEqual(validate_cards(self.catalog), [])
        for key, value in [('kind', 'Extra'), ('type_flags', 0), ('id', True), ('race', -1), ('alias', 2**32)]:
            invalid = copy.deepcopy(self.catalog)
            invalid['cards'][0][key] = value
            self.assertTrue(validate_cards(invalid), key)
        invalid = copy.deepcopy(self.catalog)
        del invalid['cards'][0]['setcodes']
        self.assertTrue(validate_cards(invalid))

    def test_schema_and_python_use_same_card_fields(self):
        schema = json.loads((ROOT / 'schemas/card.schema.json').read_text())
        required = schema['properties']['cards']['items']['required']
        self.assertEqual(set(required), set(self.catalog['cards'][0]))

