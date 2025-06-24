
fn main(){
    println!("cargo:rustc-link-search=native=../../../build");
    println!("cargo:rustc-link-lib=static=omega_match_static");
}