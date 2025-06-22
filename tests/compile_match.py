#!/usr/bin/env python3
"""
Compile and match test for omega_match.
This is a Python version of the compile_match.sh bash script.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class CompileMatchTest(OmegaMatchTest):
    """Compile and match test for omega_match."""

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
