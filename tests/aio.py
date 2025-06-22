#!/usr/bin/env python3
"""
All-in-one test for omega_match.
This is a Python version of the aio.sh bash script.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class AioTest(OmegaMatchTest):
    """All-in-one test for omega_match."""

    def run_test(self):
        """Run the test."""
        # Define file paths
        patterns_file = self.data_dir / "names.txt"
        haystack_file = self.data_dir / "kjv.txt"
        expected_file = self.data_dir / "matcher_found.txt"

        # Run the basic matcher test without any extra arguments
        self.run_matcher_test(patterns_file, haystack_file, expected_file)

if __name__ == "__main__":
    test = AioTest()
    sys.exit(test.main())
