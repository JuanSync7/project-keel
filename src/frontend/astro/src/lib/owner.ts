// title: Owner chip label
// layer: frontend
// summary: The owner chip's text; an owner filled from accountability.default_owner is labelled a placeholder, and one whose source the corpus does not name is labelled unknown.
//
// CONVENTIONS §12: owner_source `default` means no README or frontmatter named
// this node's owner, so the name is the project fallback, not a real answer.
// A null owner_source is a corpus row that names no source at all: unknown,
// which is not `none`, the claim that nothing owns the node.

export function ownerLabel(owner: string, ownerSource: string | null): string {
  if (ownerSource === null) return `owner: ${owner} (source unknown)`
  return ownerSource === 'default' ? `owner: ${owner} (default)` : `owner: ${owner}`
}
