"""
title: Integration — the canary's answer sets, launchers and one real render
kind: tests
layer: n/a
summary: scripts/canary.py is held to the files around it. Each config/project.json `canary.answer_sets` set is an answer copier.yml accepts: every key is one of its questions, every value its type and within its choices (a multiselect a subset), and every copier.yml validator renders empty with the set over copier.yml's defaults; the canary's own copier.yml reader returns every asked question and no computed one; there are at least two sets with at least two distinct frontend stacks, and a set copier refuses (astro without the showcase) fails the same check. The canary is launched by its workflow (a schedule, a manual dispatch, full history for the tags, a `make canary` step), by a CONTRIBUTING.md Release step before the push, and by the farm through a `launcher.long_scripts` entry, never by `make verify`; the workflow's failure upload names only paths under `canary.scratch_root`, no step of it sets `KEEL_CANARY_SCRATCH`, and it warns when it finds no file, each shown failing on a planted copy; and copier.yml excludes the doer, the shared snapshot module and the workflow from generated projects. One set, `skeleton`, is then rendered and updated with the real copier and git and a make that always passes: two pass lines, the update path's answers record the snapshot's HEAD as `_commit`, and both projects are gone afterwards; without copier it skips, naming the extra. The guides are held to the canary: the step table of docs/guides/generate-and-upgrade.md names each step a line can report as failed and no other, found by failing each call into a project in turn until a run passes, its example lines have the fields a line has, and the symptom table of docs/guides/limits-and-troubleshooting.md quotes the words of every `report(...)` message scripts/canary.py holds. Excluded from generated projects with the doer.
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import canary  # noqa: E402
import child_env  # noqa: E402
import config_loader  # noqa: E402
import template_snapshot  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import optional_deps  # noqa: E402

pytestmark = pytest.mark.integration

_WORKFLOWS = _ROOT / ".github" / "workflows"
_LAUNCH_KEY = "make canary"


def _answer_sets():
    loaded = config_loader.read(str(_ROOT))
    rows = config_loader.rows(("canary", "answer_sets"))
    return config_loader.resolve(loaded, rows, config_loader.CONFIG_FILE)[
        ("canary", "answer_sets")
    ]


def _questions(yaml):
    data = yaml.safe_load((_ROOT / "copier.yml").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def answer_faults(name, answers, questions, jinja2):
    """One line per way *answers* is not an answer copier.yml accepts."""
    faults = []
    if not isinstance(answers, dict):
        return ["%s: an answer set is an object, not %r" % (name, answers)]
    merged = {}
    for key, spec in questions.items():
        if isinstance(spec, dict) and "default" in spec:
            merged[key] = spec["default"]
    for key, value in sorted(answers.items()):
        spec = questions.get(key)
        if not isinstance(spec, dict) or spec.get("when") is False:
            faults.append("%s: %s is not a question copier.yml asks" % (name, key))
            continue
        merged[key] = value
        kind = spec.get("type", "str")
        choices = spec.get("choices")
        if spec.get("multiselect"):
            if not isinstance(value, list) or not set(value) <= set(choices or ()):
                faults.append(
                    "%s: %s=%r is not a subset of %r" % (name, key, value, choices)
                )
        elif kind == "bool" and not isinstance(value, bool):
            faults.append("%s: %s=%r is not true or false" % (name, key, value))
        elif kind == "str" and not isinstance(value, str):
            faults.append("%s: %s=%r is not a string" % (name, key, value))
        elif choices is not None and value not in choices:
            faults.append("%s: %s=%r is not one of %r" % (name, key, value, choices))
    for key, spec in sorted(questions.items()):
        validator = spec.get("validator") if isinstance(spec, dict) else None
        if validator:
            said = jinja2.Template(validator).render(**merged).strip()
            if said:
                faults.append("%s: copier.yml %s refuses it: %s" % (name, key, said))
    return faults


def test_each_canary_answer_set_is_a_valid_copier_answer():
    yaml = optional_deps.importorskip("yaml", extra="template")
    jinja2 = optional_deps.importorskip("jinja2", extra="template")
    questions = _questions(yaml)
    sets = _answer_sets()
    # The canary's own reader of copier.yml, which refuses an unasked key at
    # run time, agrees with this one: every asked question, and no computed one.
    asked = canary.asked_questions(str(_ROOT))
    computed = {
        k
        for k, v in questions.items()
        if isinstance(v, dict) and v.get("when") is False
    }
    assert computed, "copier.yml has no computed question to tell apart -- zero items"
    assert asked == set(questions) - computed, sorted(
        asked ^ (set(questions) - computed)
    )
    assert len(sets) >= 2, "canary.answer_sets holds %d set(s): %s" % (len(sets), sets)
    faults = [
        f
        for name, answers in sorted(sets.items())
        for f in answer_faults(name, answers, questions, jinja2)
    ]
    assert faults == [], faults
    default_stack = questions["frontend_stack"]["default"]
    stacks = {answers.get("frontend_stack", default_stack) for answers in sets.values()}
    assert len(stacks) >= 2, "every canary set renders the frontend stack %s" % stacks
    # The check can fail: copier.yml's own validator refuses this pair.
    refused = answer_faults(
        "fixture", {"frontend_stack": "astro", "showcase": False}, questions, jinja2
    )
    assert any("frontend_stack refuses it" in f for f in refused), refused
    assert answer_faults("fixture", {"no_such_question": 1}, questions, jinja2)
    assert answer_faults(
        "fixture", {"transports": ["carrier-pigeon"]}, questions, jinja2
    )


def _rel(module):
    return Path(module.__file__).resolve().relative_to(_ROOT).as_posix()


def _canary_workflows(yaml):
    found = {}
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        runs = [
            step.get("run", "")
            for job in (data.get("jobs") or {}).values()
            for step in job.get("steps") or ()
        ]
        if any(re.search(r"(^|\s)make canary\b", run) for run in runs):
            found[path] = data
    return found


def _release_steps():
    text = (_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    section = text.split("\n## Release\n", 1)[1].split("\n## ", 1)[0]
    steps = re.findall(r"^(\d+)\. (.*(?:\n   .*)*)", section, re.MULTILINE)
    return [(int(n), body) for n, body in steps]


def _recipe(target):
    """The prerequisites and recipe lines of *target* in the root Makefile."""
    lines = (_ROOT / "Makefile").read_text(encoding="utf-8").split("\n")
    for i, line in enumerate(lines):
        if re.match(r"^%s:" % re.escape(target), line):
            body = [line.split("##", 1)[0]]
            for nxt in lines[i + 1 :]:
                if not nxt.startswith("\t"):
                    break
                body.append(nxt)
            return "\n".join(body)
    raise AssertionError("the Makefile has no %s target" % target)


def test_the_canary_is_launched_by_schedule_dispatch_and_release_and_never_by_verify():
    yaml = optional_deps.importorskip("yaml", extra="template")
    workflows = _canary_workflows(yaml)
    assert workflows, "no workflow under %s runs `make canary`" % _WORKFLOWS
    for path, data in workflows.items():
        # YAML 1.1 reads the bare key `on` as true.
        triggers = data.get(True, data.get("on")) or {}
        assert "schedule" in triggers and "workflow_dispatch" in triggers, path
        checkouts = [
            step
            for job in data["jobs"].values()
            for step in job.get("steps") or ()
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert checkouts and all(
            (s.get("with") or {}).get("fetch-depth") == 0 for s in checkouts
        ), "%s: the canary needs the tags a full-history checkout carries" % path

    assert "canary" not in re.findall(r"[\w-]+", _recipe("verify"))
    assert "canary.py" not in _recipe("verify")

    steps = _release_steps()
    canary_steps = [n for n, body in steps if "make canary" in body]
    push_steps = [n for n, body in steps if "git push" in body]
    assert canary_steps and push_steps, steps
    assert max(canary_steps) < min(push_steps), steps

    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    assert _LAUNCH_KEY in manifest["launcher"]["long_scripts"]

    excluded = set(
        yaml.safe_load((_ROOT / "copier.yml").read_text("utf-8"))["_exclude"]
    )
    keel_only = {_rel(canary), _rel(template_snapshot)} | {
        p.relative_to(_ROOT).as_posix() for p in workflows
    }
    assert keel_only - excluded == set(), sorted(keel_only - excluded)


_UPLOAD = "actions/upload-artifact"
_SILENT = "ignore"


def upload_faults(name, data, scratch_root, variable):
    """One line per way the canary workflow *data* could upload nothing for a
    red run: a step or job or the workflow sets *variable* (the canary then
    renders somewhere the paths do not name), an upload path outside
    *scratch_root*, no upload step, or `if-no-files-found: ignore`."""
    faults = []
    root = scratch_root.rstrip("/") + "/"
    scopes = [("the workflow", data)]
    for job_id, job in sorted((data.get("jobs") or {}).items()):
        scopes.append(("job %s" % job_id, job))
        for i, step in enumerate(job.get("steps") or ()):
            scopes.append(("job %s step %d" % (job_id, i), step))
    uploads = []
    for where, scope in scopes:
        if variable in (scope.get("env") or {}):
            faults.append("%s: %s sets %s" % (name, where, variable))
        if str(scope.get("uses", "")).split("@", 1)[0] == _UPLOAD:
            uploads.append((where, scope.get("with") or {}))
    if not uploads:
        faults.append("%s: no %s step keeps a red run's projects" % (name, _UPLOAD))
    for where, given in uploads:
        paths = [
            p.strip() for p in str(given.get("path", "")).splitlines() if p.strip()
        ]
        if not [p for p in paths if not p.startswith("!")]:
            faults.append("%s: %s uploads no path" % (name, where))
        faults += [
            "%s: %s uploads %r, outside canary.scratch_root %r"
            % (name, where, p, scratch_root)
            for p in paths
            if not p.lstrip("!").startswith(root)
        ]
        if given.get("if-no-files-found") == _SILENT:
            faults.append("%s: %s says nothing when it finds no file" % (name, where))
    return faults


def test_the_workflow_uploads_what_the_canary_keeps_under_its_scratch_root():
    yaml = optional_deps.importorskip("yaml", extra="template")
    workflows = _canary_workflows(yaml)
    assert workflows, "no workflow under %s runs `make canary`" % _WORKFLOWS
    loaded = config_loader.read(str(_ROOT))
    row = config_loader.rows(("canary", "scratch_root"))[0]
    scratch = config_loader.resolve(loaded, [row], config_loader.CONFIG_FILE)[row.path]
    for path, data in workflows.items():
        assert upload_faults(path.name, data, scratch, row.env) == []
    # The check can fail: another scratch root, the variable set, a silent upload.
    path, data = sorted(workflows.items())[0]
    assert upload_faults(path.name, data, scratch + "-moved", row.env)
    job = dict(sorted(data["jobs"].items())[0][1], env={row.env: "/elsewhere"})
    assert upload_faults(path.name, dict(data, jobs={"j": job}), scratch, row.env)
    silent = [
        dict(s, **{"with": dict(s["with"], **{"if-no-files-found": _SILENT})})
        if str(s.get("uses", "")).startswith(_UPLOAD)
        else s
        for s in job["steps"]
    ]
    quiet = dict(data, jobs={"j": dict(job, env={}, steps=silent)})
    assert upload_faults(path.name, quiet, scratch, row.env)


def _git_out(cwd, *args):
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=child_env.build_child_env(),
    ).stdout.strip()


def test_one_set_renders_and_updates_with_real_copier_and_a_stub_make(
    tmp_path, monkeypatch, capsys
):
    """The `skeleton` set only: the farm's window holds one real render pair,
    and the full run, every set, is the canary itself on the farm."""
    optional_deps.importorskip("copier", extra="template")
    sets = _answer_sets()
    assert "skeleton" in sets, sorted(sets)
    systemp = tmp_path / "systemp"
    systemp.mkdir()
    # pytest's tmp_path lies under the system temporary directory, which the
    # canary refuses as a scratch root; this moves the refusal, not the check.
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(systemp))
    scratch = tmp_path / "canary"
    monkeypatch.setenv("KEEL_CANARY_SCRATCH", str(scratch))
    seen = {}

    def make(args, cwd, log):
        if args[-1] == "verify":
            answers = Path(cwd, ".copier-answers.yml").read_text(encoding="utf-8")
            commit = re.search(r"^_commit: (.+)$", answers, re.MULTILINE).group(1)
            src = re.search(r"^_src_path: (.+)$", answers, re.MULTILINE).group(1)
            seen[os.path.basename(cwd)] = (
                _git_out(src, "rev-parse", commit.strip("'\"") + "^{commit}"),
                _git_out(src, "rev-parse", "HEAD"),
            )
        return 0, log

    rc = canary.main(
        ["--set", "skeleton"], runner=canary.Runner(copier=None, git=None, make=make)
    )
    out = capsys.readouterr().out
    lines = [ln.split(" ") for ln in out.splitlines() if ln.strip()]
    assert rc == ExitCode.SUCCESS, out
    assert sorted((ln[0], ln[1], ln[2], ln[3]) for ln in lines) == [
        ("skeleton", "fresh", "verify", "pass"),
        ("skeleton", "update", "verify", "pass"),
    ], out
    recorded, head = seen["skeleton-update"]
    assert recorded and recorded == head, seen
    projects = {"skeleton-fresh", "skeleton-update"}
    assert sorted(p.name for p in scratch.rglob("*") if p.name in projects) == []


_GUIDES = _ROOT / "docs" / "guides"
_ELAPSED = re.compile(r"^\d+s$")


def _sections(path):
    """Each `## ` section of *path*: (heading, body) in file order."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return list(zip(parts[1::2], parts[2::2], strict=True))


