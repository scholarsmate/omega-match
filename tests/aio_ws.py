#!/usr/bin/env python3
"""
Word-suffix test for omega_match.
This is a Python version of the aio_ws.sh bash script.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import omega_test
sys.path.insert(0, str(Path(__file__).parent))
from omega_test import OmegaMatchTest

class WordSuffixTest(OmegaMatchTest):
    """Word-suffix test for omega_match."""

    def run_test(self):
        """Run the test."""
        # Define file paths
        patterns_file = self.data_dir / "tlds.txt"
        haystack_file = self.data_dir / "haystack_email.txt"
        expected_file = self.data_dir / "expected_word_suffix.txt"

        # Run the matcher test with the word-suffix option
        self.run_matcher_test(
            patterns_file,
            haystack_file,
            expected_file,
            extra_args=["--word-suffix"]
        )

if __name__ == "__main__":
    test = WordSuffixTest()
    sys.exit(test.main())
