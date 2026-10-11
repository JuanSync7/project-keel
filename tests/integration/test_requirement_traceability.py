"""
title: Integration — requirement traceability (every requirement is named by a test or is a documented gap)
kind: tests
layer: n/a
summary: The gate test judges this tree in process with scripts/traceability.py under the running session's collection rule: every requirement a `kind: spec` document under config/project.json `traceability.specs_root` defines is covered or a `traceability.gaps` row, with no finding, and zero requirements passes only under a `traceability.no_requirements` reason. Each planted fault in a scratch copy of the project adds exactly its findings: a requirement no test names, numbered criteria named only by the bare id, one criterion of three unnamed, a marker naming an undefined id or an unlisted prefix, a marker on a helper, on a test a later definition replaces or in a class pytest refuses, marked files below a directory pytest skips, a stale id through an imported `mark`, an unreadable marker, a gap for an undefined, covered or malformed id, an empty specs root, and a stale no-requirements reason. scripts/trace_requirements.py run as a command writes one schema-valid matrix and nothing else, a second run changes no byte, and its exit code is 0, 1 or 2 by the kind of red; a run that stops leaves a red matrix; a matrix path the filesystem will not write is exit 2 with one line and no temporary file, and `--help` describes the command by its header title. A child `pytest --collect-only` says which collected tests carry which id, and that equals what the reader found, in this tree and after each fault of collection; the comparison is shown to fail on a marker through an alias, a conftest `collect_ignore` and an inherited constructor, which source cannot show. A matrix path, specs root or spec file reached through a symlink is refused before anything outside the project is read or written, with and without git; an absolute, `..` or un-ignored matrix path and a broken repository are refused. The marker is registered in the parsed pytest ini and the command is reachable from `make verify`.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # before 3.11; pytest itself depends on tomli there
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import pytest_markers  # noqa: E402
import traceability as tr  # noqa: E402

import hermetic_git  # noqa: E402
import optional_deps  # noqa: E402

pytestmark = pytest.mark.integration

_CLI = "trace_requirements.py"
# What the command imports when it runs in a project.
_SCRIPTS = (
    _CLI,
    "traceability.py",
    "pytest_markers.py",
    "git_tree.py",
    "child_env.py",
    "check_structure.py",
)
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")
_GAPS_WHERE = "%s %s" % (tr.MANIFEST, tr.GAPS_KEY)
_EMPTY_WHERE = "%s %s" % (tr.MANIFEST, tr.EMPTY_KEY)


def _manifest(root):
    return json.loads((Path(root) / tr.MANIFEST).read_text(encoding="utf-8"))


def _policy(root):
    return tr.load_policy(_manifest(root))


@pytest.fixture(scope="module")
def rule(request):
    return pytest_markers.full_rule(request.config)


# ------------------------------------------------------------- the gate test


def test_every_requirement_is_covered_or_a_documented_gap(rule):
    policy = _policy(_ROOT)
    catalogue, judgement = tr.trace_tree(str(_ROOT), policy, rule)
    assert judgement.findings == [], "\n".join(
        "%(kind)s: %(id)s (%(where)s)" % f for f in judgement.findings
    )
    assert judgement.result == "pass"
    if policy.no_requirements is None:
        # A pass over zero requirements would be a pass over nothing.
        assert judgement.units, "no requirement was judged"
        assert judgement.state == "traced"
        assert sorted(u.id for u in judgement.units) == sorted(catalogue.units())
        assert all(u.verdict in ("covered", "gap") for u in judgement.units)
        assert sum(judgement.counts.values()) == len(judgement.units)
    else:
        assert judgement.state == "no-requirements" and not judgement.units


# -------------------------------------------------------------- the scratch


def _git(repo, env, *argv):
    out = subprocess.run(
        ("git",) + argv,
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert out.returncode == 0, out.stdout
    return out.stdout


def build_scratch(base, git=True):
    """A scratch copy of what the gate reads in this project: the config, the
    specs, every test file that holds the marker, the pytest ini and the
    command with what it imports. (repo, env); committed when *git*."""
    policy = _policy(_ROOT)
    work = base / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    # The command's own bytecode would show as a change the run made.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    repo = base / "repo"
    repo.mkdir()
    for tree in ("config", policy.specs_root):
        shutil.copytree(str(_ROOT / tree), str(repo / tree), ignore=_IGNORE)
    marked = 0
    for path in sorted((_ROOT / policy.tests_root).rglob("*.py")):
        rel = path.relative_to(_ROOT)
        if rel == Path(__file__).resolve().relative_to(_ROOT):
            continue
        if ".mark.%s(" % policy.marker in path.read_text(encoding="utf-8"):
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(path), str(repo / rel))
            marked += 1
    assert marked, "no test file holds the %s marker" % policy.marker
    (repo / "scripts").mkdir()
    for name in _SCRIPTS:
        shutil.copy(str(_ROOT / "scripts" / name), str(repo / "scripts" / name))
    for name in ("pyproject.toml", ".gitignore"):
        shutil.copy(str(_ROOT / name), str(repo / name))
    if git:
        _git(repo, env, "init", "-q")
        _git(repo, env, "add", "-A")
        _git(repo, env, "commit", "-q", "-m", "init")
    return repo, env


def run_cli(repo, env):
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / _CLI), "--root", str(repo)],
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def matrix_path(repo):
    return repo / _policy(_ROOT).matrix_path


def read_matrix(repo):
    return json.loads(matrix_path(repo).read_text(encoding="utf-8"))


def _set(repo, **changes):
    path = repo / tr.MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[tr.BLOCK].update(changes)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _specs(repo):
    """The spec documents of the scratch that define a requirement."""
    policy = _policy(repo)
    found = sorted(
        {
            repo / req.where.rsplit(":", 1)[0]
            for req in tr.read_specs(str(repo), policy).requirements.values()
        }
    )
    assert found
    return found


def _test_file(repo):
    """One scratch test file that holds the marker."""
    policy = _policy(repo)
    for path in sorted((repo / policy.tests_root).rglob("*.py")):
        if ".mark.%s(" % policy.marker in path.read_text(encoding="utf-8"):
            return path
    raise AssertionError("no marked test file in the scratch")


def _append(path, text):
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _units(repo, rule):
    """(units with criteria, units without) the scratch defines, as judged."""
    _, judged = tr.trace_tree(str(repo), _policy(repo), rule)
    numbered = [u for u in judged.units if u.criterion is not None]
    plain = [u for u in judged.units if u.criterion is None]
    assert numbered and plain, "the shipped example needs both kinds of unit"
    return numbered, plain


def _fresh_id(repo, criterion=None):
    """An id the registry accepts and no spec defines."""
    policy = _policy(repo)
    row = next(
        p for p in policy.prefixes if p.family == "requirement" and p.source == "self"
    )
    defined = tr.read_specs(str(repo), policy).requirements
    for n in range(10**row.digits - 1, 0, -1):
        req = "%s%0*d" % (row.prefix, row.digits, n)
        if req not in defined:
            return str(tr.TraceId(req, criterion))
    raise AssertionError("every id of %s is defined" % row.prefix)


# Each fault edits the scratch and returns the findings it must add, as
# (kind, id) pairs. The ids come from the scratch, never from a literal.


def _requirement_no_test_names(repo, rule):
    new = _fresh_id(repo)
    _append(_specs(repo)[0], "\n## %s A requirement nobody tests\n" % new)
    return [("uncovered", new)]


def _criteria_named_only_by_the_bare_id(repo, rule):
    numbered, _ = _units(repo, rule)
    req = numbered[0].req
    mine = [u for u in numbered if u.req == req]
    marker = _policy(repo).marker
    for path in sorted((repo / _policy(repo).tests_root).rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for unit in mine:
            text = text.replace(
                '%s("%s")' % (marker, unit.id), '%s("%s")' % (marker, req)
            )
        path.write_text(text, encoding="utf-8")
    return [("uncovered", u.id) for u in mine]


def _one_criterion_of_three_unnamed(repo, rule):
    numbered, _ = _units(repo, rule)
    req = numbered[0].req
    mine = sorted(u.criterion for u in numbered if u.req == req)
    spec = _specs(repo)[0]
    lines = spec.read_text(encoding="utf-8").split("\n")
    last = max(i for i, line in enumerate(lines) if tr.parse_criterion_line(line))
    added = []
    while len(mine) + len(added) < 3 or not added:
        number = max(mine + added) + 1
        added.append(number)
    assert len(added) == 1, "the shipped example has two criteria on one requirement"
    lines.insert(last + 1, "- AC-%d: a third criterion no test names." % added[0])
    spec.write_text("\n".join(lines), encoding="utf-8")
    return [("uncovered", str(tr.TraceId(req, added[0])))]


def _marker(repo, ids, name="test_planted"):
    marker = _policy(repo).marker
    _append(
        _test_file(repo),
        "\n\n@pytest.mark.%s(%s)\ndef %s():\n    pass\n" % (marker, ids, name),
    )


def _marker_names_an_undefined_id(repo, rule):
    new = _fresh_id(repo)
    _marker(repo, '"%s"' % new)
    return [("marker-undefined-id", new)]


def _marker_names_an_undefined_criterion(repo, rule):
    _, plain = _units(repo, rule)
    new = str(tr.TraceId(plain[0].req, 1))
    _marker(repo, '"%s"' % new)
    return [("marker-undefined-id", new)]


def _marker_names_an_unlisted_prefix(repo, rule):
    _marker(repo, '"ZZUNLISTED-0001"')
    return [("marker-malformed-id", "ZZUNLISTED-0001")]


def _marker_on_a_helper(repo, rule):
    _, plain = _units(repo, rule)
    _marker(repo, '"%s"' % plain[0].id, name="helper_not_collected")
    return [("marker-unattached", plain[0].id)]


def _marker_on_a_test_a_later_definition_replaces(repo, rule):
    _, plain = _units(repo, rule)
    _marker(repo, '"%s"' % plain[0].id)
    _append(_test_file(repo), "\n\ndef test_planted():\n    pass\n")
    return [("marker-unattached", plain[0].id)]


def _marked_method(repo, rule, class_body):
    """Plant a class pytest's name rule matches, holding one marked test
    method under *class_body*; the finding for a marker nothing collects."""
    _, plain = _units(repo, rule)
    _append(
        _test_file(repo),
        "\n\nclass TestPlanted:\n%s\n    @pytest.mark.%s(%s)\n"
        "    def test_planted(self):\n        pass\n"
        % (class_body, _policy(repo).marker, json.dumps(plain[0].id)),
    )
    return [("marker-unattached", plain[0].id)]


def _marker_in_a_class_with_a_constructor(repo, rule):
    return _marked_method(repo, rule, "    def __init__(self):\n        pass\n")


def _marker_in_a_class_switched_off(repo, rule):
    return _marked_method(repo, rule, "    __test__ = False\n")


def _skipped_directory(rule):
    """A directory name pytest's `norecursedirs` names outright."""
    plain = [p for p in rule[3] if p.isidentifier()]
    assert plain, "norecursedirs names no plain directory: %r" % (rule[3],)
    return plain[0]


