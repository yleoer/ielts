//! Application rules on top of FSRS, mirroring `typing-practice/backend/srs.py`.

use chrono::TimeDelta;
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::fsrs::{Card, Rating, Scheduler, State, DEFAULT_PARAMETERS};
use crate::time::{time_text, Time};

pub const MASTERED_STABILITY: f64 = 21.0;

#[derive(Clone, Debug)]
pub struct MemoryConfig {
    pub desired_retention: f64,
    pub easy_seconds: f64,
    pub hard_seconds: f64,
    pub enable_fuzzing: bool,
    pub parameters: [f64; 21],
}

impl Default for MemoryConfig {
    fn default() -> Self {
        MemoryConfig {
            desired_retention: 0.9, easy_seconds: 6.0, hard_seconds: 20.0, enable_fuzzing: true,
            parameters: DEFAULT_PARAMETERS,
        }
    }
}

pub struct Srs {
    pub config: MemoryConfig,
    pub scheduler: Scheduler,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct MemoryView {
    pub status: &'static str,
    pub state: u8,
    pub stability: Option<f64>,
    pub difficulty: Option<f64>,
    pub due: String,
    pub is_due: bool,
    pub retrievability: f64,
}

impl Srs {
    /// Fails only when FSRS parameters are out of bounds (e.g. a bad optimization result).
    pub fn new(config: MemoryConfig) -> Result<Self, String> {
        let scheduler = Scheduler::new(
            config.parameters, config.desired_retention,
            vec![TimeDelta::minutes(1), TimeDelta::minutes(10)], vec![TimeDelta::minutes(10)],
            36500, config.enable_fuzzing,
        )?;
        Ok(Srs { config, scheduler })
    }

    /// Wrong → Again; otherwise strictly > hard → Hard, strictly < easy → Easy, else Good.
    /// `duration_ms` is checked at the request boundary (`store::submit`).
    pub fn grade(&self, correct: bool, duration_ms: f64) -> Rating {
        if !correct {
            Rating::Again
        } else if duration_ms > self.config.hard_seconds * 1000.0 {
            Rating::Hard
        } else if duration_ms < self.config.easy_seconds * 1000.0 {
            Rating::Easy
        } else {
            Rating::Good
        }
    }

    /// Reviews with fuzz seeded by `attempt_id`, so replaying the same log on any
    /// device yields the same schedule.
    pub fn review(&self, card: &Card, correct: bool, duration_ms: f64, now: Time, attempt_id: &str) -> (Card, Rating) {
        let rating = self.grade(correct, duration_ms);
        (self.scheduler.review_card(card, rating, now, Some(fuzz_sample(attempt_id))), rating)
    }

    pub fn describe(&self, card: &Card, now: Time) -> MemoryView {
        MemoryView {
            status: if is_mastered(card) { "mastered" } else { "learning" },
            state: card.state as u8,
            stability: card.stability,
            difficulty: card.difficulty,
            due: time_text(card.due),
            is_due: card.due <= now,
            retrievability: self.scheduler.retrievability(card, now),
        }
    }
}

pub fn is_mastered(card: &Card) -> bool {
    card.state == State::Review && card.stability.unwrap_or(0.0) >= MASTERED_STABILITY
}

/// Uniform `[0, 1)` from the first 53 bits of SHA-256(attempt_id).
pub fn fuzz_sample(attempt_id: &str) -> f64 {
    let digest = Sha256::digest(attempt_id.as_bytes());
    let bits = u64::from_be_bytes(digest[..8].try_into().unwrap()) >> 11;
    bits as f64 / (1u64 << 53) as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fuzz_sample_is_stable_and_in_range() {
        let a = fuzz_sample("attempt-1");
        assert_eq!(a, fuzz_sample("attempt-1"));
        assert_ne!(a, fuzz_sample("attempt-2"));
        assert!((0.0..1.0).contains(&a));
    }
}
