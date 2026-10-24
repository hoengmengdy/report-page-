import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import {
  Activity, ArrowDown, ArrowDownLeft, ArrowDownToLine, ArrowRight, ArrowUpRight,
  BarChart3, Bell, CalendarDays, Check, CheckCircle2, ChevronDown, ChevronRight,
  CircleHelp, CirclePlay, ExternalLink, Eye, FileBarChart2, FileSpreadsheet,
  FlaskConical, Image, LayoutDashboard, Leaf, Link2, LoaderCircle, LockKeyhole,
  LogOut, Menu, MessageCircle, RefreshCw, Search, Settings2,
  Share2, ShieldCheck, Sparkles, ThumbsUp, TrendingUp, UsersRound, Wallet, X,
} from 'lucide-react'
import {
  Area, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, APIError, formatDate, formatNumber, safeLink, shortNumber } from './api'
import type { Metric, MetricKey, Page, PDFJob, Post, PostsResponse, Report, Session, TrackedPage, Watchlist } from './types'
import WatchlistPanel from './WatchlistPanel'
import AuthorizedPages from './AuthorizedPages'

type View = 'Overview' | 'Content' | 'Audience' | 'Reports' | 'Connections'
type Range = { days: string; since?: string; until?: string }
type ModalName = 'help' | 'settings' | 'dates' | 'notifications' | 'privacy' | 'export' | null
const NAV = [{ name: 'Overview' as const, icon: LayoutDashboard }, { name: 'Content' as const, icon: Image },
  { name: 'Audience' as const, icon: UsersRound }, { name: 'Reports' as const, icon: FileBarChart2 }]
const METRIC_LABELS = { views: 'Total views', interactions: 'Content interactions', followers: 'Total followers' }
const NO_METRIC: Metric = { value: null, previous: null, growth: null, delta: null, status: 'unavailable', reason: 'Connect a Page to see available data.', source_metric: null }

function Logo({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? 'brand-small' : ''}`}><span className="brand-icon"><BarChart3 size={23} strokeWidth={2.4} /></span>{!small && <span>pagepulse<span className="brand-dot">.</span></span>}</div>
}

function FacebookIcon({ size = 18 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.096 10.125 24v-8.437H7.078v-3.49h3.047V9.413c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.972H15.83c-1.49 0-1.955.93-1.955 1.885v2.264h3.328l-.532 3.49h-2.796V24C19.612 23.096 24 18.1 24 12.073Z" /></svg>
}

function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const id = useId()
  const closeRef = useRef(close)
  closeRef.current = close
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.querySelector<HTMLElement>('button, input, a, select')?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current()
      if (event.key === 'Tab') {
        const elements = ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href], [tabindex="0"]')
        if (!elements?.length) return
        const first = elements[0], last = elements[elements.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', keydown); previous?.focus() }
  }, [])
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close() }}>
    <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={id}>
      <div className="modal-heading"><h2 id={id}>{title}</h2><button className="icon-button" onClick={close} aria-label="Close dialog"><X size={20} /></button></div>
      {children}
    </div>
  </div>
}

function Sparkline({ values, color = '#14846a' }: { values: (number | null)[]; color?: string }) {
  const data = values.filter((v): v is number => v !== null)
  if (data.length < 2) return <span className="sparkline-empty">No trend yet</span>
  const min = Math.min(...data), max = Math.max(...data), gap = max-min || 1
  const path = data.map((n, i) => `${i === 0 ? 'M' : 'L'}${i/(data.length-1)*98},${31-(n-min)/gap*25}`).join(' ')
  return <svg className="sparkline" viewBox="0 0 100 38" aria-hidden="true"><path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

function MetricCard({ title, metric, icon, data, accent = false }: { title: string; metric: Metric; icon: ReactNode; data?: (number | null)[]; accent?: boolean }) {
  return <article className={`metric-card ${accent ? 'metric-accent' : ''}`}>
    <div className="metric-label"><span>{title}</span><span className="metric-icon">{icon}</span></div>
    <div className="metric-value">{formatNumber(metric.value)}{metric.status === 'partial' && <span className="partial-tag">Partial</span>}</div>
    <div className="metric-bottom"><div>{metric.growth !== null ? <><span className={`growth ${metric.growth < 0 ? 'growth-down' : ''}`}>{metric.growth < 0 ? <ArrowDownLeft size={13} /> : <ArrowUpRight size={13} />}{Math.abs(metric.growth)}%</span><span className="metric-comparison">vs. previous period</span></> : <span className="metric-comparison" title={metric.reason || undefined}>{metric.value === null ? 'Not available' : 'No comparable period'}</span>}</div>
      {data && metric.value !== null ? <Sparkline values={data} /> : <LockKeyhole size={25} className="metric-lock" />}</div>
  </article>
}

function PerformanceChart({ report, selectedMetric, setMetric, audience = false }: { report: Report | null; selectedMetric: MetricKey; setMetric: (metric: MetricKey) => void; audience?: boolean }) {
  const [compare, setCompare] = useState(true)
  const metric = audience ? 'followers' : selectedMetric
  const available = report?.series.some(row => row[metric] !== null)
  return <section className="panel performance-panel">
    <div className="panel-heading"><div><h2>{audience ? 'Follower growth' : 'Performance overview'}</h2><p>{audience ? 'Your community, day by day.' : 'A closer look at how your content is doing.'}</p></div>
      <span className="subtle-label"><span className="tiny-dot" />Daily</span></div>
    <div className="chart-toolbar">{!audience && <div className="segmented" aria-label="Chart metric">{(['views', 'interactions', 'followers'] as MetricKey[]).map(key => <button key={key} onClick={() => setMetric(key)} className={metric === key ? 'selected' : ''} aria-pressed={metric === key}>{key.charAt(0).toUpperCase()+key.slice(1)}</button>)}</div>}
      <label className="compare-toggle"><input type="checkbox" checked={compare} onChange={e => setCompare(e.target.checked)} /><span>Compare to previous period</span></label></div>
    <div className="chart-legend"><span><i className="legend-line" />{report ? `${formatDate(report.since)} – ${formatDate(report.until)}` : 'Selected period'}</span>{compare && <span><i className="legend-line previous" />Previous period</span>}</div>
    <div className="performance-chart" role="img" aria-label={`Daily ${metric} performance chart${compare ? ' compared with the previous period' : ''}`}>
      {available ? <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ComposedChart data={report!.series} margin={{ top: 12, right: 12, left: -15, bottom: 0 }}>
          <defs><linearGradient id={`chart-fill-${audience ? 'audience' : 'overview'}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#43a68b" stopOpacity={0.2} /><stop offset="100%" stopColor="#43a68b" stopOpacity={0.01} /></linearGradient></defs>
          <CartesianGrid vertical={false} stroke="#edf0ee" strokeDasharray="3 4" />
          <XAxis dataKey="date" tickFormatter={value => formatDate(String(value))} axisLine={false} tickLine={false} minTickGap={42} tick={{ fill: '#89928d', fontSize: 11 }} dy={8} />
          <YAxis tickFormatter={shortNumber} axisLine={false} tickLine={false} tick={{ fill: '#89928d', fontSize: 11 }} tickCount={5} domain={metric === 'followers' ? ['auto', 'auto'] : [0, 'auto']} />
          <Tooltip content={({ active, payload, label }) => active && payload?.length ? <div className="chart-tooltip"><strong>{formatDate(String(label))}</strong>{payload.map(item => <div key={String(item.dataKey)}><span style={{ color: item.color }}>●</span> {item.name}<b>{formatNumber(typeof item.value === 'number' ? item.value : null)}</b></div>)}<small>Previous period is aligned by day</small></div> : null} />
          {compare && <Line type="monotone" name="Previous period" dataKey={`previous_${metric}`} stroke="#adc6bc" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} />}
          <Area type="monotone" name={METRIC_LABELS[metric]} dataKey={metric} stroke="#18846a" strokeWidth={2.5} fill={`url(#chart-fill-${audience ? 'audience' : 'overview'})`} dot={false} activeDot={{ r: 5, fill: '#18846a', stroke: '#fff', strokeWidth: 3 }} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer> : <div className="empty-chart"><Activity size={30} /><h3>No performance data yet</h3><p>{report?.metrics[metric].reason || 'Connect an authorized Page to see its daily performance.'}</p></div>}
    </div>
    <div className="chart-footnote"><ShieldCheck size={13} /><span>{!report ? 'Page analytics appear after an authorized connection' : report.demo ? 'Sample data for demonstration purposes' : 'Available data from the official Meta Graph API'}</span><span className="ml-auto">{report?.series.length || 0} reporting days</span></div>
  </section>
}

