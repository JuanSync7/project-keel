"""
title: Integration — practice_refactor gated KG-walking loop
kind: tests
layer: backend
summary: A relative root reaches the corpus query as one absolute `--root`, with no `--corpus` beside it; a corpus given alone names its checkout, and the CLI hands refactor() that derived root, never its own `--root`; a root beside a corpus, a corpus outside some checkout's wiki/corpus.json, or one named that does not exist, is corpus_level.NotACheckout before any tool runs, and exit USAGE from the CLI. Dry-run walks the graph + gates the read-only baseline but proposes/writes nothing; execute proposes one bounded edit per chunk and a chunk is `refactored` only when the gated apply_refactor keeps make verify green (else rolled back -> `skipped`); a crash mid-refactor resumes at the cursor without re-applying accepted chunks. The gate is the run's: a reply that names a gate is declined before any apply, every apply is bound to its chunk's own file with `--allow`, a chunk with no path is declined before the model is called, and a chunk outside config/project.json corpus.served_visibilities is no candidate, nor is one whose file states a level outside it on disk now, or none that can be read, as a document reclassified after the corpus was built does; a saved run's chunk from such a file is declined at propose with no model call. Every tool call hands the refactored root to the runner, so run_tool reads the tool limits, and checks them against the gate keys, of the tree the gate runner reads.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.practice_refactor import refactor  # noqa: E402
from models import ModelMeter  # noqa: E402
from runtimes import FileCheckpointer  # noqa: E402
from scripts import corpus_level  # noqa: E402

import reclassify  # noqa: E402

pytestmark = pytest.mark.integration

# Patch the model + CLI-subprocess seams by dotted path (no import of the private
# module symbols, so the package boundary holds — tests are callers too).
_BRAIN = "agents.practice_refactor._brain"
_CODEWORD = "CODEWORD-ZEBRA"

_NODES = [
    {
        "node_id": "n1",
        "path": "src/backend/a.py",
        "tags": ["backend"],
        "text_excerpt": "x1",
        "visibility": "internal",
    },
    {
        "node_id": "n2",
        "path": "src/backend/b.py",
        "tags": ["backend"],
        "text_excerpt": "x2",
        "visibility": "internal",
    },
]


class _Runner:
    """A fake `_run` that answers each tool CLI from data — no real subprocess.

    query_corpus -> the neighbourhood; run_make_target -> a green gate;
    apply_refactor -> accept (echoing the spec's files) or reject per `gate_ok`.
    Records the tool of every call so a test can assert what did and didn't run.
    """

    def __init__(self, nodes=_NODES, baseline_ok=True, gate_ok=True):
        self.nodes = nodes
        self.baseline_ok = baseline_ok
        self.gate_ok = gate_ok
        self.calls = []
        self.argvs = {}
        self.specs = []
        self.applied_files = []
        self.roots = []

    def __call__(self, args, stdin=None, *, root):
        self.roots.append(root)
        joined = " ".join(args)
        tool = next((a for a in args if a.endswith(".py")), "")
        self.argvs.setdefault(tool.rsplit("/", 1)[-1], []).append(list(args))
        if "query_corpus.py" in joined:
            self.calls.append("query_corpus")
            return 0, json.dumps(self.nodes), ""
        if "run_make_target.py" in joined:
            self.calls.append("run_make_target")
            return (
                0,
                json.dumps(
                    {
                        "target": "verify",
                        "ok": self.baseline_ok,
                        "returncode": 0 if self.baseline_ok else 1,
                        "output": "",
                    }
                ),
                "",
            )
        if "apply_refactor.py" in joined:
            self.calls.append("apply_refactor")
            spec = json.loads(stdin)
            self.specs.append(spec)
            files = [e["file"] for e in spec.get("edits", [])]
            if self.gate_ok:
                self.applied_files.extend(files)
            return (
                0 if self.gate_ok else 1,
                json.dumps(
                    {
                        "practice": spec.get("practice", ""),
                        "gate": "verify",
                        "applied": self.gate_ok,
                        "rolled_back": not self.gate_ok,
                        "files": files,
                        "gate_output": "ok" if self.gate_ok else "RED",
                    }
                ),
                "",
            )
        self.calls.append("other")
        return 0, "", ""


_CHUNK_PATH = re.compile(r"^path: (.*)$", re.MULTILINE)


def _chunk_edit(prompt):
    """One bounded edit to the file the prompt's chunk is from: the only file
    the brain binds apply_refactor to (`--allow <chunk path>`)."""
    path = _CHUNK_PATH.findall(prompt)[-1]
    return json.dumps({"edits": [{"file": path, "find": "old", "replace": "new"}]})


class _Model:
    name = "model"

    """A model that returns one bounded edit spec per chunk (or a scripted reply)."""

    def __init__(self, replies=None):
        self.replies = replies
        self.n = 0

    def run(self, prompt):
        self.n += 1
        if self.replies is not None:
            return self.replies[self.n - 1]
        return _chunk_edit(prompt)


def _files(root):
    """Write the files _NODES name under *root*, each stating no level, so the
    level they state on disk now is `internal`, as the corpus says: the walk
    and propose serve a chunk only on the level its file states now."""
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "project.json").write_text("{}")
    for node in _NODES:
        f = root / node["path"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('"""\ntitle: %s\nsummary: s.\n"""\n' % node["node_id"])
    return str(root)


def _patch(monkeypatch, runner, model):
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)


def _checkpointer(tmp_path):
    # The default checkpointer writes under the checkout's wiki/.runtime, and
    # would resume a snapshot an earlier crashed run left there.
    return FileCheckpointer(str(tmp_path / "checkpoints"))


def test_dry_run_walks_and_previews_but_never_proposes_or_writes(tmp_path, monkeypatch):
    runner, model = _Runner(), _Model()
    _patch(monkeypatch, runner, model)

    # execute defaults to False
    rep = refactor("precise-container-types", root=_files(tmp_path))

    assert rep.dry_run is True
    assert rep.candidates == ("n1", "n2")  # the graph was walked
    assert rep.baseline_green is True  # the read-only baseline gate ran
    assert rep.refactored == () and rep.skipped == ()
    assert (
        "precise-container-types" in rep.preview and "src/backend/a.py" in rep.preview
    )
    assert model.n == 0  # MODEL_CALL step skipped in dry-run
    assert "apply_refactor" not in runner.calls  # WRITES step skipped in dry-run
    assert runner.calls == ["query_corpus", "run_make_target"]


def test_the_walk_drops_a_node_outside_the_served_levels(tmp_path, monkeypatch):
    """A confidential chunk the walk returns is no candidate: its text reaches
    neither the dry-run preview nor any proposal prompt."""
    hidden = {
        "node_id": "n0",
        "path": "src/backend/vault.py",
        "tags": ["backend"],
        "text_excerpt": "CODEWORD-ZEBRA",
        "visibility": "confidential",
    }
    runner, model = _Runner(nodes=[hidden] + _NODES), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
    )

    assert rep.candidates == ("n1", "n2")
    assert "CODEWORD-ZEBRA" not in rep.preview
    assert model.n == 2
    assert "src/backend/vault.py" not in rep.refactored + rep.skipped


def test_a_relative_root_reaches_the_corpus_query_as_one_absolute_checkout(
    tmp_path, monkeypatch
):
    """query_corpus reads the corpus of the root it is handed, so a relative
    root is made absolute first, from the caller's directory, and handed
    alone: a `--corpus` beside it could name another checkout's corpus."""
    runner, model = _Runner(), _Model()
    _patch(monkeypatch, runner, model)
    _files(tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    refactor("precise-container-types", root=tmp_path.name)
    (argv,) = runner.argvs["query_corpus.py"]
    assert os.path.isabs(_flag(argv, "--root"))
    assert os.path.realpath(_flag(argv, "--root")) == os.path.realpath(str(tmp_path))
    assert "--corpus" not in argv


def test_a_corpus_names_the_checkout_the_walk_reads(tmp_path, monkeypatch):
    """A corpus given alone is its checkout's wiki/corpus.json, a relative
    one from the caller's directory, so the query is handed that checkout."""
    runner, model = _Runner(), _Model()
    _patch(monkeypatch, runner, model)
    _files(tmp_path)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "corpus.json").write_text(json.dumps({"nodes": _NODES}))
    monkeypatch.chdir(tmp_path.parent)
    refactor(
        "precise-container-types",
        corpus=os.path.join(tmp_path.name, "wiki", "corpus.json"),
    )
    (argv,) = runner.argvs["query_corpus.py"]
    assert os.path.realpath(_flag(argv, "--root")) == os.path.realpath(str(tmp_path))
    assert "--corpus" not in argv


def test_the_cli_refactors_the_checkout_its_corpus_names(tmp_path, monkeypatch):
    """`--corpus other/wiki/corpus.json` names checkout `other`, so the CLI
    hands refactor() that derived root, and the walk queries `other`; a CLI
    passing its own `--root`, unset here, would walk this checkout."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import refactor_practice as rp  # noqa: E402

    runner, model = _Runner(), _Model()
    _patch(monkeypatch, runner, model)
    other = tmp_path / "other"
    other.mkdir()
    _files(other)
    (other / "wiki").mkdir()
    (other / "wiki" / "corpus.json").write_text(json.dumps({"nodes": _NODES}))
    corpus = str(other / "wiki" / "corpus.json")
    code = rp.main(["precise-container-types", "--corpus", corpus])
    assert code == rp.exit_codes.ExitCode.SUCCESS
    (argv,) = runner.argvs["query_corpus.py"]
    assert os.path.realpath(_flag(argv, "--root")) == os.path.realpath(str(other))


@pytest.mark.parametrize("given", ["both", "outside-wiki", "missing", "empty-root"])
def test_a_corpus_that_is_not_its_roots_own_is_refused_before_any_step(
    tmp_path, monkeypatch, capsys, given
):
    """A root beside a corpus, or a corpus outside some checkout's
    wiki/corpus.json, could pair one checkout's corpus with another's files,
    a corpus named in a folder that keeps none would walk nothing, and an
    empty root would walk this checkout as if no root were given:
    refactor() raises corpus_level.NotACheckout and runs no tool, and the
    CLI refuses it with USAGE before the agent runs."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import refactor_practice as rp  # noqa: E402

    runner, model = _Runner(), _Model()
    _patch(monkeypatch, runner, model)
    root = _files(tmp_path)
    if given == "both":
        kwargs = {"root": root, "corpus": os.path.join(root, "wiki", "corpus.json")}
    elif given == "missing":
        kwargs = {"corpus": os.path.join(root, "wiki", "corpus.json")}
    elif given == "empty-root":
        kwargs = {"root": ""}
    else:
        kwargs = {"corpus": os.path.join(root, "corpus.json")}
    with pytest.raises(corpus_level.NotACheckout):
        refactor("precise-container-types", **kwargs)
    flags = [a for k, v in sorted(kwargs.items()) for a in ("--" + k, v)]
    assert rp.main(["precise-container-types"] + flags) == rp.exit_codes.ExitCode.USAGE
    assert "wiki/corpus.json" in capsys.readouterr().err or given == "empty-root"
    assert runner.calls == []


def test_red_baseline_attempts_no_refactor(tmp_path, monkeypatch):
    runner, model = _Runner(baseline_ok=False), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
    )

    assert rep.baseline_green is False
    assert rep.refactored == () and rep.skipped == ()
    assert model.n == 0  # never proposed on a red tree
    assert "apply_refactor" not in runner.calls


