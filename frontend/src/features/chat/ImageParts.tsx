import clsx from 'clsx'
import { AlertTriangle, ImageOff, ScanSearch, ShieldAlert, Stethoscope } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { fetchObjectUrl } from '../../lib/api'

export type ImageAnalysis = {
  id: string
  status: 'ok' | 'rejected_not_skin' | 'rejected_out_of_distribution' | 'failed'
  model_version: string
  predicted_class: string | null
  probability: number | null
  probabilities: Record<string, number>
  gate: { checked?: boolean; description?: string }
  safety: { prompt_review?: boolean }
  attachment_id: string | null
  conversation_id: string | null
  created_at: string
}

const CLASSES = ['mel', 'bcc', 'akiec', 'bkl', 'nv', 'df', 'vasc']
const CONCERN = new Set(['mel', 'bcc', 'akiec'])

/** Private image: fetched with auth and shown via an object URL (never a public URL). */
export function PrivateImage({ attachmentId, className, alt }: { attachmentId: string; className?: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let u: string | null = null
    fetchObjectUrl(`/api/chat/attachments/${attachmentId}`).then((x) => { u = x; setUrl(x) }).catch(() => setFailed(true))
    return () => { if (u) URL.revokeObjectURL(u) }
  }, [attachmentId])
  if (failed) return <div className={clsx('grid place-items-center bg-slate-100 text-slate-400', className)}><ImageOff className="size-6" aria-hidden /></div>
  if (!url) return <div className={clsx('animate-pulse bg-slate-100', className)} />
  return <img src={url} alt={alt} className={clsx('object-cover', className)} />
}

export function AnalysisCard({ a }: { a: ImageAnalysis }) {
  const { t, i18n } = useTranslation()
  const pct = (v: number) => new Intl.NumberFormat(i18n.language === 'en' ? 'en-IN' : `${i18n.language}-IN`, { style: 'percent', maximumFractionDigits: 0 }).format(v)
  if (a.status !== 'ok') {
    return (
      <div className="mt-2 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        <ImageOff className="mt-0.5 size-4 shrink-0" aria-hidden />
        <div>
          <p className="font-semibold">{t(`skin.status.${a.status}`)}</p>
          <p className="mt-0.5 text-amber-800">{t('skin.retryHint')}</p>
        </div>
      </div>
    )
  }
  const sorted = CLASSES.map((c) => [c, a.probabilities[c] ?? 0] as const).sort((x, y) => y[1] - x[1])
  return (
    <div className="mt-2 rounded-xl border border-slate-200 bg-white p-4">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fuchsia-700"><ScanSearch className="size-3.5" aria-hidden />{t('skin.cardTitle')}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900">{t(`skin.classes.${a.predicted_class}`)}</p>
      <p className="text-xs text-slate-500">{t('skin.probabilityLabel', { p: pct(a.probability ?? 0) })}</p>
      {a.safety.prompt_review && (
        <p role="alert" className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-2.5 text-sm font-medium text-red-800"><ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{t('skin.seeDermatologistSoon')}</p>
      )}
      <ul className="mt-3 space-y-1.5">
        {sorted.map(([c, p]) => (
          <li key={c} className="text-xs">
            <div className="flex justify-between gap-2"><span className={clsx(CONCERN.has(c) ? 'text-slate-800' : 'text-slate-600')}>{t(`skin.classes.${c}`)}</span><span className="tabular-nums text-slate-500">{pct(p)}</span></div>
            <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden><div className={clsx('h-full rounded-full', CONCERN.has(c) ? 'bg-fuchsia-500' : 'bg-brand-400')} style={{ width: `${Math.max(1, p * 100)}%` }} /></div>
          </li>
        ))}
      </ul>
      <div className="mt-3 space-y-1.5 border-t border-slate-100 pt-3 text-xs text-slate-600">
        <p className="flex items-start gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-500" aria-hidden />{t('skin.notDiagnosis')}</p>
        <p className="flex items-start gap-1.5"><Stethoscope className="mt-0.5 size-3.5 shrink-0 text-teal-600" aria-hidden />{t('skin.seeDoctor')}</p>
        <Link to="/history/images" className="inline-block font-medium text-brand-600">{t('skin.aboutModel')}</Link>
      </div>
    </div>
  )
}
