#!/usr/bin/env python3
"""
Longest no-overlap test for omega_match.
This is a Python version of the aio_longest_no_overlap.sh bash script.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class LongestNoOverlapTest(OmegaMatchTest):
    """Longest no-overlap test for omega_match."""

    def run_test(self):
        """Run the test."""

        # Run the matcher test with longest and no-overlap options
        self.run_matcher_test(
            self.data_dir / "names.txt",
            self.data_dir / "kjv.txt",
            self.data_dir / "grep_found.txt",
            extra_args=["--longest", "--no-overlap"]
        )

if __name__ == "__main__":
    test = LongestNoOverlapTest()
    sys.exit(test.main())
