"""
title: App entrypoint
layer: app
public_api: no
summary: `python -m app` — wire dependencies and run.
"""

from backend import do_thing


def main() -> None:
    thing = do_thing("hello", 1)
    print(f"composed and ran: {thing}")


if __name__ == "__main__":
    main()
