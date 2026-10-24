"""
title: Test helper — read each CI adapter's steps and judge it against config/project.json ci_pipeline
kind: tests
layer: n/a
summary: config/project.json `ci_pipeline` states the CI pipeline once, as an ordered list of shell steps; each adapter file (`ci_pipeline.adapters`, github's .github/workflows/ci.yml and gitlab's .gitlab-ci.yml) runs them. adapter_steps reads the neutral steps an adapter file runs, stdlib line-scanning so a test that imports nothing optional can use it: in a GitHub workflow they are the `run` steps after the last `uses:` setup step, with their `env` map and whether `continue-on-error` lets the job carry on; in a GitLab file they are the `test` job's `script` lines, a leading upper-case NAME=value being the step's env and `allow_failure` making every step soft. judged names the adapter files that are keel's, and shipped adds, in the template, an adapter present only as its `.jinja` twin, so a test about what CI runs reads every adapter keel ships. gitlab_line is the one way a step is written as a GitLab script line. parity_faults names every way the adapters under a root differ from the config: no step configured, no adapter present, a chosen adapter missing, a missing marker line, steps that differ in content or order, and for gitlab an image other than `gitlab_image` filled from `toolchain`, a `GIT_DEPTH` other than "0", or any key that decides whether or how the `test` job runs (top-level `before_script`, `default`, `include`, `workflow`; the job's `before_script`, `except`, `extends`, `only`, `rules`, `when` or a `<<` merge key), none of which keel's twin sets. The GitHub reader has no such check: a job-level `if:` or a changed `on:` passes (KEEL-CIGATE-1). Which adapters are judged follows the `ci_pipeline` answer in .copier-answers.yml: every chosen one, and an unchosen one only when it carries keel's marker line, so a file the project wrote itself, which `copier update` also keeps, is not held to keel's steps; the template has no answers file and judges every adapter present, and an answers file that records no valid answer, or answers twice (YAML would read the last line, a scan the first), is a fault that shows each line as written. A layout the scanner cannot read gives steps that differ from the config, so the judge fails closed. It reads files and writes nothing.
"""

import json
import re
import shlex
from pathlib import Path

CONFIG = Path("config") / "project.json"
ANSWERS = Path(".copier-answers.yml")
# A step's env names are upper-case, so `index=$(...)` at the head of a run
# line is shell and never read as one.
_ENV_PREFIX = re.compile(r"([A-Z][A-Z0-9_]*)=(\S+)\s+")


def pipeline(root):
    """config/project.json `ci_pipeline` under *root*."""
    return json.loads((Path(root) / CONFIG).read_text("utf-8"))["ci_pipeline"]


def present(root):
    """{adapter name: path} for each adapter file that exists under *root*."""
    adapters = pipeline(root)["adapters"]
    return {
        name: Path(root) / rel
        for name, rel in sorted(adapters.items())
        if (Path(root) / rel).is_file()
    }


def chosen(root):
    """(adapter names the project chose, fault or None). The choice is the
    `ci_pipeline` line of .copier-answers.yml, `both` naming every adapter; with
    no answers file (the template itself) it is None and every adapter present
    is keel's."""
    path = Path(root) / ANSWERS
    if not path.is_file():
        return None, None
    names = sorted(pipeline(root)["adapters"])
    answers = [
        (number, line)
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1)
        if re.fullmatch(r"ci_pipeline:(.*)", line)
    ]
    if not answers:
        return [], "%s records no ci_pipeline answer" % ANSWERS
    if len(answers) > 1:
        # YAML reads the last and this scan would read the first, so neither
        # may decide what is judged.
        return [], "%s answers ci_pipeline more than once (%s): keep one" % (
            ANSWERS,
            ", ".join("line %d `%s`" % answer for answer in answers),
        )
    number, line = answers[0]
    value = _scalar(line[len("ci_pipeline:") :])
    if value == "both":
        return names, None
    if value in names:
        return [value], None
    return [], "%s line %d `%s` is not ci_pipeline 'both' or one of %s" % (
        ANSWERS,
        number,
        line,
        names,
    )


