import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest


SPEC = importlib.util.spec_from_file_location('desktop_version', Path(__file__).with_name('version.py'))
version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version)


class VersionTests(unittest.TestCase):
    def test_tag_must_match_workspace_version(self):
        self.assertEqual(version.release_tag('0.2.1', 'desktop-v0.2.1'), 'desktop-v0.2.1')
        with self.assertRaisesRegex(ValueError, '不一致'):
            version.release_tag('0.2.1', 'desktop-v0.2.0')

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
