const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness(get) {
    let options;
    vm.runInNewContext(fs.readFileSync(__dirname + '/stats.js', 'utf8'), {
        Vue: { createApp(value) { options = value; return { mount() {} }; } },
        window: { location: { origin: 'http://test' } },
        axios: { get },
        console: { error() {} }
    });
    const app = options.data();
    for (const [name, fn] of Object.entries(options.methods)) app[name] = fn.bind(app);
    app.$refs = {};
    app.$nextTick = async (callback) => callback?.();
    for (const [name, fn] of Object.entries(options.computed)) Object.defineProperty(app, name, { get: fn.bind(app) });
    return app;
}

test('calendar date detail shows every scheduled word and switches history without another request', async () => {
    const words = Array.from({ length: 501 }, (_, id) => ({ word: `word-${id}`, due: '2026-10-30T00:00:00Z' }));
    let calls = 0;
    const app = harness(async (url, { params }) => {
        calls++;
        assert.equal(url, 'http://test/api/stats/calendar-words');
        assert.equal(params.date, '2026-10-30');
        assert.equal(params.limit, undefined);
        return { data: { data: { practiced: [{ word: 'studied' }], due: words } } };
    });
    await app.openCalendarWords({ date: '2026-10-30', practiced: 0, due_count: 501 });
    assert.equal(app.detailModal.type, 'calendar');
    assert.equal(app.detailModal.title, '2026-10-30');
    assert.equal(app.detailModal.items.length, 501);
    app.selectCalendarMode('practiced');
    assert.equal(app.detailModal.items[0].word, 'studied');
    assert.equal(calls, 1);
});

test('empty calendar dates open a dated empty list', async () => {
    const app = harness(async () => ({ data: { data: { practiced: [], due: [] } } }));
    await app.openCalendarWords({ date: '2026-10-30', practiced: 0, due_count: 0 });
    assert.equal(app.detailModal.visible, true);
    assert.equal(app.detailModal.title, '2026-10-30');
    assert.equal(app.detailModal.items.length, 0);
    assert.equal(app.detailModal.error, '');
});

test('calendar detail distinguishes empty results from failures and supports retry', async () => {
    let fail = true;
    const app = harness(async () => {
        if (fail) throw new Error('offline');
        return { data: { data: { practiced: [], due: [] } } };
    });
    await app.openCalendarWords({ date: '2026-10-30', practiced: 0, due_count: 1 });
    assert.match(app.detailModal.error, /重试/);
    assert.equal(app.detailModal.loading, false);
    fail = false;
    await app.loadCalendarWords();
    assert.equal(app.detailModal.error, '');
    assert.equal(app.detailModal.items.length, 0);
});

test('a late calendar response cannot overwrite a newer selected date', async () => {
    const pending = [];
    const app = harness(() => new Promise(resolve => pending.push(resolve)));
    const first = app.openCalendarWords({ date: '2026-10-29', practiced: 1, due_count: 0 });
    const second = app.openCalendarWords({ date: '2026-10-30', practiced: 0, due_count: 1 });
    pending[1]({ data: { data: { practiced: [], due: [{ word: 'tomorrow' }] } } });
    await second;
    pending[0]({ data: { data: { practiced: [{ word: 'today' }], due: [] } } });
    await first;
    assert.equal(app.detailModal.title, '2026-10-30');
    assert.equal(app.detailModal.items[0].word, 'tomorrow');
    app.closeDetailModal();
    assert.equal(app.detailModal.visible, false);
});

test('centered calendar covers all leap-year dates and marks the current month once', () => {
    const app = harness(async () => {});
    const days = [];
    for (let d = new Date('2023-08-01T00:00:00Z'); d <= new Date('2024-07-31T00:00:00Z'); d.setUTCDate(d.getUTCDate()+1)) {
        days.push({ date: d.toISOString().slice(0, 10), practiced: 0, due_count: 0 });
    }
    app.today = '2024-02-29';
    app.calendar = { start_date: '2023-08-01', end_date: '2024-07-31', days };
    assert.equal(app.calendarWeeks.flat().filter(Boolean).length, 366);
    assert.equal(app.calendarWeeks[0][0], null);
    assert.equal(app.calendarWeeks[0][2].date, '2023-08-01');
    assert.equal(app.calendarMonths.length, 12);
    assert.equal(app.calendarMonths.filter(month => month.current).length, 1);
    assert.equal(app.calendarMonths.find(month => month.current).month, '2024-02');
    assert.equal(app.calendarWeeks.flat().filter(Boolean).map(day => day.date).join(','), days.map(day => day.date).join(','));
});

