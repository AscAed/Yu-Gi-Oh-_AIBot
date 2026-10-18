"""Opt-in engine diagnostic: follow explicit Rabbit choices and save every checkpoint."""
import json
import hashlib
import subprocess
from pathlib import Path
import argparse

p = argparse.ArgumentParser()
p.add_argument('--exit', choices=['pass', 'normal', 'rabbit', 'xyz', 'link'], default='xyz')
args = p.parse_args()
fixture = json.loads(Path('tests/fixtures/rabbit.request.json').read_text())
if args.exit == 'normal':
    fixture['opening_hand'][-1]=69247929
h = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
r = {'protocol_version': 2, 'engine': {}, 'deck': fixture['deck'], 'opening_hand': fixture['opening_hand'], 'seed': 1, 'decisions': [], 'versions': {'rules': 'ocg-mr5', 'initializer': 'fixed-hand-shuffle-v1', 'catalog': '', 'banlist': '', 'core_commit': '38d04c9feb1a26617407091380634c87262fe3f8', 'engine_sha256': h('data/runtime/engine/ocgcore.dll'), 'cdb_sha256': h('data/runtime/cards.cdb'), 'scripts_sha256': h('data/runtime/scripts.json')}, 'probe_only': False}
for step in range(64):
    proc = subprocess.run(['target/debug/ygo-engine-worker.exe'], input=json.dumps(r)+'\n', text=True, capture_output=True, timeout=30)
    if proc.returncode: raise RuntimeError(proc.stderr)
    v = json.loads(proc.stdout)
    r['decisions']=v.get('resolved_decisions',r['decisions'])
    Path(f'data/tmp/probe-{args.exit}.json').write_text(json.dumps({'request': r, 'result': v}, indent=2))
    if v['status'] != 'decision_required':
        print(v['status'], v['error'], 'gaps', v['coverage_gaps'])
        print('board', [(c['code'], c['overlay']) for c in v['checkpoint']['cards'] if c['player']==0 and c['location']==4])
        print('unknown', [(e['opcode'],len(e['raw'])) for e in v['events'] if not e['supported']])
        break
    prompt = v['prompt']; actions = prompt['actions']
    chosen = None
    if args.exit == 'normal':
        chosen=next((a for a in actions if a['choice']['kind']=='command' and a['choice']['command']==0 and 69247929 in a['card_ids']),None)
    if args.exit not in ['pass','normal']:
        for a in actions:
            c = a['choice']
            if c['kind']=='command' and c['command'] in [0,5] and 85138716 in a['card_ids']: chosen=a; break
        if chosen is None and args.exit in ['xyz','link']:
            target = 84013237 if args.exit == 'xyz' else 77637979
            chosen=next((a for a in actions if a['choice']['kind']=='command' and a['choice']['command']==1 and target in a['card_ids']), None)
    if chosen is None:
        chosen=next((a for a in actions if a['choice']['kind']=='command' and a['choice']['command']==7), None)
    if chosen is None:
        chosen=next((a for a in actions if a['choice']['kind']=='chain' and a['choice']['index'] is None), None)
    if chosen is None:
        if prompt['opcode']==26:
            frame=v['events'][-1]['raw']
            chosen=next((a for a in actions if a['choice']['kind']=='finish' and frame[2]), None)
            if chosen is None: chosen=next((a for a in actions if a['choice']['kind']=='toggle'), None)
        else:
            chosen=next((a for a in actions if a['choice']['kind']=='finish'), None)
    if chosen is None: chosen=actions[0]
    print(step, prompt['opcode'], chosen['label'])
    r['decisions'].append({'prompt_id':prompt['id'],'player':prompt['player'],'choice':chosen['choice']})
else: raise RuntimeError('depth exhausted')
