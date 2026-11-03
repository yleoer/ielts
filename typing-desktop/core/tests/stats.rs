//! Ports of `test_activity.py` / `test_vocabulary.py` for the stats routes.

mod common;

use chrono::{TimeDelta, NaiveDate};
use cijian_core::fsrs::State;
use common::{at, word, Env};
use serde_json::{json, Value};

fn sources(items: &Value) -> Vec<String> {
    items.as_array().unwrap().iter().map(|w| w["source_id"].as_str().unwrap().to_string()).collect()
}

fn counts(items: &Value) -> Vec<(i64, i64)> {
    items.as_array().unwrap().iter().map(|w| (w["correct_attempts"].as_i64().unwrap(), w["total_attempts"].as_i64().unwrap())).collect()
}

fn calendar_env() -> Env {
    let words = ["abandon", "word-ab", "word-ac", "word-ad"].iter().enumerate()
        .map(|(i, s)| word(s, i as i64 + 101, true)).collect();
    Env::new(at(2026, 10, 29, 8, 0, 0), words)
}

#[test]
fn calendar_window_covers_six_previous_and_five_next_months() {
    let env = calendar_env();
    env.set(at(2024, 2, 29, 8, 0, 0));
    let data = env.data("/api/stats/calendar");
    let days = data["days"].as_array().unwrap();
    assert_eq!(days.len(), 366);
    assert_eq!((days[0]["date"].as_str(), days[365]["date"].as_str()), (Some("2023-08-01"), Some("2024-07-31")));
    assert_eq!(data["today"], "2024-02-29");
    assert!(days.iter().all(|d| d["practiced"] == 0 && d["due_count"] == 0 && d["accuracy"].is_null()));
}

#[test]
fn calendar_merges_history_with_due_schedule_without_writes() {
    let env = calendar_env();
    env.set(at(2026, 10, 27, 8, 0, 0));
    env.review("abandon", "abandon");
    env.review("abandon", "wrong");
    env.set(at(2026, 10, 29, 8, 0, 0));
    let now = env.now();
    env.set_card("abandon", now - TimeDelta::days(10), State::Review, 25.0);
    env.set_card("word-ab", at(2027, 3, 31, 15, 59, 0), State::Review, 25.0);
    env.set_card("word-ac", at(2027, 3, 31, 16, 0, 0), State::Review, 25.0);
    let before = env.fingerprint();
    let data = env.data("/api/stats/calendar");
    let day = |d: &str| data["days"].as_array().unwrap().iter().find(|x| x["date"] == d).unwrap().clone();
    assert_eq!((day("2026-10-27")["practiced"].as_i64(), day("2026-10-27")["attempts"].as_i64()), (Some(1), Some(2)));
    assert_eq!(day("2026-10-27")["accuracy"], 50.0);
    assert_eq!(day("2026-10-29")["due_count"], 1, "overdue cards count today");
    assert_eq!(day("2027-03-31")["due_count"], 1, "16:00 UTC is the next Beijing day, outside the window");
    assert_eq!(data["days"].as_array().unwrap().iter().map(|d| d["due_count"].as_i64().unwrap()).sum::<i64>(), 2);

    let history = env.data("/api/stats/calendar-words?date=2026-10-27");
    assert_eq!(history["practiced"].as_array().unwrap().len(), 1);
    assert_eq!(history["practiced"][0]["total_attempts"], 2);
    assert_eq!(history["practiced"][0]["status"], "mastered");
    assert_eq!(history["due"], json!([]));
    for selected in ["2026-10-29", "2027-03-31"] {
        assert_eq!(env.data(&format!("/api/stats/calendar-words?date={selected}"))["due"].as_array().unwrap().len(), 1);
    }
    assert_eq!(env.fingerprint(), before);
}

#[test]
fn calendar_words_share_smoothed_error_order() {
    let env = calendar_env();
    for (source, total, errors) in [("word-ac", 10, 8), ("word-ab", 1, 1), ("abandon", 1, 0)] {
        for i in 0..total {
            env.review(source, if i < errors { "" } else { source });
        }
    }
    // Due time order opposes the desired error order.
    let now = env.now();
    for (i, source) in ["word-ac", "word-ab", "abandon"].iter().enumerate() {
        env.set_card(source, now + TimeDelta::hours(3 - i as i64), State::Review, 5.0);
    }
    let data = env.data("/api/stats/calendar-words?date=2026-10-29");
    for group in ["practiced", "due"] {
        assert_eq!(sources(&data[group]), ["word-ac", "word-ab", "abandon"], "{group}");
        assert_eq!(counts(&data[group]), [(2, 10), (0, 1), (1, 1)]);
    }
}

