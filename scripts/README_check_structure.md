---
title: check_structure.py
kind: script
layer: n/a
status: template
owner: TBD
summary: Enforces the CONVENTIONS.md labeling + boundary rules.
id: scripts-readme-check-structure
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---
# check_structure.py

Makes the conventions self-enforcing. `python3 scripts/check_structure.py`
(or `make check`) fails with a non-zero exit if any of these drift:

- **Frontmatter** — every `README.md`/`CLAUDE.md` (and `docs/**`,
  `test-docs/**` markdown) has the required keys with valid
  `kind`/`layer`/`status` values.
- **Documented dirs** — every taxonomy directory that exists carries
  both a `README.md` and a `CLAUDE.md`.
- **Package boundary** — every `src/` dir with `.py` files has an
  `__init__.py` that defines `__all__`.
- **`__init__` is the API** — no code does an absolute import of another
  package's `_private` module; callers go through the public API.

Warnings (e.g. a missing `owner`) are printed but do not fail the build.
Stdlib only; runs on Python 3.6+.
