"""
title: Integration — no file a commit could carry holds a value under a secret name
kind: tests
layer: n/a
summary: keel's own rule against a committed credential, with no outside tool. The secret names are derived from scripts/config_loader.py KEYS: each row with secret=True gives its variable name, and its config path in the file it names when it has one. The candidate files are what a commit could carry: scripts/git_tree.py candidate_files (tracked, staged, and untracked but not ignored), and, with no repository, every file scripts/check_structure.py walk reaches, ignored ones included, which is stricter. A file is judged by its basename against config/project.json secrets.json_files (JSON) and secrets.dotenv_files (`KEY=VALUE` lines), and in a repository both its work-tree copy and its index copy are judged, so a value staged and then blanked on disk is still seen. A JSON object member, at any depth, whose key is a secret variable name, or whose path is a secret row's path in that row's file, is red unless its value is "" or null; a list that holds the name is not a value. A dotenv line that assigns a secret name anything but the empty value is red: blank lines and `#` comments are skipped, `export ` is accepted, whitespace around `=` is allowed and one pair of matching outer quotes is stripped, so `${OTHER}` and `changeme` are values. A JSON file that does not parse is red. A secret row with a default other than null is red, every name models.credential_env lists must have a secret KEYS row, and no secret row's variable may be in child_env.names, which every child inherits. Judging zero secret names or zero files is a failure. Each finding is `<file>:<line>: <key> — <rule>`, never the value. It cannot see a value under a name no secret row declares, a file type it does not parse (YAML, TOML, source code), a basename outside both patterns, a value already in history, or an encoded value: those are the secret scanner's or nobody's, as docs/guides/deterministic-checks.md says.
"""

import copy
import fnmatch
import json
import os
import random
import shutil
import string
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
import git_tree  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.integration

_LOADER = "scripts/config_loader.py"
_DOTENV_ROW = ("secrets", "dotenv_files")
_JSON_ROW = ("secrets", "json_files")
_ALLOWLIST_ROW = ("child_env",)
# The only placeholders: .env.example ships a secret name with an empty
# value, and a JSON config writes "not set" as "" or null. Anything else under
# a secret name is a value, `changeme` and `${OTHER}` included.
_EMPTY_JSON = ("", None)
_EXPORT = "export"
_QUOTES = "\"'"
_FIX_FILE = (
    "never commit a credential: leave it empty here and set it in the "
    "environment or a git-ignored file; if it was real, rotate it first "
    "(docs/guides/limits-and-troubleshooting.md, 'A credential was committed')"
)


class SecretGateError(Exception):
    """The gate cannot judge: its policy is unreadable, or it would judge zero
    secret names or zero files. Never a pass."""


class Finding(NamedTuple):
    """One red: where, which key, and why; never the value."""

    file: str
    line: Optional[int]
    key: str
    rule: str


def format_finding(f):
    where = f.file if f.line is None else "%s:%d" % (f.file, f.line)
    return "%s: %s — %s" % (where, f.key, f.rule)


def secret_names(keys):
    """(names, paths): the variable names of *keys*' secret rows, and
    {file: {path}} of the config paths of those that live in a file."""
    names, paths = set(), {}
    for key in keys:
        if not key.secret:
            continue
        if key.env is not None:
            names.add(key.env)
        if key.file is not None:
            paths.setdefault(key.file, set()).add(tuple(key.path))
    return names, paths


def policy(root, keys=config_loader.KEYS):
    """{dotenv, json, allowlist, credentials}: the patterns, child_env.names and
    every models.credential_env name of *root*'s config/project.json. Raises
    SecretGateError for a config the loader refuses."""
    try:
        manifest = config_loader.read(str(root))
        got = config_loader.resolve(
            manifest,
            [k for k in keys if k.path in (_DOTENV_ROW, _JSON_ROW, _ALLOWLIST_ROW)],
            config_loader.CONFIG_FILE,
            environ={},
        )
    except config_loader.ConfigError as exc:
        raise SecretGateError("; ".join(exc.lines)) from exc
    allowlist = got[_ALLOWLIST_ROW].get("names", [])
    credentials = (manifest.get("models") or {}).get("credential_env", {})
    if not isinstance(credentials, dict) or not all(
        isinstance(v, list) and all(isinstance(n, str) and n for n in v)
        for v in credentials.values()
    ):
        raise SecretGateError(
            "%s: models.credential_env must map each adapter to a list of "
            "variable names" % config_loader.CONFIG_FILE
        )
    if not isinstance(allowlist, list):
        raise SecretGateError(
            "%s: child_env.names must be a list" % config_loader.CONFIG_FILE
        )
    return {
        "dotenv": list(got[_DOTENV_ROW]),
        "json": list(got[_JSON_ROW]),
        "allowlist": sorted(allowlist),
        "credentials": sorted({n for v in credentials.values() for n in v}),
    }


