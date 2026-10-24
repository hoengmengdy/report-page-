export type Page = { id: string; name: string; url: string; picture: string | null; category: string }
export type TrackedPage = { identity: string; url: string; label: string; status: 'active' | 'public_only' | 'not_connected' }
export type Watchlist = { pages: TrackedPage[]; count: number; demo: boolean; note: string }
export type Session = {
  demo: boolean; authenticated: boolean; page: Page | null; public_only: boolean;
  csrf_token: string; permissions: string[]; graph_version: string; login_error: string | null
}
export type MetricKey = 'views' | 'interactions' | 'followers'
export type PDFJob = {
  id: string; status: 'queued' | 'running' | 'cancelling' | 'cancelled' | 'ready' | 'failed';
  total: number; completed: number; current_page: string; limited_pages: number;
  error: string | null; filename: string; since: string; until: string
}
export type Metric = {
  value: number | null; previous: number | null; growth: number | null; delta: number | null;
  status: 'available' | 'partial' | 'unavailable'; reason: string | null; source_metric: string | null
}
export type Daily = {
  date: string; previous_date: string; views: number | null; interactions: number | null; followers: number | null;
  previous_views: number | null; previous_interactions: number | null; previous_followers: number | null
}
export type Report = {
  demo: boolean; since: string; until: string; previous_since: string; previous_until: string;
  metrics: Record<MetricKey | 'earnings' | 'reach' | 'impressions', Metric>;
  series: Daily[]; reporting_note: string; fetched_at: string
}
export type Post = {
  id: string; text: string; type: 'Photo' | 'Video' | 'Text'; picture: string | null;
  published_at: string | null; reactions: number | null; comments: number | null; shares: number | null;
  views: number | null; url: string | null; views_reason: string | null
}
export type PostsResponse = { demo: boolean; posts: Post[]; next_cursor: string | null; count: number | null; counts_note: string }
