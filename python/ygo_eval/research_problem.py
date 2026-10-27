"""Independent state-objective candidate contract, never a proof admission."""
import re
from ygo_data.identity import canonical, digest
from ygo_eval.research import _object, validate_case

OBJECTIVE = {'id':'rabbit-own-face-up-xyz-v1', 'normal_min':0, 'normal_max':7,
             'early_win':8, 'loss':-2, 'draw':-1}
CONDITIONS = ('hidden_information', 'probability', 'action_ordering', 'loops',
              'tree_size', 'necessary_actions')


def validate_problem(problem: dict) -> dict:
    """Validate a frozen candidate and report unresolved proof prerequisites."""
    _object(problem, ('schema_version','kind','problem_id','status','input','objective',
                      'termination','seed_semantics','conditions'), 'research problem')
    if type(problem['schema_version']) is not int or problem['schema_version'] != 1 or problem['kind'] != 'research_problem' or problem['status'] != 'candidate' or not isinstance(problem['problem_id'], str) or not re.fullmatch(r'[A-Za-z0-9-]+', problem['problem_id']):
        raise ValueError('unsupported candidate research problem')
    inputs = problem['input']
    _object(inputs, ('frozen_case_v1','case_sha256','request_sha256','frozen_source_sha256'), 'frozen input')
    for key in ('case_sha256','request_sha256','frozen_source_sha256'):
        if not isinstance(inputs[key], str) or not re.fullmatch('[a-f0-9]{64}', inputs[key]):
            raise ValueError('invalid source content hash')
    validate_case(inputs['frozen_case_v1'])
    if inputs['case_sha256'] != digest(canonical(inputs['frozen_case_v1'])):
        raise ValueError('frozen case content identity mismatch')
    if problem['objective'] != OBJECTIVE or any(type(problem['objective'][k]) is not int for k in ('normal_min','normal_max','early_win','loss','draw')):
        raise ValueError('unsupported state objective')
    if problem['termination'] != {'normal':'first-next-turn-process-return-v1','natural_end_has_successors':False} or type(problem['termination'].get('natural_end_has_successors')) is not bool:
        raise ValueError('explicit terminal boundary required')
    if problem['seed_semantics'] != 'reproduction_only':
        raise ValueError('seed cannot establish determinism')
    _object(problem['conditions'], CONDITIONS, 'proof conditions')
    blockers = []
    for key in CONDITIONS:
        condition = problem['conditions'][key]
        _object(condition, ('resolved','reason'), 'proof condition')
        if type(condition['resolved']) is not bool or not isinstance(condition['reason'], str) or not condition['reason'].strip():
            raise ValueError('condition requires explicit status and reason')
        if not condition['resolved']:
            blockers.append({'condition':key, 'reason':condition['reason']})
    return {'schema_version':1, 'problem_id':problem['problem_id'], 'input_complete':True,
            'problem_sha256':digest(canonical(problem)), 'blockers':blockers,
            'source_authenticity_verified':False, 'legality_verified':False,
            'proof_ready':False, 'complete_action_coverage':False, 'global_optimality':False}
