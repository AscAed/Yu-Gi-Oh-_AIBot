"""Pure, fail-closed projection of the restricted shuffle/end observation route."""
import copy

from .information_projection import _Reader, _digest, _integer, project_prefix

PROFILE = 'rabbit-shuffle-end-observation-v1'


def _action(decisions, resolved, index, routing, menu):
    if not isinstance(decisions, list) or not isinstance(resolved, list):
        raise ValueError('invalid_decision_records')
    if index >= len(decisions) or index >= len(resolved):
        raise ValueError('missing_own_action')
    if not _integer(routing['prompt_id']) or routing['prompt_id'] <= 0:
        raise ValueError('invalid_prompt_route_id')
    action = decisions[index]
    resolution = resolved[index]
    for item in (action, resolution):
        if (not isinstance(item, dict) or not _integer(item.get('player'))
                or item['player'] != 0 or not _integer(item.get('prompt_id'))
                or item['prompt_id'] != routing['prompt_id']):
            raise ValueError('action_prompt_route_mismatch')
    matches = [entry for entry in menu if _digest(entry['choice']) == _digest(action.get('choice'))]
    if len(matches) != 1 or _digest(resolution.get('choice')) != _digest(action.get('choice')):
        raise ValueError('illegal_or_unresolved_own_action')
    selected = matches[0]
    for item in (action, resolution):
        if 'bytes' in item and _digest(item['bytes']) != _digest(selected['bytes']):
            raise ValueError('action_bytes_mismatch')
    return {'kind': 'own_action', 'player': 0, 'choice': copy.deepcopy(selected['choice']),
            'bytes': selected['bytes'][:]}


def project_route(events: list, public: dict, decisions: list,
                  resolved_decisions: list, terminal_evaluation: dict | None = None) -> dict:
    """Decode only the witnessed route; terminal evidence is separately authenticated.

    Prompt identifiers bind recorded actions to raw menus and never enter strategy keys.
    No queries, processes, files, or production message parser are used here.
    """
    result = {'views': [], 'gaps': [], 'private_audit': [],
              'route_complete': False, 'terminal_bound': False}
    if not isinstance(events, list):
        result['gaps'].append({'event_index': None, 'reason': 'invalid_events'})
        return result
    prefix = project_prefix(events[:9], public)
    actions = []
    for index, observation in enumerate(prefix['views']):
        view = copy.deepcopy(observation['view'])
        view['profile'] = PROFILE
        if actions:
            view['visible_history'].insert(7, actions[0])
        result['views'].append({'kind': 'decision', 'view': view,
                                'observation_key': _digest(view), 'routing': observation['routing']})
        try:
            action = _action(decisions, resolved_decisions, index, observation['routing'], view['legal_menu'])
            if action['choice']['command'] != (8 if index == 0 else 7):
                raise ValueError('own_action_outside_shuffle_end_route')
            actions.append(action)
        except (ValueError, TypeError, KeyError) as exc:
            result['gaps'].append({'event_index': observation['routing']['event_index'], 'reason': str(exc)})
            return result
    result['gaps'].extend(prefix['gaps'])
    if result['gaps']:
        return result
    if len(actions) != 2 or len(decisions) != 2 or len(resolved_decisions) != 2:
        result['gaps'].append({'event_index': 9, 'reason': 'incomplete_or_extra_own_actions'})
        return result
    expected = [[2,1,1,23,0,0,0,0,0,0,0],
                [16,1,0,0,0,0,0,0,4,0,0,0,0,0,0,0], [41,0,2], [40,1]]
    for offset, raw in enumerate(expected):
        ordinal = offset + 9
        try:
            if ordinal >= len(events):
                raise ValueError('incomplete_shuffle_end_route')
            event = events[ordinal]
            if not isinstance(event, dict) or not isinstance(event.get('fields', {}), dict):
                raise ValueError('invalid_event_metadata')
            reader = _Reader(event.get('raw'))
            if event.get('opcode') != raw[0] or list(reader.take(len(raw))) != raw:
                raise ValueError('unsupported_shuffle_end_message')
            reader.finish()
            fields = event.get('fields', {})
            if offset == 1:
                prompt = fields.get('prompt')
                if 'prompt' in fields:
                    if (not isinstance(prompt, dict) or prompt.get('player') != 1 or prompt.get('opcode') != 16
                            or not isinstance(prompt.get('actions'), list) or len(prompt['actions']) != 1):
                        raise ValueError('invalid_private_chain_metadata')
                    item = prompt['actions'][0]
                    if (not isinstance(item, dict) or item.get('choice') != {'kind':'chain','index':None}
                            or item.get('bytes') != [255,255,255,255]):
                        raise ValueError('invalid_private_chain_metadata')
            elif 'prompt' in fields:
                raise ValueError('unexpected_prompt_metadata')
            if offset < 2:
                result['private_audit'].append({'event_index': ordinal, 'kind': 'opponent_hint' if offset == 0 else 'empty_nonforced_opponent_chain',
                                                'validated': True})
        except (ValueError, TypeError, KeyError) as exc:
            result['gaps'].append({'event_index': ordinal, 'reason': str(exc)})
            return result
    if len(events) != 13:
        result['gaps'].append({'event_index': 13, 'reason': 'extra_after_terminal_boundary'})
        return result
    result['route_complete'] = True
    evaluation = terminal_evaluation
    bound = (isinstance(evaluation, dict) and evaluation.get('binding_valid') is True
             and _integer(evaluation.get('count')) and evaluation['count'] == 0
             and _integer(evaluation.get('utility')) and evaluation['utility'] == 0
             and evaluation.get('termination') == 'terminal_boundary_bound'
             and evaluation.get('diagnostics', []) == [])
    result['terminal_bound'] = bound
    view = copy.deepcopy(result['views'][-1]['view'])
    view.update(phase=None, turn=2, turn_player=1, legal_menu=[],
                normal_count=0 if bound else None, normal_utility=0 if bound else None,
                termination='terminal_boundary_bound' if bound else 'unknown')
    view['visible_history'].extend([actions[1], {'kind':'new_phase','phase':512}, {'kind':'new_turn','player':1}])
    result['views'].append({'kind':'terminal', 'view':view, 'observation_key':_digest(view),
                            'routing':{'event_index':12,'prompt_id':None}})
    if not bound:
        result['gaps'].append({'event_index':12,'reason':'terminal_evaluation_unbound'})
    return result
