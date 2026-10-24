import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'

afterEach(() => vi.unstubAllGlobals())

it.each([[403, 0], [401, 0], [429, 60], [503, 60]])('only applies a retry cooldown to temporary failures (HTTP %s)', async (status, retryAfter) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'Page access failed', code: 'test_error' } }), {
    status, headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
  })))
  await expect(api('/api/facebook/connect')).rejects.toMatchObject({ message: 'Page access failed', retryAfter })
})

it.each([200, 404])('identifies an HTML response from a missing production API route (HTTP %s)', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<!doctype html><html>Dashboard</html>', {
    status, headers: { 'Content-Type': 'text/html; charset=utf-8' },
  })))
  await expect(api('/api/session')).rejects.toMatchObject({ code: 'api_not_configured', message: expect.stringContaining('/api route') })
})

it('identifies the plain-text 404 returned by Vercel when no API endpoint is deployed', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('The page could not be found\nNOT_FOUND', {
    status: 404, headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  })))
  await expect(api('/api/session')).rejects.toMatchObject({ code: 'api_not_configured' })
})

it('preserves a JSON 404 error returned by the Flask API', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
    message: 'This PDF export is unavailable.', code: 'export_not_found',
  } }), { status: 404, headers: { 'Content-Type': 'application/json' } })))
  await expect(api('/api/facebook/export/jobs/missing')).rejects.toMatchObject({ code: 'export_not_found' })
})
