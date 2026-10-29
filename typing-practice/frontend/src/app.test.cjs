/* Behavior tests use the real Vue options with browser services stubbed. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

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
    const sessionStorage = storage();
    const context = {
        Vue: { createApp: value => { options = value; return { mount() {} }; } },
        window: { location: { origin: 'http://test' }, setTimeout: fn => { timers.push(fn); return timers.length; }, clearTimeout() {} },
        document, localStorage, sessionStorage,
        performance: { now: () => now }, crypto: { randomUUID: () => 'session' },
        console, Date, Map, JSON, Math,
        axios: { post: async (url, payload) => { requests.push(JSON.parse(JSON.stringify(payload))); throw new Error('offline'); } }
    };
    vm.runInNewContext(fs.readFileSync(__dirname + '/app.js', 'utf8'), context);
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
    return { app, mount, context, timers, requests, localStorage, document, tick(ms) { now += ms; } };
}

test('effective time excludes hidden pages and survives draft restoration', async () => {
    const h = harness();
    h.app.beginCurrentWord();
    h.tick(6000);
    h.app.userInput = 'a';
    h.app.handleInput();
    h.app.pauseClock();
    h.document.hidden = true;
    h.tick(60000);
    assert.equal(h.app.effectiveDuration(), 6000);
    h.app.saveDraftSession();
    h.tick(60000);
    h.document.hidden = false;
    const restored = h.mount();
    assert.equal(await restored.restoreDraftSession(), true);
    h.tick(500);
    assert.equal(restored.effectiveDuration(), 6500);
    assert.equal(restored.firstInputMs, 6000);
});

test('failed submission is durable, reuses timestamp and is counted once after retry', async () => {
    const h = harness();
    h.app.beginCurrentWord();
    h.tick(7000);
    await h.app.submitInput('apple');
    assert.equal(h.app.attemptedTotal, 0);
    assert.ok(h.localStorage.getItem('typingPracticePending:fsrs:v1:attempt'));
    const original = h.requests[0];
    h.tick(90000);
    h.context.axios.post = async (url, payload) => {
        assert.deepEqual(JSON.parse(JSON.stringify(payload)), original);
        return { data: { data: { attempt_id: 'attempt', is_correct: true, rating_name: 'Good', duration_ms: 7000 } } };
    };
    const restored = h.mount();
    await restored.restoreDraftSession();
    assert.equal(restored.attemptedTotal, 1);
    assert.equal(restored.pendingAttempt, null);
    assert.equal(h.localStorage.getItem('typingPracticePending:fsrs:v1:attempt'), null);
    await restored.retryPending();
    assert.equal(restored.attemptedTotal, 1);
});

test('correction allows typing and does not submit a second review', async () => {
    const h = harness();
    h.app.answerAccepted = true;
    h.app.showAnswer = true;
    let prevented = false;
    h.app.handleBeforeInput({ data: 'a', preventDefault() { prevented = true; } });
    assert.equal(prevented, false);
    await h.app.submitInput('apple');
    assert.equal(h.requests.length, 0);
});

test('free practice records only session feedback', async () => {
    const h = harness();
    h.app.practiceMode = 'free';
    h.app.beginCurrentWord();
    h.tick(2000);
    await h.app.submitInput('apple');
    assert.equal(h.app.stats.correct, 1);
    assert.equal(h.requests.length, 0);
});

test('storage failure blocks network submission instead of losing the outbox', async () => {
    const h = harness();
    h.localStorage.setItem = () => { throw new Error('quota'); };
    h.app.beginCurrentWord();
    h.tick(2000);
    await h.app.submitInput('apple');
    assert.ok(h.app.pendingAttempt);
    assert.ok(h.app.storageError);
    assert.equal(h.requests.length, 0);
});

test('a failed acknowledged draft save prevents advancing and can be recovered', async () => {
    const h = harness();
    const originalSet = h.localStorage.setItem;
    h.context.axios.post = async () => {
        h.localStorage.setItem = () => { throw new Error('quota'); };
        return { data: { data: { attempt_id: 'attempt', is_correct: true, rating_name: 'Good', duration_ms: 7000 } } };
    };
    h.app.beginCurrentWord();
    h.tick(7000);
    await h.app.submitInput('apple');
    assert.equal(h.app.attemptedTotal, 1);
    assert.equal(h.app.isAdvancing, false);
    assert.ok(h.app.storageError);
    assert.ok(h.localStorage.getItem('typingPracticePending:fsrs:v1:attempt'));
    h.localStorage.setItem = originalSet;
    h.app.retryDraftSave();
    assert.equal(h.app.isAdvancing, true);
    assert.equal(h.localStorage.getItem('typingPracticePending:fsrs:v1:attempt'), null);
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
