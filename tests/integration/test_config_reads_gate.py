"""
title: Integration — a configured value is read only through the config loader
kind: tests
layer: n/a
summary: A tree-wide gate over the Python files tests/source_tree.py `python_files` lists under config/project.json `config_reads.roots`, read from the syntax tree, scripts/config_loader.py itself left out. It fails two kinds of direct read. The first is a read of a config file scripts/config_loader.py `PROJECT_READS` declares, found by tests/source_tree.py `config_path_reads`: an `open`, `io.open` or other `.open` call, or a `.read_text`, `.read_bytes` or `.open` on a path, whose path is a string constant naming the file, a join or `Path` of constants whose last segments are its parts (a `*NAME` of a tuple of constants, or `*TEXT.split(...)` of such a string, included), a name bound to one at module level or earlier in the same function, or a path constant (a string or a join of constants) of a project module a module-level absolute import binds, read as `mod.NAME` or imported by name with `from mod import NAME` (resolved through config/project.json `import_layers.search_roots`); or a call to a function of the same module that opens the parameter it hands such a path to. The second is a read of a variable the config declares as carrying a value (scripts/config_loader.py `declared_variables`, with each KEYS row's variable), found by tests/source_tree.py `env_reads`: `environ[...]`, `environ.get/pop/setdefault(...)`, `... in environ` or `getenv(...)` with the name a literal or a module-level string constant. Each finding is one line, `<file>:<line>: <rule> — <what to do>`. The exceptions are `config_reads.allowed`, a map from a file to the reason it still reads directly; an entry whose reason is blank, whose file is absent or outside the roots, or whose file no longer reads directly is red, and the map may hold no more entries than `_CEILING`, so it only shrinks. A walk over no root, no file, no declared file or no declared variable is a failure, never a pass. An open for writing counts too, since the loader is the one module that touches the file. It cannot see a path handed in as a parameter, an attribute of a module imported inside a function or relatively, a function of another module that opens what it is given, a method called through an object, a git cat-file blob, a variable whose name the code holds in a variable (`os.environ.get(name)` with `name` a parameter), a read through subprocess or importlib, os.environ handed on as a mapping, or a path built at run time from a value that is not a constant. It does not walk tests/, which reads config as its own policy and to build fixtures. Where the gate runs tells keel's files from a project's own: in the template repository, which holds copier.yml, a finding is red; a generated project carries no list of the files keel shipped, and keel's were judged in the template, so there the two finding tests skip with a reason naming each direct read they saw, until the warn-then-fail tier for a project's own code is built. Not a check_* letter: the letters A to Z are taken.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

_BLOCK = "config_reads"
_POLICY_ROWS = ((_BLOCK, "allowed"), (_BLOCK, "roots"))
# The loader is the one module allowed to open a config file and read a
# declared variable, so the walk leaves it out.
_LOADER = "scripts/config_loader.py"
# keel's count of config_reads.allowed entries: a migrated module leaves the
# map and this number falls with it, so the map cannot grow back unnoticed.
# A generated project renders out the entries for files it does not ship, so
# its count is lower; tests/integration/test_copier_generation.py, which
# copier prunes, holds keel's count equal to this number.
_CEILING = 12
# Where the gate runs tells keel's files from a project's own (the B1 ruling in
# docs/design/downstream-feedback.md). The template repository holds this file
# and every Python file under its roots is keel's, so a finding is red there. A
# generated project carries no list of the files keel shipped, and keel's own
# were judged in the template, so there the finding tests skip and name what
# they saw until the warn-then-fail tier is built.
_TEMPLATE_MARK = "copier.yml"
_PROJECT_SKIP = (
    "a generated project: this gate cannot tell a file keel ships from one the "
    "project wrote, so a direct read is not judged here until the warn-then-fail "
    "tier for a project's own code is built; %d direct read(s) seen%s"
)
_ALLOW = "or allowlist it in config/project.json config_reads.allowed with a reason"
_FILE_FIX = "read it through scripts/config_loader.py read and resolve, " + _ALLOW
_ENV_FIX = "read it through scripts/config_loader.py env, " + _ALLOW


def reads_policy(manifest, where=config_loader.CONFIG_FILE):
    """{roots, allowed} of a parsed config/project.json, resolved through the
    loader's rows. Raises SourceTreeError naming what is missing or malformed,
    because a gate that cannot read its policy must not pass."""
    try:
        got = config_loader.resolve(
            manifest, config_loader.rows(*_POLICY_ROWS), where, environ={}
        )
    except config_loader.ConfigError as exc:
        raise st.SourceTreeError("; ".join(exc.lines)) from exc
    roots = got[(_BLOCK, "roots")]
    allowed = got[(_BLOCK, "allowed")]
    if not roots:
        raise st.SourceTreeError(
            "%s: %s.roots names no code root -- zero items" % (where, _BLOCK)
        )
    bad = [r for r in roots if not r or r.startswith("/") or r.endswith("/")]
    if bad:
        raise st.SourceTreeError(
            "%s: %s.roots holds %r; each root is a repo-relative directory with no "
            "trailing slash" % (where, _BLOCK, bad[0])
        )
    if not all(isinstance(v, str) for v in allowed.values()):
        raise st.SourceTreeError(
            "%s: %s.allowed maps each file to a reason string" % (where, _BLOCK)
        )
    return {"roots": list(roots), "allowed": dict(allowed)}


def declared_variables(manifest, where=config_loader.CONFIG_FILE):
    """The variables *manifest* and the loader's rows declare as carrying a
    value, sorted."""
    names = set(config_loader.declared_variables(manifest, where))
    names.update(k.env for k in config_loader.KEYS if k.env is not None)
    return sorted(names)


def judges_findings(root):
    """True when *root* is the template repository, where a direct read is a
    finding; False in a generated project (_TEMPLATE_MARK)."""
    return (Path(root) / _TEMPLATE_MARK).is_file()


def project_skip_reason(lines):
    """The skip reason a generated project's finding test gives, naming each
    direct read it saw so none goes unreported."""
    return _PROJECT_SKIP % (len(lines), (": " + "; ".join(lines)) if lines else "")


def _under(relpath, roots):
    return any(relpath == r or relpath.startswith(r + "/") for r in roots)


def direct_reads(root, roots, paths, variables, search_roots):
    """{files, findings}: *files* the walked files, *findings* {file: [line]}
    for each direct read of a declared config file in *paths* or of a variable
    in *variables*, in line order; *search_roots* (config/project.json
    `import_layers.search_roots`) resolve the project modules whose string
    constants a path may name. Raises SourceTreeError for a walk over no root,
    no file, no declared file or no declared variable."""
    if not roots:
        raise st.SourceTreeError("%s: no code root to walk -- zero items" % root)
    if not paths:
        raise st.SourceTreeError("%s: no declared config file -- zero items" % root)
    if not variables:
        raise st.SourceTreeError("%s: no declared variable -- zero items" % root)
    files = [f for f in st.python_files(root) if _under(f, roots) and f != _LOADER]
    if not files:
        raise st.SourceTreeError(
            "%s: no Python file under %s -- zero items" % (root, ", ".join(roots))
        )
    wanted = set(variables)
    findings = {}
    for relpath in files:
        tree = st.parse(root, relpath)
        imported = st.imported_paths(root, tree, search_roots)
        found = [
            (line, "opens %s directly" % path, _FILE_FIX)
            for line, path in st.config_path_reads(tree, paths, imported)
        ]
        found += [
            (line, "reads the declared variable %s directly" % name, _ENV_FIX)
            for line, name in st.env_reads(tree)
            if name in wanted
        ]
        if found:
            findings[relpath] = [
                "%s:%d: %s — %s" % (relpath, line, rule, fix)
                for line, rule, fix in sorted(found)
            ]
    return {"files": files, "findings": findings}


def allowlist_findings(root, roots, allowed, findings):
    """One line per `config_reads.allowed` entry that is not a live exception:
    a blank reason, a file that is absent or outside *roots*, or a file that
    makes no direct read in *findings*."""
    out = []
    for relpath in sorted(allowed):
        where = "config/project.json config_reads.allowed %s" % relpath
        if st.blank(allowed[relpath]):
            out.append("%s: gives no reason; say why it still reads directly" % where)
        if not (Path(root) / relpath).is_file():
            out.append("%s: no such file; delete the entry" % where)
        elif not _under(relpath, roots):
            out.append(
                "%s: is outside config_reads.roots, so the gate never walks it; "
                "delete the entry" % where
            )
        elif relpath not in findings:
            out.append(
                "%s: makes no direct read any more; delete the entry and lower "
                "_CEILING in tests/integration/test_config_reads_gate.py" % where
            )
    return out


# --- the tree itself -------------------------------------------------------------

_RESULT = {}


def _tree():
    if not _RESULT:
        manifest = config_loader.read(str(_ROOT))
        policy = reads_policy(manifest)
        result = direct_reads(
            _ROOT,
            policy["roots"],
            config_loader.PROJECT_READS,
            declared_variables(manifest),
            st.import_layers(_ROOT)["search_roots"],
        )
        _RESULT.update(policy=policy, **result)
    return _RESULT


def _unexcused(rule):
    """The findings of *rule* no allowlist entry excuses; in a generated
    project the calling test skips instead, naming them."""
    tree = _tree()
    allowed = tree["policy"]["allowed"]
    found = [
        line
        for relpath, lines in sorted(tree["findings"].items())
        if relpath not in allowed
        for line in lines
        if rule in line
    ]
    if not judges_findings(_ROOT):
        pytest.skip(project_skip_reason(found))
    return found


def test_no_code_root_reads_a_config_file_outside_the_loader():
    unexcused = _unexcused(": opens ")
    assert not unexcused, "\n".join(unexcused)


def test_no_code_root_reads_a_declared_variable_outside_the_loader():
    unexcused = _unexcused(": reads the declared variable ")
    assert not unexcused, "\n".join(unexcused)


def test_every_allowlist_entry_is_a_live_exception_with_a_reason():
    tree = _tree()
    found = allowlist_findings(
        _ROOT, tree["policy"]["roots"], tree["policy"]["allowed"], tree["findings"]
    )
    assert not found, "\n".join(found)


def test_the_allowlist_only_shrinks():
    allowed = _tree()["policy"]["allowed"]
    assert len(allowed) <= _CEILING, (
        "config/project.json config_reads.allowed holds %d entries, more than "
        "the %d tests/integration/test_config_reads_gate.py _CEILING allows; read "
        "the new one through scripts/config_loader.py instead"
        % (len(allowed), _CEILING)
    )


# --- fixtures: each rule can fail ---------------------------------------------------

_PATHS = config_loader.PROJECT_READS
_MCP_MODEL = "KEEL_MCP_MODEL"
# A fixture project resolves `from src import x` from its root, as keel's own
# import_layers.search_roots does with its '' entry.
_SEARCH = [""]


def _run_date_variable():
    """The variable keel's config/project.json `evidence.run_date.env` names."""
    manifest = config_loader.read(str(_ROOT))
    return manifest["evidence"]["run_date"]["env"]