def _section_naming(path, needle):
    """The body of the one `## ` section of *path* whose text holds *needle*."""
    found = [body for _, body in _sections(path) if needle in body]
    assert len(found) == 1, "%s: %d sections name %s" % (path, len(found), needle)
    return found[0]


class _FailAt(object):
    """copier, git and make for one canary run whose *k*-th call into a
    project fails; questions about the template checkout itself are answered
    so the previous release resolves."""

    def __init__(self, k):
        self.k = k
        self.n = 0

    def _query(self, args):
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return 0 if args[3] == "HEAD" and args[2] != "HEAD" else 1
        if args[:2] == ["ls-files", "--error-unmatch"]:
            return 1
        return 0

    def __call__(self, args, cwd, log):
        if os.path.realpath(cwd) == os.path.realpath(canary.ROOT):
            return self._query(args), log
        if args[0] == "copy":
            Path(args[-1]).mkdir(parents=True, exist_ok=True)
        index, self.n = self.n, self.n + 1
        return (1 if index == self.k else 0), log


def _steps_a_line_can_report(monkeypatch, tmp_path, capsys, name):
    """Every step a canary line names as failed, found by failing each call
    into a project in turn until a run passes, and the lines printed."""
    systemp = tmp_path / "systemp"
    systemp.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(systemp))
    monkeypatch.setenv("KEEL_CANARY_SCRATCH", str(tmp_path / "canary"))

    def fake_snapshot(template, scratch, extra, skip=(), label="snapshot"):
        snap = os.path.join(scratch, "template")
        os.makedirs(snap)
        return snap, []

    monkeypatch.setattr(canary, "snapshot_working_tree", fake_snapshot)
    failed, lines = set(), []
    for k in range(100):
        fake = _FailAt(k)
        rc = canary.main(
            ["--set", name], runner=canary.Runner(copier=fake, git=fake, make=fake)
        )
        out = [ln.split(" ") for ln in capsys.readouterr().out.splitlines() if ln]
        lines.extend(out)
        failed.update(ln[2] for ln in out if ln[3] == "fail")
        if rc == ExitCode.SUCCESS:
            return failed, lines
        assert rc == ExitCode.FAILURE, (k, rc, out)
    raise AssertionError("no canary run passed in 100 runs with one failing call")


