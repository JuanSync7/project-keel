"""
title: Integration — every copier job refuses over each conflicted file it reads
kind: tests
layer: n/a
summary: Every job copier.yml runs on a project (each `_tasks` entry and each `_migrations` command that runs a script, parsed from copier.yml, never listed here) is run in a project generated from this working tree with one conflict hunk injected into each fixed project file its modules declare reading (`PROJECT_READS`, collected by scripts/jobs/conflict_guard.py along the job's import closure): it exits 2 before acting, with the one refusal line `read_refusals` parses back to that job, that file and the hunk's line, and, for a migration (run with `--finish-with`), the command that finishes the update; never a traceback or a JSON parse error, and no other file changes. A static scan proves the declarations complete: every string literal, all-literal or trailing-literal `os.path.join`, and `/` chain in a closure module that names a file the template ships is declared in that module's `PROJECT_READS` or exempted with a reason in `PROJECT_PATHS_NOT_READ`, and a `PROJECT_READS` entry no literal supports is stale. Removing child_env's declaration reds that scan and stops the job's refusal (child_env's own message still names the conflict, never the parse error). The guard refuses only over files a job reads: no job's closure holds a module that declares reads while every importer of it takes only literal constants from it (restamp_docs, importing check_structure for two constants, was refused over a conflicted Makefile it never opens), and a fault-injected module taken for a constant reds that check. An open trace (`sys.addaudithook`) of each job run in full proves the scan sees every read: each file a job opens under the project is a closure module, its bytecode, a declared read, or a Markdown worklist document. Template-only: it reads copier.yml, which no generated project has.
"""

import ast
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git
import optional_deps

copier = optional_deps.importorskip("copier", extra="template")
yaml = optional_deps.importorskip("yaml", extra="template")
jinja2_sandbox = optional_deps.importorskip("jinja2.sandbox", extra="template")
jinja2 = optional_deps.importorskip("jinja2", extra="template")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
sys.path.insert(0, str(_ROOT / "scripts"))

import child_env  # noqa: E402
import conflict_guard  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]

# The module that starts every child: a job whose closure holds it reads the
# manifest, so its declared reads cannot be empty.
_CHILD_ENV = Path(child_env.__file__).resolve().relative_to(_ROOT).as_posix()


# --- the jobs copier.yml runs -----------------------------------------------


