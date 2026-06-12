#!/usr/bin/env python3
"""
Transform-path window boundary tests for omega_match.

The case-insensitive / ignore-punctuation / elide-whitespace match paths
process the haystack in 4MB windows. These tests pin down that matches
spanning a window boundary are found in every transform mode, and that a
literal trailing space in a pattern is preserved under case-only transforms.
"""

import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

WINDOW_SIZE = 4 * 1024 * 1024  # CASE_INSENSITIVE_WINDOW_SIZE in matcher.c


class WindowBoundaryTest(OmegaMatchTest):
    """Window boundary tests for the transform match paths."""

    def check_match(self, name, extra_args, patterns, haystack, expected_lines):
        """Compile-and-match generated inputs and compare the full output."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            patterns_file = tmp_path / "patterns.txt"
            haystack_file = tmp_path / "haystack.bin"
            output_file = tmp_path / "output.txt"
            patterns_file.write_bytes(patterns)
            haystack_file.write_bytes(haystack)

            cmd = [str(self.bin_path), "match", "--output", str(output_file)]
            cmd.extend(extra_args)
            cmd.extend([str(patterns_file), str(haystack_file)])
            self.run_command(cmd, check=True, capture_output=False)

            actual = sorted(output_file.read_bytes().splitlines())
            expected = sorted(line.encode() if isinstance(line, str) else line
                              for line in expected_lines)
            if actual != expected:
                raise AssertionError(
                    f"{name}: got {actual!r}, expected {expected!r}")
            self.logger.info(f"{name}: OK")

    def run_test(self):
        """Run the test."""
        # Case-insensitive match straddling the window boundary
        pos = WINDOW_SIZE - 5
        self.check_match(
            "ci straddles window boundary",
            ["--ignore-case"],
            b"HelloWorld\n",
            b"x" * pos + b"helloworld" + b"y" * 32,
            [f"{pos}:helloworld"],
        )

        # Case-insensitive match starting exactly at the window boundary
        self.check_match(
            "ci starts at window boundary",
            ["--ignore-case"],
            b"HelloWorld\n",
            b"x" * WINDOW_SIZE + b"helloworld" + b"y" * 32,
            [f"{WINDOW_SIZE}:helloworld"],
        )

        # A literal trailing space in a pattern is significant when only
        # case folding is active (mid-haystack and at end of input)
        self.check_match(
            "ci trailing-space pattern mid-haystack",
            ["--ignore-case"],
            b"AB \n",
            b"zz ab cd",
            ["3:ab "],
        )
        self.check_match(
            "ci trailing-space pattern at end of input",
            ["--ignore-case"],
            b"AB \n",
            b"zz ab ",
            ["3:ab "],
        )

        # Elide-whitespace match straddling the boundary: the normalized
        # match spans more original bytes than its normalized length
        pos = WINDOW_SIZE - 4
        self.check_match(
            "elide-whitespace straddles window boundary",
            ["--elide-whitespace"],
            b"foo bar\n",
            b"x" * pos + b"foo \t  bar" + b"y" * 32,
            [f"{pos}:foo \t  bar"],
        )

        # Ignore-punctuation match straddling the boundary
        pos = WINDOW_SIZE - 3
        self.check_match(
            "ignore-punctuation straddles window boundary",
            ["--ignore-punctuation"],
            b"foobar\n",
            b"x" * pos + b"fo..o!!bar" + b"y" * 32,
            [f"{pos}:fo..o!!bar"],
        )

        # Single-window sanity check with combined transforms
        self.check_match(
            "single window ci+punct sanity",
            ["--ignore-case", "--ignore-punctuation"],
            b"foo bar\n",
            b"The FOO, bar mix",
            ["4:FOO, bar"],
        )


if __name__ == "__main__":
    test = WindowBoundaryTest()
    sys.exit(test.main())
