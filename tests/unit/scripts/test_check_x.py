"""
title: Unit — check_structure check_X (a child process gets an allowlisted environment)
kind: tests
layer: n/a
summary: check_X's rule, pinned: every subprocess/asyncio spawn in a .py at the repo root or under any top-level directory but tests/ (hidden, ignored and symlinked directories skipped) passes `env=` built by scripts/child_env.py `build_child_env`, directly or through a name every binding of which is a sole-target helper call and which is afterwards only read, in any scope; names resolve with Python's scope rules, so a binding in another scope never hides a spawn and a spawn name bound two ways in one scope is an error; a spawn API referenced without a call is an error; `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `pty.spawn` and `subprocess.getoutput` are errors outright, with no waiver; a helper call carrying `os.environ` or `os.getenv`, directly or through a name it reached in the module, is an error; config/project.json `child_env` is validated whenever a spawn exists. A spawn through a receiver the AST cannot resolve, and a parent value crossing a function parameter, are not seen, by design, and correct code is never an error. Keel's own tree is clean and the detector sees every spawn site in it.
"""

import io
import json
import re
import sys
import tokenize
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_HEADER = '"""\ntitle: x\nsummary: x\n"""\n'
_GOOD_MANIFEST = {
    "child_env": {
        "names": ["PATH", "HOME"],
        "prefixes": ["LC_"],
        "repo_context_names": ["GIT_DIR"],
    },
    "make_targets": {"unattended_vars": ["CI", "RALPH"], "gate_vars": ["PY"]},
}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty root with the gate's module state isolated (as test_check_w)."""
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    return tmp_path


def _manifest(root, manifest):
    (root / "config" / "project.json").write_text(json.dumps(manifest), "utf-8")


def _module(root, relpath, body):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HEADER + body, encoding="utf-8")


def _findings(body):
    return cs.spawn_findings(_HEADER + body, "scripts/x.py")


def _line_of(body, needle):
    """1-based line in `_HEADER + body` of the first line containing needle."""
    for i, line in enumerate((_HEADER + body).splitlines(), 1):
        if needle in line:
            return i
    raise AssertionError(needle)


# --- a spawn without env= -----------------------------------------------------------

_BARE = [
    ("run", "import subprocess\nsubprocess.run(['true'])\n"),
    ("Popen", "import subprocess\nsubprocess.Popen(['true'])\n"),
    ("call", "import subprocess\nsubprocess.call(['true'])\n"),
    ("check_call", "import subprocess\nsubprocess.check_call(['true'])\n"),
    ("check_output", "import subprocess\nsubprocess.check_output(['true'])\n"),
    ("alias", "import subprocess as sp\nsp.run(['true'])\n"),
    ("from-import", "from subprocess import run as r\nr(['true'])\n"),
    (
        "asyncio",
        "import asyncio\nasync def f():\n    await asyncio.create_subprocess_exec('true')\n",
    ),
    (
        "asyncio-shell",
        "import asyncio\nasync def f():\n    await asyncio.create_subprocess_shell('true')\n",
    ),
]


@pytest.mark.parametrize("body", [b for _, b in _BARE], ids=[i for i, _ in _BARE])
def test_a_spawn_without_env_is_an_error(repo, body):
    msgs = _findings(body)
    lineno = len((_HEADER + body).splitlines())  # the spawn is the last line
    assert len(msgs) == 1, msgs
    assert msgs[0].startswith("scripts/x.py:%d:" % lineno) and "env=" in msgs[0], msgs
    _manifest(repo, _GOOD_MANIFEST)
    _module(repo, "scripts/x.py", body)
    cs.check_X()
    assert cs.errors == msgs, cs.errors


# --- env= built by the helper ---------------------------------------------------------

