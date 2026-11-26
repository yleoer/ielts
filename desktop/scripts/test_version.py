import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest


SPEC = importlib.util.spec_from_file_location('desktop_version', Path(__file__).with_name('version.py'))
version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version)


class VersionTests(unittest.TestCase):
    def test_only_versions_above_every_release_are_new(self):
        listing = ('aaa\trefs/tags/desktop-v0.9.0\nbbb\trefs/tags/desktop-v0.9.0^{}\n'
                   'ccc\trefs/tags/desktop-v0.10.0\nddd\trefs/tags/media-2026.11.19\n')
        released = version.released_versions(listing)
        self.assertEqual(sorted(released), ['0.10.0', '0.9.0'])
        self.assertTrue(version.is_unreleased('0.10.1', released))
        self.assertTrue(version.is_unreleased('0.1.0', []))
        self.assertFalse(version.is_unreleased('0.10.0', released))
        for older in ['0.9.0', '0.9.5']:
            with self.subTest(older=older), self.assertRaisesRegex(ValueError, '低于已发布的 0.10.0'):
                version.is_unreleased(older, released)

    def test_new_version_outputs_its_changelog_section(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.joinpath('Cargo.toml').write_text('[workspace.package]\nversion = "0.7.1"\n', encoding='utf-8')
            root.joinpath('CHANGELOG.md').write_text(
                '# 更新记录\n\n## 0.7.10\n\n- 以后\n\n## 0.7.1\n\n- 切题不再跳动\n- 释义区预留高度\n\n## 0.7.0\n\n- 听读音\n',
                encoding='utf-8')
            self.assertEqual(version.release_outputs(root, 'x\trefs/tags/desktop-v0.7.0\n'),
                             'version=0.7.1\nnew=true\nnotes<<CIJIAN_NOTES_END\n- 切题不再跳动\n- 释义区预留高度\nCIJIAN_NOTES_END\n')
            self.assertEqual(version.release_outputs(root, 'x\trefs/tags/desktop-v0.7.1\n'), 'version=0.7.1\nnew=false\n')
            root.joinpath('CHANGELOG.md').write_text('## 0.7.0\n\n- 听读音\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '缺少 0.7.1'):
                version.release_outputs(root, 'x\trefs/tags/desktop-v0.7.0\n')

    def test_only_stable_three_part_versions(self):
        for value in ['v0.2.0', '0.2', '01.2.0', '0.2.0-beta.1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                version.validate_version(value)

    def test_set_version_updates_workspace_and_both_package_lock_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.joinpath('Cargo.toml').write_text(
                '[workspace]\nresolver = "2"\nmembers = ["app", "core"]\n[workspace.package]\nversion = "0.1.0"\nedition = "2021"\n', encoding='utf-8')
            for name, package in [('app', 'cijian'), ('core', 'cijian-core')]:
                root.joinpath(name, 'src').mkdir(parents=True)
                root.joinpath(name, 'src', 'lib.rs').write_text('', encoding='utf-8')
                root.joinpath(name, 'Cargo.toml').write_text(
                    f'[package]\nname = "{package}"\nversion.workspace = true\nedition.workspace = true\n', encoding='utf-8')
            version.set_version(root, '0.3.0')
            self.assertEqual(version.read_version(root), '0.3.0')
            lock = tomllib.loads(root.joinpath('Cargo.lock').read_text(encoding='utf-8'))
            self.assertEqual({p['version'] for p in lock['package']}, {'0.3.0'})


if __name__ == '__main__':
    unittest.main()
