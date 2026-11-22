import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Button, Card, Field, FullPageSpinner, Input, Select, TagInput } from '../../../components/ui'
import { intlLocale } from '../../../i18n/languages'
import { api } from '../../../lib/api'
import { errorMessage, fieldErrors } from '../../../lib/errors'
import { PageHeader } from './MyProfile'

export type HealthProfile = {
  height_cm: number | null
  weight_kg: number | null
  activity_level: string | null
  dietary_preference: string | null
  food_allergies: string[]
  health_conditions: string[]
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  preferred_units: 'metric' | 'imperial'
  age: number | null
  bmi: number | null
  bmi_category: string | null
  updated_at: string | null
}

const ACTIVITY = ['sedentary', 'light', 'moderate', 'active', 'very_active'] as const
const DIETS = ['vegetarian', 'vegan', 'eggetarian', 'non_vegetarian', 'jain', 'other'] as const
const CM_PER_IN = 2.54
const KG_PER_LB = 0.45359237

export default function HealthProfilePage() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['health-profile'], queryFn: () => api<HealthProfile>('/api/profile/health') })
  const [f, setF] = useState<HealthProfile | null>(null)
  // Imperial inputs are kept as strings so partial typing works; stored values are always metric.
  const [imp, setImp] = useState({ ft: '', inch: '', lb: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<{ kind: 'success' | 'error'; msg: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!data) return
    setF(data)
    if (data.height_cm) {
      const totalIn = data.height_cm / CM_PER_IN
      setImp((p) => ({ ...p, ft: String(Math.floor(totalIn / 12)), inch: String(Math.round(totalIn % 12)) }))
    }
    if (data.weight_kg) setImp((p) => ({ ...p, lb: String(Math.round(data.weight_kg! / KG_PER_LB)) }))
  }, [data])

  if (isLoading || !f) return <FullPageSpinner />
  const imperial = f.preferred_units === 'imperial'
  const num = (v: string) => (v.trim() === '' ? null : Number(v))

  const liveBmi = f.height_cm && f.weight_kg ? Math.round((f.weight_kg / (f.height_cm / 100) ** 2) * 10) / 10 : null
  const category = liveBmi == null ? null : liveBmi < 18.5 ? 'underweight' : liveBmi < 25 ? 'normal' : liveBmi < 30 ? 'overweight' : 'obese'

  const setImperial = (next: typeof imp) => {
    setImp(next)
    const ft = Number(next.ft || 0)
    const inch = Number(next.inch || 0)
    const totalIn = ft * 12 + inch
    setF({
      ...f,
      height_cm: totalIn > 0 ? Math.round(totalIn * CM_PER_IN * 10) / 10 : null,
      weight_kg: next.lb ? Math.round(Number(next.lb) * KG_PER_LB * 10) / 10 : null,
    })
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setStatus(null)
    setBusy(true)
    try {
      const body = {
        height_cm: f.height_cm,
        weight_kg: f.weight_kg,
        activity_level: f.activity_level || null,
        dietary_preference: f.dietary_preference || null,
        food_allergies: f.food_allergies,
        health_conditions: f.health_conditions,
        emergency_contact_name: f.emergency_contact_name || null,
        emergency_contact_phone: f.emergency_contact_phone || null,
        preferred_units: f.preferred_units,
      }
      const saved = await api<HealthProfile>('/api/profile/health', { method: 'PUT', body })
      qc.setQueryData(['health-profile'], saved)
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
    <div className="mx-auto max-w-3xl animate-fade-up">
      <PageHeader title={t('health.title')} desc={t('health.desc')} />
      <form onSubmit={submit} className="space-y-6" noValidate>
        {status && <Alert kind={status.kind}>{status.msg}</Alert>}
        <Card className="space-y-5">
          <Field label={t('health.units')}>
            {(id) => (
              <Select id={id} value={f.preferred_units} onChange={(e) => setF({ ...f, preferred_units: e.target.value as 'metric' | 'imperial' })}>
                <option value="metric">{t('health.metric')}</option>
                <option value="imperial">{t('health.imperial')}</option>
              </Select>
            )}
          </Field>
          <div className="grid gap-5 sm:grid-cols-3">
            {imperial ? (
              <>
                <Field label={t('health.heightFt')} error={errors.height_cm}>
                  {(id) => (
                    <div className="flex gap-2" dir="ltr">
                      <Input id={id} type="number" inputMode="numeric" min={1} max={8} placeholder="ft" value={imp.ft} onChange={(e) => setImperial({ ...imp, ft: e.target.value })} />
                      <Input type="number" inputMode="numeric" min={0} max={11} placeholder="in" aria-label="in" value={imp.inch} onChange={(e) => setImperial({ ...imp, inch: e.target.value })} />
                    </div>
                  )}
                </Field>
                <Field label={t('health.weightLb')} error={errors.weight_kg}>
                  {(id) => <Input id={id} type="number" inputMode="decimal" min={5} max={880} value={imp.lb} onChange={(e) => setImperial({ ...imp, lb: e.target.value })} />}
                </Field>
              </>
            ) : (
              <>
                <Field label={t('health.height')} error={errors.height_cm}>
                  {(id) => <Input id={id} type="number" inputMode="decimal" min={41} max={259} step="0.1" value={f.height_cm ?? ''} invalid={!!errors.height_cm} onChange={(e) => setF({ ...f, height_cm: num(e.target.value) })} />}
                </Field>
                <Field label={t('health.weight')} error={errors.weight_kg}>
                  {(id) => <Input id={id} type="number" inputMode="decimal" min={3} max={399} step="0.1" value={f.weight_kg ?? ''} invalid={!!errors.weight_kg} onChange={(e) => setF({ ...f, weight_kg: num(e.target.value) })} />}
                </Field>
              </>
            )}
            <div className="rounded-xl bg-brand-50 p-4" aria-live="polite">
              <p className="text-sm font-medium text-brand-700">{t('health.bmi')}</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{liveBmi?.toLocaleString(intlLocale(i18n.language)) ?? '—'}</p>
              {category && <p className="text-sm text-slate-600">{t(`health.bmiCategories.${category}`)}</p>}
            </div>
          </div>
          <p className="text-xs text-slate-500">{t('health.bmiNote')}</p>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label={t('health.activity')}>
              {(id) => (
                <Select id={id} value={f.activity_level ?? ''} onChange={(e) => setF({ ...f, activity_level: e.target.value || null })}>
                  <option value="">{t('health.choose')}</option>
                  {ACTIVITY.map((a) => <option key={a} value={a}>{t(`health.activityLevels.${a}`)}</option>)}
                </Select>
              )}
            </Field>
            <Field label={t('health.diet')}>
              {(id) => (
                <Select id={id} value={f.dietary_preference ?? ''} onChange={(e) => setF({ ...f, dietary_preference: e.target.value || null })}>
                  <option value="">{t('health.choose')}</option>
                  {DIETS.map((d) => <option key={d} value={d}>{t(`health.diets.${d}`)}</option>)}
                </Select>
              )}
            </Field>
          </div>
        </Card>

        <Card className="space-y-5">
          <Field label={t('health.allergies')} optional hint={<>{t('health_extra.allergiesHint')} {t('health.tagsHint')}</>}>
            {(id, d) => <TagInput id={id} describedBy={d} value={f.food_allergies} onChange={(v) => setF({ ...f, food_allergies: v })} />}
          </Field>
          <Field label={t('health.conditions')} optional hint={t('health.conditionsHint')}>
            {(id, d) => <TagInput id={id} describedBy={d} value={f.health_conditions} onChange={(v) => setF({ ...f, health_conditions: v })} />}
          </Field>
        </Card>

        <Card className="grid gap-5 sm:grid-cols-2">
          <Field label={t('health.emergencyName')} optional>
            {(id) => <Input id={id} value={f.emergency_contact_name ?? ''} onChange={(e) => setF({ ...f, emergency_contact_name: e.target.value })} />}
          </Field>
          <Field label={t('health.emergencyPhone')} optional error={errors.emergency_contact_phone}>
            {(id) => <Input id={id} type="tel" dir="ltr" value={f.emergency_contact_phone ?? ''} invalid={!!errors.emergency_contact_phone} onChange={(e) => setF({ ...f, emergency_contact_phone: e.target.value })} />}
          </Field>
        </Card>

        <div className="flex justify-end">
          <Button type="submit" size="lg" loading={busy}>{busy ? t('common.saving') : t('common.save')}</Button>
        </div>
      </form>
    </div>
  )
}