def _marked_files_below_a_directory_pytest_skips(repo, rule):
    numbered, plain = _units(repo, rule)
    policy = _policy(repo)
    hidden = repo / policy.tests_root / _skipped_directory(rule)
    hidden.mkdir()
    moved = 0
    for path in sorted((repo / policy.tests_root).rglob("*.py")):
        if ".mark.%s(" % policy.marker in path.read_text(encoding="utf-8"):
            shutil.move(str(path), str(hidden / path.name))
            moved += 1
    assert moved
    return [("uncovered", u.id) for u in numbered + plain]


def _stale_id_through_an_imported_mark(repo, rule):
    new = _fresh_id(repo)
    _append(
        _test_file(repo),
        "\n\nfrom pytest import mark  # noqa: E402\n\n\n@mark.%s(%s)\n"
        "def test_planted():\n    pass\n" % (_policy(repo).marker, json.dumps(new)),
    )
    return [("marker-undefined-id", new)]


def _marker_with_a_computed_id(repo, rule):
    _marker(repo, "str(1)")
    return [("marker-unreadable", None)]


def _gap_for_an_undefined_id(repo, rule):
    new = _fresh_id(repo)
    _set(repo, gaps={new: "the requirement this excused was removed"})
    return [("gap-undefined-id", new)]


