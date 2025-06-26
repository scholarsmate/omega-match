use std::ffi::CStr;
use std::os::raw::c_char;
pub mod dispatch;

#[link(name = "omega_match_static", kind="static")]
unsafe extern "C" {
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