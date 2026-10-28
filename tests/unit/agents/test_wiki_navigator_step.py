"""
title: Unit — the wiki navigator's model step runs on an injected backend
kind: tests
layer: n/a
summary: wiki_navigator.synthesize(question, nodes, backend=b) sends b the agent's real answer prompt (its prompt.md preamble, the question and each visible node cited by node_id), never a node outside config/project.json corpus.served_visibilities (a confidential or restricted node, one that states no level or one outside the vocabulary), and returns b's reply stripped; the plan's synthesize step calls the same function, so the eval harness judges the code answer() runs. answer(execute=True) with no approved count of model calls is a ValueError before any step runs; answer(backend_factory=f) builds its one counted backend with f from the model name, so a caller that counts calls across answers (mcp/qa_server.py's session total) sees each one, and with no factory it is models.get_model. A citation whose node names no owner_source carries None, unknown, never `none`. answer(root=r) reads each node's file under r again: in the reviewer's repro, `docs/pubguide.md` reclassified after the corpus build in each of tests/reclassify.py's ways, a dry run's prompt carries neither its summary nor its id, and nothing cites it.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.wiki_navigator import answer, synthesize  # noqa: E402
from models import ModelBackend  # noqa: E402

import reclassify  # noqa: E402

pytestmark = pytest.mark.unit

_NODES = [
    {
        "node_id": "docs/a.md",
        "path": "docs/a.md",
        "summary": "Alpha is the ingest service.",
        "summary_source": "authored",
        "visibility": "internal",
    },
    {
        "node_id": "docs/secret.md",
        "path": "docs/secret.md",
        "summary": "The vault key.",
        "summary_source": "authored",
        "visibility": "confidential",
    },
    {
        "node_id": "docs/r.md",
        "path": "docs/r.md",
        "summary": "Restricted plan.",
        "summary_source": "authored",
        "visibility": "restricted",
    },
]


class _Seen(ModelBackend):
    name = "seen"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return self.reply


def test_synthesize_sends_the_real_prompt_and_strips_the_reply():
    seen = _Seen("  Alpha ingests events [docs/a.md].\n")
    assert synthesize("What is alpha?", _NODES, backend=seen) == (
        "Alpha ingests events [docs/a.md]."
    )
    (prompt,) = seen.prompts
    assert "# Question\nWhat is alpha?" in prompt
    assert "- [authored] docs/a.md (docs/a.md): Alpha is the ingest service." in prompt
    preamble = (_ROOT / "agents" / "wiki_navigator" / "prompt.md").read_text("utf-8")
    assert prompt.startswith(preamble)


def test_synthesize_never_sends_a_confidential_or_restricted_node():
    seen = _Seen("x")
    synthesize("What is the vault key?", _NODES, backend=seen)
    (prompt,) = seen.prompts
    assert "docs/secret.md" not in prompt and "The vault key." not in prompt
    assert "docs/r.md" not in prompt


def test_synthesize_with_nothing_visible_says_so():
    seen = _Seen("x")
    synthesize("q", _NODES[1:], backend=seen)
    assert "(nothing retrieved)" in seen.prompts[0]


@pytest.mark.parametrize(
    "level", [None, "unreadable-readme", "secret"], ids=["unstated", "marker", "typo"]
)
def test_synthesize_never_sends_a_node_outside_the_vocabulary(level):
    """A node that states no level, or one outside the vocabulary, is dropped:
    the old `or "internal"` fallback served it as open."""
    node = dict(_NODES[0], node_id="docs/odd.md", summary="Odd body.")
    if level is None:
        del node["visibility"]
    else:
        node["visibility"] = level
    seen = _Seen("x")
    synthesize("q", [node], backend=seen)
    assert "docs/odd.md" not in seen.prompts[0] and "Odd body." not in seen.prompts[0]


def test_synthesize_reads_the_configured_levels(monkeypatch):
    """With `corpus.served_visibilities` read as `["public"]`, the internal node
    goes too, so the navigator acts on the key rather than a literal of its own."""
    from scripts import config_loader

    monkeypatch.setattr(
        config_loader, "served_visibilities", lambda root: frozenset({"public"})
    )
    seen = _Seen("x")
    synthesize("What is alpha?", _NODES, backend=seen)
    assert "docs/a.md" not in seen.prompts[0]
    assert "(nothing retrieved)" in seen.prompts[0]


def test_synthesize_takes_the_levels_it_is_given():
    seen = _Seen("x")
    synthesize("q", _NODES, backend=seen, served=frozenset({"confidential"}))
    assert "docs/secret.md" in seen.prompts[0] and "docs/a.md" not in seen.prompts[0]


def test_an_execute_answer_with_no_approved_count_is_refused_before_any_step():
    with pytest.raises(ValueError, match="max_model_calls"):
        answer("what is keel?", execute=True, model="fake", corpus="/nonexistent")


def _one_node_corpus(tmp_path):
    node = dict(_NODES[0], kind="doc", title="Alpha", text_excerpt="", tags=["alpha"])
    node.update(owner="alice", owner_source="frontmatter", visibility="public")
    node.update(anchor=None, lineno=None, parent=None, children=[], links=[])
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / node["path"]).write_text("---\nvisibility: public\n---\n", "utf-8")
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"schema_version": 1, "nodes": [node]}), "utf-8")
    return str(path)


def test_an_execute_answer_builds_its_backend_with_the_factory_it_is_given(tmp_path):
    built, seen = [], _Seen("Alpha ingests events [docs/a.md].")

    def factory(name):
        built.append(name)
        return seen

    got = answer(
        "what is alpha",
        execute=True,
        model="fake",
        corpus=_one_node_corpus(tmp_path),
        max_model_calls=1,
        backend_factory=factory,
        root=str(tmp_path),
    )
    assert built == ["fake"] and len(seen.prompts) == 1
    assert got.text == "Alpha ingests events [docs/a.md]." and not got.dry_run


@pytest.mark.parametrize("stored", ["absent", None, "", "frontmatter"])
def test_a_citation_says_unknown_when_its_node_names_no_owner_source(tmp_path, stored):
    """A corpus row with no owner_source says nothing about its owner, so the
    citation's source is None, never `none`, the claim that nothing owns it."""
    path = _one_node_corpus(tmp_path)
    corpus = json.loads(Path(path).read_text("utf-8"))
    if stored == "absent":
        del corpus["nodes"][0]["owner_source"]
    else:
        corpus["nodes"][0]["owner_source"] = stored
    Path(path).write_text(json.dumps(corpus), "utf-8")
    got = answer("what is alpha", corpus=path, root=str(tmp_path))
    assert [c.node_id for c in got.citations] == ["docs/a.md"], got.citations
    want = "frontmatter" if stored == "frontmatter" else None
    assert got.citations[0].owner_source == want


@pytest.mark.parametrize("how", reclassify.HOWS)
def test_a_node_whose_file_now_states_a_stricter_level_is_not_sent(tmp_path, how):
    """The reviewer's repro: the scratch corpus says `docs/pubguide.md` is
    public; once the file is reclassified on disk (*how*), a dry run's
    retrieved context carries neither its summary nor its id."""
    reclassify.public_project(tmp_path, "The pubguide body.")
    corpus = str(tmp_path / "wiki" / "corpus.json")

    def context():
        got = answer("pubguide", corpus=corpus, root=str(tmp_path))
        # The question names the id too, so only the context is searched.
        return got.text.split("# Retrieved context")[1], got.citations

    sent, cited = context()
    # The repro is the leak's shape only if the guide is sent before.
    assert "About pubguide." in sent and "pubguide" in sent and cited
    reclassify.reclassify(tmp_path / reclassify.GUIDE, how)
    sent, cited = context()
    assert "About pubguide." not in sent and "pubguide" not in sent
    assert cited == ()
