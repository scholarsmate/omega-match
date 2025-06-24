# Contributing to omega_match

We welcome contributions to the `omega_match` Python bindings!

## Local Development Setup

First, clone the repository and its submodules:

```bash
git clone --recursive https://github.com/scholarsmate/omega-match.git
cd omega-match/bindings/python
```

### On Linux/macOS:
```bash
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

### On Windows:
```powershell
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

## Code Quality

The project enforces code quality through a suite of tools. Please run these checks locally before submitting a pull request.

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

## CI/CD Pipeline

This project uses GitHub Actions for continuous integration and automated wheel building:

- **Pull Request Workflow**: Runs tests, linting, and security checks on all supported platforms.
- **Release Workflow**: Builds cross-platform packages, creates GitHub releases with wheels, and publishes to PyPI.

### Setting up CI/CD for a Fork

If you fork the repository and want to enable the CI/CD pipeline, you will need to:

1.  Set up a Personal Access Token for private submodule access. Create a repository secret named `SUBMODULE_TOKEN` for accessing the private `extern/omgmatch` submodule.
2.  See the main project's `GITHUB_SETUP.md` for more detailed instructions if needed.

### Creating a Release

Releases are triggered automatically when a new version tag is pushed:

```bash
# Create and push a version tag
git tag v0.1.0
git push origin v0.1.0
```
This will trigger the pipeline to build and publish the release.
