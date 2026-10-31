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
        window: { location: { origin: 'http://test' },
            setTimeout: (fn, delay) => { timers.push({ fn, delay, active: true }); return timers.length; },
            clearTimeout: id => { if (timers[id - 1]) timers[id - 1].active = false; } },
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
    return { app, mount, context, timers, requests, localStorage, document,
        wordChanged() { options.watch.currentWord.call(app); }, tick(ms) { now += ms; } };
}

test('an empty queue has no Chinese senses', () => {
    const h = harness();
    h.app.words = [];
    assert.equal(h.app.currentChineseSenses.length, 0);
    assert.equal(h.app.primaryChineseSense, null);
    assert.equal(h.app.secondaryChineseSenses.length, 0);
    assert.equal(h.app.remainingChineseSenses.length, 0);
});

for (const extras of [0, 1, 2, 3, 5]) {
    test(`${extras} additional senses keep the primary visible and fold only extras after the first two`, () => {
        const h = harness();
        const senses = Array.from({ length: extras + 1 }, (_, i) => ({ part_of_speech: 'n.', chinese_meaning: `义项 ${i}` }));
        h.app.currentWord.chinese_senses = senses;
        for (const mode of ['normal', 'free', 'mistakes']) {
            h.app.practiceMode = mode;
            h.app.otherSensesExpanded = false;
            assert.deepEqual(h.app.primaryChineseSense, senses[0]);
            assert.deepEqual(h.app.secondaryChineseSenses, senses.slice(1, 3));
            assert.deepEqual(h.app.remainingChineseSenses, senses.slice(3));
            h.app.toggleOtherSenses({ detail: 0 });
            assert.equal(h.app.otherSensesExpanded, extras > 2);
            assert.deepEqual(h.app.secondaryChineseSenses, senses.slice(1, 3));
            assert.deepEqual(h.app.remainingChineseSenses, senses.slice(3));
            h.app.toggleOtherSenses({ detail: 0 });
            assert.equal(h.app.otherSensesExpanded, false);
        }
        assert.equal(h.requests.length, 0);
        assert.equal(h.app.attemptedTotal, 0);
    });
}

for (const pointerType of ['mouse', 'touch', 'pen', '']) {
    test(`sense toggle with ${pointerType || 'assistive'} activation preserves native focus except for a mouse`, () => {
        const h = harness();
        h.app.currentWord.chinese_senses = Array.from({ length: 5 }, (_, i) => ({ chinese_meaning: `义项 ${i}` }));
        const focused = [];
        h.app.$refs.inputField = { focus(options) { focused.push(options); } };
        h.app.userInput = 'app';
        h.app.rememberSensePointer({ pointerType });
        h.app.toggleOtherSenses({ detail: pointerType ? 1 : 0 });
        assert.equal(h.app.otherSensesExpanded, true);
        assert.equal(focused.length, pointerType === 'mouse' ? 1 : 0);
        if (focused.length) assert.equal(focused[0].preventScroll, true);
        assert.equal(h.app.userInput, 'app');
        assert.equal(h.app.sensePointerType, '');
        assert.equal(h.requests.length, 0);
        assert.equal(h.app.attemptedTotal, 0);
    });
}

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

test('drafts retain every sense but restore the presentation in its default collapsed state', async () => {
    const h = harness();
    const senses = Array.from({ length: 5 }, (_, i) => ({ part_of_speech: '', chinese_meaning: `义项 ${i}` }));
    h.app.currentWord.chinese_senses = senses;
    h.app.otherSensesExpanded = true;
    h.app.saveDraftSession();
    const restored = h.mount();
    await restored.restoreDraftSession();
    assert.deepEqual(restored.currentChineseSenses, senses);
    assert.deepEqual(restored.primaryChineseSense, senses[0]);
    assert.deepEqual(restored.secondaryChineseSenses, senses.slice(1, 3));
    assert.deepEqual(restored.remainingChineseSenses, senses.slice(3));
    assert.equal(restored.otherSensesExpanded, false);
});

test('legacy drafts restore the primary meaning and remain submittable', async () => {
    const h = harness();
    h.app.currentWord.part_of_speech = 'n.';
    h.app.saveDraftSession();
    const restored = h.mount();
    assert.equal(await restored.restoreDraftSession(), true);
    assert.deepEqual(JSON.parse(JSON.stringify(restored.currentChineseSenses)), [
        { part_of_speech: 'n.', chinese_meaning: '苹果' }
    ]);
    h.context.axios.post = async () => ({ data: { data: { attempt_id: 'attempt', is_correct: true } } });
    await restored.submitInput('apple');
    assert.equal(restored.stats.correct, 1);
    restored.currentWord.chinese_senses = [];
    restored.currentWord.part_of_speech = '';
    assert.equal(restored.currentChineseSenses[0].part_of_speech, '');
    assert.equal(restored.currentChineseSenses[0].chinese_meaning, '苹果');
});