def _gap_for_a_covered_id(repo, rule):
    numbered, _ = _units(repo, rule)
    _set(repo, gaps={numbered[0].id: "already has a test"})
    return [("gap-redundant", numbered[0].id)]


def _gap_for_a_malformed_id(repo, rule):
    numbered, _ = _units(repo, rule)
    bad = numbered[0].id + " "
    _set(repo, gaps={bad: "a trailing space"})
    return [("gap-malformed-id", bad)]


def _empty_specs_root(repo, rule):
    for spec in _specs(repo):
        spec.unlink()
    marker = _policy(repo).marker
    for path in sorted((repo / _policy(repo).tests_root).rglob("*.py")):
        if ".mark.%s(" % marker in path.read_text(encoding="utf-8"):
            path.unlink()
    return [("no-requirements", None)]


def _stale_no_requirements_reason(repo, rule):
    _set(repo, no_requirements="nothing is specified yet")
    return [("stale-no-requirements", None)]


_FAULTS = [
    _requirement_no_test_names,
    _criteria_named_only_by_the_bare_id,
    _one_criterion_of_three_unnamed,
    _marker_names_an_undefined_id,
    _marker_names_an_undefined_criterion,
    _marker_names_an_unlisted_prefix,
    _marker_on_a_helper,
    _marker_on_a_test_a_later_definition_replaces,
    _marker_in_a_class_with_a_constructor,
    _marker_in_a_class_switched_off,
    _marked_files_below_a_directory_pytest_skips,
    _stale_id_through_an_imported_mark,
    _marker_with_a_computed_id,
    _gap_for_an_undefined_id,
    _gap_for_a_covered_id,
    _gap_for_a_malformed_id,
    _empty_specs_root,
    _stale_no_requirements_reason,
]


