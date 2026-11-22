import { CheckCircle2, XCircle } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, buttonClasses, Card, Checkbox, Field, Input, PasswordInput, PasswordStrength, Select, Spinner } from '../../components/ui'
import { api, type User } from '../../lib/api'
import { errorMessage, fieldErrors } from '../../lib/errors'

// ------------------------------------------------------------------ Forgot password
export function ForgotPassword() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api('/api/auth/forgot-password', { method: 'POST', auth: false, body: { email } })
      setDone(true)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="p-8">
      <h1 className="text-2xl font-bold text-slate-900">{t('auth.forgot.title')}</h1>
      <p className="mt-1 text-sm text-slate-600">{t('auth.forgot.subtitle')}</p>
      {done ? (
        <Alert kind="success" className="mt-6">{t('auth.forgot.done')}</Alert>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          {error != null && <Alert kind="error">{errorMessage(t, error)}</Alert>}
          <Field label={t('auth.login.email')}>
            {(id) => <Input id={id} type="email" required autoComplete="email" dir="ltr" value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!email}>
            {busy ? t('auth.forgot.submitting') : t('auth.forgot.submit')}
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm">
        <Link to="/login" className="font-semibold text-brand-600">{t('auth.forgot.back')}</Link>
      </p>
    </Card>
  )
}

// ------------------------------------------------------------------ Reset password
export function ResetPassword() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (pw !== confirm) {
      setErrors({ confirm_password: t('validation.passwords_do_not_match') })
      return
    }
    setBusy(true)
    try {
      await api('/api/auth/reset-password', { method: 'POST', auth: false, body: { token, password: pw, confirm_password: confirm } })
      setDone(true)
    } catch (err) {
      setErrors(fieldErrors(t, err))
      setFormError(errorMessage(t, err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-8">
      <h1 className="text-2xl font-bold text-slate-900">{t('auth.reset.title')}</h1>
      {!token ? (
        <Alert kind="error" className="mt-6">
          {t('auth.reset.missingToken')}{' '}
          <Link to="/forgot-password" className="font-semibold underline">{t('auth.forgot.submit')}</Link>
        </Alert>
      ) : done ? (
        <>
          <Alert kind="success" className="mt-6">{t('auth.reset.success')}</Alert>
          <Link to="/login" className={buttonClasses('primary', 'lg') + ' mt-6 w-full'}>{t('auth.register.goToLogin')}</Link>
        </>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
          {formError && <Alert kind="error">{formError}</Alert>}
          <Field label={t('auth.reset.newPassword')} error={errors.password}>
            {(id) => (
              <div className="space-y-2">
                <PasswordInput id={id} autoComplete="new-password" value={pw} invalid={!!errors.password} onChange={(e) => setPw(e.target.value)} />
                <PasswordStrength password={pw} />
              </div>
            )}
          </Field>
          <Field label={t('auth.register.confirmPassword')} error={errors.confirm_password}>
            {(id) => <PasswordInput id={id} autoComplete="new-password" value={confirm} invalid={!!errors.confirm_password} onChange={(e) => setConfirm(e.target.value)} />}
          </Field>
          <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!pw || !confirm}>
            {busy ? t('auth.reset.submitting') : t('auth.reset.submit')}
          </Button>
        </form>
      )}
    </Card>
  )
}

// ------------------------------------------------------------------ Verify email
export function VerifyEmail() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [state, setState] = useState<'working' | 'email_verified' | 'email_changed' | 'failed'>('working')
  const ran = useRef(false) // tokens are single-use: never submit twice (StrictMode double effects)
  useEffect(() => {
    if (ran.current) return
    ran.current = true
    if (!token) {
      setState('failed')
      return
    }
    api<{ code: 'email_verified' | 'email_changed' }>('/api/auth/verify-email', { method: 'POST', auth: false, body: { token } })
      .then((r) => setState(r.code))
      .catch(() => setState('failed'))
  }, [token])

  return (
    <Card className="p-8 text-center">
      {state === 'working' ? (
        <div className="flex flex-col items-center gap-4 py-6">
          <Spinner className="size-8" />
          <p className="text-slate-600">{t('auth.verify.verifying')}</p>
        </div>
      ) : state === 'failed' ? (
        <>
          <XCircle className="mx-auto size-12 text-red-500" aria-hidden />
          <p className="mt-4 text-slate-700">{t('auth.verify.failed')}</p>
          <Link to="/login" className={buttonClasses('outline') + ' mt-6'}>{t('auth.register.goToLogin')}</Link>
        </>
      ) : (
        <>
          <CheckCircle2 className="mx-auto size-12 text-mint-600" aria-hidden />
          <p className="mt-4 text-slate-700">{state === 'email_changed' ? t('auth.verify.changed') : t('auth.verify.success')}</p>
          <Link to="/login" className={buttonClasses('primary') + ' mt-6'}>{t('auth.register.goToLogin')}</Link>
        </>
      )}
    </Card>
  )
}