_GOOD = [
    (
        "direct",
        "import subprocess\nfrom child_env import build_child_env\n"
        "subprocess.run(['true'], env=build_child_env())\n",
    ),
    (
        "bound-name",
        "import subprocess\nfrom child_env import build_child_env\n"
        "def f():\n    env = build_child_env(extra={'RALPH': '1'})\n"
        "    return subprocess.run(['true'], env=env)\n",
    ),
    (
        "module-attr",
        "import subprocess\nimport child_env\n"
        "subprocess.run(['true'], env=child_env.build_child_env())\n",
    ),
    (
        "scripts-package",
        "import subprocess\nfrom scripts.child_env import build_child_env\n"
        "subprocess.run(['true'], env=build_child_env(credentials_for='a'))\n",
    ),
    (
        "from-scripts-import-module",
        "import subprocess\nfrom scripts import child_env\n"
        "subprocess.run(['true'], env=child_env.build_child_env())\n",
    ),
    (
        "dotted-import",
        "import subprocess\nimport scripts.child_env\n"
        "subprocess.run(['true'], env=scripts.child_env.build_child_env())\n",
    ),
    (
        "asyncio",
        "import asyncio\nfrom child_env import build_child_env\n"
        "async def f():\n"
        "    await asyncio.create_subprocess_exec('true', env=build_child_env())\n",
    ),
]


@pytest.mark.parametrize("body", [b for _, b in _GOOD], ids=[i for i, _ in _GOOD])
def test_env_built_by_the_helper_passes(body):
    assert _findings(body) == []


# --- env= from anywhere else --------------------------------------------------------

_IMPORTS = "import os\nimport subprocess\nfrom child_env import build_child_env\n"
_NOT_HELPER = [
    ("os.environ", "subprocess.run(['true'], env=os.environ)\n"),
    ("dict-of-environ", "subprocess.run(['true'], env=dict(os.environ))\n"),
    ("literal", "subprocess.run(['true'], env={'PATH': p})\n"),
    ("environ-copy", "subprocess.run(['true'], env=os.environ.copy())\n"),
    (
        "local-lookalike",
        "def build_child_env():\n    return dict(os.environ)\n"
        "subprocess.run(['true'], env=build_child_env())\n",
    ),
    ("parameter", "def f(env):\n    subprocess.run(['true'], env=env)\n"),
    (
        "two-bindings",
        "def f(x):\n    env = build_child_env()\n    if x:\n        env = os.environ\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "update",
        "def f():\n    env = build_child_env()\n    env.update(os.environ)\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "subscript",
        "def f():\n    env = build_child_env()\n    env['K'] = 'v'\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "setdefault",
        "def f():\n    env = build_child_env()\n    env.setdefault('K', 'v')\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "augmented",
        "def f():\n    env = build_child_env()\n    env |= {'K': 'v'}\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    ("kwargs", "def f(**kw):\n    subprocess.run(['true'], **kw)\n"),
    (
        "parameter-default-rebound",
        "def f(env=None):\n    if not env:\n        env = build_child_env()\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "chained-assignment",
        "def f():\n    a = env = build_child_env()\n    a.update(os.environ)\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "mutated-in-a-nested-def",
        "def f():\n    env = build_child_env()\n    def widen():\n"
        "        env.update(os.environ)\n    widen()\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "mutated-in-a-lambda",
        "def f():\n    env = build_child_env()\n"
        "    widen = lambda: env.update(os.environ)\n    widen()\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "mutated-through-an-alias",
        "def f():\n    env = build_child_env()\n    e2 = env\n"
        "    e2.update(os.environ)\n    subprocess.run(['true'], env=env)\n",
    ),
    (
        "mutated-through-the-unbound-method",
        "def f():\n    env = build_child_env()\n    dict.update(env, os.environ)\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "handed-to-a-function",
        "def f(widen):\n    env = build_child_env()\n    widen(env)\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
    (
        "nonlocal-rebind",
        "def f():\n    env = build_child_env()\n    def g():\n        nonlocal env\n"
        "        env = dict(os.environ)\n    g()\n"
        "    subprocess.run(['true'], env=env)\n",
    ),
]


@pytest.mark.parametrize(
    "body", [b for _, b in _NOT_HELPER], ids=[i for i, _ in _NOT_HELPER]
)
def test_env_not_from_the_helper_is_an_error(body):
    msgs = _findings(_IMPORTS + body)
    lineno = _line_of(_IMPORTS + body, "subprocess.run(")
    assert len(msgs) == 1, msgs
    assert msgs[0].startswith("scripts/x.py:%d:" % lineno), msgs


# --- spawns that cannot take an environment ---------------------------------------

_NO_ENV = [
    ("os.system", "import os\nos.system('true')\n"),
    ("os.popen", "import os\nos.popen('true')\n"),
    ("os.execv", "import os\nos.execv('/bin/true', ['true'])\n"),
    ("os.execvpe", "import os\nos.execvpe('true', ['true'], {})\n"),
    ("os.spawnl", "import os\nos.spawnl(os.P_WAIT, '/bin/true', 'true')\n"),
    ("os.posix_spawn", "import os\nos.posix_spawn('/bin/true', ['true'], {})\n"),
    ("from-os", "from os import system\nsystem('true')\n"),
    ("pty.spawn", "import pty\npty.spawn(['true'])\n"),
    ("getoutput", "import subprocess\nsubprocess.getoutput('true')\n"),
    ("getstatusoutput", "import subprocess\nsubprocess.getstatusoutput('true')\n"),
]


@pytest.mark.parametrize("body", [b for _, b in _NO_ENV], ids=[i for i, _ in _NO_ENV])
def test_a_spawn_that_cannot_take_an_environment_is_an_error(body):
    msgs = _findings(body)
    assert len(msgs) == 1, msgs
    assert "cannot take an allowlisted environment" in msgs[0], msgs
    lineno = len((_HEADER + body).splitlines())
    assert msgs[0].startswith("scripts/x.py:%d:" % lineno), msgs
    # No waiver: a reason-carrying pragma does not silence it.
    waived = body.rstrip("\n") + "  # practice-ok: needs the whole environment\n"
    assert len(_findings(waived)) == 1


# --- the helper handed the parent's environment ------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        "build_child_env(extra=dict(os.environ))",
        "build_child_env(extra={'K': os.environ['K']})",
        "build_child_env(extra={'K': os.getenv('K')})",
    ],
)
def test_the_helper_handed_the_parent_environment_is_an_error(call):
    body = _IMPORTS + "subprocess.run(['true'], env=%s)\n" % call
    msgs = _findings(body)
    assert len(msgs) == 1, msgs
    assert "child_env.names" in msgs[0] and "models.credential_env" in msgs[0], msgs