#[test]
fn beijing_midnight_and_removed_words_keep_history() {
    let env = calendar_env();
    env.set(at(2026, 10, 28, 15, 59, 58));
    for _ in 0..3 {
        env.review("abandon", "abandon");
    }
    let data = env.data("/api/stats/calendar");
    let day = |d: &str| data["days"].as_array().unwrap().iter().find(|x| x["date"] == d).unwrap().clone();
    assert_eq!((day("2026-10-28")["practiced"].as_i64(), day("2026-10-28")["attempts"].as_i64()), (Some(1), Some(1)));
    assert_eq!((day("2026-10-29")["practiced"].as_i64(), day("2026-10-29")["attempts"].as_i64()), (Some(1), Some(2)));
    env.import(vec![word("word-ab", 102, true)]);
    let data = env.data("/api/stats/calendar-words?date=2026-10-29");
    assert_eq!(data["practiced"][0]["source_id"], "abandon");
    assert_eq!(data["practiced"][0]["id"], "history-1");
    assert_eq!(data["practiced"][0]["total_attempts"], 3);
    assert_eq!(data["due"], json!([]));
}

#[test]
fn recent_activity_covers_today_and_29_previous_beijing_days() {
    let env = calendar_env();
    env.set(at(2026, 10, 2, 15, 59, 58));
    env.review("abandon", "abandon");
    env.review("abandon", "abandon");
    env.review("abandon", "wrong");
    env.set(at(2026, 10, 31, 16, 0, 0));
    env.review("abandon", "abandon");
    env.set(at(2026, 11, 1, 16, 0, 0));
    env.review("abandon", "abandon");
    env.set(at(2026, 10, 31, 16, 0, 0));
    let before = env.fingerprint();
    let data = env.data("/api/stats/recent-activity");
    assert_eq!((data["start_date"].as_str(), data["end_date"].as_str()), (Some("2026-10-03"), Some("2026-11-01")));
    let days = data["days"].as_array().unwrap();
    assert_eq!(days.len(), 30);
    assert_eq!(days[0], json!({"date": "2026-10-03", "words": 2, "accuracy": 50.0}));
    assert_eq!(days[29], json!({"date": "2026-11-01", "words": 1, "accuracy": 100.0}));
    assert!(days[1..29].iter().all(|d| d["words"] == 0 && d["accuracy"].is_null()));
    assert_eq!(env.fingerprint(), before);

    for (today, start) in [((2024, 3, 1), "2024-02-01"), ((2026, 1, 1), "2025-12-03")] {
        env.set(at(today.0, today.1, today.2, 8, 0, 0));
        let data = env.data("/api/stats/recent-activity");
        assert_eq!(data["start_date"], start);
        let end = NaiveDate::from_ymd_opt(today.0, today.1, today.2).unwrap();
        let expected: Vec<String> = (0..30).rev().map(|o| (end - TimeDelta::days(o)).to_string()).collect();
        let actual: Vec<&str> = data["days"].as_array().unwrap().iter().map(|d| d["date"].as_str().unwrap()).collect();
        assert_eq!(actual, expected);
    }
}

#[test]
fn streak_and_overview_use_beijing_days() {
    let env = calendar_env();
    let overview = env.data("/api/stats/overview");
    assert_eq!(overview, json!({"total_words_practiced": 0, "total_time_minutes": 0, "current_streak": 0}));
    env.set(at(2026, 10, 28, 15, 59, 58));
    env.review("abandon", "abandon");
    assert_eq!(env.data("/api/stats/overview")["current_streak"], 1);
    env.set(at(2026, 10, 29, 15, 59, 58));
    env.review("abandon", "abandon");
    let overview = env.data("/api/stats/overview");
    assert_eq!(overview["current_streak"], 2);
    assert_eq!(overview["total_words_practiced"], 2);
    assert_eq!(overview["total_time_minutes"], 2000.0 / 60000.0);
    env.set(at(2026, 10, 29, 16, 0, 0));
    assert_eq!(env.data("/api/stats/overview")["current_streak"], 2, "yesterday still counts");
    env.set(at(2026, 10, 30, 16, 0, 0));
    assert_eq!(env.data("/api/stats/overview")["current_streak"], 0);
}

