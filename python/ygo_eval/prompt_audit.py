"""Read-only historical frame comparisons; no worker, journal or native calls."""
import json
import re
from pathlib import Path
import subprocess
from typing import Any, Dict, Sequence, Union

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source


def _integer(value):
    return type(value) is int and value >= 0


def _bytes(value):
    return isinstance(value, list) and all(_integer(n) and n <= 255 for n in value)


def _extract(role, encoded):
    value = json.loads(encoded)
    if not isinstance(value, dict) or not isinstance(value.get('prompt_audits'), list) or not value['prompt_audits']:
        raise ValueError('nonempty prompt_audits required')
    request = value.get('request')
    if request is not None and not isinstance(request, dict):
        raise ValueError('invalid historical request')
    frames = []
    for frame in value['prompt_audits']:
        if not isinstance(frame, dict) or not _integer(frame.get('sequence')) or not _bytes(frame.get('raw')):
            raise ValueError('invalid historical frame')
        if frame['raw'] and frame.get('opcode', frame['raw'][0]) != frame['raw'][0]:
            raise ValueError('historical opcode differs from raw bytes')
        historical = frame.get('actual_response_bytes')
        historical_error = False
        if historical is not None:
            if not isinstance(historical, dict) or set(historical) not in ({'Ok'}, {'Err'}):
                raise ValueError('invalid historical response result')
            historical_error = 'Err' in historical
            if historical_error:
                if not isinstance(historical['Err'], str):
                    raise ValueError('invalid historical parser diagnostic')
                historical = None
            else:
                historical = historical['Ok']
                if not isinstance(historical, list) or not all(_bytes(b) for b in historical):
                    raise ValueError('invalid historical response bytes')
        frames.append({'sequence':frame['sequence'], 'raw':frame['raw'], 'historical':historical, 'historical_error':historical_error})
    return {'role':role, 'sha256':digest(encoded), 'request_sha256':digest(canonical(request)) if request is not None else None,
            'origin':'synthetic_fixture' if value.get('kind') == 'synthetic_prompt_fixture' else 'historical_report', 'frames':frames}


def run_runner(runner: Path, envelope: Dict[str, Any]) -> Dict[str, Any]:
    """The dedicated auditor reads stdin; it receives no asset or ledger paths."""
    result = subprocess.run([str(runner)], input=canonical(envelope), capture_output=True, timeout=60)
    if result.returncode not in (0, 1):
        raise ValueError('offline auditor failed')
    value = json.loads(result.stdout)
    if result.returncode != int(value.get('successful') is not True):
        raise ValueError('auditor exit status disagrees with report')
    return value


def _check_core(core, envelope):
    if not isinstance(core, dict) or set(core) != {'sources','summary','successful'} or type(core['successful']) is not bool:
        raise ValueError('invalid auditor report')
    if not isinstance(core['sources'], list) or len(core['sources']) != len(envelope['sources']):
        raise ValueError('auditor source binding differs')
    counts = dict(frames=0, current_mismatches=0, historical_mismatches=0, errors=0, historical_unavailable=0)
    observed = set()
    for supplied, returned in zip(envelope['sources'], core['sources']):
        if not isinstance(returned, dict) or set(returned) != set(supplied) or any(returned[k] != supplied[k] for k in supplied if k != 'frames'):
            raise ValueError('auditor source binding differs')
        if not isinstance(returned['frames'], list) or len(returned['frames']) != len(supplied['frames']):
            raise ValueError('auditor dropped frame occurrences')
        for original, frame in zip(supplied['frames'], returned['frames']):
            opcode = original['raw'][0] if original['raw'] else None
            if not isinstance(frame, dict) or set(frame) != {'sequence','opcode','raw_sha256','current','historical'} or frame['sequence'] != original['sequence'] or frame['opcode'] != opcode or frame['raw_sha256'] != digest(bytes(original['raw'])):
                raise ValueError('auditor frame binding differs')
            if opcode is not None:
                observed.add(opcode)
            counts['frames'] += 1
            for key in ('current', 'historical'):
                comparison = frame[key]
                if not isinstance(comparison, dict) or set(comparison) != {'status','audit','diagnostic'}:
                    raise ValueError('invalid comparison')
                status = comparison['status']
                if status not in ('matched','mismatch','error','unavailable') or (key == 'current' and status == 'unavailable'):
                    raise ValueError('invalid comparison status')
                if status in ('matched', 'mismatch'):
                    audit = comparison['audit']
                    if not isinstance(audit, dict) or audit.get('matches') is not (status == 'matched') or audit.get('global_optimality') is not False or audit.get('complete_action_coverage') is not False or comparison['diagnostic'] is not None:
                        raise ValueError('invalid comparison qualification')
                    if status == 'mismatch':
                        counts[key+'_mismatches'] += 1
                elif comparison['audit'] is not None or not isinstance(comparison['diagnostic'], str):
                    raise ValueError('missing comparison diagnostic')
                if status == 'error': counts['errors'] += 1
                if status == 'unavailable': counts['historical_unavailable'] += 1
    success = not any(counts[k] for k in counts if k != 'frames')
    if not isinstance(core['summary'], dict) or any(type(n) is not int for n in core['summary'].values()) or core['summary'] != counts or core['successful'] is not success:
        raise ValueError('auditor summary differs from frame results')
    return sorted(observed)


def audit_corpus(evidence: Sequence[str], runner: Union[str, Path], output: Union[str, Path]) -> Dict[str, Any]:
    """Bind immutable input bytes, current source and auditor hash to a new report."""
    repo = Path(__file__).resolve().parents[2]
    output = checked_output(repo, output)
    relative = output.relative_to(repo / 'data' / 'runtime')
    if 'research' not in relative.parts:
        raise ValueError('dedicated ignored research directory required')
    if output.exists():
        raise ValueError('output already exists')
    runner = regular_file(runner)
    paths = {}; sources = []
    for item in evidence:
        role, separator, name = item.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_-]+',role) or role in paths:
            raise ValueError('distinct evidence ROLE=PATH required')
        path = regular_file(name)
        if output == path or output == runner:
            raise ValueError('output overlaps input')
        paths[role] = path
        sources.append(_extract(role, path.read_bytes()))
    if not sources:
        raise ValueError('nonempty evidence required')
    before = stable_source(repo); runner_hash = digest(runner.read_bytes())
    core = run_runner(runner, {'schema_version':1,'sources':sources})
    if before != stable_source(repo) or runner_hash != digest(regular_file(runner).read_bytes()) or any(digest(regular_file(paths[s['role']]).read_bytes()) != s['sha256'] for s in sources):
        raise ValueError('inputs or auditor changed during audit')
    observed = _check_core(core, {'sources':sources})
    report = {'schema_version':1,'kind':'prompt_corpus_audit','provenance':{'source_head':before['head'],'source_identity':before['identity'],'runner_sha256':runner_hash},
              **core,'observed_opcodes':observed,'unobserved_opcodes':[n for n in [11,12,13,14,15,16,18,19,24,26] if n not in observed],
              'native_calls':0,'complete_action_coverage':False,'global_optimality':False,
              'coverage_gaps':['ordering_equivalence_unproven','shuffle_information_and_cycle_semantics_unproven','historical_report_is_not_new_native_replay','unobserved_opcodes_remain_unqualified']}
    # Recheck parent links at publication and use exclusive create, including errors.
    output = checked_output(repo, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(json.dumps(report,ensure_ascii=False,indent=2).encode())
    return report
