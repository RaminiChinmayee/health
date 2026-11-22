/**
 * API client.
 * - Access token lives only in memory (never localStorage), so XSS can't read a persisted token.
 * - The refresh token is an httpOnly cookie the browser sends to /api/auth/* automatically.
 * - On 401, one deduplicated refresh is attempted, then the request is retried once.
 */
export type ApiErrorDetail = {
  code: string
  fields?: Record<string, string>
  problems?: string[]
  [k: string]: unknown
}

export class ApiError extends Error {
  status: number
  code: string
  fields: Record<string, string>
  problems: string[]
  constructor(status: number, detail: ApiErrorDetail) {
    super(detail.code)
    this.status = status
    this.code = detail.code
    this.fields = detail.fields ?? {}
    this.problems = detail.problems ?? []
  }
}

export type User = {
  id: string
  email: string
  email_verified: boolean
  full_name: string
  phone: string | null
  date_of_birth: string | null
  age: number | null
  gender: string | null
  has_avatar: boolean
  has_password: boolean
  auth_methods: string[]
  ui_language: string
  chatbot_language: string
  created_at: string
  needs_onboarding: boolean
}

export type TokenResponse = { access_token: string; expires_in: number; user: User }

let accessToken: string | null = null
let refreshing: Promise<TokenResponse | null> | null = null
let onAuthLost: (() => void) | null = null

export function setAccessToken(t: string | null) {
  accessToken = t
}
export function setOnAuthLost(fn: () => void) {
  onAuthLost = fn
}

const CSRF = { 'X-HealthAI-CSRF': '1' }

async function parseError(res: Response): Promise<ApiError> {
  let detail: ApiErrorDetail = { code: 'unknown' }
  try {
    const body = await res.json()
    if (body?.detail && typeof body.detail === 'object' && 'code' in body.detail) detail = body.detail
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, detail)
}

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<TokenResponse | null> {
  refreshing ??= (async () => {
    try {
      const res = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin', headers: CSRF })
      if (!res.ok) {
        accessToken = null
        return null
      }
      const data = (await res.json()) as TokenResponse
      accessToken = data.access_token
      return data
    } catch {
      return null
    } finally {
      queueMicrotask(() => (refreshing = null))
    }
  })()
  return refreshing
}

type Options = Omit<RequestInit, 'body'> & { body?: unknown; auth?: boolean }

export async function api<T>(path: string, opts: Options = {}, retried = false): Promise<T> {
  const { body, auth = true, headers, ...rest } = opts
  const h: Record<string, string> = { ...(headers as Record<string, string>) }
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    h['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (auth && accessToken) h.Authorization = `Bearer ${accessToken}`
  if (path.startsWith('/api/auth/')) Object.assign(h, CSRF)

  let res: Response
  try {
    res = await fetch(path, { ...rest, headers: h, body: payload, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, { code: 'network' })
  }

  if (res.status === 401 && auth && !retried) {
    const refreshed = await refreshSession()
    if (refreshed) return api<T>(path, opts, true)
    onAuthLost?.()
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? res.json() : res.blob()) as Promise<T>
}

/** POST JSON and consume a Server-Sent Events stream. Calls onEvent(event, data) per event.
 *  Refreshes the access token once on 401. Throws ApiError for non-2xx responses. */
export async function streamSSE(path: string, body: unknown, onEvent: (event: string, data: unknown) => void, signal?: AbortSignal): Promise<void> {
  const doFetch = () =>
    fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
      body: JSON.stringify(body),
      signal,
    })
  let res: Response
  try {
    res = await doFetch()
    if (res.status === 401 && (await refreshSession())) res = await doFetch()
  } catch (e) {
    if ((e as DOMException)?.name === 'AbortError') throw e
    throw new ApiError(0, { code: 'network' })
  }
  if (!res.ok || !res.body) throw await parseError(res)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let ev = 'message'
      const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) ev = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (data.length) onEvent(ev, JSON.parse(data.join('\n')))
    }
  }
}

/** Fetch a private binary (e.g. avatar) with auth and return an object URL. */
export async function fetchObjectUrl(path: string): Promise<string> {
  const blob = await api<Blob>(path)
  return URL.createObjectURL(blob)
}
