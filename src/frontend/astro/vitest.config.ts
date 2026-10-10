// title: Unit runner configuration
// layer: frontend
// summary: Vitest over this app's own modules (`npm run test:unit`, `make test-fe-unit`).
//
// The include list is explicit so the runner never collects the browser
// journeys under e2e/, and passWithNoTests is stated rather than left to a
// default: a suite that finds no test fails the gate. allowOnly is stated for
// the same reason: the runner otherwise honours a focused test (`.only`)
// whenever CI is unset, skipping the rest of the suite and still exiting 0.
// Not astro's getViteConfig: the modules under test need only
// import.meta.env.BASE_URL, and it would pull astro's own vite into the runner.
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
    passWithNoTests: false,
    allowOnly: false,
  },
})
