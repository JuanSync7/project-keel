// title: Showcase UI components
// layer: frontend
// summary: Reusable client-side DOM builders for the showcase pages (uses dom.h).

import type { Check, Feature, NodeRef } from './api'
import { h } from './dom'
import { withBase } from './links'
import { renderInline } from './md'

const ICON: Record<string, string> = {
  check: '✓', tree: '⊞', boundary: '⊟', plug: '⌁',
  brain: '◐', layers: '≡', robot: '⌬', flow: '⎇', loop: '↻',
  generic: '⊛',
}

// A text element whose inline markdown (`code`, **bold**, _em_) is rendered to
// sanitized HTML — so backend-provided text never shows raw markdown markers.
export function inlineEl(tag: string, cls: string, md: string): HTMLElement {
  const el = h(tag, { class: cls })
  el.innerHTML = renderInline(md)
  return el
}

export function statCard(value: number | string, label: string): HTMLElement {
  return h('div', { class: 'rounded-xl border border-slate-200 bg-white p-5' },
    h('div', { class: 'text-3xl font-bold tracking-tight tabular-nums' }, String(value)),
    h('div', { class: 'mt-1 text-sm text-slate-500' }, label),
  )
}

const TONE_FALLBACK = 'bg-slate-100 text-slate-600'
const TONES: Record<string, string> = {
  slate: TONE_FALLBACK,
  green: 'bg-emerald-100 text-emerald-700',
  rose: 'bg-rose-100 text-rose-700',
  amber: 'bg-amber-100 text-amber-700',
  indigo: 'bg-indigo-100 text-indigo-700',
}

export function chip(text: string, tone = 'slate'): HTMLElement {
  return h('span',
    { class: `inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone] ?? TONE_FALLBACK}` },
    text)
}

export function featureCard(f: Feature): HTMLElement {
  return h('article', { class: 'rounded-xl border border-slate-200 bg-white p-6 transition-shadow hover:shadow-sm' },
    h('div', { class: 'flex items-center gap-3' },
      h('span', { class: 'grid h-9 w-9 place-items-center rounded-lg bg-slate-900 text-base text-white' },
        ICON[f.icon] ?? '◆'),
      h('h3', { class: 'text-lg font-semibold' }, f.title),
    ),
    inlineEl('p', 'mt-3 text-sm font-medium text-slate-700 [&_code]:font-mono', f.summary),
    inlineEl('p', 'mt-1 text-sm leading-relaxed text-slate-500 [&_code]:font-mono', f.detail),
    f.links.length
      ? h('div', { class: 'mt-4 flex flex-wrap gap-2' },
          f.links.map((l) =>
            h('a', { class: 'text-xs font-medium text-indigo-600 hover:underline', href: withBase(`/wiki?id=${encodeURIComponent(l.href)}`) },
              l.label, ' →')))
      : null,
  )
}

export function checkCard(c: Check): HTMLElement {
  const gateTone = c.gate === 'error' ? 'rose' : c.gate === 'warn' ? 'amber' : 'slate'
  return h('article', { class: 'rounded-xl border border-slate-200 bg-white p-6' },
    h('div', { class: 'flex flex-wrap items-center gap-2' },
      h('h3', { class: 'mr-auto text-lg font-semibold' }, c.name),
      chip(c.gate, gateTone),
      chip(c.interpreter, 'indigo'),
      c.present ? chip('present', 'green') : chip('missing', 'rose'),
    ),
    inlineEl('p', 'mt-3 text-sm leading-relaxed text-slate-600 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1', c.purpose),
    h('div', { class: 'mt-4 grid gap-2 text-sm sm:grid-cols-2' },
      h('div', null, h('span', { class: 'text-slate-400' }, 'When  '), h('span', { class: 'text-slate-600' }, c.when)),
      h('div', null, h('span', { class: 'text-slate-400' }, 'Script  '), h('code', { class: 'font-mono text-xs text-slate-700' }, c.script)),
    ),
    h('pre', { class: 'mt-3 overflow-x-auto rounded-lg bg-slate-900 px-4 py-2.5 text-xs text-slate-100' },
      h('code', { class: 'font-mono' }, c.command)),
  )
}

export function nodeRefLink(ref: NodeRef, onClick: (id: string) => void): HTMLElement {
  const kindTone: Record<string, string> = {
    doc: 'indigo', section: 'slate', module: 'green', symbol: 'amber',
  }
  const title = h('span', { class: 'block truncate font-medium text-slate-800 [&_code]:font-mono' })
  title.innerHTML = renderInline(ref.title)
  const a = h('button',
    { class: 'flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-100', type: 'button' },
    chip(ref.kind, kindTone[ref.kind] ?? 'slate'),
    h('span', { class: 'min-w-0' },
      title,
      ref.path ? h('span', { class: 'block truncate font-mono text-xs text-slate-400' }, ref.path) : null,
    ),
  )
  a.addEventListener('click', () => onClick(ref.node_id))
  return a
}
