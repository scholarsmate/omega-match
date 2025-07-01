use std::fmt::Display;

#[repr(C)]
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct MatchPatternStats {
    total_input_bytes: u64,
    total_stored_bytes: u64,
    stored_pattern_count: u32,
    short_pattern_count: u32,
    duplicate_patterns: u32,
    smallest_pattern_length: u32,
    largest_pattern_length: u32,
}
impl MatchPatternStats {
    pub fn new() -> Self {
        Self {
            total_input_bytes: 0,
            total_stored_bytes: 0,
            stored_pattern_count: 0,
            short_pattern_count: 0,
            duplicate_patterns: 0,
            smallest_pattern_length: 0,
            largest_pattern_length: 0,
        }
    }
}

impl ToString for MatchPatternStats {
    fn to_string(&self) -> String {
        format!(
            "\
  Stored pattern count: {}
  Smallest: {},
  Largest:  {},
  Duplicates:   {},
  Removed:  ---
  Input Bytes:  {},
  Stored Bytes: {},
  Ratio:    {}
",
            self.stored_pattern_count,
            self.smallest_pattern_length,
            self.largest_pattern_length,
            self.duplicate_patterns,
            self.total_input_bytes,
            self.total_stored_bytes,
            (self.total_stored_bytes / self.total_input_bytes)
        )
    }
}

pub struct MatcherStats {
    total_hits: u64,
    total_misses: u64,
    total_filtered: u64,
    total_attempts: u64,
    total_comparisons: u64,
}
impl MatcherStats {
    pub fn new() -> Self {
        Self {
            total_hits: 0,
            total_misses: 0,
            total_filtered: 0,
            total_attempts: 0,
            total_comparisons: 0,
        }
    }
}
impl Display for MatcherStats {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "\
Match Stats:
  Attempts: {},
  Filtered: {},
  Misses:   {},
  Hits:     {},
  Compares: {}
",
            self.total_attempts,
            self.total_filtered,
            self.total_misses,
            self.total_hits,
            self.total_comparisons
        );
        Ok(())
    }
}
