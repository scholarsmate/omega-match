#!/usr/bin/env python3
"""
Unified Cross-Platform PGO (Profile Guided Optimization) Workflow Script

This script automates the complete PGO process for all supported compilers and platforms:
- GCC (Linux/WSL)
- Clang (Linux/WSL/macOS)
- MSVC (Windows)

Features:
- Comprehensive training workloads for maximum optimization
- Cross-platform compatibility (Windows, Linux, macOS, WSL)
- Support for all major compilers
- Enhanced error handling and progress reporting
- CI/CD friendly operation

Usage:
    python pgo_workflow.py --compiler gcc
    python pgo_workflow.py --compiler clang
    python pgo_workflow.py --compiler msvc
    python pgo_workflow.py --compiler gcc --build-only    # Only build, skip training
    python pgo_workflow.py --compiler clang --clean       # Clean before building
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict


def detect_platform():
    """Detect the current platform and environment."""
    system = platform.system().lower()

    # Check for WSL
    if system == "linux":
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    return "wsl"
        except:
            pass
        return "linux"
    elif system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    else:
        return "unknown"


def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    if cwd:
        print(f"  Working directory: {cwd}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="ignore",
        )

        if result.stdout.strip():
            print("STDOUT:", result.stdout.strip())
        if result.stderr.strip():
            print("STDERR:", result.stderr.strip())

        if check and result.returncode != 0:
            print(f"Command failed with return code {result.returncode}")
            if not timeout:  # Don't exit on timeout failures
                sys.exit(1)

        return result
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds")
        if check:
            sys.exit(1)
        return subprocess.CompletedProcess(cmd, -1, "", "Timeout")
    except Exception as e:
        print(f"Command execution error: {e}")
        if check:
            sys.exit(1)
        return subprocess.CompletedProcess(cmd, -1, "", str(e))


def find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root (CMakeLists.txt not found)")


def check_compiler_availability(compiler: str, platform_name: str) -> None:
    """Check if the specified compiler is available."""
    try:
        if compiler == "msvc":
            # For MSVC, check if we can run cmake with Visual Studio generator
            run_command(["cmake", "--help"], check=False)
        else:
            run_command([compiler, "--version"])
        print(f"Compiler {compiler} is available")
    except FileNotFoundError:
        print(f"Error: {compiler} not found. Please install it first.")
        if compiler == "msvc" and platform_name != "windows":
            print("Note: MSVC is only available on Windows")
        sys.exit(1)


def clean_build_directories(project_root: Path, compiler: str) -> None:
    """Clean build directories for the given compiler."""
    dirs_to_clean = [f"build-{compiler}-pgo-generate", f"build-{compiler}-pgo-use"]

    for dir_name in dirs_to_clean:
        build_dir = project_root / dir_name
        if build_dir.exists():
            print(f"Cleaning {build_dir}")
            shutil.rmtree(build_dir)


def copy_pgort_dll_to_output(build_dir: Path) -> None:
    """Ensure pgort140.dll is present in the given build output directory (for MSVC PGO)."""
    if platform.system().lower() != "windows":
        return
    output_dir = build_dir / "Release"
    dll_name = "pgort140.dll"
    # Check if already present
    if (output_dir / dll_name).exists():
        return
    # Try to find VCToolsInstallDir from environment
    vc_tools_dir = os.environ.get("VCToolsInstallDir")
    candidate_paths = []
    if vc_tools_dir:
        candidate_paths.append(
            Path(vc_tools_dir) / "bin" / "Hostx64" / "x64" / dll_name
        )
        candidate_paths.append(Path(vc_tools_dir) / "bin" / dll_name)
    # Also try common install locations
    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vs_base = Path(program_files) / "Microsoft Visual Studio"
    for year in ["2022", "2019", "2017"]:
        for edition in ["Enterprise", "Professional", "Community", "BuildTools"]:
            candidate = vs_base / year / edition / "VC" / "Tools" / "MSVC"
            if candidate.exists():
                for subdir in candidate.iterdir():
                    cand = subdir / "bin" / "Hostx64" / "x64" / dll_name
                    if cand.exists():
                        candidate_paths.append(cand)
    # Copy the first found
    for cand in candidate_paths:
        if cand.exists():
            shutil.copy2(cand, output_dir / dll_name)
            print(f"Copied {dll_name} to {output_dir}")
            return
    print(
        f"Warning: {dll_name} not found in Visual Studio install. Instrumented/PGO build may not run."
    )


def configure_and_build(
    project_root: Path, preset_name: str, platform_name: str
) -> None:
    """Configure and build using the given preset."""
    print(f"\n=== Configuring {preset_name} ===")

    config_cmd = ["cmake", "--preset", preset_name]

    # Add Python executable for cross-platform compatibility
    python_exe = sys.executable
    config_cmd.extend([f"-DPython3_EXECUTABLE={python_exe}"])

    run_command(config_cmd, cwd=project_root)

    print(f"\n=== Building {preset_name} ===")

    if platform_name == "windows" and "msvc" in preset_name:
        # MSVC builds need configuration specification
        run_command(
            ["cmake", "--build", "--preset", preset_name, "--config", "Release"],
            cwd=project_root,
        )
        # Ensure pgort140.dll is present after build
        build_dir = (
            project_root
            / f"build-msvc-pgo-{'generate' if 'generate' in preset_name else 'use'}"
        )
        copy_pgort_dll_to_output(build_dir)
    else:
        run_command(["cmake", "--build", "--preset", preset_name], cwd=project_root)


def run_training_command(
    cmd: List[str], description: str, cwd: Path, env: Optional[Dict[str, str]] = None
) -> bool:
    """Run a single training command with error handling."""
    print(f"Training: {description}")
    print(f"  Command: {' '.join(cmd)}")

    result = run_command(cmd, cwd=cwd, env=env, check=False, timeout=60)

    if result.returncode == 0:
        print("Success!")
        return True
    else:
        print(f"Failed (exit {result.returncode}) - continuing training")
        return False


def get_binary_path(build_dir: Path, platform_name: str) -> Path:
    """Get the path to the compiled binary."""
    if platform_name == "windows":
        return build_dir / "Release" / "olm.exe"
    else:
        return build_dir / "olm"


def run_comprehensive_pgo_training(
    project_root: Path, build_dir: Path, compiler: str, platform_name: str
) -> bool:
    """Run comprehensive PGO training workloads."""
    olm_binary = get_binary_path(build_dir, platform_name)

    if not olm_binary.exists():
        print(f"Error: Binary not found at {olm_binary}")
        return False

    print(f"\n=== Comprehensive PGO Training for {compiler.upper()} ===")
    print(f"Platform: {platform_name}")
    print(f"Binary: {olm_binary}")
    print(f"Project root: {project_root}")
    print()

    # Set up environment for Clang PGO
    env = os.environ.copy()
    if compiler == "clang":
        pgo_dir = build_dir / "pgo-profiles"
        pgo_dir.mkdir(exist_ok=True)
        env["LLVM_PROFILE_FILE"] = str(pgo_dir / "training_%p_%m.profraw")

    # Platform-specific temp directory
    if platform_name == "windows":
        temp_dir = Path(os.environ.get("TEMP", "C:/temp"))
        null_output = "NUL"
    else:
        temp_dir = Path("/tmp")
        null_output = "/dev/null"

    # Ensure temp directory exists
    temp_dir.mkdir(exist_ok=True)

    # Comprehensive training workloads
    match_output_file = str(temp_dir / "pgo_match_output.txt")
    training_workloads = [
        # === BASIC OPERATIONS ===
        {
            "category": "Basic Operations",
            "commands": [
                ([str(olm_binary), "--help"], "Help command"),
                ([str(olm_binary), "--version"], "Version command"),
            ],
        },
        # === COMPILE OPERATIONS ===
        {
            "category": "Compilation Workloads",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "compile",
                        str(temp_dir / "names.olm"),
                        "data/names.txt",
                    ],
                    "Compile names patterns",
                ),
                (
                    [
                        str(olm_binary),
                        "compile",
                        str(temp_dir / "surnames.olm"),
                        "data/surnames.txt",
                    ],
                    "Compile surnames patterns",
                ),
                (
                    [
                        str(olm_binary),
                        "compile",
                        str(temp_dir / "census.olm"),
                        "data/surnames_us_census.txt",
                    ],
                    "Compile census surnames",
                ),
                (
                    [
                        str(olm_binary),
                        "compile",
                        str(temp_dir / "small.olm"),
                        "data/small_pats.txt",
                    ],
                    "Compile small patterns",
                ),
                (
                    [
                        str(olm_binary),
                        "compile",
                        str(temp_dir / "tlds.olm"),
                        "data/tlds.txt",
                    ],
                    "Compile TLD patterns",
                ),
            ],
        },
        # === BASIC MATCHING ===
        {
            "category": "Basic Matching",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Names in Bible",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        str(temp_dir / "surnames.olm"),
                        "data/kjv.txt",
                    ],
                    "Surnames in Bible",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        str(temp_dir / "small.olm"),
                        "data/small_hay.txt",
                    ],
                    "Small pattern test",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "data/names.txt",
                        "data/kjv.txt",
                    ],
                    "Direct text patterns",
                ),
            ],
        },
        # === CASE SENSITIVITY ===
        {
            "category": "Case Sensitivity",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--ignore-case",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Case-insensitive names",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--ignore-case",
                        str(temp_dir / "surnames.olm"),
                        "data/kjv.txt",
                    ],
                    "Case-insensitive surnames",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--ignore-case",
                        "data/tlds.txt",
                        "data/haystack_email.txt",
                    ],
                    "Case-insensitive TLDs",
                ),
            ],
        },
        # === WORD BOUNDARY MATCHING ===
        {
            "category": "Word Boundary Matching",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--word-boundary",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Word boundary names",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--word-boundary",
                        "--ignore-case",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Word boundary + case insensitive",
                ),
            ],
        },
        # === LONGEST MATCH & NO OVERLAP ===
        {
            "category": "Advanced Matching Modes",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--longest",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Longest match",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--no-overlap",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "No overlap",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--longest",
                        "--no-overlap",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Longest + no overlap",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--longest",
                        "--no-overlap",
                        "--ignore-case",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "All flags combined",
                ),
            ],
        },
        # === WHITESPACE HANDLING ===
        {
            "category": "Whitespace Processing",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--elide-whitespace",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Elide whitespace",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--word-boundary",
                        "--elide-whitespace",
                        "--longest",
                        "--no-overlap",
                        "--ignore-case",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "All flags maximum",
                ),
            ],
        },
        # === MULTI-THREADING ===
        {
            "category": "Multi-threading",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--threads",
                        "1",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Single thread",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--threads",
                        "2",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Two threads",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--threads",
                        "4",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Four threads",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--threads",
                        "8",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Eight threads",
                ),
            ],
        },
        # === CHUNK SIZES ===
        {
            "category": "Chunk Size Variations",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--chunk-size",
                        "512",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Small chunks (512)",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--chunk-size",
                        "1024",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Medium chunks (1024)",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--chunk-size",
                        "4096",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Large chunks (4096)",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--chunk-size",
                        "16384",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Very large chunks (16384)",
                ),
            ],
        },
        # === LINE ANCHORS ===
        {
            "category": "Line Anchors",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "data/line_anchor_patterns.txt",
                        "data/line_anchor_haystack.txt",
                    ],
                    "Line anchor patterns",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "data/line_exact_patterns.txt",
                        "data/line_exact_haystack.txt",
                    ],
                    "Line exact patterns",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "data/line_exact_match_patterns.txt",
                        "data/line_exact_match_haystack.txt",
                    ],
                    "Exact match patterns",
                ),
            ],
        },
        # === LARGE DATASETS ===
        {
            "category": "Large Dataset Processing",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        str(temp_dir / "census.olm"),
                        "data/surname-us.txt",
                    ],
                    "Census surnames in US surname data",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--ignore-case",
                        str(temp_dir / "names.olm"),
                        "data/surname-us.txt",
                    ],
                    "Names in large surname data",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "data/tlds.txt",
                        "data/grep_found.txt",
                    ],
                    "TLD patterns in grep results",
                ),
            ],
        },
        # === OUTPUT MODES ===
        {
            "category": "Output Handling",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        str(temp_dir / "output1.txt"),
                        str(temp_dir / "names.olm"),
                        "data/small_hay.txt",
                    ],
                    "File output",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        null_output,
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Null output",
                ),
            ],
        },
        # === STRESS TESTS ===
        {
            "category": "Stress Testing",
            "commands": [
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--threads",
                        "4",
                        "--chunk-size",
                        "1024",
                        "--longest",
                        "--no-overlap",
                        "--ignore-case",
                        str(temp_dir / "surnames.olm"),
                        "data/kjv.txt",
                    ],
                    "Complex surname matching",
                ),
                (
                    [
                        str(olm_binary),
                        "match",
                        "--output",
                        match_output_file,
                        "--threads",
                        "2",
                        "--word-boundary",
                        "--elide-whitespace",
                        str(temp_dir / "names.olm"),
                        "data/kjv.txt",
                    ],
                    "Complex name matching",
                ),
            ],
        },
    ]

    total_commands = sum(len(workload["commands"]) for workload in training_workloads)
    current_command = 0
    successful_commands = 0

    print(f"Starting comprehensive training with {total_commands} commands...")
    print()

    for workload in training_workloads:
        print(f"--- {workload['category']} ---")

        for cmd, description in workload["commands"]:
            current_command += 1
            print(f"[{current_command}/{total_commands}] ", end="")
            if run_training_command(cmd, description, project_root, env):
                successful_commands += 1

    print(f"\n=== Comprehensive PGO Training Complete ===")
    print(
        f"Successful commands: {successful_commands}/{total_commands} ({100*successful_commands/total_commands:.1f}%)"
    )

    return successful_commands > (total_commands * 0.5)  # Require at least 50% success


def copy_gcc_profile_data(project_root: Path) -> bool:
    """Copy GCC profile data (.gcda files) from generate to use directory."""
    print("\n=== Copying GCC profile data ===")

    generate_dir = project_root / "build-gcc-pgo-generate"
    use_dir = project_root / "build-gcc-pgo-use"

    # For GCC, profile data is generated in CMakeFiles subdirectories
    generate_cmake_files = generate_dir / "CMakeFiles"
    use_cmake_files = use_dir / "CMakeFiles"

    if not generate_cmake_files.exists():
        print("Warning: No CMakeFiles directory found in generate build")
        return False

    # Ensure the use directory exists
    use_dir.mkdir(exist_ok=True)

    # Copy the entire CMakeFiles directory structure
    if use_cmake_files.exists():
        shutil.rmtree(use_cmake_files)

    shutil.copytree(generate_cmake_files, use_cmake_files)

    # Count profile data files
    gcda_files = list(use_cmake_files.rglob("*.gcda"))
    print(f"Copied {len(gcda_files)} .gcda profile data files")

    if len(gcda_files) == 0:
        print(
            "Warning: No .gcda files found. Training may not have generated profile data."
        )
        return False

    print("Profile data copied successfully")
    return True


def process_clang_profiles(project_root: Path) -> bool:
    """Process Clang profile data using llvm-profdata."""
    print("\n=== Processing Clang profile data ===")

    build_dir = project_root / "build-clang-pgo-generate"
    profile_dir = build_dir / "pgo-profiles"

    if not profile_dir.exists():
        print(f"Error: Profile directory not found: {profile_dir}")
        return False

    # Find all .profraw files
    profraw_files = list(profile_dir.glob("*.profraw"))
    if not profraw_files:
        print("Warning: No .profraw files found")
        return False

    print(f"Found {len(profraw_files)} .profraw files")

    # Merge profiles
    merged_profile = profile_dir / "merged.profdata"

    # Try different llvm-profdata executables
    profdata_tools = [
        "llvm-profdata",
        "llvm-profdata-15",
        "llvm-profdata-14",
        "llvm-profdata-13",
    ]
    profdata_cmd = None

    for tool in profdata_tools:
        try:
            run_command([tool, "--version"], check=False)
            profdata_cmd = tool
            print(f"Using {tool} for profile merging")
            break
        except:
            continue

    if not profdata_cmd:
        print("Error: llvm-profdata not found. Please install LLVM tools.")
        return False

    cmd = [profdata_cmd, "merge", "-output", str(merged_profile)] + [
        str(f) for f in profraw_files
    ]
    result = run_command(cmd, cwd=project_root, check=False)

    if result.returncode != 0:
        print("Failed to merge Clang profiles")
        return False

    print(f"Merged profile data: {merged_profile}")

    # Verify the merged profile
    if merged_profile.exists() and merged_profile.stat().st_size > 0:
        print(
            f"Successfully created merged profile: {merged_profile.stat().st_size} bytes"
        )
        return True
    else:
        print("Error: Failed to create merged profile")
        return False


def copy_msvc_profile_data(project_root: Path) -> bool:
    """Copy MSVC profile data (.pgd and .pgc files) from generate to use directory."""
    print("\n=== Copying MSVC profile data ===")

    generate_dir = project_root / "build-msvc-pgo-generate" / "Release"
    use_dir = project_root / "build-msvc-pgo-use" / "Release"

    if not generate_dir.exists():
        print("Warning: Generate directory not found")
        return False

    # Ensure use directory exists
    use_dir.mkdir(parents=True, exist_ok=True)

    # Find and copy .pgd files
    pgd_files = list(generate_dir.glob("*.pgd"))

    if not pgd_files:
        print("Warning: No .pgd files found")

    for pgd_file in pgd_files:
        dest_file = use_dir / pgd_file.name
        shutil.copy2(pgd_file, dest_file)
        print(f"Copied {pgd_file.name}")

    # Find and copy .pgc files
    pgc_files = list(generate_dir.glob("*.pgc"))

    if not pgc_files:
        print("Warning: No .pgc files found")

    for pgc_file in pgc_files:
        dest_file = use_dir / pgc_file.name
        shutil.copy2(pgc_file, dest_file)
        print(f"Copied {pgc_file.name}")

    print(f"Copied {len(pgd_files)} .pgd and {len(pgc_files)} .pgc profile data files")
    return bool(pgd_files)


def run_pgo_workflow(
    compiler: str, build_only: bool, clean: bool, platform_name: str
) -> None:
    """Run the complete PGO workflow for the specified compiler."""
    print(f"=== Starting {compiler.upper()} PGO workflow on {platform_name} ===")

    # Find project root
    try:
        project_root = find_project_root()
        print(f"Project root: {project_root}")
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Check compiler availability
    check_compiler_availability(compiler, platform_name)

    if clean:
        clean_build_directories(project_root, compiler)

    # Step 1: Build instrumented version
    generate_preset = f"{compiler}-pgo-generate"
    configure_and_build(project_root, generate_preset, platform_name)

    if not build_only:
        # Step 2: Run training workloads
        build_dir = project_root / f"build-{compiler}-pgo-generate"
        training_success = run_comprehensive_pgo_training(
            project_root, build_dir, compiler, platform_name
        )

        if not training_success:
            print("Warning: Training had low success rate, but continuing...")

        # Step 3: Process and copy profile data
        profile_success = False

        if compiler == "gcc":
            profile_success = copy_gcc_profile_data(project_root)
        elif compiler == "clang":
            profile_success = process_clang_profiles(project_root)
            if profile_success:
                # Copy processed profiles to use directory
                generate_dir = project_root / "build-clang-pgo-generate"
                use_dir = project_root / "build-clang-pgo-use"
                use_dir.mkdir(exist_ok=True)

                profile_source = generate_dir / "pgo-profiles"
                profile_dest = use_dir / "pgo-profiles"

                if profile_source.exists():
                    if profile_dest.exists():
                        shutil.rmtree(profile_dest)
                    shutil.copytree(profile_source, profile_dest)
        elif compiler == "msvc":
            profile_success = copy_msvc_profile_data(project_root)

        if not profile_success:
            print(
                "Warning: Profile data processing failed, but continuing with optimization build..."
            )

        # Step 4: Build optimized version
        use_preset = f"{compiler}-pgo-use"
        configure_and_build(project_root, use_preset, platform_name)

        use_dir = project_root / f"build-{compiler}-pgo-use"
        optimized_binary = get_binary_path(use_dir, platform_name)

        print(f"\n=== {compiler.upper()} PGO workflow completed successfully ===")
        print(f"Optimized binary: {optimized_binary}")

        # Quick verification
        if optimized_binary.exists():
            print(f"Binary size: {optimized_binary.stat().st_size:,} bytes")
        else:
            print("Warning: Optimized binary not found")
    else:
        print(f"\n=== {compiler.upper()} PGO instrumentation build completed ===")


def main():
    parser = argparse.ArgumentParser(
        description="Unified Cross-Platform PGO workflow automation"
    )
    parser.add_argument(
        "--compiler",
        choices=["gcc", "clang", "msvc"],
        required=True,
        help="Compiler to use for PGO",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Only build instrumented version, skip training",
    )
    parser.add_argument(
        "--clean", action="store_true", help="Clean build directories before starting"
    )

    args = parser.parse_args()

    # Detect platform
    platform_name = detect_platform()
    print(f"Detected platform: {platform_name}")

    # Platform-specific validations
    if args.compiler == "msvc" and platform_name not in ["windows"]:
        print("Error: MSVC compiler is only supported on Windows")
        sys.exit(1)

    if platform_name == "unknown":
        print("Warning: Unknown platform detected. Proceeding with Linux defaults...")
        platform_name = "linux"

    start_time = time.time()

    try:
        run_pgo_workflow(args.compiler, args.build_only, args.clean, platform_name)
    except KeyboardInterrupt:
        print("\nWorkflow interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.1f} seconds")


if __name__ == "__main__":
    main()
