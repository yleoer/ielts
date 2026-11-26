"""Practice and statistics flows checked through W3C WebDriver (tauri-driver).

The app starts with five new words (apple bridge garden river window, served in that order).
Checks cover what only the real window shows: template bindings, focus and scrolling, keyboard
handling, WebKitGTK behaviour such as caching, native window events and the real core.
"""
from __future__ import annotations

import base64
import http.client
import json
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'
ENTER, ESCAPE, SPACE, CONTROL = '', '', ' ', ''
FIRST_ROUND = ['apple', 'bridge', 'garden', 'river', 'window']

PRACTICE_STATE = """const a = document.querySelector('#app')._vnode.component.proxy;
const main = document.querySelector('#main-content'), f = document.activeElement;
return { page: location.pathname, finished: a.isFinished, idle: a.isIdle, word: a.currentWord && a.currentWord.word,
  showAnswer: a.showAnswer, progress: !!document.querySelector('.session-progress'),
  accuracy: document.querySelector('.progress-accuracy')?.textContent.trim(),
  heading: document.querySelector('main h2')?.textContent.trim(),
  status: (document.querySelector('.result-save-status') || document.querySelector('.empty-state p'))?.textContent.trim(),
  buttons: [...document.querySelectorAll('main .button-row button')].map(b => b.textContent.trim()),
  mistakes: document.querySelectorAll('.mistakes-section li').length,
  focused: f === document.body ? 'BODY' : f.classList.contains('results-sheet') ? 'RESULTS' : f.textContent.trim() || f.tagName,
  scrollTop: Math.round(main.scrollTop), overflow: main.scrollHeight - main.clientHeight,
  title: document.querySelector('.titlebar-note')?.textContent.trim() };"""

# Counts answer-box rebuilds and loading flashes while practising; the results page ends the count.
WATCH_ANSWER_BOX = """window.__answerBox = { input: document.querySelector('#answer-input'), rebuilt: 0 };
new MutationObserver(() => {
  const box = window.__answerBox, input = document.querySelector('#answer-input');
  if (document.querySelector('#app')._vnode.component.proxy.isFinished) return;
  if (input !== box.input || document.querySelector('.empty-state[role=status]')) box.rebuilt++;
  box.input = input;
}).observe(document.querySelector('main'), { childList: true, subtree: true });"""
ANSWER_TOP = "return Math.round(document.querySelector('#answer-input').getBoundingClientRect().top)"

STATS_STATE = """const a = document.querySelector('#app')._vnode.component.proxy;
const dialog = document.querySelector('.detail-dialog');
return { page: location.pathname, loading: a.loading, loadError: a.loadError,
  cards: Object.fromEntries([...document.querySelectorAll('.metrics-strip > div')].map(d =>
    [d.querySelector('dt').textContent, d.querySelector('dd').textContent.trim()])),
  today: document.querySelector('.calendar-day.calendar-today')?.className || '',
  chart: !!document.querySelector('#trend-chart canvas'),
  overall: document.querySelector('.progress-summary strong')?.textContent.trim(),
  optimization: document.querySelector('.optimization-content')?.textContent.replace(/\\s+/g, ' ').trim(),
  dialog: dialog && { title: dialog.querySelector('#detail-title').textContent.trim(),
    entries: dialog.querySelectorAll('.entry-list > li').length,
    errors: [...dialog.querySelectorAll('.word-error-records .error-input')].map(p => p.textContent.replace(/[（(].*$/, '').trim()) } };"""


