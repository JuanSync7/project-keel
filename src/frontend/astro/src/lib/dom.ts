// title: DOM helpers
// layer: frontend
// summary: Tiny, safe hyperscript helpers for client-rendered showcase pages.
//
// Content from the backend is inserted via textContent (never innerHTML), so
// these helpers keep the client islands XSS-safe and typed.

import { API_BASE } from './api'

type Child = Node | string | number | null | undefined | Child[]

export function h(
  tag: string,
  attrs: Record<string, string> | null = null,
  ...children: Child[]
): HTMLElement {
  const node = document.createElement(tag)
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v
      else node.setAttribute(k, v)
    }
  }
  append(node, children)
  return node
}

function append(node: HTMLElement, children: Child[]): void {
  for (const c of children) {
    if (c === null || c === undefined) continue
    if (Array.isArray(c)) append(node, c)
    else if (typeof c === 'string' || typeof c === 'number')
      node.appendChild(document.createTextNode(String(c)))
    else node.appendChild(c)
  }
}

export function mount(target: HTMLElement, ...children: Child[]): void {
  target.replaceChildren()
  append(target, children)
}

export function byId(id: string): HTMLElement {
  const el = document.getElementById(id)
  if (!el) throw new Error(`missing #${id}`)
  return el
}

// Render a friendly "backend offline / empty" panel into a container. The
// hint references the configured base (or the same-origin proxy) — never a
// hardcoded port — so it stays accurate wherever the API is served.
export function showError(target: HTMLElement, err: unknown): void {
  const where = API_BASE ? `the API at ${API_BASE}` : 'the API (same origin, via /api)'
  mount(
    target,
    h('div', { class: 'rounded-xl border border-bad/40 bg-bad/10 p-6 text-sm text-bad' },
      h('p', { class: 'font-medium' }, `Could not reach ${where}.`),
      h('p', { class: 'mt-1 text-ink2' }, String(err instanceof Error ? err.message : err)),
      h('p', { class: 'mt-3 text-ink2' },
        'Start the backend (', h('code', { class: 'font-mono text-ink' }, 'make run-api'),
        ') and confirm the dev-server proxy (API_PROXY_TARGET) or PUBLIC_API_BASE points at it.'),
    ),
  )
}