test('top metrics count unique learned and mastered words and avoid false zeroes on failure', () => {
    const app = harness(async () => {});
    app.overview = { current_streak: 3, total_time_minutes: 125, total_words_practiced: 900 };
    app.vocabulary = { overall: { learned: 42, mastered: 12 } };
    assert.equal(app.overviewCards.map(card => card.label).join(','), '连续学习,已学习,已掌握,累计时长');
    assert.equal(app.overviewCards.map(card => card.value).join(','), '3,42,12,2.1');
    app.vocabularyError = true;
    assert.equal(app.overviewCards[1].value, '—');
});

test('calendar and natural-month activity load independently and use separate color scales', async () => {
    const app = harness(async (url) => ({ data: { data: url.endsWith('/calendar')
        ? { today: '2026-02-10', start_date: '2025-08-01', end_date: '2026-07-31', days: [
            { date: '2026-02-10', practiced: 4, due_count: 2 }, { date: '2026-02-11', practiced: 0, due_count: 4 }] }
        : { month: '2026-02', days: Array.from({ length: 28 }, (_, i) => ({ date: `2026-02-${String(i+1).padStart(2,'0')}`, words: 0, accuracy: null })) }
    } }));
    app.renderTrend = () => {};
    await app.loadCalendar();
    await app.loadTrend();
    assert.equal(app.calendarDayClass(app.calendar.days[0])[0], 'calendar-history-4');
    assert.equal(app.calendarDayClass(app.calendar.days[1])[0], 'calendar-due-4');
    assert.equal(app.trendData.length, 28);
    assert.equal(app.monthLabel, '2026 年 2 月');
    assert.equal(app.calendarError, false);
    assert.equal(app.trendError, false);
});

test('optimization history loads pages without replacing newer records', async () => {
    const app = harness(async (url, options) => {
        if (url.endsWith('/runs')) {
            const older = options.params.before_id === 4;
            return { data: { data: { items: [{ id: older ? 3 : 4 }], next_before_id: older ? null : 4 } } };
        }
        return { data: { data: { enabled: true, effective_reviews: 1400, minimum_reviews: 1000 } } };
    });
    await app.loadOptimization();
    assert.equal(app.optimization.status.effective_reviews, 1400);
    assert.equal(app.optimization.items[0].id, 4);
    await app.loadOptimization(true);
    assert.equal(app.optimization.items.map(item => item.id).join(','), '4,3');
    assert.equal(app.optimization.nextBeforeId, null);
    assert.equal(app.optimization.loading, false);
});

test('failed history pagination preserves records and cursor for retry', async () => {
    let fail = false;
    const app = harness(async (url) => {
        if (fail) throw new Error('offline');
        return { data: { data: url.endsWith('/runs') ? { items: [{ id: 4 }], next_before_id: 4 } : {} } };
    });
    await app.loadOptimization();
    fail = true;
    await app.loadOptimization(true);
    assert.equal(app.optimization.items[0].id, 4);
    assert.equal(app.optimization.nextBeforeId, 4);
    assert.match(app.optimization.error, /重试/);
    assert.equal(app.optimization.loading, false);
    fail = false;
    await app.loadOptimization();
    assert.equal(app.optimization.error, '');
    assert.equal(app.optimization.items.length, 1);
});