def rule_findings(rules, keys):
    """The reds in the table itself: a secret row with a default, a credential
    variable with no secret row, and a secret variable every child inherits."""
    out = []
    by_env = {}
    for key in keys:
        if key.env is not None:
            by_env.setdefault(key.env, []).append(key)
        if (
            key.secret
            and key.default is not None
            and key.default is not config_loader.NONE
        ):
            out.append(
                Finding(
                    _LOADER,
                    None,
                    ".".join(key.path),
                    "a secret KEYS row has a default; a secret's default is null",
                )
            )
    out.extend(
        Finding(
            config_loader.CONFIG_FILE,
            None,
            "models.credential_env %s" % name,
            "a credential variable needs a secret variable-only row in "
            "%s KEYS, so the gate judges a value under its name" % _LOADER,
        )
        for name in rules["credentials"]
        if not any(k.secret for k in by_env.get(name, []))
    )
    out.extend(
        Finding(
            config_loader.CONFIG_FILE,
            None,
            "child_env.names %s" % name,
            "a secret variable in the base allowlist reaches every "
            "child; name it in models.credential_env instead",
        )
        for name in rules["allowlist"]
        if any(k.secret for k in by_env.get(name, []))
    )
    return out


def candidates(root):
    """(paths, in_repo): what a commit could carry, from git; with no
    repository, every file the structure walk reaches. A repository git cannot
    read raises GitFailedError: unknown is not absent."""
    try:
        return git_tree.candidate_files(str(root)), True
    except git_tree.NoGitError:
        out = []
        for dirpath, _dirs, files in cs.walk(str(root)):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), str(root))
                out.append(rel.replace(os.sep, "/"))
        return sorted(out), False


def _matches(rel, patterns):
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(base, p) for p in patterns)


def _line_of(text, offset):
    return text.count("\n", 0, offset) + 1


_WS = " \t\n\r"
_SCALARS = json.JSONDecoder()


def _skip(text, i):
    while i < len(text) and text[i] in _WS:
        i += 1
    return i


def json_members(text):
    """[(path, value, offset)] for every object member in *text* at any depth,
    in document order, a key written twice listed twice. *text* must already
    have parsed as JSON; the walk only adds where each member's name starts."""
    out = []

    def value_at(i, path):
        i = _skip(text, i)
        opener = text[i : i + 1]
        if opener not in ("{", "["):
            return _SCALARS.raw_decode(text, i)
        closer = "}" if opener == "{" else "]"
        holder = {} if opener == "{" else []
        i = _skip(text, i + 1)
        if text[i : i + 1] == closer:
            return holder, i + 1
        while True:
            if opener == "{":
                start = i
                name, i = json.decoder.scanstring(text, i + 1)
                i = _skip(text, i) + 1  # past the ':' json.loads already checked
                value, i = value_at(i, path + (name,))
                out.append((path + (name,), value, start))
                holder[name] = value
            else:
                value, i = value_at(i, path + (len(holder),))
                holder.append(value)
            i = _skip(text, i)
            if text[i] == closer:
                return holder, i + 1
            i = _skip(text, i + 1)  # past the ','

    value_at(0, ())
    return out


