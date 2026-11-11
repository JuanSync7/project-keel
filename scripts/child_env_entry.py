"""
title: Child environment refusal boundary for entry functions
summary: Converts an escaping ChildEnvError into a CONFIG report returned from main; library functions keep raising and finish(main()) remains the process ending. Stdlib-only and Python 3.6-safe.
"""

import functools
from typing import Any, Callable, TypeVar, cast

from child_env import ChildEnvError
from exit_codes import ExitCode, report

__all__ = ["child_env_errors"]

_Entry = TypeVar("_Entry", bound=Callable[..., Any])


def child_env_errors(main: _Entry) -> _Entry:
    """Report an escaping child-environment refusal as CONFIG from an entry.

    Only entry functions opt in: imported library operations keep raising.
    ChildEnvError messages name refused inputs without their values.
    """

    @functools.wraps(main)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return main(*args, **kwargs)
        except ChildEnvError as exc:
            return report(
                ExitCode.CONFIG,
                "the child environment is refused",
                str(exc),
                "correct the named environment variable or config/project.json "
                "child_env policy, then rerun",
            )

    return cast(_Entry, guarded)
