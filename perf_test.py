#!/usr/bin/env python3
"""
Performance testing script for omega_match library.

This script benchmarks the omega_match library against grep-like tools.
It automatically detects available tools:
- grep (Linux/Unix/WSL/MSYS2) - Most accurate for comparisons
- pwsh (PowerShell Core 6.x+) - Cross-platform PowerShell
- powershell (Windows PowerShell 5.x) - Windows built-in PowerShell

The script gracefully handles systems without grep by using PowerShell's
Select-String cmdlet and regex matching as an alternative for pattern matching
comparisons. PowerShell implementation generates temporary scripts to handle
complex pattern matching scenarios like line anchors and word boundaries.

Note: PowerShell comparisons may show mismatches due to different regex engines
and output formatting compared to GNU grep, but provide a functional alternative
for performance testing on Windows systems.
"""
import os
import subprocess
import time
import csv
import shutil
import argparse
from pathlib import Path

# Config
PATTERNS = "./data/names.txt"
HAYSTACK = "./data/kjv.txt"
HAYSTACK_SIZE_MB = 1024


def get_binary_paths():
    """Detect the correct binary paths for different build systems."""
    # Windows MSVC builds
    debug_candidates = [
        "./build-msvc-debug/Debug/olm.exe",
        "./cmake-build-debug/olm.exe",
        "./cmake-build-debug/olm",
    ]
    release_candidates = [
        "./build-msvc-release/Release/olm.exe",
        "./cmake-build-release/olm.exe",
        "./cmake-build-release/olm",
    ]

    debug_build = None
    release_build = None

    for candidate in debug_candidates:
        if os.path.isfile(candidate):
            debug_build = candidate
            break

    for candidate in release_candidates:
        if os.path.isfile(candidate):
            release_build = candidate
            break

    return debug_build, release_build


DEBUG_BUILD, RELEASE_BUILD = get_binary_paths()
CSV_FILE = "./perf_results.csv"
OMP_THREADS = 8
DEFAULT_COMPILED_EXT = ".olm"

# Match variants: matcher CLI flags
MATCH_VARIANTS = {
    "baseline": f"--threads {OMP_THREADS}",
    "ignore-case": f"--threads {OMP_THREADS} --ignore-case",
    "word-boundary": f"--threads {OMP_THREADS} --word-boundary",
    "word-prefix": f"--threads {OMP_THREADS} --word-prefix",
    "word-suffix": f"--threads {OMP_THREADS} --word-suffix",
    "ignore-case+word-boundary": f"--threads {OMP_THREADS} --ignore-case --word-boundary",
    "ignore-punct": f"--threads {OMP_THREADS} --ignore-punctuation",
    "ignore-case+ignore-punct": f"--threads {OMP_THREADS} --ignore-case --ignore-punctuation",
    "ignore-case+ignore-punct+word-boundary": f"--threads {OMP_THREADS} --ignore-case --ignore-punctuation --word-boundary",
    "ignore-case+ignore-punct+word-boundary+elide-whitespace": f"--threads {OMP_THREADS} --ignore-case --ignore-punctuation --elide-whitespace --word-boundary",
    "ignore-case+no-overlap+longest": f"--threads {OMP_THREADS} --ignore-case --no-overlap --longest",
    "longest": f"--threads {OMP_THREADS} --longest",
    "no-overlap": f"--threads {OMP_THREADS} --no-overlap",
    "longest+word-boundary": f"--threads {OMP_THREADS} --longest --word-boundary",
    "no-overlap+word-boundary": f"--threads {OMP_THREADS} --no-overlap --word-boundary",
    "longest+no-overlap": f"--threads {OMP_THREADS} --longest --no-overlap",
    "longest+no-overlap+word-boundary": f"--threads {OMP_THREADS} --longest --no-overlap --word-boundary",
    "line-start": f"--threads {OMP_THREADS} --line-start --longest --no-overlap",
    "line-end": f"--threads {OMP_THREADS} --line-end --longest --no-overlap",
    "line-start+line-end": f"--threads {OMP_THREADS} --line-start --line-end --longest --no-overlap",
    "line-start+word-boundary": f"--threads {OMP_THREADS} --line-start --word-boundary --longest --no-overlap",
    "line-end+word-boundary": f"--threads {OMP_THREADS} --line-end --word-boundary --longest --no-overlap",
    "line-start+ignore-case": f"--threads {OMP_THREADS} --line-start --ignore-case --longest --no-overlap",
    "line-end+ignore-case": f"--threads {OMP_THREADS} --line-end --ignore-case --longest --no-overlap",
    "line-start+line-end+word-boundary": f"--threads {OMP_THREADS} --line-start --line-end --word-boundary --longest --no-overlap",
}

