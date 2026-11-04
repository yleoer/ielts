//! Port of py-fsrs 6.3.2 `fsrs.scheduler.Scheduler` (float path only).
//!
//! Behaviour must match `typing-practice/backend/srs.py`; verified by
//! `tests/golden.rs` against `fixtures/fsrs-golden.json`.

use std::f64::consts::E;

use chrono::TimeDelta;
use serde::{Deserialize, Serialize};

use crate::time::{days, scale, whole_days, Time};

pub const DEFAULT_PARAMETERS: [f64; 21] = [
    0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796, 1.4835,
    0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542,
];
pub const STABILITY_MIN: f64 = 0.001;
const LOWER_BOUNDS: [f64; 21] = [
    STABILITY_MIN, STABILITY_MIN, STABILITY_MIN, STABILITY_MIN, 1.0, 0.001, 0.001, 0.001, 0.0, 0.0,
    0.001, 0.001, 0.001, 0.001, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.1,
];
const UPPER_BOUNDS: [f64; 21] = [
    100.0, 100.0, 100.0, 100.0, 10.0, 4.0, 4.0, 0.75, 4.5, 0.8, 3.5, 5.0, 0.25, 0.9, 4.0, 1.0, 6.0,
    2.0, 2.0, 0.8, 0.8,
];
const MIN_DIFFICULTY: f64 = 1.0;
const MAX_DIFFICULTY: f64 = 10.0;
/// (start, end, factor)
const FUZZ_RANGES: [(f64, f64, f64); 3] = [(2.5, 7.0, 0.15), (7.0, 20.0, 0.1), (20.0, f64::INFINITY, 0.05)];

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "u8", into = "u8")]
pub enum Rating {
    Again = 1,
    Hard = 2,
    Good = 3,
    Easy = 4,
}

impl TryFrom<u8> for Rating {
    type Error = String;
    fn try_from(v: u8) -> Result<Self, String> {
        match v {
            1 => Ok(Rating::Again),
            2 => Ok(Rating::Hard),
            3 => Ok(Rating::Good),
            4 => Ok(Rating::Easy),
            _ => Err(format!("unknown rating {v}")),
        }
    }
}

impl From<Rating> for u8 {
    fn from(r: Rating) -> u8 {
        r as u8
    }
}

impl Rating {
    pub fn name(self) -> &'static str {
        match self {
            Rating::Again => "Again",
            Rating::Hard => "Hard",
            Rating::Good => "Good",
            Rating::Easy => "Easy",
        }
    }
    fn value(self) -> f64 {
        self as u8 as f64
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "u8", into = "u8")]
pub enum State {
    Learning = 1,
    Review = 2,
    Relearning = 3,
}

impl TryFrom<u8> for State {
    type Error = String;
    fn try_from(v: u8) -> Result<Self, String> {
        match v {
            1 => Ok(State::Learning),
            2 => Ok(State::Review),
            3 => Ok(State::Relearning),
            _ => Err(format!("unknown state {v}")),
        }
    }
}

impl From<State> for u8 {
    fn from(s: State) -> u8 {
        s as u8
    }
}

/// Same JSON shape as py-fsrs `Card.to_dict()`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Card {
    pub card_id: i64,
    pub state: State,
    pub step: Option<usize>,
    pub stability: Option<f64>,
    pub difficulty: Option<f64>,
    #[serde(with = "time_serde")]
    pub due: Time,
    #[serde(with = "opt_time_serde")]
    pub last_review: Option<Time>,
}

impl Card {
    pub fn new(card_id: i64, due: Time) -> Self {
        Card { card_id, state: State::Learning, step: Some(0), stability: None, difficulty: None, due, last_review: None }
    }
}

#[derive(Clone, Debug)]
pub struct Scheduler {
    pub parameters: [f64; 21],
    pub desired_retention: f64,
    pub learning_steps: Vec<TimeDelta>,
    pub relearning_steps: Vec<TimeDelta>,
    pub maximum_interval: i64,
    pub enable_fuzzing: bool,
    decay: f64,
    factor: f64,
}

