import clsx from 'clsx'
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, Info, MapPin, Phone, ShieldAlert, ShieldCheck, Stethoscope } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Alert, buttonClasses } from '../../components/ui'
import { intlLocale } from '../../i18n/languages'
import { DISEASE_DOCTORS } from './diseaseDoctors'

// ------------------------------------------------------------------ types
export type PredictionType = 'symptoms' | 'diabetes' | 'diabetes_symptoms' | 'heart' | 'kidney' | 'lung' | 'parkinsons'
export const BINARY_TYPES = ['diabetes_symptoms', 'diabetes', 'heart', 'kidney', 'lung', 'parkinsons'] as const

export type FeatureSpec = {
  name: string
  kind: 'number' | 'choice' | 'boolean'
  required?: boolean
  min?: number
  max?: number
  step?: number
  unit?: string
  options?: number[]
  profile_source?: 'age' | 'sex' | 'bmi'
}

export type Metrics = Record<string, number | null | undefined>
export type ModelCardData = {
  key: string
  version: string
  title: string
  algorithm: string
  trained_at: string
  display: 'probability' | 'similarity'
  dataset: { name: string; source: string; citation?: string; license: string; population: string; rows_after_dedup?: number; unique_patterns?: number }
  limitations: string[]
  notes?: string[]
  protocol: string
  features?: FeatureSpec[]
  metrics: {
    test?: Metrics
    ci95?: Record<string, [number, number]>
    cv?: Record<string, { mean: number; std: number }>
    external?: Record<string, Metrics>
    selected?: Record<string, { mean: number; std: number }>
  }
}

export type Warning = { code: string; fields?: string[]; symptoms?: string[]; diseases?: string[] }
export type Contribution = { feature: string; effect: number; value?: number; typical_value?: number }
export type PredictionRecord = {
  id: string
  prediction_type: PredictionType
  model_key: string
  model_version: string
  inputs: Record<string, unknown>
  result: {
    probability?: number
    risk_band?: string
    display?: 'probability' | 'similarity'
    matches?: { disease: string; score: number }[]
    typical_not_reported?: string[]
  }
  score: number | null
  label: string | null
  contributions: Contribution[]
  safety: { warnings: Warning[]; disclaimer: string; emergency?: boolean }
  created_at: string
}

// ------------------------------------------------------------------ helpers
export function usePct() {
  const { i18n } = useTranslation()
  return (v: number | null | undefined, digits = 0) =>
    v == null ? '—' : new Intl.NumberFormat(intlLocale(i18n.language), { style: 'percent', maximumFractionDigits: digits }).format(v)
}

export function useNum() {
  const { i18n } = useTranslation()
  return (v: number | null | undefined, digits = 4) =>
    v == null ? '—' : new Intl.NumberFormat(intlLocale(i18n.language), { maximumFractionDigits: digits }).format(v)
}