test('vocabulary detail loads later pages and retries without losing the first page', async () => {
    let fail = false;
    const offsets = [];
    const app = harness(async (url, { params }) => {
        assert.equal(url, 'http://test/api/stats/vocabulary-words');
        assert.equal(params.dimension, 'topic');
        assert.equal(params.value, '教育');
        assert.equal(params.status, 'all');
        offsets.push(params.offset);
        if (fail) throw new Error('offline');
        return { data: { data: { items: [{ word: params.offset ? 'second' : 'first' }], total: 2,
            next_offset: params.offset ? null : 1 } } };
    });
    await app.openVocabularyWords('topic', { value: '教育', label: '教育', learned: 1, learning: 1, total: 2, mastered: 0 });
    fail = true;
    await app.loadVocabularyWords(true);
    assert.equal(app.detailModal.items[0].word, 'first');
    assert.equal(app.detailModal.nextOffset, 1);
    assert.equal(app.detailModal.retryAppend, true);
    assert.match(app.detailModal.error, /重试/);
    fail = false;
    await app.loadVocabularyWords(app.detailModal.retryAppend);
    assert.equal(app.detailModal.items.map(item => item.word).join(','), 'first,second');
    assert.equal(app.detailModal.nextOffset, null);
    assert.equal(offsets.join(','), '0,1,1');
});

test('switching vocabulary filters resets paging and discards stale responses', async () => {
    const pending = [];
    const app = harness((url, { params }) => new Promise(resolve => pending.push({ resolve, params })));
    const initial = app.openVocabularyWords('cefr', { value: 'A1', label: '入门', learned: 2, learning: 1, total: 3, mastered: 1 });
    const filter = app.selectVocabularyStatus('mastered');
    assert.equal(pending[1].params.offset, 0);
    assert.equal(pending[1].params.status, 'mastered');
    pending[1].resolve({ data: { data: { items: [{ word: 'mastered' }], total: 1, next_offset: null } } });
    await filter;
    pending[0].resolve({ data: { data: { items: [{ word: 'old' }], total: 3, next_offset: 1 } } });
    await initial;
    assert.equal(app.detailModal.items[0].word, 'mastered');
    assert.equal(app.detailModal.total, 1);
    assert.equal(app.detailModal.nextOffset, null);
    assert.equal(app.detailModal.loading, false);
});

test('empty CEFR levels do not request words and vocabulary failures remain independent', async () => {
    let calls = 0;
    const app = harness(async () => { calls++; throw new Error('offline'); });
    await app.openVocabularyWords('cefr', { total: 0 });
    assert.equal(calls, 0);
    assert.equal(app.detailModal.visible, false);
    await app.loadVocabulary();
    assert.equal(app.vocabularyError, true);
    assert.equal(app.vocabularyLoading, false);
    assert.equal(app.loadError, false);
});

test('word errors expand by source identity, paginate, retry and preserve the containing list', async () => {
    let fail = false;
    const cursors = [];
    const app = harness(async (url, { params }) => {
        assert.equal(url, 'http://test/api/stats/word-errors');
        assert.equal(params.source_id, 'stable-source');
        cursors.push(params.before_id);
        if (fail) throw new Error('offline');
        return { data: { data: { items: [{ id: params.before_id ? 3 : 8, user_input: 'wrong' }],
            correct_attempts: 4, total_attempts: 6, next_before_id: params.before_id ? null : 8 } } };
    });
    const item = { id: 999, source_id: 'stable-source', word: 'same-spelling', total_attempts: 6 };
    app.detailModal.items = [item];
    await app.toggleWordErrors(item);
    assert.equal(item.errorHistory.expanded, true);
    assert.equal(item.correct_attempts, 4);
    assert.equal(item.total_attempts, 6);
    await app.toggleWordErrors(item);
    await app.toggleWordErrors(item);
    assert.equal(cursors.length, 1);
    fail = true;
    await app.loadWordErrors(item, true);
    assert.equal(item.errorHistory.items[0].id, 8);
    assert.equal(item.errorHistory.nextBeforeId, 8);
    assert.equal(item.errorHistory.retryAppend, true);
    fail = false;
    await app.loadWordErrors(item, item.errorHistory.retryAppend);
    assert.equal(item.errorHistory.items.map(row => row.id).join(','), '8,3');
    assert.equal(item.errorHistory.nextBeforeId, null);
    assert.equal(app.detailModal.items[0], item);
    assert.equal(cursors.join(','), '0,8,8');
});

