# omega_match

[![CI/CD Pipeline](https://github.com/scholarsmate/omega-match/actions/workflows/ci.yml/badge.svg)](https://github.com/scholarsmate/omega-match/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/omega_match.svg)](https://badge.fury.io/py/omega_match)
[![Python versions](https://img.shields.io/pypi/pyversions/omega_match.svg)](https://pypi.org/project/omega_match/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

High-performance multi-string matcher with native C backend.

## Cross-Platform Support

This package includes native libraries for Linux, macOS, and Windows.

## Installation

### Quick Install

```bash
pip install omega_match
```

### Recommended: Using Virtual Environments

Using a virtual environment is recommended to avoid conflicts with other packages and ensure a clean installation.

#### On Linux/macOS

```bash
# Create a virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Install omega_match
pip install omega_match

# Verify installation
python -c "from omega_match.omega_match import get_version; print('Version:', get_version())"

# When done, deactivate the environment
deactivate
```

#### On Windows

**Using Command Prompt:**
```cmd
# Check available Python versions (optional)
py -0

# Create a virtual environment (using latest Python 3)
py -3 -m venv .venv

# Or specify a specific version if you have multiple
py -3.11 -m venv .venv

# Activate the virtual environment
.venv\Scripts\activate

# Install omega_match
pip install omega_match

# Verify installation
python -c "from omega_match.omega_match import get_version; print('Version:', get_version())"

# When done, deactivate the environment
deactivate
```

**Using PowerShell:**
```powershell
# Check available Python versions (optional)
py -0

# Create a virtual environment (using latest Python 3)
py -3 -m venv .venv

# Or specify a specific version if you have multiple
py -3.11 -m venv .venv

# Activate the virtual environment
.venv\Scripts\Activate.ps1

# Install omega_match
pip install omega_match

# Verify installation
python -c "from omega_match.omega_match import get_version; print('Version:', get_version())"

# When done, deactivate the environment
deactivate
```

## Development and Contributing

### Local Development Setup

**On Linux/macOS:**
```bash
# Clone the repository with submodules
git clone --recursive <repository-url>
cd omega_match

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build native libraries and install in development mode
./build.sh

# Run tests
pytest

# Run tests with coverage
pytest --cov=omega_match --cov-report=html
```

**On Windows:**
```powershell
# Clone the repository with submodules
git clone --recursive <repository-url>
cd omega_match

# Create and activate virtual environment
py -3 -m venv venv
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Build native libraries and install in development mode (requires Git Bash or WSL)
./build.sh

# Run tests
pytest

# Run tests with coverage
pytest --cov=omega_match --cov-report=html
```

### CI/CD Pipeline

This project uses GitHub Actions for continuous integration and automated wheel building:

- **Pull Request Workflow**: Runs tests, linting, and security checks on all supported platforms
- **CI/CD Pipeline**: Builds cross-platform packages and creates GitHub releases with wheels
- **Release Workflow**: Creates releases with proper versioning and wheel attachments

#### Setting up CI/CD

1. Fork/clone this repository
2. Set up Personal Access Token for private submodule access:
   - `SUBMODULE_TOKEN` for accessing the private `extern/omgmatch` submodule
3. See [`GITHUB_SETUP.md`](GITHUB_SETUP.md) for detailed setup instructions

#### Creating a Release

```bash
# Create and push a version tag
git tag v0.1.0
git push origin v0.1.0
```

This will automatically trigger the CI/CD pipeline to build cross-platform wheels and attach them to a GitHub release.

### Code Quality

The project enforces code quality through:
- **Black** for code formatting
- **isort** for import sorting  
- **flake8** for linting
- **mypy** for type checking
- **bandit** for security scanning
- **pytest** with coverage reporting

Run quality checks locally:
```bash
# Format code
black olm.py omega_match/ tests/
isort olm.py omega_match/ tests/

# Lint code
flake8 olm.py omega_match/ tests/ --max-line-length=88 --extend-ignore=E203,W503

# Type checking
mypy olm.py omega_match/ --ignore-missing-imports

# Security scan
bandit -r olm.py omega_match/
```

## Quick Start

```python
import omega_match.omega_match as om

# Get library version
print(f"Library version: {om.get_version()}")

# Create a matcher and add patterns
with om.Compiler("patterns.omg") as compiler:
    compiler.add_pattern(b"pattern1")
    compiler.add_pattern(b"pattern2")

# Create matcher from compiled patterns
matcher = om.Matcher("patterns.omg")

# Search for patterns in text
results = matcher.match(b"some text with pattern1 in it")
for result in results:
    print(f"Found: {result.match} at offset {result.offset}")
```

## olm.py

`olm.py` is a command-line tool for compiling pattern lists and matching them against text files using the omega_match engine. It provides two main modes:

- **compile**: Compile a list of patterns into a fast matcher file.
- **match**: Search for patterns in a haystack file using a compiled matcher.

### Usage

```bash
# Compile patterns from a file into a matcher
python olm.py compile patterns.omg patterns.txt

# Match patterns in a haystack file
python olm.py match patterns.omg haystack.txt
```

**Commands:**

-  `compile`    Compile patterns
-  `match`      Match patterns

**Compile Command Options:**

- `--ignore-case`         Ignore case in patterns
- `--ignore-punctuation`  Ignore punctuation in patterns
- `--elide-whitespace`    Remove whitespace in patterns
- `-v, --verbose`         Enable verbose output
- `-h, --help`            Show this help message

**Match Command Options:**

- `-o, --output FILE`     Write results to FILE instead of stdout (UTF-8 and LF EOL)
- `--ignore-case`         Ignore case during matching
- `--ignore-punctuation`  Ignore punctuation during matching
- `--elide-whitespace`    Remove whitespace during matching
- `--longest`             Only return longest matches
- `--no-overlap`          Avoid overlapping matches
- `--word-boundary`       Only match at word boundaries
- `--word-prefix`         Only match at word prefixes
- `--word-suffix`         Only match at word suffixes
- `--line-start`          Only match at the start of a line
- `--line-end`            Only match at the end of a line
- `--threads N`           Number of threads to use
- `--chunk-size N`        Chunk size for parallel processing
- `-v, --verbose`         Enable verbose output
- `-h, --help`            Show this help message

### Example

```bash
# Compile a pattern list
python olm.py compile mypatterns.omg mypatterns.txt --ignore-case --elide-whitespace -v

# Match patterns in a file
python olm.py match mypatterns.omg input.txt --longest --no-overlap --threads 4 -v
```

The output will list each match as `offset:matched_text` (one per line, with Unix-style newlines).
