"""Wire contracts stay separate from semantic and native qualification."""
import copy
import unittest

from test_research import sample
from test_schemas import validator


class BaselineSchemas(unittest.TestCase):
    def test_research_case_freezes_terminal_information_and_sources(self):
        check = validator('research-case.schema.json')
        check.validate(sample())
        for mutate in (
            lambda value: value['objective']['terminal_utility'].pop('draw'),
            lambda value: value['objective'].update(priorities=['undefined']),
            lambda value: value['assets'].update(cdb_sha256='unknown'),
            lambda value: value.update(seed=True),
            lambda value: value.update(case_id=123),
            lambda value: value.update(hidden_override=True),
        ):
            invalid = copy.deepcopy(sample())
            mutate(invalid)
            self.assertTrue(list(check.iter_errors(invalid)))

    def test_response_match_never_grants_optimality(self):
        check = validator('response-audit.schema.json')
        value = {'opcode': 19, 'matches': True, 'missing': [],
                 'unexpected': [], 'duplicate_count': 0,
                 'global_optimality': False,
                 'qualification': 'canonical_response_comparison',
                 'complete_action_coverage': False,
                 'coverage_gaps': ['ordering_equivalence_unproven',
                                   'protocol_oracle_is_not_engine_semantic_proof']}
        check.validate(value)
        invalid = {**value, 'global_optimality': True}
        self.assertTrue(list(check.iter_errors(invalid)))
        invalid = {**value, 'unexpected': [[256]]}
        self.assertTrue(list(check.iter_errors(invalid)))
