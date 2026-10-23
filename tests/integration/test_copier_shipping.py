"""
title: Integration — every template file ships to a generated project or is left out of it with a reason
kind: tests
layer: n/a
summary: The template-shipping gate. Every file copier can see in keel's checkout (tracked, or untracked and not ignored) either renders into a generated project — at its own path, or through its `.jinja` twin — or is left out by a copier.yml `_exclude` entry, judged with copier's own path matcher under each answer set test_reference_drift's answer_sets enumerates (free-text questions at their defaults; a multiselect with no choice, each choice alone and every choice); each `_exclude` entry has a row in the upgrade guide's exclusion table whose Why cell is not blank, each row of that table names an `_exclude` entry (a row that names none gives a reason for a path that in fact arrives, or for one another entry leaves out), and each entry other than copier's own re-listed defaults leaves out at least one file under some answer set or is spelled by a `.gitignore` line (a leading or trailing `/` aside; a glob that only covers it does not count), so a stale or misspelled entry fails. Each entry judged alone leaves out exactly what copier's matcher over all of them does, so no entry is credited with a file that ships. Only copier itself may be absent: once it imports, a private module it no longer has is a collection error, not a skip. tests/integration/test_copier_generation.py holds the model to a real copier render. Each rule has a fault-injection twin that plants one fault and asserts exactly one more finding than the tree had before. Not a writer: it reads the tree and writes nothing.
"""

import functools
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_ROOT / "tests"))

import check_structure as cs  # noqa: E402
from child_env import build_child_env  # noqa: E402
from test_doc_drift import (  # noqa: E402
    _EXCLUSION_TABLE,
    _JINJA_TAG,
    DocDriftConfigError,
    entry_policy,
    load_manifest,
)
from test_reference_drift import _jinja, answer_sets, copier_questions  # noqa: E402

# A meta-test of copier.yml: copier.yml's own `tests/integration/test_copier_*.py`
# prune keeps it out of a generated project, and the skip covers a project that
# was generated before that prune existed.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]

copier = optional_deps.importorskip("copier", extra="template")
yaml = optional_deps.importorskip("yaml", extra="template")
pathspec = optional_deps.importorskip("pathspec", extra="template")
# copier's own matcher and defaults, not a restatement of them: copier picks the
# pathspec pattern style by the pathspec version it finds, and a custom
# `_exclude` replaces DEFAULT_EXCLUDE, which is why copier.yml re-lists it.
# Only copier itself may be absent; once it imports, these private modules are
# loaded with a plain import, so a copier release that moves or renames one is
# a collection error, not a skip that leaves the gate unrun where `template` is
# not declared required.
_pathspec_pattern = importlib.import_module("copier._main")._pathspec_pattern
DEFAULT_EXCLUDE = importlib.import_module("copier._template").DEFAULT_EXCLUDE

_WHY_COLUMN = "why"
_PATH_COLUMN = _EXCLUSION_TABLE[0].lower()


