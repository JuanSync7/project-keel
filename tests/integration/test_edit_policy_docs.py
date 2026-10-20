"""
title: Integration — the docs state the agent edit policy as the code holds it
kind: tests
layer: n/a
summary: The documents a reader meets the agent edit policy in are held to scripts/apply_refactor.py. The tool card whose `public_api` is scripts/apply_refactor.py, and the guide the feature catalogue's edit-policy row links as its deep doc (the one row whose Settings cell names an `agents` key), each name as a code span every config key the policy reads (each scripts/config_loader.py `KEYS` row under apply_refactor's own `agents` block). The symptom table of config/project.json `doc_drift.limits_guide` quotes the words of each refusal plan_edits raises (a protected path, a protected name, a spec that names a gate, an edit outside the run's `--allow` files, a file git does not track, and a root where git cannot say), each rendered by plan_edits itself over a placeholder policy, and the headline main writes when the policy is a config fault. Every expected item is derived from the doer, the loader or the catalogue, never typed here; a derived set of zero items fails, and each rule has a fault-injection twin that removes one item and asserts exactly one finding. Not a writer: it reads the tree and writes only under pytest's tmp_path.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import apply_refactor  # noqa: E402
import config_loader  # noqa: E402
import git_tree  # noqa: E402
from test_doc_drift import _backticked, entry_policy, load_manifest  # noqa: E402
from test_isolation_docs import symptom_section  # noqa: E402
from test_reference_drift import feature_rows  # noqa: E402
from test_tool_card_drift import cards  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.integration

_DOER = Path(apply_refactor.__file__).resolve()
# A markdown link's target: the deep-doc cell of a catalogue row is one link.
_LINK = re.compile(r"\]\(([^)#\s]+)")
# The edges a quoted chunk is cut at: the separators a refusal puts between
# its placeholders.
_EDGES = " :;,()'\"/."
# Placeholders the refusals are rendered with; none is a real path or key.
_DIR, _NAME, _FILE, _ALLOWED, _GATE, _REASON = (
    "<dir>",
    "<name>",
    "<file>",
    "<allowed>",
    "<gate>",
    "<reason>",
)


@pytest.fixture(autouse=True)
def _hermetic_git(tmp_path_factory, monkeypatch):
    """The untracked refusals run git, the doer's own call included, under the
    hermetic git config (the doer copies GIT_CONFIG_* through child_env)."""
    work = tmp_path_factory.mktemp("git-home")
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)


def _rel(path):
    return Path(path).resolve().relative_to(_ROOT).as_posix()


def required_spans():
    """Every config key the policy reads: each loader KEYS row under the
    top-level key apply_refactor's own policy keys sit in."""
    top = apply_refactor._PATHS_KEY[0]
    keys = sorted(".".join(k.path) for k in config_loader.KEYS if k.path[0] == top)
    assert len(keys) >= 3, "%s: %d policy keys in config_loader.KEYS" % (top, len(keys))
    return keys


def span_findings(doc, text, required):
    named = _backticked(text)
    return [
        "%s: does not name `%s`, which the agent edit policy reads" % (doc, item)
        for item in required
        if item not in named
    ]


def reach_docs():
    """{relpath: text} for the tool card over the doer and the guide the
    catalogue's edit-policy row names as its deep doc."""
    required = required_spans()
    doer = _rel(_DOER)
    card = [rel for rel, (api, _text) in cards(_ROOT).items() if api == doer]
    assert len(card) == 1, "%d tool cards wrap %s" % (len(card), doer)
    catalogue = _ROOT / entry_policy(load_manifest(_ROOT))["features_reference"]
    rows, findings = feature_rows(
        _rel(catalogue), catalogue.read_text(encoding="utf-8")
    )
    assert not findings, findings
    matches = [
        r
        for r in rows
        if any(
            span == key or span.startswith(key + ".")
            for span in _backticked(r["Settings"])
            for key in required
        )
    ]
    assert len(matches) == 1, "%s: %d rows name an edit-policy key in Settings" % (
        _rel(catalogue),
        len(matches),
    )
    targets = _LINK.findall(matches[0]["Deep doc"])
    assert len(targets) == 1, matches[0]["Deep doc"]
    docs = [_ROOT / card[0], catalogue.parent / targets[0]]
    return {_rel(d): d.read_text(encoding="utf-8") for d in docs}


def _placeholder_policy():
    rule = lambda key: ((key.casefold(),), key, _REASON)  # noqa: E731
    return apply_refactor.EditPolicy(
        protected_paths=(rule(_DIR),),
        protected_names=(rule(_NAME),),
        editable_names=(),
    )


def _refusal(root, spec, allow=None):
    with pytest.raises(apply_refactor.RefactorError) as refused:
        apply_refactor.plan_edits(spec, str(root), allow, _placeholder_policy())
    return str(refused.value)