def judge_json(rel, text, names, paths):
    """The reds in one JSON file's text: a member keyed by a secret name, or at
    a secret row's path, whose value is not "" or null; a text that does not
    parse is red too, since it cannot be judged."""
    try:
        json.loads(text)
    except ValueError as exc:
        line = getattr(exc, "lineno", None)
        return [
            Finding(
                rel,
                line,
                "(the file)",
                "does not parse as JSON, so it cannot be judged",
            )
        ]
    out = []
    for path, value, offset in json_members(text):
        if value in _EMPTY_JSON:
            continue
        name = path[-1]
        if name in names:
            rule = "a value under the secret variable name %s" % name
        elif path in paths:
            rule = "a value at a secret KEYS row's path"
        else:
            continue
        out.append(
            Finding(
                rel,
                _line_of(text, offset),
                ".".join(str(p) for p in path),
                "%s; %s" % (rule, _FIX_FILE),
            )
        )
    return out


# U+FEFF, the byte order mark a Windows editor starts a file with, is
# whitespace to the dotenv loaders (JavaScript's \s holds it) and not to
# str.strip or str.split, so it is turned into a space before either runs.
_ZWNBSP = "\ufeff"


def dotenv_assignments(text):
    """[(line, name, value)] for each `KEY=VALUE` line of a dotenv text, with
    `export ` dropped, whitespace around `=` and around the value stripped, and
    one pair of matching outer quotes removed. A line ends at LF, CRLF or a
    bare CR, as the loaders split it, and U+FEFF counts as whitespace. Blank
    lines, `#` comments and a line with no `=` assign nothing."""
    out = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for number, raw in enumerate(lines, 1):
        line = raw.replace(_ZWNBSP, " ").strip()
        if not line or line.startswith("#"):
            continue
        head, sep, value = line.partition("=")
        if not sep:
            continue
        words = head.split()
        if len(words) == 2 and words[0] == _EXPORT:
            words = words[1:]
        if len(words) != 1:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES:
            value = value[1:-1]
        out.append((number, words[0], value))
    return out


def judge_dotenv(rel, text, names):
    """The reds in one dotenv file's text: a secret name assigned anything but
    the empty value."""
    return [
        Finding(
            rel,
            number,
            name,
            "a value for the secret variable %s; %s" % (name, _FIX_FILE),
        )
        for number, name, value in dotenv_assignments(text)
        if name in names and value != ""
    ]


def _copies(root, rel, in_repo):
    """The texts a commit could carry for *rel*: the work-tree file (never one
    reached through a symlink, whose commit carries only the link) and, in a
    repository, the index copy when it differs (none for a symlink, whose blob
    is its target's path). A leading byte order mark is dropped, as the
    loaders that accept one drop it. Raises SecretGateError for bytes that are
    not UTF-8, which cannot be judged."""
    full = os.path.join(str(root), rel)
    blobs = []
    if not os.path.islink(full) and os.path.isfile(full):
        with open(full, "rb") as fh:
            blobs.append(fh.read())
    if in_repo:
        staged = git_tree.staged_blob(str(root), rel)
        if staged is not None and staged not in blobs:
            blobs.append(staged)
    try:
        return [blob.decode("utf-8-sig") for blob in blobs]
    except UnicodeDecodeError as exc:
        raise SecretGateError(
            "%s is not UTF-8 (%s), so it cannot be judged" % (rel, exc.reason)
        ) from exc


def judge(root, keys=config_loader.KEYS):
    """(findings, judged): every red under *root*, sorted and without repeats,
    and {names, json, dotenv} of what was judged. Raises SecretGateError for
    zero secret names or zero judged files."""
    names, paths = secret_names(keys)
    if not names and not paths:
        raise SecretGateError(
            "%s KEYS has no secret row -- zero secret names to judge" % _LOADER
        )
    rules = policy(root, keys)
    files, in_repo = candidates(root)
    found = set(rule_findings(rules, keys))
    judged = {"names": sorted(names), "json": [], "dotenv": []}
    for rel in files:
        if _matches(rel, rules["json"]):
            judged["json"].append(rel)
            for text in _copies(root, rel, in_repo):
                found.update(judge_json(rel, text, names, paths.get(rel, set())))
        elif _matches(rel, rules["dotenv"]):
            judged["dotenv"].append(rel)
            for text in _copies(root, rel, in_repo):
                found.update(judge_dotenv(rel, text, names))
    if not judged["json"] and not judged["dotenv"]:
        raise SecretGateError(
            "%s: no file a commit could carry matches secrets.json_files or "
            "secrets.dotenv_files -- zero files judged" % root
        )
    return sorted(found, key=lambda f: (f.file, f.line or 0, f.key, f.rule)), judged


