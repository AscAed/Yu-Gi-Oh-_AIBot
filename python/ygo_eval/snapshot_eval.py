"""Read-only snapshot objective evaluation; never invokes a worker."""
import json
from pathlib import Path
import sqlite3
import subprocess
from contextlib import closing
from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source

OBJECTIVE = 'rabbit-own-face-up-xyz-v1'


def run_runner(runner, envelope):
    process = subprocess.run([str(runner)], input=canonical(envelope), capture_output=True, timeout=60)
    if process.returncode != 0:
        raise ValueError('snapshot auditor failed')
    return json.loads(process.stdout)


def evaluate_snapshot(evidence, cdb, runner, output, report_version=1):
    """Bind source bytes and frozen CDB to a new, explicitly unqualified report."""
    if type(report_version) is not int or report_version not in (1, 2):
        raise ValueError('unsupported report version')
    repo = Path(__file__).resolve().parents[2]
    output = checked_output(repo, output)
    if 'research' not in output.relative_to(repo / 'data/runtime').parts or output.exists():
        raise ValueError('exclusive ignored research output required')
    evidence, cdb, runner = [regular_file(p) for p in (evidence, cdb, runner)]
    inputs = [(p, digest(p.read_bytes())) for p in (evidence, cdb, runner)]
    value = json.loads(evidence.read_bytes())
    request = value.get('request')
    runs = value.get('runs')
    if not isinstance(request, dict) or not isinstance(runs, list) or not runs:
        raise ValueError('request and nonempty runs required')
    if request.get('protocol_version') not in (1, 2) or request.get('versions', {}).get('cdb_sha256') != inputs[1][1]:
        raise ValueError('unsupported source version or frozen CDB mismatch')
    for run in runs:
        if not isinstance(run, dict) or set(run) not in ({'Ok'}, {'Err'}):
            raise ValueError('invalid result record')
        if 'Ok' in run and (not isinstance(run['Ok'], dict) or run['Ok'].get('protocol_version') != request['protocol_version'] or run['Ok'].get('versions', {}).get('cdb_sha256') != inputs[1][1]):
            raise ValueError('result version or CDB binding mismatch')
    with closing(sqlite3.connect(cdb.as_uri()+'?mode=ro', uri=True)) as database:
        catalog = {}
        for code, kind in database.execute('SELECT id,type FROM datas'):
            if type(code) is not int or type(kind) is not int or not 0 < code <= 0xffffffff or not 0 <= kind <= 0xffffffff or str(code) in catalog:
                raise ValueError('invalid or duplicate CDB identity')
            catalog[str(code)] = kind
    before = stable_source(repo)
    envelope = {'schema_version':report_version, 'own_player':0, 'runs':runs, 'catalog_types':catalog}
    if report_version == 2:
        envelope['request'] = request
    core = run_runner(runner, envelope)
    if before != stable_source(repo) or any(digest(regular_file(p).read_bytes()) != hashed for p, hashed in inputs):
        raise ValueError('inputs or auditor changed during evaluation')
    evaluations = core.get('evaluations') if isinstance(core, dict) else None
    if not isinstance(core, dict) or set(core) != {'evaluations'} or not isinstance(evaluations, list) or len(evaluations) != len(runs):
        raise ValueError('invalid evaluator binding')
    for item in evaluations:
        expected = {'snapshot_count','termination','utility','diagnostics'} | ({'binding_valid'} if report_version == 2 else set())
        if not isinstance(item, dict) or set(item) != expected or item['termination'] not in ('execution_failed','unknown','natural_end','next_turn_boundary_observed','not_terminated','terminal_boundary_bound') or not isinstance(item['diagnostics'], list) or not all(isinstance(s, str) for s in item['diagnostics']):
            raise ValueError('invalid evaluator result')
        if report_version == 1 and item['termination'] == 'terminal_boundary_bound':
            raise ValueError('v1 cannot bind terminal boundary')
        if report_version == 2 and (type(item['binding_valid']) is not bool or item['binding_valid'] != (item['termination'] == 'terminal_boundary_bound')):
            raise ValueError('invalid structural binding')
        if item['snapshot_count'] is not None and (type(item['snapshot_count']) is not int or not 0 <= item['snapshot_count'] <= 7):
            raise ValueError('invalid snapshot count')
        if item['utility'] is not None:
            natural = item['termination'] == 'natural_end' and item['utility'] in (-2, -1, 8)
            bound = report_version == 2 and item['binding_valid'] and item['snapshot_count'] is not None and item['utility'] == item['snapshot_count']
            if type(item['utility']) is not int or not (natural or bound):
                raise ValueError('invalid terminal utility')
    report = {'schema_version':report_version,'kind':'snapshot_evaluation','objective':OBJECTIVE,
              'source':{'sha256':inputs[0][1],'request_sha256':digest(canonical(request)), 'origin':'synthetic_fixture' if value.get('kind') == 'synthetic_snapshot_fixture' else 'historical_report'},
              'provenance':{'source_head':before['head'],'source_identity':before['identity'],'runner_sha256':inputs[2][1],'cdb_sha256':inputs[1][1]},
              'evaluations':[{'run_index':i,'role':'execution' if i == 0 else 'replay' if i == 1 else 'additional_record', **item} for i,item in enumerate(evaluations)],
              'native_calls':0,'source_authenticity_verified':False,'native_replay_verified':False,'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
    output = checked_output(repo, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2).encode())
    return report
