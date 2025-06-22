#!/usr/bin/env python3
"""
Line-start with word-boundary test for omega_match.
This is a Python version of the aio_line_start_wb.sh bash script.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class LineStartWordBoundaryTest(OmegaMatchTest):
    """Line-start with word-boundary test for omega_match."""

    def run_test(self):
        """Run the test."""
        # Define file paths
        patterns_file = self.data_dir / "line_anchor_patterns.txt"
        haystack_file = self.data_dir / "line_anchor_haystack.txt"
        expected_file = self.data_dir / "expected_line_start_word_boundary.txt"

        # Run the matcher test with line-start and word-boundary options
        self.run_matcher_test(
            patterns_file,
            haystack_file,
            expected_file,
            extra_args=["--line-start", "--word-boundary", "--longest", "--no-overlap"]
        )

if __name__ == "__main__":
    test = LineStartWordBoundaryTest()
    sys.exit(test.main())
