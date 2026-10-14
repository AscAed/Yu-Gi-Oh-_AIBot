"""Regenerate goal contracts, reusing the frozen v2 evidence definitions."""
import copy
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'schemas'
DRAFT = 'https://json-schema.org/draft/2020-12/schema'
def obj(props, required=None):
    return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
def arr(items, **limits): return {'type':'array','items':items,**limits}
def ref(name): return {'$ref':f'#/$defs/{name}'}
def nullable(x): return {'anyOf':[x,{'type':'null'}]}
def write(name, value): (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
S={'type':'string'}; I={'type':'integer','minimum':0}; B={'type':'boolean'}
H={'type':'string','pattern':'^[a-f0-9]{64}$'}
F=obj({'codes':arr({'type':'integer','minimum':1,'maximum':4294967295},maxItems=120),'player':{'enum':[0,1]},'locations':arr({'enum':[1,2,4,8,16,32,64]},maxItems=7),'position_mask':nullable({'type':'integer','minimum':1,'maximum':15}),'instance':nullable(S),'level':nullable(I),'rank':nullable(I),'proper_xyz':nullable(B),'materials_min':nullable({'type':'integer','minimum':0,'maximum':60}),'material_codes':arr(I,maxItems=60)},[])
G=obj({'id':{'type':'string','minLength':1},'filter':ref('filter'),'min_delta':{'type':'integer'}})
def node(op,props,required=None):
    p={'op':{'const':op},**props}
    return obj(p, ['op']+(list(props) if required is None else required))
defs={'filter':F,'gain':G}
for depth in reversed(range(8)):
    for factual in [False,True]:
        name=('fact' if factual else 'expr')+str(depth)
        choices=[node('count',{'filter':ref('filter'),'min':I,'max':nullable(I)},['filter','min']),node('history',{'kind':{'enum':['normal_summon','special_summon','link_summon','xyz_summon','destroyed','sent_to_grave','effect_resolved']},'filter':ref('filter'),'effect_id':nullable(S),'reason_mask':nullable(I),'min':I,'max':nullable(I)},['kind','min'])]
        if not factual:
            choices.append(node('available',{'effect_id':{'type':'string','minLength':1},'filter':ref('filter'),'window':{'type':'string','minLength':1}}))
        if depth<7:
            child=ref(('fact' if factual else 'expr')+str(depth+1))
            choices += [node(op,{'args':arr(child,minItems=1,maxItems=64)}) for op in ['all','any']]
            choices.append(node('not',{'arg':child}))
            if not factual:
                choices.append(node('continuation',{'goal':ref('fact'+str(depth+1)),'gains':arr(ref('gain'),maxItems=64),'max_steps':nullable({'type':'integer','minimum':1,'maximum':8})},['goal']))
        defs[name]={'oneOf':choices}
goal=obj({'version':{'const':1},'expr':ref('expr0'),'continuation_steps':{'type':'integer','minimum':1,'maximum':8},'max_aux_candidates':{'type':'integer','minimum':1,'maximum':8},'gain_order':arr(S,maxItems=64,uniqueItems=True)},['version','expr'])
write('goal.schema.json',{'$schema':DRAFT,'title':'Goal v1',**goal,'$defs':defs})
q=json.loads((OUT/'plan-request-v2.schema.json').read_text())
q['title']='PlanRequest v3';q['properties']['schema_version']={'const':3};q['properties']['goal']={'$ref':'goal.schema.json'};q['required']=['schema_version','analysis','goal']
write('plan-request-v3.schema.json',q)
legacy=json.loads((OUT/'plan-result-v2.schema.json').read_text())
d=copy.deepcopy(legacy['$defs'])
d['proposal']['properties']['steps']['minItems']=0;d['proposal']['properties']['goal_predicted']=B
trace=copy.deepcopy(d['attempt'])
for old,new in [('goal_achieved','execution_verified'),('line_id','execution_id')]:
    trace['properties'][new]=trace['properties'].pop(old);trace['required']=[new if x==old else x for x in trace['required']]
d['trace']=trace
truth={'enum':['yes','no','unknown']}
d['evaluation']=obj({'node':S,'result':truth,'observed':nullable({'type':'integer'}),'matches':arr(S),'reason':S,'children':arr(ref('evaluation'),maxItems=64)})
d['fact_card']=obj({'instance':S,'identity_known':B,'type_flags':I,'code':I,'player':{'enum':[0,1]},'location':I,'sequence':I,'position':I,'level':nullable(I),'rank':nullable(I),'proper_xyz':nullable(B),'materials':arr(I)})
d['history_fact']=obj({'kind':S,'card':ref('fact_card'),'effect_id':nullable(S),'reason':I,'reason_complete':B,'event':I})
d['facts']=obj({'known_effects':arr(S),'cards':arr(ref('fact_card')),'history':arr(ref('history_fact')),'history_complete':B})
combo=json.loads((OUT/'combo-result-v3.schema.json').read_text())
d['runtime']=copy.deepcopy(combo['properties']['runtime_request'])
# Runtime uses absolute schema references; preserve their frozen contract.
d['forecast']=obj({'kind':{'const':'symbolic_prediction'},'proposal_id':H,'semantic_step':I,'effect_id':S,'before':ref('facts'),'goal_before':ref('evaluation'),'goal_after':ref('evaluation'),'branch_before':nullable(ref('evaluation')),'branch_after':nullable(ref('evaluation')),'missing_nodes':arr(S),'contribution_nodes':arr(S),'lost_nodes':arr(S),'consumers':arr(S),'gain_prediction':{'type':'object','additionalProperties':{'type':'integer'}}})
d['execution']=obj({'id':S,'purpose':S,'runtime':ref('runtime'),'proposal':ref('proposal'),'trace':ref('trace'),'facts':ref('facts')})
metric={'type':'object','additionalProperties':{'type':'integer'}}
d['probe']=obj({'node':S,'anchor':S,'result':ref('evaluation'),'candidates':arr(I,maxItems=8),'best':nullable(I),'gains':metric,'lost_conditions':arr(S),'reason':S,'expansion_start':I,'expansion_end':I,'attempted':I,'plans':arr(ref('proposal'),maxItems=8)})
d['assessment']=obj({'execution':I,'evaluation':ref('evaluation'),'probes':arr(ref('probe'),maxItems=64),'verification':{'enum':['unverified','engine_observed','independently_replayed']}})
d['recommendation']=obj({'id':H,'execution_id':H,'execution':I,'evaluation':ref('evaluation'),'probes':arr(ref('probe'),maxItems=64),'gains':metric,'witness_ids':arr(H,uniqueItems=True)})
d['witness']=obj({'runtime':ref('runtime'),'events':d['observation']['properties']['events'],'checkpoint':d['observation']['properties']['checkpoint'],'decisions':arr(ref('decision')),'status':d['observation']['properties']['status'],'replay_verified':B,'steps':d['observation']['properties']['steps'],'loaded_scripts':nullable({'type':'object','additionalProperties':S})})
d['ledger']=obj({k:I for k in ['limit','used_calls','reserved_calls','main_calls','auxiliary_calls','witness_calls','expansions','aux_candidates']})
report=obj({'schema_version':{'const':3},'planner_profile':{'const':'phantom-goal-v1'},'goal_id':{'type':'string','pattern':'^goal-[a-f0-9]{64}$'},'knowledge_id':legacy['properties']['knowledge_id'],'knowledge':legacy['properties']['knowledge'],'request':{'$ref':'plan-request-v3.schema.json'},'proposals':ref('proposals'),'executions':arr(ref('execution')),'catalog_projection':{'type':'object','additionalProperties':{'$ref':'card.schema.json#/properties/cards/items'}},'forecasts':{'type':'object','propertyNames':H,'additionalProperties':arr(ref('forecast'),maxItems=32)},'assessments':arr(ref('assessment'),maxItems=8),'recommendations':arr(ref('recommendation'),maxItems=8),'witnesses':{'type':'object','propertyNames':H,'additionalProperties':ref('witness')},'ledger':ref('ledger'),'analysis':{'$ref':'combo-result-v3.schema.json'},'failure_summary':legacy['properties']['failure_summary']})
write('plan-result-v3.schema.json',{'$schema':DRAFT,'title':'PlanReport v3',**report,'$defs':d})
