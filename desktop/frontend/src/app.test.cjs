/* Behavior tests use the real Vue options with browser services stubbed. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Lets fire-and-forget summary reads finish.
const settle = () => new Promise(resolve => setImmediate(resolve));

function harness() {
    let options;
    let now = 0;
    const timers = [];
    const requests = [];
    const storage = () => {
        const values = {};
        return new Proxy({
            getItem: key => values[key] ?? null,
            setItem: (key, value) => { values[key] = String(value); },
            removeItem: key => { delete values[key]; }
        }, { ownKeys: () => Object.keys(values), getOwnPropertyDescriptor: () => ({ enumerable: true, configurable: true, writable: true }) });
    };
    const document = { hidden: false };
    const localStorage = storage();
    const context = {
        Vue: { createApp: value => { options = value; return { mount() {} }; } },
        window: { location: { origin: 'http://test' },
            setTimeout: (fn, delay) => { timers.push({ fn, delay, active: true }); return timers.length; },
            clearTimeout: id => { if (timers[id - 1]) timers[id - 1].active = false; } },
        document, localStorage,
        performance: { now: () => now }, crypto: { randomUUID: () => 'session' },
        console, Date, Map, JSON, Math,
        axios: { post: async (url, payload) => { requests.push(JSON.parse(JSON.stringify(payload))); throw new Error('offline'); } }
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(__dirname + '/workspace.js', 'utf8'), context);
    vm.runInContext(fs.readFileSync(__dirname + '/pronunciation.js', 'utf8'), context);
    vm.runInContext(fs.readFileSync(__dirname + '/app.js', 'utf8'), context);
    function mount() {
        const app = options.data();
        app.$nextTick = fn => { if (fn) fn(); return Promise.resolve(); };
        app.$refs = {};
        for (const [name, fn] of Object.entries(options.methods)) app[name] = fn.bind(app);
        for (const [name, fn] of Object.entries(options.computed)) Object.defineProperty(app, name, { get: fn.bind(app) });
        return app;
    }
    const app = mount();
    app.sessionId = 'session';
    app.words = [{ word: 'apple', source_id: 'apple', chinese_meaning: '苹果', attempt_id: 'attempt', issued_at: new Date().toISOString() }];
    return { app, mount, context, timers, requests, localStorage, document,
        wordChanged() { options.watch.currentWord.call(app); }, tick(ms) { now += ms; } };
}

test('native tray hide pauses practice and excludes hidden time until the window returns', () => {
    const h = harness();
    const listeners = {};
    h.context.window.__TAURI__ = { event: { listen(name, callback) { listeners[name] = callback; } } };
    h.context.window.matchMedia = () => ({ matches: false, addEventListener() {} });
    h.context.window.addEventListener = h.document.addEventListener = () => {};
    h.context.setInterval = () => {};
    h.context.axios.get = async () => ({ data: { data: { last_sync_at: null } } });
    let stopped = 0;
    h.app.stopWordAudio = () => { stopped++; };
    h.app.initDesktopShell();
    h.app.userInput = 'app';
    h.app.beginCurrentWord();
    h.tick(1500);
    listeners['cijian-window-hidden']();
    assert.equal(stopped, 1);
    assert.equal(h.app.clockStartedAt, null);
    assert.equal(h.app.userInput, 'app');
    h.tick(10000);
    listeners['cijian-window-shown']();
    assert.equal(h.app.effectiveDuration(), 1500);
    h.tick(500);
    assert.equal(h.app.effectiveDuration(), 2000);
});

test('merged answers from another device replace an untouched formal word, never typed input or results', async () => {
    const h = harness();
    const listeners = {};
    h.context.window.__TAURI__ = { event: { listen(name, callback) { listeners[name] = callback; } } };
    h.context.window.matchMedia = () => ({ matches: false, addEventListener() {} });
    h.context.window.addEventListener = h.document.addEventListener = () => {};
    h.context.setInterval = () => {};
    let queues = 0;
    h.context.axios.get = async url => {
        if (!url.endsWith('/practice/queue')) return { data: { data: { last_sync_at: null, total: 2 } } };
        queues++;
        return { data: { data: { items: [{ word: 'book', source_id: 'book', attempt_id: `book-${queues}` }], summary: { total: 2 } } } };
    };
    h.app.initDesktopShell();
    h.app.userInput = 'app';
    await listeners['cijian-answers-merged']();
    assert.equal(h.app.currentWord.word, 'apple', 'typing has started');
    assert.equal(h.app.userInput, 'app');
    h.app.userInput = '';
    await listeners['cijian-answers-merged']();
    assert.equal(h.app.currentWord.attempt_id, 'book-1');
    await h.app.quitPractice();
    h.app.stats.correct = 1;
    h.app.finishPractice({ abandoned: true });
    await listeners['cijian-answers-merged']();
    assert.equal(h.app.isFinished, true, 'results stay until dismissed');
    assert.equal(queues, 1);
});

test('a word reloaded while hidden in the tray starts timing only when the window returns', async () => {
    const h = harness();
    const listeners = {};
    h.context.window.__TAURI__ = { event: { listen(name, callback) { listeners[name] = callback; } } };
    h.context.window.matchMedia = () => ({ matches: false, addEventListener() {} });
    h.context.window.addEventListener = h.document.addEventListener = () => {};
    h.context.setInterval = () => {};
    h.context.axios.get = async url => url.endsWith('/practice/queue')
        ? { data: { data: { items: [{ word: 'book', source_id: 'book', attempt_id: 'book' }], summary: { total: 2 } } } }
        : { data: { data: { last_sync_at: null, total: 2 } } };
    h.app.initDesktopShell();
    h.app.beginCurrentWord();
    listeners['cijian-window-hidden']();
    await listeners['cijian-answers-merged']();
    assert.equal(h.app.currentWord.word, 'book');
    assert.equal(h.app.clockStartedAt, null);
    h.tick(60000);
    listeners['cijian-window-shown']();
    h.tick(800);
    assert.equal(h.app.effectiveDuration(), 800);
});

test('resource installation refreshes URLs without replacing the active question or typed answer', async () => {
    const h = harness();
    h.app.words[0].id = 41;
    h.app.userInput = 'app';
    h.context.axios.get = async () => ({ data: { data: { phase: 'ready', id: 'package', installed: true, busy: false } } });
    let requests = 0;
    h.context.axios.post = async (url, payload) => {
        assert.equal(url, '/api/resources/urls');
        assert.deepEqual(Array.from(payload.ids), [41]);
        requests++;
        return { data: { data: [{ id: 41, illustration_url: '/api/media/41/illustration?v=new', audio_urls: {} }] } };
    };
    const attempt = h.app.currentWord.attempt_id;
    await h.app.loadResourceStatus();
    await h.app.loadResourceStatus();
    assert.equal(h.app.currentWord.attempt_id, attempt);
    assert.equal(h.app.userInput, 'app');
    assert.equal(h.app.currentWord.illustration_url, '/api/media/41/illustration?v=new');
    assert.equal(requests, 1);
});

test('settings load resources without reading the server and pause practice until closed', async () => {
    const h = harness();
    h.app.clockStartedAt = 0;
    h.tick(1000);
    h.context.axios.get = async url => {
        assert.equal(url, '/api/resources/status');
        return { data: { data: { installed: false, phase: 'idle', busy: false } } };
    };
    await h.app.openSettings();
    assert.equal(h.app.clockStartedAt, null);
    assert.equal(h.app.setup.visible, true);
    assert.equal(h.app.resources.status.installed, false);
    assert.equal(h.app.serverSettings.loaded, false);
    h.tick(5000);
    h.app.closeSettings();
    assert.equal(h.app.setup.visible, false);
    assert.equal(h.app.elapsedMs, 1000);
    assert.equal(h.app.clockStartedAt, 6000);
});

test('settings show the installed resource version, or mark a package built before versioning', () => {
    const h = harness();
    const counts = { files: 21890, kinds: { illustration: 7298 } };
    h.app.resources.status = { installed: true, counts, version: '2026.11.19' };
    assert.equal(h.app.resourceSummaryText, `已安装 ${(7298).toLocaleString()} 张插图、${(14592).toLocaleString()} 段音频 · 版本 2026.11.19`);
    h.app.resources.status = { installed: true, counts, version: null };
    assert.match(h.app.resourceSummaryText, / · 未标注版本$/);
});

test('autostart reads system state and saves each toggle independently of the server', async () => {
    const h = harness();
    let systemEnabled = true;
    const calls = [];
    h.context.window.__TAURI__ = { core: { invoke: async (command, args) => {
        calls.push(command);
        if (command === 'get_autostart') return systemEnabled;
        assert.equal(command, 'set_autostart');
        systemEnabled = args.enabled;
    } } };
    await h.app.loadAutostartSettings();
    assert.equal(h.app.autostartSettings.enabled, true);
    h.app.autostartSettings.enabled = false;
    await h.app.saveAutostartSettings();
    assert.equal(systemEnabled, false);
    h.app.autostartSettings.enabled = true;
    await h.app.saveAutostartSettings();
    assert.equal(systemEnabled, true);
    // Changes outside the app are read again when settings are reopened.
    systemEnabled = false;
    await h.app.loadAutostartSettings();
    assert.equal(h.app.autostartSettings.enabled, false);
    assert.equal(h.app.autostartSettings.savedEnabled, false);
    assert.equal(h.requests.length, 0);
    assert.deepEqual(calls, ['get_autostart', 'set_autostart', 'set_autostart', 'get_autostart']);
});

test('autostart errors support retry and preserve the saved value while blocking duplicate saves', async () => {
    const h = harness();
    h.context.window.__TAURI__ = { core: { invoke: async () => { throw new Error('unavailable'); } } };
    await h.app.loadAutostartSettings();
    assert.equal(h.app.autostartSettings.loaded, false);
    assert.match(h.app.autostartSettings.error, /重试/);
    assert.equal(h.app.desktopSettings.error, '');
    h.context.window.__TAURI__.core.invoke = async () => false;
    await h.app.loadAutostartSettings();
    assert.equal(h.app.autostartSettings.error, '');
    let rejectSave, saves = 0;
    h.context.window.__TAURI__.core.invoke = () => {
        saves++;
        return new Promise((resolve, reject) => { rejectSave = reject; });
    };
    h.app.setup.visible = true;
    h.app.autostartSettings.enabled = true;
    const saving = h.app.saveAutostartSettings();
    assert.equal(h.app.autostartSettings.saving, true);
    h.app.closeSettings();
    assert.equal(h.app.setup.visible, true);
    await h.app.saveAutostartSettings();
    assert.equal(saves, 1);
    rejectSave(new Error('access denied'));
    await saving;
    assert.equal(h.app.autostartSettings.enabled, false);
    assert.equal(h.app.autostartSettings.saving, false);
    assert.match(h.app.autostartSettings.error, /重试/);
    h.app.closeSettings();
    assert.equal(h.app.setup.visible, false);
});

test('an interrupted local import can be cancelled', async () => {
    const h = harness();
    const calls = [];
    h.context.axios.post = async url => { calls.push(url); return { data: { data: {} } }; };
    h.context.axios.get = async () => ({ data: { data: { phase: 'idle', busy: false } } });
    h.app.resources.status = { phase: 'uploading', id: 'interrupted', busy: true };
    await h.app.cancelResourceUpload();
    assert.equal(calls[0], '/api/resources/cancel?id=interrupted');
    assert.equal(h.app.resourceBusy, false);
});

test('resource settings upload in chunks without requiring server settings', async () => {
    const h = harness();
    h.app.words = [];
    h.app.setup.visible = true;
    const calls = [];
    h.context.axios.post = async (url, body) => {
        calls.push(url);
        return { data: { data: url.endsWith('/upload') ? { id: 'package', chunk_size: 4 } : {} } };
    };
    h.context.axios.get = async () => ({ data: { data: { phase: 'ready', id: 'package', installed: true, busy: false } } });
    const target = { files: [{ name: 'media.zip', size: 8, slice: () => ({ arrayBuffer: async () => new ArrayBuffer(4) }) }], value: 'selected' };
    await h.app.importResources({ target });
    assert.equal(h.app.serverSettings.loaded, false);
    assert.equal(h.app.setup.visible, true);
    assert.equal(h.app.resources.status.installed, true);
    assert.equal(target.value, '');
    assert.deepEqual(calls, [
        '/api/resources/upload',
        '/api/resources/chunk?id=package&offset=0',
        '/api/resources/chunk?id=package&offset=4',
        '/api/resources/finish?id=package'
    ]);
});

test('exiting practice preserves saved answers without submitting the unfinished word', () => {
    const h = harness();
    h.context.confirm = () => { throw new Error('exiting practice must not ask for confirmation'); };
    h.app.practiceMode = 'free';
    h.app.words.push({ word: 'book', source_id: 'book', attempt_id: 'unfinished' });
    h.app.currentIndex = 1;
    h.app.stats.correct = 1;
    h.app.userInput = 'bo';
    h.app.beginCurrentWord();
    h.tick(500);
    let stopped = 0;
    h.app.stopWordAudio = () => { stopped++; };
    h.app.quitPractice();
    assert.equal(h.app.isFinished, true);
    assert.equal(h.app.isPracticeAbandoned, true);
    assert.equal(h.app.attemptedTotal, 1);
    assert.equal(h.app.stats.incorrect, 0);
    assert.equal(h.requests.length, 0);
    assert.equal(h.app.clockStartedAt, null);
    assert.equal(stopped, 1);
});

test('a failed answer must be saved or resolved before exiting practice', async () => {
    const h = harness();
    h.app.practiceMode = 'free';
    await h.app.submitInput('apple');
    h.context.confirm = () => { throw new Error('cannot confirm exit before saving'); };
    h.app.quitPractice();
    assert.equal(h.app.isFinished, false);
    assert.equal(h.app.pendingAttempt.attempt_id, 'attempt');
    assert.match(h.app.submitError, /先重试保存/);
    assert.equal(h.requests.length, 1);
    assert.equal(h.app.attemptedTotal, 0);
});

test('exiting before any saved answer returns to the waiting page instead of empty results', async () => {
    const h = harness();
    const summary = { total: 5, due_count: 2, new_available: 0, next_due: null };
    h.context.axios.get = async url => { assert.equal(url, '/api/memory/summary'); return { data: { data: summary } }; };
    h.app.beginCurrentWord();
    h.app.quitPractice();
    assert.equal(h.app.isFinished, false);
    assert.equal(h.app.isIdle, true);
    assert.equal(h.app.showProgress, false);
    await settle();
    assert.equal(h.app.planReady, true);
    assert.equal(h.app.planActionLabel, '开始复习');
    assert.equal(h.app.planText, '待复习 2 个');
});

test('finished results offer Done until words are due, then continue the plan', async () => {
    const h = harness();
    // Relative to the page clock so the rounded countdown is exactly ten minutes.
    const due = new Date(h.app.clockNow + 10 * 60000).toISOString();
    let summary = { total: 5, due_count: 0, new_available: 0, next_due: due };
    let queues = 0;
    h.context.axios.get = async url => {
        if (url.endsWith('/practice/queue')) { queues++; return { data: { data: { items: [], summary } } }; }
        return { data: { data: summary } };
    };
    h.app.stats = { correct: 1, incorrect: 0, errors: [] };
    h.app.summary = summary;
    h.app.finishPractice();
    assert.equal(h.app.isFinished, true);
    assert.equal(h.app.watchesPlan, true);
    assert.equal(h.app.planCount, 0);
    assert.match(h.app.planStatusText, /^下次复习 (今天|明天) \d\d:\d\d（10 分钟后）$/);

    // Far-off due times are re-read every minute; a near one just after it is due.
    const activeTimers = () => h.timers.filter(item => item.active);
    h.app.schedulePlanCheck();
    assert.equal(activeTimers().length, 1);
    assert.equal(activeTimers()[0].delay, 60000);
    h.app.summary = { ...summary, next_due: new Date(Date.now() + 5000).toISOString() };
    h.app.schedulePlanCheck();
    assert.equal(activeTimers().length, 1);
    assert.ok(activeTimers()[0].delay > 4000 && activeTimers()[0].delay <= 5200);
    summary = { total: 5, due_count: 1, new_available: 0, next_due: null };
    await h.app.checkPlan();
    assert.equal(h.app.planCount, 1);
    assert.equal(h.app.planStatusText, '待复习 1 个');
    await h.app.continuePlan();
    assert.equal(queues, 1);
});

test('results open at the top with the sheet focused instead of the bottom button', () => {
    const h = harness();
    const focused = [];
    h.app.$refs.resultsSheet = { focus: options => focused.push(options) };
    h.app.$refs.practiceMain = { scrollTop: 480 };
    h.app.revealResults();
    assert.deepEqual(focused.map(options => ({ ...options })), [{ preventScroll: true }]);
    assert.equal(h.app.$refs.practiceMain.scrollTop, 0);
});

test('Done on results goes to the waiting page without requesting a queue', async () => {
    const h = harness();
    const summary = { total: 5, due_count: 0, new_available: 0, next_due: new Date(h.app.clockNow + 3 * 3600000).toISOString() };
    h.context.axios.get = async url => { assert.equal(url, '/api/memory/summary'); return { data: { data: summary } }; };
    h.app.practiceMode = 'difficult';
    h.app.stats = { correct: 0, incorrect: 1, errors: [] };
    h.app.summary = summary;
    h.app.finishPractice();
    assert.equal(h.app.isFinished, true);
    await h.app.continuePlan();
    assert.equal(h.app.isFinished, false);
    assert.equal(h.app.isIdle, true);
    assert.equal(h.app.practiceMode, 'normal');
    assert.equal(h.app.attemptedTotal, 0);
    assert.equal(h.app.planReady, false);
    assert.match(h.app.nextDueText, /（3 小时后）$/);
});

test('hiding to the tray closes results and showing the window re-reads the plan', async () => {
    const h = harness();
    const listeners = {};
    h.context.window.__TAURI__ = { event: { listen(name, callback) { listeners[name] = callback; } } };
    h.context.window.matchMedia = () => ({ matches: false, addEventListener() {} });
    h.context.window.addEventListener = h.document.addEventListener = () => {};
    h.context.setInterval = () => {};
    let summaries = 0;
    h.context.axios.get = async url => {
        if (url.endsWith('/memory/summary')) summaries++;
        return { data: { data: { last_sync_at: null, total: 5, due_count: 0, new_available: 3 } } };
    };
    h.app.initDesktopShell();
    h.app.stats = { correct: 1, incorrect: 0, errors: [] };
    h.app.finishPractice();
    const before = summaries;
    listeners['cijian-window-hidden']();
    assert.equal(h.app.isFinished, false);
    assert.equal(h.app.isIdle, true);
    listeners['cijian-window-shown']();
    await settle();
    assert.ok(summaries >= before + 2);
    assert.equal(h.app.planReady, true);
    assert.equal(h.app.planActionLabel, '开始学习');
});

test('the plan check does not read the summary while a question is shown', async () => {
    const h = harness();
    h.context.axios.get = async () => { throw new Error('no summary while practising'); };
    assert.equal(h.app.watchesPlan, false);
    await h.app.checkPlan();
    assert.equal(h.app.planTimer, null);
    assert.equal(h.app.showProgress, true);
});

test('due times read as today, tomorrow or a date with a countdown', () => {
    const h = harness();
    const now = Date.parse('2026-11-15T02:00:00Z'); // 10:00 in Beijing
    assert.equal(h.app.formatDueTime('2026-11-15T02:00:30Z', now), '今天 10:00（1 分钟内）');
    assert.equal(h.app.formatDueTime('2026-11-15T02:25:00Z', now), '今天 10:25（25 分钟后）');
    assert.equal(h.app.formatDueTime('2026-11-15T03:30:00Z', now), '今天 11:30（1 小时 30 分钟后）');
    assert.equal(h.app.formatDueTime('2026-11-15T16:05:00Z', now), '明天 00:05（14 小时 5 分钟后）');
    assert.equal(h.app.formatDueTime('2026-11-18T01:00:00Z', now), '11月18日 09:00（2 天后）');
});

test('clicking a practice meaning plays its pronunciation and mouse users can keep typing', () => {
    const h = harness();
    let played, focused = 0, stopped = 0;
    h.app.playWord = word => { played = word; };
    h.app.stopWordAudio = () => { stopped++; };
    h.app.$refs.inputField = { focus() { focused++; } };
    const word = h.app.currentWord;
    h.app.playPracticeWord(word, { detail: 1 });
    assert.equal(played, word);
    assert.equal(h.app.currentWord.attempt_id, 'attempt');
    assert.equal(h.app.userInput, '');
    assert.equal(focused, 1);
    h.app.playPracticeWord(word, { detail: 0 });
    assert.equal(focused, 1, 'keyboard activation keeps focus on the button');
    h.wordChanged();
    assert.equal(stopped, 1);
});

test('Chinese senses keep the primary visible and fold extras after the first two', () => {
    const h = harness();
    const senses = Array.from({ length: 6 }, (_, i) => ({ part_of_speech: 'n.', chinese_meaning: `义项 ${i}` }));
    h.app.currentWord.chinese_senses = senses;
    assert.deepEqual(h.app.primaryChineseSense, senses[0]);
    assert.deepEqual(h.app.secondaryChineseSenses, senses.slice(1, 3));
    assert.deepEqual(h.app.remainingChineseSenses, senses.slice(3));
    h.app.toggleOtherSenses({ detail: 0 });
    assert.equal(h.app.otherSensesExpanded, true);
    h.app.toggleOtherSenses({ detail: 0 });
    assert.equal(h.app.otherSensesExpanded, false);
});

test('mouse activation restores input focus after toggling senses', () => {
    const h = harness();
    h.app.currentWord.chinese_senses = Array.from({ length: 5 }, (_, i) => ({ chinese_meaning: `义项 ${i}` }));
    const focused = [];
    h.app.$refs.inputField = { focus(options) { focused.push(options); } };
    h.app.rememberSensePointer({ pointerType: 'mouse' });
    h.app.toggleOtherSenses({ detail: 1 });
    assert.equal(focused.length, 1);
    assert.equal(focused[0].preventScroll, true);
});

test('keyboard activation does not restore input focus even after a mouse pointerdown', () => {
    const h = harness();
    h.app.currentWord.chinese_senses = Array.from({ length: 4 }, () => ({ chinese_meaning: '义项' }));
    let focused = false;
    h.app.$refs.inputField = { focus() { focused = true; } };
    h.app.rememberSensePointer({ pointerType: 'mouse' });
    h.app.toggleOtherSenses({ detail: 0 });
    assert.equal(h.app.otherSensesExpanded, true);
    assert.equal(focused, false);
});

test('switching words and resetting a round collapse extra senses without altering answers', () => {
    const h = harness();
    h.app.otherSensesExpanded = true;
    h.app.userInput = 'app';
    h.wordChanged();
    assert.equal(h.app.otherSensesExpanded, false);
    assert.equal(h.app.userInput, 'app');
    h.app.otherSensesExpanded = true;
    h.app.resetInputState();
    assert.equal(h.app.otherSensesExpanded, false);
});

test('mistake practice keeps every sense and does not submit the word again', async () => {
    const h = harness();
    const senses = [{ part_of_speech: 'n.', chinese_meaning: '苹果' },
        { part_of_speech: 'n.', chinese_meaning: '苹果树' }];
    h.app.currentWord.chinese_senses = senses;
    let submissions = 0;
    h.context.axios.post = async () => {
        submissions++;
        return { data: { data: { attempt_id: 'attempt', is_correct: false } } };
    };
    await h.app.submitInput('aple');
    h.app.startMistakePractice();
    assert.deepEqual(h.app.currentChineseSenses, senses);
    assert.equal(h.app.isMistakePractice, true);
    await h.app.submitInput('apple');
    assert.equal(h.app.stats.correct, 1);
    assert.equal(submissions, 1);
});

test('effective time excludes hidden pages', () => {
    const h = harness();
    h.app.beginCurrentWord();
    h.tick(6000);
    h.app.userInput = 'a';
    h.app.handleInput();
    h.app.pauseClock();
    h.document.hidden = true;
    h.tick(60000);
    assert.equal(h.app.effectiveDuration(), 6000);
    h.document.hidden = false;
    h.app.resumeClock();
    h.tick(500);
    assert.equal(h.app.effectiveDuration(), 6500);
    assert.equal(h.app.firstInputMs, 6000);
});

test('a failed save keeps the answer for a retry that reuses its time and counts once', async () => {
    const h = harness();
    h.app.beginCurrentWord();
    h.tick(7000);
    await h.app.submitInput('apple');
    assert.equal(h.app.attemptedTotal, 0);
    assert.ok(h.app.submitError);
    assert.equal(h.app.pendingAttempt.duration_ms, 7000);
    const original = h.requests[0];
    h.tick(90000);
    h.context.axios.post = async (url, payload) => {
        assert.deepEqual(JSON.parse(JSON.stringify(payload)), original);
        return { data: { data: { attempt_id: 'attempt', is_correct: true } } };
    };
    await h.app.retryPending();
    assert.equal(h.app.attemptedTotal, 1);
    assert.equal(h.app.pendingAttempt, null);
    await h.app.retryPending();
    assert.equal(h.app.attemptedTotal, 1);
});

test('corrected spelling waits for Enter and does not submit a second review', async () => {
    const h = harness();
    h.app.practiceMode = 'mistakes';
    h.app.words.push({ word: 'book', source_id: 'book' });
    await h.app.submitInput('aple');
    let prevented = false;
    h.app.handleBeforeInput({ data: 'a', preventDefault() { prevented = true; } });
    assert.equal(prevented, false);
    h.app.userInput = 'apple';
    for (const timer of h.timers.filter(timer => timer.active)) timer.fn();
    assert.equal(h.app.currentIndex, 0);
    assert.equal(h.app.showAnswer, true);
    assert.equal(h.app.isAdvancing, false);
    h.app.handleKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(h.app.currentWord.word, 'book');
    assert.equal(h.app.stats.incorrect, 1);
    assert.equal(h.app.stats.correct, 0);
    assert.equal(h.requests.length, 0);
});

test('conflict offers recovery without changing local counts', async () => {
    const h = harness();
    h.context.axios.post = async () => { throw { response: { status: 409, data: { error: 'stale' } } }; };
    h.app.beginCurrentWord();
    await h.app.submitInput('apple');
    assert.equal(h.app.submissionConflict, true);
    assert.equal(h.app.attemptedTotal, 0);
    let loaded = false;
    h.app.loadNextWord = async () => { loaded = true; };
    await h.app.continueAfterConflict();
    assert.equal(loaded, true);
    assert.equal(h.app.pendingAttempt, null);
});

// More than the old 20-word round: formal practice runs until the queue is empty.
test('formal practice completes all 25 available words when the queue empties', async () => {
    const count = 25;
    const h = harness();
    const summary = () => ({ total: count, due_count: 0, new_available: count - h.app.attemptedTotal });
    h.context.axios.get = async (url, { params } = {}) => {
        if (url.endsWith('/memory/summary')) return { data: { data: summary() } };
        assert.equal(params.limit, 3);
        const index = h.app.attemptedTotal;
        return { data: { data: {
            items: index < count ? [{ word: 'apple', source_id: `apple-${index}`, attempt_id: `attempt-${index}` }] : [],
            summary: summary(), server_time: new Date().toISOString()
        } } };
    };
    h.context.axios.post = async (url, payload) => ({ data: { data: {
        attempt_id: payload.attempt_id, is_correct: true, duration_ms: 1000
    } } });
    await h.app.fetchWords();
    assert.equal(h.app.progressTotal, count);
    for (let index = 0; index < count; index++) {
        assert.equal(h.app.isFinished, false);
        assert.equal(h.app.progressCurrent, index + 1);
        await h.app.submitInput('apple');
        await h.app.nextWord();
        assert.equal(h.app.progressTotal, count);
    }
    assert.equal(h.app.isFinished, true);
    assert.equal(h.app.attemptedTotal, count);
});

test('free practice requests at most 20 words and saves all of them', async () => {
    const count = 20;
    const h = harness();
    let queueRequests = 0;
    h.context.axios.get = async (url, { params } = {}) => {
        if (url.endsWith('/memory/summary')) return { data: { data: { total: 125 } } };
        queueRequests++;
        assert.equal(params.mode, 'free');
        assert.equal(params.limit, 20);
        return { data: { data: {
            items: Array.from({ length: count }, (_, index) => ({ word: 'apple', source_id: `apple-${index}`, attempt_id: `free-${index}` })),
            summary: { total: 125 }, server_time: new Date().toISOString()
        } } };
    };
    h.context.axios.post = async (url, payload) => {
        h.requests.push(payload);
        return { data: { data: { attempt_id: payload.attempt_id, is_correct: true, duration_ms: 1000 } } };
    };
    await h.app.fetchWords({ mode: 'free' });
    assert.equal(h.app.progressTotal, count);
    for (let index = 0; index < count; index++) {
        assert.equal(h.app.isFinished, false);
        await h.app.submitInput('apple');
        await h.app.nextWord();
    }
    assert.equal(h.app.isFinished, true);
    assert.equal(h.app.attemptedTotal, count);
    assert.equal(h.requests.length, count);
    assert.equal(queueRequests, 1);
});

for (const [mode, label] of [['difficult', '难点突破'], ['stale', '久未练习']]) test(`${mode} practice saves every answer of its selected batch`, async () => {
    const count = 3;
    const h = harness();
    let queues = 0;
    h.context.axios.get = async (url, { params } = {}) => {
        if (url.endsWith('/memory/summary')) return { data: { data: { total: 125 } } };
        queues++;
        assert.equal(params.mode, mode);
        assert.equal(params.limit, 20);
        return { data: { data: {
            items: Array.from({ length: count }, (_, index) => ({ word: 'apple', source_id: `apple-${index}`, attempt_id: `${mode}-${index}` })),
            summary: { total: 125 }
        } } };
    };
    h.context.axios.post = async (url, payload) => {
        h.requests.push(payload);
        return { data: { data: { attempt_id: payload.attempt_id, is_correct: true, duration_ms: 1000 } } };
    };
    await (mode === 'stale' ? h.app.startStalePractice() : h.app.startDifficultPractice());
    assert.equal(h.app.practiceMode, mode);
    assert.equal(h.app.titlebarNote, `${label} · 最多 20 个`);
    assert.equal(h.app.progressTotal, count);
    for (let index = 0; index < count; index++) {
        await h.app.submitInput('apple');
        await h.app.nextWord();
    }
    assert.equal(h.app.isFinished, true);
    assert.equal(h.app.attemptedTotal, count);
    assert.deepEqual(h.requests.map(request => request.attempt_id), [`${mode}-0`, `${mode}-1`, `${mode}-2`]);
    assert.equal(queues, 1);
});

test('a free practice conflict skips the stale word without fetching another batch', async () => {
    const h = harness();
    h.app.practiceMode = 'free';
    h.app.words.push({ word: 'book', source_id: 'book', attempt_id: 'second' });
    let queueRequests = 0;
    h.context.axios.get = async url => {
        if (url.endsWith('/practice/queue')) queueRequests++;
        return { data: { data: { total: 2 } } };
    };
    h.context.axios.post = async () => { throw { response: { status: 409, data: { error: 'stale' } } }; };
    await h.app.submitInput('apple');
    await h.app.continueAfterConflict();
    assert.equal(h.app.currentWord.word, 'book');
    assert.equal(h.app.attemptedTotal, 0);
    assert.equal(queueRequests, 0);
    await h.app.submitInput('book');
    await h.app.continueAfterConflict();
    // Nothing was saved, so there is no result to review: back to the waiting page.
    assert.equal(h.app.isFinished, false);
    assert.equal(h.app.isIdle, true);
    assert.equal(h.app.practiceMode, 'normal');
    assert.equal(h.app.attemptedTotal, 0);
    assert.equal(queueRequests, 0);
});

test('an empty pool shows the sync prompt without progress', async () => {
    const h = harness();
    h.context.axios.get = async () => ({ data: { data: {
        items: [], summary: { total: 0, due_count: 0, new_available: 0 }, server_time: new Date().toISOString()
    } } });
    await h.app.fetchWords();
    assert.equal(h.app.currentWord, null);
    assert.equal(h.app.isIdle, true);
    assert.equal(h.app.showProgress, false);
    assert.equal(h.app.planReady, false);
});

test('counts and advancement follow the saved result, then the core selects the next word', async () => {
    const h = harness();
    let confirm;
    h.context.axios.post = (url, payload, config) => {
        assert.equal(config.params, undefined);
        return new Promise(resolve => { confirm = resolve; });
    };
    let queues = 0;
    h.context.axios.get = async () => {
        queues++;
        return { data: { data: { items: [{ word: 'book', source_id: 'book', attempt_id: 'next' }],
            summary: { total: 2, due_count: 0, new_available: 1 } } } };
    };
    h.app.beginCurrentWord();
    h.tick(1000);
    const submission = h.app.submitInput('apple');
    let blocked = false;
    h.app.handleBeforeInput({ data: 'a', preventDefault() { blocked = true; } });
    assert.equal(blocked, true, 'the input is locked while saving');
    assert.equal(h.app.attemptedTotal, 0);
    confirm({ data: { data: { attempt_id: 'attempt', is_correct: true } } });
    await submission;
    assert.equal(h.app.attemptedTotal, 1);
    assert.equal(h.app.cardClass, 'is-success');
    assert.equal(h.timers.at(-1).delay, 180);
    await h.app.nextWord();
    assert.equal(queues, 1);
    assert.equal(h.app.currentWord.word, 'book');
    assert.equal(h.app.currentIndex, 1);
});

test('a wrong answer waits for the correct spelling and Enter', async () => {
    const h = harness();
    h.app.practiceMode = 'free';
    h.app.words.push({ word: 'book', source_id: 'book' });
    h.context.axios.post = async () => ({ data: { data: { attempt_id: 'attempt', is_correct: false } } });
    await h.app.submitInput('aple');
    assert.equal(h.app.showAnswer, true);
    assert.equal(h.app.lastWrongInput, 'aple');
    assert.equal(h.app.stats.incorrect, 1);
    assert.equal(h.app.isAdvancing, false);
    let shaken = 0;
    h.app.triggerShake = () => { shaken++; };
    h.app.userInput = 'appel';
    h.app.handleKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(h.app.currentIndex, 0);
    assert.equal(shaken, 1);
    h.app.userInput = 'apple';
    h.app.handleKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(h.app.currentWord.word, 'book');
    assert.equal(h.app.stats.incorrect, 1);
});

test('formal previews preload illustrations without appending speculative practice items', async () => {
    const h = harness();
    const images = [];
    h.context.Image = class { set src(value) { images.push(value); } };
    h.context.axios.get = async () => ({ data: { data: {
        items: Array.from({ length: 3 }, (_, i) => ({ word: `word-${i}`, attempt_id: `item-${i}`, illustration_url: `/image-${i}?v=1` })),
        summary: { total: 3 }, server_time: new Date().toISOString()
    } } });
    await h.app.fetchWords();
    assert.equal(h.app.words.length, 1);
    assert.equal(h.app.currentWord.word, 'word-0');
    assert.deepEqual(images, ['/image-0?v=1', '/image-1?v=1', '/image-2?v=1']);
    h.app.preloadIllustrations(h.app.words);
    assert.equal(images.length, 3);
});

function serverStub(h, { configured, saveError } = {}) {
    const calls = [];
    let serverConfigured = Boolean(configured);
    h.context.axios = {
        get: async url => {
            calls.push(['get', url]);
            if (url.endsWith('/settings/server')) return { data: { data: serverConfigured
                ? { configured: true, url: 'https://sync.example.com', has_token: true, editable: true, source: 'file' }
                : { configured: false, url: null, has_token: false, editable: true, source: null } } };
            if (url.endsWith('/resources/status')) return { data: { data: { installed: false, phase: 'idle', busy: false } } };
            return { data: { data: { history: [] } } };
        },
        post: async (url, body) => {
            calls.push(['post', url, body]);
            if (url.endsWith('/settings/server') && saveError) throw { response: { data: { error: saveError } } };
            if (url.endsWith('/settings/server')) {
                serverConfigured = true;
                return { data: { data: { configured: true, url: body.url.trim().replace(/\/$/, ''), has_token: true, editable: true } } };
            }
            return { data: { data: { success: true, message: 'ok' } } };
        }
    };
    h.app.fetchWords = async () => { calls.push(['fetchWords']); };
    h.app.refreshSummary = async () => {};
    return calls;
}

test('first launch requires server settings before practice', async () => {
    const h = harness();
    serverStub(h);
    assert.equal(await h.app.checkServerSetup(), true);
    assert.equal(h.app.syncModal.visible, true);
    assert.equal(h.app.serverSettings.required, true);
    assert.equal(h.app.serverSettings.editing, true);
    assert.equal(h.app.setup.visible, false);
    assert.equal(h.app.resources.status, null);
    h.app.closeSyncModal();
    assert.equal(h.app.syncModal.visible, true, 'the first connection cannot be dismissed');
});

test('a configured server skips the setup dialog', async () => {
    const h = harness();
    serverStub(h, { configured: true });
    assert.equal(await h.app.checkServerSetup(), false);
    assert.equal(h.app.setup.visible, false);
    assert.equal(h.app.serverSettings.url, 'https://sync.example.com');
    assert.equal(h.app.serverSettings.hasToken, true);
    assert.equal(h.app.serverSettings.savedUrl, 'https://sync.example.com');
    assert.equal(h.app.serverSettings.editing, false);
});

test('saving the first server syncs and then loads practice', async () => {
    const h = harness();
    const calls = serverStub(h);
    await h.app.checkServerSetup();
    Object.assign(h.app.serverSettings, { url: 'https://sync.example.com', token: 'secret' });
    await h.app.saveServerSettings();
    const saved = calls.find(call => call[1]?.endsWith('/settings/server') && call[0] === 'post')[2];
    assert.equal(JSON.stringify(saved), JSON.stringify({ url: 'https://sync.example.com', token: 'secret' }));
    assert.equal(h.app.setup.visible, false);
    assert.equal(h.app.syncModal.visible, true, 'saving stays in the sync panel');
    assert.equal(h.app.serverSettings.required, false);
    assert.equal(h.app.serverSettings.editing, false, 'a successful save collapses the form');
    assert.equal(h.app.serverSettings.token, '', 'the token is not kept in page state');
    const order = calls.map(call => call[0] === 'fetchWords' ? 'fetchWords' : call[1]?.replace('http://test/api', ''));
    assert.ok(order.indexOf('/sync/now') < order.indexOf('fetchWords'), order.join(','));
});

test('changing the server in sync keeps a blank token and does not reset practice', async () => {
    const h = harness();
    const calls = serverStub(h, { configured: true });
    await h.app.openSyncModal();
    h.app.editServerSettings();
    h.app.serverSettings.url = 'https://other.example.com/';
    h.app.serverSettings.token = '';
    await h.app.saveServerSettings();
    const saved = calls.find(call => call[0] === 'post' && call[1].endsWith('/settings/server'))[2];
    assert.equal(saved.token, '');
    assert.equal(h.app.serverSettings.url, 'https://other.example.com');
    assert.equal(h.app.serverSettings.hasToken, true);
    assert.equal(h.app.serverSettings.savedUrl, 'https://other.example.com');
    assert.equal(h.app.serverSettings.editing, false);
    assert.equal(h.app.syncModal.visible, true);
    assert.equal(calls.some(call => call[0] === 'fetchWords'), false);
});

test('server validation cannot be dismissed or submitted twice while it is running', async () => {
    const h = harness();
    serverStub(h, { configured: true });
    await h.app.openSyncModal();
    h.app.editServerSettings();
    let checked, checks = 0;
    const post = h.context.axios.post;
    h.context.axios.post = (url, body) => {
        if (!url.endsWith('/settings/server')) return post(url, body);
        checks++;
        return new Promise(resolve => { checked = resolve; });
    };
    const saving = h.app.saveServerSettings();
    assert.equal(h.app.serverSettings.saving, true);
    h.app.closeSyncModal();
    assert.equal(h.app.syncModal.visible, true);
    h.app.cancelServerEdit();
    assert.equal(h.app.serverSettings.editing, true, 'saving cannot be cancelled halfway through');
    await h.app.saveServerSettings();
    assert.equal(checks, 1);
    checked({ data: { data: { url: 'https://sync.example.com', has_token: true } } });
    await saving;
    assert.equal(h.app.serverSettings.saving, false);
    h.app.closeSyncModal();
    assert.equal(h.app.syncModal.visible, false);
});

test('a rejected server change stays editable and cancelling restores the configured address', async () => {
    const h = harness();
    const calls = serverStub(h, { configured: true, saveError: '访问令牌无效' });
    await h.app.openSyncModal();
    h.app.editServerSettings();
    h.app.serverSettings.url = 'https://other.example.com';
    h.app.serverSettings.token = 'wrong';
    await h.app.saveServerSettings();
    assert.equal(h.app.serverSettings.editing, true);
    assert.equal(h.app.serverSettings.url, 'https://other.example.com');
    assert.equal(h.app.serverSettings.savedUrl, 'https://sync.example.com');
    assert.equal(h.app.serverSettings.error, '访问令牌无效');
    assert.equal(h.app.syncModal.visible, true);
    assert.equal(h.app.serverSettings.saving, false);
    assert.equal(calls.some(call => call[1]?.endsWith('/sync/now')), false);
    h.app.cancelServerEdit();
    assert.equal(h.app.serverSettings.editing, false);
    assert.equal(h.app.serverSettings.error, '');
    assert.equal(h.app.serverSettings.token, '');
    assert.equal(h.app.serverSettings.url, 'https://sync.example.com');
});
