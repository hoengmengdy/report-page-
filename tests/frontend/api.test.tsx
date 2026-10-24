import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'

afterEach(() => vi.unstubAllGlobals())

it.each([[403, 0], [401, 0], [429, 60], [503, 60]])('only applies a retry cooldown to temporary failures (HTTP %s)', async (status, retryAfter) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'Page access failed', code: 'test_error' } }), {
    status, headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
  })))
  await expect(api('/api/facebook/connect')).rejects.toMatchObject({ message: 'Page access failed', retryAfter })
})
