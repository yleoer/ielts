const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness() {
    const calls = [];
    const update = {
        version: '0.2.0', body: '改进练习体验',
        close: async () => calls.push('close'),
        async download(onEvent) {
            calls.push('download');
            onEvent({ event: 'Started', data: { contentLength: 100 } });
            onEvent({ event: 'Progress', data: { chunkLength: 40 } });
        },
        install: async () => calls.push('install'),
    };
    const context = {
        window: { __TAURI__: {
            app: { getVersion: async () => '0.1.0' },
            updater: { check: async () => update },
        } },
        Vue: { markRaw: value => value },
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(__dirname + '/workspace.js', 'utf8') + '\nthis.controls = workspaceControls;', context);
    const app = context.controls.data();
    app.$nextTick = fn => fn?.();
    for (const [name, fn] of Object.entries(context.controls.methods)) app[name] = fn.bind(app);
    for (const [name, fn] of Object.entries(context.controls.computed)) Object.defineProperty(app, name, { get: fn.bind(app) });
    app.saveDraftSession = () => calls.push('draft');
    return { app, update, calls, api: context.window.__TAURI__ };
}

test('checks the installed version and exposes release notes without installing', async () => {
    const { app, calls } = harness();
    await app.initUpdates();
    assert.equal(app.updates.current, '0.1.0');
    assert.equal(app.updates.available.version, '0.2.0');
    assert.equal(app.updates.available.body, '改进练习体验');
    assert.equal(app.updates.phase, 'available');
    assert.deepEqual(calls, []);
});

test('no newer version is reported as current, and an old update handle is released', async () => {
    const { app, calls, api } = harness();
    await app.initUpdates();
    api.updater.check = async () => null;
    await app.checkForUpdates();
    assert.equal(app.updates.phase, 'current');
    assert.equal(app.updates.available, null);
    assert.deepEqual(calls, ['close']);
});

test('downloads with progress, saves the practice draft, then installs with restart', async () => {
    const { app, update, calls } = harness();
    await app.initUpdates();
    update.install = async () => {
        assert.equal(app.updates.phase, 'installing');
        assert.equal(app.updates.downloaded, 40);
        assert.equal(app.updateProgress, 40);
        calls.push('install');
    };
    await app.installUpdate();
    assert.deepEqual(calls, ['download', 'draft', 'install']);
});

test('a failed download leaves the app running and can be retried', async () => {
    const { app, update, calls } = harness();
    await app.initUpdates();
    update.download = async () => { throw new Error('network'); };
    await app.installUpdate();
    assert.equal(app.updateBusy, false);
    assert.match(app.updates.error, /重试/);
    assert.deepEqual(calls, []);
    update.download = async () => calls.push('download');
    await app.installUpdate();
    assert.deepEqual(calls, ['download', 'draft', 'install']);
});

test('automatic check errors stay quiet; a manual check reports a recoverable error', async () => {
    const { app, api } = harness();
    api.updater.check = async () => { throw new Error('offline'); };
    await app.initUpdates();
    assert.equal(app.updates.error, '');
    await app.checkForUpdates();
    assert.match(app.updates.error, /检查更新失败/);
    assert.equal(app.updateBusy, false);
});

test('an answer awaiting save prevents installation', async () => {
    const { app, calls } = harness();
    await app.initUpdates();
    app.pendingAttempt = { attempt_id: 'unsaved' };
    await app.installUpdate();
    assert.match(app.updates.error, /答案.*保存/);
    assert.deepEqual(calls, []);
});

test('settings cannot close while downloading, and duplicate checks are ignored', async () => {
    const { app, calls } = harness();
    app.setup.visible = true;
    app.updates.phase = 'downloading';
    app.closeSettings();
    assert.equal(app.setup.visible, true);
    await app.checkForUpdates();
    assert.deepEqual(calls, []);
});
