// title: Owner chip label tests
// layer: frontend
// summary: ownerLabel marks a default owner as a placeholder, says a null owner source is unknown, and shows every other owner source as it is.
import { describe, expect, it } from 'vitest'
import { ownerLabel } from './owner'

describe('ownerLabel', () => {
  it('marks an owner the corpus filled from accountability.default_owner', () => {
    expect(ownerLabel('platform-team', 'default')).toBe('owner: platform-team (default)')
  })

  it.each(['frontmatter', 'marker', 'inherited'])('shows a %s owner as it is', (source) => {
    expect(ownerLabel('alice', source)).toBe('owner: alice')
  })

  it('says the source is unknown when the node names none, never that it is unowned', () => {
    expect(ownerLabel('alice', null)).toBe('owner: alice (source unknown)')
  })
})
