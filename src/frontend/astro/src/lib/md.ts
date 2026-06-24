// title: Markdown renderer
// layer: frontend
// summary: Render a markdown string to sanitized HTML for the wiki node view.
//
// The content is first-party (the repo's own docs, served by our backend), but
// we still sanitize: marked → HTML → DOMPurify. This is the one place HTML is
// injected (everything else uses textContent); callers assign the result to
// innerHTML on a container styled with Tailwind Typography (`prose`).

import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: false })

export function renderMarkdown(md: string): string {
  if (!md) return ''
  const html = marked.parse(md, { async: false })
  return DOMPurify.sanitize(html)
}

// Inline-only render (no <p> wrapper): for titles and summaries that carry
// inline markdown — `code`, **bold**, _em_ — so they don't show raw markers.
export function renderInline(md: string): string {
  if (!md) return ''
  const html = marked.parseInline(md, { async: false })
  return DOMPurify.sanitize(html)
}