def _copier_yml():
    with open(str(_ROOT / "copier.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _script_jobs():
    """(id, kind, raw argv) for each copier.yml `_tasks` entry and `_migrations`
    command that hands a script to an interpreter, in copier's order. A string
    command (an `rm`) reads no project file, so it is no job of this test."""
    if not (_ROOT / "copier.yml").is_file():
        return []
    data = _copier_yml()
    entries = [("task", cmd) for cmd in data.get("_tasks") or []]
    entries += [("migration", m["command"]) for m in data.get("_migrations") or []]
    jobs = []
    for n, (kind, command) in enumerate(entries):
        if not isinstance(command, list):
            continue
        scripts = [w for w in command if str(w).endswith(".py")]
        assert len(scripts) == 1, "a list job names one script: %r" % command
        stem = posixpath.splitext(posixpath.basename(scripts[0]))[0]
        jobs.append(("%s-%d-%s" % (kind, n, stem), kind, command))
    return jobs


_JOBS = _script_jobs()


def _answers(project):
    with open(str(project / ".copier-answers.yml"), encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _render(command, project):
    """The argv copier runs for *command* in *project*: every word rendered
    with copier's variables (the interpreter, this template, `after`, HEAD as
    both versions) and the project's answers; an unknown variable fails."""
    env = jinja2_sandbox.SandboxedEnvironment(undefined=jinja2.StrictUndefined)
    context = dict(
        _answers(project),
        _copier_python=sys.executable,
        _copier_conf={"src_path": str(_ROOT)},
        _stage="after",
        _version_from="HEAD",
        _version_to="HEAD",
    )
    return [env.from_string(str(word)).render(**context) for word in command]


def _entry(project, argv):
    (script,) = [w for w in argv if w.endswith(".py")]
    return project / script


def _search(entry):
    # Each job hands the guard its own directory, then scripts/ (the
    # `search_path=(_JOBS, _SCRIPTS)` every job in scripts/jobs/ passes).
    return [str(entry.parent), str(entry.parent.parent)]


def _closure(project, entry):
    return conflict_guard.job_closure(str(entry), str(project), _search(entry))


def _reads(closure):
    """Every read the modules of *closure* declare, sorted."""
    out = set()
    for _rel, path in closure:
        with open(path, encoding="utf-8") as fh:
            out.update(conflict_guard.declared_reads(ast.parse(fh.read(), path), path))
    return sorted(out)


# --- a generated project ------------------------------------------------------


def _git(project, env, *argv):
    proc = subprocess.run(
        ["git"] + list(argv),
        cwd=str(project),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """(project, env): a project copier generates from this working tree,
    committed, and the allowlisted hermetic environment its jobs run under."""
    base = tmp_path_factory.mktemp("job-refusal")
    work = base / "gitwork"
    work.mkdir()
    project = base / "project"
    copier.run_copy(
        str(_ROOT),
        str(project),
        defaults=True,
        vcs_ref="HEAD",
        unsafe=True,
        quiet=True,
    )
    # The uncommitted guard is the one under test, not HEAD's.
    guard = Path(conflict_guard.__file__)
    assert (project / "scripts" / "jobs" / guard.name).read_bytes() == (
        guard.read_bytes()
    ), "the project was not generated from this working tree"
    env = build_child_env(
        extra=dict(hermetic_git.git_env_vars(work), GIT_CEILING_DIRECTORIES=str(base))
    )
    _git(project, env, "init", "-q", "-b", "main")
    _git(project, env, "add", "-A")
    _git(project, env, "commit", "-qm", "generated")
    return project, env


def _status(project, env):
    return _git(project, env, "status", "--porcelain=v1", "-z", "--untracked-files=all")


_OPEN, _SPLIT, _CLOSE = "<" * 7, "=" * 7, ">" * 7
_HUNK_AT = 2


def _inject(path):
    """Put a three-line hunk at line _HUNK_AT of *path*; returns the old bytes."""
    old = path.read_bytes()
    lines = old.split(b"\n")
    hunk = ("%s ours\n%s\n%s theirs" % (_OPEN, _SPLIT, _CLOSE)).encode("ascii")
    path.write_bytes(b"\n".join(lines[: _HUNK_AT - 1] + [hunk] + lines[_HUNK_AT - 1 :]))
    return old


def _run(argv, project, env):
    return subprocess.run(
        argv,
        cwd=str(project),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def test_copier_yml_runs_at_least_one_script_job():
    """A pass over zero jobs proves nothing."""
    assert _JOBS, "copier.yml lists no `_tasks` or `_migrations` script job"
    assert any(kind == "migration" for _id, kind, _cmd in _JOBS)


@pytest.mark.parametrize("job", _JOBS, ids=[j[0] for j in _JOBS])
def test_every_job_refuses_over_each_data_file_it_reads(generated, job):
    """Each declared read the job's closure reaches, conflicted alone: exit 2,
    one refusal naming that file at that line, the finish command for a
    migration, no traceback or JSON error, and no other file touched."""
    project, env = generated
    _id, kind, command = job
    argv = _render(command, project)
    entry = _entry(project, argv)
    stem = entry.stem
    closure = _closure(project, entry)
    reads = _reads(closure)
    if any(rel == _CHILD_ENV for rel, _path in closure):
        assert reads, "%s starts children through %s but declares no read" % (
            stem,
            _CHILD_ENV,
        )
    present = [rel for rel in reads if (project / rel).is_file()]
    assert present or not reads, "%s: no declared read exists to conflict" % stem
    for rel in present:
        target = project / rel
        old = _inject(target)
        try:
            before = _status(project, env)
            proc = _run(argv, project, env)
            after = _status(project, env)
        finally:
            target.write_bytes(old)
        said = proc.stdout + proc.stderr
        assert proc.returncode == 2, "%s over %s: %s" % (stem, rel, said)
        assert "Traceback" not in said and "Expecting" not in said, said
        found = conflict_guard.read_refusals(proc.stderr)
        assert len(found) == 1, "%s over %s: %s" % (stem, rel, proc.stderr)
        job_name, files, rerun = found[0]
        assert (job_name, files) == (stem, [(rel, _HUNK_AT)]), proc.stderr
        if kind == "migration":
            assert rerun == conflict_guard.finish_rerun(sys.executable), rerun
        else:
            assert conflict_guard.FINISH_SCRIPT not in rerun, rerun
        assert after == before, "%s acted before refusing over %s" % (stem, rel)


# --- the declarations are complete ---------------------------------------------


def _shipped(project):
    """The root-relative files a generated project can hold: this template's
    listed files (a `.jinja` twin counted as its rendered name) and the files
    the generated project has."""
    listed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=str(_ROOT),
        env=build_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert listed.returncode == 0, listed.stderr
    out = {rel.removesuffix(".jinja") for rel in listed.stdout.split("\0") if rel}
    for dirpath, dirnames, filenames in os.walk(str(project)):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), str(project))
            out.add(rel.replace(os.sep, "/"))
    return out


def _string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _normal(text):
    """*text* as a root-relative POSIX path, or None when it cannot be one."""
    if not text or "\n" in text or text.startswith("/"):
        return None
    path = posixpath.normpath(text)
    return None if path.startswith("..") else path


def _join_tail(args):
    """The literal tail of a join's arguments, joined; None when not two or
    more literals (a lone literal is already collected as a constant)."""
    parts = []
    for arg in reversed(args):
        value = _string(arg)
        if value is None:
            break
        parts.insert(0, value)
    return "/".join(parts) if len(parts) > 1 else None


def _div_tail(node):
    parts = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        value = _string(node.right)
        if value is None:
            return "/".join(parts) if len(parts) > 1 else None
        parts.insert(0, value)
        node = node.left
    value = _string(node)
    if value is not None:
        parts.insert(0, value)
    return "/".join(parts) if len(parts) > 1 else None


def _declarations():
    # Read when called, so a guard without the names fails a test, not collection.
    return (conflict_guard.READS_NAME, conflict_guard.NOT_READ_NAME)


def _declaration_nodes(tree):
    """The ids of every node inside a module-level declaration, which names a
    path but is the claim under test, never its support."""
    names = _declarations()
    inside = set()
    for stmt in tree.body:
        targets = []
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        if any(isinstance(t, ast.Name) and t.id in names for t in targets):
            inside.update(id(n) for n in ast.walk(stmt))
    return inside


def _path_literals(tree):
    """(line, path) for every string constant, literal-tailed `join(...)` and
    literal-tailed `/` chain outside the declarations."""
    skip = _declaration_nodes(tree)
    out = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        text = _string(node)
        if text is None and isinstance(node, ast.Call):
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if name == "join":
                text = _join_tail(node.args)
        if text is None and isinstance(node, ast.BinOp):
            text = _div_tail(node)
        path = _normal(text) if text is not None else None
        if path is not None:
            out.append((node.lineno, path))
    return out


def _not_read(tree, path):
    """The module's PROJECT_PATHS_NOT_READ as {path: reason}; a shape that is
    not a literal tuple of (path, reason) string pairs fails the test."""
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == conflict_guard.NOT_READ_NAME
            for t in stmt.targets
        ):
            value = ast.literal_eval(stmt.value)
            assert isinstance(value, tuple) and all(
                isinstance(p, tuple)
                and len(p) == 2
                and all(isinstance(x, str) for x in p)
                for p in value
            ), "%s:%d: %s must be a tuple of (path, reason) pairs" % (
                path,
                stmt.lineno,
                conflict_guard.NOT_READ_NAME,
            )
            return dict(value)
    return {}


def literal_findings(closure, shipped):
    """What makes the declarations of the modules in *closure* incomplete: a
    literal naming a shipped file neither declared nor exempted, an exemption
    with no reason, and a declared read no literal in its module supports."""
    findings = []
    for rel, path in closure:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), path)
        reads = set(conflict_guard.declared_reads(tree, path))
        exempt = _not_read(tree, rel)
        literals = _path_literals(tree)
        for lineno, literal in literals:
            if literal in shipped and literal not in reads and literal not in exempt:
                findings.append(
                    "%s:%d: %r names a shipped file; declare it in %s or exempt "
                    "it in %s with a reason"
                    % (rel, lineno, literal, _declarations()[0], _declarations()[1])
                )
        for literal, reason in sorted(exempt.items()):
            if not reason.strip():
                findings.append("%s: %r is exempted with no reason" % (rel, literal))
        supported = {literal for _lineno, literal in literals}
        findings.extend(
            "%s: %s entry %r is stale: no literal in the module names it"
            % (rel, _declarations()[0], literal)
            for literal in sorted(reads - supported)
        )
    return findings


