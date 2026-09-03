#!/usr/bin/env python3
"""
Performance testing script for omega_match library.

This script benchmarks the omega_match library against grep when available.
It automatically detects if grep is available on the system for comparisons.

On systems without grep, the script will skip output comparisons and focus
on performance benchmarking only. This is common on Windows systems where
grep is not typically installed by default.

The script gracefully handles systems without grep by providing performance
metrics for omega_match while noting that output comparisons are not available.
"""
import os
import subprocess
import time
import csv
import shutil
import argparse
from pathlib import Path
from typing import Optional, List

# Config
PATTERNS = "./data/names.txt"
HAYSTACK = "./data/kjv.txt"
HAYSTACK_SIZE_MB = 1024

# When True, append --quiet to matcher invocations to suppress result output
add_quiet: bool = False


def actual_haystack_size_mb() -> float:
    """Return the physical haystack size used by the timed command."""
    return Path(HAYSTACK).stat().st_size / (1024 * 1024)


def run_and_drain_stdout(cmd: List[str], accepted_codes=(0,)) -> None:
    """Run a command and consume all output without using /dev/null.

    GNU grep detects /dev/null and may exit after its first match. A pipe that
    is fully drained preserves the complete-search behavior needed by this
    benchmark without retaining potentially large output in memory.
    """
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    assert process.stdout is not None
    while process.stdout.read(1024 * 1024):
        pass
    returncode = process.wait()
    if returncode not in accepted_codes:
        raise subprocess.CalledProcessError(returncode, cmd)


def get_binary_paths():
    """Detect the correct binary paths for different build systems.

    Returns:
        tuple[str|None, str|None, str|None]: (debug, release, release_pgo)
    """
    # CMake builds (common patterns)
    debug_candidates = [
        "./build-msvc-debug/Debug/olm.exe",
        "./build-gcc-debug/olm",
        "./build-clang-debug/olm",
        "./cmake-build-debug/olm.exe",
        "./cmake-build-debug/olm",
    ]
    release_candidates = [
        "./build-msvc-release/Release/olm.exe",
        "./build-gcc-release/olm",
        "./build-clang-release/olm",
        "./cmake-build-release/olm.exe",
        "./cmake-build-release/olm",
    ]
    # PGO "use" phase builds (naming mirrors existing build-* dirs)
    pgo_release_candidates = [
        "./build-msvc-pgo-use/Release/olm.exe",
        "./build-gcc-pgo-use/olm",
        "./build-clang-pgo-use/olm",
        # Fallbacks in case a multi-config or alt naming is used
        "./build-msvc-pgo-use/olm.exe",
    ]

    debug_build = next((c for c in debug_candidates if os.path.isfile(c)), None)
    release_build = next((c for c in release_candidates if os.path.isfile(c)), None)
    pgo_release_build = next((c for c in pgo_release_candidates if os.path.isfile(c)), None)

    return debug_build, release_build, pgo_release_build
# Cache for binary capability checks
_BINARY_QUIET_SUPPORT_CACHE: dict[str, bool] = {}

def binary_supports_quiet(binary: str) -> bool:
    """Return True if the provided olm binary supports --quiet in match mode."""
    if not binary:
        return False
    if binary in _BINARY_QUIET_SUPPORT_CACHE:
        return _BINARY_QUIET_SUPPORT_CACHE[binary]
    try:
        result = subprocess.run([binary, "match", "--help"], capture_output=True, text=True, timeout=5)
        ok = (result.returncode == 0) and ("--quiet" in result.stdout or "--quiet" in result.stderr)
        _BINARY_QUIET_SUPPORT_CACHE[binary] = ok
        return ok
    except Exception:
        _BINARY_QUIET_SUPPORT_CACHE[binary] = False
        return False


DEBUG_BUILD, RELEASE_BUILD, PGO_RELEASE_BUILD = get_binary_paths()
CSV_FILE = "./perf_results.csv"
OMP_THREADS = 8
DEFAULT_COMPILED_EXT = ".olm"

