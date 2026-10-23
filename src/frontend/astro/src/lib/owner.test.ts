// title: Owner chip label tests
// layer: frontend
// summary: ownerLabel marks a default owner as a placeholder and shows every other owner source as it is.
import { describe, expect, it } from 'vitest'
import { ownerLabel } from './owner'

describe('ownerLabel', () => {
  it('marks an owner the corpus filled from accountability.default_owner', () => {
    expect(ownerLabel('platform-team', 'default')).toBe('owner: platform-team (default)')
  })

  it.each(['frontmatter', 'marker', 'inherited'])('shows a %s owner as it is', (source) => {
    expect(ownerLabel('alice', source)).toBe('owner: alice')
  })
})
