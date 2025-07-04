#![allow(warnings)]

use libc::FILE;
use std::{
    ffi::{self, c_char},
    ptr::null,
    str::FromStr,
};
pub mod params;
pub mod results;
pub mod stats;
use crate::{
    matcher::{params::MatchParams, results::MatcherResults},
    stdout,
};
use stats::{MatchPatternStats, MatcherStats};

pub mod modifiers;
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

    pub unsafe fn omega_list_matcher_emit_header_info(
        matcher: *mut omega_list_matcher_t,
        out: *mut FILE,
    ) -> isize;

    pub unsafe fn omega_matcher_map_filename(
        filename: *const c_char,
        size: *mut usize,
        seq_pref: isize,
    ) -> *mut u8;

    pub unsafe fn omega_list_matcher_add_stats(
        matcher: *mut omega_list_matcher_t,
        stats: *mut MatcherStats,
    ) -> isize;

    pub unsafe fn omega_list_matcher_match(
        matcher: *const omega_list_matcher_t,
        stack: *const u8,
        stack_size: usize,
        no_overlap: isize,
        longest_only: isize,
        word_boundary: isize,
        word_prefix: isize,
        word_suffix: isize,
        line_start: isize,
        line_end: isize,
    ) -> *mut MatcherResults;
}

#[repr(C)]
pub struct omega_list_matcher_t;

pub struct Matcher {
    cobj: *mut omega_list_matcher_t,
    opts: params::MatchParams,
    pattern_stats: MatchPatternStats,
    matcher_stats: MatcherStats,
    config_path: std::path::PathBuf,
    map_path: std::path::PathBuf,
}
impl Matcher {
    pub fn new(
        config_path: &std::path::Path,
        map_path: &std::path::Path,
        opts: params::MatchParams,
    ) -> Self {
        // Check set Modifiers
        let config_path_c = ffi::CString::new(config_path.to_str().unwrap()).unwrap();
        let map_path_c = ffi::CString::new(map_path.to_str().unwrap()).unwrap();
        let mut stats = MatchPatternStats::new();
        unsafe {
            let matcher_cobj =
                omega_list_matcher_create(config_path_c.as_ptr(), 0, 0, 0, &mut stats);
            if (matcher_cobj.is_null()) {
                panic!("Could not create matcher");
            }
            Self {
                cobj: matcher_cobj,
                opts,
                pattern_stats: stats,
                matcher_stats: MatcherStats::new(),
                config_path: config_path.to_owned(),
                map_path: map_path.to_owned(),
            }
        }
    }

    pub fn emit_header_info(&self) {
        if self.cobj.is_null() {
            panic!("Matcher object is NULL");
        }
        unsafe {
            omega_list_matcher_emit_header_info(self.cobj, stdout);
        }
    }

    pub fn map_filename(&mut self, haystack_size: &mut usize) -> *mut u8 {
        unsafe {
            let stack = omega_matcher_map_filename(
                ffi::CString::new(self.map_path.to_str().unwrap())
                    .unwrap()
                    .as_ptr(),
                haystack_size,
                0,
            );
            if (stack.is_null()) {
                panic!("Matcher stack is NULL");
            }

            omega_list_matcher_add_stats(self.cobj, &mut self.matcher_stats);
            return stack;
        }
    }
    pub fn execute(&mut self, haystack_size: &mut usize) {
        let mut stack = self.map_filename(haystack_size);
        let results: *mut MatcherResults;
        unsafe {
            results =
                omega_list_matcher_match(self.cobj, stack, *haystack_size, 0, 0, 0, 0, 0, 0, 0);

            if (is_enabled("verbose") && !results.is_null()) {
                println!("{}", *results);
            }
        }
    }
}
pub fn get_options<'a>(opts: impl Iterator<Item = &'a str>) -> MatchParams {
    let mut builder = params::MatchParamsBuilder::from(opts);
    let ret: MatchParams = builder.into();
    ret
}
pub fn is_match_option(opt: &str) -> bool {
    match params::MatchParamsType::from_str(opt) {
        Err(_) => false,
        _ => true,
    }
}
pub fn enable_modifier(modifier: &str) {
    match modifiers::MatchModifiers::from_str(modifier) {
        Ok(mod_id) => {
            modifiers::ENABLED_MODIFIERS.enable(mod_id);
        }
        Err(msg) => panic!("{}", msg),
    }
}

pub fn is_enabled(modifier: &str) -> bool {
    match modifiers::MatchModifiers::from_str(modifier) {
        Ok(mod_id) => modifiers::ENABLED_MODIFIERS.is_enabled(mod_id),
        Err(msg) => panic!("{}", msg),
    }
}
#[cfg(test)]
mod test {

    use super::*;

    #[test]
    fn can_enable_modifier() {
        let from_cli = "--verbose";
        enable_modifier(from_cli);
        assert!(modifiers::ENABLED_MODIFIERS.is_enabled(modifiers::MatchModifiers::Verbose));
    }
}
