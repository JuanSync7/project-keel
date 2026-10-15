// title: Browser journey configuration
// layer: frontend
// summary: Playwright, headless, against this app's BUILT site (`npm run test:e2e`, `make test-fe-e2e`).
//
// Every tunable value comes from config/project.json layers.frontend.journey:
// the loopback host and port the preview server binds, how long to wait for
// it, and an optional browser to launch instead of the runner's own cache. A
// missing or mistyped key throws here, naming it. The port is never reused: a
// server already on it fails the run rather than being tested in its place.
// The loader is repeated in each stack's config on purpose: check_H warns on a
// directory under src/frontend that is not a stack, so there is no shared home.
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const KEY = 'layers.frontend.journey'
// TCP port numbers are 16-bit.
const MAX_PORT = 2 ** 16 - 1

interface Journey {
  host: string
  port: number
  server_timeout_ms: number
  browser_executable: string | null
}

// An IPv6 literal (`::1`) takes brackets in a URL but not as the preview
// server's --host, so the URL and the command spell the host differently.
function urlHost(host: string): string {
  return host.includes(':') ? `[${host}]` : host
}

function findManifest(start: string): string {
  for (let dir = start; ; dir = dirname(dir)) {
    const candidate = join(dir, 'config', 'project.json')
    if (existsSync(candidate)) return candidate
    if (dirname(dir) === dir) {
      throw new Error(`no config/project.json above ${start}: the browser journey reads ${KEY} from it`)
    }
  }
}

function loadJourney(): Journey {
  const manifest = findManifest(dirname(fileURLToPath(import.meta.url)))
  const parsed: unknown = JSON.parse(readFileSync(manifest, 'utf-8'))
  let block: unknown = parsed
  for (const segment of KEY.split('.')) {
    block =
      typeof block === 'object' && block !== null
        ? (block as Record<string, unknown>)[segment]
        : undefined
  }
  if (typeof block !== 'object' || block === null) {
    throw new Error(`${manifest}: ${KEY} is missing or not an object`)
  }
  const j = block as Record<string, unknown>
  const fail = (key: string, want: string): never => {
    throw new Error(`${manifest}: ${KEY}.${key} must be ${want}, got ${JSON.stringify(j[key])}`)
  }
  const { host, port, server_timeout_ms, browser_executable } = j
  if (typeof host !== 'string' || host === '') return fail('host', 'a non-empty string')
  // Checked here so a host no URL can hold fails naming the key, not later as
  // a bare ERR_INVALID_URL.
  if (!URL.canParse(`http://${urlHost(host)}/`)) {
    return fail('host', 'a host name or an IP address, an IPv6 one without brackets')
  }
  if (typeof port !== 'number' || !Number.isInteger(port) || port < 1 || port > MAX_PORT) {
    return fail('port', `an integer from 1 to ${String(MAX_PORT)}`)
  }
  if (typeof server_timeout_ms !== 'number' || !Number.isInteger(server_timeout_ms) || server_timeout_ms < 1) {
    return fail('server_timeout_ms', 'a positive integer')
  }
  if (browser_executable !== null && typeof browser_executable !== 'string') {
    return fail('browser_executable', 'null or a path')
  }
  return { host, port, server_timeout_ms, browser_executable }
}

const journey = loadJourney()
const baseURL = `http://${urlHost(journey.host)}:${String(journey.port)}`

export default defineConfig({
  testDir: 'e2e',
  testMatch: '*.spec.ts',
  // Under node_modules/.cache: ignored by git and skipped by every tree walker,
  // so a failing run's traces leave the tree clean.
  outputDir: 'node_modules/.cache/browser-journey',
  reporter: 'list',
  retries: 0,
  forbidOnly: true,
  workers: 1,
  use: {
    baseURL,
    headless: true,
    launchOptions:
      journey.browser_executable === null ? {} : { executablePath: journey.browser_executable },
  },
  // package.json test:e2e:browsers (`make fe-browsers`) downloads this same
  // browser; change the two together.
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // --strictPort: vite preview otherwise moves to the next free port and the
    // run would wait on a URL nothing serves.
    command: `npm run build && npm run preview -- --host ${journey.host} --port ${String(journey.port)} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: journey.server_timeout_ms,
  },
})
