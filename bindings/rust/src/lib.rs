use std::ffi;
use std::file;
use std::os::fd::AsRawFd;
use std::os::raw::c_char;
use std::{ffi::CStr, rc::Rc};

pub mod config;
use config::{modes, modifiers};
use libc::FILE;

pub mod matcher;
#[link(name = "omega_match_static", kind = "static")]
unsafe extern "C" {
    unsafe static stdout: *mut FILE;
    unsafe fn omega_match_version() -> *const c_char;
}

/// Returns the version string from the omega-match C library
pub fn version() -> String {
    unsafe {
        let ptr = omega_match_version();
        if ptr.is_null() {
            return "<null>".to_string();
        }

        let c_str = CStr::from_ptr(ptr);
        c_str.to_string_lossy().into_owned()
    }
}
pub struct ProgramArgs {
    pub app_mode: modes::AppModes,
    pub mode_idx: i8,
    modifiers: Vec<Rc<Box<dyn modifiers::IsModifier>>>,
}
impl ProgramArgs {
    pub fn new(mode: modes::AppModes) -> Self {
        Self {
            app_mode: mode,
            mode_idx: -1,
            modifiers: Vec::new(),
        }
    }
    pub fn add_modifiers(&mut self, modifier: Box<dyn modifiers::IsModifier>) {
        self.modifiers.push(Rc::new(modifier));
    }
    pub fn get_modifier(&self, id: &str) -> Result<Rc<Box<dyn modifiers::IsModifier>>, &str> {
        match self
            .modifiers
            .iter()
            .by_ref()
            .find(|modifier| return modifier.id() == id)
        {
            Some(found) => Ok(found.to_owned()),
            None => Err("Modifier not found"),
        }
    }
}

pub fn match_compile_patterns(
    arg1: &std::path::Path,
    arg2: &std::path::Path,
    prog_args: &ProgramArgs,
) -> Result<isize, &'static str> {
    let mut a1 = ffi::CString::new(arg1.to_str().unwrap()).unwrap();
    let mut a2 = ffi::CString::new(arg2.to_str().unwrap()).unwrap();
    let mut stats = matcher::MatchPatternStats::new();
    unsafe {
        let ret = matcher::omega_list_matcher_compile_patterns_filename(
            a1.as_ptr(),
            a2.as_ptr(),
            0,
            0,
            0,
            &mut stats,
        );
        if ret < 0 {
            return Err("Returned -1");
        }
        Ok(ret)
    }
}
pub fn create_matcher(
    filepath: &std::path::Path,
) -> Result<matcher::omega_list_matcher_t, &'static str> {
    let mut f_str = ffi::CString::new(filepath.to_str().unwrap()).unwrap();
    let mut stats = matcher::MatchPatternStats::new();
    unsafe {
        let matcher_ptr = matcher::omega_list_matcher_create(f_str.as_ptr(), 0, 0, 0, &mut stats);
        if (matcher_ptr.is_null()) {
            return Err("Coulnd't create matcher object");
        }
        println!("{}", &stats.to_string());
        Ok(matcher::omega_list_matcher_t)
    }
}
#[cfg(test)]
mod test {
    use std::str::FromStr;

    use super::*;

    #[test]
    fn create_args_with_valid_mode() {
        let mode = modes::AppModes::from_str("match").unwrap();
        let args = ProgramArgs::new(mode);

        assert_eq!(args.app_mode.to_string(), "match");
    }

    #[test]
    fn can_add_single_modifiers() {
        let mode = modes::AppModes::from_str("match").unwrap();
        let mut args = ProgramArgs::new(mode);

        args.add_modifiers(Box::new(modifiers::VerboseModifier {}));

        assert!(args.get_modifier("verbose").is_ok());
    }
    #[test]
    fn can_add_multiple_modifiers() {
        let mode = modes::AppModes::from_str("match").unwrap();
        let mut args = ProgramArgs::new(mode);

        args.add_modifiers(Box::new(modifiers::VerboseModifier {}));
        args.add_modifiers(Box::new(modifiers::IgnoreCaseModifier {}));
        assert_eq!(args.modifiers.len(), 2);
        assert!(args.get_modifier("ignore-case").is_ok());
    }
}
