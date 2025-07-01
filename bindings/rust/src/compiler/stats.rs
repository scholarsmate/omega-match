use std::fmt::Display;

pub struct CompilerStats {
    total_input_bytes: u64,
    total_stored_bytes: u64,
    stored_pattern_count: u32,
    short_pattern_count: u32,
    duplicate_patterns: u32,
    smallest_pattern_length: u32,
    largest_pattern_length: u32,
}

impl CompilerStats {
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

impl Display for CompilerStats {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "\
        Bytes:
            - input:  {}
            - stored: {}
        Patterns:
            - stored: {}
            - short:  {}
            - duplicates: {}
            - smallest length: {}
            - largest length:  {}
        ",
            self.total_input_bytes,
            self.total_stored_bytes,
            self.short_pattern_count,
            self.short_pattern_count,
            self.duplicate_patterns,
            self.smallest_pattern_length,
            self.largest_pattern_length
        )
    }
}