@pytest.mark.parametrize(
    "body",
    [
        "parent = dict(os.environ)\n",
        "parent = os.environ\n",
        "parent = {}\nparent.update(os.environ)\n",
        "parent = {}\nparent['K'] = os.getenv('K')\n",
        "base = os.environ.copy()\nparent = {k: base[k] for k in base}\n",
        "parent = {}\nfor k, v in os.environ.items():\n    parent[k] = v\n",
        "from os import environ\nparent = dict(environ)\n",
    ],
    ids=[
        "dict-of",
        "alias",
        "update",
        "subscript-store",
        "two-hops",
        "loop",
        "from-os-import-environ",
    ],
)
def test_the_parent_environment_reaching_the_helper_through_a_name_is_an_error(body):
    """The leak scan follows a value through the names it is bound to, in every
    scope of the module, not only the helper call's own syntax."""
    for scope in ("", "def f():\n"):
        indent = "    " if scope else ""
        src = (
            _IMPORTS
            + scope
            + "".join(
                indent + line + "\n"
                for line in (
                    body + "subprocess.run(['true'], env=build_child_env(extra=parent))"
                ).splitlines()
            )
        )
        msgs = _findings(src)
        assert len(msgs) == 1, (src, msgs)
        assert "build_child_env is handed" in msgs[0] and "parent" in msgs[0], msgs


def test_a_value_unrelated_to_the_parent_environment_reaches_the_helper_cleanly():
    body = _IMPORTS + (
        "def f(flag):\n    extra = {'RALPH': '1'}\n    if flag:\n"
        "        extra['CI'] = 'true'\n"
        "    home = os.environ.get('HOME')\n"
        "    subprocess.run(['true'], env=build_child_env(extra=extra))\n"
        # `seen[key] = <parent value>` writes into seen, never into key.
        "    seen = {}\n    key = 'RALPH'\n    seen[key] = os.environ.get(key)\n"
        "    subprocess.run(['true'], env=build_child_env(extra={key: '1'}))\n"
    )
    assert _findings(body) == []