# Match variants: matcher CLI flags
MATCH_VARIANTS = {
    "baseline": f"--threads {OMP_THREADS}",
    "ignore-case": f"--threads {OMP_THREADS} --ignore-case",
    "ignore-case+ignore-punct": f"--threads {OMP_THREADS} --ignore-case --ignore-punctuation",
    "ignore-case+ignore-punct+word-boundary": f"--threads {OMP_THREADS} --ignore-case --ignore-punctuation --word-boundary",
    "ignore-case+ignore-punct+word-boundary+elide-whitespace": f"--threads {OMP_THREADS} --ignore-case --ignore-punctuation --elide-whitespace --word-boundary",
    "ignore-case+no-overlap+longest": f"--threads {OMP_THREADS} --ignore-case --no-overlap --longest",
    "ignore-case+word-boundary": f"--threads {OMP_THREADS} --ignore-case --word-boundary",#
    "ignore-punct": f"--threads {OMP_THREADS} --ignore-punctuation",
    "line-end": f"--threads {OMP_THREADS} --line-end --longest --no-overlap",
    "line-end+ignore-case": f"--threads {OMP_THREADS} --line-end --ignore-case --longest --no-overlap",
    "line-end+word-boundary": f"--threads {OMP_THREADS} --line-end --word-boundary --longest --no-overlap",
    "line-start": f"--threads {OMP_THREADS} --line-start --longest --no-overlap",
    "line-start+ignore-case": f"--threads {OMP_THREADS} --line-start --ignore-case --longest --no-overlap",
    "line-start+line-end": f"--threads {OMP_THREADS} --line-start --line-end --longest --no-overlap",
    "line-start+line-end+word-boundary": f"--threads {OMP_THREADS} --line-start --line-end --word-boundary --longest --no-overlap",
    "longest+no-overlap": f"--threads {OMP_THREADS} --longest --no-overlap",
    "longest+no-overlap+word-boundary": f"--threads {OMP_THREADS} --longest --no-overlap --word-boundary",
    "no-overlap+word-boundary": f"--threads {OMP_THREADS} --no-overlap --word-boundary",
    "word-boundary": f"--threads {OMP_THREADS} --word-boundary",
    "word-prefix": f"--threads {OMP_THREADS} --word-prefix",
    "word-suffix": f"--threads {OMP_THREADS} --word-suffix",
}

# Grep variants: grep CLI flags (only when grep can simulate it)
GREP_VARIANTS = {
    "ignore-case+no-overlap+longest": "-F -o -b -i",
    "ignore-case+word-boundary": "-F -o -b -i -w",
    "line-end": "-E -o -b",
    "line-end+ignore-case": "-E -o -b -i",
    "line-end+word-boundary": "-E -o -b",
    "line-start": "-E -o -b",
    "line-start+ignore-case": "-E -o -b -i",
    "line-start+line-end": "-E -o -b",
    "line-start+line-end+word-boundary": "-E -o -b",
    "longest+no-overlap": "-F -o -b",
    "longest+no-overlap+word-boundary": "-F -o -b -w",
}


def generate_haystack():
    if not os.path.isfile(HAYSTACK):
        print(f"[INFO] Generating {HAYSTACK_SIZE_MB}MB haystack...")
        base = "There was a Maryland mayor named Martin O'Malley who was known for leadership. "
        base_len = len(base)
        repeat_count = (HAYSTACK_SIZE_MB * 1024 * 1024) // base_len
        with open(HAYSTACK, "w", encoding="utf-8") as f:
            for _ in range(repeat_count):
                f.write(base)
        print(
            f"[INFO] Done generating haystack: {Path(HAYSTACK).stat().st_size / (1024*1024):.2f} MB"
        )


def run_perf_test(binary: Optional[str], flags: str, show_status: bool = False, test_name: str = "") -> str:
    if not binary or not os.path.isfile(binary):
        return "ERR (binary not found)"

    if show_status:
        print(
            f"[STATUS] Running {test_name} with {os.path.basename(binary)}...",
            end="",
            flush=True,
        )

    # Automatically add --quiet when grep is disabled and the binary supports it
    extra: List[str] = []
    if add_quiet and "--quiet" not in flags and binary_supports_quiet(binary):
        extra = ["--quiet"]
    cmd: List[str] = [binary, "match"] + extra + flags.split() + [PATTERNS, HAYSTACK]
    start = time.perf_counter()
    try:
        if add_quiet:
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
        else:
            run_and_drain_stdout(cmd)
    except Exception as e:
        if show_status:
            print("\r" + " " * 120, end="\r", flush=True)  # Clear the status line
        print(f"[ERROR] Running {cmd}: {e}")
        return "ERR"
    elapsed = time.perf_counter() - start
    if elapsed == 0:
        return "Inf"
    mb_per_sec = actual_haystack_size_mb() / elapsed

    return f"{mb_per_sec:.2f}"