def copier_rules(root):
    """{"exclude", "suffix", "answers_file"} read from *root*'s copier.yml:
    the raw `_exclude` entries in file order, `_templates_suffix` and
    `_answers_file`. A missing or mistyped key raises naming it."""
    cfg = yaml.safe_load((Path(root) / "copier.yml").read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise DocDriftConfigError("copier.yml: top level is not a mapping")
    excludes = cfg.get("_exclude")
    if (
        not isinstance(excludes, list)
        or not excludes
        or not all(isinstance(e, str) and e.strip() for e in excludes)
    ):
        raise DocDriftConfigError(
            "copier.yml: `_exclude` must be a non-empty list of non-blank strings"
        )
    rules = {"exclude": list(excludes)}
    for key, name in (
        ("_templates_suffix", "suffix"),
        ("_answers_file", "answers_file"),
    ):
        value = cfg.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DocDriftConfigError("copier.yml: `%s` is missing or blank" % key)
        rules[name] = value
    return rules


def visible_files(root):
    """Every path copier can see in *root*: the tracked files and the untracked
    ones git does not ignore. copier clones a git template, and stages a dirty
    one's working tree into its clone with `git add -A`, so an ignored file
    never reaches it whatever `_exclude` says."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(root),
        env=build_child_env(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({p for p in out.split("\0") if p})


def destination(path, suffix):
    """The path *path* renders to: its suffix dropped for a template file, the
    same path otherwise. A plain file with a template twin is not copied, but
    the twin renders to its path, so the plain file arrives either way."""
    return path.removesuffix(suffix)


def _matcher(lines):
    """copier's matcher over *lines*, as `Worker._path_matcher` builds it."""
    return pathspec.PathSpec.from_lines(_pathspec_pattern, lines).match_file


@functools.lru_cache(maxsize=None)
def _compiled(entry):
    # Compiled once per entry: parsing it again for each of about a hundred
    # answer sets costs about 1.5 s a judgement (measured).
    return _jinja().from_string(entry)


def rendered_lines(entry, answers):
    """The pattern lines *entry* gives under *answers*: copier renders each
    entry with the answers and splits the result on line breaks; an entry whose
    condition is false renders to nothing and so excludes nothing."""
    text = _compiled(entry).render(**answers)
    return [line for line in text.splitlines() if line.strip()]


def shipped_paths(files, rules, answers):
    """The destination paths a render of *files* under *answers* holds: each
    file's destination, unless copier's matcher over every `_exclude` entry
    rendered with *answers* matches it."""
    lines = [ln for e in rules["exclude"] for ln in rendered_lines(e, answers)]
    excluded = _matcher(lines)
    dests = {destination(f, rules["suffix"]) for f in files}
    return {d for d in dests if not excluded(d)}


def left_out_by(files, rules, answers, memo=None):
    """{entry: the destination paths it leaves out under *answers*}, each
    entry judged alone with copier's matcher. *memo* maps a rendered pattern
    tuple to what it matches, shared across calls over the same *files*."""
    memo = {} if memo is None else memo
    dests = sorted({destination(f, rules["suffix"]) for f in files})
    found = {}
    for entry in rules["exclude"]:
        lines = tuple(rendered_lines(entry, answers))
        if lines not in memo:
            match = _matcher(lines) if lines else None
            memo[lines] = {d for d in dests if match and match(d)}
        found[entry] = memo[lines]
    return found


def entry_coverage(files, rules, answer_sets_):
    """{entry: the destination paths it leaves out under some answer set}."""
    memo = {}
    coverage = {entry: set() for entry in rules["exclude"]}
    for answers in answer_sets_:
        for entry, paths in left_out_by(files, rules, answers, memo).items():
            coverage[entry] |= paths
    return coverage


def _bare(path):
    """*path* with its leading and trailing slashes dropped: `/tmp/`, `/tmp`
    and `tmp/` all name `tmp`."""
    return path.strip().strip("/")


def gitignore_declared(root, entries):
    """The entries a `.gitignore` line in *root* names literally, so the tree is
    declared to produce that path and keep it out of git. An exclusion there
    guards a template copied without git, where copier sees every file on disk.
    A line that only matches the entry, a glob or a parent directory, declares
    nothing: it would also pass a stale or misspelled entry. A leading slash
    (anchored at the root) or a trailing one (a directory) is allowed on either
    side; comments, blank lines and negations name no path."""
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    named = {
        _bare(ln)
        for ln in lines
        if ln.strip() and not ln.lstrip().startswith(("#", "!"))
    }
    return {e for e in entries if _bare(_stripped(e)) in named}


def exclusion_rows(guide, text):
    """[(path named in the Path cell, Why cell)] of the guide's exclusion
    table; a guide without the table, or without a Why column, raises."""
    table = cs._pipe_table(text, _EXCLUSION_TABLE + (_WHY_COLUMN,))
    if table is None:
        raise DocDriftConfigError(
            "%s: no table with the columns %s"
            % (guide, ", ".join(_EXCLUSION_TABLE + ("Why",)))
        )
    header, rows = table
    path_col, why_col = header.index(_PATH_COLUMN), header.index(_WHY_COLUMN)
    found = []
    for row in rows:
        named = cs._BACKTICKED.findall(row[path_col]) if path_col < len(row) else []
        why = row[why_col] if why_col < len(row) else ""
        found.extend((name.strip(), why.strip()) for name in named)
    return found


def _stripped(entry):
    """The path an entry names, its jinja condition dropped: what the guide's
    Path cell writes for it."""
    return _JINJA_TAG.sub("", entry).strip()


def shipping_findings(guide, rows, rules, coverage, declared, defaults):
    """Every finding of the gate: an entry with no row, or with a row whose
    Why is blank; a row naming no entry, whose path either arrives or is left
    out by another entry; an entry, not one of copier's *defaults*,
    that leaves out no file under any answer set and names no path in
    *declared*. *rows* are (path, why) pairs, *coverage* maps each raw entry
    to what it leaves out."""
    findings = []
    by_path = {}
    for path, why in rows:
        by_path.setdefault(path, []).append(why)
    named = {_stripped(e): e for e in rules["exclude"]}
    for path, raw in named.items():
        whys = by_path.get(path)
        if whys is None:
            findings.append(
                "copier.yml: `_exclude` entry %r has no row in %s, so nothing "
                "says why a generated project goes without it" % (raw, guide)
            )
        elif not all(whys):
            findings.append(
                "%s: the row for `%s` gives no reason in its Why cell" % (guide, path)
            )
    left_out = {d: raw for raw, covered in coverage.items() for d in covered}
    for path in sorted(set(by_path) - set(named)):
        if path in left_out:
            findings.append(
                "%s: the row for `%s` names no copier.yml `_exclude` entry; entry "
                "%r leaves it out, so its reason belongs on that entry's row"
                % (guide, path, left_out[path])
            )
        else:
            findings.append(
                "%s: the row for `%s` names no copier.yml `_exclude` entry and no "
                "entry leaves it out, so it in fact arrives" % (guide, path)
            )
    for raw, covered in coverage.items():
        if covered or raw in defaults or raw in declared:
            continue
        findings.append(
            "copier.yml: `_exclude` entry %r leaves out no file under any answer "
            "set and no .gitignore line spells its path: drop it, or fix the path"
            % (raw,)
        )
    return findings


# --- fixtures -------------------------------------------------------------


@pytest.fixture(scope="module")
def guide():
    return entry_policy(load_manifest(_ROOT))["upgrade_guide"]


@pytest.fixture(scope="module")
def guide_text(guide):
    return (_ROOT / guide).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rules():
    return copier_rules(_ROOT)


@pytest.fixture(scope="module")
def answers():
    found = answer_sets(copier_questions(_ROOT))
    assert found, "copier.yml allows no answer set -- zero items"
    return found


@pytest.fixture(scope="module")
def files():
    found = visible_files(_ROOT)
    assert found, "git lists no file copier can see -- zero items"
    return found


def _judge(guide, text, rules, files, answers):
    """The gate's findings for *text* as the guide and *rules* as copier.yml."""
    rows = exclusion_rows(guide, text)
    assert rows, "%s: the exclusion table has no row -- zero items" % guide
    coverage = entry_coverage(files, rules, answers)
    declared = gitignore_declared(_ROOT, rules["exclude"])
    return shipping_findings(guide, rows, rules, coverage, declared, DEFAULT_EXCLUDE)


def _one_more(before, after, phrase):
    """True when *after* is *before* plus exactly one finding carrying *phrase*,
    so a fault test judges its own plant and not the tree's state."""
    added = [f for f in after if f not in before]
    return len(after) == len(before) + 1 and len(added) == 1 and phrase in added[0]


def _replace_row(text, path, new_row):
    """*text* with the exclusion-table row whose Path cell is `path` replaced
    by *new_row* (None drops it); the row must exist exactly once."""
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith("| `%s` |" % path)]
    assert len(hits) == 1, "%d rows for `%s`" % (len(hits), path)
    if new_row is None:
        del lines[hits[0]]
    else:
        lines[hits[0]] = new_row
    return "\n".join(lines)


