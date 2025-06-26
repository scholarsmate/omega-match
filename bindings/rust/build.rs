use std::path::Path;

fn main() {
    let lib_path = Path::new("lib").canonicalize().unwrap();
    println!("cargo:rustc-link-search=native={}", lib_path.display());
    println!("cargo:rustc-link-lib=static=omega_match_static");

    println!("cargo:rerun-if-changed={}", lib_path.join("libomega_match.a").display());
}