test('word errors keep zero-history and request failure distinct, without mixing sources', async () => {
    let fail = true;
    const app = harness(async (url, { params }) => {
        if (fail) throw new Error('offline');
        return { data: { data: { items: [], correct_attempts: 0, total_attempts: 0, next_before_id: null } } };
    });
    const first = { source_id: 'first', total_attempts: 1 }, second = { source_id: 'second', total_attempts: 1 };
    await app.toggleWordErrors(first);
    assert.match(first.errorHistory.error, /重试/);
    assert.equal(first.errorHistory.loaded, false);
    fail = false;
    await app.toggleWordErrors(second);
    assert.equal(second.errorHistory.loaded, true);
    assert.equal(second.errorHistory.items.length, 0);
    assert.equal(second.errorHistory.error, '');
    assert.equal(first.errorHistory.loaded, false);
    await app.loadWordErrors(first);
    assert.equal(first.errorHistory.loaded, true);
    assert.equal(first.errorHistory.error, '');
});

test('unanswered words never expand history or request records', async () => {
    let calls = 0;
    const app = harness(async () => { calls++; });
    const item = { source_id: 'new', correct_attempts: 0, total_attempts: 0 };
    await app.toggleWordErrors(item);
    assert.equal(calls, 0);
    assert.equal(item.errorHistory, undefined);
});

test('input highlighting isolates substituted and extra characters without changing typed text', () => {
    const app = harness(async () => {});
    const wrong = app.highlightInput('library', 'libraxy');
    assert.equal(wrong.filter(part => part.kind === 'wrong').map(part => part.text).join(''), 'x');
    assert.equal(wrong.filter(part => part.kind === 'match').map(part => part.text).join(''), 'libray');
    const extra = app.highlightInput('library', 'libraryx');
    assert.equal(extra.filter(part => part.kind === 'extra').map(part => part.text).join(''), 'x');
    for (const [input, parts] of [['libraxy', wrong], ['libraryx', extra]]) {
        assert.equal(parts.filter(part => part.kind !== 'missing').map(part => part.text).join(''), input);
    }
});

test('missing letters mark gaps in the input without inserting the correct answer', () => {
    const app = harness(async () => {});
    const parts = app.highlightInput('library', 'libary');
    assert.equal(parts.map(part => part.text).join(''), 'lib□ary');
    assert.equal(parts.filter(part => part.kind === 'missing').length, 1);
    assert.equal(parts.filter(part => part.kind === 'wrong' || part.kind === 'extra').length, 0);
    const repeated = app.highlightInput('letter', 'leter');
    assert.equal(repeated.filter(part => part.kind === 'missing').length, 1);
    assert.equal(repeated.filter(part => part.kind !== 'missing').map(part => part.text).join(''), 'leter');
    const multiple = app.highlightInput('letter', 'lter');
    assert.equal(multiple.filter(part => part.kind === 'missing').length, 2);
});

test('highlighting chooses the closest accepted variant and preserves case and whitespace', () => {
    const app = harness(async () => {});
    const input = '  COLER!  ';
    const parts = app.highlightInput('colour/color', input);
    assert.equal(parts.map(part => part.text).join(''), input);
    assert.equal(parts.filter(part => part.kind === 'wrong').map(part => part.text).join(''), 'E');
    assert.equal(parts.some(part => part.kind === 'missing' || part.kind === 'extra'), false);
    const phrase = app.highlightInput('ice cream', ' ice  creem ');
    assert.equal(phrase.map(part => part.text).join(''), ' ice  creem ');
    assert.equal(phrase.filter(part => part.kind === 'wrong').map(part => part.text).join(''), 'e');
    assert.equal(app.highlightInput('library', '').length, 0);
    const invalid = '<3';
    assert.equal(app.highlightInput('library', invalid).map(part => part.text).join(''), invalid);
});
