use std::fmt::Display;

pub struct MatchResults {
    offset: usize,
    length: u32,
    match_ptr: *const u8,
}

pub struct MatcherResults {
    count: usize,
    result: MatchResults,
}

impl Display for MatcherResults {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "\
Match Results:
  Count: {}
        Offset: {},
        Length: {}
",
            self.count, self.result.offset, self.result.length
        );
        Ok(())
    }
}
