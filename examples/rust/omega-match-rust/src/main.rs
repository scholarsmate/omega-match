
use std::ffi::CStr;
use std::os::raw::c_char;

#[link(name = "omega_match_static")]
unsafe extern "C" {
    unsafe fn omega_match_version() -> *const c_char;
}

fn main() {
    let ver_ptr= unsafe { omega_match_version() };
    if ver_ptr.is_null() {
        panic!("Version is nullptr!");
    }

    let verc_str = unsafe { CStr::from_ptr(ver_ptr) };
    let ver_rust_str = verc_str.to_str().expect("Invalid format");
    println!("Version: {}", ver_rust_str);
}