#[test]
fn calendar_rejects_invalid_and_out_of_window_dates() {
    let env = calendar_env();
    for day in ["", "20261029", "2026-02-30", "2026-03-31", "2027-04-01", "2026-10-9"] {
        assert_eq!(env.get(&format!("/api/stats/calendar-words?date={day}")).0, 400, "{day}");
    }
}

fn vocabulary_env() -> Env {
    let mut words = vec![word("abandon", 101, true)];
    words.extend((0..204).map(|i| word(&format!("word-{}{}", (b'a' + i / 26) as char, (b'a' + i % 26) as char), 102 + i as i64, false)));
    // A duplicate source note counts once.
    words.push(word("abandon", 1000, false));
    Env::new(at(2026, 10, 29, 8, 0, 0), words)
}

fn page(env: &Env, query: &str) -> Value {
    env.data(&format!("/api/stats/vocabulary-words?dimension=cefr&value=B2&{query}"))
}

#[test]
fn full_deck_progress_without_expanding_practice() {
    let env = vocabulary_env();
    let before = env.fingerprint();
    let data = env.data("/api/stats/vocabulary-progress");
    assert_eq!((data["overall"]["total"].as_i64(), data["overall"]["new"].as_i64(), data["overall"]["learned"].as_i64()), (Some(205), Some(205), Some(0)));
    let levels: Vec<&str> = data["levels"].as_array().unwrap().iter().map(|l| l["value"].as_str().unwrap()).collect();
    assert_eq!(levels, ["A1", "A2", "B1", "B2", "C1", "C2"]);
    assert_eq!(data["levels"][3]["label"], "中高级");
    assert_eq!(data["levels"][3]["total"], 205);
    assert_eq!(data["topics"][0], json!({"value": "思维", "label": "思维", "total": 205, "learned": 0, "new": 205, "learning": 0, "mastered": 0}));
    assert_eq!(env.fingerprint(), before);
    assert_eq!(env.store().summary().unwrap()["total"], 1);
}

#[test]
fn fsrs_statuses_drive_groups_and_filters() {
    let env = vocabulary_env();
    env.review("abandon", "abandon");
    let data = env.data("/api/stats/vocabulary-progress");
    for group in [&data["overall"], &data["levels"][3], &data["topics"][0]] {
        assert_eq!([&group["learned"], &group["learning"], &group["mastered"], &group["new"]], [&json!(1), &json!(1), &json!(0), &json!(204)]);
    }
    assert_eq!(page(&env, "status=learning")["items"][0]["source_id"], "abandon");
    assert_eq!(page(&env, "status=new")["total"], 204);
    let now = env.now();
    for (state, stability, expected) in [(State::Review, 20.9, "learning"), (State::Review, 21.0, "mastered"), (State::Relearning, 100.0, "learning")] {
        env.set_card("abandon", now + TimeDelta::days(3), state, stability);
        assert_eq!(env.data("/api/stats/vocabulary-progress")["overall"][expected], 1);
        let items = page(&env, &format!("status={expected}"))["items"].clone();
        assert_eq!(items[0]["status"], expected);
        assert!(items[0].get("due").is_some());
        let topic = env.data(&format!("/api/stats/vocabulary-words?dimension=topic&value=思维&status={expected}"));
        assert_eq!(topic["total"], 1);
    }
}

#[test]
fn detail_lists_order_by_smoothed_errors_then_page() {
    let env = vocabulary_env();
    for (source, total, errors) in [("abandon", 1, 0), ("word-ab", 1, 1), ("word-ac", 10, 8), ("word-ad", 2, 1), ("word-ae", 4, 2), ("word-af", 4, 2)] {
        for i in 0..total {
            env.review(source, if i < errors { "" } else { source });
        }
    }
    let expected = ["word-ac", "word-ab", "word-ae", "word-af", "word-ad", "abandon"];
    for group in ["dimension=cefr&value=B2", "dimension=topic&value=%E6%80%9D%E7%BB%B4"] {
        let mut seen = vec![];
        for offset in [0, 2, 4] {
            let data = env.data(&format!("/api/stats/vocabulary-words?{group}&offset={offset}&limit=2"));
            assert_eq!((data["total"].as_i64(), data["next_offset"].as_i64()), (Some(205), Some(offset + 2)));
            seen.extend(sources(&data["items"]));
        }
        assert_eq!(seen, expected);
        assert_eq!(env.data(&format!("/api/stats/vocabulary-words?{group}&offset=6&limit=1"))["items"][0]["source_id"], "word-aa");
        let learned = env.data(&format!("/api/stats/vocabulary-words?{group}&status=learning"))["items"].clone();
        assert_eq!(sources(&learned), expected);
        assert_eq!(counts(&learned)[0], (2, 10));
        let fresh = env.data(&format!("/api/stats/vocabulary-words?{group}&status=new&limit=1"));
        assert_eq!(fresh["total"], 199);
        assert_eq!(counts(&fresh["items"]), [(0, 0)]);
    }
    let (mut all, mut offset) = (vec![], Value::from(0));
    while let Some(o) = offset.as_i64() {
        let data = page(&env, &format!("offset={o}"));
        all.extend(sources(&data["items"]));
        offset = data["next_offset"].clone();
    }
    assert_eq!(all.len(), 205);
    assert_eq!(all.iter().collect::<std::collections::HashSet<_>>().len(), 205);
    assert_eq!(page(&env, "offset=1000")["items"], json!([]));
}

