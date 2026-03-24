from omega_match import Compiler, Matcher, Reactor, RewriteAction


EXPANSIONS = {
    1: b"National Aeronautics and Space Administration (NASA)",
    2: b"Application Programming Interface (API)",
}


def main() -> None:
    compiled = "reactor_acronyms.olm"
    haystack = b"NASA published an API update."

    with Compiler(compiled) as compiler:
        compiler.add_pattern(b"NASA", key=1)
        compiler.add_pattern(b"API", key=2)

    def expand(match):
        return RewriteAction.replace(match, EXPANSIONS[match.key])

    with Matcher(compiled) as matcher, Reactor() as reactor:
        reactor.add_callback(1, expand)
        reactor.add_callback(2, expand)
        rewritten = reactor.rewrite_bytes(matcher, haystack)

    print(rewritten.decode("utf-8"))


if __name__ == "__main__":
    main()
