// title: Internal link helper
// layer: frontend
// summary: Prefix internal paths with the site base so links work at '/' or '/<repo>/'.
//
// A GitHub Pages *project* site serves under /<repo>/, so every internal link
// must respect import.meta.env.BASE_URL. Pass a root-absolute path ('/wiki',
// '/wiki?id=x'); get back a path under the base. At base '/' it is a no-op.

export const BASE_URL: string = import.meta.env.BASE_URL

export function withBase(path: string): string {
  const root = BASE_URL.replace(/\/$/, '') // '' at root, '/<repo>' on a project page
  return root + (path.startsWith('/') ? path : `/${path}`)
}