impl Scheduler {
    pub fn new(
        parameters: [f64; 21],
        desired_retention: f64,
        learning_steps: Vec<TimeDelta>,
        relearning_steps: Vec<TimeDelta>,
        maximum_interval: i64,
        enable_fuzzing: bool,
    ) -> Result<Self, String> {
        let errors: Vec<String> = parameters
            .iter()
            .enumerate()
            .filter(|(i, p)| !(LOWER_BOUNDS[*i] <= **p && **p <= UPPER_BOUNDS[*i]))
            .map(|(i, p)| format!("parameters[{i}] = {p} is out of bounds: ({}, {})", LOWER_BOUNDS[i], UPPER_BOUNDS[i]))
            .collect();
        if !errors.is_empty() {
            return Err(format!("One or more parameters are out of bounds:\n{}", errors.join("\n")));
        }
        let decay = -parameters[20];
        let factor = 0.9f64.powf(1.0 / decay) - 1.0;
        Ok(Scheduler {
            parameters, desired_retention, learning_steps, relearning_steps, maximum_interval,
            enable_fuzzing, decay, factor,
        })
    }

    pub fn retrievability(&self, card: &Card, now: Time) -> f64 {
        let (Some(last), Some(stability)) = (card.last_review, card.stability) else {
            return 0.0;
        };
        let elapsed = whole_days(now - last).max(0) as f64;
        (1.0 + self.factor * elapsed / stability).powf(self.decay)
    }

    /// `fuzz` is a uniform sample in `[0, 1)`; required only when fuzzing is enabled
    /// and the card lands in Review. `None` disables fuzz for this review.
    pub fn review_card(&self, card: &Card, rating: Rating, now: Time, fuzz: Option<f64>) -> Card {
        let mut card = card.clone();
        let since_last = card.last_review.map(|last| whole_days(now - last));
        let short_term = matches!(since_last, Some(d) if d < 1);

        let next_interval = match card.state {
            State::Learning | State::Relearning => {
                let relearning = card.state == State::Relearning;
                match (card.stability, card.difficulty) {
                    (Some(s), Some(d)) if short_term => {
                        card.stability = Some(self.short_term_stability(s, rating));
                        card.difficulty = Some(self.next_difficulty(d, rating));
                    }
                    (Some(s), Some(d)) => {
                        let r = self.retrievability(&card, now);
                        card.stability = Some(self.next_stability(d, s, r, rating));
                        card.difficulty = Some(self.next_difficulty(d, rating));
                    }
                    _ => {
                        // Relearning cards always have stability/difficulty (py-fsrs asserts).
                        assert!(!relearning, "relearning card without memory state");
                        card.stability = Some(self.initial_stability(rating));
                        card.difficulty = Some(self.initial_difficulty(rating, true));
                    }
                }
                let steps = if relearning { &self.relearning_steps } else { &self.learning_steps };
                self.step_interval(&mut card, rating, steps)
            }
            State::Review => {
                let (s, d) = (card.stability.expect("review stability"), card.difficulty.expect("review difficulty"));
                card.stability = Some(if short_term {
                    self.short_term_stability(s, rating)
                } else {
                    let r = self.retrievability(&card, now);
                    self.next_stability(d, s, r, rating)
                });
                card.difficulty = Some(self.next_difficulty(d, rating));
                if rating == Rating::Again && !self.relearning_steps.is_empty() {
                    card.state = State::Relearning;
                    card.step = Some(0);
                    self.relearning_steps[0]
                } else {
                    days(self.next_interval(card.stability.unwrap()))
                }
            }
        };

        let next_interval = match fuzz {
            Some(sample) if self.enable_fuzzing && card.state == State::Review => self.fuzzed_interval(next_interval, sample),
            _ => next_interval,
        };
        card.due = now + next_interval;
        card.last_review = Some(now);
        card
    }

    /// Replays logs (sorted by time) from a fresh card, like `Scheduler.reschedule_card`.
    pub fn reschedule(&self, card: &Card, logs: &[(Time, Rating, Option<f64>)]) -> Card {
        let mut sorted = logs.to_vec();
        sorted.sort_by_key(|log| log.0);
        sorted.iter().fold(Card::new(card.card_id, card.due), |c, (at, rating, fuzz)| self.review_card(&c, *rating, *at, *fuzz))
    }

    fn step_interval(&self, card: &mut Card, rating: Rating, steps: &[TimeDelta]) -> TimeDelta {
        let step = card.step.expect("learning step");
        let graduate = steps.is_empty() || (step >= steps.len() && rating != Rating::Again);
        if graduate {
            return self.graduate(card);
        }
        match rating {
            Rating::Again => {
                card.step = Some(0);
                steps[0]
            }
            Rating::Hard => {
                if step == 0 && steps.len() == 1 {
                    scale(steps[0], 1.5)
                } else if step == 0 {
                    scale(steps[0] + steps[1], 0.5)
                } else {
                    steps[step]
                }
            }
            Rating::Good if step + 1 == steps.len() => self.graduate(card),
            Rating::Good => {
                card.step = Some(step + 1);
                steps[step + 1]
            }
            Rating::Easy => self.graduate(card),
        }
    }

