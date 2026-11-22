import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Activity, ArrowRight, AudioLines, Bean, Wind, Droplet, HeartPulse, ListChecks, RotateCcw, UserCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useParams } from 'react-router-dom'
import { Alert, Button, Card, Field, FullPageSpinner, Input, Select } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { PageHeader } from '../../pages/app/profile/MyProfile'
import { VoiceRecording } from './VoiceRecording'
import { BINARY_TYPES, BinaryResult, ModelCard, type FeatureSpec, type ModelCardData, type PredictionRecord } from './shared'

const ICONS = { symptoms: ListChecks, diabetes: Droplet, diabetes_symptoms: Activity, heart: HeartPulse, kidney: Bean, lung: Wind, parkinsons: AudioLines } as const
const TONES = {
  symptoms: 'from-brand-500 to-brand-700 shadow-brand-500/30',
  diabetes: 'from-sky-400 to-blue-600 shadow-sky-500/30',
  diabetes_symptoms: 'from-violet-500 to-indigo-600 shadow-violet-500/30',
  heart: 'from-rose-500 to-red-600 shadow-rose-500/30',
  kidney: 'from-amber-400 to-orange-600 shadow-amber-500/30',
  lung: 'from-cyan-400 to-sky-600 shadow-cyan-500/30',
  parkinsons: 'from-teal-400 to-emerald-600 shadow-teal-500/30',
} as const

export function AssessmentsHub() {
  const { t } = useTranslation()
  const items = ['symptoms', ...BINARY_TYPES] as const
  return (
    <div className="mx-auto max-w-5xl animate-fade-up">
      <PageHeader title={t('assess.hubTitle')} desc={t('assess.hubSubtitle')} />
      <div className="grid gap-4 sm:grid-cols-2">
        {items.map((k) => {
          const Icon = ICONS[k]
          return (
            <Link key={k} to={k === 'symptoms' ? '/symptoms' : `/assessments/${k}`} className="group relative flex gap-4 overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-card transition hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift">
              <span className={clsx('grid size-12 shrink-0 place-items-center rounded-xl bg-gradient-to-br text-white shadow-lg transition group-hover:scale-105', TONES[k])}><Icon className="size-6" aria-hidden /></span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-slate-900">{t(`assess.types.${k}.title`)}</span>
                <span className="mt-1 block text-sm text-slate-600">{t(`assess.types.${k}.desc`)}</span>
              </span>
              <ArrowRight className="mt-1 size-4 shrink-0 text-slate-400 group-hover:text-brand-600 rtl:rotate-180" aria-hidden />
            </Link>
          )
        })}
      </div>
      <p className="mt-6 text-xs text-slate-500">{t('assess.disclaimer')}</p>
    </div>
  )
}

type Meta = { card: ModelCardData; prefill: { age?: number; sex?: number; bmi?: number } }

