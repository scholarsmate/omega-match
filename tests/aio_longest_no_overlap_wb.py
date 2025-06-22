#!/usr/bin/env python3
"""
Longest no-overlap with word-boundary test for omega_match.
This is a Python version of the aio_longest_no_overlap_wb.sh bash script.
"""

import sys
import tempfile
import subprocess
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class LongestNoOverlapWbTest(OmegaMatchTest):
    """Longest no-overlap with word-boundary test for omega_match."""

    def run_test(self):
        """Run the test."""

        # Run the matcher test with the appropriate options
        self.run_matcher_test(
            self.data_dir / "names.txt",
            self.data_dir / "kjv.txt",
            self.data_dir / "grep_found-wb.txt",
            extra_args=["--longest", "--no-overlap", "--word-boundary"]
        )

if __name__ == "__main__":
    test = LongestNoOverlapWbTest()
    sys.exit(test.main())
