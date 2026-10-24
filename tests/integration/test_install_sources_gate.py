"""
title: Integration — the install recipes pass config/project.json install_sources to npm and the browser runner
kind: tests
layer: n/a
summary: A real `make fe-install` and `make fe-browsers` on a copy of this project with one stub app, a stub `node` printing the configured major and a stub `npm` that records its arguments and PLAYWRIGHT_DOWNLOAD_HOST. With `install_sources.npm_registry` and `browser_download_host` null, npm is called as plain `npm install` and the browser runner sees no PLAYWRIGHT_DOWNLOAD_HOST, so the user's own .npmrc and the runner's default host hold; set, npm gets `--registry <url>` and the runner gets the host, each read from the copy's config and never a literal. A workflow step is an install when one of its shell commands, split at `;`, `&&`, `|`, `(` and newlines, is pip or pip3 install, `python -m pip install`, an npm install or ci alias, or a playwright install through npx or `npm exec`; each such step is run for real under `bash -e`, from its working-directory in a copy whose config sets the sources, with every installer stubbed: pip and npm pass `--index-url` or `--registry` with the configured URL and the browser download sees the configured host, and with the sources null none of them does. A pnpm or yarn install, an installer named by path or run under sudo, and a step that fails under the stubs are faults, so the judge fails closed; a workflow tree with no install step is a failure, not a pass. Each unwired form, put in a copy of ci.yml, is a fault, and a wired pip3 step is not. The GitLab adapter keel ships is judged the same way, each script line a step: its installs take the sources, and an unwired pip line put in a copy is a fault. A value with a URL user part stops each target before npm runs, its recipe ending 14 (CONFIG), the refusal naming the key and never the user part.
@covers Makefile
@covers scripts/install_sources.py
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ci_adapters
import makefile_copy
import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

_REGISTRY = "https://npm.mirror.example.invalid/registry/"
_HOST = "https://browsers.mirror.example.invalid"
_TOKEN = "tok-SENTINEL"


def _stub(folder, name, body):
    path = folder / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _copy(tmp_path, sources):
    """A copy of this project whose config sets install_sources to *sources*,
    with one stub app that already has node_modules."""
    work = tmp_path / "work"
    makefile_copy.copy_makefiles(work, _ROOT)
    shutil.copytree(
        str(_ROOT / "scripts"),
        str(work / "scripts"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (work / "config").mkdir()
    config = json.loads((_ROOT / config_loader.CONFIG_FILE).read_text("utf-8"))
    config["install_sources"].update(sources)
    (work / config_loader.CONFIG_FILE).write_text(json.dumps(config, indent=2))
    app = work / "src" / "frontend" / "stub"
    (app / "node_modules").mkdir(parents=True)
    (app / "package.json").write_text(json.dumps({"name": "stub"}))
    return work, config["toolchain"]["node_major"]


def _make(tmp_path, work, major, target):
    """Run *target* in *work* with stub node and npm. -> (completed, the npm
    calls recorded, one line each: its arguments, then the host it saw)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "npm-calls"
    _stub(bin_dir, "node", "echo v%d.0.0\n" % major)
    _stub(
        bin_dir,
        "npm",
        'printf "%%s|%%s\\n" "$*" "${PLAYWRIGHT_DOWNLOAD_HOST-<unset>}" >> %s\n'
        % shlex.quote(str(log)),
    )
    path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])
    ran = subprocess.run(
        ["make", "--no-print-directory", "PY=" + sys.executable, target],
        cwd=str(work),
        env=build_child_env(extra={"PATH": path}),
        capture_output=True,
        text=True,
        timeout=300,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return ran, calls


def test_null_sources_pass_nothing_so_the_tools_own_setting_holds(tmp_path):
    work, major = _copy(tmp_path, {"npm_registry": None, "browser_download_host": None})
    ran, calls = _make(tmp_path, work, major, "fe-install")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert calls == ["install|<unset>"], calls
    ran, calls = _make(tmp_path, work, major, "fe-browsers")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert len(calls) == 2 and calls[1].endswith("|<unset>"), calls


def test_a_configured_mirror_reaches_npm_and_the_browser_runner(tmp_path):
    work, major = _copy(
        tmp_path, {"npm_registry": _REGISTRY, "browser_download_host": _HOST}
    )
    ran, calls = _make(tmp_path, work, major, "fe-install")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert calls[0].split("|")[0].split() == ["install", "--registry", _REGISTRY]
    ran, calls = _make(tmp_path, work, major, "fe-browsers")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    args, host = calls[1].split("|")
    assert args.split()[:2] == ["run", "--silent"], calls
    assert host == _HOST, calls


@pytest.mark.parametrize(
    "target, key",
    [("fe-install", "npm_registry"), ("fe-browsers", "browser_download_host")],
)
def test_a_user_part_stops_the_target_before_npm_and_is_never_shown(
    tmp_path, target, key
):
    url = "https://u:%s@mirror.example.invalid/" % _TOKEN
    work, major = _copy(tmp_path, {key: url})
    ran, calls = _make(tmp_path, work, major, target)
    # make ends 2 on any failed recipe and names the recipe's own status.
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert "Error %d" % ExitCode.CONFIG in ran.stderr, ran.stderr
    assert calls == [], calls
    assert "install_sources." + key in ran.stderr, ran.stderr
    assert "SENTINEL" not in ran.stdout + ran.stderr


_WORKFLOWS = _ROOT / ".github" / "workflows"
_INDEX = "https://pypi.mirror.example.invalid/simple/"
_SET = {
    "python_index": _INDEX,
    "npm_registry": _REGISTRY,
    "browser_download_host": _HOST,
}
_NULL = {"python_index": None, "npm_registry": None, "browser_download_host": None}
# Tokens that end one shell command and start the next.
_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;"}
# Words that run the command after them rather than being it.
_WRAPPERS = {"sudo", "env", "exec", "time", "command", "nice"}
# npm's own aliases for install and clean-install (npm help install, npm help ci).
_NPM_INSTALLS = {
    "i",
    "in",
    "ins",
    "inst",
    "insta",
    "instal",
    "install",
    "isnt",
    "isnta",
    "isntal",
    "isntall",
    "add",
    "ci",
    "clean-install",
    "ic",
    "install-clean",
    "isntall-clean",
}
# The Node package managers no install source is wired for.
_UNWIRED = {"pnpm", "yarn"}


def _commands(run):
    """The word list of each simple command in a step's *run* text, a
    `$(...)` substitution counting as its own command."""
    text = run.replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    commands, words = [], []
    for token in lexer:
        # `index=$(python ...)` lexes as `index=$`, `(`, so the `(` ends the
        # assignment and the substitution is a command of its own.
        if token in _SEPARATORS:
            commands.append(words)
            words = []
        else:
            words.append(token)
    commands.append(words)
    return [w for w in commands if w]


def _subcommand(words):
    """The first word that is not an option."""
    return next((w for w in words if not w.startswith("-")), None)


def _install_kind(words):
    """'pip', 'npm', 'browser' or 'unwired' for a command that installs,
    else None."""
    while words and (
        "=" in words[0]
        and not words[0].startswith("-")
        or os.path.basename(words[0]) in _WRAPPERS
    ):
        words = words[1:]
    if not words:
        return None
    head, rest = os.path.basename(words[0]), words[1:]
    if re.fullmatch(r"python[0-9.]*", head) and rest[:2] == ["-m", "pip"]:
        head, rest = "pip", rest[2:]
    if head == "npm" and _subcommand(rest) in ("exec", "x"):
        head, rest = "npx", rest[rest.index(_subcommand(rest)) + 1 :]
    if head == "npx":
        tool = _subcommand(rest)
        if tool is None or tool.split("@")[0] != "playwright":
            return None
        head, rest = "playwright", rest[rest.index(tool) + 1 :]
    if re.fullmatch(r"pip[0-9.]*", head):
        return "pip" if _subcommand(rest) == "install" else None
    if head == "npm":
        return "npm" if _subcommand(rest) in _NPM_INSTALLS else None
    if head == "playwright":
        return "browser" if _subcommand(rest) == "install" else None
    if head in _UNWIRED:
        # A bare `yarn` installs; so does every install alias these share.
        return (
            "unwired"
            if _subcommand(rest) in (None, "install", "i", "add", "ci")
            else None
        )
    return None


def _escapes_stubs(words):
    """True when the command's installer would not be the stub on PATH: it
    is named by a path, or run by sudo, which resets PATH."""
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    return bool(words) and ("/" in words[0] or words[0] == "sudo")


def _workflow_steps(workflows, root=None):
    """Every (workflow file, step) under *workflows* that runs a shell line,
    then, with *root*, each script line of the GitLab adapter keel ships there
    (tests/ci_adapters.py shipped), as a step of its own."""
    yaml = optional_deps.importorskip("yaml", extra="template")
    found = []
    for path in sorted(workflows.glob("*.yml")):
        for job in (yaml.safe_load(path.read_text("utf-8")) or {})["jobs"].values():
            found.extend((path.name, s) for s in job.get("steps", []) if "run" in s)
    gitlab = ci_adapters.shipped(root).get("gitlab") if root else None
    if gitlab:
        found.extend(
            (gitlab.name, {"run": ci_adapters.gitlab_line(step)})
            for step in ci_adapters.adapter_steps(gitlab, "gitlab")
        )
    return found


def _run_step(tmp_path, step, sources, tag):
    """Run *step* under `bash -e` in a workspace whose config sets
    *sources*, with every installer stubbed. -> [(install kind, argument
    words, PLAYWRIGHT_DOWNLOAD_HOST or None)] per install it made, or None
    when the step fails."""
    work = tmp_path / ("ws-" + tag)
    if not work.exists():
        shutil.copytree(
            str(_ROOT / "scripts"),
            str(work / "scripts"),
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        (work / "config").mkdir()
        config = json.loads((_ROOT / config_loader.CONFIG_FILE).read_text("utf-8"))
        config["install_sources"].update(sources)
        (work / config_loader.CONFIG_FILE).write_text(json.dumps(config))
    cwd = work / step.get("working-directory", ".")
    cwd.mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / ("bin-" + tag)
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / ("calls-" + tag)
    if log.exists():
        log.unlink()
    record = (
        'printf "%%s|%%s\\n" "%s $*" "${PLAYWRIGHT_DOWNLOAD_HOST-<unset>}" >> '
        + shlex.quote(str(log))
        + "\n"
    )
    for tool in ("pip", "pip3", "npm", "npx", "pnpm", "yarn", "playwright"):
        _stub(bin_dir, tool, record % tool)
    python = shlex.quote(sys.executable)
    for tool in ("python", "python3"):
        _stub(
            bin_dir,
            tool,
            'if [ "$1" = -m ] && [ "$2" = pip ]; then shift 2; %sexit 0; fi\nexec %s "$@"\n'
            % (record % "pip", python),
        )
    path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])
    ran = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=str(cwd),
        env=build_child_env(extra={"PATH": path}),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if ran.returncode != 0:
        return None
    calls = []
    for line in log.read_text().splitlines() if log.exists() else []:
        args, host = line.rsplit("|", 1)
        words = args.split()
        calls.append((_install_kind(words), words, None if host == "<unset>" else host))
    return calls


