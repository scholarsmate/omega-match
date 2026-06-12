# tests/test_omega_match.py

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from olm import (
    _parse_first_keyed_record,
    _parse_keyed_record,
    _parse_uint64_prefix,
    compile_mode,
)
from omega_match.omega_match import (
    BuiltinReactor,
    BuiltinReactorRule,
    Compiler,
    Matcher,
    MatchStats,
    PatternStoreStats,
    NativePluginReactor,
    Reactor,
    ReactorEmission,
    ReactorSideEffect,
    RewriteScript,
    RewriteAction,
    _safe_destroy,
    get_version,
)


def write_file(path, lines):
    path.write_text("\n".join(lines), encoding="utf-8")


def dispatch_results(results, handlers):
    events = []
    for result in results:
        handler = handlers[result.key]
        handler(result, events)
    return events


def get_native_test_plugin_path() -> str:
    native_dir = (
        Path(__file__).resolve().parent.parent / "omega_match" / "native" / "lib"
    )
    if sys.platform.startswith("win"):
        plugin_name = "omega_match_test_reactor_plugin.dll"
    elif sys.platform == "darwin":
        plugin_name = "libomega_match_test_reactor_plugin.dylib"
    else:
        plugin_name = "libomega_match_test_reactor_plugin.so"
    return str(native_dir / plugin_name)


def get_python_binding_root() -> str:
    return str(Path(__file__).resolve().parent.parent)


def run_python_example(tmp_path, script_name: str) -> subprocess.CompletedProcess[str]:
    examples_dir = Path(__file__).resolve().parent.parent / "examples"
    script_path = examples_dir / script_name
    env = os.environ.copy()
    python_root = get_python_binding_root()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        python_root
        if not existing_pythonpath
        else python_root + os.pathsep + existing_pythonpath
    )
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_get_version():
    version = get_version()
    assert isinstance(version, str)
    assert len(version) > 0
    assert version.count(".") == 2
    assert version.replace(".", "").isdigit()


def test_compiler_add_patterns(tmp_path):
    output_path = str(tmp_path / "manual_add.olm")
    with Compiler(output_path, case_insensitive=True) as compiler:
        compiler.add_pattern(b"Alpha")
        compiler.add_pattern(b"Beta")
        stats = compiler.get_stats()
        assert isinstance(stats, PatternStoreStats)
        assert stats.stored_pattern_count == 1
        assert stats.short_pattern_count == 1
        assert stats.total_input_bytes == 9
        assert stats.total_stored_bytes == 5
        assert stats.smallest_pattern_length == 4
        assert stats.largest_pattern_length == 5

    # Load the compiled matcher and match
    with Matcher(output_path, case_insensitive=True) as m:
        hay = b"alpha beta gamma"
        results = m.match(hay)
        assert len(results) == 2
        assert results[0].match.lower() in [b"alpha", b"beta"]


def test_compile_and_match(tmp_path):
    patterns = ["foo", "bar", "bazinga"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)

    compiled_file = str(tmp_path / "matcher.olm")
    ps_stats = Compiler.compile_from_filename(compiled_file, str(pat_file))
    assert isinstance(ps_stats, PatternStoreStats)
    assert ps_stats.smallest_pattern_length == 3
    assert ps_stats.largest_pattern_length == 7
    assert ps_stats.stored_pattern_count == 1
    assert ps_stats.short_pattern_count == 2
    assert ps_stats.total_input_bytes == 13
    assert ps_stats.total_stored_bytes == 7

    with Matcher(compiled_file) as m2:
        haystack = b"xx foobar yy foo zz bar"
        results = m2.match(haystack)
        offsets = [r.offset for r in results]
        lengths = [r.length for r in results]
        matches = [r.match for r in results]
        assert offsets == [3, 6, 13, 20]
        assert lengths == [3, 3, 3, 3]
        assert matches == [b"foo", b"bar", b"foo", b"bar"]

        m_stats = m2.get_match_stats()
        assert isinstance(m_stats, MatchStats)
        assert m_stats.total_hits == len(matches)
        m2.reset_match_stats()
        assert m2.get_match_stats() == MatchStats(0, 0, 0, 0, 0)


def test_compile_from_buffer_and_match(tmp_path):
    pattern_buffer = b"foo\nbar\nbazinga"
    compiled_file = str(tmp_path / "matcher.olm")
    ps_stats = Compiler.compile_from_buffer(compiled_file, pattern_buffer)
    assert isinstance(ps_stats, PatternStoreStats)
    assert ps_stats.smallest_pattern_length == 3
    assert ps_stats.largest_pattern_length == 7
    assert ps_stats.stored_pattern_count == 1
    assert ps_stats.short_pattern_count == 2
    assert ps_stats.total_input_bytes == 13
    assert ps_stats.total_stored_bytes == 7

    with Matcher(compiled_file) as m2:
        haystack = b"xx foobar yy foo zz bar"
        results = m2.match(haystack)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        assert offsets == [3, 6, 13, 20]
        assert matches == [b"foo", b"bar", b"foo", b"bar"]

        m_stats = m2.get_match_stats()
        assert isinstance(m_stats, MatchStats)
        assert m_stats.total_hits == len(matches)
        m2.reset_match_stats()
        assert m2.get_match_stats() == MatchStats(0, 0, 0, 0, 0)