#[test]
fn unknown_metadata_falls_into_fallback_groups() {
    let mut odd = word("unknown", 2000, false);
    odd["cefr"] = " c1 ".into();
    odd["category"] = "".into();
    let mut bad = word("bad-level", 2001, false);
    bad["cefr"] = "bad".into();
    let env = Env::new(at(2026, 10, 29, 8, 0, 0), vec![word("abandon", 101, true), odd, bad]);
    let data = env.data("/api/stats/vocabulary-progress");
    assert_eq!(data["levels"][4]["total"], 1);
    assert_eq!(data["levels"][6]["value"], "未分级");
    assert_eq!(env.data("/api/stats/vocabulary-words?dimension=cefr&value=%E6%9C%AA%E5%88%86%E7%BA%A7")["items"][0]["source_id"], "bad-level");
    assert_eq!(env.data("/api/stats/vocabulary-words?dimension=topic&value=%E6%9C%AA%E5%88%86%E7%B1%BB")["total"], 1);
}

#[test]
fn invalid_filters_and_paging_are_rejected() {
    let env = vocabulary_env();
    for query in ["", "dimension=bad&value=B2", "dimension=cefr", "dimension=cefr&value=B2&status=bad",
                  "dimension=cefr&value=B2&offset=-1", "dimension=cefr&value=B2&offset=abc",
                  "dimension=cefr&value=B2&limit=0", "dimension=cefr&value=B2&limit=201"] {
        assert_eq!(env.get(&format!("/api/stats/vocabulary-words?{query}")).0, 400, "{query}");
    }
    for query in ["", "source_id=", "source_id=abandon&before_id=-1", "source_id=abandon&before_id=bad",
                  "source_id=abandon&limit=0", "source_id=abandon&limit=201", "source_id=abandon&limit=bad"] {
        assert_eq!(env.get(&format!("/api/stats/word-errors?{query}")).0, 400, "{query}");
    }
}

#[test]
fn word_errors_page_by_review_id_per_source() {
    let env = vocabulary_env();
    let correct_only = env.data("/api/stats/word-errors?source_id=word-ab");
    assert_eq!(correct_only, json!({"items": [], "correct_attempts": 0, "total_attempts": 0, "next_before_id": null}));
    for answer in ["abndon", "abandon", "", "abando"] {
        env.review("abandon", answer);
    }
    let before = env.fingerprint();
    let first = env.data("/api/stats/word-errors?source_id=abandon&limit=2");
    assert_eq!((first["correct_attempts"].as_i64(), first["total_attempts"].as_i64()), (Some(1), Some(4)));
    let inputs = |v: &Value| v["items"].as_array().unwrap().iter().map(|r| r["user_input"].as_str().unwrap().to_string()).collect::<Vec<_>>();
    assert_eq!(inputs(&first), ["abando", ""]);
    let keys: std::collections::BTreeSet<&str> = first["items"][0].as_object().unwrap().keys().map(String::as_str).collect();
    assert_eq!(keys, ["id", "reviewed_at", "user_input", "word"].into());
    let second = env.data(&format!("/api/stats/word-errors?source_id=abandon&limit=2&before_id={}", first["next_before_id"]));
    assert_eq!(inputs(&second), ["abndon"]);
    assert!(second["next_before_id"].is_null());
    let scheduled = env.data("/api/stats/calendar-words?date=2026-10-29")["due"][0].clone();
    assert_eq!((scheduled["correct_attempts"].as_i64(), scheduled["total_attempts"].as_i64()), (Some(1), Some(4)));
    assert_eq!(env.fingerprint(), before);
}
