import copy
import unittest
from ygo_eval.research_problem import validate_problem
from ygo_data.identity import canonical, digest
from test_schemas import validator


class ResearchProblem(unittest.TestCase):
    def candidate(self):
        from test_research import sample
        case = sample()
        # Contract tests do not reuse the implementation to create objective expectations.
        return {'schema_version':1,'kind':'research_problem','problem_id':'rabbit-terminal-v1','status':'candidate',
                'input':{'frozen_case_v1':case,'case_sha256':digest(canonical(case)),'request_sha256':'d'*64,'frozen_source_sha256':'e'*64},
                'objective':{'id':'rabbit-own-face-up-xyz-v1','normal_min':0,'normal_max':7,'early_win':8,'loss':-2,'draw':-1},
                'termination':{'normal':'first-next-turn-process-return-v1','natural_end_has_successors':False},
                'seed_semantics':'reproduction_only',
                'conditions':{key:{'resolved':False,'reason':'not yet established'} for key in ('hidden_information','probability','action_ordering','loops','tree_size','necessary_actions')}}

    def test_candidate_blocks_proof_and_missing_goal_is_rejected(self):
        value = self.candidate()
        # Frozen case has its separate, deliberately unchanged v1 contract.
        validator('research-problem.schema.json').validate(value)
        result=validate_problem(value)
        self.assertFalse(result['proof_ready'])
        self.assertEqual(len(result['blockers']),6)
        bad=copy.deepcopy(value); del bad['objective']
        with self.assertRaises(ValueError): validate_problem(bad)
        for key in ('normal_max','early_win'):
            bad=copy.deepcopy(value); bad['objective'][key]=99
            with self.assertRaises(ValueError): validate_problem(bad)
        bad=copy.deepcopy(value);bad['input']['frozen_case_v1']['seed']=2
        with self.assertRaises(ValueError): validate_problem(bad)
        bad=copy.deepcopy(value);bad['conditions']['loops']['reason']=''
        with self.assertRaises(ValueError): validate_problem(bad)