def _pairs(findings):
    return sorted(((f["kind"], f["id"]) for f in findings), key=str)


@pytest.mark.parametrize("fault", _FAULTS, ids=lambda f: f.__name__.lstrip("_"))
def test_each_planted_fault_adds_exactly_its_finding(tmp_path, rule, fault):
    repo, env = build_scratch(tmp_path, git=False)
    _, before = tr.trace_tree(str(repo), _policy(repo), rule)
    assert before.findings == [] and before.units
    expected = fault(repo, rule)
    assert expected
    _, after = tr.trace_tree(str(repo), _policy(repo), rule)
    assert _pairs(after.findings) == sorted(expected, key=str)
    assert after.result == "fail"
    assert all(f["kind"] in tr.FINDING_KINDS for f in after.findings)

    # The command reaches the same findings from the same tree, and says so.
    out = run_cli(repo, env)
    assert out.returncode == 1, out.stdout
    matrix = read_matrix(repo)
    assert _pairs(matrix["findings"]) == sorted(expected, key=str)
    assert matrix["result"] == "fail"
    for kind, _ in expected:
        assert kind in out.stdout, out.stdout


def test_a_gap_with_a_reason_excuses_an_unnamed_requirement(tmp_path, rule):
    repo, env = build_scratch(tmp_path, git=False)
    (expected,) = _requirement_no_test_names(repo, rule)
    _set(repo, gaps={expected[1]: "waits for the store"})
    _, judged = tr.trace_tree(str(repo), _policy(repo), rule)
    assert judged.findings == []
    assert judged.counts["gap"] == 1
    out = run_cli(repo, env)
    assert out.returncode == 0, out.stdout
    unit = [
        u for r in read_matrix(repo)["requirements"] for u in r["units"] if u["gap"]
    ]
    assert [(u["id"], u["verdict"], u["gap"]) for u in unit] == [
        (expected[1], "gap", "waits for the store")
    ]


def test_zero_requirements_passes_only_under_a_stated_reason(tmp_path, rule):
    repo, env = build_scratch(tmp_path, git=False)
    _empty_specs_root(repo, rule)
    assert run_cli(repo, env).returncode == 1
    assert read_matrix(repo)["counts"] == {
        "covered": None,
        "gap": None,
        "uncovered": None,
    }
    _set(repo, no_requirements="nothing is specified yet")
    out = run_cli(repo, env)
    assert out.returncode == 0, out.stdout
    matrix = read_matrix(repo)
    assert (matrix["state"], matrix["result"]) == ("no-requirements", "pass")
    assert matrix["counts"] == {"covered": None, "gap": None, "uncovered": None}
    assert "no requirement" in out.stdout, out.stdout


# ------------------------------------------------- what pytest itself collects

_PROBE = "trace_probe"
_PROBE_SOURCE = """\
import json


def pytest_collection_finish(session):
    named = {}
    for item in session.items:
        ids = [str(a) for m in item.iter_markers(name=%(marker)s) for a in m.args]
        if ids:
            named.setdefault(item.nodeid.split("[")[0], set()).update(ids)
    with open(%(out)s, "w", encoding="utf-8") as fh:
        json.dump(
            {"collected": len(session.items),
             "named": {test: sorted(ids) for test, ids in named.items()}},
            fh,
        )
"""


def _import_path():
    """The session's own import path with each entry made absolute against
    the project root, where `make` starts pytest, then the directory this
    suite's helper modules load from, which pytest adds for the project's
    tree through its conftest and a scratch copy has no conftest to add."""
    entries = [e for e in os.environ.get("PYTHONPATH", "").split(os.pathsep) if e]
    paths = [e if os.path.isabs(e) else str(_ROOT / e) for e in entries]
    helpers = str(_ROOT / "tests")
    return paths + [helpers] if helpers not in paths else paths


def named_by_pytest(root, base):
    """(tests collected, {test: [ids]}) from pytest's own collection of
    *root*: a child `pytest --collect-only` with no path argument, so the
    ini's testpaths, every conftest and every collection hook apply, asked
    which items carry the marker. Parametrized cases fold into their test."""
    policy = _policy(root)
    plugins = base / "probe"
    plugins.mkdir()
    out = plugins / "named.json"
    (plugins / (_PROBE + ".py")).write_text(
        _PROBE_SOURCE % {"marker": repr(policy.marker), "out": repr(str(out))},
        encoding="utf-8",
    )
    env = hermetic_git.git_env(plugins)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(plugins)] + _import_path())
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"]
        + ["-p", "no:cacheprovider", "-p", _PROBE],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    # A tree with no test left is still a collection pytest finished.
    finished = (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED)
    assert ran.returncode in finished, ran.stdout
    found = json.loads(out.read_text(encoding="utf-8"))
    return found["collected"], found["named"]