def findings(root, keys=config_loader.KEYS):
    """Every red under *root*, as judge gives it."""
    return judge(root, keys)[0]


# --- keel's own tree ---------------------------------------------------------


def test_no_file_a_commit_could_carry_holds_a_value_for_a_secret_name():
    found, judged = judge(_ROOT)
    assert judged["names"], "no secret variable name -- zero items"
    assert judged["json"], "no JSON file judged -- zero items"
    assert judged["dotenv"], "no dotenv file judged (.env.example) -- zero items"
    assert found == [], "\n".join(format_finding(f) for f in found)


def test_the_procedure_a_finding_cites_is_a_heading_of_that_guide():
    """A red names where to read what to do; that heading must be there."""
    cited = _FIX_FILE.rpartition("(")[2].rstrip(")")
    guide, _sep, quoted = cited.partition(", ")
    title = quoted.strip("'")
    headings = [
        line.lstrip("#").strip()
        for line in (_ROOT / guide).read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    ]
    assert title in headings, "%s has no `## %s` heading" % (guide, title)


def test_every_adapter_credential_variable_has_a_keys_row():
    rules = policy(_ROOT)
    assert rules["credentials"], "models.credential_env names nothing -- zero items"
    assert rule_findings(rules, config_loader.KEYS) == []
    by_env = {k.env: k for k in config_loader.KEYS if k.env is not None}
    assert all(by_env[n].secret for n in rules["credentials"]), rules
    # Twin: drop one credential's row and that name alone is red.
    victim = rules["credentials"][0]
    fewer = [k for k in config_loader.KEYS if k.env != victim]
    reds = rule_findings(rules, fewer)
    assert [f.key for f in reds] == ["models.credential_env %s" % victim], reds
    # Twin: a secret variable in the base allowlist is red, naming it.
    wider = dict(rules, allowlist=sorted(rules["allowlist"] + [victim]))
    reds = rule_findings(wider, config_loader.KEYS)
    assert [f.key for f in reds] == ["child_env.names %s" % victim], reds


def test_a_secret_row_with_a_default_is_red():
    planted = _planted()
    victim = next(k for k in config_loader.KEYS if k.secret)
    keys = [
        k._replace(default=planted) if k is victim else k for k in config_loader.KEYS
    ]
    reds = rule_findings(policy(_ROOT), keys)
    assert [(f.file, f.key) for f in reds] == [(_LOADER, ".".join(victim.path))], reds
    assert planted not in "\n".join(format_finding(f) for f in reds)


# --- the judges on planted text ----------------------------------------------


def _planted(seed=7):
    """A value built at run time, so no committed literal looks like a key."""
    rng = random.Random(seed)
    return "".join(rng.choice(string.ascii_letters) for _ in range(32))


@pytest.mark.parametrize(
    "line",
    ["KEY=", 'KEY=""', "KEY=''", "export KEY=", "KEY = ", "  KEY=  ", "# KEY=x", ""],
)
def test_only_the_empty_value_is_a_placeholder_green(line):
    assert judge_dotenv(".env", line + "\nOTHER=value\n", {"KEY"}) == []


@pytest.mark.parametrize(
    "line",
    ["KEY=x", 'KEY="x"', "KEY='x'", "KEY=${OTHER}", "KEY=changeme", "export KEY=x"],
)
def test_only_the_empty_value_is_a_placeholder_red(line):
    reds = judge_dotenv(".env", "# head\n" + line + "\n", {"KEY"})
    assert [(f.file, f.line, f.key) for f in reds] == [(".env", 2, "KEY")], reds


@pytest.mark.parametrize(
    "text, line",
    [
        ("\ufeffKEY=x\n", 1),
        ("A=1\n\ufeff KEY=x\n", 2),
        ("A=1\rKEY=x\r", 2),
        ("A=1\r\n\r\nKEY=x\r\n", 3),
    ],
    ids=["bom", "zero-width-space-mid-file", "cr-lines", "crlf-lines"],
)
def test_what_a_dotenv_loader_reads_as_space_or_a_line_break_hides_no_key(text, line):
    """U+FEFF is whitespace to the dotenv loaders, though not to str.strip,
    and a bare CR ends a line for them as LF does."""
    reds = judge_dotenv(".env", text, {"KEY"})
    assert [(f.line, f.key) for f in reds] == [(line, "KEY")], reds


