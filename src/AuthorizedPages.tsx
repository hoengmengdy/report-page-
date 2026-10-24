import { useEffect, useId, useState } from 'react'
import { Facebook, LoaderCircle, RefreshCw } from 'lucide-react'
import { api } from './api'
import type { Page } from './types'

type PageList = { pages: Page[]; next_cursor: string | null; requested_names?: string[] }
const nameKey = (value: string) => value.normalize('NFKC').toLowerCase().replace(/[\s\p{Cf}]/gu, '')

export default function AuthorizedPages({ pageUrl, choose, reconnect, busy }: {
  pageUrl: string; choose: (page: Page) => void; reconnect: () => void; busy: boolean
}) {
  const id = useId()
  const [pages, setPages] = useState<Page[]>([])
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [requestedNames, setRequestedNames] = useState<string[]>([])

  useEffect(() => {
    const abort = new AbortController()
    setLoading(true); setError(null); setPages([])
    async function loadAllPages() {
      const loaded = new Map<string, Page>()
      const seenCursors = new Set<string>()
      let cursor: string | null = null
      for (let batch = 0; batch < 20; batch++) {
        const query = new URLSearchParams({ limit: '100' })
        if (cursor) query.set('after', cursor)
        const data = await api<PageList>(`/api/facebook/pages?${query}`, { signal: abort.signal })
        if (abort.signal.aborted) return
        data.pages.forEach(page => loaded.set(page.id, page))
        setPages([...loaded.values()])
        setRequestedNames(data.requested_names || [])
        if (!data.next_cursor) return
        if (seenCursors.has(data.next_cursor)) throw new Error('Facebook repeated a Page list cursor. Retry to load the complete list.')
        seenCursors.add(data.next_cursor)
        cursor = data.next_cursor
      }
      throw new Error('The Page list is incomplete. Reconnect Facebook with fewer Pages and try again.')
    }
    loadAllPages().catch(value => {
      if (!abort.signal.aborted) setError(value instanceof Error ? value.message : 'Authorized Pages could not be loaded. Try again.')
    }).finally(() => { if (!abort.signal.aborted) setLoading(false) })
    return () => abort.abort()
  }, [revision])

  const selected = pages.find(page => page.url === pageUrl)
  const requestedKeys = new Set(requestedNames.map(nameKey))
  const requestedPages = pages.filter(page => requestedKeys.has(nameKey(page.name)))
  const otherPages = pages.filter(page => !requestedKeys.has(nameKey(page.name)))
  const needsReview = requestedNames.filter(name => pages.filter(page => nameKey(page.name) === nameKey(name)).length !== 1)
  const options = (items: Page[]) => [...items].sort((a, b) => a.name.localeCompare(b.name)).map(page => <option key={page.id} value={page.id}>{page.name} ({page.id})</option>)
  return <section className="authorized-pages" aria-label="Facebook Page access">
    <div className="saved-page-picker">
      <label htmlFor={id}><Facebook size={14} />Authorized Facebook Pages <span className="count-badge">{pages.length}</span></label>
      <select id={id} value={selected?.id || ''} disabled={busy || !pages.length} onChange={event => {
        const page = pages.find(item => item.id === event.target.value)
        if (page) choose(page)
      }}>
        <option value="">{loading && !pages.length ? 'Loading authorized Pages...' : 'Choose a Page Facebook has authorized'}</option>
        {requestedPages.length ? <><optgroup label="Your requested Page names">{options(requestedPages)}</optgroup>{!!otherPages.length && <optgroup label="Other authorized Pages">{options(otherPages)}</optgroup>}</> : options(pages)}
      </select>
      <button className="text-button" disabled={busy} onClick={reconnect}><RefreshCw size={13} />Reconnect Facebook</button>
    </div>
    {loading && <p role="status"><LoaderCircle size={12} className="animate-spin" />Loading all authorized Pages... {pages.length} loaded.</p>}
    {!loading && !error && <p>All {pages.length} authorized Page links loaded. Choose a Page to fill the link field automatically.</p>}
    {!loading && !error && requestedNames.length > 0 && <p>{requestedNames.length - needsReview.length} of {requestedNames.length} requested names have one exact match. Matching names appear first; use the Page ID to distinguish duplicate names.</p>}
    {!loading && !error && needsReview.length > 0 && <details className="requested-page-review"><summary>{needsReview.length} requested names need review</summary><ul>{needsReview.map(name => {
      const matches = pages.filter(page => nameKey(page.name) === nameKey(name))
      return <li key={name}>{name}: {matches.length > 1 ? `${matches.length} authorized Pages share this name; select by ID above.` : 'No exact name match returned by Facebook.'}</li>
    })}</ul></details>}
    {error ? <p role="alert">{error} <button className="text-button" disabled={loading || busy} onClick={() => setRevision(n => n+1)}>Try again</button></p>
      : !loading && <p>{pages.length ? 'Select an authorized Page, then click Connect Page. Insights still depend on your Page permissions.' : 'Facebook has not returned any Pages for this login.'} Missing a Page? Enter its URL, then use Reconnect Facebook to review the Page access you grant.</p>}
  </section>
}