def _all_closures(project):
    """{job id: closure} for every script job, in the generated project."""
    return {
        job_id: _closure(project, _entry(project, _render(command, project)))
        for job_id, _kind, command in _JOBS
    }


def test_every_fixed_path_literal_a_job_can_reach_is_declared(generated):
    project, _env = generated
    closures = _all_closures(project)
    assert closures and all(closures.values()), closures
    modules = sorted({pair for closure in closures.values() for pair in closure})
    shipped = _shipped(project)
    assert _CHILD_ENV in shipped
    assert literal_findings(modules, shipped) == []
    assert _reads(modules), "no module in any job's closure declares a read"


def _strip_declaration(path, name):
    """Remove the module-level assignment to *name* from *path* (by its AST
    line span); fails when there is none to remove."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in stmt.targets
        ):
            lines = text.splitlines(True)
            del lines[stmt.lineno - 1 : stmt.end_lineno]
            path.write_text("".join(lines), encoding="utf-8")
            return
    raise AssertionError("%s declares no %s" % (path, name))


def test_the_completeness_check_goes_red_when_a_declaration_is_removed(
    generated, tmp_path
):
    """Fault injection: child_env without its PROJECT_READS. The scan names
    the manifest literal it no longer covers, and the job whose closure
    declares the manifest only through child_env stops refusing with the
    guard's line; child_env's own message still names the conflict."""
    project, env = generated
    mutant = tmp_path / "project"
    shutil.copytree(str(project), str(mutant), symlinks=True)
    _strip_declaration(mutant / _CHILD_ENV, conflict_guard.READS_NAME)

    manifest = "config/project.json"
    picked = None
    for job_id, _kind, command in _JOBS:
        argv = _render(command, mutant)
        entry = _entry(mutant, argv)
        closure = _closure(mutant, entry)
        if any(rel == _CHILD_ENV for rel, _p in closure) and manifest not in _reads(
            closure
        ):
            picked = (job_id, argv, closure)
            break
    assert picked is not None, "no job declares the manifest only through child_env"
    job_id, argv, closure = picked

    findings = literal_findings(closure, _shipped(mutant))
    assert any(
        f.startswith(_CHILD_ENV + ":") and repr(manifest) in f for f in findings
    ), findings

    _inject(mutant / manifest)
    proc = _run(argv, mutant, env)
    assert conflict_guard.read_refusals(proc.stderr) == [], proc.stderr
    assert proc.returncode != 0, proc.stderr
    assert "merge-conflict" in proc.stderr and "Expecting" not in proc.stderr, (
        proc.stderr
    )


# --- the guard refuses only over files the job reads -----------------------------


def _literal_names(tree):
    """The module-level names *tree* binds to a literal (ast.literal_eval reads
    it): data an importer can take without running any code of the module."""
    out = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets, value = [stmt.target], stmt.value
        else:
            continue
        try:
            ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            continue
        out.update(t.id for t in targets if isinstance(t, ast.Name))
    return out


def _taken(tree, name):
    """What the module *tree* takes from the project module *name*: None when
    it does not import it, the set of attribute or imported names when that
    is all it does, and True when it uses the module any other way (passes
    it on, rebinds it, star-imports it): then any code of it may run."""
    bound = set()
    taken = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == name:
                    bound.add(alias.asname or name)
                    taken = taken if taken is not None else set()
        elif (
            isinstance(node, ast.ImportFrom) and not node.level and node.module == name
        ):
            taken = taken if taken is not None else set()
            for alias in node.names:
                if alias.name == "*":
                    return True
                taken.add(alias.name)
    if taken is None:
        return None
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in bound:
            up = parent.get(id(node))
            if not (isinstance(up, ast.Attribute) and up.value is node):
                return True
            if not isinstance(node.ctx, ast.Load):
                return True
            taken.add(up.attr)
    return taken


def uncalled_readers(closure, entry_rel):
    """The modules of *closure* (rel, path) that declare reads although no code
    of theirs can run in the job: every module that imports one takes only
    literal constants from it, or is such a module itself. The guard unions
    every declared read of the closure, so each read of such a module is a
    refusal over a file the job never reads. A module is reached by its
    stem, as the jobs' search path imports it; one imported any other way is
    never marked called, so the check errs towards a finding."""
    trees = {}
    for rel, path in closure:
        with open(path, encoding="utf-8") as fh:
            trees[rel] = ast.parse(fh.read(), path)
    stems = {rel: posixpath.splitext(posixpath.basename(rel))[0] for rel in trees}
    called = {entry_rel}
    grew = True
    while grew:
        grew = False
        for rel in sorted(trees):
            if rel in called:
                continue
            for importer in sorted(called):
                took = _taken(trees[importer], stems[rel])
                if took is True or (
                    took is not None and not took <= _literal_names(trees[rel])
                ):
                    called.add(rel)
                    grew = True
                    break
    findings = []
    for rel in sorted(trees):
        reads = conflict_guard.declared_reads(trees[rel], rel)
        if rel not in called and reads:
            findings.append(
                "%s: no code of it runs in the job (an importer takes only "
                "constants), yet the guard refuses the job over its reads %s"
                % (rel, ", ".join(reads))
            )
    return findings


def test_no_job_is_guarded_on_reads_of_a_module_it_never_calls(generated):
    """The guard unions the declared reads of every module a job imports, so a
    module kept for a constant hands the job its every read: restamp_docs
    imported check_structure for IGNORE_DIRS and the twin suffix, and a
    conflicted Makefile, which the restamp never opens, stopped the last
    migration of an update that used to finish (measured). No job's closure
    holds a reading module from which nothing but literals is taken."""
    project, _env = generated
    found = []
    for job_id, _kind, command in _JOBS:
        entry = _entry(project, _render(command, project))
        rel = entry.relative_to(project).as_posix()
        found.extend(
            "%s: %s" % (job_id, f)
            for f in uncalled_readers(_closure(project, entry), rel)
        )
    assert found == [], "\n".join(found)


def test_the_called_check_goes_red_on_a_module_taken_for_a_constant(tmp_path):
    """Fault injection: a module taken for a literal alone is a finding; the
    same module once a function of it is called is not."""
    lib = tmp_path / "lib.py"
    lib.write_text(
        'PROJECT_READS = ("Makefile",)\nCONST = {"a"}\n\n\n'
        'def read():\n    return open("Makefile").read()\n',
        encoding="utf-8",
    )
    entry = tmp_path / "job.py"
    entry.write_text("import lib\n\nX = lib.CONST\n", encoding="utf-8")

    def closure():
        return conflict_guard.job_closure(str(entry), str(tmp_path))

    found = uncalled_readers(closure(), "job.py")
    assert len(found) == 1 and found[0].startswith("lib.py:"), found
    entry.write_text("import lib\n\nX = lib.read()\n", encoding="utf-8")
    assert uncalled_readers(closure(), "job.py") == []
    entry.write_text("from lib import read\n", encoding="utf-8")
    assert uncalled_readers(closure(), "job.py") == []


# --- the trace: nothing the scan cannot see -------------------------------------

_DRIVER = """\
import json
import os
import runpy
import sys

