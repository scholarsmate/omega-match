#!/usr/bin/env python3
"""
Longest no-overlap with case-insensitive test for omega_match.
This is a Python version of the aio_longest_no_overlap_ci.sh bash script.
"""

import sys
import tempfile
import subprocess
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class LongestNoOverlapCiTest(OmegaMatchTest):
    """Longest no-overlap with case-insensitive test for omega_match."""

    def run_test(self):
        """Run the test."""

        # Run the matcher test with the appropriate options
        self.run_matcher_test(
            self.data_dir / "names.txt",
            self.data_dir / "kjv.txt",
            self.data_dir / "grep_found-ci.txt",
            extra_args=["--longest", "--no-overlap", "--ignore-case"]
        )

if __name__ == "__main__":
    test = LongestNoOverlapCiTest()
    sys.exit(test.main())