def _faults(tmp_path, workflows, root=None):
    """-> (installs judged, a message per install step under *workflows*, and
    with *root* in its GitLab adapter, that ignores config/project.json
    install_sources)."""
    judged, faults = 0, []
    want = {"pip": ("--index-url", _INDEX), "npm": ("--registry", _REGISTRY)}
    for name, step in _workflow_steps(workflows, root):
        kinds = [k for k in map(_install_kind, _commands(step["run"])) if k]
        if not kinds:
            continue
        judged += len(kinds)
        label = "%s: `%s`" % (name, step["run"].strip())
        escapes = [
            w for w in _commands(step["run"]) if _install_kind(w) and _escapes_stubs(w)
        ]
        if escapes:
            faults.append(
                "%s names its installer by path or under sudo, so it cannot be "
                "judged without really installing" % label
            )
            continue
        if "unwired" in kinds:
            faults.append(
                "%s installs with pnpm or yarn, which no install source reaches" % label
            )
            continue
        for sources, tag in ((_SET, "set"), (_NULL, "null")):
            calls = _run_step(tmp_path, step, sources, tag + str(judged))
            if calls is None:
                faults.append(
                    "%s fails under stub installers, sources %s" % (label, tag)
                )
                continue
            if sorted(k for k, _, _ in calls) != sorted(kinds):
                faults.append(
                    "%s with sources %s made installs %s, not %s"
                    % (label, tag, calls, kinds)
                )
                continue
            for kind, words, host in calls:
                if kind == "browser":
                    if host != (_HOST if tag == "set" else None):
                        faults.append(
                            "%s with sources %s saw host %r" % (label, tag, host)
                        )
                    continue
                flag, url = want[kind]
                if tag == "null" and flag in words:
                    faults.append(
                        "%s passes %s with the source null: %s" % (label, flag, words)
                    )
                if tag == "set" and (
                    flag not in words or words[words.index(flag) + 1 :][:1] != [url]
                ):
                    faults.append(
                        "%s does not pass %s %s: %s" % (label, flag, url, words)
                    )
    return judged, faults


