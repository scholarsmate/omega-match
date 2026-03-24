import time

from omega_match import BuiltinReactor, BuiltinReactorRule, Compiler, Matcher, Reactor, RewriteAction


def benchmark(label, fn, rounds=50):
    start = time.perf_counter()
    for _ in range(rounds):
        fn()
    elapsed = time.perf_counter() - start
    print(f"{label:20s} {elapsed:.4f}s total  {elapsed / rounds:.6f}s avg")


def main() -> None:
    compiled = "reactor_benchmark.olm"
    haystack = (b"alice SECRET bob WARN " * 2000) + b"done"

    with Compiler(compiled) as compiler:
        compiler.add_pattern(b"alice", key=1)
        compiler.add_pattern(b"SECRET", key=2)
        compiler.add_pattern(b"WARN", key=3)

    with Matcher(compiled) as matcher, BuiltinReactor(
        [
            BuiltinReactorRule(2, BuiltinReactor.OP_REDACT, redact_byte=ord("X")),
            BuiltinReactorRule(3, BuiltinReactor.OP_LOWER),
        ]
    ) as builtin, Reactor() as reactor:
        reactor.add_builtin(2, "redact", redact_byte=ord("X"))
        reactor.add_callback(1, lambda match: RewriteAction.replace(match, b"PERSON"))
        reactor.add_builtin(3, "lower")

        benchmark("matcher only", lambda: matcher.match(haystack))
        benchmark("builtin rewrite", lambda: builtin.rewrite_bytes(matcher, haystack))
        benchmark("python reactor", lambda: reactor.rewrite_bytes(matcher, haystack))


if __name__ == "__main__":
    main()
