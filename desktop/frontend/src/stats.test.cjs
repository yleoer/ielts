const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness(get, globals = {}) {
    let options;
    const context = vm.createContext({
        Vue: { createApp(value) { options = value; return { mount() {} }; } },
        window: { location: { origin: 'http://test' }, clearTimeout() {} },
        axios: { get },
        document: { activeElement: null },
        ...globals
    });
    vm.runInContext(fs.readFileSync(__dirname + '/workspace.js', 'utf8'), context);
    vm.runInContext(fs.readFileSync(__dirname + '/pronunciation.js', 'utf8'), context);
    vm.runInContext(fs.readFileSync(__dirname + '/stats.js', 'utf8'), context);
    const app = options.data();
    for (const [name, fn] of Object.entries(options.methods)) app[name] = fn.bind(app);
    app.$refs = {};
    app.$nextTick = async (callback) => callback?.();
    for (const [name, fn] of Object.entries(options.computed)) Object.defineProperty(app, name, { get: fn.bind(app) });
    return app;
}

test('statistics opens resource settings without reading server settings and restores focus', async () => {
    let focused = false;
    const opener = { focus() { focused = true; } };
    const app = harness(async url => {
        assert.equal(url, '/api/resources/status');
        return { data: { data: { installed: false, phase: 'idle', busy: false } } };
    }, { document: { activeElement: opener } });
    await app.openSettings();
    assert.equal(app.setup.visible, true);
    assert.equal(app.serverSettings.loaded, false);
    assert.equal(app.resources.status.installed, false);
    app.closeSettings();
    assert.equal(app.setup.visible, false);
    assert.equal(focused, true);
});

test('statistics sync refreshes statistics in place after successful synchronization', async () => {
    const requests = [];
    const batch = { id: 7, synced_at: '2026-11-03T05:44:49Z', added_words: 20 };
    const status = { history: [batch], added_words: 20, last_anki_sync_at: '2026-11-03T05:44:49Z',
        last_sync_at: '2026-11-03T06:00:00Z' };
    const app = harness(async () => ({ data: { data: { history: [] } } }), {
        axios: {
            get: async url => ({ data: { data: url.endsWith('/settings/server')
                ? { configured: true, url: 'https://sync.example', has_token: true, editable: true } : status } }),
            post: async url => { requests.push(url); return { data: { data: { ...status, success: true, message: '同步完成' } } }; }
        }
    });
    let refreshed = 0;
    app.loadAllData = async () => { refreshed++; };
    await app.openSyncModal();
    assert.equal(app.syncHistory()[0], batch);
    assert.equal(app.syncModal.status.added_words, 20);
    await app.syncNow();
    assert.equal(app.syncModal.visible, true);
    assert.equal(app.syncModal.status.message, '同步完成');
    assert.equal(app.syncModal.syncing, false);
    assert.equal(app.syncHistory()[0].synced_at, batch.synced_at);
    assert.equal(app.syncModal.status.last_anki_sync_at, status.last_anki_sync_at);
    assert.equal(app.lastSyncAt, status.last_sync_at);
    assert.equal(refreshed, 1);
    assert.deepEqual(requests, ['/api/sync/now']);
});

test('sync shows environment server settings as read-only while allowing synchronization', async () => {
    const posts = [];
    const get = async url => ({ data: { data: url.endsWith('/settings/server')
        ? { configured: true, url: 'https://env.example', has_token: true, editable: false } : { history: [] } } });
    const app = harness(get, { axios: { get, post: async url => { posts.push(url); return { data: { data: { history: [] } } }; } } });
    app.afterSync = async () => {};
    await app.openSyncModal();
    assert.equal(app.serverSettings.url, 'https://env.example');
    assert.equal(app.serverSettings.editable, false);
    assert.equal(app.serverSettings.editing, false);
    await app.syncNow();
    assert.deepEqual(posts, ['/api/sync/now']);
    assert.equal(app.setup.visible, false);
});

const statsData = {
    overview: { current_streak: 1, total_time_minutes: 0.4 },
    calendar: { today: '2026-02-10', start_date: '2025-08-01', end_date: '2026-07-31', days: [
        { date: '2026-02-10', practiced: 4, due_count: 2 }, { date: '2026-02-11', practiced: 0, due_count: 4 }] },
    'recent-activity': { days: Array.from({ length: 30 }, (_, i) => ({
        date: new Date(Date.UTC(2026, 0, 12 + i)).toISOString().slice(0, 10), words: 0, accuracy: null })) },
    'vocabulary-progress': { overall: { learned: 5, mastered: 1 }, levels: [], topics: [] }
};
const statsGet = url => ({ data: { data: statsData[url.split('/').pop()] } });

