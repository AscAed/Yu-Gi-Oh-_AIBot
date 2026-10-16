"""Check an immutable tournament transcription and its source gate offline."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .assets import verify_group


def _check_banlist(snapshot: dict) -> None:
    data = snapshot['data']
    if set(data) != {'region', 'version', 'limits'}:
        raise ValueError('invalid frozen banlist data')
    # Match the Rust Banlist struct and its numeric BTreeMap key order.
    ordered = {'region': data['region'], 'version': data['version'],
               'limits': dict(sorted(data['limits'].items(),
                                     key=lambda item: int(item[0])))}
    encode = lambda value: json.dumps(value, ensure_ascii=False,
                                      separators=(',', ':')).encode()
    body = ['banlist', snapshot['source'], snapshot['source_version'],
            snapshot['source_sha256'], snapshot['effective_date'],
            snapshot['normalizer_version'], list(encode(ordered))]
    if (snapshot['schema_version'] != 2 or snapshot['id'] !=
            'banlist-' + hashlib.sha256(encode(body)).hexdigest()):
        raise ValueError('frozen banlist identity differs from actual contents')


def validate_gate(source: dict, deck_bytes: bytes, coverage: dict) -> dict:
    """Validate declarations; actual source bytes and assets need verify_local."""
    if source.get('schema_version') != 1 or coverage.get('schema_version') != 1:
        raise ValueError('unsupported source gate version')
    selected = source['selected']
    event = date.fromisoformat(selected['event_date'])
    cutoff = date.fromisoformat(source['search']['cutoff'])
    if not date(2026, 1, 1) <= event <= cutoff:
        raise ValueError('event date is outside the approved search interval')
    if not re.fullmatch(r'https://x.com/[^/]+/status/[0-9]+', selected['url']):
        raise ValueError('selected source must identify the original post')
    if not all(selected.get(k) for k in ('publisher', 'player', 'result', 'evidence')):
        raise ValueError('incomplete original event provenance')
    if hashlib.sha256(deck_bytes).hexdigest() != source['deck_sha256']:
        raise ValueError('original deck hash differs from transcription')
    deck = json.loads(deck_bytes)
    counts = {k: len(deck[k]) for k in ('main', 'extra')}
    transcription = source['transcription']
    if (not transcription['independent_check'] or
            not transcription['all_counts_resolved'] or
            counts != transcription['counts']):
        raise ValueError('incomplete independent transcription')
    if source['side']['status'] == 'unpublished':
        if deck['side'] or source['side']['legality_verified']:
            raise ValueError('unpublished side cannot claim verified legality')
    if not 40 <= counts['main'] <= 60 or not 1 <= counts['extra'] <= 15:
        raise ValueError('invalid deck sizes')
    if 26692769 not in deck['extra'] or 25542642 not in deck['main']:
        raise ValueError('original deck is missing default goal cards')
    rules = source['rules']
    if (rules['effective_date'] != '2026-10-01' or rules['differences'] or
            rules['unresolved'] or rules['unmatched_snapshot_ids']):
        raise ValueError('rule comparison is incomplete or differs')
    cards = set(deck['main'] + deck['extra'] + deck['side'])
    releases = source['releases']
    if {r['card_id'] for r in releases} != cards or len(releases) != len(cards):
        raise ValueError('release coverage differs from original card set')
    for entry in releases:
        if not date.fromisoformat(entry['ocg_released_by']) <= event:
            raise ValueError('release occurs after original tournament')
        if not entry['basis'] or not entry['evidence']:
            raise ValueError('missing OCG release evidence')
    if (coverage['deck_sha256'] != source['deck_sha256'] or
            coverage['asset_group_id'] != source['asset_group_id']):
        raise ValueError('coverage asset or deck reference mismatch')
    if {c['card_id'] for c in coverage['cards']} != cards or len(coverage['cards']) != len(cards):
        raise ValueError('coverage card set is incomplete')
    inside = 0
    ids = set()
    verified = True
    for card in coverage['cards']:
        if not card['entries']:
            raise ValueError('card has no classified rules')
        for entry in card['entries']:
            if entry['id'] in ids:
                raise ValueError('duplicate coverage rule')
            ids.add(entry['id'])
            if entry['applicability'] == 'outside_scenario':
                if not entry['exclusion_basis']:
                    raise ValueError('missing scenario exclusion basis')
            elif entry['applicability'] == 'inside_scenario':
                inside += 1
                verified &= (entry['implementation_status'] == 'verified' and
                             bool(entry['verification_cases']))
            else:
                raise ValueError('unclassified rule')
    return {'counts': counts, 'inside_rules': inside,
            'semantics_verified': bool(verified),
            'side_legality_verified': source['side']['legality_verified']}


def verify_local(source: dict, deck_bytes: bytes, coverage: dict,
                 assets: Path, receipts: Path, banlist_path: Path) -> dict:
    """Check frozen raw bytes, actual CDB membership and combined card limits."""
    result = validate_gate(source, deck_bytes, coverage)
    manifest = verify_group(assets)
    if manifest['asset_group_id'] != source['asset_group_id']:
        raise ValueError('wrong asset group')
    rules = source['rules']
    banlist = json.loads(banlist_path.read_text(encoding='utf-8'))
    _check_banlist(banlist)
    if (banlist['id'] != rules['snapshot_id'] or
            banlist['effective_date'] != rules['effective_date'] or
            banlist['source_version'] != rules['source_commit'] or
            banlist['source_sha256'] != rules['source_sha256']):
        raise ValueError('wrong frozen banlist source or date mapping')
    root = receipts.resolve()
    evidence = source['selected']['evidence'] + rules['evidence']
    evidence += [e for r in source['releases'] for e in r['evidence']]
    for receipt in evidence:
        path = (receipts / receipt['file']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('receipt outside evidence root')
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
            raise ValueError(f'source evidence hash mismatch: {receipt["file"]}')
    deck = json.loads(deck_bytes)
    counts = Counter(deck['main'] + deck['extra'] + deck['side'])
    with sqlite3.connect(f'file:{(assets / "cards.cdb").as_posix()}?mode=ro', uri=True) as db:
        canonical = Counter()
        for code, amount in counts.items():
            row = db.execute('SELECT ot,alias FROM datas WHERE id=?', (code,)).fetchone()
            if not row or row[0] & 1 == 0:
                raise ValueError(f'not an official OCG card: {code}')
            canonical[row[1] or code] += amount
        for code, amount in canonical.items():
            limit = banlist['data']['limits'].get(str(code), 'Unlimited')
            if amount > {'Forbidden': 0, 'Limited': 1, 'SemiLimited': 2,
                         'Unlimited': 3}[limit]:
                raise ValueError(f'frozen rule violation: {code}')
        for card in coverage['cards']:
            text = db.execute('SELECT desc FROM texts WHERE id=?', (card['card_id'],)).fetchone()[0]
            if hashlib.sha256(text.encode()).hexdigest() != card['text_sha256']:
                raise ValueError('effect text source differs')
            if manifest['files'].get('script/' + card['script']) != card['script_sha256']:
                raise ValueError('effect script source differs')
    return {**result, 'raw_sources_verified': True,
            'main_extra_legality_verified': True,
            'asset_group_id': manifest['asset_group_id']}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'deck', 'coverage', 'assets', 'receipts', 'banlist'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    result = verify_local(read(args.source), args.deck.read_bytes(),
                          read(args.coverage), args.assets, args.receipts,
                          args.banlist)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