def marker(root, name):
    """The exact line an adapter file keel wrote carries."""
    return pipeline(root)["marker"].format(adapter=name)


def _scalar(value):
    """A one-line YAML scalar as its string: double- or single-quoted, or plain
    with a trailing ` #` comment cut."""
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return json.loads(value)
    if value.startswith("'") and value.endswith("'") and len(value) > 1:
        return value[1:-1].replace("''", "'")
    return re.split(r"\s#", value, maxsplit=1)[0].strip()


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _github_steps(text):
    steps, current, env_indent = [], None, None
    for line in text.splitlines():
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        if body.startswith("- "):
            current = {"keys": {}, "env": {}}
            steps.append(current)
            body = body[2:].strip()
            env_indent = None
        elif current is None:
            continue
        elif env_indent is not None and _indent(line) > env_indent:
            key, _, value = body.partition(":")
            current["env"][key.strip()] = _scalar(value)
            continue
        env_indent = None
        key, sep, value = body.partition(":")
        if not sep:
            continue
        if key.strip() == "env" and not value.strip():
            env_indent = _indent(line)
            continue
        current["keys"][key.strip()] = _scalar(value)
    setup = [i for i, step in enumerate(steps) if "uses" in step["keys"]]
    after = steps[setup[-1] + 1 :] if setup else steps
    return [
        {
            "run": step["keys"]["run"],
            "env": step["env"],
            "soft": step["keys"].get("continue-on-error") not in (None, "false"),
        }
        for step in after
        if "run" in step["keys"]
    ]


def _gitlab_lines(text):
    """-> ({top-level dotted key: scalar} for `variables.*` and `test.*`, the
    `test` job's script items)."""
    keys, script, section, script_indent = {}, [], None, None
    for line in text.splitlines():
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        indent = _indent(line)
        if (
            script_indent is not None
            and indent > script_indent
            and body.startswith("- ")
        ):
            script.append(_scalar(body[2:]))
            continue
        script_indent = None
        key, _, value = body.partition(":")
        if indent == 0:
            section = key.strip()
            continue
        if section == "test" and key.strip() == "script" and not value.strip():
            script_indent = indent
            continue
        keys["%s.%s" % (section, key.strip())] = _scalar(value)
    return keys, script


def _gitlab_steps(text):
    keys, script = _gitlab_lines(text)
    soft = keys.get("test.allow_failure") not in (None, "false")
    steps = []
    for line in script:
        env = {}
        match = _ENV_PREFIX.match(line)
        while match:
            env[match.group(1)] = shlex.split(match.group(2))[0]
            line = line[match.end() :]
            match = _ENV_PREFIX.match(line)
        steps.append({"run": line, "env": env, "soft": soft})
    return steps


# The GitLab keys that decide whether, and how, the `test` job runs its
# script: a top-level one applies to every job, a `test.` one to that job.
# keel's twin sets none of them, so any is a fault; each is a shape that
# passed the step check while running no step (`when: manual`, `rules` with
# `when: never`, a `before_script` that exits 0, an `extends` or `include`
# that replaces the job).
_GITLAB_TOP_RUN_KEYS = ("before_script", "default", "include", "workflow")
_GITLAB_JOB_RUN_KEYS = ("before_script", "except", "extends", "only", "rules", "when")


def _gitlab_run_keys(text):
    """The run-deciding keys a GitLab file sets, in file order: each top-level
    one by name, each of the `test` job's own as `test.<key>`; a YAML merge
    key (`<<`) under `test` counts too, since it can carry any of them."""
    found, section, child = [], None, None
    for line in text.splitlines():
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        indent = _indent(line)
        key = body.partition(":")[0].strip()
        if indent == 0:
            section, child = key, None
            if key in _GITLAB_TOP_RUN_KEYS:
                found.append(key)
            continue
        if section != "test":
            continue
        if child is None:
            child = indent
        if indent == child and (key in _GITLAB_JOB_RUN_KEYS or key == "<<"):
            found.append("test." + key)
    return found


