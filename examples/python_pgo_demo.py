#!/usr/bin/env python3
"""
Example demonstrating OmegaMatch Python bindings with automatic PGO variant selection.

This script shows how the Python bindings automatically select the best available
PGO-optimized library variant for maximum performance.
"""

import omega_match
import time
import platform

def main():
    print("🚀 OmegaMatch Python Bindings - PGO Variant Demo")
    print("=" * 55)
    
    # Show platform information
    print(f"Python Platform: {platform.platform()}")
    print(f"Architecture: {platform.machine()}")
    print()
    
    # Show library information  
    print("📚 Library Information:")
    info = omega_match.get_library_info()
    for key, value in info.items():
        print(f"  {key.capitalize()}: {value}")
    print()
    
    # Show version
    print(f"📦 OmegaMatch Version: {omega_match.get_version()}")
    print()
    
    # Explain PGO benefits
    if "pgo" in info['variant'].lower():
        print("✨ Using PGO-optimized variant!")
        print("   Benefits:")
        print("   • 5-20% faster pattern matching")
        print("   • Optimized for real-world workloads")
        print("   • Better branch prediction and caching")
    else:
        print("📊 Using standard variant")
        print("   For maximum performance, download PGO variants from:")
        print("   https://github.com/scholarsmate/omega-match/releases")
    print()
    
    # Demonstrate pattern matching
    print("🔍 Pattern Matching Demo:")
    
    # Create some test patterns
    patterns = ["hello", "world", "python", "performance", "optimization"]
    
    # Compile patterns
    print("  Compiling patterns...")
    start_time = time.perf_counter()
    
    with omega_match.Compiler("demo.olm", case_insensitive=True) as compiler:
        for pattern in patterns:
            compiler.add_pattern(pattern.encode())
        stats = compiler.get_stats()
    
    compile_time = time.perf_counter() - start_time
    print(f"  ✓ Compiled {stats.stored_pattern_count + stats.short_pattern_count} patterns in {compile_time:.4f}s")
    
    # Create test haystack
    haystack = b"""
    Hello world! This is a demonstration of Python pattern matching
    with high performance optimization using PGO (Profile Guided Optimization).
    Python developers can now enjoy blazing fast pattern matching
    with automatic performance optimizations.
    """
    
    # Perform matching
    print("  Searching for patterns...")
    start_time = time.perf_counter()
    
    with omega_match.Matcher("demo.olm", case_insensitive=True) as matcher:
        # Configure for optimal performance
        matcher.set_threads(4)
        matcher.set_chunk_size(1024)
        
        results = matcher.match(haystack,
                               no_overlap=True,
                               longest_only=True,
                               word_boundary=True)
        
        match_stats = matcher.get_match_stats()
    
    match_time = time.perf_counter() - start_time
    print(f"  ✓ Found {len(results)} matches in {match_time:.4f}s")
    
    # Show results
    if results:
        print("  📋 Matches found:")
        for result in results:
            match_text = result.match.decode()
            print(f"    • '{match_text}' at offset {result.offset}")
    
    print()
    print("📊 Match Statistics:")
    print(f"  Total attempts: {match_stats.total_attempts}")
    print(f"  Total hits: {match_stats.total_hits}")
    print(f"  Hit rate: {match_stats.total_hits/max(match_stats.total_attempts, 1):.2%}")
    
    print()
    print("💡 Performance Tips:")
    if "pgo" in info['variant'].lower():
        print("  ✓ Already using PGO optimization!")
    else:
        print("  • Install PGO variants for 5-20% better performance")
        print("  • Use 'python scripts/select_pgo_variant.py' to find best variant")
    print("  • Adjust thread count with matcher.set_threads()")
    print("  • Tune chunk size with matcher.set_chunk_size()")
    print("  • Use word_boundary=True for cleaner matches")
    
    # Clean up
    import os
    try:
        os.remove("demo.olm")
    except:
        pass
    
    print()
    print("🎉 Demo complete! OmegaMatch is ready for high-performance pattern matching.")

if __name__ == "__main__":
    main()
