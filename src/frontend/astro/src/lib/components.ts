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

const TONE_FALLBACK = 'border-line bg-chip text-muted'
const TONES: Record<string, string> = {
  slate: TONE_FALLBACK,
  teal: 'border-teal/40 bg-teal/10 text-teal',
  green: 'border-teal/40 bg-teal/10 text-teal',
  rose: 'border-bad/40 bg-bad/10 text-bad',
  amber: 'border-line bg-chip text-ink2',
  indigo: 'border-teal/40 bg-teal/10 text-teal',
}

export function chip(text: string, tone = 'slate'): HTMLElement {
  return h('span',
    { class: `inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${TONES[tone] ?? TONE_FALLBACK}` },
    text)
}

export function featureCard(f: Feature): HTMLElement {
  return h('article', { class: 'rounded-xl border border-line bg-panel p-6 transition-colors hover:border-teal/30' },
    h('div', { class: 'flex items-center gap-3' },
      h('span', { class: 'grid h-9 w-9 place-items-center rounded-lg border border-line bg-panel2 text-base text-teal' },
        ICON[f.icon] ?? '◆'),
      h('h3', { class: 'text-lg font-semibold text-ink' }, f.title),
    ),
    inlineEl('p', 'mt-3 text-sm font-medium text-ink2 [&_code]:font-mono', f.summary),
    inlineEl('p', 'mt-1 text-sm leading-relaxed text-muted [&_code]:font-mono', f.detail),
    f.links.length
      ? h('div', { class: 'mt-4 flex flex-wrap gap-3' },
          f.links.map((l) =>
            h('a', { class: 'font-mono text-[11px] uppercase tracking-wider text-teal hover:underline', href: withBase(`/wiki?id=${encodeURIComponent(l.href)}`) },
              l.label, ' →')))
      : null,
  )
}

// A macOS-style terminal title bar: three traffic-light dots + a label.
function termBar(label: string): HTMLElement {
  const dot = (tone: string) => h('span', { class: `h-2.5 w-2.5 rounded-full ${tone}` })
  return h('div', { class: 'flex items-center gap-1.5 border-b border-line px-3 py-2' },
    dot('bg-term-r'), dot('bg-term-y'), dot('bg-term-g'),
    h('span', { class: 'ml-2 truncate font-mono text-[10px] uppercase tracking-wider text-muted' }, label),
  )
}

export function checkCard(c: Check): HTMLElement {
  const gateTone = c.gate === 'error' ? 'rose' : c.gate === 'warn' ? 'amber' : 'teal'
  return h('article', { class: 'rounded-xl border border-line bg-panel p-6' },
    h('div', { class: 'flex flex-wrap items-center gap-2' },
      h('h3', { class: 'mr-auto text-lg font-semibold text-ink' }, c.name),
      chip(c.gate, gateTone),
      chip(c.interpreter, 'slate'),
      c.present ? chip('present', 'teal') : chip('missing', 'rose'),
    ),
    inlineEl('p', 'mt-3 text-sm leading-relaxed text-ink2 [&_code]:rounded [&_code]:bg-panel2 [&_code]:px-1 [&_code]:font-mono', c.purpose),
    h('div', { class: 'mt-3 font-mono text-xs text-muted' },
      h('span', { class: 'text-muted' }, 'when  '), h('span', { class: 'text-ink2' }, c.when)),
    h('div', { class: 'mt-3 overflow-hidden rounded-lg border border-line bg-panel2' },
      termBar(c.script),
      h('pre', { class: 'overflow-x-auto px-4 py-3 text-xs' },
        h('code', { class: 'font-mono text-ink' },
          h('span', { class: 'text-teal' }, '$ '), c.command))),
  )
}

export function nodeRefLink(ref: NodeRef, onClick: (id: string) => void): HTMLElement {
  const kindTone: Record<string, string> = {
    doc: 'teal', section: 'slate', module: 'green', symbol: 'amber',
  }
  const title = h('span', { class: 'block truncate font-medium text-ink [&_code]:font-mono' })
  title.innerHTML = renderInline(ref.title)
  const a = h('button',
    { class: 'flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-hover', type: 'button' },
    chip(ref.kind, kindTone[ref.kind] ?? 'slate'),
    h('span', { class: 'min-w-0' },
      title,
      ref.path ? h('span', { class: 'block truncate font-mono text-xs text-muted' }, ref.path) : null,
    ),
  )
  a.addEventListener('click', () => onClick(ref.node_id))
  return a
}