# Grep variants: grep CLI flags (only when grep can simulate it)
GREP_VARIANTS = {
    "longest+no-overlap": "-F -o -b",
    "ignore-case+no-overlap+longest": "-F -o -b -i",
    "longest+no-overlap+word-boundary": "-F -o -b -w",
    "ignore-case+word-boundary": "-F -o -b -i -w",
    "line-start": "-E -o -b",
    "line-end": "-E -o -b",
    "line-start+line-end": "-E -o -b",
    "line-start+word-boundary": "-E -o -b",
    "line-end+word-boundary": "-E -o -b",
    "line-start+ignore-case": "-E -o -b -i",
    "line-end+ignore-case": "-E -o -b -i",
    "line-start+line-end+word-boundary": "-E -o -b",
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


def run_perf_test(binary, flags, show_status=False, test_name=""):
    if not binary or not os.path.isfile(binary):
        return "ERR (binary not found)"

    if show_status:
        print(
            f"[STATUS] Running {test_name} with {os.path.basename(binary)}...",
            end="",
            flush=True,
        )

    cmd = [binary, "match"] + flags.split() + [PATTERNS, HAYSTACK]
    start = time.perf_counter()
    try:
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
    except Exception as e:
        if show_status:
            print("\r" + " " * 120, end="\r", flush=True)  # Clear the status line
        print(f"[ERROR] Running {cmd}: {e}")
        return "ERR"
    elapsed = time.perf_counter() - start
    if elapsed == 0:
        return "Inf"
    mb_per_sec = HAYSTACK_SIZE_MB / elapsed

    return f"{mb_per_sec:.2f}"


def detect_grep_tool():
    """Detect available grep-like tools and return the best one."""
    # Prefer grep if available (most accurate)
    if shutil.which("grep"):
        return "grep"
    # Fall back to PowerShell variants
    elif shutil.which("pwsh"):
        return "pwsh"
    elif shutil.which("powershell"):
        return "powershell"
    return None


def build_grep_command(tool, grep_flags, pattern_file, haystack, test_name):
    """Build command for different grep-like tools."""
    if tool == "grep":
        return ["grep"] + grep_flags.split() + ["-f", pattern_file, haystack]
    elif tool in ["powershell", "pwsh"]:
        # For PowerShell, we'll use Select-String with proper flag handling
        import tempfile

        case_sensitive = "-i" not in grep_flags
        word_boundary = "word-boundary" in test_name
        line_start = "line-start" in test_name
        line_end = "line-end" in test_name

        # Create a temporary PowerShell script
        script_fd, script_path = tempfile.mkstemp(suffix=".ps1", text=True)
        try:
            with os.fdopen(script_fd, "w", encoding="utf-8") as script_file:
                # Convert relative paths to absolute paths for PowerShell
                abs_pattern_file = os.path.abspath(pattern_file).replace("\\", "\\\\")
                abs_haystack = os.path.abspath(haystack).replace("\\", "\\\\")

                script_content = f"""
# Read patterns from file
$patterns = Get-Content '{abs_pattern_file}' | Where-Object {{ $_.Trim() -ne '' }}

# Modify patterns based on test requirements
if ('{word_boundary}' -eq 'True') {{
    $patterns = $patterns | ForEach-Object {{ "\\b$_\\b" }}
}}
if ('{line_start}' -eq 'True' -and '{line_end}' -eq 'True') {{
    $patterns = $patterns | ForEach-Object {{ "^$_$" }}
}} elseif ('{line_start}' -eq 'True') {{
    $patterns = $patterns | ForEach-Object {{ "^$_" }}
}} elseif ('{line_end}' -eq 'True') {{
    $patterns = $patterns | ForEach-Object {{ "$_$" }}
}}

# Process the haystack file line by line to calculate offsets
$lineOffset = 0
$content = Get-Content '{abs_haystack}' -Raw
$lines = $content -split "`r?`n"

for ($i = 0; $i -lt $lines.Length; $i++) {{
    $line = $lines[$i]
    
    # Find matches in this line
    foreach ($pattern in $patterns) {{
        $matches = [regex]::Matches($line, $pattern, $(if ('{case_sensitive}' -eq 'True') {{ 'None' }} else {{ 'IgnoreCase' }}))
        
        foreach ($match in $matches) {{
            $offset = $lineOffset + $match.Index
            Write-Output "$offset:$($match.Value)"
        }}
    }}
    
    $lineOffset += $line.Length + 1  # +1 for newline
}}
"""
                script_file.write(script_content)

            return [tool, "-ExecutionPolicy", "Bypass", "-File", script_path]
        except Exception as e:
            if os.path.exists(script_path):
                os.unlink(script_path)
            return None
    return None


def run_grep_perf_test(grep_flags, test_name, show_status=False):
    import tempfile

    tool = detect_grep_tool()
    if not tool:
        if show_status:
            print(
                f"[WARNING] No grep-like tool found, skipping grep test for {test_name}"
            )
        return "N/A"

    if show_status:
        print(f"[STATUS] Running {test_name} with {tool}...", end="", flush=True)

    pattern_file = PATTERNS
    temp_pattern_file = None
    temp_script_file = None

    # For PowerShell, we don't need to modify the pattern file - we'll handle it in the script
    # For grep, create temporary pattern file if needed for line anchors and word boundaries
    if tool == "grep" and ("line-start" in test_name or "line-end" in test_name):
        temp_pattern_file = tempfile.NamedTemporaryFile(
            delete=False, mode="w", encoding="utf-8", suffix=".txt"
        )
        with open(PATTERNS, "r", encoding="utf-8") as pf:
            for line in pf:
                line = line.rstrip("\n")
                if test_name in [
                    "line-start+line-end",
                    "line-start+line-end+word-boundary",
                ]:
                    line = f"^{line}$"
                elif "line-start" in test_name:
                    line = f"^{line}"
                elif "line-end" in test_name:
                    line = f"{line}$"
                if "word-boundary" in test_name:
                    line = f"\\b{line}\\b"
                temp_pattern_file.write(line + "\n")
        temp_pattern_file.close()
        pattern_file = temp_pattern_file.name

    try:
        cmd = build_grep_command(tool, grep_flags, pattern_file, HAYSTACK, test_name)
        if not cmd:
            if show_status:
                print("\r" + " " * 120, end="\r", flush=True)  # Clear the status line
            return "ERR"

        # Store the script file path if PowerShell is used
        if tool in ["powershell", "pwsh"] and len(cmd) > 4:
            temp_script_file = cmd[4]  # The script file path

        start = time.perf_counter()
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        elapsed = time.perf_counter() - start

        if elapsed == 0:
            return "Inf"
        mb_per_sec = HAYSTACK_SIZE_MB / elapsed
        return f"{mb_per_sec:.2f}"

    except Exception as e:
        if show_status:
            print("\r" + " " * 120, end="\r", flush=True)  # Clear the status line
        print(f"[ERROR] Running {cmd}: {e}")
        return "ERR"
    finally:
        # Clean up temporary files
        if temp_pattern_file and os.path.exists(temp_pattern_file.name):
            os.unlink(temp_pattern_file.name)
        if temp_script_file and os.path.exists(temp_script_file):
            os.unlink(temp_script_file)


def normalize(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def compare_outputs(release_build, flags, test_name, grep_flags=None):
    # Run release build and save output
    olm_out = "olm_out.txt"
    grep_out = "grep_out.txt"
    with open(olm_out, "w", encoding="utf-8") as f:
        cmd = [release_build, "match"] + flags.split() + [PATTERNS, HAYSTACK]
        subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, check=True)

    # Run grep and save output
    if grep_flags:
        import tempfile

        tool = detect_grep_tool()
        if not tool:
            return "N/A"

        pattern_file = PATTERNS
        temp_pattern_file = None
        temp_script_file = None
        # For PowerShell, we don't need to modify the pattern file - we'll handle it in the script
        # For grep, create temporary pattern file for line anchors and word boundaries
        if tool == "grep" and ("line-start" in test_name or "line-end" in test_name):
            temp_pattern_file = tempfile.NamedTemporaryFile(
                delete=False, mode="w", encoding="utf-8", suffix=".txt"
            )
            with open(PATTERNS, "r", encoding="utf-8") as pf:
                for line in pf:
                    line = line.rstrip("\n")
                    if test_name in [
                        "line-start+line-end",
                        "line-start+line-end+word-boundary",
                    ]:
                        line = f"^{line}$"
                    elif "line-start" in test_name:
                        line = f"^{line}"
                    elif "line-end" in test_name:
                        line = f"{line}$"
                    if "word-boundary" in test_name:
                        line = f"\\b{line}\\b"
                    temp_pattern_file.write(line + "\n")
            temp_pattern_file.close()
            pattern_file = temp_pattern_file.name

        try:
            cmd = build_grep_command(
                tool, grep_flags, pattern_file, HAYSTACK, test_name
            )
            if cmd:
                # Store the script file path if PowerShell is used
                if tool in ["powershell", "pwsh"] and len(cmd) > 4:
                    temp_script_file = cmd[4]  # The script file path

                with open(grep_out, "w", encoding="utf-8") as f:
                    subprocess.run(
                        cmd, stdout=f, stderr=subprocess.DEVNULL, check=False
                    )
        finally:
            # Clean up temporary files
            if temp_pattern_file and os.path.exists(temp_pattern_file.name):
                os.unlink(temp_pattern_file.name)
            if temp_script_file and os.path.exists(temp_script_file):
                os.unlink(temp_script_file)

    # Compare outputs
    try:
        if not os.path.exists(grep_out):
            return "N/A"
        if normalize(olm_out) == normalize(grep_out):
            return "OK"
        else:
            return "MISMATCH"
    except Exception:
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
        """,
    )

    parser.add_argument(
        "--no-grep",
        action="store_true",
        help="Skip grep/grep-like tool tests and comparisons",
    )

    parser.add_argument(
        "--show-status",
        action="store_true",
        help="Show status messages indicating which tests are currently running",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    generate_haystack()

    # Show binary detection results
    if DEBUG_BUILD:
        print(f"[INFO] Debug binary: {DEBUG_BUILD}")
    else:
        print("[WARNING] Debug binary not found")

    if RELEASE_BUILD:
        print(f"[INFO] Release binary: {RELEASE_BUILD}")
    else:
        print("[WARNING] Release binary not found")

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
    if args.no_grep:
        print(f"{'Test Case':56} | {'Debug MB/s':12} | {'Release MB/s':12}")
        print("-" * 85)
    else:
        print(
            f"{'Test Case':56} | {'Debug MB/s':12} | {'Release MB/s':12} | {'Grep MB/s':12} | {'Compare':8}"
        )
        print("-" * 113)

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if args.no_grep:
            writer.writerow(["test_case", "threads", "debug_mb_s", "release_mb_s"])
        else:
            writer.writerow(
                [
                    "test_case",
                    "threads",
                    "debug_mb_s",
                    "release_mb_s",
                    "grep_mb_s",
                    "compare_status",
                ]
            )

        for test_name, flags in MATCH_VARIANTS.items():
            if args.show_status:
                # Print status for debug run
                status_msg = f"[STATUS] Running Debug {test_name} with {os.path.basename(DEBUG_BUILD) if DEBUG_BUILD else 'N/A'}..."
                print(status_msg, end="", flush=True)
            debug_result = run_perf_test(
                DEBUG_BUILD, flags, False, f"Debug {test_name}"
            )

            if args.show_status:
                # Clear and print status for release run
                print(
                    f"\r{' ' * 120}\r[STATUS] Running Release {test_name} with {os.path.basename(RELEASE_BUILD) if RELEASE_BUILD else 'N/A'}...",
                    end="",
                    flush=True,
                )
            release_result = run_perf_test(
                RELEASE_BUILD, flags, False, f"Release {test_name}"
            )

            # Clear any remaining status line before printing the table row
            if args.show_status:
                print(f"\r{' ' * 120}\r", end="", flush=True)

            if args.no_grep:
                print(f"{test_name:56} | {debug_result:12} | {release_result:12}")
                writer.writerow([test_name, OMP_THREADS, debug_result, release_result])
            else:
                grep_result = "N/A"
                cmp_status = "N/A"
                if test_name in GREP_VARIANTS and grep_tool:
                    grep_flags = GREP_VARIANTS[test_name]
                    if args.show_status:
                        print(
                            f"[STATUS] Running {test_name} with {grep_tool}...",
                            end="",
                            flush=True,
                        )
                    grep_result = run_grep_perf_test(grep_flags, test_name, False)
                    # Clear any remaining status line before comparison
                    if args.show_status:
                        print(f"\r{' ' * 120}\r", end="", flush=True)
                    cmp_status = compare_outputs(
                        RELEASE_BUILD, flags, test_name, grep_flags
                    )

                # Clear any remaining status line before printing the table row
                if args.show_status:
                    print(f"\r{' ' * 120}\r", end="", flush=True)

                print(
                    f"{test_name:56} | {debug_result:12} | {release_result:12} | {grep_result:12} | {cmp_status:8}"
                )
                writer.writerow(
                    [
                        test_name,
                        OMP_THREADS,
                        debug_result,
                        release_result,
                        grep_result,
                        cmp_status,
                    ]
                )

    # Adjust footer line based on whether grep is enabled
    if args.no_grep:
        print("-" * 85)
    else:
        print("-" * 113)

    print(f"[INFO] Performance test completed. Results saved to {CSV_FILE}.")

    # Plot if gnuplot and perf_plot.gp exist
    if shutil.which("gnuplot") and os.path.isfile("perf_plot.gp"):
        subprocess.run(["gnuplot", "perf_plot.gp"])
        print("[INFO] Performance plot saved as perf_plot.png.")


if __name__ == "__main__":
    main()
