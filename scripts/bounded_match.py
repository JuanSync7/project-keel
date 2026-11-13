"""
title: Bounded configured regex matching
summary: Matches a batch, or lists every match span of it, in one isolated Python child with the loader-read tests.child_timeout_seconds deadline; child failures refuse by key and repair without showing patterns or values.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, cast

# Hook callers use bare sibling imports; package callers need the same path
# without relying on the working directory. The floor gate follows these imports.
_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

# Mypy cannot resolve the runtime scripts/ path used by hook sibling imports.
import config_loader  # type: ignore[import-not-found]  # noqa: E402
from child_env import build_child_env  # type: ignore[import-not-found]  # noqa: E402

if TYPE_CHECKING or __package__:
    from .module_identity import register_module
else:
    from module_identity import register_module

__all__ = ["match_spans", "match_values"]

_ROOT = str(Path(__file__).resolve().parents[1])

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


_SPANS = """
import json
import re
import sys

pattern, values = json.load(sys.stdin)
regex = re.compile(pattern)
json.dump(
    [[list(m.span()) for m in regex.finditer(value)] for value in values],
    sys.stdout,
)
"""


def _refusal(key: str, cause: str) -> AssertionError:
    return AssertionError(
        "%s: %s; repair %s with a simpler valid regular expression, "
        "then rerun (deadline: tests.child_timeout_seconds)" % (key, cause, key)
    )


def _run_child(
    script: str, payload: List[Any], key: str, root: str, timeout: Optional[float]
) -> Any:
    """Run *script* in one isolated child fed *payload* as JSON on stdin and
    return its parsed JSON reply, or refuse without exposing the payload."""
    if timeout is None:
        settings = config_loader.resolve(
            config_loader.read(root),
            config_loader.rows(_TIMEOUT),
            config_loader.CONFIG_FILE,
        )
        timeout = float(settings[_TIMEOUT])
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=build_child_env(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise _refusal(key, "regex child timeout") from None
    except OSError:
        raise _refusal(
            key, "regex child could not start; restore the Python executable"
        ) from None
    except UnicodeError:
        raise _refusal(key, "regex child output is not UTF-8") from None
    if proc.returncode != 0:
        raise _refusal(key, "regex child exited nonzero")
    try:
        return json.loads(proc.stdout)
    except (ValueError, RecursionError):
        raise _refusal(key, "regex child output does not parse as JSON") from None


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
    result = _run_child(_MATCH, [pattern, values, mode], key, root, timeout)
    if (
        not isinstance(result, list)
        or len(result) != len(values)
        or any(type(item) is not bool for item in result)
    ):
        raise _refusal(key, "regex child output is not one bool per value")
    return cast(List[bool], result)


def match_spans(
    pattern: str,
    key: str,
    values: List[str],
    *,
    root: str = _ROOT,
    timeout: Optional[float] = None,
) -> List[List[Tuple[int, int]]]:
    """Return every match of *pattern* in each value as `(start, end)` offsets.

    Enumerating matches is where a backtracking pattern hangs, so it happens in
    the same bounded child as match_values and the caller only slices text.
    Matches are in order, an empty match included, as re.finditer yields them.
    Empty batches start no child; the deadline and refusals are match_values'.
    """
    if not values:
        return []
    result = _run_child(_SPANS, [pattern, values], key, root, timeout)

    def sound(spans: Any, value: str) -> bool:
        return isinstance(spans, list) and all(
            isinstance(span, list)
            and len(span) == 2
            and all(type(offset) is int for offset in span)
            and 0 <= span[0] <= span[1] <= len(value)
            for span in spans
        )

    if (
        not isinstance(result, list)
        or len(result) != len(values)
        or not all(sound(result[i], values[i]) for i in range(len(values)))
    ):
        raise _refusal(key, "regex child output is not spans within each value")
    return [[(span[0], span[1]) for span in spans] for spans in result]


register_module(__name__, __file__)