out, entry = sys.argv[1], sys.argv[2]
opened = []
recording = [True]


def hook(event, args):
    if recording[0] and event == "open" and args and args[0] is not None:
        path = args[0]
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        if isinstance(path, str):
            opened.append(os.path.abspath(path))


sys.addaudithook(hook)
sys.argv = [entry] + sys.argv[3:]
code = 0
try:
    runpy.run_path(entry, run_name="__main__")
except SystemExit as stop:
    code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
recording[0] = False
with open(out, "w") as fh:
    json.dump({"code": code, "opened": opened}, fh)
"""

# A writer's atomic temporary beside the document it replaces: restamp_docs'
# mkstemp(prefix="." + name + ".", suffix=".tmp"), whose random part has no dot.
_TEMP = re.compile(r"^\.(?P<doc>.+)\.[^.]+\.tmp$")


def _worklist(rel):
    """A Markdown document a job enumerates at run time (or its template
    twin, or the temporary file it is replaced through)."""
    name = posixpath.basename(rel)
    temp = _TEMP.match(name)
    if temp:
        name = temp.group("doc")
    return name.endswith((".md", ".md.jinja"))


def _bytecode_of(rel, modules):
    head, name = posixpath.split(rel)
    if posixpath.basename(head) != "__pycache__" or not name.endswith(".pyc"):
        return False
    source = posixpath.join(posixpath.dirname(head), name.split(".", 1)[0] + ".py")
    return source in modules


@pytest.mark.parametrize("job", _JOBS, ids=[j[0] for j in _JOBS])
def test_every_file_a_job_opens_is_imported_declared_or_worklist(
    generated, tmp_path, job
):
    project, env = generated
    copy = tmp_path / "project"
    shutil.copytree(str(project), str(copy), symlinks=True)
    driver = tmp_path / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    out = tmp_path / "opened.json"
    _id, _kind, command = job
    argv = _render(command, copy)
    entry = _entry(copy, argv)
    closure = _closure(copy, entry)
    modules = {rel for rel, _path in closure}
    reads = set(_reads(closure))
    rest = argv[argv.index(str(entry.relative_to(copy))) + 1 :]
    proc = _run([sys.executable, str(driver), str(out), str(entry)] + rest, copy, env)
    assert proc.returncode == 0, proc.stderr
    trace = json.loads(out.read_text(encoding="utf-8"))
    assert trace["code"] == 0, proc.stderr
    root = os.path.realpath(str(copy))
    seen = set()
    for path in trace["opened"]:
        real = os.path.realpath(path)
        if not real.startswith(root + os.sep):
            continue
        seen.add(os.path.relpath(real, root).replace(os.sep, "/"))
    assert seen & modules, "the trace saw none of the job's own modules"
    unexplained = sorted(
        rel
        for rel in seen
        if rel not in modules
        and rel not in reads
        and not _bytecode_of(rel, modules)
        and not _worklist(rel)
    )
    assert unexplained == [], unexplained