# --- the stated under-report -------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "class A:\n    def f(self, cmd):\n        return self.runner(cmd)\n",
        "x = str.run\n",
        "run(['true'])\n",
        "obj.subprocess.run(['true'])\n",
        "import subprocess\n",
        "import subprocess\nsubprocess.PIPE\nsubprocess.TimeoutExpired\n",
        "import subprocess\ndef f():\n    sp = subprocess\n    sp.run(['true'])\n",
        "import os\nfrom scripts.child_env import build_child_env\n"
        "def f(parent):\n    return build_child_env(extra=parent)\n"
        "def g():\n    return f(dict(os.environ))\n",
    ],
    ids=[
        "self-runner",
        "str-run",
        "unimported-run",
        "unbound-obj",
        "import-only",
        "attrs",
        "module-alias-receiver",
        "parent-env-across-a-parameter",
    ],
)
def test_unresolvable_receivers_and_lookalikes_are_not_findings(body):
    assert _findings(body) == []


# --- names resolve per scope, as Python resolves them --------------------------------

_SHADOW_ELSEWHERE = [
    (
        "loop-variable-in-another-function",
        "from subprocess import run\ndef main():\n    return run(['true'])\n"
        "def summarise(runs):\n    for run in runs:\n        print(run)\n",
        "return run(",
    ),
    (
        "parameter-in-another-function",
        "import os\ndef main():\n    os.system('true')\n"
        "def helper(os=None):\n    return os\n",
        "os.system(",
    ),
    (
        "method-of-the-same-name",
        "from subprocess import run\nclass Job:\n    def run(self):\n        return 1\n"
        "def main():\n    return run(['true'])\n",
        "return run(",
    ),
    (
        "comprehension-variable",
        "import subprocess\ndef main(xs):\n"
        "    names = [subprocess for subprocess in xs]\n"
        "    return subprocess.run(['true'])\n",
        "subprocess.run(",
    ),
    (
        "local-import-in-a-function",
        "def main():\n    import subprocess\n    return subprocess.run(['true'])\n"
        "subprocess = None\n",
        "subprocess.run(",
    ),
]


@pytest.mark.parametrize(
    "body,needle",
    [(b, n) for _, b, n in _SHADOW_ELSEWHERE],
    ids=[i for i, _, _ in _SHADOW_ELSEWHERE],
)
def test_a_name_bound_in_another_scope_does_not_hide_a_spawn(body, needle):
    msgs = _findings(body)
    assert len(msgs) == 1, msgs
    assert msgs[0].startswith("scripts/x.py:%d:" % _line_of(body, needle)), msgs


@pytest.mark.parametrize(
    "body",
    [
        "from subprocess import run\ndef f(run):\n    return run(['true'])\n",
        "import subprocess\ndef f():\n    subprocess = object()\n"
        "    return subprocess.run(['true'])\n",
        "from subprocess import run\ndef f(rs):\n"
        "    return [run(['true']) for run in rs]\n",
    ],
    ids=["parameter", "local-assignment", "comprehension-variable"],
)
def test_a_spawn_name_shadowed_in_its_own_scope_is_not_a_finding(body):
    assert _findings(body) == []


@pytest.mark.parametrize(
    "body",
    [
        "from subprocess import run\nfor run in []:\n    pass\nrun(['true'])\n",
        "try:\n    from subprocess import run\nexcept ImportError:\n"
        "    def run(cmd):\n        return cmd\nrun(['true'])\n",
        "import os\ndef f():\n    global os\n    os = None\nos.system('true')\n",
    ],
    ids=["same-scope-loop", "fallback-def", "global-rebind"],
)
def test_a_spawn_name_bound_two_ways_in_one_scope_is_an_error(body):
    """The check cannot tell which binding a call means, so it fails closed."""
    msgs = _findings(body)
    assert len(msgs) == 1, msgs
    assert "bound both" in msgs[0], msgs
    assert msgs[0].startswith("scripts/x.py:%d:" % len((_HEADER + body).splitlines()))