def test_execute_applies_each_accepted_chunk_and_the_gate_keeps_it(
    tmp_path, monkeypatch
):
    runner, model = _Runner(gate_ok=True), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
    )

    assert rep.dry_run is False and rep.baseline_green is True
    assert rep.refactored == ("src/backend/a.py", "src/backend/b.py")
    assert rep.skipped == ()
    assert runner.calls.count("apply_refactor") == 2  # one gated apply per chunk
    assert model.n == 2


def test_every_tool_child_is_bounded_by_the_refactored_roots_limits(
    tmp_path, monkeypatch
):
    """The gate runner reads its limit from the refactored root, which is not
    this checkout here, so each tool call must hand that root to run_tool."""
    runner, model = _Runner(gate_ok=True), _Model()
    _patch(monkeypatch, runner, model)
    root = tmp_path / "tree"
    root.mkdir()
    _files(root)
    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=str(root),
        checkpointer=_checkpointer(tmp_path),
    )
    assert rep.baseline_green is True
    assert runner.calls.count("apply_refactor") == 2, runner.calls
    assert runner.roots == [str(root)] * len(runner.calls)


def test_gate_red_rolls_back_so_the_chunk_is_skipped_not_refactored(
    tmp_path, monkeypatch
):
    runner, model = _Runner(gate_ok=False), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
    )

    assert rep.refactored == ()  # nothing kept — the gate went red
    assert rep.skipped == ("n1", "n2")  # both chunks rolled back
    assert runner.applied_files == []


