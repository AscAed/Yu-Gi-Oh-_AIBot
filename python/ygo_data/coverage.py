"""Read-only, deliberately incomplete release and script inventory."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date
import hashlib
import json
import re
from pathlib import Path
import sqlite3

from .identity import checked_output


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tournament_evidence(path: Path) -> dict:
    """Preserve release upper bounds; they are never first-release dates."""
    source = json.loads(path.read_text(encoding='utf-8'))
    return {'schema_version': 1, 'scope': 'tournament-2026-39-card-sample',
            'source_sha256': digest(path), 'records': [
                {'card_id': row['card_id'], 'region': 'OCG', 'status': 'released',
                 'release_date': None, 'released_by': row['ocg_released_by'],
                 'basis': row['basis'], 'evidence': row['evidence']}
                for row in source['releases']]}


def inventory(cdb: Path, scripts: Path, evidence: dict,
              cutoff: str = '2026-10-19', script_root: Path | None = None,
              evidence_root: Path | None = None) -> dict:
    """Inventory explicit inputs without treating database presence as release proof."""
    date.fromisoformat(cutoff)
    if evidence.get('schema_version') != 1 or not isinstance(evidence.get('records'), list):
        raise ValueError('release evidence schema_version 1 and records required')
    before = {'cdb': digest(cdb) if cdb.exists() else None,
              'scripts': digest(scripts)}
    manifest = json.loads(scripts.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or any(
            not isinstance(name, str) or not isinstance(sha, str) or
            not re.fullmatch(r'[0-9a-f]{64}', sha) for name, sha in manifest.items()):
        raise ValueError('scripts manifest must map relative Lua filenames to SHA256')
    by_id = defaultdict(list)
    for record in evidence['records']:
        if not isinstance(record, dict) or type(record.get('card_id')) is not int or record['card_id'] <= 0:
            raise ValueError('release record requires positive integer card_id')
        if record.get('status') not in ('released', 'prerelease', 'unknown'):
            raise ValueError('invalid release status')
        for ref in record.get('evidence', []):
            if (not isinstance(ref, dict) or not isinstance(ref.get('url'), str) or
                    not isinstance(ref.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', ref['sha256'])):
                raise ValueError('invalid release source reference')
            if evidence_root is not None:
                path = (evidence_root / ref.get('file', '')).resolve()
                if not path.is_relative_to(evidence_root.resolve()) or not path.is_file() or digest(path) != ref['sha256']:
                    raise ValueError('release evidence bytes missing or mismatched')
        by_id[record['card_id']].append(record)
    unresolved = [f'duplicate_release_record:{key}' for key, rows in by_id.items() if len(rows) > 1]
    with closing(sqlite3.connect(cdb.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        source_rows = db.execute('SELECT id, ot, alias, type FROM datas ORDER BY id').fetchall()
    ids = {row[0] for row in source_rows}
    cards = []
    aliases = {row[0]: row[2] for row in source_rows}
    for card_id, ot, alias, flags in source_rows:
        issues = []
        records = by_id.get(card_id, [])
        record = records[0] if len(records) == 1 else {}
        release = 'identity_unconfirmed'
        if flags & 0x4000:
            release = 'rule_generated'
        elif ot & 0x100:
            release = 'prerelease'
            if record.get('status') == 'released':
                issues.append('region_prerelease_evidence_conflict')
        elif not ot & 1:
            release = 'region_mismatch'
        elif record.get('region') not in (None, 'OCG'):
            release = 'region_mismatch'
        elif record.get('status') == 'prerelease':
            release = 'prerelease'
        elif record.get('status') == 'released':
            bound = record.get('released_by') or record.get('release_date')
            if bound:
                date.fromisoformat(bound)
            refs = record.get('evidence', [])
            valid_refs = refs and all(r.get('url') and len(r.get('sha256', '')) == 64 for r in refs)
            if bound and bound <= cutoff and valid_refs:
                release = 'released'
            elif bound and bound > cutoff:
                release = 'prerelease'
            else:
                issues.append('release_evidence_missing')
        if not records:
            issues.append('release_evidence_missing')
        if len(records) > 1:
            issues.append('release_evidence_conflict')
        if alias:
            if alias not in ids:
                issues.append('alias_target_missing')
            if records and by_id.get(alias) and records != by_id[alias]:
                issues.append('alias_release_evidence_differs')
        target = card_id
        visited = set()
        while aliases.get(target):
            if target in visited:
                issues.append('alias_cycle')
                target = None
                break
            visited.add(target)
            target = aliases[target]
            if target not in ids:
                target = None
                break
        if len(visited) > 1:
            issues.append('alias_multihop')
        # Aliases affect naming/deck identity, not the card-specific effect script.
        names = [f'c{card_id}.lua', f'official/c{card_id}.lua']
        name = next((name for name in names if name in manifest), None)
        alias_candidate = None
        if name is None and target not in (None, card_id):
            alias_candidate = next((candidate for candidate in (f'c{target}.lua', f'official/c{target}.lua') if candidate in manifest), None)
        # Only normal non-Pendulum monsters and rule-generated tokens need no dedicated script.
        no_script = bool(flags & 0x4000) or bool(flags & 0x10 and not flags & 0x1000000)
        script_status = 'not_required' if no_script else 'missing'
        if alias_candidate and not no_script:
            script_status = 'unknown'
            issues.append('alias_script_reuse_unverified')
        if name and not no_script:
            script_status = 'unknown'
            if script_root is None:
                issues.append('script_bytes_not_checked')
            else:
                path = script_root / name
                if path.exists() and digest(path) == manifest[name]:
                    script_status = 'covered'
                else:
                    script_status = 'missing'
                    issues.append('script_missing_or_mismatch')
        cards.append({'card_id': card_id, 'alias': alias, 'region_bits': ot,
                      'release_status': release, 'release_date': record.get('release_date'),
                      'released_by': record.get('released_by'), 'release_evidence': records,
                      'script_status': script_status, 'script_file': name, 'unresolved': issues})
    for key in sorted(set(by_id) - ids):
        unresolved.append(f'evidence_card_absent:{key}')
    if before != {'cdb': digest(cdb), 'scripts': digest(scripts)}:
        raise ValueError('inputs changed during inventory')
    return {'schema_version': 1, 'cutoff': cutoff, 'region': 'OCG',
            'scope': evidence.get('scope', 'explicit-inputs-only'), 'complete': False,
            'denominator_status': 'unresolved', 'dynamic_dependencies_verified': False,
            'release_evidence_trust': 'raw_bytes_checked' if evidence_root else 'declared_provenance_only',
            'source_verified': False,
            'provided_evidence_bytes_checked': evidence_root is not None,
            'inputs': {**before, 'release_evidence': hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()},
            'counts': {'database_cards': len(cards),
                       'release_status': dict(sorted(Counter(r['release_status'] for r in cards).items())),
                       'script_status': dict(sorted(Counter(r['script_status'] for r in cards).items()))},
            'unresolved': ['global_release_denominator_not_established', *unresolved], 'cards': cards}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inv = commands.add_parser('inventory')
    inv.add_argument('--cdb', type=Path, required=True)
    inv.add_argument('--scripts', type=Path, required=True)
    inv.add_argument('--script-root', type=Path)
    inv.add_argument('--evidence-root', type=Path)
    inv.add_argument('--evidence', type=Path, required=True)
    inv.add_argument('--cutoff', default='2026-10-19')
    inv.add_argument('--output', type=Path, required=True)
    convert = commands.add_parser('tournament-evidence')
    convert.add_argument('--source', type=Path, required=True)
    convert.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = checked_output(Path.cwd(), args.output)
    if args.command == 'inventory':
        for root in (args.script_root, args.evidence_root):
            if root is not None and args.output.resolve().is_relative_to(root.resolve()):
                parser.error('output must not be inside input assets or receipts')
    protected = [args.cdb, args.scripts, args.evidence] if args.command == 'inventory' else [args.source]
    if args.output.resolve() in {path.resolve() for path in protected}:
        parser.error('output must not overwrite an input')
    if args.command == 'inventory':
        result = inventory(args.cdb, args.scripts, json.loads(args.evidence.read_text(encoding='utf-8')), args.cutoff, args.script_root, args.evidence_root)
    else:
        result = tournament_evidence(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error('output already exists; choose a fresh evidence filename')
    with args.output.open('x', encoding='utf-8') as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
