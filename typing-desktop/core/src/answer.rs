//! Answer normalization; keep identical to `srs.normalize_answer`.

/// Python `str.isspace()` (used by `\s`) also treats U+001C..U+001F as whitespace.
fn is_py_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// Keep ASCII letters, whitespace, `'` and `-`; collapse whitespace; trim; lowercase.
pub fn normalize_answer(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    let mut pending_space = false;
    for c in value.chars() {
        if is_py_space(c) {
            pending_space = true;
        } else if c.is_ascii_alphabetic() || c == '\'' || c == '-' {
            if pending_space && !out.is_empty() {
                out.push(' ');
            }
            pending_space = false;
            out.push(c.to_ascii_lowercase());
        }
    }
    out
}

/// Acceptable answers: `/`-separated alternatives, normalized, empty ones dropped.
pub fn answer_candidates(word: &str) -> Vec<String> {
    word.split('/').map(normalize_answer).filter(|v| !v.is_empty()).collect()
}

pub fn is_correct(word: &str, input: &str) -> bool {
    let normalized = normalize_answer(input);
    !normalized.is_empty() && answer_candidates(word).contains(&normalized)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn removed_characters_do_not_split_words() {
        // "ice  café cream" -> filter drops é, whitespace collapses afterwards.
        assert_eq!(normalize_answer(" ice \u{3000} caf\u{e9}  cream "), "ice caf cream");
        assert_eq!(normalize_answer("a\u{1f}b"), "a b");
        assert_eq!(normalize_answer("1 2"), "");
    }
}