# A sibling module a planted read may import a path constant from; it holds
# the constants and reads nothing, so it is never a finding itself.
_NAMES = (
    "import os\n"
    "MANIFEST = 'config/project.json'\n"
    "README = 'README.md'\n"
    "PRACTICES = os.path.join('config', 'practices.json')\n"
    "NOTES = os.path.join('docs', 'notes.md')\n"
)


def _project(tmp_path, text):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod.py").write_text(text, encoding="utf-8")
    (root / "src" / "names.py").write_text(_NAMES, encoding="utf-8")
    return root


def _findings(tmp_path, text):
    variables = [_MCP_MODEL, _run_date_variable()]
    result = direct_reads(_project(tmp_path, text), ["src"], _PATHS, variables, _SEARCH)
    return [line for lines in result["findings"].values() for line in lines]


_PLANTED = [
    ("open('config/project.json')\n", 1, "opens config/project.json"),
    (
        "import json, os\n"
        "def f(root):\n"
        "    return json.load(open(os.path.join(root, 'config', 'project.json')))\n",
        3,
        "opens config/project.json",
    ),
    (
        "import os\nP = os.path.join('config', 'project.json')\nopen(P)\n",
        3,
        "opens config/project.json",
    ),
    (
        "from pathlib import Path\n"
        "def f(root):\n"
        "    return Path(root, 'config', 'practices.json').read_text()\n",
        3,
        "opens config/practices.json",
    ),
    (
        "from pathlib import Path\n"
        "def f(root):\n"
        "    with (Path(root) / 'config' / 'project.json').open() as fh:\n"
        "        return fh.read()\n",
        3,
        "opens config/project.json",
    ),
    (
        "import io, os\n"
        "_MANIFEST = ('config', 'project.json')\n"
        "def f(root):\n"
        "    return io.open(os.path.join(root, *_MANIFEST)).read()\n",
        4,
        "opens config/project.json",
    ),
    (
        "import os\n"
        "_MANIFEST = os.path.join('config', 'project.json')\n"
        "def f(root):\n"
        "    path = os.path.join(root, _MANIFEST)\n"
        "    with open(path, 'rb') as fh:\n"
        "        return fh.read()\n",
        5,
        "opens config/project.json",
    ),
    (
        "import json, os\n"
        "ROOT = '.'\n"
        "def _read_json(path):\n"
        "    with open(path, encoding='utf-8') as fh:\n"
        "        return json.load(fh)\n"
        "def f():\n"
        "    return _read_json(os.path.join(ROOT, 'config', 'practices.json'))\n",
        7,
        "opens config/practices.json",
    ),
    (
        "from pathlib import Path\n"
        "def f(root):\n"
        "    return Path(root).joinpath('config', 'project.json').read_bytes()\n",
        3,
        "opens config/project.json",
    ),
    (
        "import os\n"
        "_MANIFEST = 'config/project.json'\n"
        "def f(root):\n"
        "    with open(os.path.join(root, *_MANIFEST.split('/'))) as fh:\n"
        "        return fh.read()\n",
        4,
        "opens config/project.json",
    ),
    (
        "import os\n"
        "from src import names\n"
        "def f(root):\n"
        "    return open(os.path.join(root, *names.MANIFEST.split('/'))).read()\n",
        4,
        "opens config/project.json",
    ),
    (
        "import os\n"
        "from src import names\n"
        "def f(root):\n"
        "    return open(os.path.join(root, names.PRACTICES)).read()\n",
        4,
        "opens config/practices.json",
    ),
    (
        "import os\n"
        "from src.names import MANIFEST\n"
        "def f(root):\n"
        "    return open(os.path.join(root, MANIFEST)).read()\n",
        4,
        "opens config/project.json",
    ),
    (
        "import os\n"
        "from src.names import PRACTICES as P\n"
        "def f(root):\n"
        "    return open(os.path.join(root, P)).read()\n",
        4,
        "opens config/practices.json",
    ),
    ("import os\nm = os.environ['KEEL_MCP_MODEL']\n", 2, "variable KEEL_MCP_MODEL"),
    (
        "import os\nm = os.environ.get('KEEL_MCP_MODEL', '')\n",
        2,
        "variable KEEL_MCP_MODEL",
    ),
    (
        "import os\n_NAME = 'KEEL_MCP_MODEL'\nset_ = _NAME in os.environ\n",
        3,
        "variable KEEL_MCP_MODEL",
    ),
    ("import os\nd = os.getenv(%r)\n", 2, "variable %s"),
]


