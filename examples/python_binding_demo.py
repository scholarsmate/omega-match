#!/usr/bin/env python3
"""
Example Python binding using ctypes to call omega_match library.
This demonstrates how to use the library for language bindings.

Prerequisites:
    cmake --preset release -DOMEGA_MATCH_BUILD_CLI=OFF
    cmake --build --preset release  
    cmake --install cmake-build-release --prefix /usr/local
"""

import ctypes
import ctypes.util
import os

def find_local_omega_match_library():
    dirs = []
    pwd = os.getcwd()
    buildDir = ''
    
    if pwd.endswith('omega-match'):
        dirs = os.listdir('.')
        
        for dir in dirs:
            if(dir.find('build') >= 0):
                buildDir = dir
        
    elif pwd.endswith('examples'):
        dirs = os.listdir('..')
        
        for dir in dirs:
            if(dir.find('build') >= 0):
                buildDir = "../" + dir
    
    if(os.path.exists(buildDir + "/libomega_match.so")):
        return buildDir + "/libomega_match.so"

    print("Could not locally resolve libomega_match.so. Please build the library.")
    exit()
        
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
    
    # Try local library search
    lib_path = find_local_omega_match_library()
    if lib_path:
        return lib_path
    
    raise FileNotFoundError("Could not find libomega_match.so. Please ensure it's installed.")

def main():
    # Load the library
    lib_path = find_omega_match_library()
    print(f"Loading library using ctypes from: {lib_path}\n")
    omega_match = ctypes.CDLL(lib_path)
    
    # Print the version
    try:
        omega_match.omega_match_version.restype = ctypes.c_char_p
        version = omega_match.omega_match_version().decode('utf-8')
        print(f"⭐ Omega Match Version: {version}\n")
    except AttributeError:
        print("Version function 'omega_match_version' not found in the library.\n")

    # Example: Get version (if such function exists)
    # This is just a demonstration - you'd need to check the actual C API
    print("✅ Successfully loaded omega_match library!")
    print("✅ Ready for pattern matching operations.\n")
    
    # For actual usage, you'd need to:
    # 1. Define ctypes function signatures matching the C API
    # 2. Create pattern store from patterns
    # 3. Perform matching operations
    # 4. Handle results
    
    print("📋 To implement full bindings:")
    print("   1. Review include/omega_match/list_matcher.h for the C API")
    print("   2. Define ctypes function prototypes")
    print("   3. Implement Python wrapper functions")
    print("   4. Handle memory management properly")

if __name__ == "__main__":
    main()
