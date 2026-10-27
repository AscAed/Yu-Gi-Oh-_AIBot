"""One frozen Rabbit pair, with an independent two-request debit scope."""
import copy
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source
from ygo_eval.terminal_regression import immutable_write

ACCEPTANCE_SHA = 'f9639df6c6f16b875f9640d8551d66d66554c3c4751dccf5a65870bb2bd1f3a1'
SOURCE_SHA = '3c6f008432d29276c302020da7a0fec2c606dfe38e6a79e432cb1c6bd8ea1014'
LEDGER_SHA = '3fd2aa6d1ff18f5eb1fe7100fe8fb4c36e9b73795e0749aa362b0bea9ea93ef2'
POLICY = {'schema_version':1,'objective':'rabbit-own-face-up-xyz-v1','boundary':'first-next-turn-process-return-v1'}


def sha(path):
    return digest(regular_file(path).read_bytes())


def validate_baseline(baseline, repo):
    """Check pinned delivery and all protected inputs before zero-call receipt verification."""
    acceptance_path = regular_file(baseline/'acceptance.json')
    if sha(acceptance_path) != ACCEPTANCE_SHA:
        raise ValueError('baseline acceptance differs')
    acceptance = json.loads(acceptance_path.read_bytes())
    checkpoint = json.loads(regular_file(baseline/'delivery-checkpoint.json').read_bytes())
    if (acceptance['source_identity'] != SOURCE_SHA or checkpoint['acceptance_sha256'] != ACCEPTANCE_SHA
            or checkpoint['source_identity'] != SOURCE_SHA or acceptance['cumulative_consumed'] != 18
            or acceptance['unknown'] != 0 or acceptance['reserved'] != 0):
        raise ValueError('baseline identity or consumption differs')
    protected = {}
    for relative, record in acceptance['evidence'].items():
        path = baseline/relative
        if not path.absolute().is_relative_to(baseline) or '..' in Path(relative).parts:
            raise ValueError('baseline evidence path escapes')
        if sha(path) != record['sha256'] or path.stat().st_size != record['bytes']:
            raise ValueError('baseline evidence differs')
        protected[path] = record['sha256']
    before = json.loads(regular_file(baseline/'before.json').read_bytes())
    for relative, expected in before['protected_files'].items():
        path = repo/relative
        if sha(path) != expected: raise ValueError('historical protected file differs')
        protected[path] = expected
    old_roots = {'old9':repo/'data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs',
                 'old8':repo/'data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs'}
    for key, files in before['blob_files'].items():
        root = old_roots[key]
        actual = {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}
        if actual != files: raise ValueError('historical blobs differ')
        protected.update({root/name:value for name,value in files.items()})
    ledger = baseline/'research/native/calls.jsonl'
    if sha(ledger) != LEDGER_SHA: raise ValueError('latest ledger differs')
    invocation = baseline/'research/native/terminal-rabbit-input.json'
    runner = baseline/'native-artifacts/terminal-regression.exe'
    native_build = json.loads(regular_file(baseline/'build-native.json').read_bytes())
    if native_build['identity'] != acceptance['native_build_identity'] or sha(runner) != native_build['artifacts']['audit']:
        raise ValueError('saved native runner differs')
    protected[runner] = native_build['artifacts']['audit']
    invocation_sha = protected[invocation]
    verified = subprocess.run([str(runner),str(invocation),'--input-sha',invocation_sha,'--verify-recorded'],capture_output=True,timeout=60)
    if any(sha(path) != value for path,value in protected.items()):
        raise ValueError('baseline changed during receipt verification')
    if verified.returncode != 0: raise ValueError('failed receipt cannot be verified')
    stats = json.loads(verified.stdout)['ledger']
    if stats['consumed'] != 1 or stats['completed'] != 1 or stats['unknown'] or stats['reserved']:
        raise ValueError('failed receipt consumption differs')
    protected[acceptance_path] = ACCEPTANCE_SHA
    protected[baseline/'delivery-checkpoint.json'] = sha(baseline/'delivery-checkpoint.json')
    return json.loads(regular_file(invocation).read_bytes()), protected