@pytest.mark.parametrize(
    "text, line, rule",
    _PLANTED,
    ids=[
        "open of the literal path",
        "json.load of an open of a join",
        "open of a module-level bound join",
        "Path read_text of the practices file",
        "Path division then .open",
        "io.open of a starred parts tuple",
        "open of a name bound in the function",
        "a same-module helper that opens its parameter",
        "Path.joinpath then read_bytes",
        "a starred split of a module constant",
        "a starred split of another module's constant",
        "another module's constant built by a join",
        "a constant imported by name from another module",
        "a joined constant imported under another name",
        "environ subscript",
        "environ.get",
        "membership through a module constant",
        "getenv of the run-date variable",
    ],
)
def test_a_planted_direct_read_is_red(tmp_path, text, line, rule):
    if "%r" in text:
        variable = _run_date_variable()
        text, rule = text % variable, rule % variable
    found = _findings(tmp_path, text)
    assert len(found) == 1, found
    assert found[0].startswith("src/mod.py:%d: " % line), found
    assert rule in found[0], found
    assert "scripts/config_loader.py" in found[0], found
    assert "config_reads.allowed" in found[0], found


@pytest.mark.parametrize(
    "text",
    [
        "import os\nP = os.path.join('config', 'project.json')\n"
        "t = os.path.getmtime(P)\nok = os.path.isfile(P)\n",
        "PROJECT_READS = ('config/project.json', 'config/practices.json')\n",
        '"""Reads config/project.json `evidence`, never opening it here."""\n',
        "import os\n"
        "def f(root):\n"
        "    return open(os.path.join(root, 'config', 'evidence', "
        "'gate-evidence.schema.json')).read()\n",
        "import os\n"
        "def f(root):\n"
        "    return open(os.path.join(root, 'tests', 'fixtures', 'project.json'))\n",
        "import subprocess\n"
        "subprocess.run(['git', 'cat-file', 'blob', 'HEAD:config/project.json'])\n",
        "print('config/project.json is the manifest')\n",
        "import os\nh = os.environ.get('HOME')\n",
        "import os\ndef f(name):\n    return os.environ.get(name)\n",
        "import os\n"
        "def f(root):\n"
        "    path = os.path.join(root, 'config', 'project.json')\n"
        "    path = os.path.join(root, 'README.md')\n"
        "    return open(path).read()\n",
        "def f(path):\n    return open(path).read()\n",
        "import os\n"
        "from src import names\n"
        "def f(root):\n"
        "    return open(os.path.join(root, *names.README.split('/'))).read()\n",
        "import os\n"
        "from src import names\n"
        "def f(root):\n"
        "    return open(os.path.join(root, names.NOTES)).read()\n",
        "import os\n"
        "from src.names import README\n"
        "def f(root):\n"
        "    return open(os.path.join(root, README)).read()\n",
    ],
    ids=[
        "getmtime and isfile of a bound path",
        "a tuple of declared paths",
        "a docstring naming the path",
        "an open of a schema file",
        "a file of the same name elsewhere",
        "a git cat-file blob",
        "a message naming the path",
        "an undeclared variable",
        "a variable named by a parameter",
        "a name rebound to another path",
        "a helper never handed a config path",
        "another module's constant naming another file",
        "another module's joined constant naming another file",
        "a constant imported by name naming another file",
    ],
)
def test_a_read_that_is_no_direct_config_read_is_not_a_finding(tmp_path, text):
    assert _findings(tmp_path, text) == []


