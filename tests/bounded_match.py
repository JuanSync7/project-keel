"""
title: Bounded configured regex matching
summary: Matches a batch in one isolated Python child with the loader-read tests.child_timeout_seconds deadline; child failures refuse by key and repair without showing patterns or values.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, cast

_ROOT = str(Path(__file__).resolve().parents[1])
_SCRIPTS = str(Path(_ROOT) / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

__all__ = ["match_values"]

_TIMEOUT = ("tests", "child_timeout_seconds")
# Python's re cannot be interrupted in-process. One child amortizes startup
# across the gate's whole batch, while run kills and reaps only that child.
_MATCH = """
import json
import re
import sys

pattern, values, mode = json.load(sys.stdin)
match = getattr(re.compile(pattern), mode)
json.dump([match(value) is not None for value in values], sys.stdout)
"""


def match_values(
    pattern: str,
    key: str,
    values: List[str],
    mode: str,
    *,
    root: str = _ROOT,
    timeout: Optional[float] = None,
) -> List[bool]:
    """Return one match decision per value, or refuse without exposing inputs.

    The mode is search or fullmatch. Empty batches start no child. The deadline
    comes from root's tests.child_timeout_seconds unless explicitly supplied.
    Timeout, failed execution and malformed replies raise AssertionError.
    """
    if mode not in ("search", "fullmatch"):
        raise ValueError("match mode must be search or fullmatch")
    if not values:
        return []
    if timeout is None:
        settings = config_loader.resolve(
            config_loader.read(root),
            config_loader.rows(_TIMEOUT),
            config_loader.CONFIG_FILE,
        )
        timeout = float(settings[_TIMEOUT])

    def refusal(cause: str) -> AssertionError:
        return AssertionError(
            "%s: %s; repair %s with a simpler valid regular expression, "
            "then rerun (deadline: tests.child_timeout_seconds)" % (key, cause, key)
        )

    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _MATCH],
            input=json.dumps([pattern, values, mode]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=build_child_env(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise refusal("regex child timeout") from None
    except OSError:
        raise refusal(
            "regex child could not start; restore the Python executable"
        ) from None
    except UnicodeError:
        raise refusal("regex child output is not UTF-8") from None
    if proc.returncode != 0:
        raise refusal("regex child exited nonzero")
    try:
        result = json.loads(proc.stdout)
    except (ValueError, RecursionError):
        raise refusal("regex child output does not parse as JSON") from None
    if (
        not isinstance(result, list)
        or len(result) != len(values)
        or any(type(item) is not bool for item in result)
    ):
        raise refusal("regex child output is not one bool per value")
    return cast(List[bool], result)