def test_the_upgrade_guide_names_every_step_a_canary_line_can_report(
    tmp_path, monkeypatch, capsys
):
    """docs/guides/generate-and-upgrade.md's canary section names each step a
    line can report as failed, no other, and its example lines have the shape
    the canary prints; it names the answer-set key and the scratch variable."""
    sets = _answer_sets()
    failed, lines = _steps_a_line_can_report(
        monkeypatch, tmp_path, capsys, sorted(sets)[0]
    )
    assert "verify" in failed, failed
    section = _section_naming(_GUIDES / "generate-and-upgrade.md", "canary.answer_sets")
    documented = set(re.findall(r"^\| `([a-z-]+)` \|", section, re.MULTILINE))
    assert documented == failed, "documented %s, the canary reports %s" % (
        sorted(documented),
        sorted(failed),
    )
    assert "canary.answer_sets" in section
    assert config_loader.rows(("canary", "scratch_root"))[0].env in section

    fences = re.findall(r"^```text\n(.*?)^```", section, re.MULTILINE | re.DOTALL)
    examples = [ln.split() for f in fences for ln in f.splitlines() if ln.strip()]
    assert examples, "the canary section shows no example line in a text fence"
    width = {len(ln) for ln in lines}
    assert len(width) == 1, lines
    verdicts = {ln[3] for ln in lines}
    for ex in examples:
        assert len(ex) in width, ex
        assert ex[0] in sets and ex[1] in canary.PATHS, ex
        assert ex[2] in failed and ex[3] in verdicts, ex
        assert _ELAPSED.match(ex[5]) and all(_ELAPSED.match(ln[5]) for ln in lines)


