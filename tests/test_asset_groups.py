import copy
import json
from pathlib import Path
import shutil
import unittest
from uuid import uuid4
import zipfile

from ygo_data.assets import freeze_group, verify_group


class AssetGroups(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).resolve().parents[1] / 'data' / 'tmp'
        self.root = self.base / ('asset-test-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup)
        self.source = self.root / 'source'
        (self.source / 'script' / 'official').mkdir(parents=True)
        (self.source / 'cards.cdb').write_bytes(b'frozen catalog')
        (self.source / 'core.dll').write_bytes(b'frozen engine')
        (self.source / 'script' / 'utility.lua').write_text(
            'Duel.LoadScript("constant.lua")', encoding='utf-8')
        (self.source / 'script' / 'constant.lua').write_text(
            'LOCATION_HAND=2', encoding='utf-8')
        (self.source / 'script' / 'official' / 'c1.lua').write_text(
            '-- official card', encoding='utf-8')
        self.recipe = {
            'schema_version': 1,
            'catalog': {'repository': 'https://github.com/ProjectIgnis/BabelCDB',
                        'commit': 'a' * 40},
            'scripts': {'repository': 'https://github.com/ProjectIgnis/CardScripts',
                        'commit': 'b' * 40},
            'core': {'core_commit': 'c' * 40, 'lua_commit': 'd' * 40,
                     'architecture': 'x64', 'api': '11.0',
                     'source_verified': True},
            'banlist_id': 'banlist-' + 'e' * 64,
        }

    def cleanup(self):
        if not self.root.resolve().is_relative_to(self.base.resolve()):
            raise ValueError('test cleanup outside workspace')
        shutil.rmtree(self.root)

    def freeze(self, name):
        return freeze_group(self.source / 'cards.cdb', self.source / 'script',
                            self.source / 'core.dll', self.recipe,
                            self.root / name)

    def test_offline_group_identity_is_independent_of_destination(self):
        a = self.freeze('one')
        b = self.freeze('two')
        self.assertEqual(a, b)
        self.assertEqual(verify_group(self.root / 'one'), a)
        self.assertEqual((self.source / 'core.dll').read_bytes(), b'frozen engine')
        self.assertIn('script/official/c1.lua', a['files'])

    def test_changed_asset_or_changed_provenance_is_rejected(self):
        self.freeze('one')
        folder = self.root / 'one'
        original = (folder / 'manifest.json').read_text(encoding='utf-8')
        changed = json.loads(original)
        changed['recipe']['catalog']['commit'] = 'f' * 40
        (folder / 'manifest.json').write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'identity'):
            verify_group(folder)
        (folder / 'manifest.json').write_text(original, encoding='utf-8')
        (folder / 'script' / 'official' / 'c1.lua').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            verify_group(folder)

    def test_missing_shared_helper_and_unpinned_sources_are_rejected(self):
        (self.source / 'script' / 'constant.lua').unlink()
        with self.assertRaisesRegex(ValueError, 'constant.lua'):
            self.freeze('missing')
        bad = copy.deepcopy(self.recipe)
        bad['scripts']['commit'] = 'master'
        with self.assertRaisesRegex(ValueError, 'commit'):
            freeze_group(self.source / 'cards.cdb', self.source / 'script',
                         self.source / 'core.dll', bad, self.root / 'unpinned')

    def test_existing_destination_cannot_overwrite_a_frozen_group(self):
        self.freeze('one')
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.freeze('one')

    def test_unlisted_runtime_script_is_rejected(self):
        self.freeze('one')
        (self.root / 'one/script/official/c999.lua').write_text('-- injected')
        with self.assertRaisesRegex(ValueError, 'unlisted'):
            verify_group(self.root / 'one')

    def test_pinned_content_hash_is_checked_before_freezing(self):
        self.recipe['catalog']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'catalog hash'):
            self.freeze('changed-source')
        self.assertFalse((self.root / 'changed-source').exists())

    def test_pinned_archive_rebuilds_the_same_group_offline(self):
        archive = self.root / 'scripts.zip'
        with zipfile.ZipFile(archive, 'w') as package:
            for path in (self.source / 'script').rglob('*.lua'):
                package.write(path, 'CardScripts-pinned/' +
                              path.relative_to(self.source / 'script').as_posix())
        expected = self.freeze('directory')
        actual = freeze_group(self.source / 'cards.cdb', archive,
                              self.source / 'core.dll', self.recipe,
                              self.root / 'archive')
        self.assertEqual(actual, expected)

    def test_archive_traversal_is_rejected_without_writing_output(self):
        archive = self.root / 'unsafe.zip'
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('root/../../outside.lua', 'bad')
        with self.assertRaisesRegex(ValueError, 'archive path'):
            freeze_group(self.source / 'cards.cdb', archive,
                         self.source / 'core.dll', self.recipe,
                         self.root / 'unsafe')
        self.assertFalse((self.root / 'unsafe').exists())


if __name__ == '__main__':
    unittest.main()
