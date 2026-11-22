import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, ListChecks, Plus, RotateCcw, Search, Sparkles, Stethoscope, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Alert, Button, Card, FullPageSpinner, Input } from '../../components/ui'
import { api } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { PageHeader } from '../../pages/app/profile/MyProfile'
import { ModelCard, SymptomResult, type ModelCardData, type PredictionRecord } from './shared'

type Meta = { card: ModelCardData; vocabulary: { symptoms: string[]; red_flag_symptoms: string[] } }

const COMMON = ['high_fever', 'mild_fever', 'headache', 'cough', 'fatigue', 'vomiting', 'nausea', 'diarrhoea', 'joint_pain', 'skin_rash', 'chills', 'abdominal_pain', 'breathlessness', 'chest_pain', 'runny_nose', 'itching']

const CHIP_TONES = [
  'bg-coral-50 text-coral-600 ring-1 ring-coral-100 hover:bg-coral-100',
  'bg-teal-50 text-teal-700 ring-1 ring-teal-100 hover:bg-teal-100',
  'bg-brand-50 text-brand-700 ring-1 ring-brand-100 hover:bg-brand-100',
  'bg-violet-50 text-violet-700 ring-1 ring-violet-100 hover:bg-violet-100',
  'bg-amber-50 text-amber-700 ring-1 ring-amber-100 hover:bg-amber-100',
]

