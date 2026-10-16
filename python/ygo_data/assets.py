"""Create and check a separate, pinned asset group without network access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
import zipfile


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _recipe(recipe: dict) -> None:
    if recipe.get('schema_version') != 1:
        raise ValueError('unsupported asset recipe version')
    for source in ('catalog', 'scripts'):
        if not re.fullmatch(r'[0-9a-f]{40}', recipe.get(source, {}).get('commit', '')):
            raise ValueError(f'{source} requires a pinned commit')
    core = recipe.get('core', {})
    for field in ('core_commit', 'lua_commit'):
        if not re.fullmatch(r'[0-9a-f]{40}', core.get(field, '')):
            raise ValueError(f'core requires pinned {field}')
    if core.get('source_verified') is not True:
        raise ValueError('core source provenance is not verified')
    if not re.fullmatch(r'banlist-[0-9a-f]{64}', recipe.get('banlist_id', '')):
        raise ValueError('a frozen banlist identity is required')


def _dependencies(files: dict[str, bytes]) -> None:
    for name, data in files.items():
        if not name.startswith('script/') or not name.endswith('.lua'):
            continue
        for reference in re.findall(
                rb'Duel\.LoadScript\([\'"]([^\'"%]+\.lua)[\'"]', data):
            target = reference.decode('utf-8')
            if f'script/{target}' not in files and f'script/official/{target}' not in files:
                raise ValueError(f'{name}: missing script dependency {target}')


def _scripts(source: Path, recipe: dict) -> dict[str, bytes]:
    files = {}
    if source.is_dir():
        for path in sorted(source.rglob('*.lua')):
            if path.is_symlink():
                raise ValueError(f'script symlinks are unsupported: {path}')
            files['script/' + path.relative_to(source).as_posix()] = path.read_bytes()
        return files
    expected = recipe['scripts'].get('archive_sha256')
    if expected is not None and _hash(source.read_bytes()) != expected:
        raise ValueError('scripts archive hash differs from pinned source')
    with zipfile.ZipFile(source) as archive:
        for item in sorted(archive.infolist(), key=lambda entry: entry.filename):
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or
                    '\\' in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe scripts archive path')
            relative = PurePosixPath(*path.parts[1:])
            if relative.suffix != '.lua':
                continue
            if str(relative) == 'unofficial/proc_unofficial.lua':
                relative = PurePosixPath('proc_unofficial.lua')
            elif len(relative.parts) > 1 and relative.parts[0] != 'official':
                continue
            key = 'script/' + str(relative)
            if key in files:
                raise ValueError('duplicate scripts archive path')
            files[key] = archive.read(item)
    return files


def freeze_group(cdb: Path, scripts: Path, core: Path, recipe: dict,
                 output: Path) -> dict:
    """Copy exact input bytes to a new directory, preserving existing groups."""
    _recipe(recipe)
    if output.exists():
        raise ValueError(f'asset group already exists: {output}')
    files = {'cards.cdb': cdb.read_bytes(), 'engine/ocgcore.dll': core.read_bytes()}
    files.update(_scripts(scripts, recipe))
    if 'script/utility.lua' not in files:
        raise ValueError('missing script dependency utility.lua')
    _dependencies(files)
    script_hashes = {name.removeprefix('script/'): _hash(data)
                     for name, data in files.items() if name.startswith('script/')}
    files['scripts.json'] = _json(script_hashes)
    for component, name, field in (
            ('catalog', 'cards.cdb', 'sha256'),
            ('scripts', 'scripts.json', 'manifest_sha256'),
            ('core', 'engine/ocgcore.dll', 'sha256')):
        expected = recipe[component].get(field)
        if expected is not None and expected != _hash(files[name]):
            raise ValueError(f'{component} hash differs from pinned source')
    files['engine/manifest.json'] = _json({
        **recipe['core'], 'sha256': _hash(files['engine/ocgcore.dll'])})
    manifest = {'schema_version': 1, 'recipe': recipe,
                'files': {name: _hash(data) for name, data in sorted(files.items())}}
    manifest['asset_group_id'] = 'asset-group-' + _hash(_json(manifest))
    output.mkdir(parents=True)
    for name, data in files.items():
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    (output / 'manifest.json').write_bytes(_json(manifest))
    return verify_group(output)


def verify_group(folder: Path) -> dict:
    """Recompute group identity and every asset hash before using a group."""
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if set(manifest) != {'schema_version', 'recipe', 'files', 'asset_group_id'}:
        raise ValueError('invalid asset manifest fields')
    body = {k: v for k, v in manifest.items() if k != 'asset_group_id'}
    if manifest['schema_version'] != 1 or manifest['asset_group_id'] != 'asset-group-' + _hash(_json(body)):
        raise ValueError('asset group identity mismatch')
    _recipe(manifest['recipe'])
    root = folder.resolve()
    present = {p.relative_to(folder).as_posix() for p in folder.rglob('*')
               if p.is_file()}
    if present != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('unlisted or missing asset group files')
    actual = {}
    for name, expected in manifest['files'].items():
        path = folder / name
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError('asset path is outside the group')
        data = path.read_bytes()
        if _hash(data) != expected:
            raise ValueError(f'asset hash mismatch: {name}')
        actual[name] = data
    for required in ('cards.cdb', 'engine/ocgcore.dll', 'engine/manifest.json',
                     'script/utility.lua', 'scripts.json'):
        if required not in actual:
            raise ValueError(f'missing asset: {required}')
    scripts = json.loads(actual['scripts.json'])
    if scripts != {name.removeprefix('script/'): _hash(data)
                   for name, data in actual.items() if name.startswith('script/')}:
        raise ValueError('script manifest references differ from group')
    _dependencies(actual)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze')
    for flag in ('cdb', 'scripts', 'core', 'recipe', 'output'):
        freeze.add_argument('--' + flag, required=True, type=Path)
    check = sub.add_parser('verify')
    check.add_argument('--input', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'freeze':
        result = freeze_group(args.cdb, args.scripts, args.core,
                              json.loads(args.recipe.read_text(encoding='utf-8')),
                              args.output)
    else:
        result = verify_group(args.input)
    print(json.dumps({'asset_group_id': result['asset_group_id'],
                      'files_verified': len(result['files'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
