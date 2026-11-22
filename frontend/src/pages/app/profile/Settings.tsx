import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, LogOut, Monitor, ShieldAlert, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../../auth/AuthProvider'
import { Alert, Button, Card, Checkbox, Field, FullPageSpinner, Input, PasswordInput, PasswordStrength, Select } from '../../../components/ui'
import { intlLocale, LANGUAGES, type LanguageCode } from '../../../i18n/languages'
import { changeLanguage } from '../../../i18n'
import { api, type User } from '../../../lib/api'
import { errorMessage, fieldErrors } from '../../../lib/errors'
import { PageHeader } from './MyProfile'

type Status = { kind: 'success' | 'error' | 'warning'; msg: string } | null

// ------------------------------------------------------------------ Language
export function LanguagePreferences() {
  const { t } = useTranslation()
  const { user, setUser } = useAuth()
  const [ui, setUi] = useState<LanguageCode>((user?.ui_language as LanguageCode) ?? 'en')
  const [chat, setChat] = useState<string>(user && user.chatbot_language !== user.ui_language ? user.chatbot_language : '')
  const [status, setStatus] = useState<Status>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const u = await api<User>('/api/profile/language', { method: 'PUT', body: { ui_language: ui, chatbot_language: chat || null } })
      await changeLanguage(ui)
      setUser(u)
      setStatus({ kind: 'success', msg: t('language.saved') })
    } catch (err) {
      setStatus({ kind: 'error', msg: errorMessage(t, err) })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <PageHeader title={t('language.title')} desc={t('language.desc')} />
      <Card>
        <form onSubmit={submit} className="space-y-5">
          {status && <Alert kind={status.kind}>{status.msg}</Alert>}
          <Field label={t('language.ui')}>
            {(id) => (
              <Select id={id} value={ui} onChange={(e) => setUi(e.target.value as LanguageCode)}>
                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native} — {l.english}</option>)}
              </Select>
            )}
          </Field>
          <Field label={t('language.chatbot')}>
            {(id) => (
              <Select id={id} value={chat} onChange={(e) => setChat(e.target.value)}>
                <option value="">{t('language.sameAsUi')}</option>
                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native} — {l.english}</option>)}
              </Select>
            )}
          </Field>
          <div className="flex justify-end">
            <Button type="submit" loading={busy}>{t('common.save')}</Button>
          </div>
        </form>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ Privacy & security
type SessionRow = { family_id: string; created_at: string; last_used_at: string | null; user_agent: string | null; ip_address: string | null; current: boolean }
type EventRow = { event_type: string; created_at: string; ip_address: string | null }

function deviceName(ua: string | null, fallback: string) {
  if (!ua) return fallback
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : null
  const os = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : null
  return [browser, os].filter(Boolean).join(' · ') || fallback
}

