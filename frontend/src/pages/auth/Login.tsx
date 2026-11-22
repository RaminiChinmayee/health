import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, Card, Checkbox, Field, Input, PasswordInput } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { errorMessage } from '../../lib/errors'

export function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.06H2.18A11 11 0 0 0 1 12c0 1.77.42 3.45 1.18 4.94l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.56 10.56 0 0 0 12 1 11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  )
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    queryFn: () => api<{ google_enabled: boolean; email_delivery_configured: boolean }>('/api/auth/config', { auth: false }),
    staleTime: 5 * 60_000,
  })
}

export function GoogleButton({ remember = false }: { remember?: boolean }) {
  const { t } = useTranslation()
  const { data } = useAuthConfig()
  if (!data?.google_enabled) return null // hidden when the server has no Google credentials
  return (
    <>
      <div className="my-6 flex items-center gap-3 text-xs uppercase text-slate-400">
        <div className="h-px flex-1 bg-slate-200" />
        {t('auth.login.or')}
        <div className="h-px flex-1 bg-slate-200" />
      </div>
      {/* Full-page navigation: the backend redirects to Google and back. */}
      <a
        href={`/api/auth/google?remember=${remember}`}
        className="flex w-full items-center justify-center gap-3 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
      >
        <GoogleIcon />
        {t('auth.login.google')}
      </a>
    </>
  )
}

export default function Login() {
  const { t } = useTranslation()
  const { login, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState<unknown>(params.get('error') ? new ApiError(400, { code: params.get('error')! }) : null)
  const [busy, setBusy] = useState(false)
  const [resent, setResent] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard'

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const user = await login(email, password, remember)
      navigate(user.needs_onboarding ? '/onboarding' : from, { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    await api('/api/auth/resend-verification', { method: 'POST', auth: false, body: { email } }).catch(() => {})
    setResent(true)
  }

  const notVerified = error instanceof ApiError && error.code === 'email_not_verified'

  return (
    <Card className="p-8">
      <h1 className="text-2xl font-bold text-slate-900">{t('auth.login.title')}</h1>
      <p className="mt-1 text-sm text-slate-600">{t('auth.login.subtitle')}</p>

      {sessionExpired && !error && <Alert kind="warning" className="mt-6">{t('auth.sessionExpired')}</Alert>}
      {error != null && (
        <Alert kind="error" className="mt-6">
          {errorMessage(t, error)}
          {notVerified && !resent && (
            <button type="button" onClick={resend} className="mt-1 block font-semibold underline">
              {t('auth.login.resend')}
            </button>
          )}
          {resent && <p className="mt-1">{t('auth.login.resent')}</p>}
        </Alert>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
        <Field label={t('auth.login.email')}>
          {(id) => <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} dir="ltr" />}
        </Field>
        <Field label={t('auth.login.password')}>
          {(id) => <PasswordInput id={id} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <div className="flex items-center justify-between gap-4">
          <Checkbox label={t('auth.login.remember')} checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <Link to="/forgot-password" className="shrink-0 text-sm font-medium text-brand-600 hover:text-brand-700">
            {t('auth.login.forgot')}
          </Link>
        </div>
        <Button type="submit" className="w-full" size="lg" loading={busy} disabled={!email || !password}>
          {busy ? t('auth.login.submitting') : t('auth.login.submit')}
        </Button>
      </form>

      <GoogleButton remember={remember} />

      <p className="mt-6 text-center text-sm text-slate-600">
        {t('auth.login.noAccount')}{' '}
        <Link to="/register" className="font-semibold text-brand-600 hover:text-brand-700">{t('auth.login.register')}</Link>
      </p>
    </Card>
  )
}
