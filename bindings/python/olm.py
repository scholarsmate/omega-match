#!/usr/bin/env python3

# olm.py

import argparse
import io
import os
import sys

from omega_match import Compiler, Matcher, get_library_info, get_version

# Force stdout to use Unix-style line endings explicitly on Windows
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, newline="\n", encoding=sys.stdout.encoding
    )


def compile_mode(
    output_file: str,
    patterns_file: str,
    case_insensitive: bool,
    ignore_punctuation: bool,
    elide_whitespace: bool,
    verbose: bool,
) -> None:
    with Compiler(
        output_file, case_insensitive, ignore_punctuation, elide_whitespace
    ) as compiler, open(patterns_file, "rb") as f:
        for line in f:
            pattern = line.rstrip(b"\r\n")
            if pattern:
                compiler.add_pattern(pattern)
        stats = compiler.get_stats()

    if verbose:
        print("Stored pattern count:", stats.stored_pattern_count, file=sys.stderr)
        print("Shortest pattern:", stats.smallest_pattern_length, file=sys.stderr)
        print("Longest pattern:", stats.largest_pattern_length, file=sys.stderr)
        print("Duplicates removed:", stats.duplicate_patterns, file=sys.stderr)
        print("Input bytes:", stats.total_input_bytes, file=sys.stderr)
        print("Stored bytes:", stats.total_stored_bytes, file=sys.stderr)
        print(
            "Ratio: {:.2f}".format(stats.total_stored_bytes / stats.total_input_bytes),
            file=sys.stderr,
        )
        print("Compile completed successfully", file=sys.stderr)


def match_mode(
    compiled_file: str,
    haystack_file: str,
    case_insensitive: bool,
    ignore_punctuation: bool,
    elide_whitespace: bool,
    no_overlap: bool,
    longest_only: bool,
    word_boundary: bool,
    word_prefix: bool,
    word_suffix: bool,
    line_start: bool,
    line_end: bool,
    threads: int,
    chunk_size: int,
    verbose: bool,
) -> None:
    with open(haystack_file, "rb") as f:
        haystack = f.read()

    with Matcher(
        compiled_file, case_insensitive, ignore_punctuation, elide_whitespace
    ) as matcher:
        if threads:
            matcher.set_threads(threads)
        if chunk_size:
            matcher.set_chunk_size(chunk_size)

        results = matcher.match(
            haystack=haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )

        if verbose:
            stats = matcher.get_match_stats()
            print("Match Stats:", stats, file=sys.stderr)

        for r in results:
            # Always emit Unix-style newlines
            sys.stdout.write(
                f"{r.offset}:{r.match.decode('utf-8', errors='replace')}\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pattern matching tool")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"v{get_version()} / Library Info: {get_library_info()}",
        help="Show version information"
    )

    subparsers = parser.add_subparsers(
        dest="mode", required=True, help="Select operation mode"
    )

    # Compile mode parser
    compile_parser = subparsers.add_parser("compile", help="Compile patterns")
    compile_parser.add_argument("compiled", help="Output compiled file")
    compile_parser.add_argument("patterns", help="Input patterns file")
    compile_parser.add_argument(
        "--ignore-case", action="store_true", help="Ignore case in patterns"
    )
    compile_parser.add_argument(
        "--ignore-punctuation",
        action="store_true",
        help="Ignore punctuation in patterns",
    )
    compile_parser.add_argument(
        "--elide-whitespace", action="store_true", help="Remove whitespace in patterns"
    )

    # Match mode parser
    match_parser = subparsers.add_parser("match", help="Match patterns")
    match_parser.add_argument("compiled", help="Input compiled file")
    match_parser.add_argument("haystack", help="Input haystack file")
    match_parser.add_argument(
        "--ignore-case", action="store_true", help="Ignore case during matching"
    )
    match_parser.add_argument(
        "--ignore-punctuation",
        action="store_true",
        help="Ignore punctuation during matching",
    )
    match_parser.add_argument(
        "--elide-whitespace",
        action="store_true",
        help="Remove whitespace during matching",
    )
    match_parser.add_argument(
        "--longest", action="store_true", help="Only return longest matches"
    )
    match_parser.add_argument(
        "--no-overlap", action="store_true", help="Avoid overlapping matches"
    )
    match_parser.add_argument(
        "--word-boundary", action="store_true", help="Only match at word boundaries"
    )
    match_parser.add_argument(
        "--word-prefix", action="store_true", help="Only match at word prefixes"
    )
    match_parser.add_argument(
        "--word-suffix", action="store_true", help="Only match at word suffixes"
    )
    match_parser.add_argument(
        "--line-start", action="store_true", help="Only match at line starts"
    )
    match_parser.add_argument(
        "--line-end", action="store_true", help="Only match at line ends"
    )
    match_parser.add_argument(
        "--threads", type=int, default=0, help="Number of threads to use"
    )
    match_parser.add_argument(
        "--chunk-size", type=int, default=0, help="Chunk size for parallel processing"
    )

    # Try to enable argcomplete (if available)
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    # Allow `-h compile` or `-h match` to redirect to `compile -h` or `match -h` respectively
    if "-h" in sys.argv or "--help" in sys.argv:
        help_index = (
            sys.argv.index("-h") if "-h" in sys.argv else sys.argv.index("--help")
        )
        if help_index + 1 < len(sys.argv):
            mode = sys.argv[help_index + 1]
            if mode in subparsers.choices:
                sys.argv = [sys.argv[0], mode, "-h"]

    args = parser.parse_args()

    if args.verbose:
        print(f"Running in {args.mode} mode with arguments: {args}")

    if args.mode == "compile":
        compile_mode(
            output_file=args.compiled,
            patterns_file=args.patterns,
            case_insensitive=args.ignore_case,
            ignore_punctuation=args.ignore_punctuation,
            elide_whitespace=args.elide_whitespace,
            verbose=args.verbose,
        )
    elif args.mode == "match":
        match_mode(
            compiled_file=args.compiled,
            haystack_file=args.haystack,
            case_insensitive=args.ignore_case,
            ignore_punctuation=args.ignore_punctuation,
            elide_whitespace=args.elide_whitespace,
            no_overlap=args.no_overlap,
            longest_only=args.longest,
            word_boundary=args.word_boundary,
            word_prefix=args.word_prefix,
            word_suffix=args.word_suffix,
            line_start=args.line_start,
            line_end=args.line_end,
            threads=args.threads,
            chunk_size=args.chunk_size,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
