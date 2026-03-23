#!/usr/bin/env python3

# olm.py

import argparse
import io
import os
import sys

from omega_match import Compiler, Matcher, get_library_info, get_version

UINT64_MAX = (1 << 64) - 1

def _configure_cli_stdout() -> None:
    if os.name == "nt":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, newline="\n", encoding=sys.stdout.encoding
        )


def _hex_digit_value(ch: int) -> int:
    if 48 <= ch <= 57:
        return ch - 48
    if 65 <= ch <= 70:
        return ch - 55
    if 97 <= ch <= 102:
        return ch - 87
    return -1


def _parse_uint64_prefix(data: bytes) -> tuple[int, int]:
    length = len(data)
    idx = 0

    while idx < length and data[idx] in b" \t\v\f\r":
        idx += 1
    if idx >= length:
        raise ValueError("missing key")
    if data[idx] == ord("-"):
        raise ValueError("negative keys are not allowed")
    if data[idx] == ord("+"):
        idx += 1
        if idx >= length:
            raise ValueError("missing key")

    if data[idx] == ord("0"):
        if idx + 1 < length and data[idx + 1] in (ord("x"), ord("X")):
            idx += 2
            if idx >= length:
                raise ValueError("missing hex digits")
            value = 0
            digits = 0
            while idx < length:
                digit = _hex_digit_value(data[idx])
                if digit < 0:
                    break
                if value > ((UINT64_MAX - digit) // 16):
                    raise ValueError("key out of range")
                value = (value << 4) + digit
                idx += 1
                digits += 1
            if digits == 0:
                raise ValueError("missing hex digits")
            return value, idx

        value = 0
        idx += 1
        while idx < length and 48 <= data[idx] <= 55:
            digit = data[idx] - 48
            if value > ((UINT64_MAX - digit) // 8):
                raise ValueError("key out of range")
            value = (value << 3) + digit
            idx += 1
        return value, idx

    if not (48 <= data[idx] <= 57):
        raise ValueError("missing key")

    value = 0
    while idx < length and 48 <= data[idx] <= 57:
        digit = data[idx] - 48
        if value > ((UINT64_MAX - digit) // 10):
            raise ValueError("key out of range")
        value = value * 10 + digit
        idx += 1
    return value, idx


def _parse_first_keyed_record(line: bytes) -> tuple[int, bytes, bytes]:
    key, end = _parse_uint64_prefix(line)
    if end >= len(line):
        raise ValueError("missing delimiter")
    delim = bytes([line[end]])
    return key, delim, line[end + 1 :]


def _parse_keyed_record(line: bytes, delim: bytes) -> tuple[int, bytes]:
    parts = line.split(delim, 1)
    if len(parts) != 2:
        raise LookupError("missing delimiter")
    key, end = _parse_uint64_prefix(parts[0])
    if end != len(parts[0]):
        raise ValueError("invalid key")
    return key, parts[1]


def compile_mode(
    output_file: str,
    patterns_file: str,
    case_insensitive: bool,
    ignore_punctuation: bool,
    elide_whitespace: bool,
    keyed: bool,
    verbose: bool,
) -> None:
    compiler = Compiler(
        output_file, case_insensitive, ignore_punctuation, elide_whitespace
    )
    stats = None
    failed = False

    try:
        with open(patterns_file, "rb") as f:
            delim: bytes | None = None
            first_key_line_num: int | None = None
            for line_num, line in enumerate(f, 1):
                line = line.rstrip(b"\r\n")
                if not line:
                    continue
                if keyed:
                    if delim is None:
                        first_key_line_num = line_num
                        try:
                            key, delim, pattern = _parse_first_keyed_record(line)
                        except ValueError:
                            print(
                                f"Error: cannot detect delimiter from line {first_key_line_num}.",
                                file=sys.stderr,
                            )
                            failed = True
                            raise SystemExit(1)
                        if verbose:
                            print(
                                f"Auto-detected delimiter: {delim!r}",
                                file=sys.stderr,
                            )
                        if pattern:
                            compiler.add_pattern(pattern, key=key)
                        continue

                    try:
                        key, pattern = _parse_keyed_record(line, delim)
                    except LookupError:
                        print(
                            f"Warning: line {line_num} has no {delim!r} delimiter, skipping.",
                            file=sys.stderr,
                        )
                        continue
                    except ValueError:
                        print(
                            f"Warning: line {line_num} has invalid key, skipping.",
                            file=sys.stderr,
                        )
                        continue

                    if pattern:
                        compiler.add_pattern(pattern, key=key)
                elif line:
                    compiler.add_pattern(line)

        stats = compiler.get_stats()
    except BaseException:
        failed = True
        raise
    finally:
        compiler.destroy()
        if failed and os.path.exists(output_file):
            os.unlink(output_file)

    if verbose:
        print("Stored pattern count:", stats.stored_pattern_count, file=sys.stderr)
        print("Shortest pattern:", stats.smallest_pattern_length, file=sys.stderr)
        print("Longest pattern:", stats.largest_pattern_length, file=sys.stderr)
        print("Duplicates removed:", stats.duplicate_patterns, file=sys.stderr)
        print("Input bytes:", stats.total_input_bytes, file=sys.stderr)
        print("Stored bytes:", stats.total_stored_bytes, file=sys.stderr)
        ratio = (
            stats.total_stored_bytes / stats.total_input_bytes
            if stats.total_input_bytes
            else 0.0
        )
        print(
            "Ratio: {:.2f}".format(ratio),
            file=sys.stderr,
        )
        print("Compile completed successfully", file=sys.stderr)


def match_mode(
    compiled_file: str,
    haystack_file: str,
    output_file: str,
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
    show_keys: bool,
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

        # Handle output file
        output_stream = sys.stdout
        if output_file and output_file.upper() != "NUL":
            output_stream = open(output_file, "w", encoding="utf-8", newline="\n")
        elif output_file and output_file.upper() == "NUL":
            # Handle NUL output (discard results)
            if os.name == "nt":
                output_stream = open("NUL", "w")
            else:
                output_stream = open("/dev/null", "w")

        try:
            for r in results:
                # Always emit Unix-style newlines
                if show_keys:
                    output_stream.write(
                        f"{r.offset}:{r.key}:{r.match.decode('utf-8', errors='replace')}\n"
                    )
                else:
                    output_stream.write(
                        f"{r.offset}:{r.match.decode('utf-8', errors='replace')}\n"
                    )
        finally:
            if output_file and output_stream != sys.stdout:
                output_stream.close()


def main() -> None:
    _configure_cli_stdout()
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
    compile_parser.add_argument(
        "--keyed",
        action="store_true",
        help="Read KEY<delim>PATTERN lines (delimiter auto-detected from first record)",
    )

    # Match mode parser
    match_parser = subparsers.add_parser("match", help="Match patterns")
    match_parser.add_argument("compiled", help="Input compiled file")
    match_parser.add_argument("haystack", help="Input haystack file")
    match_parser.add_argument(
        "-o", "--output", help="Write results to FILE instead of stdout"
    )
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
    match_parser.add_argument(
        "--show-keys", action="store_true", help="Include pattern keys in output"
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
            keyed=args.keyed,
            verbose=args.verbose,
        )
    elif args.mode == "match":
        match_mode(
            compiled_file=args.compiled,
            haystack_file=args.haystack,
            output_file=args.output,
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
            show_keys=args.show_keys,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
