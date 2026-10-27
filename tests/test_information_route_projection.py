import copy
import unittest
from unittest.mock import patch
from test_information_projection import PUBLIC, prefix, event, idle
from ygo_eval.information_route_projection import project_route


def fixture():
    events = prefix() + [event([33,0,5,0,0,0]+[123,0,0,0]*5), idle(9,(0,1,0)),
        event([2,1,1,23,0,0,0,0,0,0,0]),
        event([16,1,0,0,0,0,0,0,4,0,0,0,0,0,0,0],11), event([41,0,2]),event([40,1])]
    decisions = [{'prompt_id':p,'player':0,'choice':{'kind':'command','command':c,'index':0}} for p,c in [(7,8),(9,7)]]
    return events, copy.deepcopy(PUBLIC), decisions, copy.deepcopy(decisions)

EVAL = {'binding_valid':True,'count':0,'utility':0,'termination':'terminal_boundary_bound'}

class RouteTests(unittest.TestCase):
    def test_complete_route(self):
        r=project_route(*fixture(),EVAL)
        self.assertEqual(r['gaps'],[])
        self.assertTrue(r['route_complete']);self.assertTrue(r['terminal_bound'])
        self.assertEqual([v['kind'] for v in r['views']],['decision','decision','terminal'])
        v=r['views'][-1]['view'];self.assertIsNone(v['phase']);self.assertEqual(v['turn'],2)
        self.assertEqual(v['legal_menu'],[]);self.assertEqual(v['normal_utility'],0)
        self.assertNotIn('opponent_passed',str(v));self.assertFalse(any(h.get('player') == 1 and h.get('kind') != 'new_turn' for h in v['visible_history']))
        self.assertEqual(len([h for h in v['visible_history'] if h['kind']=='own_action']),2)

    def test_private_and_route_id_invariance(self):
        args=fixture();a=project_route(*args,EVAL)
        for e in args[0]:
            e.update(seed=987,source_hash='private',checkpoint={'hidden':1})
            e['sequence']=e.get('sequence',1)+100
        for group in args[2:]:
            for d in group:d['prompt_id']+=100
        b=project_route(*args,EVAL)
        self.assertEqual([v['observation_key'] for v in a['views']],[v['observation_key'] for v in b['views']])

    def test_fail_closed_preserves_prefix(self):
        for index in (9,10,11,12):
            args=fixture();args[0][index]['raw'].append(0)
            r=project_route(*args,EVAL);self.assertFalse(r['route_complete']);self.assertFalse(r['terminal_bound'])
            self.assertEqual(len(r['views']),2);self.assertTrue(r['gaps'])
        args=fixture();args[0].append(event([99]));self.assertFalse(project_route(*args,EVAL)['terminal_bound'])

    def test_actions_must_match_and_be_available(self):
        for mutation in ('missing','illegal','bytes','resolved'):
            args=fixture()
            if mutation=='missing':args[2].pop()
            elif mutation=='illegal':args[2][0]['choice']['command']=99
            elif mutation=='bytes':args[2][0]['bytes']=[7,0,0,0]
            else:args[3][0]['choice']['command']=7
            r=project_route(*args,EVAL);self.assertFalse(r['route_complete']);self.assertTrue(r['gaps'])

    def test_evaluation_not_inferred(self):
        for value in (None,{},dict(EVAL,binding_valid=False),dict(EVAL,count=1),dict(EVAL,utility=True),dict(EVAL,diagnostics=['untrusted'])):
            r=project_route(*fixture(),value);self.assertFalse(r['terminal_bound'])
            self.assertIsNone(r['views'][-1]['view']['normal_utility'])

    def test_public_history_and_order_are_observable(self):
        args=fixture();a=project_route(*args,EVAL)
        args[1]['rules']['version']='other'
        b=project_route(*args,EVAL)
        self.assertNotEqual(a['views'][0]['observation_key'],b['views'][0]['observation_key'])
        args=fixture()
        args[0][1]['raw'][10:14]=[124,0,0,0]
        args[0][7]['raw'][10:14]=[124,0,0,0]
        a=project_route(*args,EVAL)
        args[0][7]['raw'][10:14]=[123,0,0,0]
        args[0][7]['raw'][14:18]=[124,0,0,0]
        b=project_route(*args,EVAL)
        self.assertNotEqual(a['views'][1]['observation_key'],b['views'][1]['observation_key'])

    def test_private_chain_variants_and_metadata_block(self):
        for offset in (2,3,4,5,6,7,8,9,10,11,12,13,14,15):
            args=fixture();args[0][10]['raw'][offset]^=1
            self.assertFalse(project_route(*args,EVAL)['route_complete'])
        for fields in (None, [], {'prompt':None}, {'prompt':{}}, {'prompt':{'actions':[]}}):
            args=fixture();args[0][10]['fields']=fields
            self.assertFalse(project_route(*args,EVAL)['route_complete'])
        args=fixture();args[0].pop(11)
        self.assertFalse(project_route(*args,EVAL)['route_complete'])

    def test_known_private_chain_metadata_is_audit_only(self):
        args=fixture();a=project_route(*args,EVAL)
        args[0][10]['fields']={'prompt':{'id':999,'player':1,'opcode':16,
            'actions':[{'choice':{'kind':'chain','index':None},'bytes':[255]*4,'label':'private'}]}}
        b=project_route(*args,EVAL)
        self.assertEqual(a['views'],b['views'])

    def test_inputs_are_not_mutated(self):
        args=fixture();before=copy.deepcopy(args)
        project_route(*args,EVAL)
        self.assertEqual(args,before)

    def test_boolean_action_routing_is_rejected(self):
        for group in (2, 3):
            args=fixture();args[group][0]['player']=False
            self.assertTrue(project_route(*args,EVAL)['gaps'])
            args=fixture();args[0][6]['sequence']=1
            args[2][0]['prompt_id']=1;args[3][0]['prompt_id']=True
            self.assertTrue(project_route(*args,EVAL)['gaps'])

    def test_wrong_action_order_and_extra_terminal_event_are_rejected(self):
        args=fixture();args[2].reverse();args[3].reverse()
        self.assertFalse(project_route(*args,EVAL)['route_complete'])
        args=fixture();args[0].append(event([40,0]))
        result=project_route(*args,EVAL)
        self.assertFalse(result['terminal_bound'])
        self.assertEqual([v['kind'] for v in result['views']],['decision','decision'])

    def test_no_io(self):
        args=fixture()
        with patch('builtins.open',side_effect=AssertionError('file')),patch('subprocess.Popen',side_effect=AssertionError('process')):
            self.assertTrue(project_route(*args,EVAL)['route_complete'])

if __name__=='__main__':unittest.main()
