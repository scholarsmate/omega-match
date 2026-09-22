#!/usr/bin/env python3
"""
CLI robustness tests for omega_match.

Covers failure-path behavior of the olm CLI: failed compiles must exit
nonzero without leaving output behind, corrupt compiled files must fail
cleanly (including with --verbose), patterns that normalize to nothing must
be skipped rather than aborting, and match lines longer than the output
buffer must be printed intact.
"""

import os
import subprocess
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

            # 5. Maximum-width offsets/keys must retain their exact decimal
            #    representation after the fast integer-formatting path.
            keyed_patterns = tmp_path / "keyed_patterns.txt"
            keyed_compiled = tmp_path / "keyed_patterns.olm"
            keyed_patterns.write_bytes(b"18446744073709551615\ttarget\n")
            self.olm("compile", "--keyed", keyed_compiled, keyed_patterns,
                     check=True)
            lines = self.match_lines(
                tmp_path, keyed_compiled, b"xx target yy",
                extra_args=("--show-keys",),
            )
            if lines != [b"3:18446744073709551615:target"]:
                raise AssertionError(f"maximum key output corrupted: {lines!r}")
            self.logger.info("maximum-width keyed output: OK")

            # 6. SIMD skips and the manual OpenMP chunk loop must preserve
            #    matches around 16-byte and explicit chunk boundaries.
            boundary_patterns = tmp_path / "boundary_patterns.txt"
            boundary_patterns.write_bytes(b"foo\nbar\n")
            boundary_haystack = b"x" * 15 + b"\nfoo xbar bar\nfoo"
            probe_haystack = tmp_path / "parallel_probe.bin"
            probe_output = tmp_path / "parallel_probe.txt"
            probe_haystack.write_bytes(b"target")
            parallel_probe = self.olm(
                "match", "--output", probe_output, "--threads", "2",
                keyed_compiled, probe_haystack,
            )
            thread_args = (("--threads", "2")
                           if parallel_probe.returncode == 0 else ())
            for chunk_size in (8, 16, 32, 1_048_576):
                common_args = (*thread_args, "--chunk-size", str(chunk_size))
                lines = self.match_lines(
                    tmp_path, boundary_patterns, boundary_haystack,
                    extra_args=(*common_args, "--line-start"),
                )
                if lines != [b"16:foo", b"29:foo"]:
                    raise AssertionError(
                        f"line-start scan changed for chunk {chunk_size}: "
                        f"{lines!r}")
                lines = self.match_lines(
                    tmp_path, boundary_patterns, boundary_haystack,
                    extra_args=(*common_args, "--word-boundary"),
                )
                if lines != [b"16:foo", b"25:bar", b"29:foo"]:
                    raise AssertionError(
                        f"word-boundary scan changed for chunk {chunk_size}: "
                        f"{lines!r}")
            self.logger.info("SIMD and chunk-boundary traversal: OK")

            # 7. OpenMP may legally create fewer workers than requested when
            #    dynamic teams are enabled. Null result slots for workers that
            #    were not created must not cause finalization to crash.
            dynamic_output = tmp_path / "dynamic_output.txt"
            dynamic_haystack = tmp_path / "dynamic_haystack.bin"
            dynamic_haystack.write_bytes(b"target " * 4096)
            dynamic_env = os.environ.copy()
            dynamic_env.update({
                "OMP_DYNAMIC": "TRUE",
                "OMP_NUM_THREADS": "8",
                "OMP_THREAD_LIMIT": "1",
            })
            dynamic_thread_args = ("--threads", "2") if thread_args else ()
            result = subprocess.run(
                [str(self.bin_path), "match", "--output", str(dynamic_output),
                 *dynamic_thread_args, str(keyed_compiled),
                 str(dynamic_haystack)],
                check=False, capture_output=True, text=True, env=dynamic_env,
            )
            if result.returncode != 0:
                raise AssertionError(
                    "dynamic OpenMP team match failed with exit "
                    f"{result.returncode}: {result.stderr}")
            dynamic_lines = dynamic_output.read_bytes().splitlines()
            if (len(dynamic_lines) != 4096 or
                    dynamic_lines[0] != b"0:target" or
                    dynamic_lines[-1] != b"28665:target"):
                raise AssertionError(
                    f"dynamic OpenMP output corrupted: {len(dynamic_lines)} "
                    "lines")
            self.logger.info("dynamic OpenMP team finalization: OK")

            # 8. Chunk sizes that cannot be represented after power-of-two
            #    rounding must be rejected rather than silently becoming
            #    negative and falling back to the default.
            result = self.olm(
                "match", "--chunk-size", "2147483647", keyed_compiled,
                dynamic_haystack,
            )
            if result.returncode == 0:
                raise AssertionError("overflowing chunk size must be rejected")
            self.logger.info("overflowing chunk size rejected: OK")


if __name__ == "__main__":
    test = CliRobustnessTest()
    sys.exit(test.main())
