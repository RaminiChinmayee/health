import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, ChevronRight, Download, FileHeart, GitCompare, History as HistoryIcon, Image, MessageSquare, Star, Trash2, User as UserIcon, Utensils } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, buttonClasses, Card, Field, FullPageSpinner, Input, Select } from '../../components/ui'
import { api } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { PageHeader } from '../../pages/app/profile/MyProfile'
import { BAND_STYLE, BinaryResult, symptomStrength, ModelCard, SymptomResult, useDate, useNum, usePct, type ModelCardData, type PredictionRecord, type PredictionType } from '../predict/shared'

const TYPES: PredictionType[] = ['symptoms', 'diabetes', 'diabetes_symptoms', 'heart', 'kidney', 'lung', 'parkinsons']
const PAGE = 10

type ListResp = { total: number; items: PredictionRecord[]; counts_by_type: Record<string, number> }

function useLabels() {
  const { t } = useTranslation()
  return {
    type: (k: string) => t(`assess.types.${k}.title`),
    headline: (r: PredictionRecord) => (r.prediction_type === 'symptoms' ? t(`diseases.${r.label}`) : t(`assess.similarity.${r.prediction_type}.${r.label}`, { defaultValue: t(`assess.bands.${r.label}`) })),
    field: (type: string, name: string) => (type === 'symptoms' ? t('nav.symptomChecker') : t(`fields.${type}.${name}.label`)),
  }
}

export function PredictionHistory() {
  const { t } = useTranslation()
  const L = useLabels()
  const date = useDate()
  const pct = usePct()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [type, setType] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(0)
  const [picked, setPicked] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) })
  if (type) params.set('type', type)
  if (from) params.set('date_from', from)
  if (to) params.set('date_to', to)
  const list = useQuery({ queryKey: ['history', type, from, to, page], queryFn: () => api<ListResp>(`/api/history/predictions?${params}`) })
  const del = useMutation({
    mutationFn: (id: string) => api(`/api/history/${id}`, { method: 'DELETE' }),
    onSuccess: (_d, id) => {
      setPicked((p) => p.filter((x) => x !== id))
      setNotice(t('history.deleted'))
      qc.invalidateQueries({ queryKey: ['history'] })
      qc.invalidateQueries({ queryKey: ['records-summary'] })
    },
  })

  const items = list.data?.items ?? []
  const pickedType = items.find((i) => i.id === picked[0])?.prediction_type
  const togglePick = (r: PredictionRecord) =>
    setPicked((p) => (p.includes(r.id) ? p.filter((x) => x !== r.id) : p.length >= 2 ? [p[1], r.id] : [...p, r.id]))
  const filtered = !!(type || from || to)

  return (
    <div className="mx-auto max-w-4xl animate-fade-up">
      <PageHeader title={t('history.title')} desc={t('history.subtitle')} />
      <Card className="mb-5 grid gap-4 sm:grid-cols-3">
        <Field label={t('history.type')}>
          {(id) => (
            <Select id={id} value={type} onChange={(e) => { setType(e.target.value); setPage(0); setPicked([]) }}>
              <option value="">{t('history.allTypes')}</option>
              {TYPES.map((k) => <option key={k} value={k}>{L.type(k)}{list.data?.counts_by_type[k] ? ` (${list.data.counts_by_type[k]})` : ''}</option>)}
            </Select>
          )}
        </Field>
        <Field label={t('history.from')}>{(id) => <Input id={id} type="date" value={from} max={to || undefined} onChange={(e) => { setFrom(e.target.value); setPage(0) }} />}</Field>
        <Field label={t('history.to')}>{(id) => <Input id={id} type="date" value={to} min={from || undefined} onChange={(e) => { setTo(e.target.value); setPage(0) }} />}</Field>
      </Card>

      {notice && <Alert kind="success" className="mb-4">{notice}</Alert>}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">{t('history.compareHint')}</p>
        <div className="flex gap-2">
          {!!picked.length && <Button variant="ghost" size="sm" onClick={() => setPicked([])}>{t('history.clearSelection')}</Button>}
          <Button size="sm" variant="secondary" disabled={picked.length !== 2} onClick={() => navigate(`/history/predictions/compare/${picked[0]}/${picked[1]}`)}>
            <GitCompare className="size-4" aria-hidden /> {t('history.compare')}
          </Button>
        </div>
      </div>

      {list.isLoading ? <FullPageSpinner /> : list.isError ? <Alert kind="error">{errorMessage(t, list.error)}</Alert> : !items.length ? (
        <Card className="py-12 text-center text-slate-500">
          <HistoryIcon className="mx-auto mb-3 size-10 text-slate-300" aria-hidden />
          {filtered ? t('history.emptyFiltered') : t('history.empty')}
          {!filtered && <div className="mt-4"><Link to="/assessments" className={buttonClasses('primary', 'sm')}>{t('assess.start')}</Link></div>}
        </Card>
      ) : (
        <ul className="space-y-3">
          {items.map((r) => {
            const disabled = !!pickedType && pickedType !== r.prediction_type && !picked.includes(r.id)
            return (
              <li key={r.id} className={clsx('flex items-center gap-3 rounded-2xl border bg-white p-4 shadow-card', picked.includes(r.id) ? 'border-brand-400 ring-2 ring-brand-100' : 'border-slate-200')}>
                <input type="checkbox" className="size-4 accent-brand-600" checked={picked.includes(r.id)} disabled={disabled} onChange={() => togglePick(r)} aria-label={t('history.selectForCompare')} />
                <Link to={`/history/predictions/${r.id}`} className="min-w-0 flex-1">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{L.type(r.prediction_type)}</p>
                  <p className="mt-0.5 truncate font-semibold text-slate-900">{L.headline(r)}</p>
                  <p className="text-xs text-slate-500">{date(r.created_at, true)}{r.result.display === 'probability' && r.score != null ? ` · ${pct(r.score)}` : ''}</p>
                </Link>
                <span className={clsx('hidden rounded-full border px-2.5 py-1 text-xs font-medium sm:inline', r.prediction_type === 'symptoms' ? 'border-slate-200 bg-slate-50 text-slate-700' : BAND_STYLE[r.label ?? ''])}>
                  {r.prediction_type === 'symptoms' ? t(`checker_extra.strength.${symptomStrength(r.score)}`) : t(`assess.similarity.${r.prediction_type}.${r.label}`, { defaultValue: t(`assess.bands.${r.label}`) })}
                </span>
                <button type="button" onClick={() => window.confirm(t('history.confirmDelete')) && del.mutate(r.id)} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label={t('history.delete')}>
                  <Trash2 className="size-4" />
                </button>
                <ChevronRight className="size-4 text-slate-300 rtl:rotate-180" aria-hidden />
              </li>
            )
          })}
        </ul>
      )}
      {list.data && list.data.total > PAGE && (
        <div className="mt-5 flex items-center justify-between text-sm">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>{t('history.prev')}</Button>
          <span className="text-slate-500">{t('history.page', { from: page * PAGE + 1, to: Math.min((page + 1) * PAGE, list.data.total), total: list.data.total })}</span>
          <Button variant="outline" size="sm" disabled={(page + 1) * PAGE >= list.data.total} onClick={() => setPage((p) => p + 1)}>{t('history.next')}</Button>
        </div>
      )}
    </div>
  )
}

