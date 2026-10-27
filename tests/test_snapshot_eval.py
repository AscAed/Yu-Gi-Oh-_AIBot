import json
from pathlib import Path
import sqlite3
from contextlib import closing
import unittest
from unittest.mock import patch
from test_coverage_language import temporary_directory
from ygo_data.identity import digest
from ygo_eval.snapshot_eval import evaluate_snapshot
from test_schemas import validator

class SnapshotEvaluation(unittest.TestCase):
    def test_v2_bound_utility_requires_matching_count_and_false_claims(self):
        with temporary_directory() as directory:
            root=Path(directory); cdb=root/'cards.cdb'; runner=root/'runner.exe'; source=root/'evidence.json'
            with closing(sqlite3.connect(cdb)) as db:
                db.execute('CREATE TABLE datas(id INTEGER,type INTEGER)');db.commit()
            runner.write_bytes(b'auditor')
            versions={'cdb_sha256':digest(cdb.read_bytes())}
            source.write_text(json.dumps({'kind':'synthetic_snapshot_fixture','request':{'protocol_version':2,'versions':versions},'runs':[{'Ok':{'protocol_version':2,'versions':versions}}]}))
            output=Path(__file__).resolve().parents[1]/'data/runtime/research'/root.name/'v2.json'
            core={'evaluations':[{'snapshot_count':1,'termination':'terminal_boundary_bound','utility':1,'binding_valid':True,'diagnostics':[]}]}
            identity={'head':'a'*40,'identity':'b'*64}
            try:
                with patch('ygo_eval.snapshot_eval.stable_source',return_value=identity), patch('ygo_eval.snapshot_eval.run_runner',return_value=core) as auditor:
                    report=evaluate_snapshot(source,cdb,runner,output,2)
                    validator('snapshot-evaluation-v2.schema.json').validate(report)
                    self.assertEqual(auditor.call_args.args[1]['schema_version'],2)
                    self.assertFalse(report['source_authenticity_verified'])
                    self.assertFalse(report['native_replay_verified'])
                    output.unlink()
                    for field,value in [('utility',2),('binding_valid',False),('snapshot_count',None)]:
                        changed={'evaluations':[dict(core['evaluations'][0],**{field:value})]}
                        with patch('ygo_eval.snapshot_eval.run_runner',return_value=changed):
                            with self.assertRaises(ValueError):evaluate_snapshot(source,cdb,runner,output,2)
                    with self.assertRaises(ValueError):evaluate_snapshot(source,cdb,runner,output,1)
            finally:
                if output.exists():output.unlink()
                if output.parent.exists():output.parent.rmdir()
    def test_schema_exclusivity_versions_and_input_mutation(self):
        with temporary_directory() as directory:
            root=Path(directory); cdb=root/'cards.cdb'; runner=root/'runner.exe'; source=root/'evidence.json'
            with closing(sqlite3.connect(cdb)) as db:
                db.execute('CREATE TABLE datas(id INTEGER,type INTEGER)');db.execute('INSERT INTO datas VALUES(1,8388609)');db.commit()
            runner.write_bytes(b'auditor')
            versions={'cdb_sha256':digest(cdb.read_bytes())}
            request={'protocol_version':2,'versions':versions}
            result={'protocol_version':2,'versions':versions}
            source.write_text(json.dumps({'kind':'synthetic_snapshot_fixture','request':request,'runs':[{'Ok':result},{'Err':{'message':'private'}}]}))
            output=Path(__file__).resolve().parents[1]/'data/runtime/research'/root.name/'snapshot.json'
            core={'evaluations':[{'snapshot_count':1,'termination':'next_turn_boundary_observed','utility':None,'diagnostics':['checkpoint_not_bound_to_terminal_boundary']},{'snapshot_count':None,'termination':'execution_failed','utility':None,'diagnostics':['execution_failed']}]}
            try:
                with patch('ygo_eval.snapshot_eval.run_runner',return_value=core):
                    report=evaluate_snapshot(source,cdb,runner,output)
                    check=validator('snapshot-evaluation.schema.json');check.validate(report)
                    self.assertNotIn(str(root),json.dumps(report));self.assertNotIn('private',json.dumps(report))
                    with self.assertRaises(ValueError):evaluate_snapshot(source,cdb,runner,output)
                    output.unlink()
                    self.assertTrue(list(check.iter_errors({**report,'proof_ready':True})))
                    bad={**report,'evaluations':[{**report['evaluations'][0],'termination':'unknown','utility':8}]}
                    self.assertTrue(list(check.iter_errors(bad)))
                forged={'evaluations':[dict(core['evaluations'][0],utility=8),core['evaluations'][1]]}
                with patch('ygo_eval.snapshot_eval.run_runner',return_value=forged):
                    with self.assertRaisesRegex(ValueError,'utility'):evaluate_snapshot(source,cdb,runner,output)
                def mutate(*args):source.write_bytes(b'changed');return core
                with patch('ygo_eval.snapshot_eval.run_runner',side_effect=mutate):
                    with self.assertRaisesRegex(ValueError,'changed'):evaluate_snapshot(source,cdb,runner,output)
                self.assertFalse(output.exists())
                source.write_text(json.dumps({'request':{**request,'protocol_version':99},'runs':[{'Ok':result}]}))
                with patch('ygo_eval.snapshot_eval.run_runner') as call:
                    with self.assertRaises(ValueError):evaluate_snapshot(source,cdb,runner,output)
                    call.assert_not_called()
            finally:
                if output.exists():output.unlink()
                if output.parent.exists():output.parent.rmdir()
