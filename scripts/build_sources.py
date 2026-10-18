"""Reject dirty pinned source trees, except the exact Windows Meson adapter."""
import hashlib
import json
import subprocess
from pathlib import Path

CORE='38d04c9feb1a26617407091380634c87262fe3f8'
LUA='6e22fedb74cf0c9b6656e9fce8b7331db847c605'


def adapted_meson(text: str) -> str:
    text=text.replace("cmd = find_program('cmd')", "cmd = import('python').find_installation()")
    return text.replace("['/c', 'type', meson.current_source_dir()", "['-c', 'import sys,pathlib;sys.stdout.buffer.write(b\"\".join(pathlib.Path(p).read_bytes() for p in sys.argv[1:]))', meson.current_source_dir()")


def validate_working_tree(core_status: str, lua_status: str, meson: str, original: str) -> None:
    if lua_status.strip():
        raise ValueError('Lua source tree has local modifications or untracked files')
    if any(line[3:] != 'lua/meson.build' for line in core_status.splitlines() if line):
        raise ValueError('Core source tree has unexpected modifications or untracked files')
    if meson not in [original, adapted_meson(original)]:
        raise ValueError('Meson adapter differs from the exact approved transformation')


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git','-C',str(root),'-c','core.quotepath=false',*args],text=True,encoding='utf-8').rstrip('\n')


def verify(root: Path) -> dict:
    lua=root/'lua/src'
    if git(root,'rev-parse','HEAD')!=CORE or git(lua,'rev-parse','HEAD')!=LUA:
        raise ValueError('Pinned source commit mismatch')
    original=git(root,'show','HEAD:lua/meson.build')+'\n'
    actual=(root/'lua/meson.build').read_text(encoding='utf-8')
    validate_working_tree(git(root,'status','--porcelain','--untracked-files=all'),git(lua,'status','--porcelain','--untracked-files=all'),actual,original)
    return {'source_verified':True,'core_tree':git(root,'rev-parse','HEAD^{tree}'),'lua_tree':git(lua,'rev-parse','HEAD^{tree}'),'meson_adapter_sha256':hashlib.sha256(actual.encode()).hexdigest()}


if __name__=='__main__':
    result=verify(Path('data/tmp/ocgcore-source'))
    Path('data/tmp/source-provenance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
