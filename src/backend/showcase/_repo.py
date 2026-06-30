"""
title: Showcase repository facade
layer: backend
public_api: yes
summary: Loads the live repo (project facts + corpus) into a Showcase the API renders.
"""
from __future__ import annotations

import json
import os

from . import _content, _data, _llms, _query
from ._models import (
    Check,
    DocGroup,
    Feature,
    Layer,
    ModelAdapter,
    NodeDetail,
    Overview,
    Principle,
    SearchHit,
    Stats,
    Step,
    Transport,
)


class Showcase:
    """A read model of the template as a product, assembled from in-memory data.

    Pure and disk-free: construct it with already-loaded ``project`` and
    ``corpus`` dicts (so unit tests need no filesystem). ``load_showcase`` is the
    thin shell that reads the live repo and builds one. Every accessor returns
    frozen value objects (``_models``) the transport layer serialises as-is.
    """

    def __init__(self, *, name: str, project: dict, corpus: dict,
                 present_scripts: frozenset = frozenset(), root: str = "") -> None:
        self._name = name
        self._project = project or {}
        self._corpus = corpus or {"nodes": []}
        self._present = present_scripts
        self._root = root
        self._by_id = {n["node_id"]: n for n in self._corpus.get("nodes", [])}

    # -- curated narrative ---------------------------------------------------
    def features(self) -> tuple[Feature, ...]:
        """The product features for the features page."""
        return _data.FEATURES

    def principles(self) -> tuple[Principle, ...]:
        """The governing conventions for the conventions page."""
        return _data.PRINCIPLES

    def checks(self) -> tuple[Check, ...]:
        """The deterministic-check catalogue, each flagged present/absent on disk."""
        from dataclasses import replace
        return tuple(replace(c, present=(c.script in self._present))
                     for c in _data.CHECKS)

    def setup_steps(self) -> tuple[Step, ...]:
        """The 'use it in your own project' guide."""
        return _data.SETUP_STEPS

    # -- derived overview ----------------------------------------------------
    def overview(self) -> Overview:
        """Identity + layers + transports + headline counts (live from the repo)."""
        kinds = _query.count_kinds(self._corpus)
        groups = _query.doc_tree(self._corpus)
        stats = Stats(
            docs=kinds.get("doc", 0),
            modules=kinds.get("module", 0),
            sections=kinds.get("section", 0),
            symbols=kinds.get("symbol", 0),
            directories=len(groups),
            checks=len(_data.CHECKS),
        )
        return Overview(
            name=self._name,
            title="project_keel",
            tagline=_data.TAGLINE,
            summary=_data.SUMMARY,
            conventions=_data.CONVENTIONS,
            layers=self._layers(),
            transports=self._transports(),
            stats=stats,
        )

    def _layers(self) -> tuple[Layer, ...]:
        out = []
        for name, spec in (self._project.get("layers") or {}).items():
            if not isinstance(spec, dict):
                continue
            out.append(Layer(
                name=name,
                language=spec.get("language", ""),
                path=spec.get("path") or spec.get("root") or "",
                stack=spec.get("stack") or "",
                available=tuple(spec.get("available", []) or ()),
            ))
        return tuple(out)

    def _transports(self) -> tuple[Transport, ...]:
        t = self._project.get("transports") or {}
        enabled = set(t.get("enabled", []) or [])
        out = []
        for name, directory in sorted((t.get("available") or {}).items()):
            out.append(Transport(name=name, directory=directory,
                                  enabled=name in enabled))
        return tuple(out)

    def model_adapters(self) -> tuple[ModelAdapter, ...]:
        """The model/provider adapters this project makes available (from the manifest).

        Projected from config/project.json's optional ``models`` block (default +
        available) exactly like transports — so the read model stays pure and never
        imports the ``models/`` adapter layer. Empty when the block is absent.
        """
        m = self._project.get("models") or {}
        default = m.get("default")
        out = []
        for name, directory in sorted((m.get("available") or {}).items()):
            out.append(ModelAdapter(name=name, directory=directory,
                                    default=(name == default)))
        return tuple(out)

    # -- corpus navigation (delegates to pure _query) ------------------------
    def doc_tree(self) -> tuple[DocGroup, ...]:
        """Docs grouped by top-level directory, for the wiki sidebar."""
        return _query.doc_tree(self._corpus)

    def node(self, node_id: str) -> NodeDetail | None:
        """One corpus node with its resolved neighbours, or None if unknown."""
        return _query.node_detail(self._corpus, node_id)

    def search(self, query: str, limit: int = 10) -> tuple[SearchHit, ...]:
        """Rank corpus nodes against a free-text query."""
        return _query.search(self._corpus, query, limit)

    def markdown(self, node_id: str) -> str:
        """Return a node's renderable markdown body, read LIVE from its source file.

        Docs return their body (minus frontmatter); sections return their slice;
        modules/symbols return their docstring as a fenced code block. Reading
        on demand (rather than storing bodies in the corpus) keeps the corpus
        small and the content perfectly in sync with the file on disk. Returns
        "" for an unknown node and the corpus excerpt if the file can't be read.
        """
        n = self._by_id.get(node_id)
        if n is None:
            return ""
        rel = n.get("path", "")
        path = os.path.join(self._root, rel) if self._root else rel
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return n.get("text_excerpt", "")
        kind = n.get("kind")
        if kind == "doc":
            return _content.strip_frontmatter(text)
        if kind == "section":
            body = _content.strip_frontmatter(text)
            return _content.section_slice(body, n.get("lineno"))
        if kind == "module":
            # Render the docstring AS markdown (its `backtick` terms become code),
            # not a verbatim fenced block that would show the backticks literally.
            return _content.module_docstring(text)
        if kind == "symbol":
            return _content.symbol_docstring(text, n.get("anchor") or n.get("title", ""))
        return n.get("text_excerpt", "")

    # -- agent front door (llms.txt convention) ------------------------------
    def llms_index(self, base_url: str = "", tree_url: str = "/api/wiki/tree") -> str:
        """Render the llms.txt map (links + summaries) for agents.

        ``tree_url`` overrides the corpus-graph link for a static export
        (``/api/wiki/tree.json``), where the live endpoint does not exist.
        """
        return _llms.render_index(self.overview(), self.doc_tree(), base_url, tree_url)

    def llms_full(self) -> str:
        """Render llms-full.txt: every doc body inlined for one-shot ingestion."""
        docs = [(ref, self.markdown(ref.node_id))
                for g in self.doc_tree() for ref in g.docs]
        return _llms.render_full(self.overview(), docs)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_showcase(root: str) -> Showcase:
    """Read config/project.json + wiki/corpus.json from ``root`` into a Showcase.

    The corpus is a generated view; if it is missing, the Showcase is still
    usable (empty corpus) so the overview/features/checks pages render and the
    operator sees that the index needs rebuilding (scripts/jobs/build_corpus.py).
    """
    project = _read_json(os.path.join(root, "config", "project.json"))
    corpus = _read_json(os.path.join(root, "wiki", "corpus.json"))
    present = frozenset(c.script for c in _data.CHECKS
                        if os.path.isfile(os.path.join(root, c.script)))
    name = project.get("name") or "project_keel"
    return Showcase(name=name, project=project, corpus=corpus,
                    present_scripts=present, root=root)


__all__ = ["Showcase", "load_showcase"]
