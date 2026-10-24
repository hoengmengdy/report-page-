import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'

function loadConfig(origin, extraEnv = {}) {
  const env = { ...process.env, ...extraEnv }
  delete env.BACKEND_URL
  if (origin !== undefined) env.BACKEND_URL = origin
  return spawnSync(process.execPath, ['--input-type=module', '-e',
    "const { config } = await import('./vercel.mjs'); process.stdout.write(JSON.stringify(config))"], {
    cwd: new URL('../../', import.meta.url), env, encoding: 'utf8',
  })
}

test('production API requests keep their path on the configured HTTPS backend', () => {
  const result = loadConfig('https://api.example.com/')
  assert.equal(result.status, 0, result.stderr)
  const config = JSON.parse(result.stdout)
  assert.deepEqual(config.rewrites, [{ source: '/api/:path*', destination: 'https://api.example.com/api/:path*' }])
  assert.equal(config.framework, 'vite')
  assert.equal(config.outputDirectory, 'dist')
})

test('a deployment without a backend fails with a useful setup message', () => {
  const result = loadConfig(undefined)
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /Set BACKEND_URL/)
})

test('backend configuration rejects local hosts, incorrect paths, and embedded credentials', () => {
  for (const origin of ['not-a-url', 'http://api.example.com', 'https://localhost',
    'https://127.0.0.1', 'https://[::1]', 'https://api.example.com/api',
    'https://user:private-password@api.example.com', 'https://api.example.com?token=private-token']) {
    const result = loadConfig(origin)
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, /BACKEND_URL must/)
    assert.doesNotMatch(result.stderr, /private-password|private-token/)
  }
})

test('using the website itself as the backend is rejected instead of creating a rewrite loop', () => {
  for (const key of ['VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL']) {
    const result = loadConfig('https://pagepulse.example.com', { [key]: 'pagepulse.example.com' })
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, /not this Vercel frontend/)
  }
})
