// FE-side mirror of the backend `shared` contract (Python: src/shared).
// In a TS-backed project, GENERATE these from the shared contract or
// OpenAPI instead of hand-writing them — keep one source of truth.
export interface Thing {
  readonly name: string
  readonly value: number
}
