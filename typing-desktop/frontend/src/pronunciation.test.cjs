const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness() {
    const sounds = [], timers = [];
    const context = vm.createContext({
        Audio: class {
            constructor(url) { this.url = url; sounds.push(this); }
            play() { this.played = true; return Promise.resolve(); }
            pause() { this.paused = true; }
        },
        window: {
            setTimeout(fn, delay) { timers.push({ fn, delay, cancelled: false }); return timers.length; },
            clearTimeout(id) { if (timers[id - 1]) timers[id - 1].cancelled = true; }
        }
    });
    vm.runInContext(fs.readFileSync(__dirname + '/pronunciation.js', 'utf8'), context);
    const app = { audioError: '', ...vm.runInContext('wordAudio', context) };
    const runGap = () => timers.filter(t => !t.cancelled).splice(0).forEach(t => { t.cancelled = true; t.fn(); });
    return { app, sounds, timers, runGap };
}

test('a click plays UK, waits half a second after it ends, then plays US', () => {
    const h = harness();
    h.app.playWord({ audio_urls: { us: '/us.mp3', uk: '/uk.mp3', example: '/example.mp3' } });
    assert.deepEqual(h.sounds.map(a => a.url), ['/uk.mp3']);
    h.sounds[0].onended();
    assert.equal(h.timers[0].delay, 500);
    assert.equal(h.sounds.length, 1);
    h.runGap();
    assert.deepEqual(h.sounds.map(a => a.url), ['/uk.mp3', '/us.mp3']);
    h.sounds[1].onended();
    assert.equal(h.timers.filter(t => !t.cancelled).length, 0);
});

test('clicking another word stops the previous sound and cancels its remaining accent', () => {
    const h = harness();
    h.app.playWord({ audio_urls: { uk: '/first-uk', us: '/first-us' } });
    h.app.playWord({ audio_urls: { uk: '/second-uk', us: '/second-us' } });
    assert.equal(h.sounds[0].paused, true);
    assert.equal(h.sounds[0].onended, null);
    // A completed first accent leaves a gap; a new click cancels that gap too.
    h.sounds[1].onended();
    h.app.playWord({ audio_urls: { uk: '/third-uk' } });
    h.runGap();
    assert.deepEqual(h.sounds.map(a => a.url), ['/first-uk', '/second-uk', '/third-uk']);
    h.app.stopWordAudio();
    assert.equal(h.sounds.at(-1).paused, true);
});

test('missing accents are skipped and unavailable audio is not clickable', () => {
    const h = harness();
    assert.equal(h.app.hasWordAudio({}), false);
    assert.equal(h.app.hasWordAudio({ audio_urls: { example: '/example' } }), false);
    assert.equal(h.app.hasWordAudio({ audio_urls: { us: '/us' } }), true);
    h.app.playWord({ audio_urls: { us: '/us' } });
    assert.deepEqual(h.sounds.map(a => a.url), ['/us']);
    h.sounds[0].onended();
    assert.equal(h.timers.length, 0);
});

test('a playback error reports a retry and does not start the next accent', () => {
    const h = harness();
    h.app.playWord({ audio_urls: { uk: '/bad', us: '/us' } });
    h.sounds[0].onerror();
    h.runGap();
    assert.match(h.app.audioError, /播放失败.*重试/);
    assert.equal(h.sounds.length, 1);
    h.app.playWord({ audio_urls: { uk: '/retry' } });
    assert.equal(h.app.audioError, '');
});