def test_model_declining_a_chunk_skips_it_without_touching_apply(tmp_path, monkeypatch):
    # Non-JSON and empty-edits replies both mean "decline this chunk".
    runner = _Runner()
    model = _Model(replies=["I cannot safely edit this.", json.dumps({"edits": []})])
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
    )

    assert rep.refactored == () and rep.skipped == ("n1", "n2")
    assert (
        "apply_refactor" not in runner.calls
    )  # declined -> the gated doer is never called


def test_a_reply_that_names_a_gate_is_declined_and_never_applied(tmp_path, monkeypatch):
    """The gate is the run's: a reply naming one (here `none`, no gate at all)
    is declined before apply, and the baseline still ran the run's gate."""
    runner = _Runner()
    gated = json.loads(_chunk_edit("path: src/backend/a.py\n"))
    gated["gate"] = "none"
    model = _Model(replies=[json.dumps(gated), _chunk_edit("path: src/backend/b.py\n")])
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
    )

    assert rep.skipped == ("n1",) and rep.refactored == ("src/backend/b.py",)
    assert runner.calls.count("apply_refactor") == 1
    assert [argv[1] for argv in runner.argvs["run_make_target.py"]] == ["verify"]
    assert [sorted(spec) for spec in runner.specs] == [["edits", "practice"]]


