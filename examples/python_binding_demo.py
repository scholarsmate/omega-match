#!/usr/bin/env python3
"""
Example Python binding using ctypes to call omega_matchmatch library.
This demonstrates how to use the library for language bindings.

Prerequisites:
    cmake --preset release -Domega_match_BUILD_CLI=OFF
    cmake --build --preset release  
    cmake --install cmake-build-release --prefix /usr/local
"""

import ctypes
import ctypes.util
import os

def find_omega_match_library():
    """Find the omega_matchmatch shared library."""
    # Try common locations
    locations = [
        "/usr/local/lib/libomega_match.so",
        "/usr/lib/libomega_match.so", 
        "./build-gcc-release/libomega_match.so",
        "./libomega_match.so",
        "../build-gcc-release/libomega_match.so",
        "../libomega_match.so"
    ]
    
    for location in locations:
        if os.path.exists(location):
            return location
    
    # Try system library search
    lib_path = ctypes.util.find_library("omega_match")
    if lib_path:
        return lib_path
        
    raise FileNotFoundError("Could not find libomega_match.so. Please ensure it's installed.")

def main():
    # Load the library
    lib_path = find_omega_match_library()
    print(f"Loading library from: {lib_path}")
    omega_match = ctypes.CDLL(lib_path)
    
    # Example: Get version (if such function exists)
    # This is just a demonstration - you'd need to check the actual C API
    print("✅ Successfully loaded omega_matchmatch library!")
    print("✅ Ready for pattern matching operations.")
    
    # For actual usage, you'd need to:
    # 1. Define ctypes function signatures matching the C API
    # 2. Create pattern store from patterns
    # 3. Perform matching operations
    # 4. Handle results
    
    print("\nTo implement full bindings:")
    print("1. Review include/omega_match/list_matcher.h for the C API")
    print("2. Define ctypes function prototypes")
    print("3. Implement Python wrapper functions")
    print("4. Handle memory management properly")

if __name__ == "__main__":
    main()