function FeatureInput({ type, f, value, onChange, invalid, id, describedBy, label }: { type: string; f: FeatureSpec; value: string; onChange: (v: string) => void; invalid?: boolean; id: string; describedBy?: string; label: string }) {
  const { t } = useTranslation()
  if (f.kind === 'boolean') {
    return (
      <div id={id} data-field={f.name} tabIndex={-1} className="flex gap-2" role="radiogroup" aria-label={label} aria-describedby={describedBy}>
        {[0, 1].map((v) => (
          <button key={v} type="button" role="radio" aria-checked={value === String(v)} onClick={() => onChange(String(v))}
            className={clsx('flex-1 rounded-xl border px-4 py-2.5 text-sm font-medium transition', value === String(v) ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400', invalid && value === '' && 'border-red-400')}>
            {t(`fields.${type}.${f.name}.options.${v}`)}
          </button>
        ))}
      </div>
    )
  }
  if (f.kind === 'choice') {
    return (
      <Select id={id} data-field={f.name} aria-describedby={describedBy} value={value} invalid={invalid} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('assess.choose')}</option>
        {f.options!.map((o) => <option key={o} value={o}>{t(`fields.${type}.${f.name}.options.${o}`)}</option>)}
      </Select>
    )
  }
  return (
    <div className="relative">
      <Input id={id} data-field={f.name} aria-describedby={describedBy} type="number" inputMode="decimal" min={f.min} max={f.max} step={f.step ?? 'any'} value={value} invalid={invalid} onChange={(e) => onChange(e.target.value)} className={f.unit ? 'pe-20' : ''} dir="ltr" />
      {f.unit && <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-xs text-slate-400" dir="ltr">{f.unit}</span>}
    </div>
  )
}

export function AssessmentForm() {
  const { type = '' } = useParams()
  const { t } = useTranslation()
  const valid = (BINARY_TYPES as readonly string[]).includes(type)
  const meta = useQuery({ queryKey: ['predict-meta', type], queryFn: () => api<Meta>(`/api/predict/${type}/meta`), enabled: valid })
  const [values, setValues] = useState<Record<string, string> | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const run = useMutation({ mutationFn: (inputs: Record<string, number | null>) => api<PredictionRecord>(`/api/predict/${type}`, { method: 'POST', body: { inputs } }) })
  const [recorded, setRecorded] = useState<PredictionRecord | null>(null)

  if (!valid) return <Navigate to="/assessments" replace />
  if (meta.isLoading) return <FullPageSpinner />
  if (meta.isError || !meta.data) return <Alert kind="error">{errorMessage(t, meta.error)}</Alert>

  const { card, prefill } = meta.data
  const features = card.features ?? []
  const fieldLabel = (name: string) => t(`fields.${type}.${name}.label`)
  // Initialise from the profile once.
  const v: Record<string, string> =
    values ??
    Object.fromEntries(
      features.map((f) => {
        const src = f.profile_source ? prefill[f.profile_source] : undefined
        return [f.name, src != null && (f.min == null || src >= f.min) && (f.max == null || src <= f.max) ? String(src) : '']
      }),
    )
  const set = (name: string, val: string) => {
    setValues({ ...v, [name]: val })
    setErrors((e) => ({ ...e, [name]: '' }))
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const errs: Record<string, string> = {}
    const inputs: Record<string, number | null> = {}
    for (const f of features) {
      const raw = v[f.name]
      if (raw === '') {
        if (f.required !== false) errs[f.name] = t('validation.required')
        inputs[f.name] = null
        continue
      }
      const n = Number(raw)
      if (Number.isNaN(n) || (f.min != null && n < f.min) || (f.max != null && n > f.max)) errs[f.name] = t('assess_extra.outOfRange', { min: f.min, max: f.max })
      inputs[f.name] = n
    }
    setErrors(errs)
    if (Object.keys(errs).length) {
      document.querySelector<HTMLElement>(`[data-field="${Object.keys(errs)[0]}"]`)?.focus()
      return
    }
    run.mutate(inputs, {
      onError: (err) => {
        if (err instanceof ApiError && err.code === 'validation_error') {
          setErrors(Object.fromEntries(Object.entries(err.fields).map(([k, c]) => [k, c === 'out_of_range' ? t('assess_extra.outOfRange', { min: features.find((f) => f.name === k)?.min, max: features.find((f) => f.name === k)?.max }) : t(`validation.${c}`, { defaultValue: t('validation.value_error') })])))
        }
      },
    })
  }

  const result = run.data ?? recorded
  if (result) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
        <PageHeader title={t(`assess.types.${type}.title`)} />
        <Alert kind="success">{t('checker.saved')}</Alert>
        {recorded && <Alert kind="warning">{t('voiceTest.resultNote')}</Alert>}
        <BinaryResult rec={result} fieldLabel={fieldLabel} />
        <ModelCard card={card} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => { run.reset(); setRecorded(null) }}><RotateCcw className="size-4" aria-hidden /> {t('assess.again')}</Button>
          <Link to="/history/predictions" className="inline-flex items-center px-3 text-sm font-medium text-brand-600">{t('assess.viewHistory')}</Link>
        </div>
      </div>
    )
  }

  const required = features.filter((f) => f.required !== false)
  const optional = features.filter((f) => f.required === false)
  const renderField = (f: FeatureSpec) => {
    const fromProfile = f.profile_source && prefill[f.profile_source] != null && v[f.name] === String(prefill[f.profile_source])
    const help = t(`fields.${type}.${f.name}.help`, { defaultValue: '' })
    return (
      <Field key={f.name} label={<span className="inline-flex flex-wrap items-center gap-2">{fieldLabel(f.name)}{fromProfile && <span className="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-0.5 text-xs font-normal text-teal-700"><UserCheck className="size-3" aria-hidden />{t('assess.fromProfile')}</span>}</span>} error={errors[f.name]} hint={help || undefined}>
        {(id, d) => <FeatureInput type={type} f={f} id={id} label={fieldLabel(f.name)} describedBy={d} value={v[f.name]} invalid={!!errors[f.name]} onChange={(val) => set(f.name, val)} />}
      </Field>
    )
  }

  return (
    <div className="mx-auto max-w-3xl animate-fade-up">
      <PageHeader title={t(`assess.types.${type}.title`)} desc={t(`assess.types.${type}.desc`)} />
      {type === 'parkinsons' && <VoiceRecording onResult={setRecorded} />}
      {type === 'parkinsons' && <Alert kind="info" className="mb-5">{t('assess.parkinsonsIntro')}</Alert>}
      <form onSubmit={submit} noValidate className="space-y-6">
        <Card className="grid gap-5 sm:grid-cols-2">{required.map(renderField)}</Card>
        {!!optional.length && (
          <Card>
            <h2 className="mb-4 text-sm font-semibold text-slate-600">{t('assess.optionalSection')}</h2>
            <div className="grid gap-5 sm:grid-cols-2">{optional.map(renderField)}</div>
          </Card>
        )}
        {run.isError && !(run.error instanceof ApiError && run.error.code === 'validation_error') && <Alert kind="error">{errorMessage(t, run.error)}</Alert>}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500">{t('assess.disclaimer')}</p>
          <Button type="submit" size="lg" loading={run.isPending}>{run.isPending ? t('assess.submitting') : t('assess.submit')}</Button>
        </div>
      </form>
      <div className="mt-6"><ModelCard card={card} /></div>
    </div>
  )
}