def test_every_workflow_install_step_takes_the_configured_mirror(tmp_path):
    judged, faults = _faults(tmp_path, _WORKFLOWS, _ROOT)
    assert judged, "no workflow step under %s installs: nothing was judged" % _WORKFLOWS
    assert faults == [], "\n".join(faults)


def test_the_gitlab_adapter_install_steps_are_judged_too(tmp_path):
    """The GitLab adapter installs through the same sources: its pip and
    install lines are judged, and an unwired line put in a copy is a fault."""
    gitlab = ci_adapters.shipped(_ROOT).get("gitlab")
    if gitlab is None:
        pytest.skip("this project ships no GitLab adapter")
    none = tmp_path / "no-workflows"
    none.mkdir()
    judged, faults = _faults(tmp_path / "a", none, _ROOT)
    assert judged and faults == [], (judged, faults)
    root = tmp_path / "copy"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(str(_ROOT / ci_adapters.CONFIG), str(root / ci_adapters.CONFIG))
    text = gitlab.read_text("utf-8")
    assert text.count("    - make secrets-install\n") == 1
    (root / gitlab.name).write_text(
        text.replace(
            "    - make secrets-install\n",
            "    - make secrets-install\n    - pip install requests\n",
        )
    )
    judged, faults = _faults(tmp_path / "b", none, root)
    assert len(faults) == 1 and "pip install requests" in faults[0], faults