def test_a_planted_json_value_under_a_secret_name_is_red_at_any_depth():
    planted = _planted()
    name = "KEY"
    doc = {"a": {"b": [{"keep": 1, name: planted}]}}
    text = json.dumps(doc, indent=2)
    reds = judge_json("config/x.json", text, {name}, set())
    assert [(f.file, f.key) for f in reds] == [("config/x.json", "a.b.0." + name)]
    lines = text.split("\n")
    assert reds[0].line == 1 + next(
        i for i, ln in enumerate(lines) if ln.lstrip().startswith('"%s"' % name)
    )
    assert planted not in "\n".join(format_finding(f) for f in reds)
    for empty in ("", None):
        doc["a"]["b"][0][name] = empty
        assert judge_json("config/x.json", json.dumps(doc), {name}, set()) == []
    for other in (0, False, {"inner": ""}, ["x"]):
        doc["a"]["b"][0][name] = other
        assert len(judge_json("config/x.json", json.dumps(doc), {name}, set())) == 1
    # The models.credential_env shape: a list holding the name is no value.
    listing = json.dumps({"credential_env": {"adapter": [name]}})
    assert judge_json("config/x.json", listing, {name}, set()) == []
    # A key written twice is judged twice; json.loads would keep only the last.
    twice = '{"%s": "%s", "%s": ""}' % (name, planted, name)
    assert len(judge_json("config/x.json", twice, {name}, set())) == 1
    # A secret row's path is judged in its own file.
    nested = json.dumps({"db": {"password": planted}})
    reds = judge_json("config/project.json", nested, set(), {("db", "password")})
    assert [f.key for f in reds] == ["db.password"], reds
    broken = judge_json("config/x.json", '{"a": ', {name}, set())
    assert [f.key for f in broken] == ["(the file)"], broken


# --- the candidate set, in a repository and outside one ----------------------


