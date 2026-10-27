import unittest
from ygo_eval.information_audit import strict_json, validate_contract

class InformationAuditTests(unittest.TestCase):
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.assertRaises(ValueError): strict_json(raw)

    def test_contract_missing_sources_rejected(self):
        with self.assertRaises(ValueError): validate_contract({})

    def test_claimed_native_hash_must_be_registered(self):
        from ygo_eval.information_audit import validate_origin
        with self.assertRaises(ValueError):
            validate_origin({'role':'rabbit-empty','category':'historical_native','sha256':'0'*64})
import copy
import json
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class IntegrationContractTests(unittest.TestCase):
    def contract(self):
        from ygo_eval.information_audit import hashed
        frozen={'case':{'rules':{'region':'OCG','version':'2026-10-01','banlist_sha256':'a'*64},'assets':{'engine_sha256':'b'*64,'cdb_sha256':'c'*64,'scripts_sha256':'d'*64}},'request':{'deck':{'main':[101]*40,'extra':[],'side':[]}}}
        from collections import Counter
        from ygo_eval.information_audit import PINS, STATIC_PINS
        result = {'schema_version':1,'kind':'information-study','study_id':'rabbit-idle-information-v1','observation_profile':'rabbit-idle-observation-v1','seed_role':'reproduction_only','proof_ready':False,'complete_action_coverage':False,'global_optimality':False,'static_sources':[],
          'frozen_input':{'case_sha256':'699227e0a1fc3a5a45260f6720058d0acb4427a442b78d1c46f680cfdb63e5d1','request_sha256':'f9493273cd830eb4b99da7ecd9492145727664b50c3433d24b432d56d17665cd','frozen_source_sha256':'de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879','rules':frozen['case']['rules'],'assets':frozen['case'].get('assets',{})},
          'public':{'rules':{k:frozen['case']['rules'][k] for k in ('region','version')},'objective':{'id':'rabbit-own-face-up-xyz-v1','normal_min':0,'normal_max':7,'early_win':8,'loss':-2,'draw':-1,'boundary':'first-next-turn-process-return-v1'},'known_deck_composition':{k:dict(Counter(map(str,v))) for k,v in frozen['request']['deck'].items()},'initial_public_state':{'own_player':0,'lp':[8000,8000],'turn':1,'turn_player':0,'own_hand_count':5,'opponent_hand_count':0,'empty_field':True,'opponent_deck_model':'copy-own-main'}},
          'evidence':[{'role':'frozen-input','category':'frozen_input','scope':'source','sha256':'de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879'}]}

        result['evidence'] += [{'role':r,'sha256':h,'category':'historical_native','scope':'inventory' if r in ('rabbit-full','tournament-full') else 'projection'} for r,h in PINS.items()]
        result['evidence'] += [{'role':r,'sha256':h,'category':'static_source','scope':'static'} for r,h in STATIC_PINS.items()]
        result['static_sources'] = [{'role':r,'sha256':h,'commit':'38d04c9feb1a26617407091380634c87262fe3f8'} for r,h in STATIC_PINS.items()]
        return result

    def test_contract_schema_and_private_declarations(self):
        from test_schemas import validator
        value=self.contract();validate_contract(value)
        validator('information-study.schema.json').validate(value)
        for mutate in ('seed','checkpoint','source_sha256','prompt_id'):
            bad=copy.deepcopy(value);bad['public']['objective'][mutate]=1
            with self.assertRaises(ValueError):validate_contract(bad)
        for key in ('proof_ready','global_optimality','complete_action_coverage'):
            bad=copy.deepcopy(value);bad[key]=True
            with self.assertRaises(ValueError):validate_contract(bad)

    def test_missing_source_and_rules_mismatch(self):
        value=self.contract();value['evidence']=[]
        with self.assertRaises(ValueError):validate_contract(value)
        value=self.contract();value['public']['rules']['version']='different'
        with self.assertRaises(ValueError):validate_contract(value)

    def test_schema_rejects_positive_qualifications(self):
        from test_schemas import validator
        schema=validator('information-audit.schema.json')
        self.assertTrue(list(schema.iter_errors({'schema_version':1,'kind':'information-audit','native_calls':1,'proof_ready':True})))

class InformationIOTests(unittest.TestCase):
    def test_exclusive_output_and_source_drift_failure_report(self):
        from ygo_eval.information_audit import audit_information, hashed
        from test_coverage_language import temporary_directory
        from test_schemas import validator
        with temporary_directory() as tmp:
            folder=Path(tmp)
            contract=folder/'contract.json';samples=folder/'samples.json';evidence=folder/'evidence.json';output=folder/'output.json'
            contract.write_text('{}');samples.write_text('{"schema_version":1,"kind":"information-policy-samples","samples":[{}]}');evidence.write_text('{"runs":[]}')
            declaration={'evidence':[{'role':'synthetic','sha256':hashed(evidence.read_bytes()),'scope':'inventory','category':'synthetic'}],'public':{}}
            source={'identity':'0'*64}
            with patch('ygo_eval.information_audit.checked_output',side_effect=lambda _,p:Path(p)),patch('ygo_eval.information_audit.stable_source',side_effect=[source,{'identity':'1'*64}]),patch('ygo_eval.information_audit.validate_contract',return_value=declaration),patch('subprocess.run',side_effect=AssertionError('no process')):
                result=audit_information(contract,samples,['synthetic='+str(evidence)],output)
            self.assertFalse(result['successful']);self.assertEqual(result['native_calls'],0)
            validator('information-audit.schema.json').validate(result)
            self.assertEqual(result['diagnostics'][-1]['reason'],'input_or_source_changed_during_capture')
            before=output.read_bytes()
            with patch('ygo_eval.information_audit.checked_output',side_effect=lambda _,p:Path(p)):
                with self.assertRaises(ValueError):audit_information(contract,samples,[],output)
            self.assertEqual(before,output.read_bytes())

    def test_malformed_input_is_saved_and_does_not_write_source(self):
        from ygo_eval.information_audit import audit_information
        from test_coverage_language import temporary_directory
        with temporary_directory() as tmp:
            folder=Path(tmp);contract=folder/'contract.json';samples=folder/'samples.json';output=folder/'output.json'
            contract.write_text('{"schema_version":1,"schema_version":2}');samples.write_text('{}')
            before=contract.read_bytes()
            with patch('ygo_eval.information_audit.checked_output',side_effect=lambda _,p:Path(p)),patch('ygo_eval.information_audit.stable_source',return_value={'identity':'0'*64}),patch('subprocess.run',side_effect=AssertionError('no process')):
                result=audit_information(contract,samples,[],output)
            self.assertFalse(result['successful']);self.assertEqual(contract.read_bytes(),before)
            self.assertEqual(result['diagnostics'][0]['reason'],'duplicate_json_key')

    def test_historical_roles_cannot_be_reclassified_or_static_forged(self):
        value=IntegrationContractTests().contract()
        value['evidence'][1]['scope']='inventory'
        with self.assertRaises(ValueError):validate_contract(value)
        value=IntegrationContractTests().contract();value['evidence'][1]['category']='synthetic'
        with self.assertRaises(ValueError):validate_contract(value)
        value=IntegrationContractTests().contract();value['static_sources'][0]['sha256']='f'*64
        with self.assertRaises(ValueError):validate_contract(value)


class VersionTests(unittest.TestCase):
    def test_runtime_rejects_boolean_version_and_wrong_study(self):
        for key,value in [('schema_version',True),('study_id','other')]:
            contract=IntegrationContractTests().contract();contract[key]=value
            with self.assertRaises(ValueError):validate_contract(contract)