def named_by_the_reader(root, rule):
    """{test: [ids]} as scripts/traceability.py reads it from source."""
    citations, _ = tr.scan_tests(str(root), _policy(root), rule)
    named = {}
    for citation in citations:
        for test in citation.tests:
            named.setdefault(test, set()).update(citation.ids)
    return {test: sorted(ids) for test, ids in named.items()}


def test_the_reader_and_pytest_agree_on_which_test_names_which_id(tmp_path, rule):
    """The reader judges by name and imports nothing, so what pytest really
    collects is the only proof that a test it counts is a test that runs."""
    collected, theirs = named_by_pytest(_ROOT, tmp_path)
    assert collected, "pytest collected nothing"
    ours = named_by_the_reader(_ROOT, rule)
    if _policy(_ROOT).no_requirements is None:
        assert ours, "the reader found no test naming a requirement"
    assert ours == theirs


_STATIC_FAULTS = [
    _marker_on_a_helper,
    _marker_on_a_test_a_later_definition_replaces,
    _marker_in_a_class_with_a_constructor,
    _marker_in_a_class_switched_off,
    _marked_files_below_a_directory_pytest_skips,
    _stale_id_through_an_imported_mark,
]


@pytest.mark.parametrize("fault", _STATIC_FAULTS, ids=lambda f: f.__name__.lstrip("_"))
def test_the_reader_counts_no_test_pytest_does_not_collect(tmp_path, rule, fault):
    repo, _ = build_scratch(tmp_path, git=False)
    assert named_by_the_reader(repo, rule)
    assert fault(repo, rule)
    _, judged = tr.trace_tree(str(repo), _policy(repo), rule)
    assert judged.findings, "the fault planted nothing the reader reports"
    assert named_by_the_reader(repo, rule) == named_by_pytest(repo, tmp_path)[1]


def _marker_through_an_alias(repo, rule):
    _append(
        _test_file(repo),
        "\n\n_m = pytest.mark\n\n\n@_m.%s(%s)\ndef test_planted():\n    pass\n"
        % (_policy(repo).marker, json.dumps(_fresh_id(repo))),
    )


def _conftest_ignores_the_marked_file(repo, rule):
    path = _test_file(repo)
    (path.parent / "conftest.py").write_text(
        "collect_ignore = [%s]\n" % json.dumps(path.name), encoding="utf-8"
    )


def _class_inherits_a_constructor(repo, rule):
    numbered, _ = _units(repo, rule)
    _append(
        _test_file(repo),
        "\n\nclass Base:\n    def __init__(self):\n        pass\n\n\n"
        "class TestPlanted(Base):\n    @pytest.mark.%s(%s)\n"
        "    def test_planted(self):\n        pass\n"
        % (_policy(repo).marker, json.dumps(numbered[0].id)),
    )