test('statistics load together and a refresh keeps the page mounted', async () => {
    const pending = [];
    const app = harness(url => new Promise(resolve => pending.push({ url, resolve })));
    app.renderTrend = app.centerCalendar = () => {};
    app.loading = false;
    const refresh = app.afterSync();
    assert.equal(app.loading, false, 'refresh must keep the existing chart container mounted');
    assert.deepEqual(pending.map(item => item.url),
        ['/api/stats/overview', '/api/stats/calendar', '/api/stats/recent-activity', '/api/stats/vocabulary-progress']);
    for (const { url, resolve } of pending) resolve(statsGet(url));
    await refresh;
    assert.equal(app.today, '2026-02-10');
    assert.equal(app.calendarFocusDate, '2026-02-10');
    assert.equal(app.overviewCards[1].value, 5);
});

test('any failed statistics request shows one page error and retrying reloads everything', async () => {
    let fail = true;
    const app = harness(async url => {
        if (fail && url.endsWith('/vocabulary-progress')) throw new Error('broken');
        return statsGet(url);
    });
    app.renderTrend = app.centerCalendar = () => {};
    await app.loadAllData();
    assert.equal(app.loadError, true);
    assert.equal(app.loading, false);
    fail = false;
    await app.loadAllData();
    assert.equal(app.loadError, false);
    assert.equal(app.vocabulary.overall.learned, 5);
});

test('calendar date detail shows every scheduled word and switches history without another request', async () => {
    const words = Array.from({ length: 501 }, (_, id) => ({ word: `word-${id}`, due: '2026-10-30T00:00:00Z' }));
    let calls = 0;
    const app = harness(async (url, { params }) => {
        calls++;
        assert.equal(url, '/api/stats/calendar-words');
        assert.equal(params.date, '2026-10-30');
        assert.equal(params.limit, undefined);
        return { data: { data: { practiced: [{ word: 'studied' }], due: words } } };
    });
    app.today = '2026-10-30';
    await app.openCalendarWords({ date: '2026-10-30', practiced: 0, due_count: 501 });
    assert.equal(app.detailModal.type, 'calendar');
    assert.equal(app.detailModal.title, '2026-10-30');
    assert.equal(app.detailModal.subtitle, '已学习 1 个词 · 待复习 501 个词');
    assert.equal(app.detailModal.items.length, 501);
    app.selectCalendarMode('practiced');
    assert.equal(app.detailModal.items[0].word, 'studied');
    assert.equal(calls, 1);
});

test('past calendar dates only describe history and future dates only plans', async () => {
    const app = harness(async (url, { params }) => ({ data: { data: params.date < '2026-02-10'
        ? { practiced: [{ word: 'studied' }], due: [] } : { practiced: [], due: [{ word: 'planned' }] } } }));
    app.today = '2026-02-10';
    assert.equal(app.calendarDayDescription({ date: '2026-02-09', practiced: 3, due_count: 0 }), '2026-02-09：已学习 3 个词');
    assert.equal(app.calendarDayDescription({ date: '2026-02-10', practiced: 4, due_count: 2 }), '2026-02-10：已学习 4 个词，待复习 2 个词');
    assert.equal(app.calendarDayDescription({ date: '2026-02-11', practiced: 0, due_count: 4 }), '2026-02-11：待复习 4 个词');
    await app.openCalendarWords({ date: '2026-02-09', practiced: 1, due_count: 0 });
    assert.equal(app.detailModal.subtitle, '已学习 1 个词');
    await app.openCalendarWords({ date: '2026-02-11', practiced: 0, due_count: 1 });
    assert.equal(app.detailModal.subtitle, '待复习 1 个词');
    assert.equal(app.detailModal.items[0].word, 'planned');
});

test('empty calendar dates do not open a dialog or request words', async () => {
    let calls = 0;
    const app = harness(async () => { calls++; });
    await app.openCalendarWords({ date: '2026-10-30', practiced: 0, due_count: 0 });
    assert.equal(app.detailModal.visible, false);
    assert.equal(calls, 0);
});

