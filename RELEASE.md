# Release Instructions

This document outlines the process for creating and publishing releases of omega_match.

## Version Numbering

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality in a backwards-compatible manner
- **PATCH**: Backwards-compatible bug fixes

## Release Process

### 1. Prepare the Release

1. Version is now automatically extracted from git tags. The CMake build system will:
   - First try to extract version from the latest git tag (e.g., `v1.0.0`)
   - Fall back to hardcoded version in CMakeLists.txt if git is unavailable or no tags exist
   - This ensures release artifacts always match the git tag version

   Manual version update is only needed if not using git tags:
   ```cmake
   set(PROJECT_VERSION_MAJOR X)
   set(PROJECT_VERSION_MINOR Y)
   set(PROJECT_VERSION_PATCH Z)
   ```

2. Update `CHANGELOG.md` with:
   - New version number and date
   - Summary of changes
   - Move unreleased changes to the new version section


3. Test the build:
   ```bash
   cmake --preset release
   cmake --build --preset release
   ctest --test-dir build-gcc-release --output-on-failure
   ```

4. Run performance tests:
   ```bash
   python perf_test.py
   ```

### 2. Create and Tag the Release

1. Commit all changes:
   ```bash
   git add .
   git commit -m "Release v1.0.0"
   ```

2. Create and push the tag:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin main
   git push origin v1.0.0
   ```

### 3. Automated Release

The GitHub Actions workflow will automatically:
- Build cross-platform binaries
- Run the complete test suite
- Create platform-specific packages (DEB, RPM, TGZ, WIX)
- Upload artifacts to the GitHub release

## Release Checklist

- [ ] Version updated in CMakeLists.txt
- [ ] CHANGELOG.md updated
- [ ] All tests pass
- [ ] Performance benchmarks run successfully
- [ ] Documentation is up to date
- [ ] License files are current
- [ ] Git tag created and pushed
- [ ] GitHub release created
- [ ] Release artifacts verified

## Post-Release

1. Verify the release on GitHub
2. Test installation from packages
3. Update any dependent projects
4. Announce the release (if applicable)
