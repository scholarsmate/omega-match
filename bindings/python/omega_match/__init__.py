"""OmegaMatch Python bindings with automatic PGO variant selection."""

from .omega_match import (
    BuiltinReactor,
    BuiltinReactorRule,
    Compiler,
    Matcher,
    MatchResult,
    MatchStats,
    NativePluginReactor,
    PatternStoreStats,
    Reactor,
    ReactorEmission,
    ReactorSideEffect,
    RewriteAction,
    RewriteScript,
    RewriteScriptOp,
    get_version,
    get_library_info,
)

__all__ = [
    "BuiltinReactor",
    "BuiltinReactorRule",
    "Compiler",
    "Matcher",
    "MatchResult",
    "MatchStats",
    "NativePluginReactor",
    "PatternStoreStats",
    "Reactor",
    "ReactorEmission",
    "ReactorSideEffect",
    "RewriteAction",
    "RewriteScript",
    "RewriteScriptOp",
    "get_version",
    "get_library_info",
]