function EngagementPanel({ posts }: { posts: Post[] }) {
  const data = [{ name: 'Reactions', value: posts.some(p => p.reactions !== null) ? posts.reduce((sum, p) => sum+(p.reactions || 0), 0) : null, color: '#1e8269', icon: ThumbsUp },
    { name: 'Comments', value: posts.some(p => p.comments !== null) ? posts.reduce((sum, p) => sum+(p.comments || 0), 0) : null, color: '#a0cbbb', icon: MessageCircle },
    { name: 'Shares', value: posts.some(p => p.shares !== null) ? posts.reduce((sum, p) => sum+(p.shares || 0), 0) : null, color: '#dce9e0', icon: Share2 }]
  const total = data.reduce((sum, item) => sum+(item.value || 0), 0)
  const hasCounters = data.some(item => item.value !== null)
  return <section className="panel engagement-panel"><div className="panel-heading"><div><h2>Engagement breakdown</h2><p>How your audience connects.</p></div></div>
    <div className="donut-wrap" role="img" aria-label={data.map(item => `${item.name}: ${item.value}`).join(', ')}>
      <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={total ? data : [{ name: 'No data', value: 1, color: '#edf1ee' }]} dataKey="value" innerRadius={65} outerRadius={83} startAngle={90} endAngle={-270} paddingAngle={total ? 4 : 0} stroke="none" cornerRadius={4}>{(total ? data : [{ color: '#edf1ee' }]).map((item, i) => <Cell key={i} fill={item.color} />)}</Pie></PieChart></ResponsiveContainer>
      <div className="donut-center"><b>{total ? shortNumber(total) : hasCounters ? '0' : '—'}</b><span>interactions</span></div></div>
    <div className="breakdown-list">{data.map(item => <div key={item.name}><span className="breakdown-name"><i style={{ background: item.color }} />{item.name}</span><b>{formatNumber(item.value)}</b><span>{item.value === null ? '—' : `${total ? Math.round(item.value/total*100) : 0}%`}</span></div>)}</div>
    <div className="engagement-note">Available lifetime counters from {posts.length} loaded posts.</div>
  </section>
}

function PostsTable({ data, loading, loadMore, exportPosts, busy }: { data: PostsResponse | null; loading: boolean; loadMore: () => void; exportPosts: () => void; busy: boolean }) {
  const [filter, setFilter] = useState('All content')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'date' | 'views'>('date')
  const posts = [...(data?.posts || [])].filter(p => (filter === 'All content' || p.type === filter) && p.text.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => sort === 'views' ? (b.views ?? -1)-(a.views ?? -1) : String(b.published_at).localeCompare(String(a.published_at)))
  return <section className="panel posts-panel"><div className="panel-heading"><div><h2>Recent content <span className="count-badge">{data?.count ?? data?.posts.length ?? 0}</span></h2><p>Your latest posts, and the conversations they start.</p></div>
      <button className="text-button" onClick={exportPosts} disabled={!data?.posts.length}><ArrowDownToLine size={14} />Export loaded posts</button></div>
    <div className="table-toolbar"><div className="post-filters">{['All content', 'Photo', 'Video', 'Text'].map(item => <button key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item === 'Photo' ? 'Photos' : item === 'Video' ? 'Videos' : item}</button>)}</div>
      <label className="post-search"><Search size={15} /><input aria-label="Search loaded posts" placeholder="Search loaded posts..." value={query} onChange={e => setQuery(e.target.value)} /></label></div>
    <div className="table-scroll"><table><thead><tr><th className="post-cell">Post</th><th>Published</th><th><ThumbsUp size={12} /> Reactions</th><th><MessageCircle size={12} /> Comments</th><th><Share2 size={12} /> Shares</th><th><button className="sort-button" onClick={() => setSort(sort === 'date' ? 'views' : 'date')}>Views <ArrowDown size={12} className={sort === 'views' ? 'text-emerald-700' : ''} /></button></th><th><span className="sr-only">Open post</span></th></tr></thead>
      <tbody>{posts.map(post => <tr key={post.id}><td><div className="post-description"><div className="post-thumbnail">{safeLink(post.picture) ? <img src={safeLink(post.picture)} alt="" loading="lazy" onError={e => { e.currentTarget.style.display = 'none' }} /> : <Leaf size={19} />}{post.type === 'Video' && <span className="video-indicator"><CirclePlay size={16} /></span>}</div><div><p title={post.text}>{post.text}</p><span>{post.type === 'Video' ? <CirclePlay size={11} /> : post.type === 'Photo' ? <Image size={11} /> : <MessageCircle size={11} />}{post.type}</span></div></div></td>
        <td className="post-date">{post.published_at ? formatDate(post.published_at) : '—'}<small>{post.published_at ? formatDate(post.published_at, { year: 'numeric' }) : ''}</small></td><td>{formatNumber(post.reactions)}</td><td>{formatNumber(post.comments)}</td><td>{formatNumber(post.shares)}</td><td className="post-views" title={post.views_reason || 'Lifetime media views'}>{formatNumber(post.views)}</td><td>{safeLink(post.url) ? <a className="icon-button small" href={safeLink(post.url)} target="_blank" rel="noreferrer" aria-label="Open Facebook post"><ArrowUpRight size={15} /></a> : <span className="sample-post-label" title={data?.demo ? 'Fictional sample post' : 'Post link unavailable'}>{data?.demo ? <FlaskConical size={13} /> : '—'}</span>}</td></tr>)}</tbody>
    </table></div>
    {!posts.length && <div className="table-empty"><Search size={25} /><h3>{loading ? 'Loading your content…' : query || filter !== 'All content' ? 'No matching posts' : 'No posts to show'}</h3><p>{query || filter !== 'All content' ? 'Try another filter or search the posts you have loaded.' : 'Posts published in your selected date range will appear here.'}</p></div>}
    <div className="table-footer"><span>Showing {posts.length} of {data?.posts.length || 0} loaded posts{data?.count != null ? ` · ${data.count} total` : ''}</span>{data?.next_cursor && <button className="text-button" disabled={busy || loading} onClick={loadMore}>{loading ? <LoaderCircle size={14} className="animate-spin" /> : null}Load more posts<ChevronRight size={14} /></button>}</div>
    <div className="post-count-note">{data?.counts_note || 'Post counters are lifetime totals for posts published in the selected range.'}</div>
  </section>
}