type Detail = PredictionRecord & { model_card: ModelCardData | null; model_superseded: boolean }

function InputsTable({ rec }: { rec: PredictionRecord }) {
  const { t } = useTranslation()
  const num = useNum()
  if (rec.prediction_type === 'symptoms') {
    return (
      <div className="flex flex-wrap gap-2">
        {((rec.inputs.symptoms as string[]) ?? []).map((s) => <span key={s} className="rounded-lg bg-slate-100 px-2.5 py-1 text-sm">{t(`symptoms.${s}`)}</span>)}
      </div>
    )
  }
  return (
    <dl className="divide-y divide-slate-100 text-sm">
      {Object.entries(rec.inputs).map(([k, v]) => {
        const opt = v != null ? t(`fields.${rec.prediction_type}.${k}.options.${v}`, { defaultValue: '' }) : ''
        return (
          <div key={k} className="flex justify-between gap-4 py-2">
            <dt className="text-slate-600">{t(`fields.${rec.prediction_type}.${k}.label`)}</dt>
            <dd className="text-end font-medium text-slate-900">{v == null ? <span className="text-slate-400">{t('history.notProvided')}</span> : opt || num(v as number)}</dd>
          </div>
        )
      })}
    </dl>
  )
}

export function PredictionDetail() {
  const { id } = useParams()
  const { t } = useTranslation()
  const date = useDate()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['history-detail', id], queryFn: () => api<Detail>(`/api/history/predictions/${id}`) })
  const del = useMutation({
    mutationFn: () => api(`/api/history/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['history'] }); navigate('/history/predictions', { replace: true }) },
  })
  if (q.isLoading) return <FullPageSpinner />
  if (q.isError || !q.data) return <Alert kind="error">{errorMessage(t, q.error)}</Alert>
  const rec = q.data
  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
      <Link to="/history/predictions" className="inline-flex items-center gap-1 text-sm font-medium text-brand-600"><ArrowLeft className="size-4 rtl:rotate-180" aria-hidden /> {t('history.title')}</Link>
      <PageHeader title={t(`assess.types.${rec.prediction_type}.title`)} action={<Button variant="ghost" size="sm" onClick={() => window.confirm(t('history.confirmDelete')) && del.mutate()}><Trash2 className="size-4" aria-hidden /> {t('history.delete')}</Button>} />
      <Alert kind="warning">{t('history.pastBanner', { date: date(rec.created_at, true) })}{rec.model_superseded && <span className="mt-1 block">{t('history.superseded')}</span>}</Alert>
      {rec.prediction_type === 'symptoms' ? <SymptomResult rec={rec} /> : <BinaryResult rec={rec} fieldLabel={(f) => t(`fields.${rec.prediction_type}.${f}.label`)} />}
      <Card>
        <h2 className="mb-3 font-semibold text-slate-900">{t('history.inputs')}</h2>
        <InputsTable rec={rec} />
      </Card>
      {rec.model_card && <ModelCard card={rec.model_card} />}
    </div>
  )
}

export function PredictionCompare() {
  const { a, b } = useParams()
  const { t } = useTranslation()
  const date = useDate()
  const pct = usePct()
  const num = useNum()
  const qa = useQuery({ queryKey: ['history-detail', a], queryFn: () => api<Detail>(`/api/history/predictions/${a}`) })
  const qb = useQuery({ queryKey: ['history-detail', b], queryFn: () => api<Detail>(`/api/history/predictions/${b}`) })
  if (qa.isLoading || qb.isLoading) return <FullPageSpinner />
  if (!qa.data || !qb.data) return <Alert kind="error">{errorMessage(t, qa.error ?? qb.error)}</Alert>
  const [r1, r2] = [qa.data, qb.data].sort((x, y) => x.created_at.localeCompare(y.created_at))
  const type = r1.prediction_type
  const keys = type === 'symptoms' ? [] : Object.keys(r1.inputs)
  const val = (r: PredictionRecord, k: string) => {
    const v = r.inputs[k] as number | null
    if (v == null) return '—'
    return t(`fields.${type}.${k}.options.${v}`, { defaultValue: '' }) || num(v)
  }
  return (
    <div className="mx-auto max-w-4xl space-y-6 animate-fade-up">
      <Link to="/history/predictions" className="inline-flex items-center gap-1 text-sm font-medium text-brand-600"><ArrowLeft className="size-4 rtl:rotate-180" aria-hidden /> {t('history.title')}</Link>
      <PageHeader title={t('history.compareTitle')} desc={t(`assess.types.${type}.title`)} />
      <Alert kind="info">{t('history.subtitle')}</Alert>
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr><th className="p-3 text-start font-medium">{t('history.date')}</th><th className="p-3 text-start font-medium">{date(r1.created_at, true)}</th><th className="p-3 text-start font-medium">{date(r2.created_at, true)}</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            <tr className="font-semibold">
              <td className="p-3">{t('history.result')}</td>
              {[r1, r2].map((r) => (
                <td key={r.id} className="p-3">
                  {type === 'symptoms' ? `${t(`diseases.${r.label}`)} (${t(`checker_extra.strength.${symptomStrength(r.score)}`)})` : `${t(`assess.similarity.${r.prediction_type}.${r.label}`, { defaultValue: t(`assess.bands.${r.label}`) })}${r.result.display === 'probability' ? ` · ${pct(r.score)}` : ''}`}
                </td>
              ))}
            </tr>
            {type === 'symptoms' ? (
              <tr><td className="p-3 align-top">{t('history.inputs')}</td>{[r1, r2].map((r) => <td key={r.id} className="p-3 align-top">{((r.inputs.symptoms as string[]) ?? []).map((s) => t(`symptoms.${s}`)).join(', ')}</td>)}</tr>
            ) : (
              keys.map((k) => (
                <tr key={k} className={clsx(val(r1, k) !== val(r2, k) && 'bg-amber-50/50')}>
                  <td className="p-3 text-slate-600">{t(`fields.${type}.${k}.label`)}</td>
                  <td className="p-3">{val(r1, k)}</td>
                  <td className="p-3">{val(r2, k)}</td>
                </tr>
              ))
            )}
            <tr className="text-xs text-slate-500"><td className="p-3">{t('card.title')}</td><td className="p-3" dir="ltr">v{r1.model_version}</td><td className="p-3" dir="ltr">v{r2.model_version}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ diet plan history
type DietRow = { id: string; title: string; targets: { kcal: number }; is_favorite: boolean; created_at: string; days: number }

export function DietHistory() {
  const { t } = useTranslation()
  const date = useDate()
  const qc = useQueryClient()
  const [favOnly, setFavOnly] = useState(false)
  const q = useQuery({ queryKey: ['diet-history', favOnly], queryFn: () => api<{ total: number; items: DietRow[] }>(`/api/history/diets?favorites_only=${favOnly}`) })
  const fav = useMutation({ mutationFn: (r: DietRow) => api(`/api/diet/plans/${r.id}`, { method: 'PATCH', body: { is_favorite: !r.is_favorite } }), onSuccess: () => qc.invalidateQueries({ queryKey: ['diet-history'] }) })
  const del = useMutation({ mutationFn: (id: string) => api(`/api/history/${id}`, { method: 'DELETE' }), onSuccess: () => qc.invalidateQueries({ queryKey: ['diet-history'] }) })
  return (
    <div className="mx-auto max-w-3xl animate-fade-up">
      <PageHeader title={t('dietHistory.title')} action={<Link to="/diet" className={buttonClasses('primary', 'sm')}>{t('dietHistory.create')}</Link>} />
      <label className="mb-4 inline-flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" className="size-4 accent-brand-600" checked={favOnly} onChange={(e) => setFavOnly(e.target.checked)} />{t('dietHistory.favoritesOnly')}</label>
      {q.isLoading ? <FullPageSpinner /> : !q.data?.items.length ? (
        <Card className="py-12 text-center text-slate-500"><Utensils className="mx-auto mb-3 size-10 text-slate-300" aria-hidden />{t('dietHistory.empty')}</Card>
      ) : (
        <ul className="space-y-3">
          {q.data.items.map((r) => (
            <li key={r.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
              <button type="button" onClick={() => fav.mutate(r)} aria-pressed={r.is_favorite} aria-label={r.is_favorite ? t('dietHistory.unfavorite') : t('dietHistory.favorite')} className="rounded-lg p-1.5 hover:bg-amber-50">
                <Star className={clsx('size-5', r.is_favorite ? 'fill-amber-400 text-amber-400' : 'text-slate-300')} />
              </button>
              <Link to={`/diet?plan=${r.id}`} className="min-w-0 flex-1">
                <p className="truncate font-semibold text-slate-900">{t('dietHistory.created', { date: date(r.created_at) })}</p>
                <p className="text-xs text-slate-500">{t('dietHistory.days', { count: r.days })} · {t('dietHistory.kcal', { kcal: r.targets.kcal })}</p>
              </Link>
              <button type="button" onClick={() => window.confirm(t('history.confirmDelete')) && del.mutate(r.id)} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label={t('history.delete')}><Trash2 className="size-4" /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ records hub
export function Records() {
  const { t } = useTranslation()
  const preds = useQuery({ queryKey: ['records-summary', 'p'], queryFn: () => api<ListResp>('/api/history/predictions?limit=1') })
  const diets = useQuery({ queryKey: ['records-summary', 'd'], queryFn: () => api<{ total: number }>('/api/history/diets?limit=1') })
  const download = async () => {
    const blob = await api<Blob>('/api/profile/export')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'healthassist-my-data.json'
    a.click()
    URL.revokeObjectURL(url)
  }
  const tile = 'flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-card transition hover:border-brand-200 hover:shadow-lift'
  return (
    <div className="mx-auto max-w-4xl animate-fade-up">
      <PageHeader title={t('records.title')} desc={t('records.subtitle')} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Link to="/history/predictions" className={tile}><FileHeart className="size-8 text-brand-600" aria-hidden /><span><span className="block font-semibold">{t('records.predictions')}</span><span className="text-sm text-slate-500">{t('records.predictionsCount', { count: preds.data?.total ?? 0 })}</span></span></Link>
        <Link to="/history/diets" className={tile}><Utensils className="size-8 text-green-600" aria-hidden /><span><span className="block font-semibold">{t('records.diets')}</span><span className="text-sm text-slate-500">{t('records.dietsCount', { count: diets.data?.total ?? 0 })}</span></span></Link>
        <Link to="/profile/health" className={tile}><UserIcon className="size-8 text-teal-600" aria-hidden /><span><span className="block font-semibold">{t('records.healthProfile')}</span><span className="text-sm text-slate-500">{t('records.healthProfileDesc')}</span></span></Link>
        <button type="button" onClick={download} className={clsx(tile, 'text-start')}><Download className="size-8 text-slate-600" aria-hidden /><span><span className="block font-semibold">{t('records.export')}</span><span className="text-sm text-slate-500">{t('records.exportDesc')}</span></span></button>
        <Link to="/history/chats" className={tile}><MessageSquare className="size-8 text-indigo-600" aria-hidden /><span><span className="block font-semibold">{t('records.chats')}</span><span className="text-sm text-slate-500">{t('records.chatsDesc')}</span></span></Link>
        <Link to="/history/images" className={tile}><Image className="size-8 text-fuchsia-600" aria-hidden /><span><span className="block font-semibold">{t('records.images')}</span><span className="text-sm text-slate-500">{t('skin.historySubtitle')}</span></span></Link>
      </div>
    </div>
  )
}
