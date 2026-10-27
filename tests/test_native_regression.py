import unittest
import copy
from ygo_eval.native_regression import derive_request, check_observations, immutable_write
from pathlib import Path
from test_coverage_language import temporary_directory
from test_schemas import validator


class NativeRegressionTests(unittest.TestCase):
    def test_derivation_uses_parent_public_prompt_only(self):
        request = {'decisions': []}
        result = {'prompt': {'id': 37, 'player': 0, 'opcode': 11, 'actions': [
            {'choice': {'kind': 'command', 'command': 8, 'index': 0}, 'bytes': [8, 0, 0, 0]}]}}
        import copy
        result['events'] = [{'sequence':37,'opcode':11,'raw':[11,0]+[0]*24+[0,0,1],
                             'fields':{'prompt':copy.deepcopy(result['prompt'])}}]
        derived = derive_request(request, result, 8)
        self.assertEqual(derived['decisions'], [{'prompt_id': 37, 'player': 0,
            'choice': {'kind': 'command', 'command': 8, 'index': 0}}])
        self.assertEqual(request['decisions'], [])
        with self.assertRaises(ValueError): derive_request(request, result, 7)
        tampered = copy.deepcopy(result); tampered['prompt']['id'] = 38
        with self.assertRaises(ValueError): derive_request(request,tampered,8)
        result['prompt']['actions'][0]['bytes'] = [7, 0, 0, 0]
        with self.assertRaises(ValueError): derive_request(request, result, 8)

    def test_shuffle_requires_message_multiset_and_closed_option(self):
        parent = {'events':[], 'checkpoint': {'cards': [{'player':0,'location':2,'code':7}, {'player':0,'location':2,'code':9}]}}
        child = {'checkpoint': {'cards': [{'player':0,'location':2,'code':9}, {'player':0,'location':2,'code':7}]},
                 'events':[{'raw':[33,0,2,0,0,0,9,0,0,0,7,0,0,0]}], 'prompt': {'player':0,'opcode':11,'actions':[]}}
        self.assertTrue(check_observations('rabbit-shuffle',child,parent))
        child['checkpoint']['cards'][0]['code'] = 8
        with self.assertRaises(ValueError): check_observations('rabbit-shuffle',child,parent)

    def test_shuffle_checks_only_new_suffix_after_exact_parent_history(self):
        message = {'sequence':1,'opcode':33,'raw':[33,0,2,0,0,0,7,0,0,0,9,0,0,0]}
        parent = {'events':[copy.deepcopy(message)], 'checkpoint':{'cards':[
            {'player':0,'location':2,'code':7},{'player':0,'location':2,'code':9}]}}
        new_message = copy.deepcopy(message); new_message['sequence'] = 2
        child = {'events':parent['events']+[new_message],
                 'checkpoint':copy.deepcopy(parent['checkpoint']),
                 'prompt':{'player':0,'opcode':11,'actions':[]}}
        self.assertTrue(check_observations('rabbit-shuffle',child,parent))
        changed_prefix = copy.deepcopy(child)
        changed_prefix['events'][0]['raw'][-1] = 1
        with self.assertRaises(ValueError): check_observations('rabbit-shuffle',changed_prefix,parent)
        extra_message = copy.deepcopy(child); extra_message['events'].append(copy.deepcopy(new_message))
        with self.assertRaises(ValueError): check_observations('rabbit-shuffle',extra_message,parent)

    def test_boundary_requires_raw_end_and_next_turn(self):
        result = {'events':[{'raw':[41,0,2]},{'raw':[40,1]}]}
        self.assertTrue(check_observations('rabbit-end', result, None))
        result['events'].pop()
        with self.assertRaises(ValueError): check_observations('rabbit-end',result,None)

    def test_immutable_intent_never_overwrites(self):
        with temporary_directory() as root:
            path = Path(root)/'intent.json'
            immutable_write(path, {'request':1})
            immutable_write(path, {'request':1})
            with self.assertRaises(ValueError): immutable_write(path, {'request':2})

    def test_report_contract_cannot_upgrade_qualifications_or_budget(self):
        report = {'schema_version':1,'kind':'native_regression_summary','context':'a'*64,
                  'cases':[],'successful':False,'diagnostic':'incomplete','old_consumed':9,
                  'new_consumed':0,'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        check = validator('native-regression.schema.json')
        check.validate(report)
        for key,value in [('new_consumed',17),('old_consumed',0),('proof_ready',True),('complete_action_coverage',True),('global_optimality',True)]:
            invalid = dict(report); invalid[key] = value
            self.assertTrue(list(check.iter_errors(invalid)),key)


if __name__ == '__main__': unittest.main()
