use std::{
    ffi::{CString, c_char},
    fmt::Display,
    path::{Path, PathBuf},
};

use crate::compiler::{patterns::CompilerPatterns, stats::CompilerStats};
pub mod patterns;
pub mod stats;

#[link(name = "omega_match_static", kind = "static")]
unsafe extern "C" {
    pub unsafe fn omega_list_matcher_compile_patterns_filename(
        match_file: *const c_char,
        patterns_file: *const c_char,
        case_insensitive: isize,
        ignore_punctuation: isize,
        elide_whitespace: isize,
        pattern_stats: *mut stats::CompilerStats,
    ) -> isize;
}

pub enum CompilerOptions {
    CaseInsensitive,
    IgnorePunctionation,
    ElideWhitespace,
}
static COMPILE_OPT_COUNT: usize = 3;

pub struct Compiler {
    opts: [bool; COMPILE_OPT_COUNT],
    patterns: CompilerPatterns,
    stats: CompilerStats,
}

impl Compiler {
    pub fn new() -> Self {
        Self {
            opts: [false; COMPILE_OPT_COUNT],
            patterns: CompilerPatterns::new(),
            stats: CompilerStats::new(),
        }
    }
    pub fn set(&mut self, opt: CompilerOptions) -> &mut Self {
        self.opts[opt as usize] = true;
        self
    }
    pub fn is_set(&self, opt: CompilerOptions) -> bool {
        self.opts[opt as usize]
    }
    pub fn get_opts_as_params(&self) -> [isize; COMPILE_OPT_COUNT] {
        let mut ret: [isize; COMPILE_OPT_COUNT] = [0; COMPILE_OPT_COUNT];
        for (index, opt) in self.opts.iter().enumerate() {
            ret[index] = *opt as isize;
        }
        return ret;
    }
}
#[derive(Debug, Default)]
pub struct OLMCompilerError(String);
impl Display for OLMCompilerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(f, "[Rust OLM] ERR: {}", self.0)
    }
}
impl From<String> for OLMCompilerError {
    fn from(value: String) -> Self {
        Self(format!("[Rust OLM] Err: {}", value))
    }
}
impl std::error::Error for OLMCompilerError {}

pub fn compile_patterns_filename(
    compiler: &mut Compiler,
    match_file: &Path,
    patterns_file: &Path,
) -> Result<(), OLMCompilerError> {
    let [case_insensetive, ignore_punc, elide_wht] = compiler.get_opts_as_params();
    let match_file_ptr = CString::new(match_file.to_str().unwrap())
        .map_err(|e| -> OLMCompilerError { OLMCompilerError(format!("{}", e)) })?;
    let pattern_file_ptr = CString::new(patterns_file.to_str().unwrap())
        .map_err(|e| -> OLMCompilerError { OLMCompilerError(format!("{}", e)) })?;

    unsafe {
        if omega_list_matcher_compile_patterns_filename(
            match_file_ptr.as_ptr(),
            pattern_file_ptr.as_ptr(),
            case_insensetive,
            ignore_punc,
            elide_wht,
            &mut compiler.stats,
        ) != 0
        {
            return Err(OLMCompilerError(
                "Failed to compile from filename".to_string(),
            ));
        }
    }
    Ok(())
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn can_chain_set_compile_opts() {
        let mut compiler = Compiler::new();
        compiler
            .set(CompilerOptions::CaseInsensitive)
            .set(CompilerOptions::ElideWhitespace);
        assert!(compiler.is_set(CompilerOptions::CaseInsensitive));
        assert!(compiler.is_set(CompilerOptions::ElideWhitespace));
    }

    #[test]
    fn can_convert_opts_to_ints() {
        let mut compiler = Compiler::new();
        compiler
            .set(CompilerOptions::CaseInsensitive)
            .set(CompilerOptions::ElideWhitespace);
        let [noncase, ignore, ewht] = compiler.get_opts_as_params();
        assert_eq!(noncase, 1);
        assert_eq!(ignore, 0);
        assert_eq!(ewht, 1);
    }

    #[test]
    fn populates_stats_upon_compilation() {
        let mut compiler = Compiler::new();
        let patterns_filepath = Path::new("../../data/names.txt");
        let match_filepath = Path::new("/tmp/output.olm");

        compile_patterns_filename(&mut compiler, match_filepath, patterns_filepath);

        println!("{}", &compiler.stats)
    }
}
