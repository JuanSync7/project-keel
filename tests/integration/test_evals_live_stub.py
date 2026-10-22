"""
title: Integration — the live eval path against a stub model server over a real socket
kind: tests
layer: n/a
summary: scripts/run_evals.py --mode live runs every shipped case through models.registry.get_model with the openai-compatible adapter pointed, by config/project.json `evals.live.model_options`, at tests/stub_model_server.py on a loopback port the OS assigns, so the real HTTP path is proven with no paid call. With replies that pass, it exits 0, counts one call per case, sends exactly one request per case, writes one candidate per case under `evals.report_dir` whose hashes match the reply and the prompt the server received, leaves the tracked dataset unchanged, and a candidate promoted by hand over its case replays green. Each red path keeps its own exit: a reply that fails its scorer or an HTTP 500 is a fail (1); a case count above `evals.live.max_calls` or a null model is refused (2) before any request; a port with nothing listening is absent (BACKEND_ABSENT), the first case absent and the rest not run; and a refused or absent run leaves no candidate from an earlier run behind. An `evals.live.model_options.api_key_env` that `models.credential_env` does not declare for the adapter is refused (2) with no request sent, and the variable's value appears in neither the output nor the report. The config lists the stub's `host:port` in `models.allowed_hosts.openai-compatible`; with it unlisted the run is refused (2) with nothing sent to the server and a detail naming that key and not the path. A 301, 302, 303, 307 or 308 from a listed endpoint is a RuntimeError naming the first endpoint and the status, never the Location, and the second server receives no request, so the credential never follows a redirect.
@covers scripts/run_evals.py
"""

import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from exit_codes import ExitCode  # noqa: E402
from test_evals_gate import build_scratch, read_report, run_cli  # noqa: E402

from live_server import free_port, load_server_config  # noqa: E402
from stub_model_server import Redirect, stub_chat_server  # noqa: E402

pytestmark = pytest.mark.integration

_SERVER = load_server_config(str(_ROOT))
# The registry name of the adapter that speaks the chat-completions wire format;
# the harness reads it from config, so the test writes it there.
_ADAPTER = "openai-compatible"
_STUB_MODEL = "stub"


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest(repo):
    return json.loads((repo / "config" / "project.json").read_text("utf-8"))


def _datasets(repo):
    cfg = _manifest(repo)["evals"]
    return sorted((repo / cfg["dataset_dir"]).iterdir())


def _shipped_cases(repo):
    return [
        json.loads(line)
        for path in _datasets(repo)
        for line in path.read_text("utf-8").splitlines()
    ]


def _host_port(base_url):
    """The `host:port` an allowed_hosts entry is written as for *base_url*."""
    return urllib.parse.urlsplit(base_url).netloc


