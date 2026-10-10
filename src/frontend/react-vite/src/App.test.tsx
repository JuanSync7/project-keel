// title: App render tests
// layer: frontend
// summary: The app's first render shows the starting count and the button that raises it.
//
// Rendered to static markup so the runner needs no DOM; the click itself is
// the browser journey's job (e2e/counter.spec.ts).
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { App } from './index'

// The text a reader sees: tags and React's text separators removed.
const text = (html: string): string => html.replace(/<!-- -->/g, '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

describe('App', () => {
  const markup = renderToStaticMarkup(<App />)

  it('renders the starting count in its one heading', () => {
    const headings = markup.match(/<h1[^>]*>[\s\S]*?<\/h1>/g) ?? []
    expect(headings).toHaveLength(1)
    expect(text(headings[0] ?? '')).toBe('hello: 0')
  })

  it('renders a button labelled increment', () => {
    const buttons = markup.match(/<button[^>]*>[\s\S]*?<\/button>/g) ?? []
    expect(buttons.map(text)).toEqual(['increment'])
    expect(buttons[0]).toContain('type="button"')
  })
})
