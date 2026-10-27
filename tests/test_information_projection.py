import copy
import unittest
from ygo_eval.information_projection import project_prefix, check_policy_samples

def event(raw,seq=1): return {'raw':raw,'opcode':raw[0],'sequence':seq}
def idle(seq=7, flags=(0,1,1), pos=0):
    raw=[11,0]
    for command in range(6):
        raw += list((1 if command==0 else 0).to_bytes(4,'little'))
        if command==0: raw+=list((123).to_bytes(4,'little'))+[0,2]+list(pos.to_bytes(4,'little'))
    return event(raw+list(flags),seq)
def prefix():
    return [event([40,0]),event([33,0,5,0,0,0]+[123,0,0,0]*5),event([41,1,0]),event([2,1,0,27,0,0,0,0,0,0,0]),event([41,2,0]),event([41,4,0]),idle()]
PUBLIC={'rules':{'region':'OCG','version':'frozen'},'objective':{'id':'rabbit-own-face-up-xyz-v1','normal_min':0,'normal_max':7,'early_win':8,'loss':-2,'draw':-1,'boundary':'first-next-turn-process-return-v1'},'known_deck_composition':{'main':{'123':5},'extra':{},'side':{}},'initial_public_state':{'own_player':0,'lp':[8000,8000],'turn':1,'turn_player':0,'own_hand_count':5,'opponent_hand_count':0,'empty_field':True,'opponent_deck_model':'copy-own-main'}}
class ProjectionTests(unittest.TestCase):
    def test_raw_projection_excludes_private_metadata(self):
        e=prefix(); a=project_prefix(e,PUBLIC)['views'][0]
        for x in e: x.update(seed=999,checkpoint={'cards':['hidden']},source_hash='secret',sequence=900)
        b=project_prefix(e,PUBLIC)['views'][0]
        self.assertEqual(a['observation_key'],b['observation_key'])
        self.assertEqual(a['view']['phase'],4)
        self.assertEqual(a['view']['own_hand'],[{'code':123,'position':i} for i in range(5)])
    def test_order_menu_history_change_key(self):
        a=project_prefix(prefix(),PUBLIC)['views'][0]['observation_key']
        p=prefix();p[-1]=idle(flags=(0,0,1));self.assertNotEqual(a,project_prefix(p,PUBLIC)['views'][0]['observation_key'])
        p=prefix();p[-1]=idle(pos=1);self.assertNotEqual(a,project_prefix(p,PUBLIC)['views'][0]['observation_key'])
    def test_unknown_blocks_and_bad_index_rejected(self):
        p=prefix();p.insert(2,event([99]));r=project_prefix(p,PUBLIC);self.assertFalse(r['views']);self.assertTrue(r['gaps'])
        p=prefix();p[-1]=idle(pos=5);self.assertFalse(project_prefix(p,PUBLIC)['views'])
    def test_forged_prompt_rejected(self):
        p=prefix();p[-1]['fields']={'prompt':{'actions':[]}};self.assertFalse(project_prefix(p,PUBLIC)['views'])
    def test_policy_groups_and_exact_distribution(self):
        obs={'a':project_prefix(prefix(),PUBLIC)['views'][0]}
        def s(policy,word):return {'policy_id':policy,'observation_id':'a','distribution':[{'bytes':[word,0,0,0],'numerator':1,'denominator':1}]}
        self.assertTrue(check_policy_samples([s('x',0),s('y',7)],obs)['valid'])
        self.assertFalse(check_policy_samples([s('x',0),s('x',7)],obs)['valid'])
        self.assertFalse(check_policy_samples([s('x',99)],obs)['valid'])
        bad=s('x',0);bad['distribution'][0]['denominator']=2;self.assertFalse(check_policy_samples([bad],obs)['valid'])
    def test_second_idle_and_no_later_projection(self):
        p=prefix();p += [event([33,0,5,0,0,0]+[123,0,0,0]*5),idle(9,(0,1,0))]
        self.assertEqual(len(project_prefix(p,PUBLIC)['views']),2)
        p += [event([41,0,2]),idle(10)]
        self.assertEqual(len(project_prefix(p,PUBLIC)['views']),2)
    def test_hand_order_is_visible_and_private_changes_are_not(self):
        p=prefix(); p[1]['raw'][10:14]=[124,0,0,0]
        a=project_prefix(p,PUBLIC)['views'][0]
        q=copy.deepcopy(p);q[1]['raw'][6:10],q[1]['raw'][10:14]=q[1]['raw'][10:14],q[1]['raw'][6:10]
        q[-1]['raw'][6:10]=[124,0,0,0]
        b=project_prefix(q,PUBLIC)['views'][0]
        self.assertNotEqual(a['observation_key'],b['observation_key'])
        self.assertNotEqual(a['view']['visible_history'],b['view']['visible_history'])
    def test_hint_phase_and_trailing_bytes_rejected(self):
        for ordinal,offset,value in [(3,3,28),(2,1,4)]:
            p=prefix();p[ordinal]['raw'][offset]=value
            self.assertFalse(project_prefix(p,PUBLIC)['views'])
        p=prefix();p[-1]['raw'].append(0);self.assertFalse(project_prefix(p,PUBLIC)['views'])
    def test_projection_and_policy_do_not_start_processes(self):
        from unittest.mock import patch
        with patch('subprocess.Popen',side_effect=AssertionError('process forbidden')):
            o=project_prefix(prefix(),PUBLIC)['views'][0]
            self.assertTrue(check_policy_samples([],{'a':o})['valid'])
    def test_fraction_normalization_and_duplicate_negative_entries(self):
        obs={'a':project_prefix(prefix(),PUBLIC)['views'][0]}
        def sample(items):return {'policy_id':'x','observation_id':'a','distribution':items}
        def item(n,d=1):return {'bytes':[7,0,0,0],'numerator':n,'denominator':d}
        self.assertTrue(check_policy_samples([sample([item(1)]),sample([item(2,2)])],obs)['valid'])
        for items in ([item(1),item(0)], [item(-1)], [item(1,0)]):
            self.assertFalse(check_policy_samples([sample(items)],obs)['valid'])
    def test_nested_hidden_public_data_and_truncation_rejected(self):
        public=copy.deepcopy(PUBLIC);public['rules']['seed']=42
        self.assertTrue(project_prefix(prefix(),public)['gaps'])
        self.assertTrue(project_prefix(prefix()[:-1],PUBLIC)['gaps'])
    def test_public_declaration_is_copied(self):
        public=copy.deepcopy(PUBLIC);r=project_prefix(prefix(),public)
        public['rules']['version']='changed'
        self.assertNotEqual(r['views'][0]['view']['rules']['version'],'changed')
    def test_malformed_recorded_metadata_produces_gap(self):
        for fields in (None, [], {'prompt':None}, {'prompt':[]}, {'prompt':{'actions':17}}, {'prompt':{'actions':[3]}}):
            p=prefix();p[-1]['fields']=fields
            self.assertTrue(project_prefix(p,PUBLIC)['gaps'])
        for malformed in (None, [], 3):
            self.assertTrue(project_prefix([malformed],PUBLIC)['gaps'])
if __name__=='__main__':unittest.main()
