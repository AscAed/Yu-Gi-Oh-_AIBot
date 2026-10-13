"""Freeze local official assets in the ignored runtime directory."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--ignis', type=Path, default=Path('C:/ProjectIgnis'))
args = parser.parse_args()
out = Path('data/runtime')
out.mkdir(parents=True, exist_ok=True)
shutil.copy2(args.ignis / 'expansions/cards.cdb', out / 'cards.cdb')
manifest = {}
for folder in ['', 'official']:
    for source in sorted((args.ignis / 'script' / folder).glob('*.lua')):
        relative = source.relative_to(args.ignis / 'script')
        dest = out / 'script' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
            dest.write_bytes(content)
        manifest[relative.as_posix()] = digest
# utility.lua loads this shared helper unconditionally, even for official cards.
helper = args.ignis / 'script/unofficial/proc_unofficial.lua'
if helper.is_file():
    content = helper.read_bytes()
    (out / 'script/proc_unofficial.lua').write_bytes(content)
    manifest['proc_unofficial.lua'] = hashlib.sha256(content).hexdigest()
(out / 'scripts.json').write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')), encoding='utf-8')
print(f'Frozen {len(manifest)} Lua files and official CDB; external assets remain ignored.')
