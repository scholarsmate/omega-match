#!/usr/bin/env python3
"""Byte-accurate OmegaMatch/grep/ripgrep scaling benchmark.

The legacy perf_test.py is useful as a broad smoke benchmark, but historically
used a fixed 1 GiB throughput numerator for the checked-in ~4 MiB haystack and
sent grep output directly to /dev/null. GNU grep can turn the latter into an
exit-on-first-match search. This runner instead:

* generates exact-size corpora on a caller-selected filesystem;
* drains every comparator's complete output through a pipe;
* sorts comparator patterns longest-first and escapes anchored regexes;
* strips the source UTF-8 BOM so ripgrep and byte-oriented tools agree;
* verifies output byte count and SHA-256 before recording timings; and
* records every sample plus environment metadata in CSV and JSON.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

MIB = 1024 * 1024
UTF8_BOM = b"\xef\xbb\xbf"

CASES: dict[str, tuple[str, ...]] = {
    "longest-no-overlap": ("--longest", "--no-overlap"),
    "line-start": ("--line-start", "--longest", "--no-overlap"),
    "line-end": ("--line-end", "--longest", "--no-overlap"),
    "line-exact": (
        "--line-start",
        "--line-end",
        "--longest",
        "--no-overlap",
    ),
}


@dataclass
class Tool:
    name: str
    command: Callable[[str, Path, bool], list[str]]
    accepted_codes: tuple[int, ...] = (0,)


@dataclass
class Result:
    case: str
    tool: str
    mode: str
    threads: int
    input_bytes: int
    input_mib: float
    runs: int
    median_s: float
    min_s: float
    max_s: float
    median_mib_s: float
    output_bytes: int
    output_sha256: str
    samples_s: list[float]


def parse_csv_ints(value: str) -> list[int]:
    values = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not values or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("expected comma-separated positive integers")
    return values


def parse_cases(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in values if item not in CASES]
    if not values or unknown:
        choices = ", ".join(CASES)
        raise argparse.ArgumentTypeError(
            f"unknown case(s): {', '.join(unknown)}; choices: {choices}"
        )
    return values


def parse_olm(value: str) -> tuple[str, Path]:
    if "=" in value:
        name, raw_path = value.split("=", 1)
    else:
        raw_path = value
        name = Path(value).name
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("expected [LABEL=]PATH")
    return name, Path(raw_path).resolve()


def version_output(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"


def generate_corpus(source: Path, destination: Path, size: int) -> None:
    data = source.read_bytes()
    if data.startswith(UTF8_BOM):
        data = data[len(UTF8_BOM) :]
    if not data:
        raise ValueError(f"source haystack is empty after BOM removal: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as stream:
        whole, tail = divmod(size, len(data))
        for _ in range(whole):
            stream.write(data)
        stream.write(data[:tail])
    if destination.stat().st_size != size:
        raise RuntimeError(f"failed to generate exact-size corpus: {destination}")


def prepare_patterns(source: Path, work_dir: Path) -> dict[str, Path]:
    patterns = [line.rstrip(b"\r") for line in source.read_bytes().splitlines()]
    patterns = [pattern for pattern in patterns if pattern]
    patterns.sort(key=lambda pattern: (-len(pattern), pattern))
    if not patterns:
        raise ValueError(f"pattern file has no non-empty patterns: {source}")

    paths = {
        "fixed": work_dir / "patterns-longest-first.txt",
        "line-start": work_dir / "patterns-line-start.regex",
        "line-end": work_dir / "patterns-line-end.regex",
        "line-exact": work_dir / "patterns-line-exact.regex",
    }
    paths["fixed"].write_bytes(b"\n".join(patterns) + b"\n")
    for name, prefix, suffix in (
        ("line-start", b"^", b""),
        ("line-end", b"", b"$"),
        ("line-exact", b"^", b"$"),
    ):
        escaped = (prefix + re.escape(pattern) + suffix for pattern in patterns)
        paths[name].write_bytes(b"\n".join(escaped) + b"\n")
    return paths


def drain_command(
    command: Sequence[str],
    env: dict[str, str],
    digest: bool,
    accepted_codes: tuple[int, ...] = (0,),
) -> tuple[float, int, str]:
    hasher = hashlib.sha256() if digest else None
    output_bytes = 0
    start = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(MIB)
        if not chunk:
            break
        output_bytes += len(chunk)
        if hasher is not None:
            hasher.update(chunk)
    returncode = process.wait()
    elapsed = time.perf_counter() - start
    if returncode not in accepted_codes:
        raise RuntimeError(f"command exited {returncode}: {' '.join(command)}")
    return elapsed, output_bytes, hasher.hexdigest() if hasher is not None else ""


def quiet_command(
    command: Sequence[str], env: dict[str, str]
) -> tuple[float, int, str]:
    start = time.perf_counter()
    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        check=False,
    )
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        raise RuntimeError(
            f"command exited {result.returncode}: {' '.join(command)}"
        )
    return elapsed, 0, ""


def warm_file(path: Path) -> None:
    with path.open("rb") as stream:
        while stream.read(8 * MIB):
            pass


def compile_patterns(
    binary: Path, patterns: Path, destination: Path, env: dict[str, str]
) -> None:
    result = subprocess.run(
        [str(binary), "compile", str(destination), str(patterns)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to compile patterns with {binary}: {result.stderr.strip()}"
        )


def build_tools(
    olm_binaries: list[tuple[str, Path]],
    compiled: dict[str, Path],
    pattern_paths: dict[str, Path],
    threads: int,
    include_grep: bool,
    include_ripgrep: bool,
) -> list[Tool]:
    tools: list[Tool] = []
    for name, binary in olm_binaries:
        compiled_path = compiled[name]

        def olm_command(
            case: str,
            haystack: Path,
            quiet: bool,
            binary: Path = binary,
            compiled_path: Path = compiled_path,
        ) -> list[str]:
            return [
                str(binary),
                "match",
                *(["--quiet"] if quiet else []),
                "--threads",
                str(threads),
                *CASES[case],
                str(compiled_path),
                str(haystack),
            ]

        tools.append(Tool(f"olm-{name}", olm_command))

    if include_grep and shutil.which("grep"):

        def grep_command(case: str, haystack: Path, quiet: bool) -> list[str]:
            del quiet
            pattern_path = (
                pattern_paths["fixed"]
                if case == "longest-no-overlap"
                else pattern_paths[case]
            )
            return [
                "grep",
                "-a",
                "-F" if case == "longest-no-overlap" else "-E",
                "-o",
                "-b",
                "-f",
                str(pattern_path),
                str(haystack),
            ]

        tools.append(Tool("grep", grep_command, (0, 1)))

    if include_ripgrep and shutil.which("rg"):

        def rg_command(case: str, haystack: Path, quiet: bool) -> list[str]:
            del quiet
            pattern_path = (
                pattern_paths["fixed"]
                if case == "longest-no-overlap"
                else pattern_paths[case]
            )
            command = [
                "rg",
                "--text",
                "--no-heading",
                "--color",
                "never",
                "--no-unicode",
                "-j",
                str(threads),
            ]
            if case == "longest-no-overlap":
                command.append("-F")
            command.extend(("-o", "-b", "-f", str(pattern_path), str(haystack)))
            return command

        tools.append(Tool("ripgrep", rg_command, (0, 1)))
    return tools


def write_csv(path: Path, results: Iterable[Result]) -> None:
    rows = [asdict(result) for result in results]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            row["samples_s"] = json.dumps(row["samples_s"])
            writer.writerow(row)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--olm",
        action="append",
        type=parse_olm,
        help="OmegaMatch binary as [LABEL=]PATH; may be repeated",
    )
    parser.add_argument("--patterns", type=Path, default=Path("data/names.txt"))
    parser.add_argument("--haystack", type=Path, default=Path("data/kjv.txt"))
    parser.add_argument(
        "--sizes-mib", type=parse_csv_ints, default=parse_csv_ints("4,16,64,256")
    )
    parser.add_argument(
        "--cases",
        type=parse_cases,
        default=parse_cases("longest-no-overlap,line-start,line-end"),
    )
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--mode",
        choices=("output", "quiet"),
        default="output",
        help="output is equivalent CLI work; quiet suppresses only OM output",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(os.environ.get("TMPDIR", "/tmp")) / "omega-match-scaling",
    )
    parser.add_argument("--skip-correctness", action="store_true")
    parser.add_argument("--skip-grep", action="store_true")
    parser.add_argument("--skip-ripgrep", action="store_true")
    args = parser.parse_args(argv)

    if args.threads <= 0 or args.runs <= 0:
        parser.error("--threads and --runs must be positive")
    olm_binaries = args.olm or [("release", Path("build-gcc-release/olm").resolve())]
    for _, binary in olm_binaries:
        if not binary.is_file():
            parser.error(f"OmegaMatch binary not found: {binary}")
    if not args.patterns.is_file() or not args.haystack.is_file():
        parser.error("pattern and haystack source files must exist")

    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    pattern_paths = prepare_patterns(args.patterns, work_dir)
    env = os.environ.copy()
    env.update({"LC_ALL": "C", "OMP_DYNAMIC": "FALSE"})

    compiled: dict[str, Path] = {}
    for name, binary in olm_binaries:
        destination = work_dir / f"patterns-{name}.olm"
        compile_patterns(binary, args.patterns.resolve(), destination, env)
        compiled[name] = destination

    corpora: list[Path] = []
    for size_mib in args.sizes_mib:
        destination = work_dir / f"haystack-{size_mib}m.bin"
        generate_corpus(args.haystack.resolve(), destination, size_mib * MIB)
        corpora.append(destination)

    tools = build_tools(
        olm_binaries,
        compiled,
        pattern_paths,
        args.threads,
        not args.skip_grep,
        not args.skip_ripgrep,
    )
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "threads": args.threads,
        "mode": args.mode,
        "runs": args.runs,
        "sizes_mib": args.sizes_mib,
        "cases": args.cases,
        "source_haystack": str(args.haystack.resolve()),
        "source_patterns": str(args.patterns.resolve()),
        "work_dir": str(work_dir),
        "versions": {
            **{
                f"olm-{name}": version_output([str(binary), "--version"])
                for name, binary in olm_binaries
            },
            "grep": version_output(["grep", "--version"])
            if shutil.which("grep")
            else "unavailable",
            "ripgrep": version_output(["rg", "--version"])
            if shutil.which("rg")
            else "unavailable",
        },
    }

    correctness: dict[str, dict[str, dict[str, object]]] = {}
    if not args.skip_correctness:
        smallest = corpora[0]
        for case in args.cases:
            expected: tuple[int, str] | None = None
            correctness[case] = {}
            for tool in tools:
                _, output_bytes, digest = drain_command(
                    tool.command(case, smallest, False),
                    env,
                    True,
                    tool.accepted_codes,
                )
                correctness[case][tool.name] = {
                    "bytes": output_bytes,
                    "sha256": digest,
                }
                if expected is None:
                    expected = (output_bytes, digest)
                elif (output_bytes, digest) != expected:
                    raise RuntimeError(
                        f"correctness mismatch for {case}: {tool.name} produced "
                        f"{output_bytes} bytes/{digest}, expected {expected}"
                    )
            print(f"correctness {case}: OK ({expected[0] if expected else 0} bytes)")

    results: list[Result] = []
    quiet = args.mode == "quiet"
    for corpus in corpora:
        input_bytes = corpus.stat().st_size
        input_mib = input_bytes / MIB
        warm_file(corpus)
        for case in args.cases:
            samples: dict[str, list[tuple[float, int]]] = {
                tool.name: [] for tool in tools
            }
            # Rotate tool order between repetitions to reduce thermal/order bias.
            for run in range(args.runs):
                order = tools[run % len(tools) :] + tools[: run % len(tools)]
                for tool in order:
                    command = tool.command(case, corpus, quiet)
                    if quiet and tool.name.startswith("olm-"):
                        elapsed, output_bytes, _ = quiet_command(command, env)
                    else:
                        elapsed, output_bytes, _ = drain_command(
                            command, env, False, tool.accepted_codes
                        )
                    samples[tool.name].append((elapsed, output_bytes))

            for tool in tools:
                tool_samples = samples[tool.name]
                elapsed_samples = [item[0] for item in tool_samples]
                output_sizes = {item[1] for item in tool_samples}
                if len(output_sizes) != 1:
                    raise RuntimeError(
                        f"unstable output size for {case}/{tool.name}: {output_sizes}"
                    )
                median_s = statistics.median(elapsed_samples)
                digest = (
                    str(
                        correctness.get(case, {})
                        .get(tool.name, {})
                        .get("sha256", "")
                    )
                    if corpus == corpora[0]
                    else ""
                )
                result = Result(
                    case=case,
                    tool=tool.name,
                    mode=args.mode,
                    threads=args.threads,
                    input_bytes=input_bytes,
                    input_mib=input_mib,
                    runs=args.runs,
                    median_s=median_s,
                    min_s=min(elapsed_samples),
                    max_s=max(elapsed_samples),
                    median_mib_s=input_mib / median_s,
                    output_bytes=next(iter(output_sizes)),
                    output_sha256=digest,
                    samples_s=elapsed_samples,
                )
                results.append(result)
                print(
                    f"{case:20} {input_mib:7.1f} MiB {tool.name:16} "
                    f"{median_s:8.4f} s {result.median_mib_s:9.1f} MiB/s"
                )

    csv_path = work_dir / "scaling-results.csv"
    json_path = work_dir / "scaling-results.json"
    write_csv(csv_path, results)
    json_path.write_text(
        json.dumps(
            {
                "metadata": metadata,
                "correctness": correctness,
                "results": [asdict(result) for result in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