def detect_grep_tool() -> Optional[str]:
    """Detect available grep-like tools and return the best one."""
    # Check for direct grep first (Linux/Unix/WSL)
    if shutil.which("grep"):
        return "grep"
    # Check for grep through bash (Git Bash on Windows)
    elif shutil.which("bash"):
        try:
            result = subprocess.run(
                ["bash", "-c", "grep --version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return "bash-grep"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass
    return None


def build_grep_command(tool: str, grep_flags: str, pattern_file: str, haystack: str, test_name: str) -> Optional[List[str]]:
    """Build command for different grep-like tools."""
    if tool == "grep":
        return ["grep"] + grep_flags.split() + ["-f", pattern_file, haystack]
    elif tool == "bash-grep":
        # Use bash to run grep command
        grep_cmd = "grep " + grep_flags + " -f " + pattern_file + " " + haystack
        return ["bash", "-c", grep_cmd]
    return None


def run_grep_perf_test(grep_flags: str, test_name: str, show_status: bool = False) -> str:

    tool = detect_grep_tool()
    if not tool:
        if show_status:
            print(
                f"[WARNING] No grep tool found, skipping grep test for {test_name}"
            )
        return "N/A"

    if show_status:
        print(f"[STATUS] Running {test_name} with {tool}...", end="", flush=True)

    pattern_file = PATTERNS
    temp_pattern_file = None
    
    # For grep and bash-grep, create temporary pattern file if needed for line anchors and word boundaries
    if tool in ["grep", "bash-grep"] and ("line-start" in test_name or "line-end" in test_name):
            # Create temp file in current directory so bash can access it
            import uuid
            temp_filename = f"temp_patterns_{uuid.uuid4().hex[:8]}.txt"
            with open(temp_filename, "w", encoding="utf-8", newline='\n') as temp_pattern_file:
                with open(PATTERNS, "r", encoding="utf-8") as pf:
                    for line in pf:
                        line = line.rstrip("\n\r")  # Remove both Windows and Unix line endings
                        if test_name in [
                            "line-start+line-end",
                            "line-start+line-end+word-boundary",
                        ]:
                            line = f"^{line}$"
                            # Don't add word boundaries for full line matches - they're redundant
                        elif "line-start" in test_name:
                            line = f"^{line}"
                            if "word-boundary" in test_name:
                                line = f"^\\b{line}"  # Correct: line start + word boundary
                        elif "line-end" in test_name:
                            line = f"{line}$"
                            if "word-boundary" in test_name:
                                line = f"{line}\\b$"  # Correct: word boundary + line end
                        elif "word-boundary" in test_name:
                            line = f"\\b{line}\\b"
                        temp_pattern_file.write(line + "\n")  # Use explicit Unix line ending
            pattern_file = temp_filename

    cmd: Optional[List[str]] = None
    try:
        cmd = build_grep_command(tool, grep_flags, pattern_file, HAYSTACK, test_name)
        if not cmd:
            if show_status:
                print("\r" + " " * 120, end="\r", flush=True)  # Clear the status line
            return "ERR"

        start = time.perf_counter()
        run_and_drain_stdout(cmd, accepted_codes=(0, 1))
        elapsed = time.perf_counter() - start

        if elapsed == 0:
            return "Inf"
        mb_per_sec = actual_haystack_size_mb() / elapsed
        return f"{mb_per_sec:.2f}"

    except Exception as e:
        if show_status:
            print("\r" + " " * 120, end="\r", flush=True)  # Clear the status line
        print(f"[ERROR] Running {cmd}: {e}")
        return "ERR"
    finally:
        # Clean up temporary files
        if pattern_file != PATTERNS and os.path.exists(pattern_file):
            os.unlink(pattern_file)


def normalize(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def compare_outputs(release_build: str, flags: str, test_name: str, grep_flags: Optional[str] = None) -> str:
    # Run release build and save output
    olm_out = "olm_out.txt"
    grep_out = "grep_out.txt"
    with open(olm_out, "w", encoding="utf-8") as f:
        cmd: List[str] = [release_build, "match"] + flags.split() + [PATTERNS, HAYSTACK]
        subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, check=True)

    # Run grep and save output
    if grep_flags:
        tool = detect_grep_tool()
        if not tool:
            return "N/A"

        pattern_file = PATTERNS
        
        # For grep and bash-grep, create temporary pattern file for line anchors and word boundaries
        if tool in ["grep", "bash-grep"] and ("line-start" in test_name or "line-end" in test_name):
            # Create temp file in current directory so bash can access it
            import uuid
            temp_filename = f"temp_patterns_{uuid.uuid4().hex[:8]}.txt"
            with open(temp_filename, "w", encoding="utf-8", newline='\n') as temp_pattern_file:
                with open(PATTERNS, "r", encoding="utf-8") as pf:
                    for line in pf:
                        line = line.rstrip("\n\r")  # Remove both Windows and Unix line endings
                        if test_name in [
                            "line-start+line-end",
                            "line-start+line-end+word-boundary",
                        ]:
                            line = f"^{line}$"
                            # Don't add word boundaries for full line matches - they're redundant
                        elif "line-start" in test_name:
                            line = f"^{line}"
                            if "word-boundary" in test_name:
                                line = f"\\b{line}"
                        elif "line-end" in test_name:
                            line = f"{line}$"
                            if "word-boundary" in test_name:
                                line = f"{line}\\b"
                        elif "word-boundary" in test_name:
                            line = f"\\b{line}\\b"
                        temp_pattern_file.write(line + "\n")  # Use explicit Unix line ending
            pattern_file = temp_filename

        try:
            cmd2: Optional[List[str]] = build_grep_command(
                tool, grep_flags, pattern_file, HAYSTACK, test_name
            )
            if cmd2:
                with open(grep_out, "w", encoding="utf-8") as f:
                    subprocess.run(
                        cmd2, stdout=f, stderr=subprocess.DEVNULL, check=False
                    )
        finally:
            # Clean up temporary files
            if pattern_file != PATTERNS and os.path.exists(pattern_file):
                os.unlink(pattern_file)

    # Compare outputs
    try:
        if not os.path.exists(grep_out):
            return "N/A"
        
        # Read and normalize both outputs
        olm_content = normalize(olm_out)
        grep_content = normalize(grep_out)
        
        if olm_content == grep_content:
            return "OK"
        else:
            # For debugging - save a copy with test name to inspect mismatches
            debug_olm = f"debug_olm_{test_name}.txt"
            debug_grep = f"debug_grep_{test_name}.txt"
            
            with open(debug_olm, "w", encoding="utf-8") as f:
                f.write(olm_content)
            with open(debug_grep, "w", encoding="utf-8") as f:
                f.write(grep_content)
                
            # Quick analysis of the difference
            olm_lines = olm_content.split('\n')
            grep_lines = grep_content.split('\n')
            
            print(f"[DEBUG] {test_name}: OLM lines={len(olm_lines)}, Grep lines={len(grep_lines)}")
            if len(olm_lines) > 0 and len(grep_lines) > 0:
                print(f"[DEBUG] {test_name}: First OLM line: {repr(olm_lines[0][:100])}")
                print(f"[DEBUG] {test_name}: First Grep line: {repr(grep_lines[0][:100])}")
            
            return "MISMATCH"
    except Exception as e:
        print(f"[ERROR] Comparison failed for {test_name}: {e}")
        return "MISMATCH"
    finally:
        # Clean up temporary files with retry logic
        for f in [olm_out, grep_out]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except PermissionError:
                    # File might be in use, wait a bit and try again
                    import time

                    time.sleep(0.1)
                    try:
                        os.remove(f)
                    except PermissionError:
                        pass  # If still can't remove, just continue


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Performance testing script for omega_match library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run all tests with grep comparisons
  %(prog)s --no-grep               # Run tests without grep comparisons
  %(prog)s --show-status           # Show status messages during execution
  %(prog)s --no-grep --show-status # Skip grep and show status messages
  %(prog)s --tests baseline,line-start,word-boundary  # Run only specified tests
        """,
    )

    parser.add_argument(
        "--no-grep",
        action="store_true",
        help="Skip grep/grep-like tool tests and comparisons",
    )

    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Skip running debug binary benchmarks",
    )

    parser.add_argument(
        "--release-binary",
        type=str,
        help="Explicit path to release/optimized olm binary to benchmark (overrides auto-detect)",
    )
    parser.add_argument(
        "--pgo-binary",
        type=str,
        help="Explicit path to release+PGO olm binary to benchmark (overrides auto-detect)",
    )

    parser.add_argument(
        "--debug-binary",
        type=str,
        help="Explicit path to debug olm binary to benchmark (overrides auto-detect)",
    )

    parser.add_argument(
        "--show-status",
        action="store_true",
        help="Show status messages indicating which tests are currently running",
    )

    parser.add_argument(
        "--tests",
        type=str,
        help="Comma-separated list of specific tests to run. Use 'list' to see available tests.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Handle test listing and selection
    if args.tests == "list":
        print("Available tests:")
        for test_name in MATCH_VARIANTS.keys():
            print(f"  {test_name}")
        return

    # Determine which tests to run
    if args.tests:
        selected_tests = [test.strip() for test in args.tests.split(",")]
        # Validate test names
        invalid_tests = [test for test in selected_tests if test not in MATCH_VARIANTS]
        if invalid_tests:
            print(f"[ERROR] Invalid test names: {', '.join(invalid_tests)}")
            print("Use --tests list to see available tests.")
            return
        tests_to_run = {name: flags for name, flags in MATCH_VARIANTS.items() if name in selected_tests}
        print(f"[INFO] Running {len(tests_to_run)} selected tests: {', '.join(selected_tests)}")
    else:
        tests_to_run = MATCH_VARIANTS
        print(f"[INFO] Running all {len(tests_to_run)} tests")

    # Enable --quiet when grep is disabled to minimize work in child process
    global add_quiet
    add_quiet = bool(args.no_grep)

    generate_haystack()
    print(f"[INFO] Physical haystack size: {actual_haystack_size_mb():.2f} MiB")

    # Optional binary overrides (use locals to avoid reassigning module constants)
    debug_bin = DEBUG_BUILD
    release_bin = RELEASE_BUILD
    pgo_bin = PGO_RELEASE_BUILD
    if args.release_binary:
        release_bin = args.release_binary
    if args.debug_binary is not None:
        debug_bin = args.debug_binary
    if args.pgo_binary:
        pgo_bin = args.pgo_binary

    # Show binary detection results
    if not args.no_debug:
        if debug_bin:
            print(f"[INFO] Debug binary: {debug_bin}")
        else:
            print("[WARNING] Debug binary not found")

    if release_bin:
        print(f"[INFO] Release binary: {release_bin}")
    else:
        print("[WARNING] Release binary not found")

    if pgo_bin:
        print(f"[INFO] Release+PGO binary: {pgo_bin}")
    else:
        print("[INFO] Release+PGO binary not found (optional)")

    # Detect grep tool and inform user
    if not args.no_grep:
        grep_tool = detect_grep_tool()
        if grep_tool:
            print(f"[INFO] Using `{grep_tool}` for grep comparisons")
        else:
            print(
                "[WARNING] No grep-like tool found. Grep comparisons will be skipped."
            )
    else:
        print("[INFO] Grep comparisons disabled via --no-grep")
        grep_tool = None

    print(f"[INFO] OMP threads: {OMP_THREADS}")
    if args.show_status:
        print("[INFO] Status messages enabled")
    print()

    # Adjust table headers based on whether grep is enabled
    # Dynamically build table headers depending on available binaries
    header_parts = ["Test Case"]
    if not args.no_debug:
        header_parts.append("Debug MB/s")
    header_parts.append("Release MB/s")
    if pgo_bin:
        header_parts.append("PGO MB/s")
    if args.no_grep:
        pass
    else:
        header_parts.extend(["Grep MB/s", "Ratio", "Compare"])

    # Compute total width for separator (approx)
    header_line = " | ".join(f"{h:>12}" if h != "Test Case" else f"{h:56}" for h in header_parts)
    print(header_line)
    print("-" * (len(header_line)))

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # CSV header
        csv_header = ["test_case", "threads"]
        if not args.no_debug:
            csv_header.append("debug_mb_s")
        csv_header.append("release_mb_s")
        if pgo_bin:
            csv_header.append("pgo_mb_s")
        if not args.no_grep:
            csv_header.extend(["grep_mb_s", "release_grep_ratio", "compare_status"])
        writer.writerow(csv_header)

        for test_name, flags in tests_to_run.items():
            if not args.no_debug:
                if args.show_status:
                    # Print status for debug run
                    status_msg = f"[STATUS] Running Debug {test_name} with {os.path.basename(debug_bin) if debug_bin else 'N/A'}..."
                    print(status_msg, end="", flush=True)
                debug_result = run_perf_test(
                    debug_bin, flags, False, f"Debug {test_name}"
                )
            else:
                debug_result = "N/A"

            if args.show_status:
                # Clear and print status for release run
                print(
                    f"\r{' ' * 120}\r[STATUS] Running Release {test_name} with {os.path.basename(release_bin) if release_bin else 'N/A'}...",
                    end="",
                    flush=True,
                )
            release_result = run_perf_test(
                release_bin, flags, False, f"Release {test_name}"
            )

            # Clear any remaining status line before printing the table row
            if args.show_status:
                print(f"\r{' ' * 120}\r", end="", flush=True)

            # Run PGO release build if present
            if pgo_bin:
                if args.show_status:
                    print(
                        f"\r{' ' * 120}\r[STATUS] Running PGO Release {test_name} with {os.path.basename(pgo_bin)}...",
                        end="",
                        flush=True,
                    )
                pgo_result = run_perf_test(pgo_bin, flags, False, f"PGO Release {test_name}")
            else:
                pgo_result = "N/A"

            if args.no_grep:
                row_display_parts = [f"{test_name:56}"]
                csv_row: List[object] = [test_name, OMP_THREADS]
                if not args.no_debug:
                    row_display_parts.append(f"{debug_result:12}")
                    csv_row.append(debug_result)
                row_display_parts.append(f"{release_result:12}")
                csv_row.append(release_result)
                if pgo_bin:
                    row_display_parts.append(f"{pgo_result:12}")
                    csv_row.append(pgo_result)
                print(" | ".join(row_display_parts))
                writer.writerow(csv_row)
            else:
                grep_result = "N/A"
                cmp_status = "N/A"
                if test_name in GREP_VARIANTS and grep_tool:
                    grep_flags = GREP_VARIANTS[test_name]
                    grep_result = run_grep_perf_test(grep_flags, test_name, args.show_status)
                    if args.show_status:
                        print(
                            f"\r{' ' * 120}\r[STATUS] Comparing {test_name} outputs...",
                            end="",
                            flush=True,
                        )
                    if release_bin:
                        cmp_status = compare_outputs(release_bin, flags, test_name, grep_flags)

                if args.show_status:
                    print(f"\r{' ' * 120}\r", end="", flush=True)

                # Ratio uses (non-PGO) release build for continuity
                try:
                    if grep_result not in ("N/A", "ERR", "Inf") and release_result not in ("N/A", "ERR", "Inf"):
                        release_val = float(release_result)
                        grep_val = float(grep_result)
                        ratio = release_val / grep_val if grep_val > 0 else 0
                        ratio_str = f"{ratio:.2f}x" if grep_val > 0 else "N/A"
                    else:
                        ratio = 0
                        ratio_str = "N/A"
                except (ValueError, ZeroDivisionError):
                    ratio = 0
                    ratio_str = "N/A"

                row_display_parts = [f"{test_name:56}"]
                csv_row: List[object] = [test_name, OMP_THREADS]
                if not args.no_debug:
                    row_display_parts.append(f"{debug_result:12}")
                    csv_row.append(debug_result)
                row_display_parts.append(f"{release_result:12}")
                csv_row.append(release_result)
                if pgo_bin:
                    row_display_parts.append(f"{pgo_result:12}")
                    csv_row.append(pgo_result)
                row_display_parts.extend([f"{grep_result:12}", f"{ratio_str:8}", f"{cmp_status:8}"])
                csv_row.extend([grep_result, ratio, cmp_status])
                print(" | ".join(row_display_parts))
                writer.writerow(csv_row)

    # Adjust footer line based on whether grep is enabled
    # Footer separator (reuse header length)
    print("-" * len(header_line))

    print(f"[INFO] Performance test completed. Results saved to {CSV_FILE}.")

    # Plot if gnuplot and perf_plot.gp exist
    if shutil.which("gnuplot") and os.path.isfile("perf_plot.gp"):
        subprocess.run(["gnuplot", "perf_plot.gp"])
        print("[INFO] Performance plot saved as perf_plot.png.")


if __name__ == "__main__":
    main()