def _flag(argv, name):
    assert argv.count(name) == 1, argv
    return argv[argv.index(name) + 1]


def test_each_apply_is_bound_to_the_chunks_own_file(tmp_path, monkeypatch):
    nodes = _NODES + [
        {"node_id": "n3", "path": "", "text_excerpt": "x3", "visibility": "internal"}
    ]
    runner = _Runner(nodes=nodes)
    model = _Model(
        replies=[
            _chunk_edit("path: src/backend/a.py\n"),
            _chunk_edit("path: src/backend/b.py\n"),
            _chunk_edit("path: src/backend/a.py\n"),
        ]
    )
    _patch(monkeypatch, runner, model)

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=_files(tmp_path),
        checkpointer=_checkpointer(tmp_path),
        gate="verify",
    )

    applies = runner.argvs["apply_refactor.py"]
    assert [_flag(a, "--allow") for a in applies] == [
        "src/backend/a.py",
        "src/backend/b.py",
    ]
    assert [_flag(a, "--gate") for a in applies] == ["verify", "verify"]
    # A chunk with no path cannot be bound, and has no file whose level can
    # be read now, so the walk drops it: no candidate, no model call, never
    # applied.
    assert rep.candidates == ("n1", "n2") and rep.skipped == ()
    assert len(applies) == 2 and model.n == 2


def test_no_matching_nodes_reports_empty_candidates(monkeypatch):
    runner, model = _Runner(nodes=[]), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor("no-such-practice-id")

    assert rep.candidates == () and rep.preview == ""
    assert rep.baseline_green is True  # baseline still gated honestly


