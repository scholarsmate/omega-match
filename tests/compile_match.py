#!/usr/bin/env python3
"""
Compile and match test for omega_match.
This is a Python version of the compile_match.sh bash script.
"""

import os
import struct
import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class CompileMatchTest(OmegaMatchTest):
    """Compile and match test for omega_match."""

    HEADER_FORMAT = "<8sIIQ10I2f"

    def assert_v4_alignment(self, compiled_file):
        """Verify naturally aligned offsets in a newly compiled v4 file."""
        data = compiled_file.read_bytes()
        header_size = struct.calcsize(self.HEADER_FORMAT)
        header = struct.unpack_from(self.HEADER_FORMAT, data)
        version = header[1]
        flags = header[2]
        pattern_store_size = header[3]
        bloom_filter_size = header[7]
        hash_buckets_size = header[8]
        table_size = header[9]
        short_matcher_size = header[13]
        if version < 4:
            raise AssertionError(f"expected compiled format v4+, got v{version}")

        offset = header_size + pattern_store_size
        if offset % 8 or data[offset:offset + 8] != b"0MG8L0oM":
            raise AssertionError(f"unaligned/invalid Bloom header at {offset}")
        offset += 8 + 4 + 4  # magic, bit size, v4 reserved alignment word
        if offset % 8:
            raise AssertionError(f"unaligned Bloom bits at {offset}")
        offset += bloom_filter_size
        if offset % 8 or data[offset:offset + 8] != b"0MG*H4sH":
            raise AssertionError(f"unaligned/invalid hash header at {offset}")
        offset += 8 + table_size
        if offset % 4:
            raise AssertionError(f"unaligned hash index at {offset}")
        offset += table_size * 4
        if offset % 8:
            raise AssertionError(f"unaligned hash buckets at {offset}")
        offset += hash_buckets_size
        if short_matcher_size:
            if offset % 8 or data[offset:offset + 8] != b"0MG5HOrT":
                raise AssertionError(
                    f"unaligned/invalid short matcher at {offset}"
                )
            short_start = offset
            if flags & (1 << 4):
                p = short_start + 8 + 32 + 8192
                len1, len2, len3, len4 = struct.unpack_from("<4I", data, p)
                del len1, len2
                p += 16 + (len3 + len4) * 4
                p += (-p) % 8
                if p % 8:
                    raise AssertionError(f"unaligned one-byte keys at {p}")
                p += 256 * 8
                len2_keyed = struct.unpack_from("<I", data, p)[0]
                p += 4 + len2_keyed * 4
                p += (-p) % 8
                if p % 8:
                    raise AssertionError(f"unaligned two-byte keys at {p}")
                p += len2_keyed * 8
                if p % 8:
                    raise AssertionError(f"unaligned three-byte keys at {p}")
                p += len3 * 8
                if p % 8:
                    raise AssertionError(f"unaligned four-byte keys at {p}")
                p += len4 * 8
                if p != short_start + short_matcher_size:
                    raise AssertionError(
                        "keyed short matcher extent does not match header"
                    )
            offset += short_matcher_size
        if offset != len(data):
            raise AssertionError(
                f"compiled layout ended at {offset}, file size is {len(data)}"
            )

    def run_test(self):
        """Run the test."""
        # Define file paths
        patterns_file = self.data_dir / "names.txt"
        haystack_file = self.data_dir / "kjv.txt"
        expected_file = self.data_dir / "matcher_found.txt"

        # Create a temporary file for the compiled patterns
        with tempfile.NamedTemporaryFile(delete=False, suffix=self.args.compiled_ext) as temp_file:
            compiled_file = Path(temp_file.name)

        try:
            # First compile the patterns
            self.logger.info(f"Compiling patterns from {patterns_file} to {compiled_file}")
            self.run_command([
                self.bin_path,
                "compile",
                str(compiled_file),
                str(patterns_file)
            ], check=True)

            # Verify the compiled file exists and has size
            if not compiled_file.exists() or os.path.getsize(compiled_file) == 0:
                self.logger.error(f"Failed to create compiled file: {compiled_file}")
                return 1
            self.assert_v4_alignment(compiled_file)

            # Exercise the pattern-store padding path: a single five-byte long
            # pattern otherwise leaves every following mmap section unaligned.
            with tempfile.TemporaryDirectory() as align_tmp:
                align_tmp = Path(align_tmp)
                align_patterns = align_tmp / "patterns.txt"
                align_compiled = align_tmp / "patterns.olm"
                align_patterns.write_bytes(b"abcde\nxy\n")
                self.run_command([
                    self.bin_path,
                    "compile",
                    str(align_compiled),
                    str(align_patterns),
                ], check=True)
                self.assert_v4_alignment(align_compiled)

            # Exercise both v4 key-array padding points: an odd combined
            # three/four-byte count and an even two-byte keyed count.
            with tempfile.TemporaryDirectory() as keyed_tmp:
                keyed_tmp = Path(keyed_tmp)
                keyed_patterns = keyed_tmp / "patterns.txt"
                keyed_compiled = keyed_tmp / "patterns.olm"
                keyed_patterns.write_bytes(
                    b"1\tA\n2\tBC\n3\tDEF\n4\tGHIJ\n5\tKLMNO\n"
                    b"6\tXYZ\n7\tPQ\n"
                )
                self.run_command([
                    self.bin_path,
                    "compile",
                    "--keyed",
                    str(keyed_compiled),
                    str(keyed_patterns),
                ], check=True)
                self.assert_v4_alignment(keyed_compiled)

            # Now run the matcher with the compiled patterns
            self.logger.info(f"Running matcher with compiled patterns file")
            self.run_matcher_test(
                compiled_file,
                haystack_file,
                expected_file
            )
        finally:
            # Clean up the temporary file
            if compiled_file.exists():
                compiled_file.unlink()

if __name__ == "__main__":
    test = CompileMatchTest()
    sys.exit(test.main())
