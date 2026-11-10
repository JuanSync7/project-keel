"""
title: Copier collection probe — observe imports with copier unavailable
summary: A child pytest collector blocks every copier import, records its importing test module and collection outcome as JSON, and leaves the verdict to its parent.
"""

import importlib.abc
import json
import sys
from pathlib import Path
from types import FrameType
from typing import Any

import pytest
from exit_codes import PassedThrough, passthrough

import optional_deps

PREFIX = "KEEL_COPIER_COLLECTION="


class CopierProbe(importlib.abc.MetaPathFinder):
    """Record blocked imports and pytest's collection reports."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.attempts: list[tuple[str, str]] = []
        self.reports: list[tuple[str, str, str]] = []
        self.tests: list[tuple[str, str]] = []

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname != "copier" and not fullname.startswith("copier."):
            return
        frame: FrameType | None = sys._getframe()  # noqa: TID251 -- attribute the actual import stack, independently of source syntax
        importer = "<unknown>"
        while frame is not None:
            source = Path(frame.f_code.co_filename).resolve()
            if source.name.startswith("test_") and source.is_relative_to(self.root):
                importer = source.relative_to(self.root).as_posix()
                break
            frame = frame.f_back
        self.attempts.append((importer, fullname))
        raise ImportError("copier hidden by collection probe: %s" % fullname)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        self.reports.append((report.nodeid, report.outcome, str(report.longrepr)))

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call":
            self.tests.append((report.nodeid, report.outcome))

    def pytest_sessionfinish(self) -> None:
        sys.stdout.write(
            "\n"
            + PREFIX
            + json.dumps(
                {
                    "attempts": self.attempts,
                    "reports": self.reports,
                    "tests": self.tests,
                },
                sort_keys=True,
            )
            + "\n"
        )


def collect(root: str, paths: list[str], *, run_tests: bool = False) -> PassedThrough:
    """Collect paths with no required extras and emit the observed inventory."""
    assert not any(
        name == "copier" or name.startswith("copier.") for name in sys.modules
    )
    # The probe models a clone that requested no optional surfaces, including
    # transports that the checkout's normal configuration declares required.
    optional_deps.required_extras = lambda loaded=None: set()
    probe = CopierProbe(Path(root).resolve())
    sys.meta_path.insert(0, probe)
    return passthrough(
        int(
            pytest.main(
                [
                    *([] if run_tests else ["--collect-only"]),
                    "-qq",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "addopts=",
                    *paths,
                ],
                plugins=[probe],
            )
        )
    )