class Session:
    def __init__(self, base: str, app: str, shots: Path):
        self.base, self.shots, self.results = base, shots, []
        self.path = '/session/' + self.call('POST', '/session', {'capabilities': {'alwaysMatch': {'tauri:options': {'application': app}}}})['sessionId']

    def call(self, method, path, body=None, retry=True):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)['value']
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{method} {path}: {error.read().decode()}') from None
        except (http.client.RemoteDisconnected, ConnectionResetError):
            # tauri-driver occasionally forwards on a pooled connection WebKitWebDriver already
            # closed; the command never arrives, so sending it once more is safe.
            if not retry:
                raise
            time.sleep(0.5)
            return self.call(method, path, body, retry=False)

    def js(self, script, *args):
        return self.call('POST', self.path + '/execute/sync', {'script': script, 'args': list(args)})

    def find(self, css):
        return self.call('POST', self.path + '/element', {'using': 'css selector', 'value': css})[ELEMENT]

    def type_into(self, css, text):
        self.call('POST', f'{self.path}/element/{self.find(css)}/value', {'text': text})

    def keys(self, *keys):
        actions = [{'type': 'keyDown', 'value': key} for key in keys] + [{'type': 'keyUp', 'value': key} for key in reversed(keys)]
        self.call('POST', self.path + '/actions', {'actions': [{'type': 'key', 'id': 'keyboard', 'actions': actions}]})
        self.call('DELETE', self.path + '/actions')

    def click(self, css):
        self.call('POST', f'{self.path}/element/{self.find(css)}/click', {})

    def click_button(self, label):
        self.js("[...document.querySelectorAll('main button')].find(b => b.textContent.trim() === arguments[0]).click()", label)

    def shot(self, name):
        (self.shots / f'{name}.png').write_bytes(base64.b64decode(self.call('GET', self.path + '/screenshot')))

    def wait(self, script, predicate, timeout=10, what=''):
        end = time.time() + timeout
        while True:
            try:
                current = self.js(script)
            except RuntimeError:  # the page is navigating
                current = None
            if current is not None and predicate(current):
                return current
            if time.time() > end:
                raise RuntimeError(f'timed out waiting for {what}: {current}')
            time.sleep(0.25)

    def practice(self, predicate, timeout=10, what=''):
        return self.wait(PRACTICE_STATE, lambda s: s['page'] != '/stats.html' and predicate(s), timeout, what)

    def stats(self, predicate, timeout=10, what=''):
        return self.wait(STATS_STATE, lambda s: s['page'] == '/stats.html' and not s['loading'] and predicate(s), timeout, what)

    def ready(self):
        """The app syncs at startup; once the mock data is merged, reload so the page reads it."""
        self.wait("return axios.get('/api/sync/status').then(response => response.data.data.last_sync_at)", bool, 30, 'first sync')
        self.js('setTimeout(() => location.reload(), 0)')
        time.sleep(0.5)

    def check(self, name, condition, detail=''):
        self.results.append(bool(condition))
        print(('PASS ' if condition else 'FAIL ') + name + ('' if condition else f'  -> {detail}'), flush=True)

    def answer(self, word, wrong=False):
        self.practice(lambda s: s['word'] == word and not s['showAnswer'], 15, f'word {word}')
        if wrong:
            self.type_into('#answer-input', word[:-1] + ENTER)
            self.practice(lambda s: s['showAnswer'], 5, f'correction for {word}')
        self.type_into('#answer-input', word + ENTER)

    def answer_until_finished(self):
        """Answers whatever the queue serves (due words can join mid-round) until the results show."""
        while True:
            s = self.practice(lambda s: s['finished'] or (s['word'] and not s['showAnswer']), 15, 'next word or results')
            if s['finished']:
                return s
            self.type_into('#answer-input', s['word'] + ENTER)
            self.practice(lambda c: c['finished'] or c['word'] != s['word'] or c['showAnswer'], 5, 'answer accepted')


def until(predicate, timeout):
    end = time.time() + timeout
    while not predicate():
        if time.time() > end:
            return False
        time.sleep(0.25)
    return True


