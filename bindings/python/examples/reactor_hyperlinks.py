from omega_match import Compiler, Matcher, Reactor, RewriteAction


def main() -> None:
    compiled = "reactor_hyperlinks.olm"
    haystack = b"Visit https://example.com and https://omega.dev for details."

    with Compiler(compiled) as compiler:
        compiler.add_pattern(b"https://example.com", key=1)
        compiler.add_pattern(b"https://omega.dev", key=2)

    def hyperlink(match):
        text = match.match.decode("utf-8")
        replacement = f'<a href="{text}">{text}</a>'.encode("utf-8")
        return RewriteAction.replace(match, replacement)

    with Matcher(compiled) as matcher, Reactor() as reactor:
        reactor.add_callback(1, hyperlink)
        reactor.add_callback(2, hyperlink)
        rewritten = reactor.rewrite_bytes(matcher, haystack)

    print(rewritten.decode("utf-8"))


if __name__ == "__main__":
    main()