# --- the gate -------------------------------------------------------------


def test_every_left_out_file_has_a_reason_and_every_reason_leaves_one_out(
    guide, guide_text, rules, files, answers
):
    findings = _judge(guide, guide_text, rules, files, answers)
    assert not findings, "\n".join(findings)


def test_copier_yml_relists_copier_defaults_which_need_only_a_row(
    guide, guide_text, rules, files, answers
):
    """A custom `_exclude` replaces copier's defaults, so copier.yml re-lists
    each; most leave out nothing in a clean clone, and that is no finding."""
    missing = [d for d in DEFAULT_EXCLUDE if d not in rules["exclude"]]
    assert not missing, "copier.yml `_exclude` drops copier defaults %s" % missing
    findings = _judge(guide, guide_text, rules, files, answers)
    about_defaults = [
        f for f in findings if any("entry %r " % d in f for d in DEFAULT_EXCLUDE)
    ]
    assert not about_defaults, "\n".join(about_defaults)


def test_each_entry_judged_alone_leaves_out_what_copier_leaves_out(
    rules, files, answers
):
    """The gate credits each entry with what it leaves out judged alone, while
    copier judges every entry together, last match winning. The two agree only
    while no later entry takes a path back (a `!` line): otherwise an entry
    would be credited with a file that in fact ships, and a stale entry could
    pass on that credit."""
    dests = {destination(f, rules["suffix"]) for f in files}
    memo = {}
    for a in answers:
        alone = set().union(*left_out_by(files, rules, a, memo).values())
        together = dests - shipped_paths(files, rules, a)
        assert alone == together, (
            "under %r, credited but shipped: %s; left out but credited to none: %s"
            % (a, sorted(alone - together), sorted(together - alone))
        )


