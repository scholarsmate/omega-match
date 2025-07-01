use std::fmt::Display;

pub struct CompilerPatterns {
    patterns: Vec<String>,
}
impl CompilerPatterns {
    pub fn new() -> Self {
        Self {
            patterns: Vec::new(),
        }
    }
    pub fn add_pattern(&mut self, pattern: &str) {
        self.patterns.push(pattern.to_string());
    }
}
impl From<Vec<String>> for CompilerPatterns {
    fn from(value: Vec<String>) -> Self {
        Self { patterns: value }
    }
}
impl From<Vec<&str>> for CompilerPatterns {
    fn from(value: Vec<&str>) -> Self {
        let mut patterns: Vec<String> = Vec::new();
        for pattern in value {
            patterns.push(pattern.to_string());
        }
        Self { patterns: patterns }
    }
}

impl Display for CompilerPatterns {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        for pattern in &self.patterns {
            write!(f, "{}\n", &pattern)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn retains_patterns_for_compilation() {
        let mut compiler = CompilerPatterns::new();
        compiler.add_pattern("foo");
        assert_eq!(compiler.patterns.len(), 1);
    }

    #[test]
    fn can_create_patterns_from_vector() {
        let patterns = vec!["foo", "bar"];
        let compiler = CompilerPatterns::from(patterns);
        assert_eq!(compiler.patterns.len(), 2);
    }

    #[test]
    fn can_write_patterns_to_formatter() {
        let patterns = vec!["foo", "bar"];
        let compiler = CompilerPatterns::from(patterns);
        let output = format!("{}", compiler);

        assert_eq!(output, "foo\nbar\n");
    }
}
