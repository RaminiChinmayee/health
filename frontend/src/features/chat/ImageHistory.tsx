import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, Camera, Info, MessageSquare, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { buttonClasses, Card, FullPageSpinner } from '../../components/ui'
import { api } from '../../lib/api'
import { PageHeader } from '../../pages/app/profile/MyProfile'
import { useDate, usePct } from '../predict/shared'
import { PrivateImage, type ImageAnalysis } from './ImageParts'

type ModelInfo = {
  version: string; architecture: string; class_names: Record<string, string>; classes: string[]
  dataset: { name: string; source: string; citation: string; license: string; population: string }
  limitations: string[]; protocol: string
  metrics: { n_test: number; accuracy: number; balanced_accuracy: number; macro_f1: number; macro_roc_auc_ovr: number; per_class: Record<string, { n_test: number; precision: number; recall_sensitivity: number; specificity: number; f1: number; roc_auc: number }> }
}

function ModelPanel() {
  const { t } = useTranslation()
  const pct = usePct()
  const q = useQuery({ queryKey: ['image-model'], queryFn: () => api<ModelInfo>('/api/chat/image-model'), retry: false })
  if (q.isError) return <Card className="text-sm text-slate-600">{t('skin.errors.image_model_unavailable')}</Card>
  if (!q.data) return null
  const m = q.data
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center gap-2 p-5 font-semibold text-slate-900"><Info className="size-5 text-brand-600" aria-hidden />{t('skin.aboutModel')}</summary>
      <div className="space-y-4 border-t border-slate-100 p-5 text-sm">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[['skin.metrics.accuracy', m.metrics.accuracy], ['skin.metrics.balanced', m.metrics.balanced_accuracy], ['skin.metrics.macroF1', m.metrics.macro_f1], ['skin.metrics.auc', m.metrics.macro_roc_auc_ovr]].map(([k, v]) => (
            <div key={k as string} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{t(k as string)}</p><p className="text-lg font-semibold">{pct(v as number, 1)}</p></div>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-slate-500"><tr><th className="py-1 text-start">{t('skin.metrics.category')}</th><th>{t('skin.metrics.sensitivity')}</th><th>{t('skin.metrics.specificity')}</th><th>{t('skin.metrics.n')}</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {m.classes.map((c) => <tr key={c}><td className="py-1.5">{t(`skin.classes.${c}`)}</td><td className="text-center">{pct(m.metrics.per_class[c].recall_sensitivity)}</td><td className="text-center">{pct(m.metrics.per_class[c].specificity)}</td><td className="text-center">{m.metrics.per_class[c].n_test}</td></tr>)}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-500" dir="ltr" lang="en">{m.protocol}</p>
        <p className="text-xs text-slate-600" dir="ltr" lang="en">{m.dataset.name} — {m.dataset.population} — {m.dataset.license}. {m.dataset.citation}</p>
        <ul className="list-disc space-y-1 ps-5 text-slate-600">{m.limitations.map((l, i) => <li key={i}>{t(`skin.limits.${i}`, { defaultValue: l })}</li>)}</ul>
      </div>
    </details>
  )
}

export default function ImageHistory() {
  const { t } = useTranslation()
  const date = useDate()
  const pct = usePct()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['image-history'], queryFn: () => api<{ total: number; items: ImageAnalysis[] }>('/api/history/images') })
  const del = useMutation({ mutationFn: (id: string) => api(`/api/history/${id}`, { method: 'DELETE' }), onSuccess: () => { qc.invalidateQueries({ queryKey: ['image-history'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) } })
  return (
    <div className="mx-auto max-w-5xl space-y-6 animate-fade-up">
      <PageHeader title={t('skin.historyTitle')} desc={t('skin.historySubtitle')} action={<Link to="/chat?image=1" className={buttonClasses('primary', 'sm')}><Camera className="size-4" aria-hidden />{t('skin.newCheck')}</Link>} />
      <p className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{t('skin.notDiagnosis')}</p>
      {q.isLoading ? <FullPageSpinner /> : !q.data?.items.length ? (
        <Card className="py-12 text-center text-slate-500"><Camera className="mx-auto mb-3 size-10 text-slate-300" aria-hidden />{t('skin.historyEmpty')}</Card>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.items.map((a) => (
            <li key={a.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
              {a.attachment_id ? <PrivateImage attachmentId={a.attachment_id} alt={t('skin.yourPhoto')} className="h-44 w-full" /> : <div className="h-44 bg-slate-100" />}
              <div className="space-y-1 p-4">
                <p className="text-xs text-slate-500">{date(a.created_at, true)}</p>
                {a.status === 'ok' ? (
                  <>
                    <p className="font-semibold text-slate-900">{t(`skin.classes.${a.predicted_class}`)}</p>
                    <p className={clsx('text-xs', a.safety.prompt_review ? 'font-medium text-red-700' : 'text-slate-500')}>{t('skin.probabilityLabel', { p: pct(a.probability ?? 0) })}{a.safety.prompt_review ? ` · ${t('skin.reviewAdvised')}` : ''}</p>
                  </>
                ) : <p className="text-sm font-medium text-amber-800">{t(`skin.status.${a.status}`)}</p>}
                <div className="flex items-center justify-between pt-2">
                  {a.conversation_id ? <Link to={`/chat/${a.conversation_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-600"><MessageSquare className="size-4" aria-hidden />{t('skin.openChat')}</Link> : <span />}
                  <button type="button" onClick={() => window.confirm(t('skin.confirmDelete')) && del.mutate(a.id)} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label={t('history.delete')}><Trash2 className="size-4" /></button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ModelPanel />
    </div>
  )
}
