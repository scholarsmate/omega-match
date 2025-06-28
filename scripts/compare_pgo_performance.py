#!/usr/bin/env python3
"""
Performance comparison script for PGO vs non-PGO builds.
Compares binary sizes and execution performance across different workloads.
"""

import os
import sys
import time
import subprocess
import statistics
from pathlib import Path
from typing import List, Dict, Tuple
import argparse


def get_file_size(filepath: Path) -> int:
    """Get file size in bytes."""
    return filepath.stat().st_size if filepath.exists() else 0


def format_bytes(size: int) -> str:
    """Format bytes into human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def run_command_with_timing(cmd: List[str], runs: int = 3) -> Tuple[float, bool]:
    """Run a command multiple times and return average execution time."""
    times = []
    success = True

    for i in range(runs):
        try:
            start_time = time.perf_counter()
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            end_time = time.perf_counter()
            times.append((end_time - start_time) * 1000)  # Convert to milliseconds
        except subprocess.CalledProcessError as e:
            print(f"  Command failed on run {i+1}: {e}")
            success = False
            break

    if success and times:
        return statistics.mean(times), True
    return 0.0, False


def analyze_build_sizes(build_dirs: Dict[str, Path]) -> None:
    """Analyze and compare binary sizes."""
    print("=" * 60)
    print("BINARY SIZE ANALYSIS")
    print("=" * 60)

    size_data = {}

    for build_name, build_dir in build_dirs.items():
        exe_path = build_dir / "Release" / "olm.exe"
        static_lib_path = build_dir / "Release" / "omega_match_static.lib"
        shared_lib_path = build_dir / "Release" / "omega_match.dll"

        size_data[build_name] = {
            "exe": get_file_size(exe_path),
            "static_lib": get_file_size(static_lib_path),
            "shared_lib": get_file_size(shared_lib_path),
        }

        print(f"\n{build_name}:")
        print(f"  olm.exe: {format_bytes(size_data[build_name]['exe'])}")
        print(
            f"  omega_match_static.lib: {format_bytes(size_data[build_name]['static_lib'])}"
        )
        if size_data[build_name]["shared_lib"] > 0:
            print(
                f"  omega_match.dll: {format_bytes(size_data[build_name]['shared_lib'])}"
            )
        else:
            print(f"  omega_match.dll: Not built (expected for PGO)")

    # Compare sizes
    if len(build_dirs) >= 2:
        builds = list(build_dirs.keys())
        build1, build2 = builds[0], builds[1]

        print(f"\nSIZE COMPARISON ({build1} vs {build2}):")
        print("-" * 40)

        for binary_type in ["exe", "static_lib", "shared_lib"]:
            size1 = size_data[build1][binary_type]
            size2 = size_data[build2][binary_type]

            if size1 > 0 and size2 > 0:
                diff = size2 - size1
                percent = (diff / size1) * 100
                direction = "larger" if diff > 0 else "smaller"

                binary_name = {
                    "exe": "olm.exe",
                    "static_lib": "omega_match_static.lib",
                    "shared_lib": "omega_match.dll",
                }[binary_type]

                print(f"  {binary_name}: {diff:+,} bytes ({percent:+.1f}% {direction})")


def benchmark_performance(build_dirs: Dict[str, Path], data_dir: Path) -> None:
    """Run performance benchmarks."""
    print("\n" + "=" * 60)
    print("PERFORMANCE BENCHMARKS")
    print("=" * 60)

    # Test configurations
    test_configs = [
        {
            "name": "Small workload",
            "patterns": "small_pats.txt",
            "haystack": "small_hay.txt",
            "runs": 5,
        },
        {
            "name": "Large workload (names -> KJV)",
            "patterns": "names.txt",
            "haystack": "kjv.txt",
            "runs": 3,
        },
    ]

    results = {}

    for config in test_configs:
        print(f"\n{config['name']}:")
        print(f"  Patterns: {config['patterns']}")
        print(f"  Haystack: {config['haystack']}")
        print("-" * 40)

        patterns_file = data_dir / config["patterns"]
        haystack_file = data_dir / config["haystack"]

        if not patterns_file.exists() or not haystack_file.exists():
            print(f"  Skipping - missing files")
            continue

        config_results = {}

        for build_name, build_dir in build_dirs.items():
            exe_path = build_dir / "Release" / "olm.exe"

            if not exe_path.exists():
                print(f"  {build_name}: Executable not found")
                continue

            # Test compile phase - create safe filename
            safe_build_name = build_name.replace(" ", "_").replace("-", "_")
            safe_config_name = (
                config["name"]
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .replace("->", "_to_")
            )
            compile_output = f"test_{safe_build_name}_{safe_config_name}.olm"
            compile_cmd = [str(exe_path), "compile", compile_output, str(patterns_file)]

            print(f"  {build_name} - Compile: ", end="", flush=True)
            compile_time, compile_success = run_command_with_timing(
                compile_cmd, config["runs"]
            )

            if not compile_success:
                print("FAILED")
                continue

            print(f"{compile_time:.1f} ms")

            # Test match phase
            match_cmd = [str(exe_path), "match", compile_output, str(haystack_file)]

            print(f"  {build_name} - Match: ", end="", flush=True)
            match_time, match_success = run_command_with_timing(
                match_cmd, config["runs"]
            )

            if not match_success:
                print("FAILED")
                continue

            print(f"{match_time:.1f} ms")

            total_time = compile_time + match_time
            config_results[build_name] = {
                "compile": compile_time,
                "match": match_time,
                "total": total_time,
            }

            # Clean up
            try:
                os.remove(compile_output)
            except:
                pass

        results[config["name"]] = config_results

        # Compare performance for this config
        if len(config_results) >= 2:
            builds = list(config_results.keys())
            build1, build2 = builds[0], builds[1]

            print(f"\n  Performance comparison ({build1} vs {build2}):")
            for phase in ["compile", "match", "total"]:
                time1 = config_results[build1][phase]
                time2 = config_results[build2][phase]

                if time1 > 0 and time2 > 0:
                    speedup = time1 / time2
                    if speedup > 1:
                        print(
                            f"    {phase.capitalize()}: {speedup:.2f}x faster ({((speedup-1)*100):.1f}% improvement)"
                        )
                    else:
                        print(
                            f"    {phase.capitalize()}: {(1/speedup):.2f}x slower ({((1-speedup)*100):.1f}% regression)"
                        )


def main():
    parser = argparse.ArgumentParser(
        description="Compare PGO vs non-PGO build performance"
    )
    parser.add_argument(
        "--msvc-only", action="store_true", help="Only compare MSVC builds"
    )
    parser.add_argument(
        "--all-compilers", action="store_true", help="Compare all available compilers"
    )
    args = parser.parse_args()

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data"

    if not data_dir.exists():
        print(f"Error: Data directory not found at {data_dir}")
        sys.exit(1)

    # Define build directories to compare
    build_dirs = {}

    if args.msvc_only or not args.all_compilers:
        # MSVC comparison (default)
        msvc_release = project_root / "build-msvc-release"
        msvc_pgo = project_root / "build-msvc-pgo-use"

        if msvc_release.exists():
            build_dirs["MSVC Release"] = msvc_release
        if msvc_pgo.exists():
            build_dirs["MSVC PGO"] = msvc_pgo

    if args.all_compilers:
        # Add all available builds
        all_builds = {
            "GCC Release": "build-gcc-release",
            "GCC PGO": "build-gcc-pgo-use",
            "Clang PGO": "build-clang-pgo-use",
            "MSVC Release": "build-msvc-release",
            "MSVC PGO": "build-msvc-pgo-use",
        }

        for name, dir_name in all_builds.items():
            build_path = project_root / dir_name
            if build_path.exists():
                build_dirs[name] = build_path

    if not build_dirs:
        print("Error: No build directories found!")
        print("Available directories:")
        for item in project_root.iterdir():
            if item.is_dir() and item.name.startswith("build-"):
                print(f"  {item.name}")
        sys.exit(1)

    print("OMEGA MATCH - PGO PERFORMANCE COMPARISON")
    print("=" * 60)
    print(f"Comparing builds: {', '.join(build_dirs.keys())}")

    # Run analysis
    analyze_build_sizes(build_dirs)
    benchmark_performance(build_dirs, data_dir)

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