def _configure(repo, base_url, model=_ADAPTER, max_calls=None, listed=True):
    """Point the live run at *base_url*, listing its host:port in the scratch
    config's models.allowed_hosts unless *listed* is False."""
    manifest = _manifest(repo)
    manifest["models"]["allowed_hosts"] = {
        _ADAPTER: [_host_port(base_url)] if listed else []
    }
    live = manifest["evals"]["live"]
    live["model"] = model
    live["max_calls"] = len(_shipped_cases(repo)) if max_calls is None else max_calls
    live["model_options"] = {
        "base_url": base_url,
        "model": _STUB_MODEL,
        "timeout": _SERVER["request_timeout_s"],
    }
    (repo / "config" / "project.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _live_env(env):
    env = dict(env)
    # urllib honours proxy variables; a loopback stub must not be routed away.
    env["no_proxy"] = env["NO_PROXY"] = "*"
    env.pop("OPENAI_API_KEY", None)
    return env


def _report_dir(repo):
    return repo / _manifest(repo)["evals"]["report_dir"]


def _candidates(repo):
    return sorted((_report_dir(repo) / "live-candidates").glob("*.jsonl"))


def test_live_against_a_stub_server_green_and_candidates(tmp_path):
    repo, env = build_scratch(tmp_path)
    cases = _shipped_cases(repo)
    before = {p.name: p.read_bytes() for p in _datasets(repo)}
    replies = [c["recorded"]["response"] for c in cases]
    with stub_chat_server(_ROOT, replies) as (base, requests):
        _configure(repo, base + "/v1")
        out = run_cli(repo, _live_env(env), mode="live")
        assert out.returncode == 0, out.stdout
        assert len(requests) == len(cases)
    report = read_report(repo, "live")
    assert (report["result"], report["calls"], report["model"]) == (
        "pass",
        len(cases),
        _ADAPTER,
    )
    assert {p.name: p.read_bytes() for p in _datasets(repo)} == before
    sent = [r["messages"][-1]["content"] for r in requests]
    assert all(r["model"] == _STUB_MODEL for r in requests)

    # One candidate file per suite, named after it, in the datasets' order.
    cand_files = _candidates(repo)
    assert [p.name for p in cand_files] == [p.name for p in _datasets(repo)]
    first = cand_files[0].read_text("utf-8").splitlines()
    lines = [ln for f in cand_files for ln in f.read_text("utf-8").splitlines()]
    candidates = [json.loads(line) for line in lines]
    assert [c["id"] for c in candidates] == [c["id"] for c in cases]
    for cand, case, prompt in zip(candidates, cases, sent, strict=True):
        rec = cand["recorded"]
        assert (rec["source"], rec["model"]) == ("model", _ADAPTER)
        assert rec["sha256"] == _sha(rec["response"]) == case["recorded"]["sha256"]
        assert rec["prompt_sha256"] == _sha(prompt) == case["recorded"]["prompt_sha256"]
        assert (cand["input"], cand["scorer"]) == (case["input"], case["scorer"])
    assert lines[0] == json.dumps(
        candidates[0], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    # Promotion is a hand copy of one line over its case line; replay stays green.
    dataset = _datasets(repo)[0]
    old = dataset.read_text("utf-8").splitlines()
    old[0] = first[0]
    dataset.write_text("\n".join(old) + "\n", encoding="utf-8")
    out = run_cli(repo, env)
    assert out.returncode == 0, out.stdout


def _plant_stale_candidates(repo):
    stale = _report_dir(repo) / "live-candidates" / "old.jsonl"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("{}\n", encoding="utf-8")
    return stale


def _scorer_fail(cases):
    return [""] + [c["recorded"]["response"] for c in cases[1:]]


def _http_500(cases):
    return [500] + [c["recorded"]["response"] for c in cases[1:]]


# The member each red path ends on, by name: the test reads its value from the
# enum the CLI returns, so a renumbered member needs no edit here.
_FAIL = "FAILURE"
_REFUSED = "USAGE"
_ABSENT = "BACKEND_ABSENT"
_ERRORED = ["below-threshold", "case-error"]


@pytest.mark.parametrize(
    "replies, overrides, member, result, reasons, first, calls",
    [
        (_scorer_fail, {}, _FAIL, "fail", ["below-threshold"], "fail", "all"),
        (_http_500, {}, _FAIL, "fail", _ERRORED, "error", "all"),
        (None, {"max_calls": -1}, _REFUSED, "refused", ["cap-exceeded"], None, 0),
        (None, {"model": None}, _REFUSED, "refused", ["refused"], None, 0),
        (None, {"absent": True}, _ABSENT, "absent", ["backend-absent"], "absent", 1),
    ],
    ids=["scorer-fail", "http-500", "over-cap", "null-model", "absent"],
)
def test_live_red_paths_over_a_real_socket(
    tmp_path, replies, overrides, member, result, reasons, first, calls
):
    code = int(ExitCode[member])
    repo, env = build_scratch(tmp_path)
    cases = _shipped_cases(repo)
    stale = _plant_stale_candidates(repo)
    scripted = replies(cases) if replies else [c["recorded"]["response"] for c in cases]
    with stub_chat_server(_ROOT, scripted) as (base, requests):
        url = base + "/v1"
        if overrides.get("absent"):
            url = "http://%s:%d/v1" % (_SERVER["host"], free_port(_SERVER["host"]))
        cap = None
        if "max_calls" in overrides:
            cap = len(cases) + overrides["max_calls"]
        _configure(repo, url, model=overrides.get("model", _ADAPTER), max_calls=cap)
        out = run_cli(repo, _live_env(env), mode="live")
        assert out.returncode == code, out.stdout
        seen = len(requests)
    report = read_report(repo, "live")
    assert (report["result"], report["reasons"]) == (result, reasons), report
    expected_calls = len(cases) if calls == "all" else calls
    assert report["calls"] == expected_calls, report
    assert not stale.exists()
    if member == _REFUSED:
        assert seen == 0
        assert report["suites"] == [] and report["detail"], report
        assert _candidates(repo) == []
        return
    outcomes = [c["outcome"] for s in report["suites"] for c in s["cases"]]
    by_id = {c["id"]: c["outcome"] for s in report["suites"] for c in s["cases"]}
    assert by_id[cases[0]["id"]] == first, by_id
    if member == _ABSENT:
        assert seen == 0
        assert sorted(outcomes) == sorted(["absent"] + ["not-run"] * (len(cases) - 1))
        assert _candidates(repo) == []
    else:
        assert seen == len(cases)


def test_live_refuses_a_credential_variable_config_does_not_declare(tmp_path):
    """`evals.live.model_options` reaches the adapter as keyword arguments, so
    it could name any environment variable to send as the bearer token; one
    `models.credential_env` does not declare for the adapter is refused before
    a request is made."""
    repo, env = build_scratch(tmp_path)
    cases = _shipped_cases(repo)
    canary = "canary-not-a-model-key"
    with stub_chat_server(_ROOT, [c["recorded"]["response"] for c in cases]) as (
        base,
        requests,
    ):
        _configure(repo, base + "/v1")
        manifest = _manifest(repo)
        manifest["evals"]["live"]["model_options"]["api_key_env"] = "UNRELATED_SECRET"
        (repo / "config" / "project.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        live_env = dict(_live_env(env), UNRELATED_SECRET=canary)
        out = run_cli(repo, live_env, mode="live")
        assert out.returncode == 2, out.stdout
        assert len(requests) == 0
    report = read_report(repo, "live")
    assert (report["result"], report["reasons"]) == ("refused", ["refused"]), report
    assert "models.credential_env" in report["detail"], report
    assert canary not in out.stdout and canary not in json.dumps(report)
    assert _candidates(repo) == []


def test_live_refuses_a_host_config_does_not_list(tmp_path):
    """The adapter sends its credential only to a host config/project.json
    `models.allowed_hosts` lists for it; with the list left empty the run is
    refused before a request reaches the server that is listening."""
    repo, env = build_scratch(tmp_path)
    cases = _shipped_cases(repo)
    with stub_chat_server(_ROOT, [c["recorded"]["response"] for c in cases]) as served:
        base, requests = served
        _configure(repo, base + "/v1/path-canary", listed=False)
        out = run_cli(repo, _live_env(env), mode="live")
        assert out.returncode == int(ExitCode.USAGE), out.stdout
        assert requests == [] and served.seen == []
    report = read_report(repo, "live")
    assert (report["result"], report["reasons"]) == ("refused", ["refused"]), report
    assert "models.allowed_hosts.openai-compatible" in report["detail"], report
    assert "path-canary" not in report["detail"], report
    assert _candidates(repo) == []


_REDIRECTS = (301, 302, 303, 307, 308)


@pytest.mark.parametrize("status", _REDIRECTS)
def test_a_redirect_is_refused_and_the_credential_never_reaches_the_second_server(
    monkeypatch, status
):
    """urllib follows a 301, 302 or 303 answer to a POST with a new request
    that keeps every header but the body's, Authorization included, so a
    listed endpoint could hand the credential to any host. The adapter refuses
    every redirect: it reports the endpoint that answered, never the Location
    it named, and the second server sees nothing. Both servers are listed, so
    the allowlist is not what stops it."""
    from models import get_model
    from models import openai_compatible as mod

    canary = "sk-redirect-canary"
    with stub_chat_server(_ROOT, []) as second:
        target = second[0] + "/v1/chat/completions"
        with stub_chat_server(_ROOT, [Redirect(status, target)]) as first:
            policy = mod.load_policy()._replace(
                allowed_hosts={_ADAPTER: (_host_port(first[0]), _host_port(second[0]))}
            )
            monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)
            monkeypatch.setenv("OPENAI_API_KEY", canary)
            # urllib honours proxy variables; the loopback servers are direct.
            monkeypatch.setenv("no_proxy", "*")
            monkeypatch.setenv("NO_PROXY", "*")
            backend = get_model(
                _ADAPTER,
                base_url=first[0] + "/v1",
                model=_STUB_MODEL,
                timeout=_SERVER["request_timeout_s"],
            )
            with pytest.raises(RuntimeError) as info:
                backend.run("ping")
            first_seen = list(first.seen)
        second_seen = list(second.seen)
    message = str(info.value)
    assert "redirect" in message and str(status) in message, message
    # The only origin the message names is the endpoint that answered; a
    # substring test could pass on a port that shares a prefix.
    assert re.findall(r"[a-z]+://[^\s/`'\"(),]+", message) == [first[0]], message
    assert target not in message, message
    assert "/chat/completions" not in message and canary not in message, message
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert second_seen == [], second_seen
    assert [s.has_authorization for s in first_seen] == [True], first_seen
