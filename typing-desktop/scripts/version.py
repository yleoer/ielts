"""Cargo 工作区是桌面版本的唯一来源；更新版本或校验发布标签。"""
import argparse
from pathlib import Path
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def validate_version(value):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('版本号使用正式版三段数字，例如 0.2.1')
    return value


def read_version(root=ROOT):
    config = tomllib.loads(root.joinpath('Cargo.toml').read_text(encoding='utf-8'))
    return validate_version(config['workspace']['package']['version'])


def release_tag(value, tag):
    expected = f'desktop-v{value}'
    if tag != expected:
        raise ValueError(f'标签 {tag} 与桌面版本不一致，应为 {expected}')
    return expected


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
    action.add_argument('--tag', help='验证 desktop-v<版本> 标签')
    args = parser.parse_args()
    try:
        if args.new_version:
            set_version(ROOT, args.new_version)
        value = read_version()
        if args.tag:
            release_tag(value, args.tag)
    except ValueError as error:
        parser.error(str(error))
    print(value)


if __name__ == '__main__':
    main()