def practice_round(t: Session, mock):
    # A smaller window makes five mistakes overflow the results page.
    t.call('POST', t.path + '/window/rect', {'width': 960, 'height': 640})
    t.ready()
    s = t.practice(lambda s: s['word'] == 'apple', 15, 'apple')
    t.check('round starts with progress and a dash for accuracy', s['progress'] and s['accuracy'] == '正确率 —', s)
    t.js(WATCH_ANSWER_BOX)
    tops = []
    for word in FIRST_ROUND:
        t.practice(lambda s: s['word'] == word and not s['showAnswer'], 15, f'word {word}')
        tops.append(t.js(ANSWER_TOP))
        t.answer(word, wrong=True)

    s = t.practice(lambda s: s['finished'], 10, 'results')
    t.check('results heading, saved count and next review', s['heading'] == '本轮练习完成'
            and s['status'].startswith('5 次作答已保存 · 下次复习 今天') and s['status'].endswith('（1 分钟内）'), s)
    rebuilt = t.js('return window.__answerBox.rebuilt')
    t.check('the answer box stays in place between words with one or two senses', len(set(tops)) == 1 and rebuilt == 0,
            {'tops': tops, 'rebuilt': rebuilt})
    t.check('results list all five mistakes with only mistake practice and Done', s['mistakes'] == 5 and s['buttons'] == ['错词重练', '完成'], s)
    t.check('long results open at the top with the sheet focused', s['overflow'] > 0 and s['scrollTop'] == 0 and s['focused'] == 'RESULTS', s)
    # Saved answers go up right away, not with the next once-a-minute sync.
    t.check('answers reach the server right after saving', until(lambda: len(mock.log) >= 5, 5), len(mock.log))
    t.shot('practice-results')
    t.keys(SPACE)
    s = t.practice(lambda s: s['scrollTop'] > 0 or not s['finished'], 3, 'space scrolls')
    t.check('Space scrolls the review instead of pressing Done', s['finished'] and s['scrollTop'] > 0, s)

    # Words due one minute after a wrong answer turn Done into Start review on the same page.
    s = t.practice(lambda s: '开始复习' in s['buttons'], 80, 'due on results')
    t.check('due time turns Done into Start review', s['buttons'] == ['错词重练', '开始复习'] and s['status'].startswith('5 次作答已保存 · 待复习'), s)
    t.keys(ENTER)
    t.practice(lambda s: s['word'], 10, 'first due word')
    t.type_into('#answer-input', ESCAPE)
    s = t.practice(lambda s: s['idle'], 5, 'idle after zero-answer quit')
    t.check('quitting without answers skips the results page', not s['finished'] and s['heading'] == '复习时间到了', s)
    t.check('waiting page focuses Start review', s['buttons'][0] == '开始复习' and s['focused'] == '开始复习', s)

    t.click_button('开始复习')
    s = t.answer_until_finished()
    t.check('clean round shows only Done and the next review', s['buttons'] == ['完成'] and '下次复习' in s['status'], s)
    t.keys(ENTER)
    s = t.practice(lambda s: s['idle'], 5, 'waiting page')
    t.check('waiting page: no progress, next review, extra modes only', not s['progress'] and s['heading'] == '暂无待复习'
            and s['status'].startswith('下次复习') and s['buttons'] == ['自由练习', '难点突破', '久未练习'], s)


def open_stats(t: Session, learned: int):
    t.keys(CONTROL, '2')
    return t.stats(lambda s: s['chart'] and s['cards'].get('已学习') == f'{learned}词', 15, f'statistics with {learned} learned')


def stats_page(t: Session):
    s = open_stats(t, 5)
    t.check('statistics count the learned words and practice time', s['cards']['累计时长'].endswith('分钟') and not s['loadError'], s)
    t.check('today is marked as studied in the calendar', 'calendar-history-' in s['today'], s)
    t.check('recent activity chart renders and vocabulary totals add up', s['chart'] and s['overall'] == '5 / 0 / 5', s)
    t.shot('stats-overview')

    t.click('.calendar-day.calendar-today')
    s = t.stats(lambda s: s['dialog'] and s['dialog']['entries'], 5, 'calendar day words')
    t.check('today opens the words studied today', s['dialog']['entries'] == 5, s)
    t.keys(ESCAPE)
    t.stats(lambda s: not s['dialog'], 5, 'dialog closed')

    t.click('.route-stop:not([disabled])')
    t.stats(lambda s: s['dialog'] and s['dialog']['entries'] == 5, 5, 'level words')
    t.js("[...document.querySelectorAll('.detail-dialog .entry-list > li')].find(li => li.textContent.includes('apple')).querySelector('.word-attempts').click()")
    s = t.stats(lambda s: s['dialog']['errors'], 5, 'word errors')
    # The box marks the missing letter in the typed answer.
    t.check('a level lists its words and expands one word\'s wrong answers', s['dialog']['errors'] == ['appl□'], s)
    t.shot('stats-word-errors')
    t.keys(ESCAPE)
    t.stats(lambda s: not s['dialog'], 5, 'dialog closed')

    t.js("document.querySelector('.optimization-history').open = true")
    s = t.stats(lambda s: '自动优化已关闭' in (s['optimization'] or ''), 5, 'optimization history')
    t.check('optimization history loads in place', '暂无优化记录' in s['optimization'], s)
    t.keys(CONTROL, '1')
    s = t.practice(lambda s: s['idle'], 15, 'practice waiting page')
    t.check('Ctrl+1 returns to the waiting page', s['heading'] == '暂无待复习', s)


