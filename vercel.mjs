// Keep API requests on the website's origin so Facebook session cookies and
// CSRF checks work with the separately hosted Flask application.
const configuredBackend = process.env.BACKEND_URL
if (!configuredBackend) {
  throw new Error('Set BACKEND_URL in Vercel to your hosted Flask API origin, for example https://api.example.com. The localhost API cannot serve a deployed website.')
}

let backend
try {
  backend = new URL(configuredBackend)
} catch {
  throw new Error('BACKEND_URL must be a valid HTTPS origin.')
}
if (backend.protocol !== 'https:' || backend.username || backend.password ||
    backend.search || backend.hash || backend.pathname !== '/' ||
    ['localhost', '127.0.0.1', '[::1]'].includes(backend.hostname)) {
  throw new Error('BACKEND_URL must be a public HTTPS origin without credentials, a path, a query, or a fragment.')
}
const frontendHosts = [process.env.VERCEL_URL, process.env.VERCEL_PROJECT_PRODUCTION_URL].filter(Boolean)
if (frontendHosts.includes(backend.host)) {
  throw new Error('BACKEND_URL must point to the hosted Flask API, not this Vercel frontend.')
}

export const config = {
  framework: 'vite',
  buildCommand: 'npm run build',
  installCommand: 'npm ci',
  outputDirectory: 'dist',
  rewrites: [{ source: '/api/:path*', destination: `${backend.origin}/api/:path*` }],
}