def summarize(context, pair, stats, decisions, evidence_sha):
    """Successful is possible only for two independently verified, settled outcomes."""
    diagnostic = 'runner_failed_or_outcome_unavailable' if pair is None else pair.get('diagnostic')
    if stats is None or stats.get('unknown') or stats.get('reserved'):
        diagnostic = 'unresolved_consumption'
    if pair is not None and not diagnostic:
        if any(pair.get(flag) is not False for flag in ('proof_ready','complete_action_coverage','global_optimality')):
            diagnostic = 'qualification_flags_invalid'
        audits = pair.get('prompt_audits_by_run')
        if not isinstance(audits,list) or len(audits) != 2 or any(not isinstance(group,list) or any(not isinstance(a,dict) or a.get('audit',{}).get('Ok',{}).get('matches') is not True for a in group) for group in audits):
            diagnostic = 'prompt_response_audit_failed'
        if (pair.get('assets_unchanged') is not True or pair.get('independent_replay_matches') is not True
                or len(pair.get('runs',[])) != 2 or len(pair.get('terminal_audits',[])) != 2):
            diagnostic = 'pair_verification_failed'
        else:
            for run in pair['runs']:
                if set(run) != {'Ok'} or 'error' not in run['Ok'] or run['Ok']['error'] is not None or 'prompt' not in run['Ok'] or run['Ok']['prompt'] is not None or run['Ok'].get('status') not in ('engine_verified','partial') or run['Ok'].get('resolved_decisions') != decisions:
                    diagnostic = 'execution_or_decisions_failed'
            for audit in pair['terminal_audits']:
                if audit.get('binding_valid') is not True or audit.get('snapshot_count') != 1 or audit.get('utility') != 1:
                    diagnostic = 'terminal_binding_or_utility_failed'
    if not diagnostic and (stats.get('consumed') != 2 or stats.get('completed') != 2 or stats.get('limit') != 2 or stats.get('abandoned')):
        diagnostic = 'incomplete_consumption'
    return {'schema_version':1,'kind':'terminal_smoke_summary','context':context,
            'case_id':'terminal-rabbit','evidence_sha256':evidence_sha,'ledger':stats,
            'successful':diagnostic is None,'diagnostic':diagnostic,'old_consumed':18,
            'new_consumed':stats['consumed'] if stats else None,'proof_ready':False,
            'complete_action_coverage':False,'global_optimality':False}


def add_arguments(parser):
    for name in ('cases','baseline-dir','runner','worker','build-record','identity','window-start','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')