def test_a_stale_or_unreasoned_allowlist_entry_is_red(tmp_path):
    root = _project(tmp_path, "open('config/project.json')\n")
    (root / "src" / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (root / "other").mkdir()
    (root / "other" / "out.py").write_text("x = 1\n", encoding="utf-8")
    result = direct_reads(root, ["src"], _PATHS, [_MCP_MODEL], _SEARCH)
    reason = "the reader is migrated in a later slice"
    assert (
        allowlist_findings(root, ["src"], {"src/mod.py": reason}, result["findings"])
        == []
    )
    for allowed, expected in (
        ({"src/mod.py": " -- "}, "src/mod.py: gives no reason"),
        ({"src/gone.py": reason}, "src/gone.py: no such file"),
        ({"other/out.py": reason}, "other/out.py: is outside config_reads.roots"),
        ({"src/clean.py": reason}, "src/clean.py: makes no direct read any more"),
    ):
        found = allowlist_findings(root, ["src"], allowed, result["findings"])
        assert len(found) == 1 and expected in found[0], (allowed, found)


def test_a_policy_with_a_missing_or_wrong_key_is_refused_by_name():
    with pytest.raises(st.SourceTreeError, match=r"\[not set\] config_reads\.allowed"):
        reads_policy({_BLOCK: {"roots": ["src"]}})
    with pytest.raises(st.SourceTreeError, match=r"config_reads\.roots is string"):
        reads_policy({_BLOCK: {"roots": "src", "allowed": {}}})
    with pytest.raises(st.SourceTreeError, match="reason string"):
        reads_policy({_BLOCK: {"roots": ["src"], "allowed": {"src/a.py": 1}}})
    assert reads_policy({_BLOCK: {"roots": ["src"], "allowed": {}}}) == {
        "roots": ["src"],
        "allowed": {},
    }


def test_a_finding_is_judged_in_the_template_and_named_in_a_generated_project(
    tmp_path,
):
    template = tmp_path / "template"
    project = tmp_path / "project"
    template.mkdir()
    project.mkdir()
    (template / _TEMPLATE_MARK).write_text("_subdirectory: .\n", encoding="utf-8")
    assert judges_findings(template) is True
    assert judges_findings(project) is False
    seen = ["src/a.py:3: opens config/project.json directly", "src/b.py:9: reads"]
    reason = project_skip_reason(seen)
    assert "2 direct read(s) seen: src/a.py:3: " in reason, reason
    assert "; src/b.py:9: reads" in reason, reason
    assert project_skip_reason([]).endswith("0 direct read(s) seen"), reason


def test_a_walk_over_zero_files_or_zero_declared_names_fails(tmp_path):
    root = _project(tmp_path, "x = 1\n")
    with pytest.raises(st.SourceTreeError, match="zero items"):
        reads_policy({_BLOCK: {"roots": [], "allowed": {}}})
    with pytest.raises(st.SourceTreeError, match="no code root"):
        direct_reads(root, [], _PATHS, [_MCP_MODEL], _SEARCH)
    with pytest.raises(st.SourceTreeError, match="no Python file under absent"):
        direct_reads(root, ["absent"], _PATHS, [_MCP_MODEL], _SEARCH)
    with pytest.raises(st.SourceTreeError, match="no declared variable"):
        direct_reads(root, ["src"], _PATHS, [], _SEARCH)
    with pytest.raises(st.SourceTreeError, match="no declared config file"):
        direct_reads(root, ["src"], (), [_MCP_MODEL], _SEARCH)
    assert direct_reads(root, ["src"], _PATHS, [_MCP_MODEL], _SEARCH)["files"] == [
        "src/mod.py",
        "src/names.py",
    ]


def test_the_live_walk_covers_files_and_declared_variables():
    """The live gate judged something: files under its roots and a declared
    variable set that holds the run-date variable."""
    tree = _tree()
    assert tree["files"], "no file walked -- zero items"
    manifest = config_loader.read(str(_ROOT))
    assert _run_date_variable() in declared_variables(manifest)
