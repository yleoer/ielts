"""Regenerate the README screenshots from demo data (Linux, same environment as run.py).

    python3 desktop/e2e/screenshots.py

Words come from e2e/demo-vocabulary.txt (from hefengxian/my-ielts). The mock server also serves about three
weeks of answers, as if the other computer had synced them, so the calendar, the chart and
the level rings have data. Output: docs/desktop/screenshots/*.png.
"""
from __future__ import annotations

import datetime as dt
import random
import sys
import time
import uuid

import flows
import run

ROOT = run.DESKTOP.parent
OUT = ROOT / 'docs/desktop/screenshots'
LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']


def demo_words(topics=5, per_topic=10) -> list[dict]:
    words, counts, topic = [], {}, None
    for line in (ROOT / 'desktop/e2e/demo-vocabulary.txt').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line in ('+++', '---'):  # topic marker and word-group separator
            continue
        if '|' not in line:
            topic = line
            continue
        if topic not in counts and len(counts) == topics:
            break
        text, pos, meaning = line.split('|')[:3]
        if counts.get(topic, 0) == per_topic or not text.isalpha():
            continue
        senses = [(pos, part.strip()) for part in meaning.split('；') if part.strip()][:3]
        level = LEVELS[min(5, max(0, (len(text) - 3) // 2))]
        words.append(run.word(len(words), text, senses, cefr=level, category=topic))
        counts[topic] = counts.get(topic, 0) + 1
    return words


def demo_log(words: list[dict], now: dt.datetime, new_words=6) -> list[dict]:
    """Spaced answers ending before now: roughly doubling gaps, about one in six wrong."""
    rng = random.Random(7)
    log = []
    for item in words[:-new_words]:
        day = (now - dt.timedelta(days=rng.randint(8, 24))).date()
        gap = 1
        while True:
            # 08:00–22:59 in Beijing.
            at = dt.datetime.combine(day, dt.time(rng.randint(0, 14), rng.randint(0, 59), rng.randint(0, 59)), dt.timezone.utc)
            if at > now - dt.timedelta(hours=2):
                break
            text = item['word']
            wrong = rng.random() < 0.18
            rating = 1 if wrong else 4 if rng.random() < 0.3 else 3
            cut = rng.randrange(1, len(text))
            log.append({
                'attempt_id': str(uuid.UUID(int=rng.getrandbits(128))), 'word_key': f"word-atlas:{item['source_id']}",
                'word': text, 'chinese_meaning': item['chinese_meaning'], 'category': item['category'],
                'user_input': text[:cut] + text[cut + 1:] if wrong else text, 'is_correct': not wrong, 'rating': rating,
                'reviewed_at': at.strftime('%Y-%m-%dT%H:%M:%S.000000Z'),
                'duration_ms': {1: 14000, 3: 9000, 4: 4000}[rating], 'first_input_ms': 1500,
            })
            gap = 1 if wrong else gap * 2 + rng.randint(0, 1)
            day += dt.timedelta(days=gap)
    return sorted(log, key=lambda row: row['reviewed_at'])


def capture(t: flows.Session):
    t.call('POST', t.path + '/window/rect', {'width': 1100, 'height': 720})
    t.ready()
    first = t.practice(lambda s: s['word'] and not s['showAnswer'], 20, 'first word')['word']
    t.type_into('#answer-input', first[:3])
    # The first capture of a fresh WebKit profile can come back black before compositing settles.
    t.call('GET', t.path + '/screenshot')
    time.sleep(1)
    t.shot('practice')
    t.type_into('#answer-input', 'q' + flows.ENTER)
    t.practice(lambda s: s['showAnswer'], 5, 'correction')
    time.sleep(0.4)
    t.shot('correction')
    t.type_into('#answer-input', first + flows.ENTER)

    # Answer the rest of today's round, getting one more word wrong.
    answered = 1
    while True:
        s = t.practice(lambda s: s['finished'] or (s['word'] and s['word'] != first and not s['showAnswer']), 15, 'next word')
        if s['finished']:
            break
        first = s['word']
        answered += 1
        if answered == 3:
            t.answer(first, wrong=True)
        else:
            t.type_into('#answer-input', first + flows.ENTER)
    time.sleep(0.6)
    t.shot('results')
    t.keys(flows.ENTER)
    t.practice(lambda s: s['idle'] and s['heading'] == '暂无待复习', 5, 'waiting page')
    time.sleep(0.4)
    t.shot('waiting')

    t.keys(flows.CONTROL, '2')
    t.stats(lambda s: s['chart'], 15, 'statistics')
    time.sleep(0.8)
    t.shot('stats')
    t.js("document.querySelector('#route-title').scrollIntoView({ block: 'start' })")
    time.sleep(0.4)
    t.shot('stats-progress')
    t.js("""const stops = [...document.querySelectorAll('.route-stop:not([disabled])')];
        stops.sort((a, b) => b.querySelector('.route-count').textContent.split('/').pop() - a.querySelector('.route-count').textContent.split('/').pop());
        stops[0].click();""")
    t.stats(lambda s: s['dialog'] and s['dialog']['entries'], 5, 'level words')
    t.js("""const button = [...document.querySelectorAll('.detail-dialog .word-attempts')]
        .find(b => { const [right, total] = b.textContent.match(/\\d+/g); return right !== total; });
        button.click();""")
    t.stats(lambda s: s['dialog']['errors'], 5, 'word errors')
    time.sleep(0.4)
    t.shot('stats-detail')


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    words = demo_words()
    mock = run.MockServer(words, demo_log(words, dt.datetime.now(dt.timezone.utc)))
    with run.environment(mock) as (base, app):
        t = flows.Session(base, app, OUT)
        try:
            capture(t)
        finally:
            t.call('DELETE', t.path)
    print('wrote', ', '.join(sorted(path.name for path in OUT.glob('*.png'))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
