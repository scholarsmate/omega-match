use libc::FILE;

unsafe extern "C" {
    pub unsafe static mut stdout: *mut FILE;
}
