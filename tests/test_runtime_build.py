import json
import pathlib
import unittest
import os


@unittest.skipUnless(os.environ.get('YGO_LIVE_ENGINE') == '1', 'opt-in: local engine assets not supplied by CI')
class RuntimeBuild(unittest.TestCase):
    def test_pinned_x64_engine_and_abi_probe(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'data/runtime/engine/manifest.json').read_text())
        self.assertEqual(manifest['core_commit'], '38d04c9feb1a26617407091380634c87262fe3f8')
        self.assertEqual(manifest['lua_commit'], '6e22fedb74cf0c9b6656e9fce8b7331db847c605')
        self.assertEqual(manifest['architecture'], 'x64')
        self.assertEqual(manifest['api'], '11.0')
        self.assertTrue(manifest['abi_probe_passed'])
        self.assertTrue(manifest['source_verified'])


if __name__ == '__main__':
    unittest.main()
