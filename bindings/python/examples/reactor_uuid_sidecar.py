import uuid

from omega_match import Compiler, Matcher, Reactor, ReactorEmission, ReactorSideEffect, RewriteAction


def main() -> None:
    compiled = "reactor_uuid_sidecar.olm"
    haystack = b"alice met bob and alice called bob"

    with Compiler(compiled) as compiler:
        compiler.add_pattern(b"alice", key=1)
        compiler.add_pattern(b"bob", key=2)

    def replace_with_uuid(match):
        token = str(uuid.uuid4()).encode("ascii")
        return ReactorEmission(
            actions=[RewriteAction.replace(match, token)],
            side_effects=[
                ReactorSideEffect.for_match(
                    match,
                    "uuid-map",
                    payload={
                        "replacement": token.decode("ascii"),
                        "original": match.match.decode("utf-8"),
                    },
                )
            ],
        )

    with Matcher(compiled) as matcher, Reactor() as reactor:
        reactor.add_callback(1, replace_with_uuid)
        reactor.add_callback(2, replace_with_uuid)
        emission = reactor.plan(matcher, haystack)
        rewritten = reactor.rewrite_bytes(matcher, haystack)

    print(rewritten.decode("utf-8"))
    for effect in emission.side_effects:
        print(effect.payload)


if __name__ == "__main__":
    main()
