"""
title: Evals public API
layer: n/a
public_api: yes
summary: The eval harness that judges actual responses: typed JSONL datasets, the closed SCORERS and DOERS registries, replay of recorded responses through the real doers (the `make eval` gate), a live run capped by config/project.json `evals.live.max_calls`, the exact-threshold verdict and the canonical report. scripts/run_evals.py is its only command-line caller.
"""

from ._config import ConfigError, EvalConfig, load_config, parse_config
from ._dataset import Case, DatasetError, Suite, load_suites, parse_cases
from ._doers import DOERS, prompt_sha256, sha256_text
from ._report import (
    OUTCOMES,
    REASONS,
    RESULTS,
    Outcome,
    Report,
    SuiteResult,
    aggregate,
    render,
    verdict,
)
from ._run import LiveRun, SpendCapExceeded, replay, run_live
from ._scorers import SCORERS, Scorer

__all__ = [
    "DOERS",
    "OUTCOMES",
    "REASONS",
    "RESULTS",
    "SCORERS",
    "Case",
    "ConfigError",
    "DatasetError",
    "EvalConfig",
    "LiveRun",
    "Outcome",
    "Report",
    "Scorer",
    "SpendCapExceeded",
    "Suite",
    "SuiteResult",
    "aggregate",
    "load_config",
    "load_suites",
    "parse_cases",
    "parse_config",
    "prompt_sha256",
    "render",
    "replay",
    "run_live",
    "sha256_text",
    "verdict",
]