export function useDate() {
  const { i18n } = useTranslation()
  return (iso: string, withTime = false) =>
    new Intl.DateTimeFormat(intlLocale(i18n.language), withTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(new Date(iso))
}

export const symptomStrength = (s: number | null | undefined) => ((s ?? 0) >= 0.6 ? 'strong' : (s ?? 0) >= 0.2 ? 'possible' : 'weak')

const BAND_GLOW: Record<string, string> = {
  lower: 'bg-gradient-to-br from-mint-50 to-teal-50',
  moderate: 'bg-gradient-to-br from-amber-50 to-orange-50',
  higher: 'bg-gradient-to-br from-red-50 to-rose-50',
  resembles_healthy: 'bg-gradient-to-br from-mint-50 to-teal-50',
  inconclusive: 'bg-gradient-to-br from-slate-50 to-brand-50',
  resembles_condition: 'bg-gradient-to-br from-amber-50 to-orange-50',
}
const BAND_ICON: Record<string, typeof ShieldCheck> = { lower: ShieldCheck, resembles_healthy: ShieldCheck, moderate: AlertTriangle, resembles_condition: AlertTriangle, higher: ShieldAlert, inconclusive: Info }

export const BAND_STYLE: Record<string, string> = {
  lower: 'bg-mint-50 text-green-800 border-mint-100',
  moderate: 'bg-amber-50 text-amber-900 border-amber-200',
  higher: 'bg-red-50 text-red-800 border-red-200',
  resembles_healthy: 'bg-mint-50 text-green-800 border-mint-100',
  inconclusive: 'bg-slate-50 text-slate-800 border-slate-200',
  resembles_condition: 'bg-amber-50 text-amber-900 border-amber-200',
}

// ------------------------------------------------------------------ emergency + warnings
export function EmergencyBanner({ warnings }: { warnings: Warning[] }) {
  const { t } = useTranslation()
  const red = warnings.find((w) => w.code === 'red_flag_symptoms')
  const urgent = warnings.find((w) => w.code === 'urgent_condition_possible')
  if (!red && !urgent) return null
  return (
    <div role="alert" className="rounded-2xl border-2 border-red-300 bg-red-50 p-5 text-red-900">
      <p className="flex items-center gap-2 text-lg font-bold">
        <ShieldAlert className="size-6" aria-hidden /> {t('emergency.title')}
      </p>
      {red && <p className="mt-2">{t('emergency.redFlags', { symptoms: red.symptoms!.map((s) => t(`symptoms.${s}`)).join(', ') })}</p>}
      {urgent && <p className="mt-2">{t('emergency.urgent', { diseases: urgent.diseases!.map((d) => t(`diseases.${d}`)).join(', ') })}</p>}
      <p className="mt-2 font-semibold">{t('emergency.call')}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <a href="tel:112" className={buttonClasses('danger')}>
          <Phone className="size-4" aria-hidden /> 112
        </a>
        <Link to="/hospitals" className={buttonClasses('outline')}>
          <MapPin className="size-4" aria-hidden /> {t('emergency.findHospital')}
        </Link>
      </div>
    </div>
  )
}

export function Warnings({ warnings, fieldLabel }: { warnings: Warning[]; fieldLabel?: (f: string) => string }) {
  const { t } = useTranslation()
  const shown = warnings.filter((w) => !['red_flag_symptoms', 'urgent_condition_possible'].includes(w.code))
  if (!shown.length) return null
  return (
    <div className="space-y-2">
      {shown.map((w) => (
        <Alert key={w.code} kind={w.code === 'consult_doctor' ? 'warning' : 'info'}>
          {t(`assess.warnings.${w.code}`)}
          {w.fields && fieldLabel && <span className="mt-1 block text-xs opacity-80">{w.fields.map(fieldLabel).join(', ')}</span>}
        </Alert>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ model card
function Metric({ label, value, ci }: { label: string; value: string; ci?: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-lg font-semibold text-slate-900">{value}</p>
      {ci && <p className="text-xs text-slate-500">{ci}</p>}
    </div>
  )
}

export function ModelCard({ card, defaultOpen = false }: { card: ModelCardData; defaultOpen?: boolean }) {
  const { t } = useTranslation()
  const pct = usePct()
  const date = useDate()
  const m = card.metrics
  const ci = (k: string) => (m.ci95?.[k] ? t('card.ci', { lo: pct(m.ci95[k][0]), hi: pct(m.ci95[k][1]) }) : undefined)
  return (
    <details open={defaultOpen} className="group rounded-2xl border border-slate-200 bg-white [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5 font-semibold text-slate-900">
        <span className="flex items-center gap-2">
          <Info className="size-5 text-brand-600" aria-hidden /> {t('card.title')}
        </span>
        <ChevronDown className="size-5 text-slate-400 transition group-open:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-5 border-t border-slate-100 p-5 text-sm">
        <p className="text-xs text-slate-500">{t('card.version', { version: card.version, date: date(card.trained_at) })} · {card.algorithm}</p>
        {m.test ? (
          <div>
            <h3 className="font-semibold text-slate-900">{t('card.method')}</h3>
            <p className="mt-1 text-slate-600">{t('card.testSize', { n: m.test.n })}</p>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Metric label={t('card.sensitivity')} value={pct(m.test.recall_sensitivity)} ci={ci('recall_sensitivity')} />
              <Metric label={t('card.specificity')} value={pct(m.test.specificity)} ci={ci('specificity')} />
              <Metric label={t('card.accuracy')} value={pct(m.test.accuracy)} ci={ci('accuracy')} />
              <Metric label={t('card.auc')} value={pct(m.test.roc_auc)} ci={ci('roc_auc')} />
            </div>
            {m.cv?.roc_auc && <p className="mt-2 text-xs text-slate-500">{t('card.cv', { mean: pct(m.cv.roc_auc.mean, 1), sd: pct(m.cv.roc_auc.std, 1) })}</p>}
            {m.external &&
              Object.entries(m.external).map(([name, e]) => (
                <p key={name} className="mt-1 text-xs text-slate-500">
                  {t('card.external', { name, acc: pct(e.accuracy), auc: pct(e.roc_auc) })}
                </p>
              ))}
          </div>
        ) : m.selected ? (
          <div>
            <h3 className="font-semibold text-slate-900">{t('card.method')}</h3>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <Metric label={t('card.symTop1')} value={pct(m.selected.partial_top1?.mean, 1)} />
              <Metric label={t('card.symTop3')} value={pct(m.selected.partial_top3?.mean, 1)} />
              <Metric label={t('card.symFull')} value={pct(m.selected.full_top1?.mean, 1)} />
            </div>
          </div>
        ) : null}
        <p className="text-xs text-slate-500" lang="en" dir="ltr">{card.protocol}</p>
        <div>
          <h3 className="font-semibold text-slate-900">{t('card.dataset')}</h3>
          <dl className="mt-2 space-y-1 text-slate-600" lang="en" dir="ltr">
            <div><dt className="inline font-medium">{t('card.dataset')}: </dt><dd className="inline">{card.dataset.name}</dd></div>
            <div><dt className="inline font-medium">{t('card.population')}: </dt><dd className="inline">{card.dataset.population}</dd></div>
            <div><dt className="inline font-medium">{t('card.license')}: </dt><dd className="inline">{card.dataset.license}</dd></div>
            {card.dataset.citation && <div><dt className="inline font-medium">{t('card.citation')}: </dt><dd className="inline">{card.dataset.citation}</dd></div>}
            <div>
              <dt className="inline font-medium">{t('card.source')}: </dt>
              <dd className="inline break-all"><a className="text-brand-600 underline" href={card.dataset.source.split(' ')[0]} target="_blank" rel="noreferrer">{card.dataset.source.split(' ')[0]}</a></dd>
            </div>
            {card.dataset.rows_after_dedup != null && <div className="text-xs">{t('card.rows', { n: card.dataset.rows_after_dedup })}</div>}
            {card.dataset.unique_patterns != null && <div className="text-xs">{t('card.patterns', { n: card.dataset.unique_patterns })}</div>}
          </dl>
        </div>
        <div>
          <h3 className="flex items-center gap-1.5 font-semibold text-slate-900"><AlertTriangle className="size-4 text-amber-500" aria-hidden /> {t('card.limitations')}</h3>
          {/* Translated per model version; falls back to the card's English text if a translation is missing. */}
          <ul className="mt-2 list-disc space-y-1.5 ps-5 text-slate-600">
            {card.limitations.map((l, i) => <li key={i}>{t(`limits.${card.key}.${i}`, { defaultValue: l })}</li>)}
          </ul>
        </div>
        {!!card.notes?.length && (
          <div>
            <h3 className="font-semibold text-slate-900">{t('card.notes')}</h3>
            <ul className="mt-2 list-disc space-y-1 ps-5 text-xs text-slate-500" lang="en" dir="ltr">
              {card.notes.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        )}
      </div>
    </details>
  )
}

// ------------------------------------------------------------------ results
export function BinaryResult({ rec, fieldLabel, children }: { rec: PredictionRecord; fieldLabel: (f: string) => string; children?: ReactNode }) {
  const { t } = useTranslation()
  const pct = usePct()
  const num = useNum()
  const band = rec.result.risk_band ?? 'inconclusive'
  const similarity = rec.result.display === 'similarity'
  const p = rec.result.probability ?? 0
  const Icon = BAND_ICON[band] ?? Info
  return (
    <div className="space-y-5">
      <div className={clsx('relative overflow-hidden rounded-3xl border p-6 shadow-card sm:p-7', BAND_STYLE[band], BAND_GLOW[band])}>
        <Icon className="pointer-events-none absolute -bottom-8 -end-6 size-40 opacity-[0.07]" strokeWidth={1.25} aria-hidden />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
          {!similarity && (
            <div className="relative grid size-32 shrink-0 place-items-center self-center" aria-hidden>
              <svg viewBox="0 0 120 120" className="absolute inset-0 -rotate-90">
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="12" />
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" strokeWidth="12" strokeLinecap="round"
                  strokeDasharray={`${Math.max(0.02, p) * 326.7} 326.7`} className="transition-[stroke-dasharray] duration-700" />
              </svg>
              <span className="text-3xl font-extrabold">{pct(p)}</span>
            </div>
          )}
          {similarity && (
            <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-white/70 shadow-sm"><Icon className="size-8" aria-hidden /></span>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium opacity-80">{t('assess.resultTitle')}</p>
            <p className="mt-1 text-2xl font-bold">{similarity ? t(`assess.similarity.${rec.prediction_type}.${band}`, { defaultValue: t(`assess.bands.${band}`) }) : t(`assess.bands.${band}`)}</p>
            {!similarity ? (
              <>
                <p className="mt-1 text-sm font-medium opacity-80">{t('assess.probability')}</p>
                <p className="mt-3 text-sm">{t('assess.probabilityExplain', { n: Math.round(p * 100) })}</p>
              </>
            ) : (
              <p className="mt-3 text-sm">{t(`assess.similarity.${rec.prediction_type}.explain`, { defaultValue: t('assess.similarityExplain') })}</p>
            )}
          </div>
        </div>
      </div>

      <Warnings warnings={rec.safety.warnings} fieldLabel={fieldLabel} />

      {!!rec.contributions.length && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-slate-900">{t('assess.factorsTitle')}</h3>
          <p className="mt-1 text-xs text-slate-500">{t('assess.factorsExplain')}</p>
          <ul className="mt-4 space-y-3">
            {rec.contributions.map((c) => {
              const up = c.effect > 0
              const pts = Math.abs(Math.round(c.effect * 1000) / 10)
              return (
                <li key={c.feature} className="flex items-start gap-3">
                  <span className={clsx('mt-0.5 grid size-7 shrink-0 place-items-center rounded-full', up ? 'bg-red-50 text-red-600' : 'bg-mint-50 text-green-700')}>
                    {up ? <ArrowUp className="size-4" aria-hidden /> : <ArrowDown className="size-4" aria-hidden />}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{fieldLabel(c.feature)}</p>
                    <p className="text-xs text-slate-600">
                      {similarity ? null : (up ? t('assess.raised', { pts }) : t('assess.lowered', { pts }))}
                      {c.value != null && <span className="ms-1 text-slate-400">· {t('assess.typical', { value: num(c.value), typical: num(c.typical_value) })}</span>}
                    </p>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}
      <p className="text-xs text-slate-500">{t('assess.disclaimer')}</p>
      {children}
    </div>
  )
}

export function SymptomResult({ rec }: { rec: PredictionRecord }) {
  const { t } = useTranslation()
  // Raw scores from this model are extreme (synthetic training data), so we show a qualitative
  // strength instead of a percentage, and omit near-zero matches.
  const all = rec.result.matches ?? []
  const matches = all.filter((m, i) => i === 0 || m.score >= 0.02)
  const top = all[0]?.disease
  const strength = (s: number) => (s >= 0.6 ? 'strong' : s >= 0.2 ? 'possible' : 'weak')
  const tone = { strong: 'bg-brand-600', possible: 'bg-brand-400', weak: 'bg-brand-200' }
  return (
    <div className="space-y-5">
      <EmergencyBanner warnings={rec.safety.warnings} />
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="text-lg font-semibold text-slate-900">{t('checker.resultsTitle')}</h3>
        <p className="mt-1 text-xs text-slate-500">{t('checker_extra.strengthExplain')}</p>
        <ol className="mt-4 space-y-3">
          {matches.map((m, i) => {
            const st = strength(m.score)
            return (
              <li key={m.disease} className={clsx('overflow-hidden rounded-2xl border transition', i === 0 ? 'border-brand-200 bg-gradient-to-r from-brand-50/60 to-teal-50/40 shadow-sm' : 'border-slate-100 hover:border-brand-100')}>
                <details open={i === 0} className="group">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-3 [&::-webkit-details-marker]:hidden">
                    <span className={clsx('flex items-center gap-1.5 font-medium', i === 0 ? 'text-slate-900' : 'text-slate-700')}>
                      <ChevronDown className="size-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180" aria-hidden />
                      <span className={clsx('grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold', i === 0 ? 'bg-gradient-to-br from-brand-600 to-teal-500 text-white shadow' : 'bg-slate-100 text-slate-600')} aria-hidden>{i + 1}</span>
                      <span className="sr-only">{i + 1}.</span>{t(`diseases.${m.disease}`)}
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-slate-600">
                      <span className="flex gap-0.5" aria-hidden>
                        {['weak', 'possible', 'strong'].map((lvl, j) => (
                          <span key={lvl} className={clsx('h-2 w-5 rounded-full', j <= ['weak', 'possible', 'strong'].indexOf(st) ? tone[st as keyof typeof tone] : 'bg-slate-100')} />
                        ))}
                      </span>
                      {t(`checker_extra.strength.${st}`)}
                    </span>
                  </summary>
                  <DiseaseCare disease={m.disease} />
                </details>
              </li>
            )
          })}
        </ol>
        {matches.length === 1 && <p className="mt-3 text-sm text-slate-500">{t('checker_extra.noOthers')}</p>}
        <p className="mt-3 text-xs text-slate-500">{t('checker_extra.careNote')}</p>
      </div>
      <Warnings warnings={rec.safety.warnings} />
      {!!rec.contributions.length && top && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-slate-900">{t('checker.whyTitle')}</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            {rec.contributions.filter((c) => c.effect > 0).map((c) => (
              <span key={c.feature} className="rounded-lg bg-brand-50 px-2.5 py-1 text-sm text-brand-700">{t(`symptoms.${c.feature}`)}</span>
            ))}
          </div>
        </div>
      )}
      {!!rec.result.typical_not_reported?.length && top && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-slate-900">{t('checker.notReported', { disease: t(`diseases.${top}`) })}</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            {rec.result.typical_not_reported.map((s) => (
              <span key={s} className="rounded-lg bg-slate-100 px-2.5 py-1 text-sm text-slate-700">{t(`symptoms.${s}`)}</span>
            ))}
          </div>
        </div>
      )}
      <p className="text-xs text-slate-500">{t('assess.disclaimer')}</p>
    </div>
  )
}

function DiseaseCare({ disease }: { disease: string }) {
  const { t, i18n } = useTranslation()
  const key = `disease_info.${disease}`
  if (!i18n.exists(key)) return null
  const pre = t(`${key}.precautions`, { returnObjects: true }) as Record<string, string>
  const steps = Object.keys(pre).sort((a, b) => +a - +b).map((k) => pre[k])
  const doctors = DISEASE_DOCTORS[disease] ?? []
  return (
    <div className="space-y-3 border-t border-slate-100 px-4 pb-4 pt-3 text-sm">
      {!!doctors.length && (
        <div>
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500"><Stethoscope className="size-3.5" aria-hidden /> {t('checker_extra.consult')}</p>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {doctors.map((d) => (
              <span key={d} className={clsx('rounded-lg px-2.5 py-1 font-medium', d === 'emergency' ? 'bg-red-50 text-red-700' : 'bg-teal-50 text-teal-800')}>{t(`doctors.${d}`)}</span>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500"><ShieldCheck className="size-3.5" aria-hidden /> {t('checker_extra.precautions')}</p>
        <ul className="mt-1.5 list-disc space-y-1 ps-5 text-slate-700">{steps.map((x, j) => <li key={j}>{x}</li>)}</ul>
      </div>
      <p className="rounded-lg bg-amber-50 px-3 py-2 text-amber-900"><span className="font-semibold">{t('checker_extra.urgentIf')}</span> {t(`${key}.urgent`)}</p>
    </div>
  )
}