# --- a copier that moves its private modules ------------------------------

# Imported by the pytest a test starts, before collection: copier imports, then
# its `_main` module goes missing, as a copier release that renames it would.
_MOVED_MAIN_PLUGIN = """import sys

import copier  # noqa: F401

sys.modules["copier._main"] = None
"""


def _collect(path, plugin_dir=None):
    """(exit status, output) of collecting *path* with no surface declared
    required, through the plugin in *plugin_dir* when one is given."""
    extra = {"KEEL_REQUIRED_EXTRAS": ""}
    args = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--co", "-q"]
    if plugin_dir is not None:
        extra["PYTHONPATH"] = str(plugin_dir)
        args += ["-p", "moved_copier_main"]
    result = subprocess.run(
        args + [str(path)],
        cwd=str(_ROOT),
        env=build_child_env(extra=extra),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return result.returncode, result.stdout + result.stderr


def test_a_copier_that_moves_a_private_module_fails_and_spares_generation(tmp_path):
    """Once copier imports, a private module it no longer has is an error, not
    a skip, even where `template` is not declared required; and the generation
    suite, which reuses this gate's model, still collects every test."""
    (tmp_path / "moved_copier_main.py").write_text(_MOVED_MAIN_PLUGIN, encoding="utf-8")
    here = Path(__file__).resolve()
    status, out = _collect(here, tmp_path)
    assert status != 0 and "copier._main" in out and "skipped" not in out, out
    generation = here.with_name("test_copier_generation.py")
    _, clean = _collect(generation)
    _, moved = _collect(generation, tmp_path)
    count = re.search(r"^(\d+) tests? collected", clean, re.MULTILINE)
    assert count and int(count.group(1)) > 0, clean
    assert count.group(0) in moved, moved


# --- fault injection: one planted fault, exactly one finding --------------


def test_a_blank_reason_is_a_finding(guide, guide_text, rules, files, answers):
    planted = _replace_row(
        guide_text, "scripts/canary.py", "| `scripts/canary.py` | never |  |"
    )
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, planted, rules, files, answers)
    assert _one_more(before, findings, "gives no reason"), findings


def test_an_entry_with_no_row_is_a_finding(guide, guide_text, rules, files, answers):
    planted = _replace_row(guide_text, "scripts/canary.py", None)
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, planted, rules, files, answers)
    assert _one_more(before, findings, "has no row"), findings


def test_a_reason_for_a_shipped_file_is_a_finding(
    guide, guide_text, rules, files, answers
):
    shipped = "docs/guides/python-style.md"
    assert shipped in shipped_paths(files, rules, answers[0])
    planted = _replace_row(
        guide_text,
        "scripts/canary.py",
        "| `scripts/canary.py` | never | its reason |\n| `%s` | never | planted |"
        % shipped,
    )
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, planted, rules, files, answers)
    assert _one_more(before, findings, "in fact arrives"), findings


def test_a_row_for_a_path_another_entry_leaves_out_is_a_finding(
    guide, guide_text, rules, files, answers
):
    """The glob row carries the reason for every meta-test it leaves out; a
    row of its own for one of them names no entry and is a finding."""
    meta = "tests/integration/test_copier_update.py"
    assert meta in files
    planted = _replace_row(
        guide_text,
        "scripts/canary.py",
        "| `scripts/canary.py` | never | its reason |\n| `%s` | never | planted |"
        % meta,
    )
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, planted, rules, files, answers)
    assert _one_more(before, findings, "belongs on that entry's row"), findings


def test_an_entry_that_leaves_out_no_file_is_a_finding(
    guide, guide_text, rules, files, answers
):
    stale = "scripts/no_such_check.py"
    planted_rules = dict(rules, exclude=rules["exclude"] + [stale])
    planted = _replace_row(
        guide_text,
        "scripts/canary.py",
        "| `scripts/canary.py` | never | its reason |\n| `%s` | never | planted |"
        % stale,
    )
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, planted, planted_rules, files, answers)
    assert _one_more(before, findings, "leaves out no file"), findings


