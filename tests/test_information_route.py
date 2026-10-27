import copy
import json
from pathlib import Path
import shutil
import uuid
from contextlib import contextmanager

@contextmanager
def temporary_directory():
    root = Path(__file__).resolve().parents[1]/"data/runtime"/str(uuid.uuid4())
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)
import unittest
from unittest.mock import patch

from ygo_data.identity import canonical
from ygo_eval.information_route import validate_contract, validate_evaluations, validate_queries
from ygo_eval.information_audit import strict_json


class RouteValidationTests(unittest.TestCase):
    def test_boolean_count_is_not_a_bound_terminal(self):
        with self.assertRaises(ValueError):
            validate_evaluations({'evaluations':[{'binding_valid':True,'snapshot_count':False,'utility':False,'termination':'terminal_boundary_bound','diagnostics':[]}]},1)

    def test_contract_rejects_self_declared_sources(self):
        with self.assertRaises(ValueError):
            validate_contract({'schema_version':True})

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): strict_json(raw)

    def test_fourteen_queries_must_have_all_distinct_coordinates(self):
        from ygo_eval.information_audit import hashed
        queries = [{'controller':player,'location':4,'sequence':slot,'flags':11,'raw':[],'sha256':hashed(b''),'error':None} for player in (0,1) for slot in range(7)]
        run = {'terminal_observation':{'capture_query_count':14,'queries':queries}}
        validate_queries(run)
        queries[-1] = copy.deepcopy(queries[0])
        with self.assertRaises(ValueError): validate_queries(run)

    def test_additional_or_nonempty_evaluator_diagnostics_fail(self):
        item = {'binding_valid':True,'snapshot_count':0,'utility':0,'termination':'terminal_boundary_bound','diagnostics':[]}
        validate_evaluations({'evaluations':[item]},1)
        for key,value in [('diagnostics',['unverified']),('utility',True),('extra',False),('binding_valid',1)]:
            forged = dict(item,**{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError): validate_evaluations({'evaluations':[forged]},1)

    def test_rejected_source_saves_failure_without_starting_process(self):
        from ygo_eval.information_route import audit_information_route
        with temporary_directory() as directory:
            root = Path(directory)
            paths = {}
            for role in ('contract','samples','runner','cdb'):
                paths[role] = root / role
                paths[role].write_text('{}')
            output = root/'nested'/'failure.json'
            with patch('ygo_eval.information_route.checked_output',side_effect=lambda repo,path:Path(path)), patch('ygo_eval.information_route.stable_source',return_value={'identity':'a'*64}), patch('ygo_eval.information_route.run_runner') as runner:
                report = audit_information_route(paths['contract'],paths['samples'],[],paths['cdb'],paths['runner'],output,repo=root)
            runner.assert_not_called()
            self.assertFalse(report['successful'])
            self.assertEqual(report['native_calls'],0)
            self.assertTrue(output.is_file())
            import jsonschema
            schema = json.loads((Path(__file__).resolve().parents[1]/'schemas/information-route-audit.schema.json').read_text())
            jsonschema.validate(report,schema)

    def test_source_drift_invalidates_every_layer(self):
        from ygo_eval.information_route import audit_information_route
        with temporary_directory() as directory:
            root=Path(directory)
            source=root/'input'; source.write_text('{}')
            with patch('ygo_eval.information_route.checked_output',side_effect=lambda repo,path:Path(path)), patch('ygo_eval.information_route.stable_source',side_effect=[{'identity':'a'*64},{'identity':'b'*64}]):
                report=audit_information_route(source,source,[],source,source,root/'out',repo=root)
            self.assertFalse(any(report['layers'].values()))
            self.assertIn({'reason':'input_or_source_changed_during_capture'},report['diagnostics'])

    def test_failure_report_explicitly_preserves_scope_and_reexecution_limits(self):
        from ygo_eval.information_route import audit_information_route
        with temporary_directory() as directory:
            source=Path(directory)/'input'; source.write_text('{}')
            with patch('ygo_eval.information_route.checked_output',side_effect=lambda repo,path:Path(path)), patch('ygo_eval.information_route.stable_source',return_value={'identity':'a'*64}), patch('ygo_eval.information_route.run_runner') as runner:
                report=audit_information_route(source,source,[],source,source,Path(directory)/'out',repo=directory)
            self.assertEqual(report['out_of_scope'],['rabbit-full','tournament-full'])
            self.assertFalse(report['historical_reexecution_performed'])
            self.assertFalse(report['new_native_replay_verified'])
            self.assertEqual(report['route_audits'],[])
            runner.assert_not_called()

    def test_preexisting_output_is_not_overwritten(self):
        from ygo_eval.information_route import audit_information_route
        with temporary_directory() as directory:
            source=Path(directory)/'input'; source.write_text('{}')
            output=Path(directory)/'out'; output.write_text('protected')
            with patch('ygo_eval.information_route.checked_output',side_effect=lambda repo,path:Path(path)), self.assertRaises(ValueError):
                audit_information_route(source,source,[],source,source,output,repo=directory)
            self.assertEqual(output.read_text(),'protected')

    def test_observation_schema_rejects_terminal_phase_and_private_injections(self):
        import jsonschema
        from test_information_route_projection import fixture, EVAL
        from ygo_eval.information_route_projection import project_route
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/information-route-audit.schema.json').read_text())
        observation_schema={'$ref':'#/$defs/observation','$defs':schema.get('$defs',{})}
        views=project_route(*fixture(),EVAL)['views']
        for observation in views:
            observation['provenance']={'role':'terminal-shuffle-end','category':'historical_native'}
            jsonschema.validate(observation,observation_schema)
        for index,scope,key,value in [(2,'view','phase',512),(0,'view','seed',999),(0,'rules','source_hash','secret'),(0,'history','opponent_hand',[1]),(0,'view','opponent_hand',[1]),(0,'history','player',1)]:
            forged=copy.deepcopy(views[index])
            target=forged['view'] if scope=='view' else forged['view']['rules'] if scope=='rules' else forged['view']['visible_history'][0]
            target[key]=value
            with self.subTest(scope=scope,key=key), self.assertRaises(jsonschema.ValidationError): jsonschema.validate(forged,observation_schema)

    def test_terminal_unknown_schema_requires_null_counts(self):
        import jsonschema
        from test_information_route_projection import fixture
        from ygo_eval.information_route_projection import project_route
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/information-route-audit.schema.json').read_text())
        observation_schema={'$ref':'#/$defs/observation','$defs':schema.get('$defs',{})}
        observation=project_route(*fixture())['views'][-1]
        observation['provenance']={'role':'terminal-shuffle-end','category':'historical_native'}
        jsonschema.validate(observation,observation_schema)
        observation['view']['normal_count']=0
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(observation,observation_schema)
