import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../../auth/AuthProvider'
import { Alert, Button, Card, Field, Input, Select } from '../../../components/ui'
import { api, type User } from '../../../lib/api'
import { errorMessage, fieldErrors } from '../../../lib/errors'
import { PageHeader } from './MyProfile'

export default function PersonalInfo() {
  const { t } = useTranslation()
  const { user, setUser } = useAuth()
  const [f, setF] = useState({
    full_name: user?.full_name ?? '',
    phone: user?.phone ?? '',
    date_of_birth: user?.date_of_birth ?? '',
    gender: user?.gender ?? '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<{ kind: 'success' | 'error'; msg: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setStatus(null)
    if (f.full_name.trim().length < 2) {
      setErrors({ full_name: t('validation.name_too_short') })
      return
    }
    setBusy(true)
    try {
      const u = await api<User>('/api/profile', {
        method: 'PUT',
        body: { full_name: f.full_name, phone: f.phone.trim() || null, date_of_birth: f.date_of_birth || null, gender: f.gender || null },
      })
      setUser(u)
      setErrors({})
      setStatus({ kind: 'success', msg: t('common.saved') })
    } catch (err) {
      setErrors(fieldErrors(t, err))
      setStatus({ kind: 'error', msg: errorMessage(t, err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <PageHeader title={t('profile.personalInfo')} desc={t('profile.personalInfoDesc')} />
      <Card>
        <form onSubmit={submit} className="space-y-5" noValidate>
          {status && <Alert kind={status.kind}>{status.msg}</Alert>}
          <Field label={t('profile.fullName')} error={errors.full_name}>
            {(id) => <Input id={id} value={f.full_name} invalid={!!errors.full_name} autoComplete="name" onChange={(e) => setF({ ...f, full_name: e.target.value })} />}
          </Field>
          <Field label={t('profile.email')} hint={t('settings.changeEmailDesc')}>
            {(id, d) => <Input id={id} aria-describedby={d} value={user?.email ?? ''} disabled dir="ltr" />}
          </Field>
          <Field label={t('profile.phone')} optional error={errors.phone}>
            {(id) => <Input id={id} type="tel" dir="ltr" value={f.phone} invalid={!!errors.phone} autoComplete="tel" onChange={(e) => setF({ ...f, phone: e.target.value })} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label={t('profile.dob')} error={errors.date_of_birth}>
              {(id) => <Input id={id} type="date" max={new Date().toISOString().slice(0, 10)} value={f.date_of_birth} invalid={!!errors.date_of_birth} onChange={(e) => setF({ ...f, date_of_birth: e.target.value })} />}
            </Field>
            <Field label={t('profile.gender')} optional hint={t('auth.register.genderHint')}>
              {(id, d) => (
                <Select id={id} aria-describedby={d} value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}>
                  <option value="">{t('health.choose')}</option>
                  {(['female', 'male', 'other', 'prefer_not_to_say'] as const).map((g) => (
                    <option key={g} value={g}>{t(`auth.gender.${g}`)}</option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <div className="flex justify-end">
            <Button type="submit" loading={busy}>{busy ? t('common.saving') : t('common.save')}</Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