def test_case_insensitive_matching(tmp_path):
    patterns = ["Foo", "BaR"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file), case_insensitive=True) as m:
        hay = b"foo BAR Baz fooBar"
        results = m.match(hay)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        assert offsets == [0, 4, 12, 15]
        assert matches == [b"foo", b"BAR", b"foo", b"Bar"]


def test_ignore_punctuation_and_case(tmp_path):
    pattern_buffer = b"f'oo\nbar\n"
    compiled_file = str(tmp_path / "matcher.olm")
    Compiler.compile_from_buffer(
        compiled_file, pattern_buffer, ignore_punctuation=True, case_insensitive=True
    )
    with Matcher(str(compiled_file)) as m:
        hay = b"f'oo BAR Baz fooBar"
        results = m.match(hay)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        assert offsets == [0, 5, 13, 16]
        assert matches == [b"f'oo", b"BAR", b"foo", b"Bar"]


def test_no_overlap_and_longest_only(tmp_path):
    patterns = ["abc", "abcd"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        hay = b"xxabcdyy"
        res = m.match(hay)
        assert any(r.match == b"abc" for r in res)
        assert any(r.match == b"abcd" for r in res)

        res2 = m.match(hay, longest_only=True)
        assert all(r.match == b"abcd" for r in res2)

        res3 = m.match(hay, no_overlap=True)
        assert all(r.match == b"abcd" for r in res3)


def test_word_boundary(tmp_path):
    patterns = ["in", "and"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        hay = b"land and inland"
        res_all = m.match(hay)
        assert any(r.match == b"in" for r in res_all)
        assert any(r.match == b"and" for r in res_all)

        res_wb = m.match(hay, word_boundary=True)
        assert len(res_wb) == 1
        assert res_wb[0].match == b"and"
        assert res_wb[0].offset == 5


def test_word_prefix(tmp_path):
    patterns = ["foo", "bar"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        hay = b"foobar foo barbar"
        # Only match at start of word
        results = m.match(hay, word_prefix=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # "foo" at offsets 0 and 7, "bar" at offset 3 and 11 but only prefixes
        assert offsets == [0, 7, 11]
        assert matches == [b"foo", b"foo", b"bar"]


def test_word_suffix(tmp_path):
    patterns = ["foo", "bar"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        hay = b"foofoo toolbar bar"
        # Only match at end of word
        results = m.match(hay, word_suffix=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # "foo" at end of word at offset 3, "bar" at offset 11 and 15
        assert offsets == [3, 11, 15]
        assert matches == [b"foo", b"bar", b"bar"]


def test_set_threads(tmp_path):
    patterns = ["foo", "bar"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        # Try different thread counts, starting with a conservative number
        # OpenMP on some platforms (especially macOS) can be restrictive
        thread_counts_to_try = [2, 1, 4]
        success = False

        for threads in thread_counts_to_try:
            try:
                m.set_threads(threads)
                assert m.get_threads() == threads
                success = True
                break
            except ValueError:
                # This thread count didn't work, try the next one
                continue

        if not success:
            pytest.skip("OpenMP thread setting not supported on this platform")

        m.set_chunk_size(1024)
        assert m.get_chunk_size() == 1024

        haystack = b"xx foobar yy foo zz bar"
        results = m.match(haystack)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        assert offsets == [3, 6, 13, 20]
        assert matches == [b"foo", b"bar", b"foo", b"bar"]

        m.set_threads(0)
        assert m.get_threads() > 0
        m.set_chunk_size(0)
        assert m.get_chunk_size() == 4096

        with pytest.raises(ValueError):
            m.set_threads(-1)
        with pytest.raises(ValueError):
            m.set_chunk_size(-1)


def test_word_prefix_and_boundary(tmp_path):
    patterns = ["foo"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        hay = b"foobar foo foo barfoo"
        # Only match 'foo' at start and as a full word
        results = m.match(hay, word_prefix=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # 'foo' in 'foobar' is prefix but not full word; matches at offsets 7 and 11
        assert offsets == [0, 7, 11]
        assert matches == [b"foo", b"foo", b"foo"]


def test_word_suffix_and_boundary(tmp_path):
    patterns = ["foo"]
    pat_file = tmp_path / "patterns.txt"
    write_file(pat_file, patterns)
    with Matcher(str(pat_file)) as m:
        hay = b"foobar foo foo barfoo"
        # Only match 'foo' at end of word and as a full word
        results = m.match(hay, word_suffix=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # 'foo' in 'foobar' is suffix? no; matches as full word at offsets 7 and 11
        assert offsets == [7, 11, 18]
        assert matches == [b"foo", b"foo", b"foo"]


def test_line_start_and_end(tmp_path):
    """Test line_start and line_end matching options."""
    patterns = ["start", "end", "middle"]
    pat_file = tmp_path / "line_patterns.txt"
    write_file(pat_file, patterns)

    with Matcher(str(pat_file)) as m:
        # Test data with patterns at different line positions
        hay = b"start of line\nmiddle start here\nsome middle text\nline end"

        # Test line_start matching - should only match patterns at start of lines
        results = m.match(hay, line_start=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # "start" at offset 0 (start of first line)
        # "middle" at offset 14 (start of second line, after newline at 13)
        assert offsets == [0, 14]
        assert matches == [b"start", b"middle"]

        # Test line_end matching - should only match patterns at end of lines
        results = m.match(hay, line_end=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # "end" at offset 54 (end of last line)
        assert offsets == [54]
        assert matches == [b"end"]
        # Test both line_start and line_end together
        results = m.match(hay, line_start=True, line_end=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # Should match patterns that are both at start AND end of lines (entire line content)
        # In our test data, no pattern forms an entire line by itself
        assert offsets == []
        assert matches == []


def test_line_exact_match(tmp_path):
    """Test matching patterns that are exactly a complete line."""
    patterns = ["exactline"]
    pat_file = tmp_path / "exact_patterns.txt"
    write_file(pat_file, patterns)

    with Matcher(str(pat_file)) as m:
        # Test data where pattern matches entire line
        hay = b"before\nexactline\nafter"

        # Test that pattern matches when it forms a complete line
        results = m.match(hay, line_start=True, line_end=True)
        offsets = [r.offset for r in results]
        matches = [r.match for r in results]
        # "exactline" should match as it's both at start and end of its line
        assert len(offsets) == 1
        assert matches == [b"exactline"]
        assert offsets[0] == 7  # Position after "before\n"


def test_pattern_keys_basic(tmp_path):
    """Test that patterns compiled with keys return correct keys in results."""
    output_path = str(tmp_path / "keyed.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"hello", key=100)
        compiler.add_pattern(b"world", key=200)

    with Matcher(output_path) as m:
        results = m.match(b"hello world")
        assert len(results) == 2
        assert results[0].match == b"hello"
        assert results[0].key == 100
        assert results[1].match == b"world"
        assert results[1].key == 200


def test_pattern_keys_default_zero(tmp_path):
    """Test that patterns without explicit keys get key=0."""
    output_path = str(tmp_path / "nokeys.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"alpha")
        compiler.add_pattern(b"bravo")

    with Matcher(output_path) as m:
        results = m.match(b"alpha bravo")
        assert len(results) == 2
        for r in results:
            assert r.key == 0


def test_pattern_keys_mixed(tmp_path):
    """Test mixing keyed and unkeyed patterns (unkeyed get key=0)."""
    output_path = str(tmp_path / "mixed.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"apple", key=42)
        compiler.add_pattern(b"banana")  # key=0

    with Matcher(output_path) as m:
        results = m.match(b"apple banana")
        assert len(results) == 2
        keyed = {r.match: r.key for r in results}
        assert keyed[b"apple"] == 42
        assert keyed[b"banana"] == 0


def test_pattern_keys_short_patterns(tmp_path):
    """Test keys with short patterns (1-4 bytes) handled by the short matcher."""
    output_path = str(tmp_path / "short_keyed.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"ab", key=10)
        compiler.add_pattern(b"xyz", key=20)
        compiler.add_pattern(b"test", key=30)

    with Matcher(output_path) as m:
        results = m.match(b"ab xyz test")
        assert len(results) == 3
        keyed = {r.match: r.key for r in results}
        assert keyed[b"ab"] == 10
        assert keyed[b"xyz"] == 20
        assert keyed[b"test"] == 30


def test_pattern_keys_large_values(tmp_path):
    """Test that large 64-bit key values are preserved correctly."""
    output_path = str(tmp_path / "large_keys.olm")
    large_key = (1 << 63) - 1  # Near max uint64
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"target", key=large_key)

    with Matcher(output_path) as m:
        results = m.match(b"find target here")
        assert len(results) == 1
        assert results[0].key == large_key


def test_pattern_keys_single_byte(tmp_path):
    """Test keys with single-byte patterns."""
    output_path = str(tmp_path / "single_keyed.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"X", key=99)
        compiler.add_pattern(b"Y", key=88)

    with Matcher(output_path) as m:
        results = m.match(b"XaYbX")
        assert len(results) == 3
        keys = [r.key for r in results]
        assert keys == [99, 88, 99]


@pytest.mark.parametrize(
    ("raw", "expected_value", "expected_end"),
    [
        (b"0", 0, 1),
        (b"0x0,", 0, 3),
        (b"0123\t", 83, 4),
        (b"+7:", 7, 2),
        (b" \t42,", 42, 4),
        (b"18446744073709551615,", (1 << 64) - 1, 20),
    ],
)
def test_parse_uint64_prefix_valid_cases(raw, expected_value, expected_end):
    value, end = _parse_uint64_prefix(raw)
    assert value == expected_value
    assert end == expected_end


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b" ",
        b"-1",
        b"+",
        b"0x",
        b"xyz",
        b"18446744073709551616",
    ],
)
def test_parse_uint64_prefix_rejects_invalid_cases(raw):
    with pytest.raises(ValueError):
        _parse_uint64_prefix(raw)


def test_parse_first_keyed_record_detects_delimiter():
    key, delim, pattern = _parse_first_keyed_record(b"0x10\talpha")
    assert key == 16
    assert delim == b"\t"
    assert pattern == b"alpha"


def test_parse_keyed_record_rejects_invalid_key_and_missing_delimiter():
    with pytest.raises(ValueError):
        _parse_keyed_record(b"12x,alpha", b",")
    with pytest.raises(LookupError):
        _parse_keyed_record(b"12 alpha", b",")


def test_compiler_add_pattern_rejects_invalid_key_range(tmp_path):
    output_path = str(tmp_path / "invalid_key.olm")
    with Compiler(output_path) as compiler:
        with pytest.raises(ValueError):
            compiler.add_pattern(b"alpha", key=-1)
        with pytest.raises(ValueError):
            compiler.add_pattern(b"alpha", key=1 << 64)
        with pytest.raises(TypeError):
            compiler.add_pattern(b"alpha", key="7")  # type: ignore[arg-type]


def test_pattern_keys_same_bucket(tmp_path):
    """Regression: keys must stay in sync when patterns sharing a 4-byte
    prefix are sorted by length within their hash bucket."""
    output_path = str(tmp_path / "same_bucket.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"abcde", key=1)
        compiler.add_pattern(b"abcdef", key=2)

    with Matcher(output_path) as m:
        results = m.match(b"xxabcdefyy")
        keyed = {r.match: r.key for r in results}
        assert keyed[b"abcde"] == 1
        assert keyed[b"abcdef"] == 2


def test_pattern_keys_same_bucket_mixed_keyed_and_unkeyed(tmp_path):
    """Regression: lockstep reordering must preserve zero-key entries too."""
    output_path = str(tmp_path / "same_bucket_mixed.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"abcdeg", key=11)
        compiler.add_pattern(b"abcdefg")
        compiler.add_pattern(b"abcdef", key=22)
        compiler.add_pattern(b"abcde")

    with Matcher(output_path) as m:
        results = m.match(b"xxabcdefgyy")
        keyed = {r.match: r.key for r in results}
        assert keyed[b"abcde"] == 0
        assert keyed[b"abcdef"] == 22
        assert keyed[b"abcdefg"] == 0


def test_python_keyed_compile_mode_parses_plus_and_octal(tmp_path):
    patterns_path = tmp_path / "keyed_patterns.txt"
    patterns_path.write_bytes(b"+7,xyz\n0123,abc\n")
    output_path = tmp_path / "cli_keyed.olm"

    compile_mode(
        str(output_path),
        str(patterns_path),
        case_insensitive=False,
        ignore_punctuation=False,
        elide_whitespace=False,
        keyed=True,
        verbose=False,
    )

    with Matcher(str(output_path)) as m:
        results = m.match(b"abc xyz")
        keyed = {r.match: r.key for r in results}
        assert keyed[b"xyz"] == 7
        assert keyed[b"abc"] == 83


def test_python_keyed_compile_mode_rejects_invalid_first_record(tmp_path):
    patterns_path = tmp_path / "bad_keyed_patterns.txt"
    patterns_path.write_bytes(b"foo\tabc\n7\txyz\n")
    output_path = tmp_path / "bad_cli_keyed.olm"

    with pytest.raises(SystemExit) as exc:
        compile_mode(
            str(output_path),
            str(patterns_path),
            case_insensitive=False,
            ignore_punctuation=False,
            elide_whitespace=False,
            keyed=True,
            verbose=False,
        )

    assert exc.value.code == 1
    assert not output_path.exists()


def test_python_keyed_compile_mode_reports_actual_first_key_line(tmp_path, capsys):
    patterns_path = tmp_path / "bad_keyed_patterns_with_blanks.txt"
    patterns_path.write_bytes(b"\n\nfoo\tabc\n7\txyz\n")
    output_path = tmp_path / "bad_cli_keyed_line_num.olm"

    with pytest.raises(SystemExit) as exc:
        compile_mode(
            str(output_path),
            str(patterns_path),
            case_insensitive=False,
            ignore_punctuation=False,
            elide_whitespace=False,
            keyed=True,
            verbose=False,
        )

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "line 3" in captured.err
    assert not output_path.exists()


def test_compile_mode_verbose_empty_file_does_not_divide_by_zero(tmp_path, capsys):
    patterns_path = tmp_path / "empty_patterns.txt"
    patterns_path.write_bytes(b"")
    output_path = tmp_path / "empty.olm"

    compile_mode(
        str(output_path),
        str(patterns_path),
        case_insensitive=False,
        ignore_punctuation=False,
        elide_whitespace=False,
        keyed=False,
        verbose=True,
    )

    captured = capsys.readouterr()
    assert "Ratio: 0.00" in captured.err


def test_pattern_reactor_dispatch_order(tmp_path):
    """Pattern keys should support deterministic callback-table dispatch."""
    output_path = str(tmp_path / "reactor_order.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"ERROR", key=1)
        compiler.add_pattern(b"WARN", key=2)
        compiler.add_pattern(b"OK", key=3)

    handlers = {
        1: lambda result, events: events.append(
            ("error", result.offset, result.match.decode("ascii"))
        ),
        2: lambda result, events: events.append(
            ("warn", result.offset, result.match.decode("ascii"))
        ),
        3: lambda result, events: events.append(
            ("ok", result.offset, result.match.decode("ascii"))
        ),
    }

    with Matcher(output_path) as m:
        results = m.match(b"OK WARN ERROR OK")

    events = dispatch_results(results, handlers)
    assert events == [
        ("ok", 0, "OK"),
        ("warn", 3, "WARN"),
        ("error", 8, "ERROR"),
        ("ok", 14, "OK"),
    ]


def test_pattern_reactor_respects_longest_only_and_no_overlap(tmp_path):
    """Reactor dispatch should receive the same filtered match stream users see."""
    output_path = str(tmp_path / "reactor_filters.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"abc", key=1)
        compiler.add_pattern(b"abcd", key=2)

    handlers = {
        1: lambda result, events: events.append(("short", result.offset)),
        2: lambda result, events: events.append(("long", result.offset)),
    }

    with Matcher(output_path) as m:
        all_events = dispatch_results(m.match(b"xxabcdyy"), handlers)
        longest_events = dispatch_results(
            m.match(b"xxabcdyy", longest_only=True), handlers
        )
        no_overlap_events = dispatch_results(
            m.match(b"xxabcdyy", no_overlap=True), handlers
        )

    assert all_events == [("long", 2), ("short", 2)]
    assert longest_events == [("long", 2)]
    assert no_overlap_events == [("long", 2)]


def test_pattern_reactor_large_same_bucket_dispatch(tmp_path):
    """Shared-prefix keyed dispatch should stay correct across a larger bucket."""
    output_path = str(tmp_path / "reactor_same_bucket_large.olm")
    patterns = [
        (f"same-prefix-{i:02d}".encode("ascii"), i + 1) for i in range(24)
    ]

    with Compiler(output_path) as compiler:
        for pattern, key in patterns:
            compiler.add_pattern(pattern, key=key)

    haystack = b" | ".join(pattern for pattern, _ in patterns)
    expected = {
        pattern: (key, haystack.index(pattern)) for pattern, key in patterns
    }

    handlers = {
        key: (
            lambda expected_pattern: (
                lambda result, events: events.append(
                    (expected_pattern, result.key, result.offset)
                )
            )
        )(pattern)
        for pattern, key in patterns
    }

    with Matcher(output_path) as m:
        results = m.match(haystack)

    events = dispatch_results(results, handlers)
    assert len(events) == len(patterns)
    for pattern, key, offset in events:
        expected_key, expected_offset = expected[pattern]
        assert key == expected_key
        assert offset == expected_offset


def test_builtin_reactor_emits_builtin_overwrite_actions(tmp_path):
    output_path = str(tmp_path / "builtin_overwrite.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"mIxEd", key=11)
        compiler.add_pattern(b"LOUD", key=12)
        compiler.add_pattern(b"secret", key=13)
        compiler.add_pattern(b"ignored", key=99)

    with Matcher(output_path) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(11, BuiltinReactor.OP_UPPER),
            BuiltinReactorRule(12, BuiltinReactor.OP_LOWER),
            BuiltinReactorRule(13, BuiltinReactor.OP_REDACT, redact_byte=ord("X")),
        ]
    ) as reactor:
        actions = reactor.plan(matcher, b"mIxEd LOUD secret ignored")

    assert [
        (action.start, action.end, action.rule_id, action.kind, action.data)
        for action in actions
    ] == [
        (0, 5, 11, BuiltinReactor.KIND_OVERWRITE, b"MIXED"),
        (6, 10, 12, BuiltinReactor.KIND_OVERWRITE, b"loud"),
        (11, 17, 13, BuiltinReactor.KIND_OVERWRITE, b"XXXXXX"),
    ]


def test_builtin_reactor_uuid_replace_respects_match_filters(tmp_path):
    output_path = str(tmp_path / "builtin_uuid.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"abc", key=21)
        compiler.add_pattern(b"abcd", key=22)

    uuid_pattern = re.compile(
        rb"^[0-9a-f]{8}-[0-9a-f]{4}-8[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )

    with Matcher(output_path) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(21, BuiltinReactor.OP_UUID),
            BuiltinReactorRule(22, BuiltinReactor.OP_UUID),
        ]
    ) as reactor:
        all_actions = reactor.plan(matcher, b"xxabcdyy")
        longest_actions = reactor.plan(matcher, b"xxabcdyy", longest_only=True)

    assert [action.rule_id for action in all_actions] == [22, 21]
    assert [action.kind for action in all_actions] == [
        BuiltinReactor.KIND_REPLACE,
        BuiltinReactor.KIND_REPLACE,
    ]
    assert [(action.start, action.end) for action in all_actions] == [(2, 6), (2, 5)]
    assert len(longest_actions) == 1
    assert longest_actions[0].rule_id == 22

    for action in all_actions + longest_actions:
        assert len(action.data) == 36
        assert uuid_pattern.match(action.data), action.data


def test_builtin_reactor_rejects_duplicate_rule_ids():
    with pytest.raises(RuntimeError):
        BuiltinReactor(
            [
                BuiltinReactorRule(7, BuiltinReactor.OP_UPPER),
                BuiltinReactorRule(7, BuiltinReactor.OP_LOWER),
            ]
        )


def test_builtin_reactor_rejects_rule_id_zero():
    # Rule ID 0 is reserved: matches from patterns compiled without a key
    # carry key 0, so a rule registered as 0 would fire on every unkeyed match
    with pytest.raises(RuntimeError):
        BuiltinReactor([BuiltinReactorRule(0, BuiltinReactor.OP_UPPER)])


def test_rewrite_script_applies_reverse_order_variable_width_edits(tmp_path):
    output_path = str(tmp_path / "rewrite_bytes.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"bob", key=31)
        compiler.add_pattern(b"TAIL", key=32)

    with Matcher(output_path) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(31, BuiltinReactor.OP_UUID),
            BuiltinReactorRule(32, BuiltinReactor.OP_LOWER),
        ]
    ) as reactor, reactor.build_script(matcher, b"bob TAIL") as script:
        ops = script.ops()
        rewritten = script.apply_bytes(b"bob TAIL")

    assert [(op.kind, op.offset, op.length, op.rule_id) for op in ops] == [
        (BuiltinReactor.SCRIPT_OVERWRITE, 4, 4, 32),
        (BuiltinReactor.SCRIPT_DELETE, 0, 3, 31),
        (BuiltinReactor.SCRIPT_INSERT, 0, 0, 31),
    ]
    assert ops[0].data == b"tail"
    assert len(ops[2].data) == 36
    assert rewritten.endswith(b" tail")
    assert re.match(
        rb"^[0-9a-f]{8}-[0-9a-f]{4}-8[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12} tail$",
        rewritten,
    )


def test_rewrite_script_rejects_overlapping_edit_actions(tmp_path):
    output_path = str(tmp_path / "rewrite_overlap.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"abc", key=41)
        compiler.add_pattern(b"abcd", key=42)

    with Matcher(output_path) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(41, BuiltinReactor.OP_UUID),
            BuiltinReactorRule(42, BuiltinReactor.OP_UUID),
        ]
    ) as reactor:
        with pytest.raises(RuntimeError):
            reactor.build_script(matcher, b"xxabcdyy")


def test_builtin_reactor_rewrite_bytes_helper(tmp_path):
    output_path = str(tmp_path / "rewrite_helper.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"LOUD", key=51)
        compiler.add_pattern(b"secret", key=52)

    with Matcher(output_path) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(51, BuiltinReactor.OP_LOWER),
            BuiltinReactorRule(52, BuiltinReactor.OP_REDACT, redact_byte=ord("*")),
        ]
    ) as reactor:
        rewritten = reactor.rewrite_bytes(matcher, b"LOUD secret")

    assert rewritten == b"loud ******"


def test_rewrite_script_apply_omega_edit_matches_in_memory_replay(tmp_path):
    if not RewriteScript.omega_edit_available():
        pytest.skip("OmegaEdit adapter not available in this build")

    output_path = str(tmp_path / "rewrite_file.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"bob", key=61)
        compiler.add_pattern(b"TAIL", key=62)

    input_path = tmp_path / "input.txt"
    output_file = tmp_path / "output.txt"
    input_bytes = b"bob TAIL"
    input_path.write_bytes(input_bytes)

    with Matcher(output_path) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(61, BuiltinReactor.OP_UUID),
            BuiltinReactorRule(62, BuiltinReactor.OP_LOWER),
        ]
    ) as reactor, reactor.build_script(matcher, input_bytes) as script:
        expected = script.apply_bytes(input_bytes)
        script.apply_omega_edit(str(input_path), str(output_file))

    assert output_file.read_bytes() == expected


def test_native_plugin_reactor_dispatch_and_rewrite(tmp_path):
    output_path = str(tmp_path / "native_plugin.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"alpha", key=201)
        compiler.add_pattern(b"secret", key=202)
        compiler.add_pattern(b"ignored", key=999)

    plugin_path = get_native_test_plugin_path()
    assert os.path.exists(plugin_path), plugin_path

    with Matcher(output_path) as matcher, NativePluginReactor(plugin_path) as reactor:
        actions = reactor.plan(matcher, b"alpha secret ignored")
        rewritten = reactor.rewrite_bytes(matcher, b"alpha secret ignored")

    assert [
        (action.start, action.end, action.rule_id, action.kind, action.data)
        for action in actions
    ] == [
        (0, 5, 201, BuiltinReactor.KIND_REPLACE, b"[alpha]"),
        (6, 12, 202, BuiltinReactor.KIND_OVERWRITE, b"######"),
    ]
    assert rewritten == b"[alpha] ###### ignored"


def test_native_plugin_reactor_rejects_missing_init_symbol():
    plugin_path = get_native_test_plugin_path()
    assert os.path.exists(plugin_path), plugin_path
    with pytest.raises(RuntimeError):
        NativePluginReactor(plugin_path, init_symbol="omega_reactor_plugin_init_missing")


def test_native_plugin_reactor_rejects_sparse_rule_id_dispatch_table():
    plugin_path = get_native_test_plugin_path()
    assert os.path.exists(plugin_path), plugin_path
    with pytest.raises(RuntimeError):
        NativePluginReactor(plugin_path, init_symbol="omega_reactor_plugin_init_sparse_rule")


def test_python_reactor_builtin_configuration_and_rewrite(tmp_path):
    output_path = str(tmp_path / "python_reactor_builtin.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"mIxEd", key=301)
        compiler.add_pattern(b"secret", key=302)

    with Matcher(output_path) as matcher, Reactor() as reactor:
        reactor.add_builtin(301, "upper")
        reactor.add_builtin(302, "redact", redact_byte=ord("*"))
        emission = reactor.plan(matcher, b"mIxEd secret")
        rewritten = reactor.rewrite_bytes(matcher, b"mIxEd secret")

    assert emission.side_effects == []
    assert [
        (action.start, action.end, action.rule_id, action.kind, action.data)
        for action in emission.actions
    ] == [
        (0, 5, 301, BuiltinReactor.KIND_OVERWRITE, b"MIXED"),
        (6, 12, 302, BuiltinReactor.KIND_OVERWRITE, b"******"),
    ]
    assert rewritten == b"MIXED ******"


def test_python_reactor_callback_emits_actions_and_side_effects(tmp_path):
    output_path = str(tmp_path / "python_reactor_callback.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"alice", key=401)

    def callback(result):
        return ReactorEmission(
            actions=[RewriteAction.replace(result, b"PERSON-1")],
            side_effects=[
                ReactorSideEffect.for_match(
                    result, "entity-map", payload={"replacement": "PERSON-1"}
                )
            ],
        )

    with Matcher(output_path) as matcher, Reactor() as reactor:
        reactor.add_callback(401, callback)
        emission = reactor.plan(matcher, b"alice met alice")
        rewritten = reactor.rewrite_bytes(matcher, b"alice met alice")

    assert rewritten == b"PERSON-1 met PERSON-1"
    assert [action.data for action in emission.actions] == [b"PERSON-1", b"PERSON-1"]
    assert [effect.kind for effect in emission.side_effects] == ["entity-map", "entity-map"]
    assert emission.side_effects[0].payload == {"replacement": "PERSON-1"}


def test_python_reactor_rejects_invalid_callback_return(tmp_path):
    output_path = str(tmp_path / "python_reactor_bad_callback.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"alpha", key=501)

    with Matcher(output_path) as matcher, Reactor() as reactor:
        reactor.add_callback(501, lambda result: 123)
        with pytest.raises(TypeError):
            reactor.plan(matcher, b"alpha")


def test_python_reactor_rejects_duplicate_rule_ids_across_builtin_and_callback():
    with Reactor() as reactor:
        reactor.add_builtin(701, "upper")
        with pytest.raises(ValueError):
            reactor.add_callback(701, lambda result: result)

    with Reactor() as reactor:
        reactor.add_callback(702, lambda result: result)
        with pytest.raises(ValueError):
            reactor.add_builtin(702, "lower")


def test_python_reactor_ignores_unmatched_rule_ids_and_handles_empty_haystack(tmp_path):
    output_path = str(tmp_path / "python_reactor_unmatched.olm")
    with Compiler(output_path) as compiler:
        compiler.add_pattern(b"alpha", key=801)

    with Matcher(output_path) as matcher, Reactor() as reactor:
        reactor.add_builtin(801, "upper")
        reactor.add_callback(
            999,
            lambda result: ReactorEmission(
                side_effects=[ReactorSideEffect.for_match(result, "unreachable")]
            ),
        )

        empty_emission = reactor.plan(matcher, b"")
        populated_emission = reactor.plan(matcher, b"alpha beta")
        rewritten = reactor.rewrite_bytes(matcher, b"alpha beta")

    assert empty_emission.actions == []
    assert empty_emission.side_effects == []
    assert [action.data for action in populated_emission.actions] == [b"ALPHA"]
    assert populated_emission.side_effects == []
    assert rewritten == b"ALPHA beta"


def test_pattern_keys_same_bucket_capacity_growth_from_unkeyed_to_keyed(tmp_path):
    """Regression: growing a previously unkeyed bucket must zero legacy slots."""
    output_path = str(tmp_path / "same_bucket_growth.olm")
    patterns = [
        (b"abcd-0000", 0),
        (b"abcd-0001", 0),
        (b"abcd-0002", 0),
        (b"abcd-0003", 0),
        (b"abcd-0004", 77),
    ]

    with Compiler(output_path) as compiler:
        for pattern, key in patterns:
            compiler.add_pattern(pattern, key=key)

    haystack = b" ".join(pattern for pattern, _ in patterns)
    expected = {pattern: key for pattern, key in patterns}

    with Matcher(output_path) as m:
        results = m.match(haystack)

    keyed = {r.match: r.key for r in results}
    for pattern, key in expected.items():
        assert keyed[pattern] == key


def test_python_binding_shutdown_cleanup_exits_cleanly(tmp_path):
    output_path = tmp_path / "shutdown_cleanup.olm"
    script = textwrap.dedent(
        f"""
        from omega_match.omega_match import Compiler, Matcher

        output_path = r"{output_path}"

        with Compiler(output_path) as compiler:
            compiler.add_pattern(b"alpha", key=11)
            compiler.add_pattern(b"beta")

        closed_matcher = Matcher(output_path)
        assert [result.key for result in closed_matcher.match(b"alpha beta")] == [11, 0]
        closed_matcher.destroy()

        leaked_matcher = Matcher(output_path)
        assert [result.key for result in leaked_matcher.match(b"beta alpha")] == [0, 11]
        """
    )
    env = os.environ.copy()
    python_root = str(__file__)
    python_root = os.path.dirname(os.path.dirname(os.path.abspath(python_root)))
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        python_root
        if not existing_pythonpath
        else python_root + os.pathsep + existing_pythonpath
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_safe_destroy_tracks_state_per_object():
    destroyed = []

    class DummyDestroyable:
        def __init__(self, name):
            self.name = name
            self._omega_destroyed = False
            self._omega_destroying = False

        def destroy(self):
            destroyed.append(self.name)

    first = DummyDestroyable("first")
    second = DummyDestroyable("second")

    _safe_destroy(first, "DummyDestroyable")
    _safe_destroy(first, "DummyDestroyable")
    _safe_destroy(second, "DummyDestroyable")

    assert destroyed == ["first", "second"]


@pytest.mark.parametrize(
    ("script_name", "expected_output"),
    [
        ("reactor_redactor.py", "alice shared a XXXXXX and bob shared another XXXXXX"),
        (
            "reactor_hyperlinks.py",
            'Visit <a href="https://example.com">https://example.com</a> and <a href="https://omega.dev">https://omega.dev</a> for details.',
        ),
        (
            "reactor_acronyms.py",
            "National Aeronautics and Space Administration (NASA) published an Application Programming Interface (API) update.",
        ),
    ],
)
def test_reactor_examples_smoke(tmp_path, script_name, expected_output):
    completed = run_python_example(tmp_path, script_name)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert completed.stdout.strip() == expected_output


def test_reactor_uuid_sidecar_example_smoke(tmp_path):
    completed = run_python_example(tmp_path, "reactor_uuid_sidecar.py")
    assert completed.returncode == 0, completed.stderr or completed.stdout

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 5

    rewritten = lines[0]
    uuid_matches = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        rewritten,
    )
    assert len(uuid_matches) == 4
    assert "alice" not in rewritten
    assert "bob" not in rewritten

    payload_lines = lines[1:]
    assert any("'original': 'alice'" in line for line in payload_lines)
    assert any("'original': 'bob'" in line for line in payload_lines)


def test_reactor_benchmark_example_smoke(tmp_path):
    completed = run_python_example(tmp_path, "reactor_benchmark.py")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    output = completed.stdout
    assert "matcher only" in output
    assert "builtin rewrite" in output
    assert "python reactor" in output
