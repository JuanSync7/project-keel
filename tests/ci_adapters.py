"""
title: Test helper — read each CI adapter's steps and judge it against config/project.json ci_pipeline
kind: tests
layer: n/a
summary: config/project.json `ci_pipeline` states the CI pipeline once, as an ordered list of shell steps; each adapter file (`ci_pipeline.adapters`, github's .github/workflows/ci.yml and gitlab's .gitlab-ci.yml) runs them. adapter_steps reads the neutral steps an adapter file runs, stdlib line-scanning so a test that imports nothing optional can use it: in a GitHub workflow they are the `run` steps after the last `uses:` setup step, with their `env` map and whether `continue-on-error` lets the job carry on; in a GitLab file they are the `test` job's `script` lines, a leading upper-case NAME=value being the step's env and `allow_failure` making every step soft. judged names the adapter files that are keel's, and shipped adds, in the template, an adapter present only as its `.jinja` twin, so a test about what CI runs reads every adapter keel ships. gitlab_line is the one way a step is written as a GitLab script line. parity_faults names every way the adapters under a root differ from the config: no step configured, no adapter present, a chosen adapter missing, a missing marker line, and steps that differ in content or order. The GitLab judge guards whether keel's `test` job runs and exactly what it runs, never where it runs or what else the project runs. It compares with keel's file the `test` job, the top-level keys GitLab applies to every job (`after_script`, `before_script`, `cache`, `default`, `image`, `include`, `services`, `variables`, `workflow`), and any other top-level key the `test` job reads through a YAML anchor or merge, `extends` or `!reference`; every other top-level key, `stages` or a job or hidden job only the project's own jobs read, is the project's own and is not compared. In the `test` job, `interruptible`, `retry`, `stage`, `tags` and `timeout` may be set, `image` may take the long form `{name: ...}` naming the same image, and every other key, `rules`, `when`, `needs`, `allow_failure`, `variables` and `script` among them, is compared. A variable compares as GitLab reads it: a number is its string, so `GIT_DEPTH: 0` equals `"0"`. The file is read with pyyaml's safe loader, the reader copier uses, so a quoted (`"when"`) or explicit (`? when`) key reads as the key itself, a key one mapping sets twice is a fault naming both lines, since YAML would keep the last in silence, and a `!reference` reads as a value no setting of keel's equals; then a compared key that gitlab_document (the shipped file, built from config: `ci_pipeline.gitlab_image` filled from `toolchain`, the steps, and `GIT_DEPTH` "0") lacks, sets otherwise, or sets and the file lacks is a fault naming its key path, and the `script`, one string or a list GitLab flattens, must run exactly the steps, judged line by line: a NAME=value prefix ends at a space or a tab, so it reaches only the command on its own line, and a line holding only NAME=value words is a fault naming its step. A comment, a blank line, key order, quoting, and flow or block style are edits YAML does not read, so none is a fault. Without pyyaml a GitLab file is a fault, never a pass. adapter_steps keeps its stdlib scanner for the gitlab twin keel ships, because tests/integration/test_gate_scope.py and tests/integration/test_copier_generator_contract.py read it and must never skip; tests/integration/test_ci_pipeline_gate.py holds that twin, read by yaml, equal to gitlab_document. The GitHub reader has no key check: a job-level `if:` or a changed `on:` passes (KEEL-CIGATE-1). Which adapters are judged follows the `ci_pipeline` answer in .copier-answers.yml: every chosen one, and an unchosen one only when it carries keel's marker line, so a file the project wrote itself, which `copier update` also keeps, is not held to keel's steps; the answers are read by the same YAML loader, the one copier reads them with, so a quoted, spaced or explicit `ci_pipeline` key reads as itself; the template has no answers file and judges every adapter present, and an answers file YAML cannot read, one that records no valid answer (shown by its line as written), and one that sets a key twice (named by both lines) is a fault. A GitHub layout the scanner cannot read gives steps that differ from the config, a GitLab file YAML cannot read, a control character included, is a fault naming the file, and a step shell words cannot split is a fault naming the step, so the judge fails closed and never raises on a file. It reads files and writes nothing.
"""

import json
import re
import shlex
from pathlib import Path

