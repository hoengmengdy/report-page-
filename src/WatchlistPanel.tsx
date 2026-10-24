import { useState } from 'react'
import { ArrowRight, CheckCircle2, ExternalLink, Facebook, Link2, LockKeyhole, Search } from 'lucide-react'
import { safeLink } from './api'
import type { TrackedPage, Watchlist } from './types'

export default function WatchlistPanel({ watchlist, loading, error, retry, choose }: {
  watchlist: Watchlist | null; loading: boolean; error: string | null; retry: () => void; choose: (page: TrackedPage) => void
}) {
  const [search, setSearch] = useState('')
  const pages = (watchlist?.pages || []).filter(page => `${page.label} ${page.url}`.toLowerCase().includes(search.toLowerCase()))
  const active = watchlist?.pages.filter(page => page.status === 'active').length || 0
  return <section className="panel watchlist-panel" aria-busy={loading}>
    <div className="panel-heading"><div><h2>Saved Facebook Pages <span className="count-badge">{watchlist?.count || 0}</span></h2><p>Choose a Page URL, then connect it through Facebook Login.</p></div><span className="watchlist-active-count"><CheckCircle2 size={14} />{active} active</span></div>
    <div className="watchlist-notice"><LockKeyhole size={17} /><p>{watchlist?.demo ? 'Demo mode is active. These saved Pages have no live analytics connected. Sample charts belong only to fictional Verdant Studio.' : 'Saving a URL does not grant access to its Insights. Only the currently authorized Page supplies dashboard analytics.'}</p></div>
    <div className="table-toolbar"><span className="watchlist-count">{pages.length} of {watchlist?.count || 0} saved URLs</span><label className="post-search"><Search size={15} /><input aria-label="Search saved Pages" placeholder="Search by Page ID or URL…" value={search} onChange={event => setSearch(event.target.value)} /></label></div>
    {error && <div className="watchlist-error" role="alert"><p>{error}</p><button className="button button-white" onClick={retry}>Retry list</button></div>}
    {loading && !watchlist && <div className="table-empty" role="status">Loading your saved Pages…</div>}
    <div className="watchlist-rows">{pages.map((page, index) => <article className="watchlist-row" key={page.identity}>
      <span className="watchlist-number">{index+1}</span><span className="facebook-tile"><Facebook size={19} /></span>
      <div className="watchlist-page"><h3>{page.label}</h3><a href={safeLink(page.url)} target="_blank" rel="noreferrer">{page.url.replace('https://www.', '')}<ExternalLink size={11} /></a></div>
      <span className={`watchlist-status ${page.status === 'active' ? 'watchlist-status-active' : ''}`}>{page.status === 'active' ? <CheckCircle2 size={12} /> : <LockKeyhole size={12} />}{page.status === 'active' ? 'Active Page' : page.status === 'public_only' ? 'Public metadata only' : 'Not connected'}</span>
      <button className="button button-white watchlist-use" onClick={() => choose(page)} aria-label={`Use ${page.label}`}><Link2 size={13} />Use Page<ArrowRight size={13} /></button>
    </article>)}</div>
    {!loading && !error && !pages.length && <div className="table-empty"><Search size={25} /><h3>No matching Pages</h3><p>Try another Page ID or username.</p></div>}
    <div className="post-count-note">{watchlist?.note || 'Saved URLs only. Facebook permissions are required to retrieve real analytics.'}</div>
  </section>
}
