import { MailCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Alert, Button, buttonClasses, Card, Checkbox, Field, Input, PasswordInput, PasswordStrength, Select } from '../../components/ui'
import type { LanguageCode } from '../../i18n/languages'
import { api } from '../../lib/api'
import { errorMessage, fieldErrors } from '../../lib/errors'
import { GoogleButton } from './Login'

type Form = {
  full_name: string
  email: string
  phone: string
  password: string
  confirm_password: string
  date_of_birth: string
  gender: string
  accept_terms: boolean
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Client-side checks mirror the server's (which remain authoritative). */
export function validateRegistration(f: Form): Record<string, string> {
  const e: Record<string, string> = {}
  if (f.full_name.trim().length < 2) e.full_name = 'name_too_short'
  if (!f.email.trim()) e.email = 'required'
  else if (!EMAIL_RE.test(f.email.trim())) e.email = 'invalid_email'
  if (f.phone.trim() && !/^\+?[0-9 ()-]{7,20}$/.test(f.phone.trim())) e.phone = 'invalid_phone'
  if (!f.password) e.password = 'required'
  else if (f.password.length < 10) e.password = 'password_too_short'
  else if ([/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(f.password)).length < 3) e.password = 'password_needs_variety'
  if (f.confirm_password !== f.password) e.confirm_password = 'passwords_do_not_match'
  if (!f.date_of_birth) e.date_of_birth = 'required'
  else if (new Date(f.date_of_birth) > new Date()) e.date_of_birth = 'dob_in_future'
  if (!f.accept_terms) e.accept_terms = 'terms_required'
  return e
}

export default function Register() {
  const { t, i18n } = useTranslation()
  const [f, setF] = useState<Form>({ full_name: '', email: '', phone: '', password: '', confirm_password: '', date_of_birth: '', gender: '', accept_terms: false })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<null | 'sent' | 'not_configured' | 'failed'>(null)

  const set = <K extends keyof Form>(k: K, v: Form[K]) => {
    setF((p) => ({ ...p, [k]: v }))
    setErrors((p) => ({ ...p, [k]: '' }))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)
    const local = validateRegistration(f)
    if (Object.keys(local).length) {
      setErrors(Object.fromEntries(Object.entries(local).map(([k, code]) => [k, t(`validation.${code}`)])))
      return
    }
    setBusy(true)
    try {
      const res = await api<{ email_delivery: 'sent' | 'not_configured' | 'failed' }>('/api/auth/register', {
        method: 'POST',
        auth: false,
        body: {
          ...f,
          phone: f.phone.trim() || null,
          gender: f.gender || null,
          language: i18n.language as LanguageCode,
        },
      })
      setDone(res.email_delivery)
    } catch (err) {
      const fe = fieldErrors(t, err)
      setErrors(fe)
      // Server-side "_form" error (e.g. passwords mismatch) → show against confirm field.
      if (fe._form) setErrors((p) => ({ ...p, confirm_password: fe._form }))
      setFormError(errorMessage(t, err))
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <Card className="p-8 text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-mint-50 text-mint-600">
          <MailCheck className="size-7" aria-hidden />
        </div>
        <h1 className="mt-5 text-2xl font-bold text-slate-900">{t('auth.register.successTitle')}</h1>
        <Alert kind={done === 'sent' ? 'success' : 'warning'} className="mt-5 text-start">
          {done === 'sent'
            ? t('auth.register.successSent', { email: f.email })
            : done === 'not_configured'
              ? t('auth.register.successNotConfigured')
              : t('auth.register.successFailed')}
        </Alert>
        <Link to="/login" className={buttonClasses('primary', 'lg') + ' mt-6 w-full'}>
          {t('auth.register.goToLogin')}
        </Link>
      </Card>
    )
  }

  const maxDob = new Date().toISOString().slice(0, 10)

  return (
    <Card className="p-8">
      <h1 className="text-2xl font-bold text-slate-900">{t('auth.register.title')}</h1>
      <p className="mt-1 text-sm text-slate-600">{t('auth.register.subtitle')}</p>
      {formError && <Alert kind="error" className="mt-6">{formError}</Alert>}

      <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
        <Field label={t('auth.register.fullName')} error={errors.full_name}>
          {(id, d) => <Input id={id} aria-describedby={d} autoComplete="name" value={f.full_name} invalid={!!errors.full_name} onChange={(e) => set('full_name', e.target.value)} />}
        </Field>
        <Field label={t('auth.register.email')} error={errors.email}>
          {(id, d) => <Input id={id} aria-describedby={d} type="email" autoComplete="email" dir="ltr" value={f.email} invalid={!!errors.email} onChange={(e) => set('email', e.target.value)} />}
        </Field>
        <Field label={t('auth.register.phone')} optional error={errors.phone}>
          {(id, d) => <Input id={id} aria-describedby={d} type="tel" autoComplete="tel" dir="ltr" placeholder="+91" value={f.phone} invalid={!!errors.phone} onChange={(e) => set('phone', e.target.value)} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('auth.register.dob')} error={errors.date_of_birth}>
            {(id, d) => <Input id={id} aria-describedby={d} type="date" max={maxDob} autoComplete="bday" value={f.date_of_birth} invalid={!!errors.date_of_birth} onChange={(e) => set('date_of_birth', e.target.value)} />}
          </Field>
          <Field label={t('auth.register.gender')} optional hint={t('auth.register.genderHint')} error={errors.gender}>
            {(id, d) => (
              <Select id={id} aria-describedby={d} value={f.gender} onChange={(e) => set('gender', e.target.value)}>
                <option value="">{t('health.choose')}</option>
                {(['female', 'male', 'other', 'prefer_not_to_say'] as const).map((g) => (
                  <option key={g} value={g}>{t(`auth.gender.${g}`)}</option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <Field label={t('auth.register.password')} error={errors.password}>
          {(id, d) => (
            <div className="space-y-2">
              <PasswordInput id={id} aria-describedby={d} autoComplete="new-password" value={f.password} invalid={!!errors.password} onChange={(e) => set('password', e.target.value)} />
              <PasswordStrength password={f.password} />
            </div>
          )}
        </Field>
        <Field label={t('auth.register.confirmPassword')} error={errors.confirm_password}>
          {(id, d) => <PasswordInput id={id} aria-describedby={d} autoComplete="new-password" value={f.confirm_password} invalid={!!errors.confirm_password} onChange={(e) => set('confirm_password', e.target.value)} />}
        </Field>
        <div>
          <Checkbox
            checked={f.accept_terms}
            onChange={(e) => set('accept_terms', e.target.checked)}
            label={
              <Trans
                i18nKey="auth.register.terms"
                components={{
                  terms: <Link to="/terms" target="_blank" className="font-medium text-brand-600 underline" />,
                  privacy: <Link to="/privacy" target="_blank" className="font-medium text-brand-600 underline" />,
                }}
              />
            }
          />
          {errors.accept_terms && <p className="mt-1 text-sm text-red-600" role="alert">{errors.accept_terms}</p>}
        </div>
        <Button type="submit" className="w-full" size="lg" loading={busy}>
          {busy ? t('auth.register.submitting') : t('auth.register.submit')}
        </Button>
      </form>

      <GoogleButton />

      <p className="mt-6 text-center text-sm text-slate-600">
        {t('auth.register.haveAccount')}{' '}
        <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">{t('auth.register.login')}</Link>
      </p>
    </Card>
  )
}
