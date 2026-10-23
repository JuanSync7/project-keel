// title: Owner chip label
// layer: frontend
// summary: The owner chip's text; an owner filled from accountability.default_owner is labelled a placeholder.
//
// CONVENTIONS §12: owner_source `default` means no README or frontmatter named
// this node's owner, so the name is the project fallback, not a real answer.

export function ownerLabel(owner: string, ownerSource: string): string {
  return ownerSource === 'default' ? `owner: ${owner} (default)` : `owner: ${owner}`
}
