"""OmegaMatch Python bindings with automatic PGO variant selection."""

from .omega_match import (
    Compiler,
    Matcher,
    MatchResult,
    MatchStats,
    PatternStoreStats,
    get_version,
    get_library_info,
)

__all__ = [
    "Compiler",
    "Matcher",
    "MatchResult",
    "MatchStats",
    "PatternStoreStats",
    "get_version",
    "get_library_info",
]