def terminal_smoke(args):
    """Freeze one Rabbit request and run or recover the fixed execution/replay pair."""
    from ygo_eval.research import validate_sources
    repo = Path(__file__).resolve().parents[2]
    output = checked_output(repo,args.output)
    if 'research' not in output.relative_to(repo/'data/runtime').parts:
        raise ValueError('dedicated research output required')
    paths = {key:regular_file(getattr(args,key).absolute()) for key in
             ('cases','runner','worker','build_record','identity','window_start')}
    if any(p == output or p.is_relative_to(output) or output.is_relative_to(p) for p in paths.values()):
        raise ValueError('output overlaps input')
    hashes = {key:sha(path) for key,path in paths.items()}
    previous, protected = validate_baseline(args.baseline_dir.absolute(),repo)
    source = stable_source(repo)
    build = json.loads(paths['build_record'].read_bytes())
    identity = json.loads(paths['identity'].read_bytes())
    window = json.loads(paths['window_start'].read_bytes())
    if (window.get('schema_version') != 1 or window.get('kind') != 'terminal_smoke_window_start'
            or type(window.get('started_at')) is not int or not 0 <= window['started_at'] <= int(time.time())):
        raise ValueError('invalid immutable window')
    if build.get('status') != 'recorded' or build.get('source_before') != source or build.get('source_after') != source:
        raise ValueError('build source differs')
    if any(hashes[role] not in build.get('artifacts',{}).values() for role in ('runner','worker')):
        raise ValueError('build artifacts differ')
    if identity.get('source') != source or identity.get('consistent') is not True:
        raise ValueError('candidate identity differs')
    frozen = json.loads(paths['cases'].read_bytes())
    rabbits = [item for item in frozen['cases'] if item['case']['case_id'] == 'rabbit']
    if len(rabbits) != 1: raise ValueError('exactly one frozen Rabbit required')
    item = rabbits[0]
    validate_sources(item['case'],item['request'],Path(item['banlist_path']))
    request = copy.deepcopy(item['request'])
    request['research_capture'] = POLICY
    recorded = copy.deepcopy(previous['request'])
    request['engine']['worker_path'] = recorded['engine']['worker_path']
    if request != recorded: raise ValueError('Rabbit request differs from failed frozen request')
    request['engine']['worker_path'] = str(paths['worker'])
    runtime = identity['runtimes']['ordinary']
    if runtime['roles']['worker']['sha256'] != hashes['worker']: raise ValueError('candidate worker differs')
    for asset, version in [('dll','engine_sha256'),('cdb','cdb_sha256'),('script_manifest','scripts_sha256')]:
        if runtime['roles'][asset]['sha256'] != request['versions'][version]: raise ValueError('asset version differs')
    cdb = regular_file(Path(request['engine']['catalog_path']).absolute())
    cdb_hash = sha(cdb)
    with sqlite3.connect(cdb.as_uri()+'?mode=ro',uri=True) as conn:
        rows = list(conn.execute('select id,type from datas'))
        if any(type(code) is not int or not 0 < code <= 0xffffffff or type(kind) is not int or not 0 <= kind <= 0xffffffff for code,kind in rows) or len({code for code,_ in rows}) != len(rows):
            raise ValueError('invalid or duplicate catalog type row')
        catalog = {str(code):kind for code,kind in rows}
    if sha(cdb) != cdb_hash or cdb_hash != request['versions']['cdb_sha256']: raise ValueError('CDB changed')
    manifest = {'schema_version':1,'kind':'terminal_smoke_manifest','source_identity':source['identity'],
                'output_relative':output.relative_to(repo).as_posix(),'input_sha256':hashes,
                'baseline_acceptance_sha256':ACCEPTANCE_SHA,'old_consumed':18,'limit':2,'planned_calls':2,
                'window_seconds':7200,'started_at':window['started_at'],'case_ids':['terminal-rabbit'],
                'request_sha256':digest(canonical(request)),'catalog_types_sha256':digest(canonical(catalog)),
                'cdb_sha256':cdb_hash,'runtimes':identity['runtimes'],'proof_ready':False,
                'complete_action_coverage':False,'global_optimality':False}
    manifest['context'] = digest(canonical(manifest))
    immutable_write(checked_output(repo,paths['window_start'].with_suffix('.binding.json')),
                    {'context':manifest['context'],'output_relative':manifest['output_relative']})
    output.mkdir(parents=True,exist_ok=True)
    immutable_write(checked_output(repo,output/'manifest.json'),manifest)
    invocation = {'batch_kind':'terminal-smoke-v1','context':manifest['context'],
                  'ledger':str(output/'calls.jsonl'),'output':str(output/'terminal-rabbit.json'),
                  'case_id':'terminal-rabbit','request':request,'expected_identity':runtime,
                  'started_at':window['started_at'],'catalog_types':catalog,'expected_count':1}
    invocation_path = checked_output(repo,output/'terminal-rabbit-input.json')
    immutable_write(invocation_path,invocation)
    immutable_write(checked_output(repo,output/'terminal-rabbit-request.json'),
                    {'request_sha256':manifest['request_sha256'],'input':invocation})
    invocation_sha = digest(canonical(invocation))
    def unchanged():
        if stable_source(repo) != source or sha(invocation_path) != invocation_sha or regular_file(invocation_path).read_bytes() != canonical(invocation) or sha(cdb) != cdb_hash or any(sha(p) != hashes[k] for k,p in paths.items()) or any(sha(p) != value for p,value in protected.items()):
            raise ValueError('frozen input changed')
    unchanged()
    if args.prepare_only: return {'prepared':True,'planned_calls':2,'native_calls':0,'context':manifest['context']}
    pair_path = output/'terminal-rabbit.json'
    command = [str(paths['runner']),str(invocation_path),'--input-sha',invocation_sha]
    recorded_pair = pair_path.exists()
    try:
        completed = subprocess.run(command+(['--verify-recorded'] if recorded_pair else []),capture_output=True,timeout=7200)
    except subprocess.TimeoutExpired:
        completed = subprocess.CompletedProcess(command,2,b'',b'runner_timeout')
    if recorded_pair and completed.returncode != 0:
        raise ValueError('recorded receipt verification failed')
    stats = None
    if completed.returncode in (0,1) and pair_path.exists():
        stats = json.loads(completed.stdout)['ledger']
    else:
        response = subprocess.run(command+['--stats'],capture_output=True,timeout=60)
        if response.returncode == 0: stats = json.loads(response.stdout)['ledger']
    pair = json.loads(regular_file(pair_path).read_bytes()) if pair_path.exists() else None
    if pair is not None and (pair.get('context') != manifest['context'] or pair.get('request') != request or pair.get('case_id') != 'terminal-rabbit'):
        raise ValueError('recorded pair binding differs')
    if pair_path.exists() and completed.returncode not in (0,1): raise ValueError('recorded receipt verification failed')
    report = summarize(manifest['context'],pair,stats,request['decisions'],sha(pair_path) if pair else None)
    unchanged()
    immutable_write(checked_output(repo,output/('summary-'+digest(canonical(report))+'.json')),report)
    return report
