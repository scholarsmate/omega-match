# Omega-Match Library Usage in Rust

## Requirements

- Omega-Match library requirements.
- Rust (Cargo) [^1]

## Build & Execution

### Build Omega-Match

The Rust example links the static library built from the Omega-Match project.

#### Building Omega-Match

**NOTE**: The libraries CMake presets create differing build directory names. The Rust example depends upon
this build directory name for locally linking the library.

> **build.rs:3** `println!("cargo:rustc-link-search=native=../../../build");`
>
> **Cargo.toml:8** `rustflags = ["-C", "link-args=-Wl,-rpath,$ORIGIN/../../../build", "-L", "../../../build"]`

To ensure consistent linkage, the build directory name can be overridden.

Within the project root directory, build the library with a CMake preset via:

```bash
$ cmake --preset -B <build_dir>
```

The build the project via:

```bash
$ cmake --build build
```

#### Building The Rust Example

Change the directory:

```bash
$ cd examples/rust/omega-match-rust
```

### Execution

Within the `omega-match-rust` directory, execute the example with:

```bash
cargo run
```