@pytest.mark.parametrize(
    "body",
    [
        "runner = subprocess.run\nrunner(['true'])\n",
        "import functools\nrunner = functools.partial(subprocess.Popen, shell=False)\n",
        "def f(runner=subprocess.check_output):\n    return runner(['true'])\n",
        "from os import system\nhooks = [system]\n",
    ],
    ids=["assigned", "partial", "default", "in-a-list"],
)
def test_a_spawn_api_referenced_without_a_call_is_an_error(body):
    """A reference starts a child where this check cannot read its env=."""
    msgs = _findings(_IMPORTS + body)
    assert len(msgs) == 1, msgs
    assert "referenced, not called" in msgs[0], msgs


def test_type_uses_of_popen_are_not_findings():
    body = _IMPORTS + (
        "def f(p: subprocess.Popen) -> subprocess.Popen:\n"
        "    q: subprocess.Popen = p\n"
        "    assert isinstance(q, subprocess.Popen)\n    return q\n"
    )
    assert _findings(body) == []


def test_reading_the_built_environment_is_allowed():
    body = _IMPORTS + (
        "def f():\n    env = build_child_env()\n"
        "    if 'PATH' in env and env.get('HOME') and env['PATH']:\n"
        "        return subprocess.run(['true'], env=env)\n"
        "    def g():\n        env = {}\n        env.update(os.environ)\n"
        "        return env\n"
    )
    assert _findings(body) == []


def test_a_syntax_error_is_not_this_checks_to_report():
    assert cs.spawn_findings("def (:\n", "scripts/x.py") == []


# --- the walk --------------------------------------------------------------------------


def test_check_x_scans_writer_roots_and_skips_tests(repo):
    _manifest(repo, _GOOD_MANIFEST)
    bare = "import subprocess\nsubprocess.run(['true'])\n"
    _module(repo, "scripts/a.py", bare)
    _module(repo, "models/b.py", bare)
    _module(repo, "tests/c.py", bare)
    cs.check_X()
    assert len(cs.errors) == 2, cs.errors
    assert cs.errors[0].startswith("models/b.py:") and cs.errors[1].startswith(
        "scripts/a.py:"
    ), cs.errors


def test_check_x_scans_every_top_level_code_home_and_skips_tests(repo):
    """evals/ (the model and agent harness), ops/, a declared extra top-level
    directory and a root-level module are code that can start a child too."""
    _manifest(repo, dict(_GOOD_MANIFEST, structure={"extra_toplevel": ["tools"]}))
    bare = "import subprocess\nsubprocess.run(['true'])\n"
    for path in ("evals/a.py", "ops/b.py", "tools/c.py", "d.py", "tests/e.py"):
        _module(repo, path, bare)
    _module(repo, "stray/f.py", bare)  # undeclared: check_B's to report
    cs.check_X()
    assert sorted(e.split(":")[0] for e in cs.errors) == [
        "d.py",
        "evals/a.py",
        "ops/b.py",
        "stray/f.py",
        "tools/c.py",
    ], cs.errors


def test_check_x_does_not_read_through_a_symlinked_top_level_dir(
    repo, tmp_path_factory
):
    _manifest(repo, _GOOD_MANIFEST)
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "a.py").write_text(
        "import subprocess\nsubprocess.run(['true'])\n", encoding="utf-8"
    )
    (repo / "linked").symlink_to(elsewhere)
    cs.check_X()
    assert cs.errors == [], cs.errors


def test_the_literal_reader_handles_the_old_and_new_string_node():
    """The gate runs under 3.6 (ast.Str) and 3.8+ (ast.Constant); check_X reads
    import names through ast nodes that are not literals, but a check that reads
    one must take both (as check_V does)."""
    import ast

    assert cs._literal_str(ast.parse("'x'").body[0].value) == "x"


# --- the policy ---------------------------------------------------------------------


def test_a_malformed_policy_is_reported_with_the_manifest_prefix(repo):
    _manifest(
        repo,
        dict(
            _GOOD_MANIFEST,
            child_env={
                "names": ["MAKEFLAGS"],
                "prefixes": [],
                "repo_context_names": ["GIT_DIR"],
            },
        ),
    )
    _module(
        repo,
        "scripts/a.py",
        "import subprocess\nfrom child_env import build_child_env\n"
        "subprocess.run(['true'], env=build_child_env())\n",
    )
    cs.check_X()
    assert len(cs.errors) == 1, cs.errors
    assert (
        cs.errors[0].startswith("config/project.json: ")
        and "MAKEFLAGS" in (cs.errors[0])
    ), cs.errors


