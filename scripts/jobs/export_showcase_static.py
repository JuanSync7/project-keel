#!/usr/bin/env python3
"""
title: Export showcase static job
kind: script
layer: n/a
summary: Deterministic: snapshot the showcase API + agent front door to static files so the frontend runs with no backend (static hosting, e.g. GitHub Pages).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
# The read model lives in the domain (src/backend/showcase), reused by the live
# API (api/rest_fastapi/showcase_api.py) and this static export — one source of
# truth, so the snapshot matches the live JSON byte-for-byte in shape.
sys.path.insert(0, os.path.join(ROOT, "src"))


def _write_json(path: str, obj: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Snapshot the showcase read model to static JSON + llms.txt so the "
                    "frontend can run with no backend (static hosting, e.g. GitHub "
                    "Pages). Run after build_corpus + link_corpus.")
    ap.add_argument("--root", default=ROOT, help="repo root (default: this repo)")
    ap.add_argument("--out-dir",
                    default=os.path.join("src", "frontend", "astro", "public"),
                    help="output dir = the frontend's static assets "
                         "(default: src/frontend/astro/public)")
    ap.add_argument("--base-url", default="",
                    help="site base for llms.txt links (e.g. /project_keel); default: relative")
    args = ap.parse_args(argv)

    try:
        from backend.showcase import load_showcase, to_jsonable
    except ImportError as exc:
        # The showcase domain is product-specific; without it there is nothing to
        # snapshot. Skip gracefully (like the optional contract checks) rather than fail.
        sys.stderr.write("export_showcase_static skipped (backend.showcase unavailable: %s)\n" % exc)
        return 0

    sc = load_showcase(args.root)
    out = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(args.root, args.out_dir)
    api = os.path.join(out, "api")

    # 1) Single object/list endpoints — mirror showcase_api.py exactly.
    _write_json(os.path.join(api, "overview.json"), to_jsonable(sc.overview()))
    _write_json(os.path.join(api, "features.json"), to_jsonable(list(sc.features())))
    _write_json(os.path.join(api, "principles.json"), to_jsonable(list(sc.principles())))
    _write_json(os.path.join(api, "models.json"), to_jsonable(list(sc.model_adapters())))
    _write_json(os.path.join(api, "checks.json"), to_jsonable(list(sc.checks())))
    _write_json(os.path.join(api, "setup.json"), to_jsonable(list(sc.setup_steps())))
    _write_json(os.path.join(api, "wiki", "tree.json"), to_jsonable(list(sc.doc_tree())))

    # 2) Per-node detail (incl. rendered markdown) for every corpus node, as one
    #    map the client fetches once. This replaces the dynamic /api/wiki/node?id=
    #    and powers client-side search — there is no server to query on static hosting.
    #    Tradeoff: one file holds the whole corpus (grows linearly; ~1MB for a few
    #    hundred nodes), fetched on the first wiki/search interaction and cached.
    #    Fine while the corpus is repo-bounded; if it ever matters, shard into
    #    per-node files (mirroring /api/wiki/node) + a small separate search index.
    with open(os.path.join(args.root, "wiki", "corpus.json"), encoding="utf-8") as fh:
        corpus = json.load(fh)
    nodes: dict = {}
    for n in corpus.get("nodes", []):
        nid = n.get("node_id")
        detail = sc.node(nid)
        if detail is None:
            continue
        payload = to_jsonable(detail)
        payload["markdown"] = sc.markdown(nid)   # renderable body, baked in
        nodes[nid] = payload
    _write_json(os.path.join(api, "wiki", "nodes.json"), nodes)

    # 3) Agent front door, colocated with the deployed site so it resolves under
    #    the static base (e.g. /project_keel/llms.txt).
    # The corpus-graph link must point at the snapshot file, not the live route.
    for name, text in (("llms.txt", sc.llms_index(args.base_url, tree_url="/api/wiki/tree.json")),
                       ("llms-full.txt", sc.llms_full())):
        p = os.path.join(out, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    rel = os.path.relpath(out, args.root)
    print("wrote static showcase -> %s/ (overview/features/principles/models/checks/setup/tree + "
          "%d nodes in wiki/nodes.json + llms.txt/llms-full.txt)" % (rel, len(nodes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