export default function App() {
  const [view, setView] = useState<View>('Overview')
  const [session, setSession] = useState<Session | null>(null)
  const [watchlist, setWatchlist] = useState<Watchlist | null>(null)
  const [watchlistLoading, setWatchlistLoading] = useState(true)
  const [watchlistError, setWatchlistError] = useState<string | null>(null)
  const [watchlistRevision, setWatchlistRevision] = useState(0)
  const [report, setReport] = useState<Report | null>(null)
  const [posts, setPosts] = useState<PostsResponse | null>(null)
  const [pageUrl, setPageUrl] = useState('')
  const [authorizedChoice, setAuthorizedChoice] = useState<Page | null>(null)
  const [range, setRange] = useState<Range>({ days: '28' })
  const [draftDates, setDraftDates] = useState({ since: '', until: '' })
  const [selectedMetric, setMetric] = useState<MetricKey>('views')
  const [loading, setLoading] = useState(true)
  const [postLoading, setPostLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [pdfJob, setPdfJob] = useState<PDFJob | null>(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState('')
  const [modal, setModal] = useState<ModalName>(null)
  const [mobileNav, setMobileNav] = useState(false)
  const [revision, setRevision] = useState(0)
  const [retryAt, setRetryAt] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const urlRef = useRef<HTMLInputElement>(null)
  const requestGeneration = useRef(0)
  const exportAbort = useRef<AbortController | null>(null)
  const autoLoginAttempted = useRef(false)
  const skipAutoLogin = useRef(new URLSearchParams(window.location.search).has('deletion') || new URLSearchParams(window.location.search).get('auth') === 'error')
  const closeModal = () => setModal(null)
  const page: Page | null = session?.page || null
  const trackedSelection = watchlist?.pages.find(item => item.url === pageUrl)
  const trackedIsCurrent = !!trackedSelection && !session?.demo && !!page && (
    trackedSelection.identity === page.id || trackedSelection.url.toLowerCase().replace(/\/$/, '') === page.url.toLowerCase().replace(/\/$/, ''))
  const pendingTracked = !!trackedSelection && !trackedIsCurrent
  const pendingAuthorized = !!authorizedChoice && authorizedChoice.url === pageUrl && authorizedChoice.id !== page?.id
  const pendingPage = pendingTracked || pendingAuthorized
  const ready = !!session && (session.demo || !!session.page) && !session.public_only && !pendingPage
  const canPdfExport = !!session && (session.demo ? ready && !!report : session.authenticated)
  const queryString = new URLSearchParams(Object.entries(range).filter(([,v]) => v !== undefined) as [string, string][]).toString()
  const rangeRef = useRef(queryString)
  rangeRef.current = queryString

  function showError(value: unknown) {
    if (value instanceof DOMException && value.name === 'AbortError') return
    setError(value instanceof Error ? value.message : 'Something went wrong. Please try again.')
    if (value instanceof APIError && value.retryAfter) setRetryAt(Date.now()+value.retryAfter*1000)
    if (value instanceof APIError && ['reauthorize', 'login_required'].includes(value.code)) {
      setSession(current => current && !current.demo ? { ...current, authenticated: false, page: null } : current)
      setReport(null); setPosts(null)
    }
  }

  useEffect(() => {
    const abort = new AbortController()
    api<Session>('/api/session', { signal: abort.signal }).then(data => {
      setSession(data); setPageUrl(data.page?.url || ''); setLoading(false)
      if (data.login_error) setError(data.login_error)
      const params = new URLSearchParams(window.location.search)
      if (params.has('auth')) {
        window.history.replaceState({}, '', window.location.pathname)
        if (params.get('auth') === 'connected') setToast('Your Facebook Page is connected.')
        if (params.get('auth') === 'authorized') setToast('Your Facebook account is connected. Loading all authorized Page links.')
      }
      if (params.has('deletion')) api<{ message: string }>(`/api/deletion-status/${encodeURIComponent(params.get('deletion')!)}`).then(result => { setToast(result.message); setModal('privacy') }).catch(showError)
    }).catch(err => { if (!abort.signal.aborted) { showError(err); setLoading(false) } })
    return () => abort.abort()
  }, [])

  useEffect(() => {
    if (!session || autoLoginAttempted.current) return
    autoLoginAttempted.current = true
    if (session.demo || session.authenticated || session.login_error || skipAutoLogin.current) return
    // Attempt once per tab so cancelled or failed login never creates a redirect loop.
    try {
      if (window.sessionStorage.getItem('pagepulse-auto-login')) return
      window.sessionStorage.setItem('pagepulse-auto-login', 'attempted')
    } catch { /* The component guard still prevents duplicate requests when storage is unavailable. */ }
    void connect(false, true, true)
  }, [session])

  useEffect(() => {
    if (!ready) { setReport(null); setPosts(null); setLoading(false); return }
    const abort = new AbortController()
    const generation = ++requestGeneration.current
    setLoading(true); setPostLoading(false); setReport(null); setPosts(null)
    Promise.allSettled([
      api<Report>(`/api/facebook/insights?${queryString}${revision ? '&refresh=1' : ''}`, { signal: abort.signal }),
      api<PostsResponse>(`/api/facebook/posts?${queryString}&limit=6`, { signal: abort.signal }),
    ]).then(results => {
      if (abort.signal.aborted || generation !== requestGeneration.current) return
      const authFailure = results.find(result => result.status === 'rejected' && result.reason instanceof APIError && ['reauthorize', 'login_required'].includes(result.reason.code))
      if (authFailure?.status === 'rejected') {
        showError(authFailure.reason); setLoading(false); return
      }
      if (results[0].status === 'fulfilled') setReport(results[0].value); else showError(results[0].reason)
      if (results[1].status === 'fulfilled') setPosts(results[1].value); else showError(results[1].reason)
      setLoading(false)
    })
    return () => { abort.abort(); requestGeneration.current++ }
  }, [ready, session?.page?.id, queryString, revision])

  useEffect(() => {
    if (!session) return
    const abort = new AbortController()
    setWatchlistLoading(true); setWatchlistError(null)
    api<Watchlist>('/api/facebook/watchlist', { signal: abort.signal }).then(data => {
      if (!abort.signal.aborted) setWatchlist(data)
    }).catch(err => {
      if (!abort.signal.aborted) setWatchlistError(err instanceof Error ? err.message : 'The saved Pages could not be loaded.')
    }).finally(() => { if (!abort.signal.aborted) setWatchlistLoading(false) })
    return () => abort.abort()
  }, [!!session, session?.authenticated, session?.page?.id, watchlistRevision])

  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(''), 6000); return () => clearTimeout(timer) }, [toast])
  useEffect(() => () => exportAbort.current?.abort(), [])
  useEffect(() => {
    if (!retryAt) return
    const tick = () => setSeconds(Math.max(0, Math.ceil((retryAt-Date.now())/1000)))
    tick(); const timer = window.setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [retryAt])

  async function connect(reauthorize = false, accountOnly = false, autoConnect = false) {
    if (!session) { setRevision(n => n+1); window.location.reload(); return }
    if (session.demo && trackedSelection && !accountOnly) {
      setToast('This saved Page is selected. Configure your Meta app and Facebook Login to retrieve its real analytics. No data has been fetched for this Page.')
      setModal('help')
      return
    }
    setConnecting(true); setError(null)
    try {
      const data = await api<{ authorization_url?: string; page?: Page; demo?: boolean; authenticated?: boolean; public_only?: boolean; message?: string }>('/api/facebook/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify(accountOnly ? { account_only: true, reauthorize, auto_connect: autoConnect } : { page_url: pageUrl, reauthorize }),
      })
      if (data.authorization_url) { window.location.assign(data.authorization_url); return }
      if (data.page) {
        setSession(current => current ? { ...current, page: data.page!, authenticated: data.authenticated ?? current.authenticated, public_only: !!data.public_only } : current)
        setPageUrl(data.page.url); setReport(null); setPosts(null); setRevision(n => n+1)
      }
      if (data.message) setToast(data.message)
    } catch (err) { showError(err) }
    finally { setConnecting(false) }
  }

  async function loadMore() {
    if (!posts?.next_cursor) return
    const capturedQuery = queryString, generation = requestGeneration.current
    setPostLoading(true)
    try {
      const data = await api<PostsResponse>(`/api/facebook/posts?${queryString}&limit=6&after=${encodeURIComponent(posts.next_cursor)}`)
      if (rangeRef.current !== capturedQuery || generation !== requestGeneration.current) return
      setPosts(current => current ? { ...data, posts: [...current.posts, ...data.posts.filter(p => !current.posts.some(old => old.id === p.id))] } : data)
    } catch (err) { showError(err) }
    finally { if (generation === requestGeneration.current) setPostLoading(false) }
  }

  async function exportReport() {
    if (!session || exporting) return
    const abort = new AbortController()
    exportAbort.current = abort
    setExporting(true); setPdfJob(null); setPdfError(null); setError(null); setModal('export')
    try {
      let job = await api<PDFJob>('/api/facebook/export/jobs', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify(range), signal: abort.signal,
      })
      setPdfJob(job)
      while (['queued', 'running', 'cancelling'].includes(job.status)) {
        await new Promise(resolve => window.setTimeout(resolve, 1500))
        if (abort.signal.aborted) return
        job = await api<PDFJob>(`/api/facebook/export/jobs/${encodeURIComponent(job.id)}`, { signal: abort.signal })
        setPdfJob(job)
      }
      if (job.status === 'failed') throw new Error(job.error || 'The PDF export could not be completed.')
      if (job.status === 'cancelled') { setToast('PDF export cancelled.'); return }
      await downloadPdf(job, abort.signal)
      setToast(`PDF exported for ${job.total} Pages.${job.limited_pages ? ` ${job.limited_pages} Pages have limited or unavailable metrics.` : ''}`)
    } catch (err) { if (!abort.signal.aborted) { setPdfError(err instanceof Error ? err.message : 'The PDF could not be exported.'); showError(err) } }
    finally { if (!abort.signal.aborted) setExporting(false) }
  }

  async function downloadPdf(job: PDFJob, signal?: AbortSignal) {
    const response = await fetch(`/api/facebook/export/jobs/${encodeURIComponent(job.id)}/file`, { credentials: 'same-origin', signal })
    if (!response.ok) {
      const data = await response.json()
      throw new APIError(data.error?.message || 'The PDF could not be downloaded.', data.error?.code)
    }
    download(await response.blob(), job.filename)
  }

  async function cancelPdfExport() {
    if (!session || !pdfJob) return
    try {
      const job = await api<PDFJob>(`/api/facebook/export/jobs/${encodeURIComponent(pdfJob.id)}`, {
        method: 'DELETE', headers: { 'X-CSRF-Token': session.csrf_token },
      })
      setPdfJob(job)
    } catch (err) { showError(err) }
  }

  async function exportCsvReport() {
    setExporting(true); setPdfJob(null)
    try {
      const response = await fetch(`/api/facebook/export?${queryString}`, { credentials: 'same-origin' })
      if (!response.ok) {
        const result = await response.json()
        throw new APIError(result.error?.message || 'Export failed.', result.error?.code, Number(response.headers.get('Retry-After')))
      }
      download(await response.blob(), `pagepulse-analytics-${report?.since || 'report'}${session?.demo ? '-sample' : ''}.csv`)
      setToast('Analytics exported, including availability and previous-period values.')
    } catch (err) { showError(err) }
    finally { setExporting(false) }
  }

  function download(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob), a = document.createElement('a')
    a.href = url; a.download = name; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  function exportPosts() {
    const cell = (value: unknown) => {
      let str = value == null ? '' : String(value)
      if (typeof value === 'string' && /^[\s]*[=+\-@\t\r\n]/.test(str)) str = "'"+str
      return `"${str.replaceAll('"', '""')}"`
    }
    const rows = [['source', 'post_id', 'text', 'published_at', 'reactions_lifetime', 'comments_lifetime', 'shares_lifetime', 'views_lifetime', 'url'],
      ...(posts?.posts || []).map(p => [session?.demo ? 'SAMPLE DATA' : 'Meta Graph API', p.id, p.text, p.published_at, p.reactions, p.comments, p.shares, p.views, p.url])]
    download(new Blob(['\ufeff'+rows.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }), `pagepulse-loaded-posts${session?.demo ? '-sample' : ''}.csv`)
    setToast(`Exported ${posts?.posts.length || 0} loaded posts. Counts are lifetime totals.`)
  }

  async function disconnect() {
    if (!session) return
    try {
      await api('/api/session', { method: 'DELETE', headers: { 'X-CSRF-Token': session.csrf_token } })
      const data = await api<Session>('/api/session')
      setSession(data); setReport(null); setPosts(null); setPageUrl(data.page?.url || ''); setRevision(n => n+1)
      setError(null); setToast('Stored connection and cached analytics deleted from this browser session.'); closeModal()
    } catch (err) { showError(err) }
  }

  function changeView(next: View) { setView(next); setMobileNav(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  function chooseTrackedPage(target: TrackedPage) {
    setPageUrl(target.url); setError(null); changeView('Overview')
    setToast(`${target.label} selected. Connect this Page through Facebook Login to retrieve authorized analytics.`)
  }
  function applyDates() {
    const start = new Date(draftDates.since), end = new Date(draftDates.until)
    if (!draftDates.since || !draftDates.until || end < start || (end.getTime()-start.getTime())/86400000 >= 90 || end > new Date()) {
      setToast('Choose a range of 1–90 days, ending no later than today.'); return
    }
    setError(null); setRange({ days: '28', ...draftDates }); closeModal()
  }
  const subtitle = { Overview: 'Turn your page performance into your next big idea.', Content: 'Find the stories that make people stop, connect, and share.', Audience: 'Get to know the community growing around your page.', Reports: 'Take your insights with you. Make your next move with confidence.', Connections: 'Your saved Page URLs, ready for authorized Facebook connections.' }
  const m = report?.metrics

  return <div className="app-shell">
    {mobileNav && <button className="sidebar-overlay" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}><a href="#overview" aria-label="Pagepulse home" onClick={e => { e.preventDefault(); changeView('Overview') }}><Logo /></a>
      <button className="workspace-switch" onClick={() => setModal('settings')}><span className="workspace-avatar">V<span /></span><span><b>My workspace</b><small>{session?.demo ? 'Demo workspace' : 'Facebook analytics'}</small></span><ChevronDown size={14} /></button>
      <div className="nav-label">WORKSPACE</div><nav aria-label="Main navigation">{NAV.map(item => <button key={item.name} onClick={() => changeView(item.name)} className={`nav-item ${view === item.name ? 'nav-active' : ''}`} aria-current={view === item.name ? 'page' : undefined}><item.icon size={18} />{item.name}{view === item.name && <span className="nav-active-dot" />}</button>)}</nav>
      <div className="sidebar-divider" /><div className="nav-label">MANAGE</div><button className={`nav-item ${view === 'Connections' ? 'nav-active' : ''}`} onClick={() => changeView('Connections')} aria-current={view === 'Connections' ? 'page' : undefined}><Link2 size={18} />Page connections<span className="nav-count">{watchlist?.count || 0}</span></button><button className="nav-item" onClick={() => setModal('settings')}><Settings2 size={18} />Settings</button>
      <div className="sidebar-bottom"><div className="sidebar-tip"><span className="tip-icon"><Sparkles size={18} /></span><b>A little insight. A big impact.</b><p>Understand what works.<br />Create more of it.</p><button onClick={() => setModal('help')}>Explore your dashboard<ArrowRight size={14} /></button></div><button className="nav-item help-link" onClick={() => setModal('help')}><CircleHelp size={18} />Help & resources<ArrowUpRight size={14} /></button>
        <div className="workspace-status"><span className={`status-dot ${session?.demo ? 'demo-dot' : ''}`} /><span>{session?.demo ? 'Sample data workspace' : session?.authenticated ? 'Facebook account connected' : 'Connect your Facebook Page'}</span><ShieldCheck size={13} /></div></div>
    </aside>

    <div className="main-shell"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setMobileNav(!mobileNav)} aria-label="Open navigation"><Menu size={22} /></button><span className="breadcrumb">Workspace<ChevronRight size={13} /><b>Facebook analytics</b></span></div><div className="topbar-actions"><span className="platform-label"><FacebookIcon size={15} />Facebook</span><span className="topbar-divider" /><button className="icon-button notification-button" aria-label="View notifications" onClick={() => setModal('notifications')}><Bell size={18} />{session?.demo && <i />}</button><button className="user-avatar" aria-label="Open workspace settings" onClick={() => setModal('settings')}>{page?.name.split(' ').map(word => word[0]).slice(0,2).join('') || 'ME'}</button></div></header>
      <main id="main-content"><div className="page-heading"><div><div className="eyebrow">FACEBOOK PAGE ANALYTICS</div><h1>{view === 'Overview' ? 'Your page, at a glance' : view === 'Content' ? 'Content that connects' : view === 'Audience' ? 'A community in the making' : view === 'Connections' ? 'Your Pages, in one place' : 'Insights worth sharing'}<span className="heading-dot">.</span></h1><p>{subtitle[view]}</p></div><div className="heading-actions"><button className="button button-white refresh-button" onClick={() => { if (view === 'Connections') setWatchlistRevision(n => n+1); else { setError(null); setRevision(n => n+1) } }} disabled={view === 'Connections' ? watchlistLoading : !ready || loading || seconds > 0} title={view === 'Connections' ? 'Refresh saved Pages' : 'Refresh analytics'}><RefreshCw size={15} className={loading && ready ? 'animate-spin' : ''} /><span>{seconds > 0 ? `${seconds}s` : 'Refresh'}</span></button>{view !== 'Connections' && <button className="button button-dark" onClick={exportReport} disabled={!canPdfExport || exporting || seconds > 0}>{exporting ? <LoaderCircle size={15} className="animate-spin" /> : <ArrowDownToLine size={15} />}Export PDF</button>}</div></div>

        {session?.demo && <div className="demo-banner"><span className="demo-label"><FlaskConical size={14} />Demo mode</span><span>You're exploring sample data. Connect your Meta app to make it yours.</span><button onClick={() => setModal('help')}>How to connect<ArrowUpRight size={13} /></button></div>}
        {error && <div className="error-banner" role="alert"><CircleHelp size={18} /><span>{error}{seconds > 0 && ` Try again in ${seconds} seconds.`}</span><button onClick={() => setError(null)} aria-label="Dismiss error"><X size={17} /></button></div>}
        {exporting && pdfJob && <div className="pdf-export-banner" role="status"><LoaderCircle size={15} className="animate-spin" /><span>Preparing PDF: {pdfJob.completed} of {pdfJob.total || '...'} Pages</span><button className="text-button" onClick={() => setModal('export')}>View progress</button></div>}

        {session && !session.demo && !session.authenticated && <section className="authorized-pages" aria-label="Connect Facebook account"><div className="saved-page-picker"><button className="button button-green" disabled={connecting || seconds > 0} onClick={() => void connect(true, true, true)}>{connecting ? <LoaderCircle size={14} className="animate-spin" /> : <FacebookIcon size={16} />}{connecting ? 'Connecting Facebook...' : 'Connect Facebook'}</button></div><p>{connecting ? 'Opening Facebook Login. After approval, your first available Page will connect automatically.' : 'Facebook connects automatically once per browser tab. If login was cancelled, use Connect Facebook to try again. Facebook may ask you to approve access.'}</p></section>}
        {session?.authenticated && !session.demo && <AuthorizedPages key={session.csrf_token} pageUrl={pageUrl} busy={connecting || seconds > 0} choose={target => { setAuthorizedChoice(target); setPageUrl(target.url); setError(null); setView('Overview') }} reconnect={() => void connect(true, true, true)} />}
        {view !== 'Connections' && <>
        <section className="panel connection-panel"><div className="connect-intro"><span className="facebook-tile"><FacebookIcon size={22} /></span><div><h2>Your Facebook Page</h2><p>One link. A clearer picture.</p></div></div><form className="connection-form" onSubmit={event => { event.preventDefault(); void connect() }}><label className="url-input"><Link2 size={16} /><input ref={urlRef} aria-label="Facebook Page URL" placeholder="https://www.facebook.com/YourPageName" type="url" required maxLength={2048} value={pageUrl} onChange={e => setPageUrl(e.target.value)} /></label><button type="submit" className="button button-green" disabled={connecting || seconds > 0}>{connecting ? <LoaderCircle size={14} className="animate-spin" /> : <Link2 size={14} />}Connect Page</button><button type="button" className="button button-white fetch-button" disabled={!ready || loading || seconds > 0} onClick={() => { setError(null); setRevision(n => n+1) }}><RefreshCw size={14} />Fetch Data</button></form></section>

        {!pendingPage && <>
        <div className="page-summary"><div className="page-identity"><div className="page-avatar">{safeLink(page?.picture) ? <img src={safeLink(page?.picture)} alt={`${page?.name} profile`} /> : <FacebookIcon size={24} />}<span><FacebookIcon size={12} /></span></div><div><div className="page-name"><h2>{page?.name || 'Your Facebook Page'}</h2><span className={`connection-badge ${session?.demo ? 'sample-badge' : ''}`}>{session?.demo ? <FlaskConical size={11} /> : page ? <Check size={11} /> : <LockKeyhole size={11} />}{session?.demo ? 'Sample Page' : session?.public_only ? 'Public metadata' : page ? 'Connected' : 'Not connected'}</span></div>{safeLink(page?.url) && !session?.demo ? <a className="page-url" href={safeLink(page?.url)} target="_blank" rel="noreferrer">{page?.url.replace('https://www.', '')}<ExternalLink size={11} /></a> : <span className="page-url">{session?.demo ? `${page?.url.replace('https://www.', '')} · Illustrative URL` : 'Sign in with Facebook to access the Pages you manage.'}</span>}</div></div>
          <div className="date-controls"><span className="date-caption">{report ? `${formatDate(report.since)} – ${formatDate(report.until)}, ${formatDate(report.until, { year: 'numeric' })}` : 'Select a reporting period'}</span><label className="date-select"><CalendarDays size={15} /><select aria-label="Date range" value={range.since ? 'custom' : range.days} onChange={e => { if (e.target.value === 'custom') { setDraftDates({ since: report?.since || '', until: report?.until || '' }); setModal('dates') } else { setError(null); setRange({ days: e.target.value }) } }}><option value="7">Last 7 days</option><option value="28">Last 28 days</option><option value="90">Last 90 days</option><option value="custom">Custom range</option></select><ChevronDown size={13} /></label>{range.since && <button className="icon-button small" aria-label="Edit custom date range" onClick={() => { setDraftDates({ since: range.since!, until: range.until! }); setModal('dates') }}><Settings2 size={14} /></button>}</div></div>

        </>}

        {pendingPage && <div className="public-notice selected-page-notice"><LockKeyhole size={20} /><div><h3>{pendingAuthorized ? authorizedChoice?.name : trackedSelection?.label} — awaiting connection</h3><p>{session?.demo ? 'No live analytics have been retrieved for this Page. Configure your Meta app, then connect through Facebook Login. The saved URLs do not use the sample dataset.' : 'Connect this Page to switch the dashboard to its authorized analytics. Its URL alone does not grant Insights access.'}</p></div></div>}
        </>}

        {session?.public_only && <div className="public-notice"><LockKeyhole size={20} /><div><h3>Public information only</h3><p>Meta allowed this Page's name and profile information. Private Insights require authorized Page access and the appropriate permissions.</p></div></div>}
        {view === 'Connections' && <WatchlistPanel watchlist={watchlist} loading={watchlistLoading} error={watchlistError} retry={() => setWatchlistRevision(n => n+1)} choose={chooseTrackedPage} />}
        <div aria-busy={loading} className={loading ? 'dashboard-loading' : ''}>{loading && view !== 'Connections' && <div className="loading-status" role="status"><LoaderCircle size={16} className="animate-spin" />Loading available analytics…</div>}

        {(view === 'Overview' || view === 'Audience') && <div className={`metrics-grid ${view === 'Audience' ? 'audience-metrics' : ''}`}>
          {view === 'Overview' && <><MetricCard title="Total views" metric={m?.views || NO_METRIC} icon={<Eye size={17} />} data={report?.series.map(d => d.views)} accent /><MetricCard title="Content interactions" metric={m?.interactions || NO_METRIC} icon={<MessageCircle size={16} />} data={report?.series.map(d => d.interactions)} /></>}
          <MetricCard title="Total followers" metric={m?.followers || NO_METRIC} icon={<UsersRound size={17} />} data={report?.series.map(d => d.followers)} />
          {view === 'Overview' && <MetricCard title="Estimated earnings" metric={m?.earnings || NO_METRIC} icon={<Wallet size={17} />} />}
          {view === 'Audience' && <><article className="metric-card"><div className="metric-label">Net follower change<TrendingUp size={17} /></div><div className="metric-value">{m?.followers.delta != null ? `${m.followers.delta > 0 ? '+' : ''}${formatNumber(m.followers.delta)}` : '—'}</div><span className="metric-comparison">End of period vs. previous period end</span></article><article className="metric-card"><div className="metric-label">Follower growth<UsersRound size={17} /></div><div className="metric-value">{m?.followers.growth != null ? `${m.followers.growth}%` : '—'}</div><span className="metric-comparison">Change in total follower count</span></article></>}
        </div>}

        {view === 'Overview' && <><div className="charts-grid"><PerformanceChart report={report} selectedMetric={selectedMetric} setMetric={setMetric} /><EngagementPanel posts={posts?.posts || []} /></div><div className="availability-strip"><ShieldCheck size={16} /><span><b>Clear data. Honest insights.</b> Some metrics depend on your Page's permissions and eligibility.</span><button onClick={() => setModal('settings')}>View availability<ArrowUpRight size={13} /></button></div></>}
        {(view === 'Overview' || view === 'Content') && <PostsTable data={posts} loading={postLoading || loading} loadMore={loadMore} exportPosts={exportPosts} busy={loading || seconds > 0} />}
        {view === 'Content' && <div className="content-note"><ShieldCheck size={17} />Filters and sorting apply to loaded posts. Load more to include additional content.</div>}
        {view === 'Audience' && <><PerformanceChart report={report} selectedMetric="followers" setMetric={setMetric} audience /><section className="panel audience-note"><span className="soft-icon"><ShieldCheck size={23} /></span><div><h2>Privacy is part of the picture.</h2><p>Demographics, reach, and impressions are shown only when a supported API and your permissions provide them. This integration does not infer private audience information.</p></div></section></>}
        {view === 'Reports' && <><div className="reports-grid"><section className="panel report-card"><span className="report-file-icon"><FileBarChart2 size={27} /></span><span className="report-type">ALL PAGES PDF REPORT</span><h2>Your performance, in perspective.</h2><p>Export every authorized Page with views, interactions, followers, growth percentages and trend lines for the selected date range.</p><div className="report-card-meta"><CalendarDays size={15} />{range.since ? `${range.since} to ${range.until}` : `Last ${range.days} days`}</div>
          <button className="button button-green" disabled={!canPdfExport || exporting || seconds > 0} onClick={() => void exportReport()}><ArrowDownToLine size={15} />Download all Pages PDF</button>
          <button className="text-button" disabled={!report || exporting || seconds > 0} onClick={exportCsvReport}>Download analytics CSV</button>
        </section><section className="panel report-card"><span className="report-file-icon report-file-light"><FileSpreadsheet size={27} /></span><span className="report-type">CONTENT REPORT</span><h2>The story behind every post.</h2><p>Export your loaded posts with publication dates and available lifetime reactions, comments, shares, and views.</p><div className="report-card-meta"><Image size={15} />{posts?.posts.length || 0} loaded posts included</div><button className="button button-white" disabled={!posts?.posts.length} onClick={exportPosts}><ArrowDownToLine size={15} />Download loaded posts CSV</button></section></div><div className="availability-strip"><FlaskConical size={17} /><span>{session?.demo ? 'All exported values are clearly labeled SAMPLE DATA.' : 'PDF reports mark missing metrics as unavailable. Unavailable CSV values stay empty.'}</span></div></>}
        </div>

        <footer className="page-footer"><span><Logo small />A little clarity for your next big thing.</span><div><span>{session?.demo ? 'Demo · No live Facebook data' : `Meta Graph API ${session?.graph_version || ''}`}</span><span className="footer-dot">·</span><button onClick={() => setModal('privacy')}>Privacy & data</button></div></footer>
      </main>
    </div>

    {toast && <div className="toast" role="status"><CheckCircle2 size={19} /><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={16} /></button></div>}
    {modal === 'export' && <Modal title="All Pages PDF export" close={closeModal}>
      <p className="modal-description">Three metric cards for every Page Facebook authorized for this login: total views, content interactions and total followers.</p>
      {pdfJob && <p className="modal-description">{pdfJob.since} to {pdfJob.until}</p>}
      {exporting && <div className="pdf-export-progress"><progress aria-label="PDF export progress" max={pdfJob?.total || 1} value={pdfJob?.completed || 0} /><p>{pdfJob?.total ? `${pdfJob.completed} of ${pdfJob.total} Pages processed` : 'Loading authorized Pages...'}</p><p>{pdfJob?.status === 'cancelling' ? 'Cancelling after the current request...' : pdfJob?.current_page || 'Preparing your report...'}</p></div>}
      {pdfJob?.status === 'ready' && <p className="modal-description">Your PDF for {pdfJob.total} Pages is ready.{pdfJob.limited_pages > 0 && ` ${pdfJob.limited_pages} Pages have limited or missing metrics, clearly marked in the PDF.`}</p>}
      {(pdfError || pdfJob?.status === 'failed') && <p className="modal-description" role="alert">{pdfError || pdfJob?.error}</p>}
      {pdfJob?.status === 'cancelled' && <p className="modal-description">Export cancelled.</p>}
      {!exporting && !pdfJob && <p className="modal-description">The export could not be started. Check the error message and try again.</p>}
      <div className="modal-actions">{exporting && pdfJob && <button className="button button-white" disabled={pdfJob.status === 'cancelling'} onClick={() => void cancelPdfExport()}>Cancel export</button>}{!exporting && pdfJob?.status === 'ready' && <button className="button button-green" onClick={() => void downloadPdf(pdfJob).catch(showError)}><ArrowDownToLine size={15} />Download PDF again</button>}<button className="button button-white" onClick={closeModal}>{exporting ? 'Continue in background' : 'Done'}</button></div>
    </Modal>}
    {modal === 'dates' && <Modal title="Choose your date range" close={closeModal}><p className="modal-description">Compare up to 90 days with the previous period of the same length. Recent Meta reporting may be delayed.</p><div className="custom-date-fields"><label>Start date<input type="date" value={draftDates.since} onChange={e => setDraftDates(current => ({ ...current, since: e.target.value }))} /></label><label>End date<input type="date" value={draftDates.until} onChange={e => setDraftDates(current => ({ ...current, until: e.target.value }))} /></label></div><div className="modal-actions"><button className="button button-white" onClick={closeModal}>Cancel</button><button className="button button-green" onClick={applyDates}>Apply date range<ArrowRight size={14} /></button></div></Modal>}
    {modal === 'help' && <Modal title="A clearer picture starts here." close={closeModal}><div className="help-hero"><span className="soft-icon"><Leaf size={25} /></span><div><h3>Welcome to Pagepulse.</h3><p>Explore your content, understand your audience, and take your insights with you.</p></div></div><ol className="help-steps"><li><span>1</span><div><h3>Set up your Meta app</h3><p>Configure the backend .env with your Meta app credentials, encryption key, and registered login redirect URL. Restart Flask to leave demo mode.</p></div></li><li><span>2</span><div><h3>Connect a Page you can access</h3><p>Enter its Facebook URL and choose Connect Page. Sign in through the official Facebook Login and grant access to your Page.</p></div></li><li><span>3</span><div><h3>Make your next move</h3><p>Choose a date range, explore your performance, and export the data that's available. A public URL alone does not unlock private Insights.</p></div></li></ol><a className="docs-link" href="https://developers.facebook.com/docs/pages-api/" target="_blank" rel="noreferrer">Meta Pages API documentation<ArrowUpRight size={15} /></a><div className="modal-actions"><button className="button button-green" onClick={() => { closeModal(); urlRef.current?.focus() }}>Explore my dashboard<ArrowRight size={14} /></button></div></Modal>}
    {modal === 'settings' && <Modal title="Page connection & data" close={closeModal}><div className="connection-status-card"><span className="facebook-tile"><FacebookIcon size={24} /></span><div><h3>{page?.name || 'No Page connected'}</h3><p>{session?.demo ? 'Demo mode · Fictional sample Page' : session?.authenticated ? 'Authenticated through Facebook Login' : 'Sign in with Facebook to get started'}</p></div></div><h3 className="modal-section-title">Metric availability</h3><div className="availability-list">{(['views', 'interactions', 'followers', 'earnings', 'reach', 'impressions'] as const).map(key => { const item = m?.[key]; return <div key={key}><span>{key === 'earnings' ? 'Estimated earnings' : key.charAt(0).toUpperCase()+key.slice(1)}<small>{item?.reason || item?.source_metric || 'No data loaded'}</small></span><span className={`availability-badge ${item?.status === 'available' ? 'is-available' : ''}`}>{item?.status || 'Not loaded'}</span></div> })}</div><p className="modal-description">Graph API {session?.graph_version || 'v26.0'} · Requested permissions: pages_show_list, pages_read_engagement, read_insights.</p>{!session?.demo && <p className="modal-description">Granted: {session?.permissions.join(', ') || 'None yet'}.</p>}<div className="modal-actions">{session?.authenticated && <button className="button button-white text-red-700" onClick={disconnect}><LogOut size={14} />Disconnect & delete stored data</button>}{!session?.demo && <button className="button button-green" disabled={!pageUrl || connecting || seconds > 0} onClick={() => { closeModal(); void connect(true) }}><FacebookIcon size={14} />Reconnect Facebook</button>}<button className="button button-white" onClick={closeModal}>Done</button></div></Modal>}
    {modal === 'notifications' && <Modal title="Your workspace updates" close={closeModal}><div className="notification-entry"><span className="soft-icon">{session?.demo ? <FlaskConical size={23} /> : <ShieldCheck size={23} />}</span><div><h3>{session?.demo ? 'Your sample workspace is ready' : session?.authenticated ? 'Your Facebook connection is ready' : 'Connect your Facebook Page'}</h3><p>{session?.demo ? 'Explore the dashboard using fictional Verdant Studio data. No real Page analytics have been retrieved.' : 'Only the data Meta authorizes for your account and Page will appear in this workspace.'}</p></div></div><div className="notification-entry"><span className="soft-icon"><CalendarDays size={22} /></span><div><h3>About reporting freshness</h3><p>Meta metrics may take 24–48 hours to update. The default range ends yesterday, and live reports are cached for five minutes. Refresh requests fresh data.</p></div></div></Modal>}
    {modal === 'privacy' && <Modal title="Your data, in your control." close={closeModal}><div className="privacy-content"><ShieldCheck size={31} /><p>Pagepulse uses official Facebook Login. It never asks for Facebook passwords, cookies, or pasted access tokens.</p><p>In live mode, Meta access tokens and cached analytics are encrypted in the backend database. An opaque browser session expires after eight hours. Disconnect in Page connections to delete this browser's stored data. Remove the app in Facebook's Business Integrations to revoke Meta authorization.</p><p>Meta deauthorization and signed data-deletion callbacks delete all stored sessions associated with that Facebook user. Expired sessions are removed by the server's scheduled cleanup command.</p><p>{session?.demo ? 'This workspace displays synthetic data for a fictional Page. No Meta credentials are configured.' : 'Access to private Insights requires appropriate Page tasks, permissions, and app approval. Unavailable data is never inferred.'}</p><p className="muted">Self-hosted deployment: the operator must publish an appropriate privacy policy and configure Meta's deletion and deauthorization URLs before public use.</p></div><div className="modal-actions"><button className="button button-green" onClick={closeModal}>Got it<Check size={14} /></button></div></Modal>}
  </div>
}
