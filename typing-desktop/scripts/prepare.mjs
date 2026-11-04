// Shared Tauri dev/build hook: render the frontend; media is distributed separately.
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const desktop = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repo = resolve(desktop, '..');
const python = [join(repo, '.venv', 'Scripts', 'python.exe'), join(repo, '.venv', 'bin', 'python')]
    .find(existsSync) || (process.platform === 'win32' ? 'python' : 'python3');
const result = spawnSync(python, ['-X', 'utf8', 'typing-desktop/scripts/build_frontend.py'], { cwd: repo, stdio: 'inherit' });
if (result.error) console.error(result.error.message);
if (result.status !== 0) process.exit(result.status || 1);