def _report_messages():
    """The literal words of each `report(...)` *what failed* part in
    scripts/canary.py: a format string gives its runs of two or more words."""
    tree = ast.parse(Path(canary.__file__).read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "report"
            and len(node.args) >= 2
        ):
            continue
        what = node.args[1]
        if isinstance(what, ast.BinOp) and isinstance(what.op, ast.Mod):
            what = what.left
        assert isinstance(what, ast.Constant) and isinstance(what.value, str), (
            "line %d: a report message the test cannot read" % node.lineno
        )
        for chunk in re.split(r"%[-0-9.]*[sdr]", what.value):
            chunk = chunk.strip(" :;,()")
            if len(chunk.split()) >= 2:
                out.append(chunk)
    return out


def test_the_troubleshooting_guide_names_every_refusal_the_canary_prints():
    """docs/guides/limits-and-troubleshooting.md's symptom table quotes the
    words of every failure scripts/canary.py reports, and says what a kept
    project is."""
    messages = _report_messages()
    assert len(messages) >= 5, messages
    table = _section_naming(_GUIDES / "limits-and-troubleshooting.md", "| Symptom |")
    missing = [m for m in messages if m not in table]
    assert missing == [], "no symptom row quotes: %s" % missing
    assert "make canary" in table and "kept" in table
