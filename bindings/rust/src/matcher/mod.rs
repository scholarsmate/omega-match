use libc::FILE;
use std::ffi::{self, c_char};
#[link(name = "omega_match_static", kind = "static")]
unsafe extern "C" {
    pub unsafe fn omega_list_matcher_compile_patterns_filename(
        arg1: *const c_char,
        arg2: *const c_char,
        case_insensitive: usize,
        ignore_punctuation: usize,
        elide_whitespace: usize,
        pattern_store_stats: *mut MatchPatternStats,
    ) -> isize;

    pub unsafe fn omega_list_matcher_create(
        arg1: *const c_char,
        case_insensitive: usize,
        ignore_punctuation: usize,
        elide_whitespace: usize,
        pattern_store_stats: *mut MatchPatternStats,
    ) -> *mut omega_list_matcher_t;
}

#[repr(C)]
pub struct omega_list_matcher_t;

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