@pytest.mark.parametrize(
    "fault",
    [
        _marker_through_an_alias,
        _conftest_ignores_the_marked_file,
        _class_inherits_a_constructor,
    ],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_the_comparison_fails_on_what_only_pytest_can_see(tmp_path, rule, fault):
    """Each of these is decided at import or by a hook, so reading source
    cannot see it; the comparison with pytest's collection is what catches it."""
    repo, _ = build_scratch(tmp_path, git=False)
    work = tmp_path / "clean"
    work.mkdir()
    assert named_by_the_reader(repo, rule) == named_by_pytest(repo, work)[1]
    fault(repo, rule)
    work = tmp_path / "faulted"
    work.mkdir()
    assert named_by_the_reader(repo, rule) != named_by_pytest(repo, work)[1]


# --------------------------------------------------------------- the command


def _header_title():
    """The `title:` of the command's module header, the line check_O reads."""
    source = (_ROOT / "scripts" / _CLI).read_text(encoding="utf-8")
    meta = cs._module_meta(ast.get_docstring(ast.parse(source)))
    assert meta["title"]
    return meta["title"]


def test_help_describes_the_command_by_its_title(tmp_path):
    repo, env = build_scratch(tmp_path, git=False)
    out = subprocess.run(
        [sys.executable, str(repo / "scripts" / _CLI), "--help"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert out.returncode == 0, out.stdout
    said = " ".join(out.stdout.split())
    assert " ".join(_header_title().split()) in said, out.stdout
    assert "kind:" not in said and "exit: 0" in said, out.stdout


def _a_directory_where_the_matrix_goes(repo):
    matrix_path(repo).mkdir(parents=True)


def _a_file_where_its_directory_goes(repo):
    parent = matrix_path(repo).parent
    assert parent != repo, "the matrix sits in the project root"
    parent.parent.mkdir(parents=True, exist_ok=True)
    parent.write_text("not a directory\n", encoding="utf-8")


@pytest.mark.parametrize("git", [True, False], ids=["git", "no-git"])
@pytest.mark.parametrize(
    "squat",
    [_a_directory_where_the_matrix_goes, _a_file_where_its_directory_goes],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_a_matrix_that_cannot_be_written_is_exit_2_and_says_why(tmp_path, git, squat):
    repo, env = build_scratch(tmp_path, git=git)
    squat(repo)
    before = _tree(repo)
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "Traceback" not in out.stdout, out.stdout
    assert "traceability.matrix_path" in out.stdout, out.stdout
    assert "cannot be written" in out.stdout, out.stdout
    assert str(repo) not in out.stdout, out.stdout
    # Nothing is left behind: no temporary file, and no matrix a reader
    # could take for this run's.
    assert _tree(repo) == before


def _tree(path):
    return {
        str(p.relative_to(path)): (
            os.readlink(str(p))
            if p.is_symlink()
            else p.read_bytes()
            if p.is_file()
            else None
        )
        for p in sorted(path.rglob("*"))
        if ".git" not in p.relative_to(path).parts
    }


def test_the_cli_writes_one_matrix_and_a_second_run_changes_nothing(tmp_path):
    jsonschema = optional_deps.importorskip("jsonschema", extra="dev")
    repo, env = build_scratch(tmp_path)
    before = _tree(repo)
    first = run_cli(repo, env)
    assert first.returncode == 0, first.stdout
    after = _tree(repo)
    rel = _policy(_ROOT).matrix_path
    added = sorted(set(after) - set(before))
    assert [p for p in added if after[p] is not None] == [rel], added
    assert {p: after[p] for p in before} == before
    assert _git(repo, env, "status", "--porcelain") == ""

    text = matrix_path(repo).read_text(encoding="utf-8")
    matrix = json.loads(text)
    assert text == json.dumps(matrix, indent=2, sort_keys=True) + "\n"
    schema = json.loads(
        (repo / _policy(_ROOT).matrix_schema).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(matrix)
    assert (matrix["state"], matrix["result"]) == ("traced", "pass")
    units = [u for r in matrix["requirements"] for u in r["units"]]
    assert units and all(u["verdict"] == "covered" and u["tests"] for u in units)
    assert matrix["counts"]["covered"] == len(units)
    for unit in units:
        for test in unit["tests"]:
            assert (repo / test.split("::")[0]).is_file(), test
    assert str(repo) not in text and str(tmp_path) not in text

    second = run_cli(repo, env)
    assert second.returncode == 0, second.stdout
    assert _tree(repo) == after
    assert second.stdout == first.stdout


def _unlisted_prefix_in_a_spec(repo):
    _append(_specs(repo)[0], "\n## ZZUNLISTED-0001 A heading no registry row reads\n")
    return "ZZUNLISTED-0001"


def _test_file_that_does_not_parse(repo):
    _append(_test_file(repo), "\ndef (:\n")
    return _test_file(repo).name


def _schema_missing(repo):
    (repo / _policy(repo).matrix_schema).unlink()
    return "traceability.matrix_schema"


def _schema_without_a_cap(repo):
    path = repo / _policy(repo).matrix_schema
    schema = json.loads(path.read_text(encoding="utf-8"))
    del schema["$defs"]["reason"]["maxLength"]
    path.write_text(json.dumps(schema), encoding="utf-8")
    return "maxLength"


def _specs_root_missing(repo):
    shutil.rmtree(str(repo / _policy(repo).specs_root))
    return "traceability.specs_root"


def _ini_does_not_configure(repo):
    _append(repo / "pyproject.toml", "\n[tool.pytest.ini_options.broken\n")
    return "collection rule"


@pytest.mark.parametrize(
    "fault",
    [
        _unlisted_prefix_in_a_spec,
        _test_file_that_does_not_parse,
        _schema_missing,
        _schema_without_a_cap,
        _specs_root_missing,
        _ini_does_not_configure,
    ],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_an_input_that_cannot_be_read_is_exit_2_and_leaves_no_green_matrix(
    tmp_path, fault
):
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    assert read_matrix(repo)["result"] == "pass"
    said = fault(repo)
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert said in out.stdout, out.stdout
    if matrix_path(repo).exists():
        matrix = read_matrix(repo)
        assert (matrix["state"], matrix["result"]) == ("refused", "refused")
        assert matrix["counts"] == {"covered": None, "gap": None, "uncovered": None}
        assert matrix["requirements"] == []
    else:
        assert fault in (_schema_missing, _schema_without_a_cap)
        assert "removed" in out.stdout, out.stdout


def test_the_cli_exit_code_says_which_kind_of_red(tmp_path, rule):
    repo, env = build_scratch(tmp_path)
    green = run_cli(repo, env)
    assert green.returncode == 0, green.stdout
    assert "pass" in green.stdout

    (expected,) = _requirement_no_test_names(repo, rule)
    red = run_cli(repo, env)
    assert red.returncode == 1, red.stdout
    assert "uncovered" in red.stdout and expected[1] in red.stdout, red.stdout
    assert read_matrix(repo)["result"] == "fail"

    # A config the loader refuses names no path this run may trust, so the
    # earlier matrix is neither rewritten nor removed, and the run says so.
    earlier = matrix_path(repo).read_bytes()
    for change in (
        {"kind_evidence": {}},
        {"marker": "not a name"},
        {"gaps": {"X": ""}},
    ):
        scratch_manifest = (repo / tr.MANIFEST).read_text(encoding="utf-8")
        _set(repo, **change)
        out = run_cli(repo, env)
        assert out.returncode == 2, out.stdout
        assert "traceability." in out.stdout and "may still stand" in out.stdout
        assert matrix_path(repo).read_bytes() == earlier
        (repo / tr.MANIFEST).write_text(scratch_manifest, encoding="utf-8")

    (repo / tr.MANIFEST).write_text("{not json", encoding="utf-8")
    out = run_cli(repo, env)
    assert out.returncode == 2 and "may still stand" in out.stdout, out.stdout

    usage = subprocess.run(
        [sys.executable, str(repo / "scripts" / _CLI), "--no-such-flag"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert usage.returncode == 2, usage.stdout


def test_a_run_that_stops_leaves_a_red_matrix(tmp_path, monkeypatch):
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    for key, value in hermetic_git.git_env_vars(tmp_path / "work").items():
        monkeypatch.setenv(key, value)
    import trace_requirements

    def stop(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(trace_requirements.traceability, "trace_tree", stop)
    with pytest.raises(KeyboardInterrupt):
        trace_requirements.main(["--root", str(repo)])
    matrix = read_matrix(repo)
    assert (matrix["state"], matrix["result"]) == ("incomplete", "incomplete")


# ------------------------------------------------- where a config path lands


def _outside(tmp_path):
    """A directory beside the project holding what a run must not touch or
    read: a file, and a spec defining a requirement of its own."""
    outside = tmp_path / "outside"
    (outside / "traceability").mkdir(parents=True)
    (outside / "keep.txt").write_text("precious\n", encoding="utf-8")
    (outside / "traceability" / "keep.txt").write_text("precious\n", encoding="utf-8")
    (outside / "outside-spec.md").write_text(
        "---\ntitle: Outside\nkind: spec\n---\n\n## %s From outside the project\n"
        % _fresh_id(_ROOT),
        encoding="utf-8",
    )
    return outside


def _link_first_part(repo, outside):
    rel = Path(_policy(repo).matrix_path)
    link = repo / rel.parts[0]
    assert not link.exists() and len(rel.parts) >= 3
    link.symlink_to(outside, target_is_directory=True)


def _link_parent(repo, outside):
    parent = matrix_path(repo).parent
    parent.parent.mkdir(parents=True)
    parent.symlink_to(outside / "traceability", target_is_directory=True)


def _link_matrix(repo, outside):
    matrix_path(repo).parent.mkdir(parents=True)
    matrix_path(repo).symlink_to(outside / "keep.txt")


def _link_tmp_sibling(repo, outside):
    path = matrix_path(repo)
    path.parent.mkdir(parents=True)
    (path.parent / (path.name + ".tmp")).symlink_to(outside / "keep.txt")


def _link_specs_root(repo, outside):
    specs = repo / _policy(repo).specs_root
    shutil.rmtree(str(specs))
    specs.symlink_to(outside, target_is_directory=True)


def _link_one_spec(repo, outside):
    (repo / _policy(repo).specs_root / "linked.md").symlink_to(
        outside / "outside-spec.md"
    )


def _link_spec_dir(repo, outside):
    link = repo / _policy(repo).specs_root / "more"
    link.symlink_to(outside, target_is_directory=True)


def _link_tests_root(repo, outside):
    tests = repo / _policy(repo).tests_root
    shutil.move(str(tests), str(outside / "tests"))
    tests.symlink_to(outside / "tests", target_is_directory=True)


def _link_schema(repo, outside):
    schema = repo / _policy(repo).matrix_schema
    shutil.move(str(schema), str(outside / "schema.json"))
    schema.symlink_to(outside / "schema.json")


_LINKS = [
    _link_first_part,
    _link_parent,
    _link_matrix,
    _link_tmp_sibling,
    _link_specs_root,
    _link_one_spec,
    _link_spec_dir,
    _link_tests_root,
    _link_schema,
]


@pytest.mark.parametrize("git", [True, False], ids=["git", "no-git"])
@pytest.mark.parametrize("link", _LINKS, ids=lambda f: f.__name__.lstrip("_"))
def test_a_path_through_a_symlink_writes_and_reads_nothing(tmp_path, git, link):
    """A config path is judged as text by the loader and by git's ignore rule;
    a symlinked component points the write, or the read, somewhere neither
    looked. The check that catches it needs no git."""
    repo, env = build_scratch(tmp_path, git=git)
    outside = _outside(tmp_path)
    link(repo, outside)
    before = _tree(outside)
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "symlink" in out.stdout, out.stdout
    assert _tree(outside) == before, out.stdout
    foreign = _fresh_id(_ROOT)
    path = matrix_path(repo)
    if link in (_link_one_spec, _link_spec_dir):
        # The roots themselves are the project's, so the run starts and then
        # refuses at the link: a red matrix inside the project, none of the
        # outside spec in it.
        text = path.read_text(encoding="utf-8")
        assert json.loads(text)["state"] == "refused" and foreign not in text
    else:
        assert (
            not os.path.lexists(str(path)) or path.is_symlink() or link is _link_parent
        )
    assert foreign not in out.stdout


@pytest.mark.parametrize("git", [True, False], ids=["git", "no-git"])
@pytest.mark.parametrize(
    "bad", ["/tmp/keel-matrix.json", "../matrix.json", "a/../../m.json"]
)
def test_a_matrix_path_outside_the_project_is_refused(tmp_path, git, bad):
    repo, env = build_scratch(tmp_path, git=git)
    _set(repo, matrix_path=bad)
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "traceability.matrix_path" in out.stdout, out.stdout
    assert (
        not (tmp_path / "matrix.json").exists() and not (tmp_path / "m.json").exists()
    )
    assert not os.path.exists(bad) or not os.path.isabs(bad)


def test_a_matrix_git_would_list_is_refused_and_without_git_is_written(tmp_path):
    repo, env = build_scratch(tmp_path)
    _set(repo, matrix_path="docs/matrix.json")
    _git(repo, env, "commit", "-q", "-am", "matrix path")
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "is not git-ignored" in out.stdout, out.stdout
    assert not (repo / "docs" / "matrix.json").exists()
    assert _git(repo, env, "status", "--porcelain") == ""

    shutil.rmtree(str(repo / ".git"))
    out = run_cli(repo, env)
    assert out.returncode == 0, out.stdout
    assert (
        json.loads((repo / "docs" / "matrix.json").read_text("utf-8"))["result"]
        == "pass"
    )


def test_a_repository_git_cannot_read_is_not_read_as_no_repository(tmp_path):
    repo, env = build_scratch(tmp_path)
    shutil.rmtree(str(repo / ".git"))
    (repo / ".git").write_text("not a repository\n", encoding="utf-8")
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "git" in out.stdout and "ignored" in out.stdout, out.stdout
    assert not matrix_path(repo).exists()


# ------------------------------------------------------------------ the wiring


def test_the_marker_is_registered_and_the_gate_is_a_verify_goal():
    policy = _policy(_ROOT)
    inis = [
        p for p in ("pyproject.toml", "pyproject.toml.jinja") if (_ROOT / p).is_file()
    ]
    assert "pyproject.toml" in inis
    for name in inis:
        # The template's ini holds its placeholders inside strings and
        # comments only, so it is the same TOML before and after rendering.
        ini = tomllib.loads((_ROOT / name).read_text(encoding="utf-8"))
        rows = ini["tool"]["pytest"]["ini_options"]["markers"]
        registered = [row.split(":", 1)[0].split("(", 1)[0].strip() for row in rows]
        assert policy.marker in registered, "%s registers %s, not `%s`" % (
            name,
            registered,
            policy.marker,
        )
    rules = cs._make_rules((_ROOT / "Makefile").read_text(encoding="utf-8"))
    unresolved = []
    reached = cs._scripts_reachable_from(rules, "verify", unresolved)
    assert "scripts/%s" % _CLI in reached, sorted(reached)
    assert not unresolved, unresolved
    assert (_ROOT / policy.matrix_schema).is_file()
    assert tr.read_bounds(json.loads((_ROOT / policy.matrix_schema).read_text("utf-8")))
