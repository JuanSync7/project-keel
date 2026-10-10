// title: Internal link helper tests
// layer: frontend
// summary: withBase roots a path under the site base exactly once, at '/' and under a sub-path.
//
// links.ts reads import.meta.env.BASE_URL once, when it loads, so each base is
// stubbed and the module re-imported; otherwise every case would test '/'.
import { afterEach, describe, expect, it, vi } from 'vitest'

async function withBaseUnder(base: string): Promise<(path: string) => string> {
  vi.stubEnv('BASE_URL', base)
  vi.resetModules()
  const links = await import('./links')
  expect(links.BASE_URL).toBe(base)
  return links.withBase
}

const PATHS = ['/wiki', 'wiki', '/wiki?id=x', 'a/b/c', '/', '']

// A path as the site root sees it: always absolute.
const rooted = (path: string): string => (path.startsWith('/') ? path : `/${path}`)

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('withBase at the site root', () => {
  it('leaves an absolute path alone and roots a relative one', async () => {
    const withBase = await withBaseUnder('/')
    for (const path of PATHS) {
      expect(withBase(path)).toBe(rooted(path))
    }
  })
})

describe.each(['/sub/', '/sub'])('withBase under the base %j', (base) => {
  it('prefixes every path with the base exactly once and no doubled slash', async () => {
    const withBase = await withBaseUnder(base)
    for (const path of PATHS) {
      const out = withBase(path)
      expect(out.startsWith('/sub/')).toBe(true)
      expect(out.split('/sub').length - 1).toBe(1)
      expect(out).not.toContain('//')
      expect(out.endsWith(rooted(path))).toBe(true)
    }
  })

  it('maps the root and the empty path to the base with its trailing slash', async () => {
    const withBase = await withBaseUnder(base)
    expect(withBase('/')).toBe('/sub/')
    expect(withBase('')).toBe('/sub/')
  })
})