def _git(repo, *argv):
    subprocess.run(
        ["git", *argv],
        cwd=str(repo),
        env=hermetic_git.git_env(repo.parent / "gitwork"),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A committed repository holding keel's config/project.json and
    .env.example and an ignore rule for local env files; the hermetic git
    environment is exported, because git_tree takes its environment from
    child_env, which copies GIT_CONFIG_* from here."""
    work = tmp_path / "gitwork"
    work.mkdir()
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    shutil.copy(str(_ROOT / "config" / "project.json"), str(proj / "config"))
    shutil.copy(str(_ROOT / ".env.example"), str(proj))
    (proj / ".gitignore").write_text(".env\n.env.local\n", encoding="utf-8")
    _git(proj, "init", "-q")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "init")
    return proj


def _keys_of(found):
    return [(f.file, f.line, f.key.split(".")[-1]) for f in found]


# Two secret variable names from the KEYS rows the gate reads, never typed
# here, so renaming a credential's variable changes the test with it.
_SECRET_NAMES = sorted(secret_names(config_loader.KEYS)[0])
_ONE, _OTHER = _SECRET_NAMES[0], _SECRET_NAMES[-1]


def test_a_planted_dotenv_value_is_red_naming_file_and_key_never_the_value(project):
    assert findings(project) == []
    planted = _planted(11)
    (project / ".env.production").write_text(
        "%s=%s\n" % (_ONE, planted), encoding="utf-8"
    )
    _git(project, "add", "-f", ".env.production")
    found = findings(project)
    assert _keys_of(found) == [(".env.production", 1, _ONE)], found
    text = "\n".join(format_finding(f) for f in found)
    assert planted not in text and ".env.production:1: %s" % _ONE in text


def test_an_ignored_file_is_not_judged_and_a_force_added_one_is(project):
    planted = _planted(13)
    (project / ".env").write_text("%s=%s\n" % (_OTHER, planted), encoding="utf-8")
    assert findings(project) == []
    _git(project, "add", "-f", ".env")
    assert _keys_of(findings(project)) == [(".env", 1, _OTHER)]
    (project / ".env.prod").write_text("%s=%s\n" % (_ONE, planted), encoding="utf-8")
    assert (".env.prod", 1, _ONE) in _keys_of(findings(project))


def test_the_index_copy_is_judged_when_the_work_tree_is_blanked(project):
    """A value staged, or committed, and then blanked on disk is still what
    the next commit, or HEAD, carries."""
    planted = _planted(17)
    env_file = project / ".env.production"
    env_file.write_text("%s=%s\n" % (_ONE, planted), encoding="utf-8")
    _git(project, "add", "-f", ".env.production")
    env_file.write_text("%s=\n" % _ONE, encoding="utf-8")
    assert _keys_of(findings(project)) == [(".env.production", 1, _ONE)]
    env_file.unlink()
    assert _keys_of(findings(project)) == [(".env.production", 1, _ONE)]
    _git(project, "rm", "-q", "--cached", ".env.production")
    assert findings(project) == []


def test_a_byte_order_mark_hides_no_value_on_disk_or_in_the_index(project):
    """Windows editors start a file with U+FEFF, which dotenv loaders skip as
    whitespace; the first key after it is still that key, and a JSON file
    that starts with one is judged, not merely refused."""
    planted = _planted(23)
    env_file = project / ".env.production"
    env_file.write_bytes(
        b"\xef\xbb\xbf" + ("%s=%s\n" % (_ONE, planted)).encode("utf-8")
    )
    _git(project, "add", "-f", ".env.production")
    assert _keys_of(findings(project)) == [(".env.production", 1, _ONE)]
    env_file.unlink()
    assert _keys_of(findings(project)) == [(".env.production", 1, _ONE)]
    _git(project, "rm", "-q", "--cached", ".env.production")
    (project / "local.json").write_bytes(
        b"\xef\xbb\xbf" + json.dumps({_ONE: planted}).encode("utf-8")
    )
    assert _keys_of(findings(project)) == [("local.json", 1, _ONE)]


def test_a_committed_symlink_is_judged_through_its_target_only(project):
    """git stores a symlink as its target's path, which is no file's text: the
    link is not judged, and the file it names is, under its own path."""
    os.symlink(os.path.join("config", "project.json"), str(project / "alias.json"))
    os.symlink(".env.example", str(project / ".env.alias"))
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "links")
    assert findings(project) == []
    judged = judge(project)[1]
    assert "alias.json" in judged["json"] and "config/project.json" in judged["json"]
    # The target still carries its own value, under its own path.
    planted = _planted(29)
    with open(str(project / ".env.example"), "a", encoding="utf-8") as fh:
        fh.write("%s=%s\n" % (_ONE, planted))
    assert [f.file for f in findings(project)] == [".env.example"]


def test_judging_nothing_is_a_failure(project):
    no_secret = [k._replace(secret=False) for k in config_loader.KEYS]
    with pytest.raises(SecretGateError, match="zero secret names"):
        judge(project, no_secret)
    for rel in (".env.example", "config/project.json"):
        _git(project, "rm", "-q", "--cached", rel)
    (project / ".gitignore").write_text(".env.example\nconfig/\n", encoding="utf-8")
    with pytest.raises(SecretGateError, match="zero files judged"):
        judge(project)


def test_outside_a_repository_the_walk_is_judged(project, tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    shutil.copytree(str(project / "config"), str(lone / "config"))
    planted = _planted(19)
    (lone / ".gitignore").write_text(".env.local\n", encoding="utf-8")
    (lone / ".env.local").write_text("%s=%s\n" % (_ONE, planted), encoding="utf-8")
    with pytest.raises(git_tree.NoGitError):
        git_tree.candidate_files(str(lone))
    assert _keys_of(findings(lone)) == [(".env.local", 1, _ONE)]
    # A repository git cannot read is unknown, never "no repository".
    (project / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")
    with pytest.raises(git_tree.GitFailedError):
        findings(project)


def test_a_policy_with_no_pattern_is_refused(project):
    manifest = json.loads((project / "config" / "project.json").read_text("utf-8"))
    broken = copy.deepcopy(manifest)
    broken["secrets"]["dotenv_files"] = []
    (project / "config" / "project.json").write_text(json.dumps(broken), "utf-8")
    with pytest.raises(SecretGateError, match="secrets.dotenv_files"):
        judge(project)