@pytest.mark.parametrize(
    "run",
    [
        "pip3 install requests",
        "python -m pip install requests",
        "python3 -m pip install -e .",
        "/usr/bin/pip install requests",
        "cd . && pip -q install requests",
        "npm i left-pad",
        "npm add left-pad",
        "npx playwright install chromium",
        "npx -y playwright@1.49 install",
        "npm exec playwright install",
        "pnpm install",
        "yarn install",
        "yarn",
        "echo start\nyarn add left-pad",
        "sudo pip install requests",
        "PIP_NO_CACHE_DIR=1 pip install requests",
        # A literal mirror passes the set check and is caught with the source null.
        "pip install requests --index-url https://pypi.mirror.example.invalid/simple/",
        "npm ci --registry https://npm.mirror.example.invalid/registry/",
    ],
    ids=lambda run: run.replace("\n", " / "),
)
def test_an_unwired_install_step_put_in_a_copy_of_ci_yml_is_a_fault(tmp_path, run):
    yaml = optional_deps.importorskip("yaml", extra="template")
    workflows = tmp_path / "workflows"
    shutil.copytree(str(_WORKFLOWS), str(workflows))
    ci = workflows / "ci.yml"
    doc = yaml.safe_load(ci.read_text("utf-8"))
    next(iter(doc["jobs"].values()))["steps"].append({"run": run})
    ci.write_text(yaml.safe_dump(doc))
    judged, faults = _faults(tmp_path, workflows)
    assert faults and all(run.strip() in f for f in faults), faults


def test_a_wired_pip3_step_put_in_a_copy_of_ci_yml_is_no_fault(tmp_path):
    """The differential: the injected cases are faults because they are
    unwired, not because the judge refuses any new install."""
    yaml = optional_deps.importorskip("yaml", extra="template")
    workflows = tmp_path / "workflows"
    shutil.copytree(str(_WORKFLOWS), str(workflows))
    ci = workflows / "ci.yml"
    doc = yaml.safe_load(ci.read_text("utf-8"))
    run = 'index=$(python scripts/install_sources.py python_index) && pip3 install x ${index:+--index-url "$index"}'
    next(iter(doc["jobs"].values()))["steps"].append({"run": run})
    ci.write_text(yaml.safe_dump(doc))
    before, _ = _faults(tmp_path / "a", _WORKFLOWS)
    judged, faults = _faults(tmp_path / "b", workflows)
    assert judged == before + 1 and faults == [], faults
