//! Difficult and stale practice select from history without issuing or recording reviews.

mod common;

use chrono::TimeDelta;
use cijian_core::fsrs::State;
use common::{at, word, Env};
use serde_json::{json, Value};

fn sources(data: &Value) -> Vec<String> {
    data["items"].as_array().unwrap().iter().map(|item| item["source_id"].as_str().unwrap().to_string()).collect()
}

#[test]
fn ranks_current_learned_words_by_smoothed_errors_then_error_count_without_writes() {
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
    env.set_card("hard", env.now() + TimeDelta::days(1), State::Review, 10.0);
    let before = env.fingerprint();
    let data = env.data("/api/practice/queue?session_id=focus&mode=difficult");
    assert_eq!(sources(&data), ["hard", "rare", "many", "alpha", "beta"]);
    assert_eq!(data["items"][0]["total_attempts"], 10);
    assert_eq!(data["items"][0]["correct_attempts"], 2);
    assert_eq!(data["items"][1]["id"], 200, "history follows SourceId after a reimport");
    assert!(data["items"].as_array().unwrap().iter().all(|word| word.get("attempt_id").is_none()));
    assert_eq!(env.fingerprint(), before, "selection must not even create practice_items");
}

#[test]
fn caps_the_sorted_batch_at_twenty_and_honors_smaller_limits() {
    let words: Vec<_> = (0..25).rev().map(|index| word(&format!("word-{index:02}"), index + 1, true)).collect();
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), words);
    for index in 0..25 { env.review(&format!("word-{index:02}"), "wrong"); }
    let expected: Vec<_> = (0..20).map(|index| format!("word-{index:02}")).collect();
    let before = env.fingerprint();
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=difficult")), expected);
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=difficult&limit=3")), expected[..3]);
    assert_eq!(env.fingerprint(), before);
}

#[test]
fn no_error_history_returns_an_empty_batch_instead_of_unpracticed_or_correct_words() {
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), vec![word("correct", 1, true), word("never", 2, true)]);
    env.review("correct", "correct");
    let before = env.fingerprint();
    let data = env.data("/api/practice/queue?session_id=focus&mode=difficult");
    assert_eq!(data["items"], json!([]));
    assert_eq!(data["summary"]["total"], 2);
    assert_eq!(env.fingerprint(), before);
}

#[test]
fn stale_practice_orders_practiced_words_by_oldest_last_review_without_writes() {
    let words: Vec<_> = ["old", "middle", "recent", "never"].iter().enumerate()
        .map(|(i, name)| word(name, i as i64 + 1, true)).collect();
    let env = Env::new(at(2026, 11, 11, 0, 0, 0), words);
    env.review("middle", "middle");
    env.review("old", "wrong");
    env.review("recent", "recent");
    env.advance(TimeDelta::days(3));
    env.review("middle", "middle");
    env.review("recent", "recent");
    let before = env.fingerprint();
    let data = env.data("/api/practice/queue?session_id=focus&mode=stale&limit=2");
    assert_eq!(sources(&data), ["old", "middle"]);
    assert!(data["items"][0]["last_reviewed_at"].as_str().unwrap() < data["items"][1]["last_reviewed_at"].as_str().unwrap());
    assert!(data["items"][0].get("attempt_id").is_none());
    assert_eq!(sources(&env.data("/api/practice/queue?session_id=focus&mode=stale")), ["old", "middle", "recent"]);
    assert_eq!(env.fingerprint(), before);
}
