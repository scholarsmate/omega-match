#!/usr/bin/env python3
"""
CLI robustness tests for omega_match.

Covers failure-path behavior of the olm CLI: failed compiles must exit
nonzero without leaving output behind, corrupt compiled files must fail
cleanly (including with --verbose), patterns that normalize to nothing must
be skipped rather than aborting, and match lines longer than the output
buffer must be printed intact.
"""

import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest


class CliRobustnessTest(OmegaMatchTest):
    """CLI failure-path and output robustness tests."""

    def olm(self, *args, check=False):
        return self.run_command([str(self.bin_path), *map(str, args)],
                                check=check)

    def match_lines(self, tmp_path, compiled_or_patterns, haystack_bytes,
                    extra_args=()):
        haystack_file = tmp_path / "haystack.bin"
        output_file = tmp_path / "output.txt"
        haystack_file.write_bytes(haystack_bytes)
        self.olm("match", "--output", output_file, *extra_args,
                 compiled_or_patterns, haystack_file, check=True)
        return output_file.read_bytes().splitlines()

    def run_test(self):
        """Run the test."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # 1. Compiling a missing patterns file must exit nonzero and not
            #    leave an output file behind
            out = tmp_path / "out.olm"
            result = self.olm("compile", out, tmp_path / "missing.txt")
            if result.returncode == 0:
                raise AssertionError(
                    "compile of a missing patterns file must exit nonzero")
            if out.exists():
                raise AssertionError(
                    "failed compile must not leave an output file behind")
            self.logger.info("failed compile exits nonzero: OK")

            # 2. A corrupt compiled file (valid magic, truncated header) must
            #    fail cleanly with --verbose, not crash
            corrupt = tmp_path / "corrupt.olm"
            corrupt.write_bytes(b"0MGM4tCH")
            hay = tmp_path / "hay.txt"
            hay.write_bytes(b"hello")
            result = self.olm("match", "--verbose", corrupt, hay)
            if result.returncode != 1:
                raise AssertionError(
                    f"corrupt matcher with --verbose: expected exit 1, "
                    f"got {result.returncode}")
            self.logger.info("corrupt matcher fails cleanly: OK")

            # 3. Patterns that normalize to nothing (all punctuation with
            #    --ignore-punctuation) are skipped, not fatal
            pats = tmp_path / "punct_patterns.txt"
            pats.write_bytes(b"!!!\nfoo\n")
            out2 = tmp_path / "out2.olm"
            result = self.olm("compile", "--ignore-punctuation", out2, pats)
            if result.returncode != 0:
                raise AssertionError(
                    "compile with a fully-punctuation pattern must succeed")
            lines = self.match_lines(tmp_path, out2, b"say foo!")
            if lines != [b"4:foo"]:
                raise AssertionError(
                    f"expected [b'4:foo'], got {lines!r}")
            self.logger.info("zero-length normalized pattern skipped: OK")

            # 4. A match line longer than the CLI's 256KB output buffer is
            #    printed intact
            long_pat = b"A" * 300_000
            pats3 = tmp_path / "long_pattern.txt"
            pats3.write_bytes(long_pat + b"\n")
            lines = self.match_lines(tmp_path, pats3,
                                     b"zz" + long_pat + b"zz")
            if lines != [b"2:" + long_pat]:
                raise AssertionError(
                    f"long match line corrupted: got {len(lines)} line(s), "
                    f"first {lines[0][:40]!r}... len "
                    f"{len(lines[0]) if lines else 0}")
            self.logger.info("long match line printed intact: OK")


if __name__ == "__main__":
    test = CliRobustnessTest()
    sys.exit(test.main())
