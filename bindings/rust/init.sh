#!/bin/bash

cd ../..

cmake --preset debug -Bbuild_rlib && cmake --build build_rlib

echo "\n[ROLM]: Installing static OLM library to Rust library..."

mkdir -p bindings/rust/lib

cp build_rlib/libomega_match_static.a bindings/rust/lib  