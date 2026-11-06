//! Review proximity and top-to-bottom tinting, independent of the native tray.

use chrono::TimeDelta;
use serde_json::Value;

use cijian_core::time::{parse_time, Time};

pub const FULL: u16 = 600;

pub fn level(summary: &Value, now: Time) -> Result<u16, String> {
    if summary["due_count"].as_u64().unwrap_or(0) > 0 {
        return Ok(FULL);
    }
    let Some(next) = summary["next_due"].as_str() else {
        return Ok(0);
    };
    let remaining = parse_time(next)? - now;
    if remaining <= TimeDelta::zero() {
        Ok(FULL)
    } else if remaining >= TimeDelta::minutes(10) {
        Ok(0)
    } else {
        // Reserve the fully tinted state for the actual deadline.
        Ok(((600_000 - remaining.num_milliseconds()) / 1000).min(599) as u16)
    }
}

pub fn render(rgba: &[u8], width: u32, height: u32, level: u16) -> Vec<u8> {
    let mut output = rgba.to_vec();
    let front = height as f32 * level as f32 / FULL as f32;
    for (index, pixel) in output.chunks_exact_mut(4).enumerate() {
        let weight = (front - (index / width as usize) as f32).clamp(0.0, 1.0);
        // Keep the book's white pages and the original alpha/outline shape.
        if weight == 0.0 || (pixel[0] > 250 && pixel[1] > 248 && pixel[2] > 244) {
            continue;
        }
        let shade = *pixel[..3].iter().max().unwrap() as f32 / 255.0;
        for (channel, target) in pixel[..3].iter_mut().zip([246.0, 173.0, 67.0]) {
            *channel = (*channel as f32 * (1.0 - weight) + target * shade * weight).round() as u8;
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    use cijian_core::time::time_text;
    use serde_json::json;

    #[test]
    fn fills_only_in_the_final_ten_minutes_and_stays_full_when_due() {
        let deadline = parse_time("2026-11-06T12:00:00Z").unwrap();
        let summary = json!({"due_count": 0, "next_due": time_text(deadline)});
        for (milliseconds, expected) in [
            (660_000, 0),
            (600_000, 0),
            (599_000, 1),
            (300_000, 300),
            (1, 599),
            (0, 600),
            (-60_000, 600),
        ] {
            assert_eq!(
                level(&summary, deadline - TimeDelta::milliseconds(milliseconds)).unwrap(),
                expected
            );
        }
        assert_eq!(
            level(
                &json!({"due_count": 3, "next_due": time_text(deadline + TimeDelta::days(1))}),
                deadline
            )
            .unwrap(),
            FULL
        );
        // Completing reviews replaces the cached summary with the next plan.
        assert_eq!(
            level(
                &json!({"due_count": 0, "next_due": time_text(deadline + TimeDelta::days(1))}),
                deadline
            )
            .unwrap(),
            0
        );
    }

    #[test]
    fn new_words_do_not_trigger_the_reminder_and_invalid_time_is_reported() {
        let now = parse_time("2026-11-06T12:00:00Z").unwrap();
        for summary in [
            json!({"new_available": 5}),
            json!({"next_due": null}),
            json!({}),
        ] {
            assert_eq!(level(&summary, now).unwrap(), 0);
        }
        assert!(level(&json!({"next_due": "invalid"}), now).is_err());
    }

    #[test]
    fn tint_advances_downward_preserving_pages_alpha_and_source() {
        let source = [
            40, 80, 60, 128, 40, 80, 60, 255, 255, 254, 251, 255, 40, 80, 60, 0,
        ];
        assert_eq!(render(&source, 1, 4, 0), source);
        let half = render(&source, 1, 4, 300);
        let full = render(&source, 1, 4, FULL);
        assert_eq!(&half[..8], &full[..8]);
        assert_eq!(&half[8..], &source[8..]);
        assert_ne!(&full[12..15], &source[12..15]);
        assert_eq!(&full[8..12], &source[8..12]);
        for i in (3..source.len()).step_by(4) {
            assert_eq!(full[i], source[i]);
        }
        assert_eq!(source[0], 40);
        let before = render(&source, 1, 4, 100);
        let after = render(&source, 1, 4, 101);
        assert!(after[0] >= before[0]);
        assert_eq!(&before[4..], &source[4..]);
    }
}
