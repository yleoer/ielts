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
    return app;
}

test('forecast detail requests the selected date and displays all returned words', async () => {
    const words = Array.from({ length: 501 }, (_, id) => ({ word: `word-${id}`, due: '2026-10-30T00:00:00Z' }));
    const app = harness(async (url, { params }) => {
        assert.equal(url, 'http://test/api/memory/forecast-words');
        assert.equal(params.date, '2026-10-30');
        assert.equal(params.limit, undefined);
        return { data: { data: words } };
    });
    await app.openForecastWords({ date: '2026-10-30', label: '明天', count: 501 });
    assert.equal(app.detailModal.visible, true);
    assert.equal(app.detailModal.type, 'forecast');
    assert.equal(app.detailModal.title, '明天待复习');
    assert.equal(app.detailModal.subtitle, '2026-10-30 · 501 个单词');
    assert.equal(app.detailModal.items.length, 501);
    assert.equal(app.detailModal.loading, false);
    assert.equal(app.detailModal.error, '');
});

test('zero-count forecast days do not open a modal or request words', async () => {
    let requests = 0;
    const app = harness(async () => { requests++; return { data: { data: [] } }; });
    await app.openForecastWords({ date: '2026-10-30', label: '明天', count: 0 });
    assert.equal(requests, 0);
    assert.equal(app.detailModal.visible, false);
});

test('empty and failed forecast requests keep distinct modal states', async () => {
    const day = { date: '2026-10-30', label: '明天', count: 1 };
    const empty = harness(async () => ({ data: { data: [] } }));
    await empty.openForecastWords(day);
    assert.equal(empty.detailModal.visible, true);
    assert.equal(empty.detailModal.items.length, 0);
    assert.equal(empty.detailModal.error, '');
    assert.equal(empty.detailModal.loading, false);

    const failed = harness(async () => { throw new Error('offline'); });
    await failed.openForecastWords(day);
    assert.equal(failed.detailModal.error, '加载单词失败');
    assert.equal(failed.detailModal.loading, false);
});

test('an older detail response cannot overwrite a newer selected day', async () => {
    const pending = [];
    const app = harness(() => new Promise(resolve => pending.push(resolve)));
    const first = app.openForecastWords({ date: '2026-10-29', label: '今天', count: 1 });
    const second = app.openForecastWords({ date: '2026-10-30', label: '明天', count: 1 });
    pending[1]({ data: { data: [{ word: 'tomorrow' }] } });
    await second;
    pending[0]({ data: { data: [{ word: 'today' }] } });
    await first;
    assert.equal(app.detailModal.title, '明天待复习');
    assert.equal(app.detailModal.items[0].word, 'tomorrow');
    app.closeDetailModal();
    assert.equal(app.detailModal.visible, false);
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