test('all senses survive draft restoration and mistake practice without duplicate reviews', async () => {
    const h = harness();
    const senses = [{ part_of_speech: 'n.', chinese_meaning: '苹果' },
        { part_of_speech: 'n.', chinese_meaning: '苹果树' }];
    h.app.currentWord.chinese_senses = senses;
    h.app.saveDraftSession();
    const restored = h.mount();
    await restored.restoreDraftSession();
    assert.deepEqual(restored.currentChineseSenses, senses);
    let submissions = 0;
    h.context.axios.post = async () => {
        submissions++;
        return { data: { data: { attempt_id: 'attempt', is_correct: false } } };
    };
    await restored.submitInput('aple');
    restored.startMistakePractice();
    assert.deepEqual(restored.currentChineseSenses, senses);
    assert.equal(restored.isMistakePractice, true);
    await restored.submitInput('apple');
    assert.equal(restored.stats.correct, 1);
    assert.equal(submissions, 1);
});

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

test('correct feedback is immediate but counts and advancement wait for server confirmation', async () => {
    const h = harness();
    let confirm;
    h.context.axios.post = (url, payload, config) => {
        assert.equal(config.params.next_limit, 3);
        return new Promise(resolve => { confirm = resolve; });
    };
    h.context.axios.get = async () => { throw new Error('unnecessary queue request'); };
    h.app.beginCurrentWord();
    h.tick(1000);
    const submission = h.app.submitInput('apple');
    assert.equal(h.app.isCorrect, true);
    assert.equal(h.app.cardClass, 'is-success');
    assert.equal(h.app.answerAccepted, false);
    assert.equal(h.app.attemptedTotal, 0);
    await h.app.nextWord();
    assert.equal(h.app.currentIndex, 0);
    h.tick(500);
    confirm({ data: { data: { attempt_id: 'attempt', is_correct: true }, next_queue: {
        items: [{ word: 'book', source_id: 'book', attempt_id: 'next' }],
        summary: { total: 2, due_count: 0, new_available: 1 }, server_time: new Date().toISOString()
    } } });
    await submission;
    assert.equal(h.app.attemptedTotal, 1);
    assert.equal(h.timers.at(-1).delay, 0); // Network waiting already covered the feedback interval.
    const draft = JSON.parse(h.localStorage.getItem('typingPracticeDraftSession:fsrs:v1:session'));
    assert.equal('nextQueue' in draft, false);
    await h.app.nextWord();
    assert.equal(h.app.currentWord.word, 'book');
    assert.equal(h.app.currentIndex, 1);
    assert.equal(h.app.attemptedTotal, 1);
});

test('restoring a saved answer fetches a fresh queue instead of persisting short-lived candidates', async () => {
    const h = harness();
    h.context.axios.post = async () => ({ data: { data: { attempt_id: 'attempt', is_correct: true } } });
    await h.app.submitInput('apple');
    let fetched = 0;
    h.context.axios.get = async () => {
        fetched++;
        return { data: { data: { items: [{ word: 'book', source_id: 'book', attempt_id: 'fresh' }],
            summary: { total: 2 }, server_time: new Date().toISOString() } } };
    };
    const restored = h.mount();
    assert.equal(await restored.restoreDraftSession(), true);
    assert.equal(fetched, 1);
    assert.equal(restored.currentWord.word, 'book');
    assert.equal(restored.currentIndex, 1);
    assert.equal(restored.attemptedTotal, 1);
});

test('correction can begin during a slow save and survives confirmation without another review', async () => {
    const h = harness();
    let confirm;
    h.context.axios.post = () => new Promise(resolve => { confirm = resolve; });
    const submission = h.app.submitInput('aple');
    assert.equal(h.app.showAnswer, true);
    assert.equal(h.app.lastWrongInput, 'aple');
    let blocked = false;
    h.app.handleBeforeInput({ data: 'a', preventDefault() { blocked = true; } });
    assert.equal(blocked, false);
    h.app.userInput = 'apple';
    h.app.startCorrectAdvance();
    h.timers.at(-1).fn();
    assert.equal(h.app.currentIndex, 0);
    assert.equal(h.app.attemptedTotal, 0);
    confirm({ data: { data: { attempt_id: 'attempt', is_correct: false } } });
    await submission;
    assert.equal(h.app.userInput, 'apple');
    assert.equal(h.app.stats.incorrect, 1);
    assert.equal(h.app.isAdvancing, true);
    assert.equal(h.timers.at(-1).delay, 0);
});

test('server correction overrides a local preview and is the only result counted', async () => {
    const h = harness();
    h.context.axios.post = async () => ({ data: { data: { attempt_id: 'attempt', is_correct: false } } });
    await h.app.submitInput('apple');
    assert.equal(h.app.isCorrect, false);
    assert.equal(h.app.showAnswer, true);
    assert.equal(h.app.stats.correct, 0);
    assert.equal(h.app.stats.incorrect, 1);
    assert.equal(h.app.isAdvancing, false);
});

for (const reason of ['expired', 'newly-due']) {
    test(`a ${reason} buffered queue is refreshed before selecting the next real item`, async () => {
        const h = harness();
        h.app.nextQueue = { items: [{ word: 'stale' }], summary: {
            next_due: reason === 'newly-due' ? new Date(0).toISOString() : null
        }, server_time: new Date().toISOString() };
        h.app.nextQueueReceivedAt = Date.now() - (reason === 'expired' ? 6000 : 0);
        h.app.answerAccepted = true;
        let requests = 0;
        h.context.axios.get = async () => {
            requests++;
            return { data: { data: { items: [{ word: 'due', attempt_id: 'due' }],
                summary: { total: 2 }, server_time: new Date().toISOString() } } };
        };
        await h.app.nextWord();
        assert.equal(requests, 1);
        assert.equal(h.app.currentWord.word, 'due');
    });
}

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
