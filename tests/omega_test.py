#!/usr/bin/env python3
"""
Base test class for omega_match tests.
"""

import argparse
import logging
import os
import subprocess
import sys
import tempfile
import filecmp
from abc import ABC, abstractmethod
from pathlib import Path

class OmegaMatchTest(ABC):
    """Base class for omega_match tests."""

    def __init__(self):
        """Initialize the test."""
        self.args = None
        self.bin_path = None
        self.data_dir = None
        self.logger = None
        self.setup_logging()
        self.parse_args()
        self.validate_args()

    def setup_logging(self):
        """Set up logging."""
        self.logger = logging.getLogger(self.__class__.__name__)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def parse_args(self):
        """Parse command line arguments."""
        parser = argparse.ArgumentParser(description='Run omega_match test.')
        parser.add_argument('bin_path', help='Path to the olm executable')
        parser.add_argument('data_dir', help='Path to the data directory')
        parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
        parser.add_argument('--no-valgrind', action='store_true', help='Disable valgrind')
        parser.add_argument('--compiled-ext', default='.olm', help='Default extension for compiled pattern files')

        self.args = parser.parse_args()

        if self.args.verbose:
            self.logger.setLevel(logging.DEBUG)

        self.bin_path = Path(self.args.bin_path)
        self.data_dir = Path(self.args.data_dir)

    def validate_args(self):
        """Validate command line arguments."""
        # Ensure the binary exists
        if not self.bin_path.exists() or not os.access(self.bin_path, os.X_OK):
            self.logger.error(f"Binary not found or not executable: {self.bin_path}")
            sys.exit(1)

        # Ensure data directory exists
        if not self.data_dir.is_dir():
            self.logger.error(f"Data directory not found: {self.data_dir}")
            sys.exit(1)

    def run_command(self, cmd, use_valgrind=False, check=True, capture_output=True):
        if use_valgrind:
            valgrind_cmd = ['valgrind', '--leak-check=full', '--error-exitcode=1']
            cmd = valgrind_cmd + cmd

        # Log the command being run
        self.logger.info(f"Running command: {cmd}")
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        return result

    def validate_files(self, file_dict):
        """Validate that the specified files exist.

        Args:
            file_dict: Dictionary mapping file paths to descriptions
        """
        for file_path, desc in file_dict.items():
            if not file_path.is_file():
                self.logger.error(f"{desc} not found: {file_path}")
                sys.exit(1)

    def run_matcher_test(self, patterns_file, haystack_file, expected_file, extra_args=None):
        """Run a matcher test with the specified files.

        Args:
            patterns_file: Path to the patterns file
            haystack_file: Path to the haystack file
            expected_file: Path to the expected output file
            extra_args: Additional arguments to pass to the matcher
        """
        # Validate input files
        self.validate_files({
            patterns_file: "Patterns file",
            haystack_file: "Haystack file",
            expected_file: "Expected output file"
        })

        # Create temporary file for output
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_file = Path(temp_file.name)

        # Build command
        cmd = [self.bin_path, "match", "--output", str(output_file)]

        if extra_args:
            cmd.extend(extra_args)
        cmd.extend([str(patterns_file), str(haystack_file)])

        try:
            # Run the matcher and capture output
            self.logger.info(f"Running matcher on {patterns_file} and {haystack_file}")
            result = self.run_command(cmd, check=True, capture_output=False)

            # Compare the output
            self.logger.info(f"Comparing output to {expected_file}")
            if not filecmp.cmp(output_file, expected_file):
                self.logger.error("Output does not match expected output")
                # Keep temporary output file for debugging
                debug_output = output_file.with_suffix('.debug')
                output_file.rename(debug_output)
                self.logger.error(f"Output saved to {debug_output}")
                sys.exit(1)

            self.logger.info("Test passed!")
        finally:
            # Clean up
            if output_file.exists():
                output_file.unlink()

    @abstractmethod
    def run_test(self):
        """Run the test. Must be implemented by subclasses."""
        pass

    def main(self):
        """Main entry point."""
        try:
            self.run_test()
            self.logger.info("Test passed!")
            return 0
        except Exception as e:
            self.logger.exception(f"Test failed: {e}")
            return 1

if __name__ == "__main__":
    print("This is a base class and should not be run directly.")
    sys.exit(1)