test('calendar detail distinguishes empty results from failures, and reopening retries', async () => {
    let fail = true;
    const app = harness(async () => {
        if (fail) throw new Error('broken');
        return { data: { data: { practiced: [], due: [] } } };
    });
    const day = { date: '2026-10-30', practiced: 0, due_count: 1 };
    await app.openCalendarWords(day);
    assert.match(app.detailModal.error, /无法加载/);
    assert.equal(app.detailModal.loading, false);
    fail = false;
    await app.openCalendarWords(day);
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

test('top metrics count unique learned and mastered words and show short practice as under a minute', () => {
    const app = harness(async () => {});
    app.overview = { current_streak: 3, total_time_minutes: 125, total_words_practiced: 900 };
    assert.equal(app.overviewCards[1].value, '—', 'no false zero before the vocabulary loads');
    app.vocabulary = { overall: { learned: 42, mastered: 12 } };
    assert.equal(app.overviewCards.map(card => card.label).join(','), '连续学习,已学习,已掌握,累计时长');
    assert.equal(app.overviewCards.map(card => card.value).join(','), '3,42,12,2.1');
    app.overview = { total_time_minutes: 0.4 };
    assert.deepEqual([app.overviewCards[3].value, app.overviewCards[3].unit], ['<1', '分钟']);
    app.overview = { total_time_minutes: 0 };
    assert.equal(app.overviewCards[3].value, 0);
});

test('record times read as yesterday, today, tomorrow or a date without seconds', () => {
    const app = harness(async () => {});
    const now = Date.parse('2026-11-15T02:00:00Z'); // 10:00 in Beijing
    assert.equal(app.formatDateTime('2026-11-14T13:05:09Z', now), '昨天 21:05');
    assert.equal(app.formatDateTime('2026-11-15T13:34:51Z', now), '今天 21:34');
    assert.equal(app.formatDateTime('2026-11-16T01:00:00Z', now), '明天 09:00');
    assert.equal(app.formatDateTime('2026-11-20T01:00:00Z', now), '11月20日 09:00');
    assert.equal(app.formatDateTime('2025-11-20T01:00:00Z', now), '2025年11月20日 09:00');
});

test('calendar and recent activity use separate color scales', async () => {
    const app = harness(async url => statsGet(url));
    assert.equal(app.trendRangeLabel, '最近 30 天');
    app.renderTrend = app.centerCalendar = () => {};
    await app.loadAllData();
    assert.equal(app.calendarDayClass(app.calendar.days[0])[0], 'calendar-history-4');
    assert.equal(app.calendarDayClass(app.calendar.days[1])[0], 'calendar-due-4');
    assert.equal(app.trendData.length, 30);
    assert.equal(app.trendRangeLabel, '最近 30 天 · 2026.01.12 — 2026.02.10');
    assert.equal(app.monthLabel, '2026 年 2 月');
});

test('recent activity chart distinguishes months on the axis and keeps zero days without accuracy', () => {
    let option;
    const container = {};
    const app = harness(async () => {}, {
        document: { getElementById() { return container; } }, echarts: {}
    });
    app.trendChart = { getDom: () => container, setOption(value) { option = value; } };
    app.trendData = [
        { date: '2025-12-31', words: 2, accuracy: 50 },
        { date: '2026-01-01', words: 0, accuracy: null }
    ];
    app.renderTrend();
    assert.equal(option.xAxis.data.join(','), '12/31,1/1');
    assert.equal(option.series[0].data.join(','), '2,0');
    assert.equal(option.series[1].data[1], null);
    assert.match(option.tooltip.formatter([{ dataIndex: 0 }]), /2025-12-31.*正确率: 50.0%/);
    assert.match(option.tooltip.formatter([{ dataIndex: 1 }]), /2026-01-01.*未练习/);
});

test('optimization history loads the status and every run at once', async () => {
    const requests = [];
    const app = harness(async (url, options) => {
        requests.push([url, options]);
        if (url.endsWith('/runs')) return { data: { data: { items: [{ id: 4 }, { id: 3 }] } } };
        return { data: { data: { enabled: true, effective_reviews: 1400, minimum_reviews: 1000 } } };
    });
    await app.onOptimizationToggle({ target: { open: true } });
    assert.equal(app.optimization.status.effective_reviews, 1400);
    assert.equal(app.optimization.items.map(item => item.id).join(','), '4,3');
    assert.equal(app.optimization.loading, false);
    assert.deepEqual(requests.map(([url, options]) => [url, options]), [['/api/memory/optimization', undefined], ['/api/memory/optimization/runs', undefined]]);
    await app.onOptimizationToggle({ target: { open: true } });
    assert.equal(requests.length, 2, 'reopening keeps loaded records');
});

test('a failed optimization load shows an error and opening the section again retries', async () => {
    let fail = true;
    const app = harness(async url => {
        if (fail) throw new Error('broken');
        return { data: { data: url.endsWith('/runs') ? { items: [{ id: 4 }] } : { enabled: true } } };
    });
    await app.onOptimizationToggle({ target: { open: true } });
    assert.match(app.optimization.error, /无法加载/);
    assert.equal(app.optimization.loading, false);
    fail = false;
    await app.onOptimizationToggle({ target: { open: true } });
    assert.equal(app.optimization.error, '');
    assert.equal(app.optimization.items.length, 1);
});

test('vocabulary detail loads later pages and a failed page can be requested again', async () => {
    let fail = false;
    const offsets = [];
    const app = harness(async (url, { params }) => {
        assert.equal(url, '/api/stats/vocabulary-words');
        assert.equal(params.dimension, 'topic');
        assert.equal(params.value, '教育');
        assert.equal(params.status, 'all');
        offsets.push(params.offset);
        if (fail) throw new Error('broken');
        return { data: { data: { items: [{ word: params.offset ? 'second' : 'first' }], total: 2,
            next_offset: params.offset ? null : 1 } } };
    });
    await app.openVocabularyWords('topic', { value: '教育', label: '教育', learned: 1, learning: 1, total: 2, mastered: 0 });
    fail = true;
    await app.loadVocabularyWords(true);
    assert.equal(app.detailModal.items[0].word, 'first');
    assert.equal(app.detailModal.nextOffset, 1);
    assert.match(app.detailModal.error, /无法加载/);
    fail = false;
    await app.loadVocabularyWords(true);
    assert.equal(app.detailModal.items.map(item => item.word).join(','), 'first,second');
    assert.equal(app.detailModal.nextOffset, null);
    assert.equal(app.detailModal.error, '');
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

test('empty CEFR levels do not open a dialog or request words', async () => {
    let calls = 0;
    const app = harness(async () => { calls++; });
    await app.openVocabularyWords('cefr', { total: 0 });
    assert.equal(calls, 0);
    assert.equal(app.detailModal.visible, false);
});

test('word errors load every record once by source identity and keep the containing list', async () => {
    const requests = [];
    const app = harness(async (url, { params }) => {
        assert.equal(url, '/api/stats/word-errors');
        requests.push(params);
        return { data: { data: { items: [{ id: 8, user_input: 'wrong' }, { id: 3, user_input: 'wrnog' }],
            correct_attempts: 4, total_attempts: 6 } } };
    });
    const item = { id: 999, source_id: 'stable-source', word: 'same-spelling', total_attempts: 5 };
    app.detailModal.items = [item];
    await app.toggleWordErrors(item);
    assert.equal(item.errorHistory.expanded, true);
    assert.equal(item.errorHistory.items.map(row => row.id).join(','), '8,3');
    assert.equal(item.correct_attempts, 4);
    assert.equal(item.total_attempts, 6);
    await app.toggleWordErrors(item);
    await app.toggleWordErrors(item);
    assert.deepEqual(requests.map(params => ({ ...params })), [{ source_id: 'stable-source' }]);
    assert.equal(app.detailModal.items[0], item);
});

test('word errors keep zero-history and failures apart, and expanding again retries', async () => {
    let fail = true;
    const app = harness(async () => {
        if (fail) throw new Error('broken');
        return { data: { data: { items: [], correct_attempts: 0, total_attempts: 0 } } };
    });
    const first = { source_id: 'first', total_attempts: 1 }, second = { source_id: 'second', total_attempts: 1 };
    await app.toggleWordErrors(first);
    assert.match(first.errorHistory.error, /无法加载/);
    assert.equal(first.errorHistory.loaded, false);
    fail = false;
    await app.toggleWordErrors(second);
    assert.equal(second.errorHistory.loaded, true);
    assert.equal(second.errorHistory.items.length, 0);
    assert.equal(second.errorHistory.error, '');
    assert.equal(first.errorHistory.loaded, false);
    await app.toggleWordErrors(first);
    await app.toggleWordErrors(first);
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
