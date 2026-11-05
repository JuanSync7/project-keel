"""
title: Unit — refused manifests and actionable launcher errors
kind: tests
layer: n/a
summary: AST reachability independently discovers potential manifest readers across scripts, evals, API, MCP and agents. Cases prove either one-line refusals for eight input kinds or no manifest read; actual job guards are subprocesses. Every listed route pins its absent exit and messages to cf7ca3e. Stop hooks keep their hunk exception, imported readers raise, and launcher errors require a remedy.
"""

import ast
import importlib
import io
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts/jobs"))
sys.path.insert(0, str(_ROOT / "scripts/hooks"))

import config_loader  # noqa: E402
import launch  # noqa: E402
import on_stop_doc_review  # noqa: E402
import on_stop_triage  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit


def test_an_absent_manifest_declares_no_frontend(tmp_path):
    if not (_ROOT / "scripts/jobs/export_showcase_static.py").is_file():
        pytest.skip("this project declined the showcase exporter")
    import export_showcase_static

    assert export_showcase_static._declared_frontend_public(str(tmp_path)) is None


# Each row names the module whose refusal handler is exercised. The eval
# wrapper has no CLI: its public caller, run_evals, reports its refusal.
_READERS = (
    (
        "scripts/apply_refactor.py",
        "edits",
        ("--dry-run",),
        (
            14,
            "",
            "apply_refactor: the edit policy in config/project.json `agents` could not be used: "
            "config/project.json does not exist; fix the key the message names; nothing was changed\n",
        ),
    ),
    (
        "scripts/audit_dependencies.py",
        "settings",
        (),
        (
            14,
            "",
            "the dependency audit settings are refused: config/project.json does not exist; fix the "
            "dependency_audit block of config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/audit_project.py",
        "date",
        (".",),
        (
            2,
            "",
            "audit_project: DEST is not a keel project: . (.copier-answers.yml: missing; "
            ".copier-answers.yml: `_src_path` missing or empty; .copier-answers.yml: `_commit` missing or "
            "empty; config/project.json: missing); name a project generated from this template\n",
        ),
    ),
    (
        "scripts/audit_project.py",
        "collect",
        (".", "--today", "2026-11-05"),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/audit_project.py",
        "epoch",
        (".",),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/canary.py",
        "settings",
        (),
        (
            14,
            "",
            "the canary settings are refused: config/project.json does not exist; fix the canary block of "
            "config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/cdmon_sync.py",
        "environment",
        (),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/check_practices.py",
        "profiles",
        (),
        (
            14,
            "",
            "coding-practices: refused before any file was scanned: config/project.json does not exist; "
            "correct the config file it names, then run `make advise` again\n",
        ),
    ),
    (
        "scripts/check_structure.py",
        "gate",
        ("--root", "."),
        (
            1,
            "ERROR required top-level dir 'src/' is missing\n"
            "ERROR required top-level dir 'tests/' is missing\n"
            "ERROR required top-level dir 'docs/' is missing\n"
            "ERROR config/: missing README.md\n"
            "ERROR config/: missing CLAUDE.md\n"
            "ERROR config/project.json: not found, so no project fact is judged -- restore it (`git "
            "checkout -- config/project.json`, or `copier update` in a generated project)\n"
            "\n"
            "check_structure: 6 error(s), 0 warning(s)\n"
            "next: `make advise` reports what this gate does not fail on; `make doc-review` runs the doc "
            "reviewer (dry-run)\n",
            "[using default] evidence.run_date = null  (not set; to change it, set evidence.run_date in "
            "config/project.json)\n"
            "check_structure: the tree breaks the conventions: 6 error(s) in .; fix each ERROR line above "
            "and run it again\n",
        ),
    ),
    (
        "scripts/make_help.py",
        "no-read",
        (),
        (
            0,
            "Usage: make <target>   (EFFECT=<word> or AREA=<area> filters the list)\n"
            "\n"
            "Effect labels (docs/adr/keel/K-0011-make-target-effect-labels.md):\n"
            "  [local] this machine only; writes nothing git would list\n"
            "  [tree] rewrites files in the working tree\n"
            "  [read] reads a remote service\n"
            "  [cost] spends money\n"
            "  [write] changes shared remote state; refused under CI and gate runs\n",
            "",
        ),
    ),
    (
        "api/rest_fastapi/export_openapi.py",
        "no-read",
        (),
        (0, "wrote <root>/openapi.json\n", ""),
    ),
    (
        "scripts/check_toolchain.py",
        "settings",
        ("versions",),
        (
            14,
            "",
            "the toolchain settings are refused: config/project.json does not exist; fix the toolchain "
            "block of config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/check_venv.py",
        "settings",
        (),
        (
            14,
            "",
            "check_venv: the venv settings are refused: config/project.json does not exist; fix "
            "venv.extras, transports or install_sources.python_index in config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/child_exec.py",
        "environment",
        ("probe.sh",),
        (
            14,
            "",
            "child_exec: the allowlisted environment cannot be built (config/project.json does not exist, "
            "so no child may start without an allowlist): probe.sh; correct config/project.json child_env "
            "as the message says, then run the script again\n",
        ),
    ),
    (
        "scripts/config_get.py",
        "value",
        ("tests.child_timeout_seconds",),
        (
            14,
            "",
            "config_get: tests.child_timeout_seconds cannot be read: config/project.json does not exist; "
            "correct config/project.json as the line says, then run it again\n",
        ),
    ),
    (
        "scripts/doc_review.py",
        "cap",
        ("--execute",),
        (
            14,
            "",
            "doc_review: the model-call cap cannot be read: config/project.json agents.max_model_calls; set "
            "it to a whole number of 0 or more, as the line above says\n",
        ),
    ),
    (
        "scripts/doc_review.py",
        "agent",
        (),
        (
            14,
            "",
            "doc_review: a setting the model or the runtime reads is refused: config/project.json does not "
            "exist; set each key the line names inside its bound\n",
        ),
    ),
    (
        "scripts/exit_code_table.py",
        "policy",
        (),
        (
            14,
            "",
            "exit_code_table: the manifest block cannot be used: config/project.json `doc_drift`: "
            "config/project.json does not exist; correct it as the lines above say\n",
        ),
    ),
    (
        "scripts/gate_evidence.py",
        "policy",
        ("--gate", "probe", "--", "make", "lint"),
        (
            14,
            "",
            "gate_evidence: refused before any goal ran: config/project.json does not exist; correct "
            "config/project.json `evidence`\n",
        ),
    ),
    (
        "scripts/hooks/on_stop_doc_review.py",
        "cap",
        ("--execute",),
        (
            14,
            "",
            "on_stop_doc_review: the model-call cap cannot be read: config/project.json "
            "agents.max_model_calls; set it to a whole number of 0 or more, as the line above says\n",
        ),
    ),
    (
        "scripts/hooks/on_stop_doc_review.py",
        "agent",
        (),
        (
            14,
            "",
            "on_stop_doc_review: a setting the model or the runtime reads is refused: config/project.json "
            "does not exist; set each key the line names inside its bound\n",
        ),
    ),
    (
        "scripts/hooks/on_stop_triage.py",
        "cap",
        ("--execute",),
        (
            14,
            "",
            "on_stop_triage: the model-call cap cannot be read: config/project.json agents.max_model_calls; "
            "set it to a whole number of 0 or more, as the line above says\n",
        ),
    ),
    (
        "scripts/hooks/on_stop_triage.py",
        "agent",
        (),
        (
            14,
            "",
            "on_stop_triage: a setting the model or the runtime reads is refused: config/project.json does "
            "not exist; set each key the line names inside its bound\n",
        ),
    ),
    (
        "scripts/install_scanner.py",
        "settings",
        (),
        (
            14,
            "",
            "the secret scanner settings are refused: config/project.json does not exist; fix the "
            "secrets.scanner block of config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/install_sources.py",
        "source",
        ("python_index",),
        (
            14,
            "",
            "the install source install_sources.python_index is refused: config/project.json does not "
            "exist; set it to a bare https mirror URL with no `@`, `?`, `#` or backslash, or to null for "
            "the tool's own setting, then rerun\n",
        ),
    ),
    (
        "scripts/jobs/build_corpus.py",
        "build",
        (),
        (
            0,
            "wrote wiki/corpus.json: 0 nodes (0 summary gaps, 0 unowned, 0 on the default owner)\n",
            "[using default] accountability.default_owner = null  (not set; to change it, set "
            "accountability.default_owner in config/project.json)\n",
        ),
    ),
    (
        "scripts/jobs/build_llms_txt.py",
        "levels",
        (),
        (
            14,
            "",
            "build_llms_txt: the levels a served node may carry cannot be read: config/project.json does "
            "not exist; set corpus.served_visibilities to members of public, internal, confidential, "
            "restricted, then rerun; nothing was written\n",
        ),
    ),
    (
        "scripts/jobs/check_corpus.py",
        "build",
        (),
        (
            0,
            "check_corpus: no local wiki/corpus.json yet (generated view) -- agents build one with `make "
            "site-data`\n"
            "check_corpus: fresh build valid + deterministic (0 nodes, 0 edges)\n",
            "[using default] accountability.default_owner = null  (not set; to change it, set "
            "accountability.default_owner in config/project.json)\n",
        ),
    ),
    ("scripts/jobs/declare_no_app.py", "manifest", (), (0, "", "")),
    (
        "scripts/jobs/export_showcase_static.py",
        "frontend",
        (),
        (
            0,
            "",
            "export_showcase_static skipped (no frontend declared in config/project.json)\n",
        ),
    ),
    (
        "scripts/jobs/export_showcase_static.py",
        "levels",
        ("--out-dir", "public"),
        (
            14,
            "",
            "export_showcase_static: the levels a served node may carry cannot be read: config/project.json "
            "does not exist; set corpus.served_visibilities to members of public, internal, confidential, "
            "restricted, then rerun; nothing was written\n",
        ),
    ),
    (
        "scripts/jobs/finish_update.py",
        "environment",
        ("--dry-run",),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/jobs/keep_edited_retired.py",
        "environment",
        ("--template", ".", "--from", "HEAD"),
        (
            2,
            "",
            "keep_edited_retired: cannot judge the files the update deleted: git diff-index: "
            "config/project.json does not exist, so no child may start without an allowlist; fix what it "
            "names, then finish the update\n",
        ),
    ),
    (
        "scripts/jobs/resolve_stamp_conflicts.py",
        "environment",
        (),
        (
            2,
            "",
            "resolve_stamp_conflicts: cannot read the update's conflicts: git ls-files: config/project.json "
            "does not exist, so no child may start without an allowlist; fix what it names, then finish the "
            "update\n",
        ),
    ),
    (
        "scripts/jobs/restamp_docs.py",
        "date",
        (),
        (
            2,
            "",
            "restamp_docs: cannot start git: config/project.json does not exist, so no child may start "
            "without an allowlist; resolve it, then run `make restamp-docs`\n",
        ),
    ),
    (
        "scripts/jobs/restamp_docs.py",
        "check",
        ("--today", "2026-11-05", "--check"),
        (
            2,
            "",
            "restamp_docs: cannot start git: config/project.json does not exist, so no child may start "
            "without an allowlist; resolve it, then run `make restamp-docs`\n",
        ),
    ),
    (
        "scripts/jobs/restamp_docs.py",
        "worklist",
        ("--today", "2026-11-05"),
        (
            2,
            "",
            "restamp_docs: cannot start git: config/project.json does not exist, so no child may start "
            "without an allowlist; resolve it, then run `make restamp-docs`\n",
        ),
    ),
    (
        "scripts/jobs/review_docs.py",
        "date",
        (),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/jobs/review_docs.py",
        "collect",
        ("--today", "2026-11-05"),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/jobs/review_docs.py",
        "epoch",
        (),
        (
            (
                "ChildEnvError",
                "config/project.json does not exist, so no child may start without an allowlist",
            ),
            "",
            "",
        ),
    ),
    (
        "scripts/launch.py",
        "manifest",
        ("--root", ".", "--", "true"),
        (
            2,
            "",
            "launch: refused before anything ran: config/project.json is unreadable or not JSON "
            "(FileNotFoundError); restore config/project.json\n",
        ),
    ),
    (
        "scripts/long_scripts.py",
        "manifest",
        ("--root", "."),
        (
            2,
            "",
            "long_scripts: refused before judging: config/project.json is unreadable or not JSON "
            "(FileNotFoundError); restore config/project.json\n",
        ),
    ),
    (
        "scripts/query_corpus.py",
        "levels",
        ("what",),
        (
            14,
            "",
            "query_corpus: the levels a served node may carry cannot be read: config/project.json does not "
            "exist; set corpus.served_visibilities to members of public, internal, confidential, "
            "restricted, then rerun\n",
        ),
    ),
    (
        "scripts/record_gate_baseline.py",
        "policy",
        (),
        (
            14,
            "",
            "record_gate_baseline: config/project.json does not exist: config/project.json; correct the "
            "named key or file, then rerun `make gate-baseline`\n",
        ),
    ),
    (
        "scripts/record_gate_baseline.py",
        "timeout",
        (),
        (
            14,
            "",
            "record_gate_baseline: config/project.json does not exist: config/project.json; set "
            "tests.child_timeout_seconds, then rerun `make gate-baseline`\n",
        ),
    ),
    (
        "scripts/refactor_practice.py",
        "cap",
        ("x", "--execute"),
        (
            14,
            "",
            "refactor_practice: the model-call cap cannot be read: config/project.json "
            "agents.max_model_calls; set it to a whole number of 0 or more, as the line above says\n",
        ),
    ),
    (
        "scripts/refactor_practice.py",
        "agent",
        ("x",),
        (
            14,
            "",
            "refactor_practice: a setting the model or the runtime reads is refused: config/project.json "
            "does not exist; set each key the line names inside its bound\n",
        ),
    ),
    (
        "scripts/run_app.py",
        "manifest",
        (),
        (
            14,
            "",
            "run_app: config/project.json cannot be used: config/project.json does not exist; fix the file "
            "the message names, then run again\n",
        ),
    ),
    (
        "scripts/run_evals.py",
        "config",
        ("--root", "."),
        (
            14,
            "",
            "run_evals: `evals.report_dir` is unusable, so an earlier report may still stand; trust this "
            "exit code, not that file\n"
            "run_evals: the evals config was refused: config/project.json does not exist; correct "
            "config/project.json `evals` and run it again\n",
        ),
    ),
    (
        "evals/_config.py",
        "public-caller",
        ("--root", "."),
        (
            14,
            "",
            "run_evals: `evals.report_dir` is unusable, so an earlier report may still stand; trust this "
            "exit code, not that file\n"
            "run_evals: the evals config was refused: config/project.json does not exist; correct "
            "config/project.json `evals` and run it again\n",
        ),
    ),
    (
        "scripts/run_make_target.py",
        "limits",
        ("lint",),
        (
            2,
            "run_make_target: refused `make lint`: config/project.json is absent, so the make_targets "
            "policy is unknown\n"
            "\n"
            "run_make_target: `make lint` [] -> REFUSED (rc=None)\n",
            "run_make_target: refused, and make was never run: `make lint`: config/project.json is absent, "
            "so the make_targets policy is unknown; run a target config/project.json "
            "`make_targets.gate_effects` allows\n",
        ),
    ),
    (
        "scripts/scan_secrets.py",
        "settings",
        ("--staged",),
        (
            14,
            "",
            "the secret scanner settings are refused: config/project.json does not exist; fix the "
            "secrets.scanner block of config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/shell_gate.py",
        "settings",
        ("lint",),
        (
            14,
            "",
            "the shell settings are refused: config/project.json does not exist; fix the shell block of "
            "config/project.json, then rerun\n",
        ),
    ),
    (
        "scripts/trace_requirements.py",
        "policy",
        ("--root", "."),
        (
            2,
            "",
            "trace: the `traceability` block is what names the matrix, so nothing was written or removed "
            "and an earlier matrix may still stand; trust this exit code, not that file\n"
            "trace: could not judge: config/project.json cannot be read (FileNotFoundError); correct "
            "config/project.json `traceability` and run it again\n",
        ),
    ),
    (
        "mcp/action_server.py",
        "settings",
        (),
        (
            14,
            "",
            "the MCP action server's settings are refused: config/project.json does not exist; set each key "
            "the line names inside its bound\n",
        ),
    ),
    (
        "mcp/qa_server.py",
        "settings",
        (),
        (
            14,
            "",
            "the MCP Q&A server's settings are refused: config/project.json does not exist; set each key or "
            "variable the line names inside its bound\n",
        ),
    ),
    (
        "api/rest_fastapi/serve.py",
        "limits",
        ("--port", "8123"),
        (
            14,
            "",
            "the REST server's limits are refused: config/project.json does not exist; set "
            "config/project.json transports.serve inside its bound\n",
        ),
    ),
    (
        "api/grpc/server.py",
        "settings",
        (),
        (
            14,
            "",
            "the gRPC server's settings are refused: config/project.json does not exist; set each key the "
            "line names inside its bound\n",
        ),
    ),
)
_HUNK = (
    "{\n"
    + "<" * 7
    + ' ours\n"a": 1\n'
    + "=" * 7
    + '\n"a": 2\n'
    + ">" * 7
    + " theirs\n}\n"
).encode("utf-8")
_REFUSALS = (
    pytest.param(b"", ExitCode.CONFIG, id="empty"),
    pytest.param(b"null", ExitCode.CONFIG, id="null"),
    pytest.param(b"\xff\xfe", ExitCode.CONFIG, id="non-utf8"),
    pytest.param(b'{"a": 1, "a": 2}', ExitCode.CONFIG, id="duplicate"),
    pytest.param(b"[]", ExitCode.CONFIG, id="not-object"),
    pytest.param(b"not JSON", ExitCode.CONFIG, id="not-json"),
    pytest.param(None, ExitCode.CONFIG, id="unreadable"),
    pytest.param(_HUNK, ExitCode.USAGE, id="hunk"),
)


def _is_main_guard(stmt):
    """True for a top-level `if` whose test names both `__name__` and the
    string "__main__", in any order or combination: a guard is found by what
    it compares, never by which side each operand is written on."""
    if not isinstance(stmt, ast.If):
        return False
    parts = list(ast.walk(stmt.test))
    return any(isinstance(x, ast.Name) and x.id == "__name__" for x in parts) and any(
        isinstance(x, ast.Constant) and x.value == "__main__" for x in parts
    )


def _manifest_readers():
    """Follow local symbols from every main guard, independent of reporters.

    Resolve absolute, relative and namespace-package imports against the entry's
    directory, scripts/jobs, scripts, src and the checkout. Follow called or
    referenced functions and registries, plus import-time calls, until reaching
    config_loader.read/resolve/env/served_visibilities or child_env's allowlist.
    This conservatively includes callbacks referenced by reachable functions;
    importing a module just for constants does not make all its functions live.
    References overestimate callbacks and registry construction: the no-read
    rows for make_help and export_openapi assert that read is never called.
    No handler name participates in discovery.
    """
    paths = {
        p.resolve()
        for directory in (
            "scripts",
            "evals",
            "api",
            "mcp",
            "agents",
            "models",
            "runtimes",
            "src",
        )
        for p in (_ROOT / directory).rglob("*.py")
    }
    trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in paths}

    def resolve(dotted, search):
        for base in search:
            target = base.joinpath(*dotted.split("."))
            for path in (target.with_suffix(".py"), target / "__init__.py"):
                if path.resolve() in trees:
                    return path.resolve()
        return None

    def walk(entry):
        search = (
            entry.parent,
            _ROOT / "scripts/jobs",
            _ROOT / "scripts",
            _ROOT / "src",
            _ROOT,
        )
        pending, seen = [(entry, None)], set()
        while pending:
            path, symbol = pending.pop()
            if (path, symbol) in seen:
                continue
            seen.add((path, symbol))
            if path.name == "config_loader.py" and symbol in {
                "read",
                "resolve",
                "env",
                "served_visibilities",
            }:
                return True
            if path.name == "child_env.py" and symbol in {
                "build_child_env",
                "load_policy",
            }:
                return True
            tree = trees[path]
            bindings, definitions = {}, {}
            for node in tree.body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    definitions[node.name] = node
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            definitions[target.id] = node.value
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = resolve(alias.name, search)
                        if target:
                            bindings[alias.asname or alias.name] = (target, None)
                elif isinstance(node, ast.ImportFrom):
                    base = path.parent
                    for _ in range(max(0, node.level - 1)):
                        base = base.parent
                    where = (base,) if node.level else search
                    prefix = node.module or ""
                    for alias in node.names:
                        target = resolve(
                            prefix + "." + alias.name if prefix else alias.name, where
                        )
                        if target:
                            bindings[alias.asname or alias.name] = (target, None)
                        else:
                            target = resolve(prefix, where)
                            if target:
                                bindings[alias.asname or alias.name] = (
                                    target,
                                    alias.name,
                                )
            if symbol in bindings:
                pending.append(bindings[symbol])
                continue
            if symbol is None:
                # Imports execute module bodies, never all imported functions.
                pending.extend((target, None) for target, _ in bindings.values())
                nodes = [
                    n
                    for stmt in tree.body
                    if not isinstance(
                        stmt,
                        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If),
                    )
                    for n in ast.walk(stmt)
                    if isinstance(n, ast.Call)
                ]
                nodes += (
                    [
                        n
                        for stmt in tree.body
                        if _is_main_guard(stmt)
                        for n in ast.walk(stmt)
                        if isinstance(n, ast.Call)
                    ]
                    if path == entry
                    else []
                )
            elif symbol in definitions:
                nodes = list(ast.walk(definitions[symbol]))
            else:
                continue
            for node in nodes:
                if isinstance(node, ast.Call):
                    node = node.func
                if isinstance(node, ast.Name):
                    if node.id in bindings:
                        pending.append(bindings[node.id])
                    elif node.id in definitions:
                        pending.append((path, node.id))
                elif isinstance(node, ast.Attribute) and isinstance(
                    node.value, ast.Name
                ):
                    bound = bindings.get(node.value.id)
                    if bound and bound[1] is None:
                        pending.append((bound[0], node.attr))
        return False

    return {
        p.relative_to(_ROOT).as_posix()
        for p, tree in trees.items()
        if p.relative_to(_ROOT).parts[0] in {"scripts", "evals", "api", "mcp", "agents"}
        and any(_is_main_guard(n) for n in tree.body)
        and walk(p)
    }


@pytest.mark.parametrize(
    ("source", "guard"),
    [
        ('if __name__ == "__main__":\n    pass\n', True),
        ('if "__main__" == __name__:\n    pass\n', True),
        ('if __name__ == "__main__" and ready:\n    pass\n', True),
        ('if mode == "__main__":\n    pass\n', False),
        ("if __name__:\n    pass\n", False),
    ],
)
def test_a_main_guard_is_found_in_either_order(source, guard):
    """Discovery and the walk share one predicate, so an entry point written
    with its compare reversed is neither missed nor walked differently."""
    assert _is_main_guard(ast.parse(source).body[0]) is guard


def test_every_manifest_reader_has_cases():
    """Find main guards under all five entry roots, then follow local imports,
    referenced functions, registries and import-time calls to loader reads or
    allowlist builds. This conservative symbol walk does not inspect refusal
    handlers; no-read rows prove its overestimates, and a missing row or an
    empty walk fails. See _manifest_readers for resolution details.
    """
    found = _manifest_readers()
    assert found, "discovered zero manifest readers"
    covered = {module for module, _route, _argv, _absent in _READERS}
    assert not found - covered, "add refusal cases for: %s" % sorted(found - covered)


def _prepare_reader(tmp_path, monkeypatch, module, route):
    if not (_ROOT / module).is_file():
        pytest.skip("this generated project does not ship %s" % module)
    name = Path(module).stem
    if module.startswith(("api/", "mcp/")):
        if module == "api/grpc/server.py":
            # Only import-time types are needed: no transport starts on refusal.
            monkeypatch.setitem(sys.modules, "grpc", SimpleNamespace())
            monkeypatch.setitem(sys.modules, "thing_pb2", SimpleNamespace())
            monkeypatch.setitem(
                sys.modules,
                "thing_pb2_grpc",
                SimpleNamespace(ThingServiceServicer=object),
            )
        spec = importlib.util.spec_from_file_location("refusal_" + name, _ROOT / module)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
    else:
        reader = importlib.import_module(
            "run_evals" if module == "evals/_config.py" else name
        )
    import child_env
    import review_docs

    # Relocate checkout defaults, including the allowlist's file-derived root;
    # leave the loader and its real parsing/classification code intact.
    monkeypatch.chdir(tmp_path)
    for attr in ("ROOT", "_ROOT", "_REPO", "_DEFAULT_ROOT"):
        if hasattr(reader, attr):
            monkeypatch.setattr(reader, attr, str(tmp_path))
    if hasattr(reader, "_SCRIPTS"):
        monkeypatch.setattr(reader, "_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setattr(review_docs, "ROOT", str(tmp_path))
    monkeypatch.setattr(child_env, "__file__", str(tmp_path / "scripts/child_env.py"))
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    if route == "epoch":
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1793836800")
    if name == "audit_project":
        monkeypatch.setattr(reader, "TEMPLATE", str(_ROOT))
        if route in {"collect", "epoch"}:
            # The audited destination is separate from the template's config.
            # Reach a real allowlist read inside audit after date resolution.
            monkeypatch.setattr(
                reader, "audit", lambda *_args: child_env.build_child_env()
            )
    if module == "api/rest_fastapi/serve.py":
        monkeypatch.setattr(reader.resource_limits, "_REPO", str(tmp_path))
    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"practice":"p","edits":[{"file":"README.md"}]}')
    )

    def read_at_agent_boundary(*_args, **_kwargs):
        return config_loader.read(str(tmp_path))

    if route == "agent":
        # No model runs: exercise the entry point's handler for a loader
        # refusal raised inside the imported agent, as the runtime would.
        agent = (
            "triage"
            if name == "on_stop_triage"
            else "refactor"
            if name == "refactor_practice"
            else "review"
        )
        monkeypatch.setattr(reader, agent, read_at_agent_boundary)
    if name == "cdmon_sync":
        # Pass the optional-tool checks so the environment read is reached.
        monkeypatch.setattr(reader.shutil, "which", lambda _name: "/unused/cdmon")
        config = tmp_path / reader.DEFAULT_CONFIG
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("# probe\n", encoding="utf-8")
    if name == "export_openapi":
        monkeypatch.setattr(reader, "_OUT", str(tmp_path / "openapi.json"))
    if name == "child_exec":
        (tmp_path / "probe.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    if name == "check_practices":
        (tmp_path / "config/practices.json").write_text("{}", encoding="utf-8")
    if name == "record_gate_baseline":
        (tmp_path / ".copier-answers.yml").write_text(
            "_commit: probe\n", encoding="utf-8"
        )
        if route == "timeout":
            # The timeout has its own handler after policy/baseline loading;
            # retain the real run_checks, which reads before spawning pytest.
            monkeypatch.setattr(
                reader.expiring_tier,
                "load_policy",
                lambda _root: SimpleNamespace(baseline="baseline.json"),
            )
            monkeypatch.setattr(
                reader.expiring_tier, "read_baseline", lambda *_args: {}
            )
    return reader


@pytest.mark.parametrize("payload, expected", _REFUSALS)
@pytest.mark.parametrize(
    "module, route, argv",
    [
        pytest.param(module, route, argv, id=module + ":" + route)
        for module, route, argv, _absent in _READERS
    ],
)
def test_a_refused_manifest_is_one_config_line(
    tmp_path, capsys, monkeypatch, module, route, argv, payload, expected
):
    (tmp_path / "config").mkdir()
    manifest = tmp_path / "config/project.json"
    if payload is None:
        manifest.mkdir()
    else:
        manifest.write_bytes(payload)
    reader = _prepare_reader(tmp_path, monkeypatch, module, route)
    if route == "no-read":

        def unexpected_read(*_args, **_kwargs):
            pytest.fail("a conservative discovery case became a manifest reader")

        monkeypatch.setattr(config_loader, "read", unexpected_read)
    if (
        module == "scripts/check_venv.py"
        or module.startswith("mcp/")
        or module == "api/grpc/server.py"
    ):
        result = reader.main(root=str(tmp_path))
    else:
        result = reader.main(list(argv))
    captured = capsys.readouterr()
    if module.startswith("scripts/hooks/") and "--execute" not in argv:
        expected = ExitCode.CONFIG
    if route == "no-read":
        assert result is ExitCode.SUCCESS
        return
    assert result is expected
    assert len(captured.err.splitlines()) == 1
    assert "config/project.json" in captured.err
    assert "Traceback" not in captured.out + captured.err
    assert captured.out == ""
    assert manifest.is_dir() if payload is None else manifest.read_bytes() == payload


@pytest.mark.parametrize("payload, expected", _REFUSALS)
@pytest.mark.parametrize(
    "module, argv",
    sorted(
        {
            (module, argv)
            for module, _route, argv, _absent in _READERS
            if Path(module).stem
            in {
                "restamp_docs",
                "declare_no_app",
                "resolve_stamp_conflicts",
                "keep_edited_retired",
                "finish_update",
            }
        }
    ),
)
def test_job_entry_guard_classifies_manifest(tmp_path, module, argv, payload, expected):
    """Run the actual __main__ guard before the job imports its readers."""
    shutil.copytree(
        _ROOT / "scripts",
        tmp_path / "scripts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (tmp_path / "config").mkdir()
    manifest = tmp_path / "config/project.json"
    if payload is None:
        manifest.mkdir()
    else:
        manifest.write_bytes(payload)
    timeout = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(("tests", "child_timeout_seconds")),
        config_loader.CONFIG_FILE,
    )[("tests", "child_timeout_seconds")]
    result = subprocess.run(
        [sys.executable, "-B", str(tmp_path / module), *argv],
        cwd=tmp_path,
        env=build_child_env(root=str(_ROOT)),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == expected, result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert "config/project.json" in result.stderr
    assert "Traceback" not in result.stderr + result.stdout
    assert result.stdout == ""


@pytest.mark.parametrize(
    "module, route, argv, expected",
    [pytest.param(*row, id=row[0] + ":" + row[1]) for row in _READERS],
)
def test_an_absent_manifest_keeps_the_readers_previous_path(
    tmp_path, capsys, monkeypatch, module, route, argv, expected
):
    """Pin cf7ca3e's exit and both messages, including its raised absent paths.

    The historical results live in _READERS so generated projects need no
    template git history. External agents remain at the same read boundary.
    """
    (tmp_path / "config").mkdir()
    reader = _prepare_reader(tmp_path, monkeypatch, module, route)
    config_loader._ANNOUNCED.clear()
    try:
        if (
            module == "scripts/check_venv.py"
            or module.startswith("mcp/")
            or module == "api/grpc/server.py"
        ):
            code = reader.main(root=str(tmp_path))
        else:
            code = reader.main(list(argv))
    except Exception as exc:  # noqa: BLE001 -- cf7ca3e raised on some absent paths; preserve the type and message
        code = (type(exc).__name__, str(exc))
    captured = capsys.readouterr()
    actual = (
        code,
        captured.out.replace(str(tmp_path), "<root>"),
        captured.err.replace(str(tmp_path), "<root>"),
    )
    assert actual == expected


@pytest.mark.parametrize("template", ["{unknown}", "{cpus}", "{cpus"])
def test_render_requires_an_edit_that_clears_the_refusal(template):
    with pytest.raises(launch.LauncherConfigError) as caught:
        launch.render(template, {})
    assert "placeholder" in caught.value.fix
    assert caught.value.fix not in str(caught.value)


def test_launcher_errors_have_no_default_remedy():
    with pytest.raises(TypeError):
        launch.LauncherConfigError("problem")


def test_an_imported_reader_raises_without_reporting(tmp_path, capsys):
    if not (_ROOT / "scripts/jobs/export_showcase_static.py").is_file():
        pytest.skip("this project declined the showcase exporter")
    import export_showcase_static

    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_bytes(b"null")
    with pytest.raises(config_loader.ConfigUnreadable):
        export_showcase_static._declared_frontend_public(str(tmp_path))
    assert capsys.readouterr().err == ""


def _hunk_refusal(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_text(
        "{\n"
        + "<" * 7
        + ' ours\n"a": 1\n'
        + "=" * 7
        + '\n"a": 2\n'
        + ">" * 7
        + " theirs\n}\n",
        encoding="utf-8",
    )
    with pytest.raises(config_loader.ConfigUnreadable) as caught:
        config_loader.read(str(tmp_path))
    assert config_loader.is_conflict(caught.value)
    return caught.value


@pytest.mark.parametrize(
    "hook, agent", [(on_stop_doc_review, "review"), (on_stop_triage, "triage")]
)
def test_a_triggered_hook_ends_a_conflict_hunk_as_config_not_2(
    tmp_path, capsys, monkeypatch, hook, agent
):
    refusal = _hunk_refusal(tmp_path)

    def refused(*_args, **_kwargs):
        raise refusal

    monkeypatch.setattr(hook, agent, refused)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    result = hook.main(["-"])
    err = capsys.readouterr().err
    assert result is ExitCode.CONFIG
    assert len(err.splitlines()) == 1
    assert "config/project.json" in err and "hunk" in err
