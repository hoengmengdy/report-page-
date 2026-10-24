export class APIError extends Error {
  constructor(message: string, public code = 'request_failed', public retryAfter = 0) { super(message) }
}

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try { response = await fetch(url, { credentials: 'same-origin', ...options }) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new APIError('The server is unreachable. Check that the Flask API is running, then try again.')
  }
  let data
  try { data = await response.json() }
  catch { throw new APIError('The server returned an unexpected response. Check that the Flask API is running.') }
  if (!response.ok) {
    // The limiter also adds Retry-After to ordinary permission failures.
    const retry = response.status === 429 || response.status === 503 ? Number(response.headers.get('Retry-After')) : 0
    throw new APIError(data.error?.message || 'Something went wrong. Try again.', data.error?.code, Number.isFinite(retry) && retry > 0 ? retry : 0)
  }
  return data as T
}

export function safeLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined
  if (value.startsWith('/assets/')) return value
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined }
  catch { return undefined }
}

export const formatNumber = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('en-US').format(value)
export const shortNumber = (value: number) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
export const formatDate = (date: string, options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }) => new Date(date.length === 10 ? `${date}T12:00:00` : date).toLocaleDateString('en-US', options)
