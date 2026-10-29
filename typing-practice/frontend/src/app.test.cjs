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

test('free practice persists submissions and restores a failed submission for retry', async () => {
    const h = harness();
    h.app.practiceMode = 'free';
    h.app.beginCurrentWord();
    h.tick(2000);
    await h.app.submitInput('apple');
    assert.equal(h.app.stats.correct, 0);
    assert.equal(h.requests.length, 1);
    assert.ok(h.app.pendingAttempt);
    assert.ok(h.localStorage.getItem('typingPracticePending:fsrs:v1:attempt'));
    h.context.axios.post = async (url, payload) => ({ data: { data: {
        attempt_id: payload.attempt_id, is_correct: true, duration_ms: 2000
    } } });
    const restored = h.mount();
    await restored.restoreDraftSession();
    assert.equal(restored.practiceMode, 'free');
    assert.equal(restored.stats.correct, 1);
    assert.equal(restored.pendingAttempt, null);
    assert.equal(h.localStorage.getItem('typingPracticePending:fsrs:v1:attempt'), null);
});

test('mistake practice records only session feedback', async () => {
    const h = harness();
    h.app.practiceMode = 'mistakes';
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

for (const count of [3, 25]) {
    test(`formal practice completes the available ${count} words when the queue empties`, async () => {
        const h = harness();
        const summary = () => ({ total: count, due_count: 0, new_available: count - h.app.attemptedTotal });
        h.context.axios.get = async (url, { params } = {}) => {
            if (url.endsWith('/memory/summary')) return { data: { data: summary() } };
            assert.equal(params.limit, 1);
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
        assert.equal(h.app.resultTotal, count);
    });
}

for (const count of [3, 20]) {
    test(`free practice requests at most 20 words and saves all ${count} answers`, async () => {
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
        assert.equal(h.app.resultTotal, count);
        assert.equal(h.requests.length, count);
        assert.equal(queueRequests, 1);
    });
}

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
    assert.equal(h.app.resultTotal, 0);
    assert.equal(queueRequests, 0);
    await h.app.submitInput('book');
    await h.app.continueAfterConflict();
    assert.equal(h.app.isFinished, true);
    assert.equal(h.app.resultTotal, 0);
    assert.equal(queueRequests, 0);
});

test('an old unrecorded free draft starts a new round without replaying old counts', async () => {
    const h = harness();
    h.app.practiceMode = 'free';
    h.app.words = Array.from({ length: 125 }, () => ({ word: 'apple', source_id: 'apple' }));
    h.app.currentIndex = 5;
    h.app.stats.correct = 5;
    h.app.saveDraftSession();
    h.context.axios.get = async (url, { params }) => {
        assert.equal(params.mode, 'free');
        assert.equal(params.limit, 20);
        return { data: { data: {
            items: Array.from({ length: 20 }, (_, index) => ({ word: 'apple', attempt_id: `new-${index}` })),
            summary: { total: 125 }, server_time: new Date().toISOString()
        } } };
    };
    const restored = h.mount();
    assert.equal(await restored.restoreDraftSession(), true);
    assert.equal(restored.practiceMode, 'free');
    assert.equal(restored.progressTotal, 20);
    assert.equal(restored.progressCurrent, 1);
    assert.equal(restored.resultTotal, 0);
    assert.equal(h.requests.length, 0);
});

test('a legacy draft at the old 20-word limit continues loading available words', async () => {
    const h = harness();
    h.app.words = Array.from({ length: 20 }, () => ({ word: 'apple' }));
    h.app.currentIndex = 20;
    h.app.stats.correct = 20;
    h.app.saveDraftSession();
    const key = 'typingPracticeDraftSession:fsrs:v1:session';
    const draft = JSON.parse(h.localStorage.getItem(key));
    h.localStorage.setItem(key, JSON.stringify({ ...draft, sessionLimit: 20 }));
    h.context.axios.get = async () => ({ data: { data: {
        items: [{ word: 'book', source_id: 'book', attempt_id: 'next' }],
        summary: { total: 25, due_count: 0, new_available: 5 }, server_time: new Date().toISOString()
    } } });
    const restored = h.mount();
    assert.equal(await restored.restoreDraftSession(), true);
    assert.equal(restored.isFinished, false);
    assert.equal(restored.currentWord.word, 'book');
    assert.equal(restored.progressCurrent, 21);
    assert.equal(restored.progressTotal, 25);
});

test('an empty pool shows zero progress and no current question', async () => {
    const h = harness();
    h.context.axios.get = async () => ({ data: { data: {
        items: [], summary: { total: 0, due_count: 0, new_available: 0 }, server_time: new Date().toISOString()
    } } });
    await h.app.fetchWords();
    assert.equal(h.app.currentWord, null);
    assert.equal(h.app.progressTotal, 0);
    assert.equal(h.app.progressCurrent, 0);
});