_READERS = {"github": _github_steps, "gitlab": _gitlab_steps}


def adapter_steps(path, name):
    """[{run, env, soft}] the adapter *name* at *path* runs, in order."""
    return _READERS[name](Path(path).read_text("utf-8"))


def gitlab_line(step):
    """A configured step as the GitLab script line that runs it."""
    env = step.get("env", {})
    prefix = "".join(
        "%s=%s " % (key, shlex.quote(value)) for key, value in sorted(env.items())
    )
    return prefix + step["run"]


def _lines(path):
    return Path(path).read_text("utf-8").splitlines()


def judged(root):
    """{adapter name: path} for each adapter file under *root* that is keel's:
    every one present in the template, and in a project each chosen one plus an
    unchosen one that carries keel's marker line."""
    choice, _ = chosen(root)
    # An adapter the project did not choose and that carries no marker is the
    # project's own file, which update also keeps (copier.yml).
    return {
        name: path
        for name, path in present(root).items()
        if choice is None or name in choice or marker(root, name) in _lines(path)
    }


def shipped(root):
    """judged(root), plus in the template each adapter that ships only as its
    `.jinja` twin: its step lines carry no jinja, so the scanner reads them as
    they render."""
    found = judged(root)
    for name, rel in sorted(pipeline(root)["adapters"].items()):
        twin = Path(root) / (rel + ".jinja")
        if name not in found and twin.is_file():
            found[name] = twin
    return found


def parity_faults(root):
    """A message per way the adapters under *root* differ from
    config/project.json `ci_pipeline`."""
    config = pipeline(root)
    want = [(step["run"], step.get("env", {})) for step in config["steps"]]
    if not want:
        return ["config/project.json ci_pipeline.steps is empty: no adapter is judged"]
    choice, fault = chosen(root)
    if fault:
        return [fault]
    found = judged(root)
    faults = [
        "the chosen adapter %s (%s) is missing" % (name, config["adapters"][name])
        for name in choice or []
        if name not in found
    ]
    if not found:
        return faults or [
            "no CI adapter of config/project.json ci_pipeline.adapters (%s) is "
            "present: the pipeline runs nowhere" % sorted(config["adapters"].values())
        ]
    for name, path in found.items():
        text = path.read_text("utf-8")
        if marker(root, name) not in text.splitlines():
            faults.append("%s: no line `%s`" % (path.name, marker(root, name)))
        got = [(s["run"], s["env"]) for s in adapter_steps(path, name)]
        if got != want:
            faults.append(
                "%s runs %s, not config/project.json ci_pipeline.steps %s"
                % (path.name, got, want)
            )
        if name == "gitlab":
            keys, _ = _gitlab_lines(text)
            toolchain = json.loads((Path(root) / CONFIG).read_text("utf-8"))[
                "toolchain"
            ]
            image = config["gitlab_image"].format(**toolchain)
            if keys.get("test.image") != image:
                faults.append(
                    "%s: image %r, not ci_pipeline.gitlab_image filled from toolchain %r"
                    % (path.name, keys.get("test.image"), image)
                )
            faults.extend(
                "%s: `%s` decides whether or how the test job runs, and keel's "
                "adapter sets no `%s`: remove it, or the job may pass without "
                "running a step" % (path.name, key, key)
                for key in _gitlab_run_keys(text)
            )
            if keys.get("variables.GIT_DEPTH") != "0":
                faults.append(
                    '%s: GIT_DEPTH %r, not "0"'
                    % (path.name, keys.get("variables.GIT_DEPTH"))
                )
    return faults
