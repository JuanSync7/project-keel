// title: Showcase API client
// layer: frontend
// summary: Typed fetch client for the project_keel backend; the FE↔BE contract.
//
// Types mirror the JSON the FastAPI showcase router returns
// (api/rest_fastapi/showcase_api.py → backend.showcase value objects). Keeping
// them here is the single place the frontend states the contract; if the
// backend payload changes, `astro check` flags the drift.

import { withBase } from './links'

export interface Stats {
  readonly docs: number
  readonly modules: number
  readonly sections: number
  readonly symbols: number
  readonly directories: number
  readonly checks: number
}

export interface Layer {
  readonly name: string
  readonly language: string
  readonly path: string
  readonly stack: string
  readonly available: readonly string[]
}

export interface Transport {
  readonly name: string
  readonly directory: string
  readonly enabled: boolean
}

export interface Overview {
  readonly name: string
  readonly title: string
  readonly tagline: string
  readonly summary: string
  readonly conventions: readonly string[]
  readonly layers: readonly Layer[]
  readonly transports: readonly Transport[]
  readonly stats: Stats
}

export interface Link {
  readonly label: string
  readonly href: string
}

export interface Feature {
  readonly slug: string
  readonly title: string
  readonly summary: string
  readonly detail: string
  readonly icon: string
  readonly links: readonly Link[]
}

export interface Check {
  readonly slug: string
  readonly name: string
  readonly script: string
  readonly purpose: string
  readonly gate: string
  readonly interpreter: string
  readonly command: string
  readonly when: string
  readonly present: boolean
}

export interface Step {
  readonly title: string
  readonly body: string
  readonly command: string
}

export interface NodeRef {
  readonly node_id: string
  readonly kind: string
  readonly title: string
  readonly path: string
  readonly summary: string
}

export interface DocGroup {
  readonly directory: string
  readonly docs: readonly NodeRef[]
}

export interface NodeDetail {
  readonly node_id: string
  readonly kind: string
  readonly title: string
  readonly path: string
  readonly summary: string
  readonly excerpt: string
  readonly owner: string
  readonly tags: readonly string[]
  readonly anchor: string
  readonly lineno: number
  readonly parent: NodeRef | null
  readonly children: readonly NodeRef[]
  readonly related: readonly NodeRef[]
  readonly markdown: string
}

export interface SearchHit {
  readonly node: NodeRef
  readonly score: number
}

// Where the backend lives. Default '' = SAME ORIGIN: the client fetches
// relative '/api/...' and the dev server proxies them to the backend (see
// astro.config.mjs `server.proxy`). That keeps the browser talking to one
// origin (no cross-port/CORS/firewall surprises) and bakes no host:port into
// the bundle. Set PUBLIC_API_BASE only to point the browser directly at a
// cross-origin API instead of proxying.
export const API_BASE: string = import.meta.env.PUBLIC_API_BASE ?? ''

// Two data modes, selected at build time:
//   • live  (default; dev) — fetch the FastAPI backend at /api/* (via the proxy).
//   • static (PUBLIC_DATA_MODE=static) — read the build-time snapshot written by
//     scripts/jobs/export_showcase_static.py. No backend, so it works on static
//     hosting (e.g. GitHub Pages). Files live under the site base, which on a
//     project Pages site is /<repo>/ (import.meta.env.BASE_URL).
const STATIC = import.meta.env.PUBLIC_DATA_MODE === 'static'

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { accept: 'application/json' } })
  if (!res.ok) throw new Error(`GET ${url} → ${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

// Pick the live endpoint or the static snapshot file for the same logical call.
// Static files live under the site base (withBase handles '/' vs '/<repo>/').
function get<T>(livePath: string, staticFile: string): Promise<T> {
  return getJSON<T>(STATIC ? withBase(staticFile) : `${API_BASE}${livePath}`)
}

export const getOverview = (): Promise<Overview> =>
  get<Overview>('/api/overview', 'api/overview.json')
export const getFeatures = (): Promise<Feature[]> =>
  get<Feature[]>('/api/features', 'api/features.json')
export const getChecks = (): Promise<Check[]> =>
  get<Check[]>('/api/checks', 'api/checks.json')
export const getSetup = (): Promise<Step[]> =>
  get<Step[]>('/api/setup', 'api/setup.json')
export const getTree = (): Promise<DocGroup[]> =>
  get<DocGroup[]>('/api/wiki/tree', 'api/wiki/tree.json')

// In static mode every node (with its rendered markdown) is baked into one map,
// fetched once and cached. It also backs client-side search — there is no server
// to query on static hosting.
let _nodes: Promise<Record<string, NodeDetail>> | null = null
function nodeMap(): Promise<Record<string, NodeDetail>> {
  if (!_nodes) _nodes = getJSON<Record<string, NodeDetail>>(withBase('api/wiki/nodes.json'))
  return _nodes
}

export async function getNode(id: string): Promise<NodeDetail> {
  if (!STATIC) {
    return getJSON<NodeDetail>(`${API_BASE}/api/wiki/node?id=${encodeURIComponent(id)}`)
  }
  const node = (await nodeMap())[id]
  if (!node) throw new Error(`unknown node ${id}`)
  return node
}

export async function search(q: string, limit = 10): Promise<SearchHit[]> {
  if (!STATIC) {
    return getJSON<SearchHit[]>(`${API_BASE}/api/search?q=${encodeURIComponent(q)}&limit=${limit}`)
  }
  // Static fallback for the backend's ranked keyword search (the full
  // corpus-graph version lives in src/backend/showcase). Kept deliberately close
  // to the API: term overlap over the same fields (title + summary + tags),
  // score rounded the same way, ties broken by node_id, limit clamped to 1..50.
  // It's a presentation-time filter over shipped data, not a second domain rank.
  const cap = Math.min(Math.max(limit, 1), 50)
  const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (terms.length === 0) return []
  const hits: SearchHit[] = []
  for (const n of Object.values(await nodeMap())) {
    const hay = `${n.title} ${n.summary} ${(n.tags ?? []).join(' ')}`.toLowerCase()
    const matched = terms.filter((t) => hay.includes(t)).length
    if (matched === 0) continue
    const score = Math.round((matched / terms.length) * 1e4) / 1e4
    hits.push({
      node: { node_id: n.node_id, kind: n.kind, title: n.title, path: n.path, summary: n.summary },
      score,
    })
  }
  hits.sort((a, b) => b.score - a.score || a.node.node_id.localeCompare(b.node.node_id))
  return hits.slice(0, cap)
}

export async function ping(): Promise<boolean> {
  if (STATIC) return true // no backend to ping; the static snapshot is always "live"
  try {
    const res = await fetch(`${API_BASE}/health`)
    return res.ok
  } catch {
    return false
  }
}
