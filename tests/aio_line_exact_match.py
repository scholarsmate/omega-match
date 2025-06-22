#!/usr/bin/env python3
"""
Line exact match test for omega_match.
This is a Python version of the aio_line_exact_match.sh bash script.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class LineExactMatchTest(OmegaMatchTest):
    """Line exact match test for omega_match."""

    def run_test(self):
        """Run the test."""
        # Define file paths
        patterns_file = self.data_dir / "line_exact_match_patterns.txt"
        haystack_file = self.data_dir / "line_exact_match_haystack.txt"
        expected_file = self.data_dir / "expected_line_exact_match.txt"

        # Run the matcher test with line-start and line-end options
        self.run_matcher_test(
            patterns_file,
            haystack_file,
            expected_file,
            extra_args=["--line-start", "--line-end", "--longest", "--no-overlap"]
        )

if __name__ == "__main__":
    test = LineExactMatchTest()
    sys.exit(test.main())
