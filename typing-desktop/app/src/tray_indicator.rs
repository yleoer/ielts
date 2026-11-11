//! Review proximity and top-to-bottom tinting, independent of the native tray.

use chrono::TimeDelta;
use serde_json::Value;

use cijian_core::time::{parse_time, Time};

pub const FULL: u16 = 600;
const APPROACHING_COLOR: [f32; 3] = [246.0, 173.0, 67.0];
const DUE_COLOR: [f32; 3] = [216.0, 76.0, 62.0];

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
        // Reserve the full fill and its distinct due color for the actual deadline.
        Ok(((600_000 - remaining.num_milliseconds()) / 1000).min(599) as u16)
    }
}

pub fn render(rgba: &[u8], width: u32, height: u32, level: u16) -> Vec<u8> {
    let mut output = rgba.to_vec();
    let front = height as f32 * level as f32 / FULL as f32;
    let tint = if level == FULL {
        DUE_COLOR
    } else {
        APPROACHING_COLOR
    };
    for (index, pixel) in output.chunks_exact_mut(4).enumerate() {
        let weight = (front - (index / width as usize) as f32).clamp(0.0, 1.0);
        // Keep the book's white pages and the original alpha/outline shape.
        if weight == 0.0 || (pixel[0] > 250 && pixel[1] > 248 && pixel[2] > 244) {
            continue;
        }
        let shade = *pixel[..3].iter().max().unwrap() as f32 / 255.0;
        for (channel, target) in pixel[..3].iter_mut().zip(tint) {
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
        let almost_due = render(&source, 1, 4, FULL - 1);
        let due = render(&source, 1, 4, FULL);
        assert_eq!(&half[..8], &almost_due[..8]);
        assert_eq!(&half[8..], &source[8..]);
        assert_ne!(&due[12..15], &source[12..15]);
        for tinted in [&half, &almost_due, &due] {
            assert_eq!(&tinted[8..12], &source[8..12]);
            for i in (3..source.len()).step_by(4) {
                assert_eq!(tinted[i], source[i]);
            }
        }
        assert_eq!(source[0], 40);
        let before = render(&source, 1, 4, 100);
        let after = render(&source, 1, 4, 101);
        assert!(after[0] >= before[0]);
        assert_eq!(&before[4..], &source[4..]);
    }

    #[test]
    fn deadline_switches_from_orange_to_red_before_the_cached_due_count_refreshes() {
        let deadline = parse_time("2026-11-06T12:00:00Z").unwrap();
        let summary = json!({"due_count": 0, "next_due": time_text(deadline)});
        let source = [40, 80, 60, 255];
        let approaching = render(
            &source,
            1,
            1,
            level(&summary, deadline - TimeDelta::milliseconds(1)).unwrap(),
        );
        let due = render(&source, 1, 1, level(&summary, deadline).unwrap());
        // Nearly full orange and due red differ in hue, not just the last sliver of fill.
        assert!(approaching[1] > approaching[0] / 2);
        assert!(due[1] < due[0] / 2);
        assert_eq!(
            due,
            render(
                &source,
                1,
                1,
                level(&json!({"due_count": 1, "next_due": null}), deadline).unwrap()
            )
        );
        assert_eq!(
            due,
            render(
                &source,
                1,
                1,
                level(&summary, deadline + TimeDelta::days(1)).unwrap()
            )
        );
        let completed =
            json!({"due_count": 0, "next_due": time_text(deadline + TimeDelta::days(1))});
        assert_eq!(
            render(&source, 1, 1, level(&completed, deadline).unwrap()),
            source
        );
    }
}
