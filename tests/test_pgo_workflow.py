"""Regression tests for the PGO workflow helpers."""

import importlib.util
from pathlib import Path


def load_pgo_workflow():
    """Load the workflow script without requiring scripts to be a package."""
    script = Path(__file__).parents[1] / "scripts" / "pgo_workflow.py"
    spec = importlib.util.spec_from_file_location("pgo_workflow", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_copy_gcc_profile_data_excludes_build_artifacts(tmp_path):
    """Only GCC counters should cross from generate to use builds."""
    workflow = load_pgo_workflow()
    source_dir = (
        tmp_path
        / "build-gcc-pgo-generate"
        / "CMakeFiles"
        / "omega_match_static.dir"
        / "omega_match"
        / "src"
    )
    source_dir.mkdir(parents=True)
    (source_dir / "matcher.c.gcda").write_bytes(b"profile-data")
    (source_dir / "matcher.c.o").write_bytes(b"instrumented-object")
    (source_dir / "flags.make").write_text("instrumented flags")

    stale_dir = (
        tmp_path
        / "build-gcc-pgo-use"
        / "CMakeFiles"
        / "stale.dir"
    )
    stale_dir.mkdir(parents=True)
    (stale_dir / "old.gcda").write_bytes(b"stale-profile")

    assert workflow.copy_gcc_profile_data(tmp_path)

    use_cmake_files = tmp_path / "build-gcc-pgo-use" / "CMakeFiles"
    copied_profile = (
        use_cmake_files
        / "omega_match_static.dir"
        / "omega_match"
        / "src"
        / "matcher.c.gcda"
    )
    assert copied_profile.read_bytes() == b"profile-data"
    assert not (stale_dir / "old.gcda").exists()
    assert not list(use_cmake_files.rglob("*.o"))
    assert not list(use_cmake_files.rglob("flags.make"))