export function PrivacySecurity() {
  const { t, i18n } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: () => api<SessionRow[]>('/api/profile/sessions') })
  const events = useQuery({ queryKey: ['security-events'], queryFn: () => api<EventRow[]>('/api/profile/security-events') })
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' })
  const [pwErrors, setPwErrors] = useState<Record<string, string>>({})
  const [pwStatus, setPwStatus] = useState<Status>(null)
  const [busy, setBusy] = useState(false)
  const fmt = (d: string) => new Intl.DateTimeFormat(intlLocale(i18n.language), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(d))

  const revoke = useMutation({
    mutationFn: (id: string) => api(`/api/profile/sessions/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
  const signOutAll = async () => {
    await api('/api/auth/logout-all', { method: 'POST' }).catch(() => {})
    await logout()
    navigate('/login', { replace: true })
  }

  const changePw = async (e: FormEvent) => {
    e.preventDefault()
    setPwStatus(null)
    if (pw.next !== pw.confirm) {
      setPwErrors({ confirm: t('validation.passwords_do_not_match') })
      return
    }
    setBusy(true)
    try {
      await api('/api/profile/password', { method: 'POST', body: { current_password: pw.current || null, new_password: pw.next, confirm_password: pw.confirm } })
      setPw({ current: '', next: '', confirm: '' })
      setPwErrors({})
      setPwStatus({ kind: 'success', msg: t('security.passwordChanged') })
      qc.invalidateQueries({ queryKey: ['sessions'] })
    } catch (err) {
      const fe = fieldErrors(t, err)
      setPwErrors({ next: fe.password ?? fe.new_password ?? '' })
      setPwStatus({ kind: 'error', msg: errorMessage(t, err) })
    } finally {
      setBusy(false)
    }
  }

  if (!user) return null
  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
      <PageHeader title={t('security.title')} />

      <Card>
        <h2 className="text-lg font-semibold text-slate-900">{user.has_password ? t('security.changePassword') : t('security.setPassword')}</h2>
        {!user.has_password && <p className="mt-1 text-sm text-slate-600">{t('security.setPasswordDesc')}</p>}
        <form onSubmit={changePw} className="mt-5 space-y-4" noValidate>
          {pwStatus && <Alert kind={pwStatus.kind}>{pwStatus.msg}</Alert>}
          {user.has_password && (
            <Field label={t('security.currentPassword')}>
              {(id) => <PasswordInput id={id} autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />}
            </Field>
          )}
          <Field label={t('security.newPassword')} error={pwErrors.next}>
            {(id) => (
              <div className="space-y-2">
                <PasswordInput id={id} autoComplete="new-password" value={pw.next} invalid={!!pwErrors.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
                <PasswordStrength password={pw.next} />
              </div>
            )}
          </Field>
          <Field label={t('security.confirmPassword')} error={pwErrors.confirm}>
            {(id) => <PasswordInput id={id} autoComplete="new-password" value={pw.confirm} invalid={!!pwErrors.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />}
          </Field>
          <div className="flex justify-end">
            <Button type="submit" loading={busy} disabled={!pw.next || !pw.confirm || (user.has_password && !pw.current)}>{t('common.save')}</Button>
          </div>
        </form>
      </Card>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{t('security.sessions')}</h2>
            <p className="mt-1 text-sm text-slate-600">{t('security.sessionsDesc')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={signOutAll}>
            <LogOut className="size-4" aria-hidden /> {t('security.signOutAll')}
          </Button>
        </div>
        <ul className="mt-5 divide-y divide-slate-100">
          {sessions.data?.map((s) => (
            <li key={s.family_id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <Monitor className="size-5 text-slate-400" aria-hidden />
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    {deviceName(s.user_agent, t('security.unknownDevice'))}
                    {s.current && <span className="ms-2 rounded-full bg-mint-50 px-2 py-0.5 text-xs font-medium text-green-700">{t('security.thisDevice')}</span>}
                  </p>
                  <p className="text-xs text-slate-500">{t('security.lastActive', { date: fmt(s.created_at) })}{s.ip_address ? ` · ${s.ip_address}` : ''}</p>
                </div>
              </div>
              {!s.current && (
                <Button variant="ghost" size="sm" onClick={() => revoke.mutate(s.family_id)} loading={revoke.isPending && revoke.variables === s.family_id}>
                  {t('security.signOutDevice')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-slate-900">{t('security.activity')}</h2>
        <ul className="mt-4 divide-y divide-slate-100">
          {events.data?.slice(0, 15).map((e, i) => (
            <li key={i} className="flex items-center justify-between gap-4 py-2.5 text-sm">
              <span className="flex items-center gap-2 text-slate-700">
                {['login_failed', 'refresh_token_reuse', 'password_change_failed'].includes(e.event_type) && <ShieldAlert className="size-4 text-amber-500" aria-hidden />}
                {t(`security.events.${e.event_type}`, { defaultValue: e.event_type })}
              </span>
              <span className="shrink-0 text-xs text-slate-500">{fmt(e.created_at)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ Account settings
type Notif = { email_security_alerts: boolean; email_health_reminders: boolean; email_product_updates: boolean }

export function AccountSettings() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const notif = useQuery({ queryKey: ['notifications'], queryFn: () => api<Notif>('/api/profile/notifications') })
  const [newEmail, setNewEmail] = useState('')
  const [emailPw, setEmailPw] = useState('')
  const [emailStatus, setEmailStatus] = useState<Status>(null)
  const [emailBusy, setEmailBusy] = useState(false)
  const [confirmDel, setConfirmDel] = useState(false)
  const [delInput, setDelInput] = useState('')
  const [delStatus, setDelStatus] = useState<Status>(null)

  const saveNotif = useMutation({
    mutationFn: (n: Notif) => api<Notif>('/api/profile/notifications', { method: 'PUT', body: n }),
    onSuccess: (n) => qc.setQueryData(['notifications'], n),
  })

  if (!user) return null

  const changeEmail = async (e: FormEvent) => {
    e.preventDefault()
    setEmailBusy(true)
    setEmailStatus(null)
    try {
      const r = await api<{ email_delivery: string }>('/api/profile/email', { method: 'POST', body: { new_email: newEmail, current_password: emailPw || null } })
      setEmailStatus(
        r.email_delivery === 'sent'
          ? { kind: 'success', msg: t('settings.emailPending', { email: newEmail }) }
          : { kind: 'warning', msg: t('settings.emailNotConfigured') },
      )
      setEmailPw('')
    } catch (err) {
      setEmailStatus({ kind: 'error', msg: errorMessage(t, err) })
    } finally {
      setEmailBusy(false)
    }
  }

  const download = async () => {
    const blob = await api<Blob>('/api/profile/export')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'healthassist-my-data.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const deleteAccount = async () => {
    setDelStatus(null)
    try {
      await api('/api/profile', {
        method: 'DELETE',
        body: user.has_password ? { current_password: delInput } : { confirm_email: delInput },
      })
      navigate('/', { replace: true, state: { deleted: true } })
      await logout().catch(() => {})
    } catch (err) {
      setDelStatus({ kind: 'error', msg: errorMessage(t, err) })
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
      <PageHeader title={t('settings.title')} />

      <Card>
        <h2 className="text-lg font-semibold text-slate-900">{t('settings.changeEmail')}</h2>
        <p className="mt-1 text-sm text-slate-600">{t('settings.changeEmailDesc')}</p>
        <form onSubmit={changeEmail} className="mt-5 space-y-4">
          {emailStatus && <Alert kind={emailStatus.kind}>{emailStatus.msg}</Alert>}
          <Field label={t('settings.newEmail')}>
            {(id) => <Input id={id} type="email" dir="ltr" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />}
          </Field>
          {user.has_password && (
            <Field label={t('security.currentPassword')}>
              {(id) => <PasswordInput id={id} autoComplete="current-password" value={emailPw} onChange={(e) => setEmailPw(e.target.value)} />}
            </Field>
          )}
          <div className="flex justify-end">
            <Button type="submit" loading={emailBusy} disabled={!newEmail || (user.has_password && !emailPw)}>{t('settings.sendConfirmation')}</Button>
          </div>
        </form>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-slate-900">{t('settings.notifications')}</h2>
        {notif.isLoading || !notif.data ? (
          <FullPageSpinner />
        ) : (
          <div className="mt-4 space-y-3">
            {(['email_security_alerts', 'email_health_reminders', 'email_product_updates'] as const).map((k) => (
              <Checkbox
                key={k}
                checked={notif.data[k]}
                onChange={(e) => saveNotif.mutate({ ...notif.data!, [k]: e.target.checked })}
                label={t({ email_security_alerts: 'settings.notifSecurity', email_health_reminders: 'settings.notifReminders', email_product_updates: 'settings.notifUpdates' }[k])}
              />
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{t('settings.download')}</h2>
            <p className="mt-1 text-sm text-slate-600">{t('settings.downloadDesc')}</p>
          </div>
          <Button variant="outline" onClick={download}>
            <Download className="size-4" aria-hidden /> {t('settings.downloadButton')}
          </Button>
        </div>
      </Card>

      <Card className="border-red-200">
        <h2 className="text-lg font-semibold text-red-700">{t('settings.danger')}</h2>
        <p className="mt-1 text-sm text-slate-600">{t('settings.dangerDesc')}</p>
        {!confirmDel ? (
          <Button variant="danger" className="mt-4" onClick={() => setConfirmDel(true)}>
            <Trash2 className="size-4" aria-hidden /> {t('settings.deleteButton')}
          </Button>
        ) : (
          <div className="mt-5 space-y-4 rounded-xl border border-red-200 bg-red-50/50 p-4" role="alertdialog" aria-labelledby="del-title">
            <p id="del-title" className="font-semibold text-slate-900">{t('settings.confirmDeleteTitle')}</p>
            {delStatus && <Alert kind={delStatus.kind}>{delStatus.msg}</Alert>}
            <Field label={user.has_password ? t('settings.confirmWithPassword') : t('settings.confirmWithEmail', { email: user.email })}>
              {(id) =>
                user.has_password ? (
                  <PasswordInput id={id} autoComplete="current-password" value={delInput} onChange={(e) => setDelInput(e.target.value)} />
                ) : (
                  <Input id={id} dir="ltr" value={delInput} onChange={(e) => setDelInput(e.target.value)} />
                )
              }
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setConfirmDel(false); setDelInput('') }}>{t('common.cancel')}</Button>
              <Button variant="danger" disabled={!delInput} onClick={deleteAccount}>{t('settings.deleteButton')}</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