@pytest.mark.parametrize("engine", ["inprocess", "langgraph"])
def test_crash_mid_refactor_resumes_without_reapplying(engine, tmp_path, monkeypatch):
    if engine == "langgraph":
        pytest.importorskip("langgraph")
    (tmp_path / "wiki").mkdir()
    _files(tmp_path)

    runner = _Runner()
    calls = {"n": 0}

    class _Crashy:
        name = "crashy"

        def run(self, prompt):
            calls["n"] += 1
            if calls["n"] == 2:  # SIGKILL-ish on the 2nd chunk's propose
                raise RuntimeError("crash mid-refactor")
            return _chunk_edit(prompt)

    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: _Crashy())

    with pytest.raises(RuntimeError):
        refactor(
            "precise-container-types",
            execute=True,
            max_model_calls=8,
            root=str(tmp_path),
            runtime=engine,
            run_key="job",
        )
    assert calls["n"] == 2  # chunk0 applied, chunk1 in flight

    rep = refactor(
        "precise-container-types",
        execute=True,
        max_model_calls=8,
        root=str(tmp_path),
        runtime=engine,
        run_key="job",
    )
    assert rep.refactored == (
        "src/backend/a.py",
        "src/backend/b.py",
    )  # both chunks done
    assert calls["n"] == 3  # only the in-flight chunk retried
    # chunk0 was NOT re-applied: 1 apply on the first run + 1 on resume == 2 total
    assert runner.calls.count("apply_refactor") == 2


def test_cli_entrypoint_dry_run_reports_candidates_as_json(
    tmp_path, monkeypatch, capsys
):
    # The thin scripts/ doer behind the practice-refactor skill: it must drive the
    # agent and stay a pass-through (no logic of its own).
    sys.path.insert(0, str(_ROOT / "scripts"))
    import refactor_practice as rp  # noqa: E402

    _patch(monkeypatch, _Runner(), _Model())
    # dry-run by default
    rc = rp.main(["precise-container-types", "--json", "--root", _files(tmp_path)])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["practice"] == "precise-container-types"
    assert out["candidates"] == ["n1", "n2"] and out["dry_run"] is True
    assert out["refactored"] == [] and out["baseline_green"] is True


def test_cli_entrypoint_reports_an_unavailable_model_as_a_skip(monkeypatch, capsys):
    """The model-absent path (documentation-quality plan, phase 6): a doer that
    cannot run its model says so and exits 0, writing nothing."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import model_budget  # noqa: E402
    import refactor_practice as rp  # noqa: E402
    from models import ModelUnavailable

    # Approved, so the absent model is what this case reaches; the cap itself
    # is tests/unit/scripts/test_agent_spend_cap.py.
    monkeypatch.setattr(model_budget, "cap", lambda root: 8)

    def no_model(*args, **kwargs):
        raise ModelUnavailable("claude binary 'claude' is not on PATH")

    monkeypatch.setattr(rp, "refactor", no_model)
    assert rp.main(["precise-container-types", "--execute"]) == 0
    assert "skipping" in capsys.readouterr().out


class _Recording(_Model):
    """_Model that keeps each prompt it is sent."""

    def __init__(self):
        super().__init__()
        self.prompts = []

    def run(self, prompt):
        self.prompts.append(prompt)
        return super().run(prompt)


@pytest.mark.parametrize("how", reclassify.HOWS)
def test_a_doc_reclassified_after_the_build_never_reaches_a_prompt(
    tmp_path, monkeypatch, how
):
    """The corpus says docs/pubguide.md is public; the file then states a
    stricter level, or none that can be read. The walk asks the level the
    file states now, so no candidate, preview or prompt carries its text, and
    a chunk a saved run queued before the change is declined at propose with
    no model call."""
    nodes = reclassify.public_project(tmp_path, _CODEWORD)
    runner, model = _Runner(nodes=nodes), _Recording()
    _patch(monkeypatch, runner, model)

    def run(store):
        # A fresh store each run, so the second never resumes the first.
        return refactor(
            "precise-container-types",
            execute=True,
            max_model_calls=8,
            root=str(tmp_path),
            checkpointer=FileCheckpointer(str(tmp_path / store)),
        )

    before = run("before")
    # The text reaches a prompt while the file is public, so a leak is seen.
    assert before.candidates and any(_CODEWORD in p for p in model.prompts)
    reclassify.reclassify(tmp_path / reclassify.GUIDE, how)
    model.prompts.clear()
    after = run("after")
    assert after.candidates == () and _CODEWORD not in after.preview
    assert model.prompts == []
    brain = sys.modules[_BRAIN]
    state = {"root": str(tmp_path), "practice": "p", "chunks": nodes, "cursor": 0}
    meter = ModelMeter(None, 8, lambda name: model)
    assert brain._propose(state, meter) == {"spec": None}
    assert model.prompts == []