def test_a_manifest_allowlisting_a_repository_variable_fails_check_x_with_the_fix(
    repo,
):
    """GIT_DIR in child_env.names would hand every child the repository its
    parent was started in. The gate says which key marks it and what to do."""
    child = dict(_GOOD_MANIFEST["child_env"], names=["PATH", "HOME", "GIT_DIR"])
    _manifest(repo, dict(_GOOD_MANIFEST, child_env=child))
    _module(
        repo,
        "scripts/a.py",
        "import subprocess\nfrom child_env import build_child_env\n"
        "subprocess.run(['true'], env=build_child_env())\n",
    )
    cs.check_X()
    assert len(cs.errors) == 1, cs.errors
    msg = cs.errors[0]
    assert msg.startswith("config/project.json: child_env.names lists GIT_DIR"), msg
    assert "child_env.repo_context_names" in msg, msg
    assert "build_child_env(repo_context=True)" in msg, msg
    # The same tree with GIT_DIR gone is clean: the guard is not vacuous.
    cs.errors[:] = []
    cs._CONFIG_READ.clear()  # one gate run reads the manifest once; this is a second
    _manifest(repo, _GOOD_MANIFEST)
    cs.check_X()
    assert cs.errors == [], cs.errors


def test_a_missing_block_with_a_spawn_site_is_an_error(repo):
    _manifest(repo, {"name": "x"})
    _module(
        repo,
        "scripts/a.py",
        "import subprocess\nfrom child_env import build_child_env\n"
        "subprocess.run(['true'], env=build_child_env())\n",
    )
    cs.check_X()
    assert len(cs.errors) == 1 and "no child_env block" in cs.errors[0], cs.errors


def test_no_spawn_site_and_no_block_is_silent(repo):
    _manifest(repo, {"name": "x"})
    _module(repo, "scripts/a.py", "x = 1\n")
    cs.check_X()
    assert cs.errors == [] and cs.warnings == []


def test_an_unreadable_manifest_is_not_reported_twice(repo):
    (repo / "config" / "project.json").write_text("{nope", encoding="utf-8")
    _module(repo, "scripts/a.py", "import subprocess\nsubprocess.run(['x'])\n")
    cs.check_X()
    cs.check_X()
    manifest_errs = [e for e in cs.errors if e.startswith("config/project.json")]
    assert len(manifest_errs) == 1, cs.errors


# --- keel itself -----------------------------------------------------------------------


def _isolate(monkeypatch, root):
    monkeypatch.setattr(cs, "ROOT", str(root))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())


def _code_only(source):
    """source with its strings and comments blanked, so the text-level oracle
    below counts calls, not an error message that quotes one."""
    out = []
    prev_op = True
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT) or not tok.string.strip():
            continue
        is_op = tok.type == tokenize.OP
        out.append(tok.string if (is_op or prev_op) else " " + tok.string)
        prev_op = is_op
    return "".join(out)


def test_keel_itself_is_clean_and_not_vacuous(monkeypatch):
    _isolate(monkeypatch, _ROOT)
    cs.check_X()
    assert cs.errors == [], cs.errors
    calls = re.compile(r"\bsubprocess\.(?:run|Popen|call|check_call|check_output)\(")
    importers = {}
    for wroot in cs.WRITER_ROOTS:
        base = _ROOT / wroot
        if not base.is_dir():
            continue
        for dirpath, _, filenames in cs.walk(str(base)):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                path = Path(dirpath) / f
                text = path.read_text(encoding="utf-8-sig")
                code = _code_only(text)
                if calls.search(code):
                    importers[str(path.relative_to(_ROOT))] = (
                        len(calls.findall(code)),
                        len(cs.spawn_sites(text)),
                    )
    # The eleven modules that spawn today, so a walker that finds none fails.
    assert len(importers) >= 10, importers
    blind = sorted(p for p, (want, seen) in importers.items() if seen < want)
    assert blind == [], importers
