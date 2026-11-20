//! Difficult and stale practice select from history, then issue tickets like free practice:
//! first answers are saved and update FSRS, even before the card is due.

mod common;

use chrono::TimeDelta;
use cijian_core::fsrs::State;
use cijian_core::time::time_text;
use common::{at, word, Env};
use serde_json::{json, Value};

fn sources(data: &Value) -> Vec<String> {
    data["items"].as_array().unwrap().iter().map(|item| item["source_id"].as_str().unwrap().to_string()).collect()
}

fn reviews(env: &Env, source: &str) -> i64 {
    env.db().query_row("SELECT COUNT(*) FROM word_reviews WHERE word_key=?", [format!("word-atlas:{source}")], |r| r.get(0)).unwrap()
}

#[test]
fn ranks_current_learned_words_by_smoothed_errors_then_error_count() {
    let cases = [("hard", 10, 8), ("rare", 1, 1), ("many", 4, 2), ("alpha", 2, 1),
                 ("beta", 2, 1), ("correct", 3, 0), ("excluded", 3, 3), ("removed", 3, 3)];
    let mut words: Vec<_> = cases.iter().enumerate().map(|(i, (name, _, _))| word(name, i as i64 + 1, true)).collect();
    words.push(word("never", 100, true));
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), words.clone());
    for (name, total, errors) in cases {
        for index in 0..total { env.review(name, if index < errors { "wrong" } else { name }); }
    }
    words.retain(|word| word["source_id"] != "removed");
    for word in &mut words {
        if word["source_id"] == "excluded" { word["learned"] = false.into(); }
        if word["source_id"] == "rare" { word["id"] = 200.into(); }
    }
    env.import(words);
    let data = env.data("/api/practice/queue?session_id=focus&mode=difficult");
    assert_eq!(sources(&data), ["hard", "rare", "many", "alpha", "beta"]);
    assert_eq!(data["items"][1]["id"], 200, "history follows SourceId after a reimport");
    assert!(data["items"].as_array().unwrap().iter().all(|word| word["attempt_id"].is_string() && word["memory"].is_object()));
}

#[test]
fn caps_the_sorted_batch_at_twenty_and_honors_smaller_limits() {
    let words: Vec<_> = (0..25).rev().map(|index| word(&format!("word-{index:02}"), index + 1, true)).collect();
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), words);
    for index in 0..25 { env.review(&format!("word-{index:02}"), "wrong"); }
    let expected: Vec<_> = (0..20).map(|index| format!("word-{index:02}")).collect();
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=difficult")), expected);
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=difficult&limit=3")), expected[..3]);
}

#[test]
fn no_error_history_returns_an_empty_batch_instead_of_unpracticed_or_correct_words() {
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), vec![word("correct", 1, true), word("never", 2, true)]);
    env.review("correct", "correct");
    let before = env.fingerprint();
    let data = env.data("/api/practice/queue?session_id=focus&mode=difficult");
    assert_eq!(data["items"], json!([]));
    assert_eq!(data["summary"]["total"], 2);
    assert_eq!(env.fingerprint(), before, "an empty batch issues no tickets");
}

#[test]
fn stale_practice_orders_practiced_words_by_oldest_last_review() {
    let words: Vec<_> = ["old", "middle", "recent", "never"].iter().enumerate()
        .map(|(i, name)| word(name, i as i64 + 1, true)).collect();
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), words);
    env.review("middle", "middle");
    env.review("old", "wrong");
    env.review("recent", "recent");
    env.advance(TimeDelta::days(3));
    env.review("middle", "middle");
    env.review("recent", "recent");
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=stale&limit=2")), ["old", "middle"]);
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=stale")), ["old", "middle", "recent"]);
}

#[test]
fn difficult_and_stale_answers_are_saved_before_the_card_is_due() {
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), vec![word("hard", 1, true)]);
    env.review("hard", "wrong");
    for mode in ["difficult", "stale"] {
        let due = env.now() + TimeDelta::days(5);
        env.set_card("hard", due, State::Review, 10.0);
        let item = env.data(&format!("/api/practice/queue?session_id={mode}&mode={mode}"))["items"][0].clone();
        assert_eq!(item["memory"]["is_due"], false);
        let before = reviews(&env, "hard");
        env.advance(TimeDelta::seconds(5));
        let answer = env.store().submit(&json!({"attempt_id": item["attempt_id"], "session_id": mode, "user_input": "hard",
            "duration_ms": 3000, "reviewed_at": time_text(env.now())})).unwrap();
        assert_eq!(answer["is_correct"], true, "{mode}");
        assert_eq!(answer["card_version"], item["card_version"].as_i64().unwrap() + 1, "{mode}");
        assert_eq!(reviews(&env, "hard"), before + 1, "{mode} answers count toward statistics");
        let next: String = env.db().query_row("SELECT due FROM word_memory WHERE word_key='word-atlas:hard'", [], |r| r.get(0)).unwrap();
        assert_ne!(next, time_text(due), "{mode} answers reschedule the card");
    }
}