export default function SymptomChecker() {
  const { t } = useTranslation()
  const meta = useQuery({ queryKey: ['predict-meta', 'symptoms'], queryFn: () => api<Meta>('/api/predict/symptoms/meta') })
  const [selected, setSelected] = useState<string[]>([])
  const [q, setQ] = useState('')
  const run = useMutation({ mutationFn: (symptoms: string[]) => api<PredictionRecord>('/api/predict/symptoms', { method: 'POST', body: { symptoms } }) })

  const label = (s: string) => t(`symptoms.${s}`)
  const all = useMemo(() => {
    const list = meta.data?.vocabulary.symptoms ?? []
    return [...list].sort((a, b) => label(a).localeCompare(label(b)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.data, t])
  const filtered = q.trim()
    ? all.filter((s) => label(s).toLowerCase().includes(q.trim().toLowerCase()) || s.includes(q.trim().toLowerCase().replace(/\s+/g, '_')))
    : all

  if (meta.isLoading) return <FullPageSpinner />
  if (meta.isError) return <Alert kind="error">{errorMessage(t, meta.error)}</Alert>

  const toggle = (s: string) => setSelected((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]))
  const reset = () => {
    setSelected([])
    run.reset()
  }

  if (run.data) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
        <PageHeader title={t('checker.title')} />
        <Alert kind="success">{t('checker.saved')}</Alert>
        <SymptomResult rec={run.data} />
        <ModelCard card={meta.data!.card} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={reset}><RotateCcw className="size-4" aria-hidden /> {t('checker.newCheck')}</Button>
          <Link to="/history/predictions" className="inline-flex items-center px-3 text-sm font-medium text-brand-600">{t('assess.viewHistory')}</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl animate-fade-up">
      <PageHeader title={t('checker.title')} desc={t('checker.subtitle')} />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card className="space-y-5">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800"><span className="grid size-7 place-items-center rounded-lg bg-coral-50 text-coral-600"><Sparkles className="size-4" aria-hidden /></span>{t('checker.common')}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {COMMON.filter((s) => all.includes(s)).map((s, i) => (
                <button key={s} type="button" onClick={() => toggle(s)} aria-pressed={selected.includes(s)}
                  className={clsx('inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium transition hover:-translate-y-0.5', selected.includes(s) ? 'bg-gradient-to-r from-brand-600 to-teal-600 text-white shadow-md shadow-brand-600/25' : CHIP_TONES[i % CHIP_TONES.length])}>
                  {selected.includes(s) ? <Check className="size-3.5" aria-hidden /> : <Plus className="size-3.5" aria-hidden />}
                  {label(s)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800"><span className="grid size-7 place-items-center rounded-lg bg-brand-50 text-brand-600"><ListChecks className="size-4" aria-hidden /></span>{t('checker.all')}</h2>
            <div className="relative mt-2">
              <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('checker.search')} aria-label={t('checker.search')} className="ps-9" />
            </div>
            <div className="mt-3 grid max-h-[26rem] gap-1.5 overflow-y-auto rounded-2xl bg-slate-50/80 p-2 sm:grid-cols-2" role="group" aria-label={t('checker.all')}>
              {filtered.length === 0 && <p className="p-4 text-sm text-slate-500">{t('checker.noResults')}</p>}
              {filtered.map((s) => {
                const on = selected.includes(s)
                return (
                  <label key={s} className={clsx('group relative flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition', on ? 'bg-white shadow-sm ring-1 ring-brand-200' : 'hover:bg-white')}>
                    <input type="checkbox" checked={on} onChange={() => toggle(s)} className="peer absolute start-3 size-5 cursor-pointer opacity-0" />
                    <span className={clsx('grid size-5 shrink-0 place-items-center rounded-md border transition peer-focus-visible:ring-4 peer-focus-visible:ring-brand-100', on ? 'border-transparent bg-gradient-to-br from-brand-500 to-teal-500 text-white' : 'border-slate-300 bg-white group-hover:border-brand-400')} aria-hidden>
                      {on && <Check className="size-3.5" strokeWidth={3} />}
                    </span>
                    <span className={clsx(on ? 'font-medium text-brand-800' : 'text-slate-700')}>{label(s)}</span>
                  </label>
                )
              })}
            </div>
          </div>
        </Card>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="overflow-hidden p-0">
            <div className="flex items-center justify-between bg-gradient-to-r from-brand-700 to-teal-600 px-5 py-4 text-white">
              <h2 className="flex items-center gap-2 font-semibold"><Stethoscope className="size-5" aria-hidden />{t('checker.selected', { count: selected.length })}</h2>
              {!!selected.length && <button type="button" onClick={() => setSelected([])} className="rounded-lg px-2 py-1 text-xs font-medium text-white/80 hover:bg-white/15 hover:text-white">{t('checker.clear')}</button>}
            </div>
            <div className="p-5">
            <div className="mb-3 flex gap-1" aria-hidden>
              {[1, 2, 3, 4, 5].map((n) => <span key={n} className={clsx('h-1.5 flex-1 rounded-full transition', selected.length >= n ? (selected.length >= 3 ? 'bg-teal-500' : 'bg-amber-400') : 'bg-slate-100')} />)}
            </div>
            {selected.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">{t('checker.none')}</p>
            ) : (
              <ul className="mt-3 flex flex-wrap gap-2">
                {selected.map((s) => (
                  <li key={s} className="inline-flex animate-pop items-center gap-1 rounded-full bg-brand-50 px-3 py-1 text-sm font-medium text-brand-700 ring-1 ring-brand-100">
                    {label(s)}
                    <button type="button" onClick={() => toggle(s)} aria-label={t('checker.remove', { item: label(s) })}><X className="size-3.5" /></button>
                  </li>
                ))}
              </ul>
            )}
            {selected.length > 0 && selected.length < 3 && <p className="mt-3 text-xs text-amber-700">{t('checker.minHint')}</p>}
            {run.isError && <Alert kind="error" className="mt-3">{errorMessage(t, run.error)}</Alert>}
            <Button className="mt-4 w-full" size="lg" disabled={!selected.length} loading={run.isPending} onClick={() => run.mutate(selected)}>
              {run.isPending ? t('checker.submitting') : t('checker.submit')}
            </Button>
            </div>
          </Card>
          <p className="px-1 text-xs text-slate-500">{t('assess.disclaimer')}</p>
          <Link to="/assessments" className="block px-1 text-sm font-medium text-brand-600">{t('checker.otherChecks')} →</Link>
        </aside>
      </div>
    </div>
  )
}
