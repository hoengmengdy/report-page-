import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/App'
import type { Post, Report, Session } from '../../src/types'

// Browser layout/chart rendering is separate from these interaction tests.
vi.mock('recharts', () => {
  const Container = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => null
  return { ResponsiveContainer: Container, ComposedChart: Container, PieChart: Container,
    CartesianGrid: Empty, XAxis: Empty, YAxis: Empty, Tooltip: Empty,
    Area: Empty, Line: Empty, Pie: Empty, Cell: Empty }
})

const session: Session = {
  demo: true, authenticated: false, public_only: false, csrf_token: 'csrf-test', permissions: [], graph_version: 'v26.0', login_error: null,
  page: { id: 'demo-verdant', name: 'Verdant Studio', url: 'https://www.facebook.com/verdantstudio', picture: '/assets/verdant.svg', category: 'Sample Page' },
}
const metric = { value: 100, previous: 80, growth: 25, delta: 20, status: 'available' as const, reason: null, source_metric: 'page_media_view' }
const report: Report = {
  demo: true, since: '2026-09-25', until: '2026-10-22', previous_since: '2026-08-28', previous_until: '2026-09-24',
  metrics: { views: metric, interactions: metric, followers: metric, earnings: { ...metric, value: null, status: 'unavailable' }, reach: { ...metric, value: null }, impressions: { ...metric, value: null } },
  series: [{ date: '2026-10-22', previous_date: '2026-09-24', views: 100, interactions: 20, followers: 10, previous_views: 80, previous_interactions: 10, previous_followers: 8 }],
  reporting_note: 'Synthetic sample data.', fetched_at: '2026-10-23T01:00:00Z',
}
const post: Post = { id: 'post1', text: 'A little green goes a long way.', type: 'Photo', picture: null,
  published_at: '2026-10-22T09:00:00Z', reactions: 50, comments: 10, shares: 5, views: 300, url: null, views_reason: 'Sample views' }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  window.sessionStorage.clear()
  fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/session') return json(session)
    if (url.startsWith('/api/facebook/pages?')) return json({ pages: [session.page], next_cursor: null })
    if (url === '/api/facebook/watchlist') return json({ count: 2, demo: true, pages: [
      { identity: '61580719959744', url: 'https://www.facebook.com/profile.php?id=61580719959744', label: 'Page 61580719959744', status: 'not_connected' },
      { identity: 'komsantv1629', url: 'https://www.facebook.com/komsantv1629', label: '@komsantv1629', status: 'not_connected' },
    ], note: 'Saved URLs for manual Page tracking.' })
    if (url.startsWith('/api/facebook/insights')) return json(report)
    if (url.startsWith('/api/facebook/posts')) return json({ demo: true, posts: [post], count: 2, next_cursor: '6', counts_note: 'Sample lifetime counters.' })
    if (url === '/api/facebook/connect') return json({ demo: true, page: session.page, message: 'No data was fetched from the submitted URL.' })
    throw new Error(`Unexpected test request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
})

describe('Dashboard interactions', () => {
  it('starts Facebook account login automatically without asking for a Page URL', async () => {
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: false, page: null }))
      if (url === '/api/facebook/connect') return Promise.resolve(json({ message: 'Facebook login requested.' }))
      return original(url)
    })
    render(<App />)
    await screen.findByText('Facebook login requested.')
    const request = fetchMock.mock.calls.find(([url]) => url === '/api/facebook/connect')!
    const options = request[1] as RequestInit
    expect(JSON.parse(String(options.body))).toEqual({ account_only: true, reauthorize: false, auto_connect: true })
    expect((options.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-test')
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/facebook/connect')).toHaveLength(1)
  })

  it('restores an existing connection returned by auto-connect without another login redirect', async () => {
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: false, page: null }))
      if (url === '/api/facebook/connect') return Promise.resolve(json({ demo: false, authenticated: true, page: session.page, public_only: false }))
      return original(url)
    })
    render(<App />)
    await screen.findByRole('combobox', { name: /Authorized Facebook Pages/ })
    await screen.findByText(post.text)
    expect(screen.queryByRole('button', { name: 'Connect Facebook', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fetch Data' })).toBeEnabled()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/facebook/connect')).toHaveLength(1)
  })

  it('does not repeat automatic login after a previous attempt and allows a manual retry', async () => {
    window.sessionStorage.setItem('pagepulse-auto-login', 'attempted')
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: false, page: null }))
      if (url === '/api/facebook/connect') return Promise.resolve(json({ message: 'Manual login requested.' }))
      return original(url)
    })
    render(<App />)
    const button = await screen.findByRole('button', { name: 'Connect Facebook', exact: true })
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/facebook/connect')).toBe(false)
    await user.click(button)
    await screen.findByText('Manual login requested.')
    const request = fetchMock.mock.calls.find(([url]) => url === '/api/facebook/connect')!
    expect(JSON.parse(String((request[1] as RequestInit).body))).toEqual({ account_only: true, reauthorize: true, auto_connect: true })
  })

  it('keeps a cancelled Facebook Login error visible without automatically redirecting again', async () => {
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => url === '/api/session'
      ? Promise.resolve(json({ ...session, demo: false, authenticated: false, page: null, login_error: 'Facebook Login was cancelled.' }))
      : original(url))
    render(<App />)
    await screen.findByText('Facebook Login was cancelled.')
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/facebook/connect')).toBe(false)
    expect(screen.getByRole('button', { name: 'Connect Facebook', exact: true })).toBeEnabled()
  })

  it('loads every Facebook Page batch and fills the URL for a Page in the last batch', async () => {
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    const lastPage = { ...session.page!, id: 'last-page', name: 'Last Facebook Page', url: 'https://www.facebook.com/LastPage' }
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true, page: null }))
      if (url.startsWith('/api/facebook/pages?')) return Promise.resolve(json(url.includes('after=next-batch')
        ? { pages: [session.page, lastPage], next_cursor: null }
        : { pages: [session.page], next_cursor: 'next-batch' }))
      return original(url)
    })
    render(<App />)
    await screen.findByText('All 2 authorized Page links loaded. Choose a Page to fill the link field automatically.')
    await user.selectOptions(screen.getByRole('combobox', { name: /Authorized Facebook Pages/ }), lastPage.id)
    expect(screen.getByRole('textbox', { name: 'Facebook Page URL' })).toHaveValue(lastPage.url)
    expect(screen.getByRole('button', { name: 'Fetch Data' })).toBeDisabled()
  })

  it('stops repeated Facebook pagination cursors and explains that the list is incomplete', async () => {
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true, page: null }))
      if (url.startsWith('/api/facebook/pages?')) return Promise.resolve(json({ pages: [session.page], next_cursor: 'repeated' }))
      return original(url)
    })
    render(<App />)
    await screen.findByText(/Facebook repeated a Page list cursor/)
    expect(fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/api/facebook/pages?'))).toHaveLength(2)
    expect(screen.queryByText(/All .* authorized Page links loaded/)).not.toBeInTheDocument()
  })

  it('exports all authorized Pages as PDF with progress even without a selected Page', async () => {
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    const active = { id: 'pdf-job', status: 'running', total: 54, completed: 7, current_page: 'Komsan Today', limited_pages: 0, error: null, filename: 'pagepulse-all-pages.pdf', since: '2026-09-25', until: '2026-10-22' }
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true, page: null }))
      if (url === '/api/facebook/export/jobs') return Promise.resolve(json(active, 202))
      if (url === '/api/facebook/export/jobs/pdf-job') return Promise.resolve(json({ ...active, status: 'ready', completed: 54 }))
      if (url === '/api/facebook/export/jobs/pdf-job/file') return Promise.resolve(new Response('%PDF-test', { headers: { 'Content-Type': 'application/pdf' } }))
      return original(url)
    })
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:pdf-test') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const downloaded: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) { downloaded.push(this.download) })
    render(<App />)
    await screen.findByRole('combobox', { name: /Authorized Facebook Pages/ })
    await user.click(screen.getByRole('button', { name: 'Export PDF' }))
    const progress = await screen.findByRole('progressbar', { name: 'PDF export progress' })
    expect(progress).toHaveAttribute('max', '54')
    expect(progress).toHaveAttribute('value', '7')
    await user.click(screen.getByRole('button', { name: 'Continue in background' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View progress' }))
    expect(screen.getByRole('dialog', { name: 'All Pages PDF export' })).toBeInTheDocument()
    await waitFor(() => expect(downloaded).toEqual(['pagepulse-all-pages.pdf']), { timeout: 4000 })
    const request = fetchMock.mock.calls.find(([url]) => url === '/api/facebook/export/jobs')!
    const options = request[1] as RequestInit
    expect(JSON.parse(String(options.body))).toEqual({ days: '28' })
    expect((options.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-test')
  })

  it('cancels a PDF export without downloading a partial file', async () => {
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    const job = { id: 'cancel-job', status: 'running', total: 54, completed: 1, current_page: 'A Page', limited_pages: 0, error: null, filename: 'unused.pdf', since: '2026-09-25', until: '2026-10-22' }
    fetchMock.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/facebook/export/jobs') return Promise.resolve(json(job, 202))
      if (url === '/api/facebook/export/jobs/cancel-job') return Promise.resolve(json({ ...job, status: options?.method === 'DELETE' ? 'cancelling' : 'cancelled' }))
      return original(url)
    })
    render(<App />)
    await screen.findByText(post.text)
    await user.click(screen.getByRole('button', { name: 'Export PDF' }))
    await user.click(await screen.findByRole('button', { name: 'Cancel export' }))
    expect(await screen.findByText('Cancelling after the current request...')).toBeInTheDocument()
    await screen.findByRole('button', { name: 'Done' }, { timeout: 4000 })
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/file'))).toBe(false)
  })

  const authorizedPage = { id: '10001', name: 'Authorized Garden', url: 'https://www.facebook.com/profile.php?id=10001', picture: null, category: 'Community' }

  it('prioritizes requested names and distinguishes duplicate names by Page ID', async () => {
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true, page: null }))
      if (url.startsWith('/api/facebook/pages?')) return Promise.resolve(json({
        pages: [authorizedPage, { ...authorizedPage, id: '10002', name: 'Komsan Today' }, { ...authorizedPage, id: '10003', name: 'Komsan Today' }, { ...authorizedPage, id: '10004', name: 'An unrelated Page' }],
        requested_names: ['Authorized Garden', 'Komsan Today', 'Missing Page'], next_cursor: null,
      }))
      return original(url)
    })
    render(<App />)
    const requested = await screen.findByRole('group', { name: 'Your requested Page names' })
    expect(within(requested).getByRole('option', { name: 'Authorized Garden (10001)' })).toBeInTheDocument()
    expect(within(requested).getByRole('option', { name: 'Komsan Today (10002)' })).toBeInTheDocument()
    expect(within(requested).getByRole('option', { name: 'Komsan Today (10003)' })).toBeInTheDocument()
    expect(within(requested).queryByText('An unrelated Page (10004)')).not.toBeInTheDocument()
    expect(screen.getByText(/1 of 3 requested names have one exact match/)).toBeInTheDocument()
    expect(screen.getByText(/Missing Page: No exact name match/)).toBeInTheDocument()
    expect(screen.getByText(/Komsan Today: 2 authorized Pages share this name/)).toBeInTheDocument()
  })

  it('lets a Facebook-authenticated user recover from an inaccessible saved URL by choosing an authorized Page', async () => {
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true, page: null, login_error: 'The saved Page was not authorized.' }))
      if (url.startsWith('/api/facebook/pages?')) return Promise.resolve(json({ pages: [authorizedPage], next_cursor: null }))
      if (url === '/api/facebook/connect') return Promise.resolve(json({ page: authorizedPage, public_only: false }))
      return original(url)
    })
    render(<App />)
    expect(await screen.findByText('The saved Page was not authorized.')).toBeInTheDocument()
    const picker = await screen.findByRole('combobox', { name: /Authorized Facebook Pages/ })
    await user.selectOptions(picker, authorizedPage.id)
    expect(screen.getByRole('textbox', { name: 'Facebook Page URL' })).toHaveValue(authorizedPage.url)
    expect(screen.getByRole('button', { name: 'Fetch Data' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Connect Page' }))
    await waitFor(() => expect(screen.getByText('Connected', { exact: true })).toBeInTheDocument())
    const request = fetchMock.mock.calls.find(([url]) => url === '/api/facebook/connect')!
    expect(JSON.parse((request[1] as RequestInit).body as string)).toEqual({ page_url: authorizedPage.url, reauthorize: false })
    expect(screen.getByRole('heading', { name: authorizedPage.name })).toBeInTheDocument()
  })

  it('clears the previous Page analytics while another authorized Page is staged', async () => {
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true }))
      if (url.startsWith('/api/facebook/pages?')) return Promise.resolve(json({ pages: [authorizedPage], next_cursor: null }))
      return original(url)
    })
    render(<App />)
    await screen.findByText(post.text)
    await user.selectOptions(screen.getByRole('combobox', { name: /Authorized Facebook Pages/ }), authorizedPage.id)
    await screen.findByRole('heading', { name: /Authorized Garden.*awaiting connection/ })
    await waitFor(() => expect(screen.queryByText(post.text)).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Fetch Data' })).toBeDisabled()
  })

  it('keeps connection recovery available when a 403 response includes the limiter Retry-After header', async () => {
    const user = userEvent.setup()
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => {
      if (url === '/api/session') return Promise.resolve(json({ ...session, demo: false, authenticated: true, page: null }))
      if (url === '/api/facebook/connect') return Promise.resolve(new Response(JSON.stringify({ error: { code: 'page_not_accessible', message: 'Choose an authorized Page.' } }), {
        status: 403, headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
      }))
      return original(url)
    })
    render(<App />)
    await screen.findByRole('combobox', { name: /Authorized Facebook Pages/ })
    await user.type(screen.getByRole('textbox', { name: 'Facebook Page URL' }), 'https://www.facebook.com/UnavailablePage')
    await user.click(screen.getByRole('button', { name: 'Connect Page' }))
    await screen.findByText('Choose an authorized Page.')
    expect(screen.getByRole('button', { name: 'Connect Page' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Reconnect Facebook', exact: true })).toBeEnabled()
    expect(screen.queryByText(/Try again in/)).not.toBeInTheDocument()
  })

  it('searches saved Pages and stages a real URL without attaching demo analytics to it', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /Page connections/ }))
    await screen.findByRole('button', { name: 'Use Page 61580719959744' })
    expect(screen.getByRole('heading', { name: 'Your Pages, in one place.' })).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Search saved Pages' }), '61580719959744')
    expect(screen.queryByRole('button', { name: 'Use @komsantv1629' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use Page 61580719959744' }))
    expect(screen.getByRole('textbox', { name: 'Facebook Page URL' })).toHaveValue('https://www.facebook.com/profile.php?id=61580719959744')
    await screen.findByRole('heading', { name: /61580719959744.*awaiting connection/ })
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Fetch Data' })).toBeDisabled()
    expect(screen.queryByText(post.text)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Connect Page' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/facebook/connect')).toBe(false)
  })

  it('can return from a saved real Page to the explicitly labeled demo dataset', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(post.text)
    const input = screen.getByRole('textbox', { name: 'Facebook Page URL' })
    await user.clear(input)
    await user.type(input, 'https://www.facebook.com/komsantv1629')
    await screen.findByRole('heading', { name: /komsantv1629.*awaiting connection/ })
    expect(screen.getByRole('button', { name: 'Fetch Data' })).toBeDisabled()
    await user.clear(input)
    await user.type(input, session.page!.url)
    await screen.findByText(post.text)
    expect(screen.getByRole('textbox', { name: 'Facebook Page URL' })).toHaveValue(session.page!.url)
    expect(screen.getByText('Sample Page')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeEnabled()
  })

  it('labels demo data and keeps exports disabled until reporting data loads', async () => {
    render(<App />)
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled()
    await screen.findByText('Sample Page')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export PDF' })).toBeEnabled())
    expect(screen.getByText('Demo mode')).toBeInTheDocument()
    expect(screen.getByText(/No live Facebook data/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /facebook.com\/verdantstudio/ })).not.toBeInTheDocument()
  })

  it('passes CSRF protection on connect without attributing sample analytics to the entered URL', async () => {
    const user = userEvent.setup()
    render(<App />)
    const input = await screen.findByRole('textbox', { name: 'Facebook Page URL' })
    await waitFor(() => expect(input).toHaveValue(session.page!.url))
    await user.clear(input); await user.type(input, 'https://www.facebook.com/UnrelatedPage')
    await user.click(screen.getByRole('button', { name: 'Connect Page' }))
    await screen.findByText('No data was fetched from the submitted URL.')
    expect(input).toHaveValue(session.page!.url)
    const request = fetchMock.mock.calls.find(([url]) => url === '/api/facebook/connect')!
    const options = request[1] as RequestInit
    expect((options.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-test')
    expect(JSON.parse(String(options.body)).page_url).toBe('https://www.facebook.com/UnrelatedPage')
  })

  it('filters only loaded posts and switches between functional dashboard views', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(post.text)
    await user.type(screen.getByRole('textbox', { name: 'Search loaded posts' }), 'not found')
    expect(screen.getByText('No matching posts')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Audience', exact: true }))
    expect(screen.getByRole('heading', { name: 'A community in the making.' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Follower growth' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reports', exact: true }))
    expect(screen.getByRole('button', { name: 'Download analytics CSV' })).toBeEnabled()
    expect(screen.getByText('1 loaded posts included')).toBeInTheDocument()
  })

  it('discards a late post-pagination response after the selected reporting range changes', async () => {
    let finish: ((response: Response) => void) | undefined
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => url.includes('after=6')
      ? new Promise<Response>(resolve => { finish = resolve }) : original(url))
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(post.text)
    await user.click(screen.getByRole('button', { name: 'Load more posts' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Date range' }), '7')
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('days=7'))).toBe(true))
    finish!(json({ demo: true, posts: [{ ...post, id: 'late', text: 'OUTDATED PAGINATION DATA' }], next_cursor: null, count: 2, counts_note: 'Old range' }))
    await waitFor(() => expect(screen.getByText(post.text)).toBeInTheDocument())
    expect(screen.queryByText('OUTDATED PAGINATION DATA')).not.toBeInTheDocument()
  })

  it('removes protected data when the server reports revoked Facebook authorization', async () => {
    const user = userEvent.setup()
    const live = { ...session, demo: false, authenticated: true }
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => url === '/api/session' ? Promise.resolve(json(live)) : original(url))
    render(<App />)
    await screen.findByText(post.text)
    fetchMock.mockImplementation((url: string) => url.startsWith('/api/facebook/insights')
      ? Promise.resolve(json({ error: { code: 'reauthorize', message: 'Reconnect your Page.' } }, 401)) : original(url))
    await user.click(screen.getByRole('button', { name: 'Refresh', exact: true }))
    expect(await screen.findByText('Reconnect your Page.')).toBeInTheDocument()
    expect(screen.getByText('Not connected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled()
    expect(screen.queryByText(post.text)).not.toBeInTheDocument()
  })

  it('does not display unknown engagement counters as zero', async () => {
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string) => url.startsWith('/api/facebook/posts')
      ? Promise.resolve(json({ demo: false, posts: [{ ...post, reactions: null, comments: null, shares: null }], next_cursor: null, count: 1, counts_note: 'Lifetime' })) : original(url))
    render(<App />)
    await screen.findByText(post.text)
    const breakdown = screen.getByRole('heading', { name: 'Engagement breakdown' }).closest('section')!
    expect(within(breakdown).queryByText('0')).not.toBeInTheDocument()
    expect(within(breakdown).getAllByText('—').length).toBeGreaterThan(2)
  })
})