CONFIG = Path("config") / "project.json"
ANSWERS = Path(".copier-answers.yml")
# A step's env names are upper-case, so `index=$(...)` at the head of a run
# line is shell and never read as one. Only a space or a tab ends a prefix:
# bash passes NAME=value to the command on its own line, never the next one.
_ENV_PREFIX = re.compile(r"([A-Z][A-Z0-9_]*)=(\S+)[ \t]+")
# A line that is only NAME=value words sets an unexported shell variable that
# no command sees.
_ENV_ALONE = re.compile(r"(?:[A-Z][A-Z0-9_]*=\S*[ \t]*)+")


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
    `ci_pipeline` answer in .copier-answers.yml, read by _load as copier reads
    it, `both` naming every adapter; with no answers file (the template itself)
    it is None and every adapter present is keel's."""
    path = Path(root) / ANSWERS
    if not path.is_file():
        return None, None
    names = sorted(pipeline(root)["adapters"])
    answers, lines, _, fault = _load(path)
    if fault:
        return [], fault
    if not isinstance(answers, dict) or "ci_pipeline" not in answers:
        return [], "%s records no ci_pipeline answer" % ANSWERS
    value = answers["ci_pipeline"]
    if value == "both":
        return names, None
    if value in names:
        return [value], None
    number = lines["ci_pipeline"]
    return [], "%s line %d `%s` is not ci_pipeline 'both' or one of %s" % (
        ANSWERS,
        number,
        path.read_text("utf-8").splitlines()[number - 1],
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
        run, env = _split_env(line)
        steps.append({"run": run, "env": env, "soft": soft})
    return steps


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


# The top-level keys GitLab applies to every job, keel's `test` job among
# them; any other top-level key is `stages`, a job or a hidden job.
GITLAB_GLOBAL_KEYS = frozenset(
    {
        "after_script",
        "before_script",
        "cache",
        "default",
        "image",
        "include",
        "services",
        "variables",
        "workflow",
    }
)
# The `test` job keys that say where it runs or how a run is bounded, never
# whether it runs or what it runs.
GITLAB_PLACEMENT_KEYS = frozenset(
    {"interruptible", "retry", "stage", "tags", "timeout"}
)


class _Reference(tuple):
    """A GitLab `!reference [key, ...]`: a value another key holds, which no
    shell line or setting keel ships equals."""

    __slots__ = ()

    def __repr__(self):
        return "!reference [%s]" % ", ".join(map(str, self))


class _DoubledKey(ValueError):
    """A mapping in a YAML file sets one key twice."""


def _unique_key_loader(yaml):
    """pyyaml's safe loader, which is what copier reads answers with and reads
    a key as GitLab does, quoted (`"when"`) or explicit (`? when`) alike, with
    two changes: a mapping that sets a key twice raises _DoubledKey with both
    lines, where the safe loader would keep the last in silence, and GitLab's
    `!reference` reads as a _Reference, where the safe loader would fail the
    whole file over a tag in a job that is the project's own."""

    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            seen = {}
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    key = "<<"
                elif isinstance(key_node, yaml.ScalarNode):
                    key = self.construct_object(key_node)
                else:
                    continue
                line = key_node.start_mark.line + 1
                if key in seen:
                    raise _DoubledKey(key, seen[key], line)
                seen[key] = line
            return super().construct_mapping(node, deep=deep)

    UniqueKeyLoader.add_constructor(
        "!reference",
        lambda loader, node: _Reference(loader.construct_sequence(node)),
    )
    return UniqueKeyLoader


def _load(path):
    """(the YAML document at *path*, {top-level key: its line}, its YAML node
    graph, fault or None).
    The fault names a key set twice with both lines as written, any other YAML
    error, and a missing pyyaml: the dev extra installs it (pre-commit needs
    it) and the template extra too (copier needs it), and without it nothing
    may be judged a pass."""
    try:
        import yaml
    except ImportError:
        return (
            None,
            {},
            None,
            (
                "%s cannot be judged: pyyaml is not importable; install the dev extra"
                % path.name
            ),
        )
    text = path.read_text("utf-8")
    loader = None
    try:
        # The reader refuses a control character as it is built, so it is
        # built where a YAML error becomes a fault.
        loader = _unique_key_loader(yaml)(text)
        node = loader.get_single_node()
        doc = None if node is None else loader.construct_document(node)
    except _DoubledKey as e:
        key, first, second = e.args
        lines = text.splitlines()
        return (
            None,
            {},
            None,
            (
                "%s sets `%s` twice, line %d `%s` and line %d `%s`; YAML keeps the "
                "last, so keep one"
                % (path.name, key, first, lines[first - 1], second, lines[second - 1])
            ),
        )
    except yaml.YAMLError as e:
        return None, {}, None, "%s: %s" % (path.name, " ".join(str(e).split()))
    finally:
        if loader is not None:
            loader.dispose()
    top = {}
    if isinstance(node, yaml.MappingNode):
        for key_node, _ in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                top.setdefault(key_node.value, key_node.start_mark.line + 1)
    return doc, top, node, None


def gitlab_document(root):
    """The .gitlab-ci.yml keel ships under *root*, as YAML reads it: the
    `test` job's image is `ci_pipeline.gitlab_image` filled from `toolchain`,
    its script the configured steps, and `GIT_DEPTH` is "0" for the same
    reason ci.yml checks out with fetch-depth: 0."""
    config = json.loads((Path(root) / CONFIG).read_text("utf-8"))
    block = config["ci_pipeline"]
    return {
        "variables": {"GIT_DEPTH": "0"},
        "test": {
            "image": block["gitlab_image"].format(**config["toolchain"]),
            "script": [gitlab_line(step) for step in block["steps"]],
        },
    }


_ABSENT = object()


def _differences(got, want, path=()):
    """(key path, got, want) for each key *got* sets that *want* lacks or sets
    otherwise, then each key *want* sets that *got* lacks, descending only
    where both are mappings, so a key keel does not ship is named whole."""
    if not (isinstance(got, dict) and isinstance(want, dict)):
        if got != want:
            yield ".".join(path), got, want
        return
    for key in list(got) + [key for key in want if key not in got]:
        yield from _differences(
            got.get(key, _ABSENT), want.get(key, _ABSENT), path + (str(key),)
        )


def _script(value):
    """The shell lines a GitLab `script` value runs, or None when it is no
    script: one string is one line, and a list is flattened, as GitLab
    flattens a nested one."""
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return None
    lines = []
    for item in value:
        found = _script(item)
        if found is None:
            return None
        lines.extend(found)
    return lines


def _split_env(line):
    """(command, {NAME: value}) for a script line led by NAME=value words."""
    env = {}
    match = _ENV_PREFIX.match(line)
    while match:
        env[match.group(1)] = shlex.split(match.group(2))[0]
        line = line[match.end() :]
        match = _ENV_PREFIX.match(line)
    return line, env


def _reads(node):
    """(the id of every YAML node under *node*, the top-level keys a
    `!reference` under it names). An alias is the node its anchor marks, so
    two keys that share an id share a value."""
    seen, names, stack = set(), set(), [node]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        children = current.value if isinstance(current.value, list) else []
        if current.tag == "!reference" and children:
            names.add(children[0].value)
        for child in children:
            stack.extend(child if isinstance(child, tuple) else (child,))
    return seen, names


def _judged_keys(node, doc):
    """The top-level keys of a GitLab document that are compared with keel's:
    `test`, each of GITLAB_GLOBAL_KEYS, and, until none is added, a key whose
    value shares a node with a judged one (an anchor, a merge), that a judged
    job `extends`, or that a judged `!reference` names. A merge into the top
    level is judged, since it can set any of them."""
    values = {
        key.value: value for key, value in node.value if isinstance(key.value, str)
    }
    judged = {"test", "<<"} | (GITLAB_GLOBAL_KEYS & set(values))
    while True:
        ids, names = set(), set()
        for key in sorted(judged & set(values)):
            found, referenced = _reads(values[key])
            ids |= found
            names |= referenced
            extends = (
                doc.get(key, {}).get("extends")
                if isinstance(doc.get(key), dict)
                else None
            )
            names |= {extends} if isinstance(extends, str) else set(extends or [])
        more = {
            key
            for key, value in values.items()
            if key not in judged
            and (key in names or not ids.isdisjoint(_reads(value)[0]))
        }
        if not more:
            return judged
        judged |= more


def _cast(variables):
    """A GitLab `variables` map as GitLab reads it: a number is its string."""
    if not isinstance(variables, dict):
        return variables
    return {
        name: str(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else value
        for name, value in variables.items()
    }


def _compared(doc, judged):
    """The part of a GitLab document compared with keel's: the *judged*
    top-level keys, variables as GitLab reads them, and the `test` job without
    GITLAB_PLACEMENT_KEYS and with a long-form image `{name: ...}` read as
    its name."""
    doc = {key: value for key, value in doc.items() if key in judged}
    if "variables" in doc:
        doc["variables"] = _cast(doc["variables"])
    job = doc.get("test")
    if isinstance(job, dict):
        job = {k: v for k, v in job.items() if k not in GITLAB_PLACEMENT_KEYS}
        image = job.get("image")
        if isinstance(image, dict) and list(image) == ["name"]:
            job["image"] = image["name"]
        if "variables" in job:
            job["variables"] = _cast(job["variables"])
        doc["test"] = job
    return doc


def _gitlab_faults(root, path, want):
    """A message per way the GitLab file at *path* differs from
    gitlab_document: every key path it sets that keel's does not, or sets to
    another value, or lacks, and a script that does not run *want*."""
    doc, _, node, fault = _load(path)
    if fault:
        return [fault]
    if not isinstance(doc, dict):
        return ["%s holds %r, not a mapping of jobs" % (path.name, doc)]
    doc = _compared(doc, _judged_keys(node, doc))
    shipped_doc = gitlab_document(root)
    shipped_job = shipped_doc["test"]
    job = doc.get("test")
    # The script is judged as steps, so a value YAML writes another way
    # (a flow list, one string, a nested list) is not a difference.
    script = _ABSENT
    if isinstance(job, dict) and "script" in job:
        job = dict(job)
        script = job.pop("script")
        doc = dict(doc, test=job)
    shipped_doc["test"] = {k: v for k, v in shipped_job.items() if k != "script"}
    faults = []
    for key, got, keel in _differences(doc, shipped_doc):
        if got is _ABSENT:
            said = "is missing, and keel's adapter sets it to %r" % (keel,)
        elif keel is _ABSENT and "." not in key and key not in GITLAB_GLOBAL_KEYS:
            said = (
                "is %r, and the `test` job reads it (an anchor, `extends` or "
                "`!reference`) where keel's adapter has no `%s`: remove it, or "
                "the job may skip or change keel's gate steps" % (got, key)
            )
        elif keel is _ABSENT:
            said = (
                "is %r, and keel's adapter sets no `%s`: remove it, or the job "
                "may skip or change keel's gate steps" % (got, key)
            )
        else:
            said = "is %r, and keel's adapter sets %r%s" % (
                got,
                keel,
                _FROM.get(key, ""),
            )
        faults.append("%s: `%s` %s" % (path.name, key, said))
    lines = [] if script is _ABSENT else _script(script)
    if lines is None:
        faults.append(
            "%s: `test.script` is %r, not a shell line or a list of them"
            % (path.name, script)
        )
        return faults
    got = []
    for number, step in enumerate(lines, 1):
        # A multi-line step is one shell script, so each line is judged as a
        # step of its own and a blank line runs nothing.
        for line in step.split("\n"):
            if not line.strip():
                continue
            if _ENV_ALONE.fullmatch(line.strip()):
                faults.append(
                    "%s: `test.script` step %d sets `%s` on a line of its own, so "
                    "the shell passes it to no command: write it before the "
                    "command, on that command's line"
                    % (path.name, number, line.strip())
                )
            try:
                got.append(_split_env(line))
            except ValueError as e:
                faults.append(
                    "%s: `test.script` step %d `%s` cannot be split into shell "
                    "words (%s): write each env value without a space"
                    % (path.name, number, line, e)
                )
                got.append((line, {}))
    if got != want:
        faults.append(
            "%s runs %s, not config/project.json ci_pipeline.steps %s"
            % (path.name, got, want)
        )
    return faults


# Where a value of gitlab_document comes from, for a fault to say.
_FROM = {
    "test.image": " (config/project.json ci_pipeline.gitlab_image filled from toolchain)"
}


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
        if marker(root, name) not in _lines(path):
            faults.append("%s: no line `%s`" % (path.name, marker(root, name)))
        if name == "gitlab":
            faults.extend(_gitlab_faults(root, path, want))
            continue
        got = [(s["run"], s["env"]) for s in adapter_steps(path, name)]
        if got != want:
            faults.append(
                "%s runs %s, not config/project.json ci_pipeline.steps %s"
                % (path.name, got, want)
            )
    return faults
