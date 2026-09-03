"""Regression tests for the scaling benchmark helpers."""

import importlib.util
import sys
from pathlib import Path

import pytest


def load_benchmark_scaling():
    """Load the benchmark script without requiring scripts to be a package."""
    script = Path(__file__).parents[1] / "scripts" / "benchmark_scaling.py"
    spec = importlib.util.spec_from_file_location("benchmark_scaling", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("source", (("olm-pgo-compile+match", "compile+match", "names.txt"),)),
        ("compiled", (("olm-pgo-match-only", "match-only", "patterns.olm"),)),
        (
            "both",
            (
                ("olm-pgo-compile+match", "compile+match", "names.txt"),
                ("olm-pgo-match-only", "match-only", "patterns.olm"),
            ),
        ),
    ),
)
def test_build_tools_selects_olm_pattern_setup(mode, expected, tmp_path):
    benchmark = load_benchmark_scaling()
    binary = tmp_path / "olm"
    source = tmp_path / "names.txt"
    compiled = tmp_path / "patterns.olm"

    tools = benchmark.build_tools(
        [("pgo", binary)],
        {} if mode == "source" else {"pgo": compiled},
        source,
        {},
        8,
        mode,
        False,
        False,
    )

    actual = tuple(
        (
            tool.name,
            tool.pattern_setup,
            Path(tool.command("line-start", tmp_path / "haystack", False)[-2]).name,
        )
        for tool in tools
    )
    assert actual == expected
