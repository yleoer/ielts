//! UTC timestamps with microsecond precision, matching `srs.time_text`.

use chrono::{DateTime, SecondsFormat, TimeDelta, Utc};

pub type Time = DateTime<Utc>;

pub const MICROS_PER_DAY: i64 = 86_400_000_000;

/// `2026-01-01T00:00:00.000000Z`
pub fn time_text(value: Time) -> String {
    value.to_rfc3339_opts(SecondsFormat::Micros, true)
}

/// Parses RFC 3339 with an explicit offset (naive times are rejected like `srs.parse_time`).
pub fn parse_time(value: &str) -> Result<Time, String> {
    DateTime::parse_from_rfc3339(value)
        .map(|v| v.with_timezone(&Utc))
        .map_err(|_| "时间必须包含时区".to_string())
}

/// Python `timedelta.days`: floor division of the delta by one day.
pub fn whole_days(delta: TimeDelta) -> i64 {
    let micros = delta.num_microseconds().expect("time delta overflow");
    micros.div_euclid(MICROS_PER_DAY)
}

pub fn days(n: i64) -> TimeDelta {
    TimeDelta::days(n)
}

/// Python `timedelta * float`, rounded half-to-even to whole microseconds.
pub fn scale(delta: TimeDelta, factor: f64) -> TimeDelta {
    let micros = delta.num_microseconds().expect("time delta overflow") as f64 * factor;
    TimeDelta::microseconds(micros.round_ties_even() as i64)
}