def _chunks(message, cuts):
    """Every run of two or more words of *message* between the cuts and the
    `; ` separator."""
    edges = re.compile(
        "|".join(re.escape(c) for c in sorted(cuts, key=len, reverse=True)) + "|; "
    )
    out = []
    for chunk in edges.split(message):
        chunk = chunk.strip(_EDGES)
        if len(chunk.split()) >= 2:
            out.append(chunk)
    return out


def refusal_chunks(root, capsys):
    """The words of each refusal plan_edits raises over a placeholder policy,
    and of the headline main writes for a config fault."""
    edit = lambda path: {"edits": [{"file": path, "content": ""}]}  # noqa: E731
    cuts = ("edit 0", "%s/%s" % (_DIR, _FILE), _DIR, _NAME, _FILE, _ALLOWED)
    cuts += (repr(_GATE), _REASON)
    messages = [
        _refusal(root, edit("%s/%s" % (_DIR, _FILE))),
        _refusal(root, edit(_NAME)),
        _refusal(root, dict(edit(_FILE), gate=_GATE)),
        _refusal(root, edit(_FILE), allow=[_ALLOWED]),
    ]
    # The two untracked refusals need a file that exists: one in a work tree
    # git has not been told to track, one in a root with no repository, whose
    # git failure text is the doer's quote of git and is cut out like a path.
    tree = Path(root) / "tree"
    tree.mkdir()
    (tree / _FILE).write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=str(tree), check=True, env=os.environ)
    messages.append(_refusal(tree, edit(_FILE)))
    loose = Path(root) / "loose"
    loose.mkdir()
    (loose / _FILE).write_text("", encoding="utf-8")
    with pytest.raises(git_tree.NoGitError) as nogit:
        git_tree.tracked(str(loose), [_FILE])
    cuts += (str(nogit.value),)
    messages.append(_refusal(loose, edit(_FILE)))
    chunks = []
    for message in messages:
        for chunk in _chunks(message, cuts):
            if chunk not in chunks:
                chunks.append(chunk)
    # The config-fault headline: main over a root with no config at all.
    bare = Path(root) / "no-config"
    bare.mkdir()
    spec = Path(root) / "spec.json"
    spec.write_text(json.dumps(edit(_FILE)), encoding="utf-8")
    with pytest.raises(config_loader.ConfigError) as fault:
        apply_refactor.load_policy(str(bare))
    capsys.readouterr()
    code = apply_refactor.main(["--spec", str(spec), "--root", str(bare)])
    assert code == apply_refactor.ExitCode.CONFIG, code
    line = capsys.readouterr().err.strip().splitlines()[-1]
    headline = line.split(": " + str(fault.value))[0]
    assert headline != line, line
    chunks.append(headline)
    # A refusal that said nothing would make the symptom rule vacuous.
    assert len(chunks) >= 7, chunks
    for key in (apply_refactor._PATHS_KEY, apply_refactor._NAMES_KEY):
        assert any(".".join(key) in c for c in chunks), (key, chunks)
    return chunks


def symptom_findings(guide, section, chunks):
    return [
        "%s: the symptom table does not quote %r" % (guide, chunk)
        for chunk in chunks
        if chunk not in section
    ]


def _guide_section():
    guide = entry_policy(load_manifest(_ROOT))["limits_guide"]
    return guide, symptom_section((_ROOT / guide).read_text(encoding="utf-8"))


def test_each_document_that_states_the_edit_policy_names_its_keys():
    required = required_spans()
    docs = reach_docs()
    assert len(docs) == 2, sorted(docs)
    findings = [
        f for doc, text in docs.items() for f in span_findings(doc, text, required)
    ]
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize("which", range(2))
def test_dropping_a_policy_key_from_a_document_reds_it(which):
    required = required_spans()
    doc, text = sorted(reach_docs().items())[which]
    item = required[-1]
    assert span_findings(doc, text, required) == [], "the unplanted doc must be clean"
    planted = text.replace("`%s`" % item, item)
    assert planted != text
    findings = span_findings(doc, planted, required)
    assert len(findings) == 1 and item in findings[0], findings


def test_the_troubleshooting_guide_quotes_each_refusal_of_an_agent_edit(
    tmp_path, capsys
):
    guide, section = _guide_section()
    findings = symptom_findings(guide, section, refusal_chunks(tmp_path, capsys))
    assert not findings, "\n".join(findings)


def test_dropping_a_refusal_from_the_troubleshooting_guide_reds_it(tmp_path, capsys):
    guide, section = _guide_section()
    chunks = refusal_chunks(tmp_path, capsys)
    assert symptom_findings(guide, section, chunks) == [], (
        "the unplanted guide must be clean"
    )
    for chunk in chunks:
        planted = section.replace(chunk, "")
        assert planted != section, chunk
        # Removing a chunk also removes any chunk that contains it, so the
        # expected count is derived, never assumed to be one.
        expected = [c for c in chunks if chunk in c or c not in planted]
        findings = symptom_findings(guide, planted, chunks)
        assert len(findings) == len(expected) >= 1, (chunk, findings)
        assert any(repr(chunk) in f for f in findings), (chunk, findings)
