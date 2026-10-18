"""Adapt only upstream's Windows Lua concatenation command; core sources stay pinned."""
from pathlib import Path

path = Path('data/tmp/ocgcore-source/lua/meson.build')
text = path.read_text()
if "cmd = find_program('cmd')" in text:
    text = text.replace("cmd = find_program('cmd')", "cmd = import('python').find_installation()")
    text = text.replace("['/c', 'type', meson.current_source_dir()", "['-c', 'import sys,pathlib;sys.stdout.buffer.write(b\"\".join(pathlib.Path(p).read_bytes() for p in sys.argv[1:]))', meson.current_source_dir()")
    path.write_text(text)
