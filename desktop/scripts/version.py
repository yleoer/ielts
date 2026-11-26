"""Cargo 工作区是桌面版本的唯一来源；更新版本，或核对是否为待发布的新版本。"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]
NOTES_END = 'CIJIAN_NOTES_END'


def validate_version(value):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('版本号使用正式版三段数字，例如 0.2.1')
    return value


def version_key(value):
    return tuple(int(part) for part in value.split('.'))


def read_version(root=ROOT):
    config = tomllib.loads(root.joinpath('Cargo.toml').read_text(encoding='utf-8'))
    return validate_version(config['workspace']['package']['version'])


def released_versions(listing):
    """Versions in `git ls-remote --tags` output. A Release creates its desktop-v tag when published."""
    return re.findall(r'refs/tags/desktop-v(\d+\.\d+\.\d+)$', listing, re.M)


def is_unreleased(value, released):
    """True above every release, False for the latest one; going back below it is an error."""
    latest = max(released, key=version_key, default=None)
    if latest is None or version_key(value) > version_key(latest):
        return True
    if value == latest:
        return False
    raise ValueError(f'版本 {value} 低于已发布的 {latest}，请用 --set 设为更高的版本')


def release_notes(root, value):
    """The `## <version>` section of CHANGELOG.md, used as the Release body and the in-app notes."""
    text = root.joinpath('CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## {re.escape(value)}[ \t]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match or not match[1].strip():
        raise ValueError(f'CHANGELOG.md 缺少 {value} 的更新说明')
    return match[1].strip()


def release_outputs(root, listing):
    value = read_version(root)
    new = is_unreleased(value, released_versions(listing))
    lines = [f'version={value}', f'new={str(new).lower()}']
    if new:
        lines += [f'notes<<{NOTES_END}', release_notes(root, value), NOTES_END]
    return '\n'.join(lines) + '\n'


def set_version(root, value):
    validate_version(value)
    manifest = root / 'Cargo.toml'
    text = manifest.read_text(encoding='utf-8')
    text = re.sub(r'(\[workspace\.package\][\s\S]*?\nversion\s*=\s*")[^"]+(")',
                  lambda match: f'{match[1]}{value}{match[2]}', text, count=1)
    manifest.write_text(text, encoding='utf-8')
    # Only refresh workspace versions; keep third-party dependencies locked.
    subprocess.run(['cargo', 'update', '--workspace', '--offline'], cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--set', dest='new_version', help='设置版本，同时刷新 Cargo.lock')
    action.add_argument('--check-release', action='store_true',
                        help='对照已发布的 desktop-v 标签判断是否为新版本，新版本还需 CHANGELOG.md 中的更新说明；'
                             '在 Actions 中写入步骤输出，本机直接打印')
    args = parser.parse_args()
    try:
        if args.check_release:
            listing = subprocess.run(['git', 'ls-remote', '--tags', 'origin', 'desktop-v*'], cwd=ROOT,
                                     check=True, capture_output=True, text=True).stdout
            outputs = release_outputs(ROOT, listing)
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as target:
                    target.write(outputs)
            else:
                print(outputs, end='')
            return
        if args.new_version:
            set_version(ROOT, args.new_version)
        print(read_version())
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
