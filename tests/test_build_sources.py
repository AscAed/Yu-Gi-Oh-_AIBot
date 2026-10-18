import importlib.util
import pathlib
import unittest

path=pathlib.Path(__file__).resolve().parents[1]/'scripts/build_sources.py'
spec=importlib.util.spec_from_file_location('build_sources',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BuildSources(unittest.TestCase):
    def test_only_exact_known_meson_adapter_is_allowed(self):
        original="cmd = find_program('cmd')\narguments : ['/c', 'type', meson.current_source_dir()]"
        adapted=module.adapted_meson(original)
        module.validate_working_tree('', '', original, original)
        module.validate_working_tree(' M lua/meson.build', '', adapted, original)
        for status,lua,content in [(' M field.cpp','',adapted),('?? injected.h','',adapted),('',' M lapi.c',adapted),(' M lua/meson.build','',adapted+'\nmalicious_command()')]:
            with self.assertRaises(ValueError):
                module.validate_working_tree(status,lua,content,original)