    fn graduate(&self, card: &mut Card) -> TimeDelta {
        card.state = State::Review;
        card.step = None;
        days(self.next_interval(card.stability.unwrap()))
    }

    fn clamp_difficulty(d: f64) -> f64 {
        d.clamp(MIN_DIFFICULTY, MAX_DIFFICULTY)
    }

    fn clamp_stability(s: f64) -> f64 {
        s.max(STABILITY_MIN)
    }

    fn initial_stability(&self, rating: Rating) -> f64 {
        Self::clamp_stability(self.parameters[rating as usize - 1])
    }

    fn initial_difficulty(&self, rating: Rating, clamp: bool) -> f64 {
        let w = &self.parameters;
        let d = w[4] - E.powf(w[5] * (rating.value() - 1.0)) + 1.0;
        if clamp { Self::clamp_difficulty(d) } else { d }
    }

    pub fn next_interval(&self, stability: f64) -> i64 {
        let interval = (stability / self.factor) * (self.desired_retention.powf(1.0 / self.decay) - 1.0);
        (interval.round_ties_even() as i64).max(1).min(self.maximum_interval)
    }

    fn short_term_stability(&self, stability: f64, rating: Rating) -> f64 {
        let w = &self.parameters;
        let mut increase = E.powf(w[17] * (rating.value() - 3.0 + w[18])) * stability.powf(-w[19]);
        if rating != Rating::Again {
            increase = increase.max(1.0);
        }
        Self::clamp_stability(stability * increase)
    }

    fn next_difficulty(&self, difficulty: f64, rating: Rating) -> f64 {
        let w = &self.parameters;
        let arg1 = self.initial_difficulty(Rating::Easy, false);
        let delta = -(w[6] * (rating.value() - 3.0));
        let arg2 = difficulty + (10.0 - difficulty) * delta / 9.0;
        Self::clamp_difficulty(w[7] * arg1 + (1.0 - w[7]) * arg2)
    }

    fn next_stability(&self, difficulty: f64, stability: f64, retrievability: f64, rating: Rating) -> f64 {
        let w = &self.parameters;
        let next = if rating == Rating::Again {
            let long_term = w[11]
                * difficulty.powf(-w[12])
                * ((stability + 1.0).powf(w[13]) - 1.0)
                * E.powf((1.0 - retrievability) * w[14]);
            let short_term = stability / E.powf(w[17] * w[18]);
            long_term.min(short_term)
        } else {
            let hard_penalty = if rating == Rating::Hard { w[15] } else { 1.0 };
            let easy_bonus = if rating == Rating::Easy { w[16] } else { 1.0 };
            stability
                * (1.0
                    + E.powf(w[8])
                        * (11.0 - difficulty)
                        * stability.powf(-w[9])
                        * (E.powf((1.0 - retrievability) * w[10]) - 1.0)
                        * hard_penalty
                        * easy_bonus)
        };
        Self::clamp_stability(next)
    }

    fn fuzzed_interval(&self, interval: TimeDelta, sample: f64) -> TimeDelta {
        let interval_days = whole_days(interval);
        if (interval_days as f64) < 2.5 {
            return interval;
        }
        let mut delta = 1.0;
        for (start, end, factor) in FUZZ_RANGES {
            delta += factor * ((interval_days as f64).min(end) - start).max(0.0);
        }
        let min_ivl = ((interval_days as f64 - delta).round_ties_even() as i64).max(2);
        let max_ivl = ((interval_days as f64 + delta).round_ties_even() as i64).min(self.maximum_interval);
        let min_ivl = min_ivl.min(max_ivl);
        let fuzzed = sample * (max_ivl - min_ivl + 1) as f64 + min_ivl as f64;
        days((fuzzed.round_ties_even() as i64).min(self.maximum_interval))
    }
}

mod time_serde {
    use super::Time;
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S: Serializer>(value: &Time, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&crate::time::time_text(*value))
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Time, D::Error> {
        crate::time::parse_time(&String::deserialize(d)?).map_err(serde::de::Error::custom)
    }
}

mod opt_time_serde {
    use super::Time;
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S: Serializer>(value: &Option<Time>, s: S) -> Result<S::Ok, S::Error> {
        match value {
            Some(v) => s.serialize_str(&crate::time::time_text(*v)),
            None => s.serialize_none(),
        }
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Option<Time>, D::Error> {
        Option::<String>::deserialize(d)?
            .map(|v| crate::time::parse_time(&v).map_err(serde::de::Error::custom))
            .transpose()
    }
}