// ------------------------------------------------------------------ Google callback
export function AuthCallback() {
  const { t } = useTranslation()
  const { completeExternalLogin } = useAuth()
  const navigate = useNavigate()
  const [failed, setFailed] = useState(false)
  const ran = useRef(false)
  useEffect(() => {
    if (ran.current) return
    ran.current = true
    completeExternalLogin().then((user) => {
      if (!user) setFailed(true)
      else navigate(user.needs_onboarding ? '/onboarding' : '/dashboard', { replace: true })
    })
  }, [completeExternalLogin, navigate])
  return (
    <Card className="p-8 text-center">
      {failed ? (
        <>
          <Alert kind="error">{t('auth.callback.failed')}</Alert>
          <Link to="/login" className={buttonClasses('outline') + ' mt-6'}>{t('auth.register.goToLogin')}</Link>
        </>
      ) : (
        <div className="flex flex-col items-center gap-4 py-6">
          <Spinner className="size-8" />
          <p className="text-slate-600">{t('auth.callback.working')}</p>
        </div>
      )}
    </Card>
  )
}

// ------------------------------------------------------------------ Onboarding (Google sign-ups: terms + DOB)
export function Onboarding() {
  const { t } = useTranslation()
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [dob, setDob] = useState(user?.date_of_birth ?? '')
  const [gender, setGender] = useState(user?.gender ?? '')
  const [terms, setTerms] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const errs: Record<string, string> = {}
    if (!dob) errs.date_of_birth = t('validation.required')
    if (!terms) errs.accept_terms = t('validation.terms_required')
    setErrors(errs)
    if (Object.keys(errs).length) return
    setBusy(true)
    try {
      const u = await api<User>('/api/profile', { method: 'PUT', body: { date_of_birth: dob, gender: gender || null, accept_terms: true } })
      setUser(u)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setErrors(fieldErrors(t, err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mx-auto max-w-md">
      <Card className="p-8">
        <h1 className="text-2xl font-bold text-slate-900">{t('auth.onboarding.title')}</h1>
        <p className="mt-1 text-sm text-slate-600">{t('auth.onboarding.subtitle')}</p>
        <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
          <Field label={t('auth.register.dob')} error={errors.date_of_birth}>
            {(id) => <Input id={id} type="date" max={new Date().toISOString().slice(0, 10)} value={dob} invalid={!!errors.date_of_birth} onChange={(e) => setDob(e.target.value)} />}
          </Field>
          <Field label={t('auth.register.gender')} optional hint={t('auth.register.genderHint')}>
            {(id) => (
              <Select id={id} value={gender} onChange={(e) => setGender(e.target.value)}>
                <option value="">{t('health.choose')}</option>
                {(['female', 'male', 'other', 'prefer_not_to_say'] as const).map((g) => (
                  <option key={g} value={g}>{t(`auth.gender.${g}`)}</option>
                ))}
              </Select>
            )}
          </Field>
          <div>
            <Checkbox checked={terms} onChange={(e) => setTerms(e.target.checked)} label={<span>{t('footer.terms')} · {t('footer.privacy')} · {t('footer.disclaimer')}</span>} />
            {errors.accept_terms && <p className="mt-1 text-sm text-red-600" role="alert">{errors.accept_terms}</p>}
          </div>
          <Button type="submit" size="lg" className="w-full" loading={busy}>{t('auth.onboarding.submit')}</Button>
        </form>
      </Card>
    </div>
  )
}