def test_an_entry_for_a_path_gitignore_declares_is_no_finding(
    guide, guide_text, rules, files, answers
):
    """A generated view git ignores never reaches copier from a clone, but an
    entry for it guards a copy made without git, so it is no finding."""
    view = "wiki/INDEX.md"
    assert view not in files
    planted_rules = dict(rules, exclude=rules["exclude"] + [view])
    planted = _replace_row(
        guide_text,
        "scripts/canary.py",
        "| `scripts/canary.py` | never | its reason |\n| `%s` | never | planted |"
        % view,
    )
    before = _judge(guide, guide_text, rules, files, answers)
    assert _judge(guide, planted, planted_rules, files, answers) == before


def test_a_gitignore_line_declares_its_path_with_or_without_slashes(tmp_path):
    """A line declares the entry it spells, a leading or trailing slash aside
    on either side; a glob, a parent directory, a comment or a negation that
    spells it declares nothing."""
    (tmp_path / ".gitignore").write_text(
        "/tmp/\nwiki/.runtime/\n/dist\nconfig/*.local.*\nbuild\n"
        "# notes/x.md\n!keep.txt\n",
        encoding="utf-8",
    )
    entries = [
        "/tmp",
        "tmp/",
        "wiki/.runtime",
        "dist/",
        "config/old.local.json",
        "build/x",
        "notes/x.md",
        "# notes/x.md",
        "keep.txt",
        "!keep.txt",
    ]
    assert gitignore_declared(tmp_path, entries) == {
        "/tmp",
        "tmp/",
        "wiki/.runtime",
        "dist/",
    }


@pytest.mark.parametrize(
    "stale", ["config/old.local.json", "build/x", "node_modules/zzz"]
)
def test_an_entry_a_gitignore_glob_covers_is_still_a_finding(
    stale, guide, guide_text, rules, files, answers
):
    """git would ignore each of these paths through a glob or a directory line,
    but no `.gitignore` line names it, so the entry is stale or misspelled and
    a finding."""
    assert stale not in files
    planted_rules = dict(rules, exclude=rules["exclude"] + [stale])
    planted = _replace_row(
        guide_text,
        "scripts/canary.py",
        "| `scripts/canary.py` | never | its reason |\n| `%s` | never | planted |"
        % stale,
    )
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, planted, planted_rules, files, answers)
    assert _one_more(before, findings, "leaves out no file"), findings


def test_a_new_file_ships_unless_an_entry_with_a_reason_leaves_it_out(
    guide, guide_text, rules, files, answers
):
    """A file a slice adds ships by default; an entry that leaves it out with
    no row is a finding, so it cannot quietly go missing downstream."""
    new = "scripts/check_new_thing.py"
    planted_files = sorted(files + [new])
    assert new in shipped_paths(planted_files, rules, answers[0])
    planted_rules = dict(rules, exclude=rules["exclude"] + [new])
    assert new not in shipped_paths(planted_files, planted_rules, answers[0])
    before = _judge(guide, guide_text, rules, files, answers)
    findings = _judge(guide, guide_text, planted_rules, planted_files, answers)
    assert _one_more(before, findings, "has no row"), findings


def test_a_conditional_entry_covers_what_its_answer_leaves_out(rules, files, answers):
    """An answer-driven entry leaves its path out only under the answers its
    condition names, through copier's own rendering of the entry."""
    pruned = [a for a in answers if a.get("frontend_stack") == "none"]
    kept = [a for a in answers if a.get("frontend_stack") != "none"]
    assert pruned and kept
    probe = "src/frontend/README.md"
    assert probe in files
    assert all(probe not in shipped_paths(files, rules, a) for a in pruned)
    assert all(probe in shipped_paths(files, rules, a) for a in kept)


def test_the_scratch_entry_leaves_out_the_root_tmp_and_no_nested_one(
    rules, files, answers
):
    """The scratch entry is anchored at the root, as `.gitignore`'s `/tmp/` is:
    a `tmp` directory deeper in the tree is project content and ships."""
    root_scratch = "tmp/notes.md"
    nested = ["src/backend/tmp/x.py", "tests/fixtures/tmp/case.json"]
    planted = sorted(files + [root_scratch] + nested)
    for a in answers:
        shipped = shipped_paths(planted, rules, a)
        assert root_scratch not in shipped, a
        assert all(n in shipped for n in nested), (a, sorted(set(nested) - shipped))