def extra_modes_and_sync(t: Session, mock):
    t.click_button('难点突破')
    s = t.answer_until_finished()
    t.check('difficult answers are saved and the results offer Done', s['heading'] == '难点突破完成'
            and s['status'].startswith('5 次作答已保存') and s['buttons'] == ['完成'], s)
    t.click_button('完成')
    t.practice(lambda s: s['idle'], 5, 'idle after difficult')
    t.click_button('久未练习')
    s = t.practice(lambda s: s['word'], 10, 'stale word')
    t.check('stale practice labels the title bar', s['title'].startswith('久未练习'), s)
    t.type_into('#answer-input', ESCAPE)
    s = t.practice(lambda s: s['idle'], 5, 'idle after stale quit')
    t.check('stale quit returns to the formal waiting page', s['heading'] == '暂无待复习' and s['title'].startswith('待复习'), s)

    mock.add_word('candle', [('n.', '蜡烛')])
    s = t.practice(lambda s: s['heading'] == '有新词可学', 150, 'new word from background sync')
    t.check('background sync new word shows Start learning', s['buttons'][0] == '开始学习' and s['status'] == '新词 1 个', s)
    t.call('POST', t.path + '/window/rect', {'width': 760, 'height': 560})
    t.shot('practice-narrow-new-word')
    t.keys(ENTER)
    t.practice(lambda s: s['word'] == 'candle', 10, 'candle')
    # The other computer learns candle meanwhile; the next sync replaces the stale question.
    mock.answer_elsewhere('candle')
    s = t.practice(lambda s: s['word'] != 'candle', 90, 'candle answered elsewhere')
    t.check('an answer merged from another device replaces the word on screen', s['idle'] and s['heading'] == '暂无待复习', s)
    # Opening statistics again must show fresh numbers, not WebKit's cached responses.
    s = open_stats(t, 6)
    t.check('statistics refresh after merged answers', s['overall'] == '6 / 0 / 6', s)
    t.keys(CONTROL, '1')
    t.practice(lambda s: s['idle'], 15, 'practice waiting page')


def close_to_tray(t: Session):
    t.click_button('自由练习')
    s = t.practice(lambda s: s['word'] and not s['showAnswer'], 10, 'free word')
    t.type_into('#answer-input', s['word'] + ENTER)
    t.practice(lambda c: c['word'] != s['word'], 5, 'next free word')
    t.type_into('#answer-input', ESCAPE)
    s = t.practice(lambda s: s['finished'], 5, 'results after quitting free practice')
    t.check('quitting after an answer shows the results', s['heading'] == '已退出练习', s)
    # Closing hides to the tray (the default) via the native event; the window cannot return in Xvfb.
    t.click('[data-window-action=close]')
    s = t.practice(lambda s: s['idle'], 5, 'waiting page after closing to the tray')
    t.check('closing to the tray leaves the results for the waiting page', not s['finished'], s)


def run(base: str, app: str, mock, shots: Path) -> int:
    t = Session(base, app, shots)
    try:
        for flow in (lambda t: practice_round(t, mock), stats_page, lambda t: extra_modes_and_sync(t, mock), close_to_tray):
            flow(t)
    except Exception as error:  # noqa: BLE001 - report, keep the screenshot, still clean up
        print(f'ERROR {error}')
        print(''.join(traceback.format_exc().splitlines(keepends=True)[-6:]))
        t.results.append(False)
        try:
            t.shot('failure')
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            t.call('DELETE', t.path)
        except Exception:  # noqa: BLE001
            pass
    print(f'{sum(t.results)}/{len(t.results)} checks passed')
    return 0 if t.results and all(t.results) else 1
