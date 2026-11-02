//! Parity with py-fsrs: replays `fixtures/fsrs-golden.json` (fuzz disabled).

use std::path::PathBuf;

use cijian_core::answer::{answer_candidates, is_correct, normalize_answer};
use cijian_core::fsrs::{Card, Rating};
use cijian_core::srs::{MemoryConfig, Srs};
use cijian_core::time::{parse_time, time_text};
use serde_json::Value;

fn fixture() -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures/fsrs-golden.json");
    serde_json::from_str(&std::fs::read_to_string(path).expect("run scripts/gen_fsrs_fixtures.py")).unwrap()
}

fn srs() -> Srs {
    Srs::new(MemoryConfig { enable_fuzzing: false, ..MemoryConfig::default() }).unwrap()
}

fn close(actual: Option<f64>, expected: &Value, what: &str) {
    match (actual, expected.as_f64()) {
        (None, None) => {}
        (Some(a), Some(e)) => assert!((a - e).abs() <= 1e-9 * e.abs().max(1.0), "{what}: {a} != {e}"),
        _ => panic!("{what}: {actual:?} != {expected}"),
    }
}

#[test]
fn scheduler_matches_py_fsrs() {
    let data = fixture();
    let srs = srs();
    let mut reviews = 0;
    for seq in data["sequences"].as_array().unwrap() {
        let id = seq["card_id"].as_i64().unwrap();
        let mut card = Card::new(id, parse_time(seq["start"].as_str().unwrap()).unwrap());
        for (i, step) in seq["steps"].as_array().unwrap().iter().enumerate() {
            let at = parse_time(step["reviewed_at"].as_str().unwrap()).unwrap();
            let rating = Rating::try_from(step["rating"].as_u64().unwrap() as u8).unwrap();
            card = srs.scheduler.review_card(&card, rating, at, None);
            let exp = &step["after"];
            let what = format!("card {id} step {i}");
            assert_eq!(card.state as u64, exp["state"].as_u64().unwrap(), "{what} state");
            assert_eq!(card.step.map(|s| s as u64), exp["step"].as_u64(), "{what} step");
            assert_eq!(time_text(card.due), exp["due"].as_str().unwrap(), "{what} due");
            assert_eq!(card.last_review.map(time_text).as_deref(), exp["last_review"].as_str(), "{what} last_review");
            close(card.stability, &exp["stability"], &format!("{what} stability"));
            close(card.difficulty, &exp["difficulty"], &format!("{what} difficulty"));
            let r = srs.scheduler.retrievability(&card, at + chrono::TimeDelta::days(1));
            close(Some(r), &step["retrievability_at_review_plus_1d"], &format!("{what} retrievability"));
            reviews += 1;
        }
    }
    assert!(reviews > 2000);
}

#[test]
fn grading_matches_srs_py() {
    let data = fixture();
    let srs = srs();
    for case in data["grading"]["cases"].as_array().unwrap() {
        let rating = srs.grade(case["correct"].as_bool().unwrap(), case["duration_ms"].as_f64().unwrap()).unwrap();
        assert_eq!(rating as u64, case["rating"].as_u64().unwrap(), "{case}");
    }
}

#[test]
fn answers_match_srs_py() {
    let data = fixture();
    for case in data["answers"].as_array().unwrap() {
        let (word, input) = (case["word"].as_str().unwrap(), case["input"].as_str().unwrap());
        assert_eq!(normalize_answer(input), case["normalized"].as_str().unwrap(), "{case}");
        let candidates: Vec<String> = serde_json::from_value(case["candidates"].clone()).unwrap();
        assert_eq!(answer_candidates(word), candidates, "{case}");
        assert_eq!(is_correct(word, input), case["correct"].as_bool().unwrap(), "{case}");
    }
}

#[test]
fn card_json_reads_py_fsrs_format() {
    let card: Card = serde_json::from_str(
        r#"{"card_id":7,"state":2,"step":null,"stability":3.5,"difficulty":5.1,"due":"2026-01-05T00:00:00+00:00","last_review":"2026-01-01T00:00:00.123456+00:00"}"#,
    )
    .unwrap();
    assert_eq!(time_text(card.last_review.unwrap()), "2026-01-01T00:00:00.123456Z");
    let back: Card = serde_json::from_str(&serde_json::to_string(&card).unwrap()).unwrap();
    assert_eq!(back, card);
}
