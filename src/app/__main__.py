"""
title: App entrypoint
layer: app
public_api: no
summary: `python -m app` — wire dependencies and run.
"""
from backend import do_thing


def main() -> int:
    thing = do_thing("hello", 1)
    print(f"composed and ran: {thing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
