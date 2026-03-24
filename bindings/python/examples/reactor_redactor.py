from omega_match import Compiler, Matcher, Reactor


def main() -> None:
    compiled = "reactor_redactor.olm"
    haystack = b"alice shared a SECRET and bob shared another SECRET"

    with Compiler(compiled) as compiler:
        compiler.add_pattern(b"SECRET", key=1)

    with Matcher(compiled) as matcher, Reactor() as reactor:
        reactor.add_builtin(1, "redact", redact_byte=ord("X"))
        rewritten = reactor.rewrite_bytes(matcher, haystack)

    print(rewritten.decode("utf-8"))


if __name__ == "__main__":
    main()
