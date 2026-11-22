import { ChevronDown, Construction, Phone } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Alert, buttonClasses, Card } from '../../components/ui'
import { PageHeader } from './profile/MyProfile'

const CONTACT_EMAIL = import.meta.env.VITE_CONTACT_EMAIL as string | undefined

export function Help() {
  const { t } = useTranslation()
  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
      <PageHeader title={t('help.title')} desc={t('help.intro')} />
      <Alert kind="error">
        <p className="flex items-center gap-2 font-semibold"><Phone className="size-4" aria-hidden />{t('help.emergencyTitle')}</p>
        <p className="mt-1">{t('help.emergencyBody')}</p>
      </Alert>
      <div className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
        {[1, 2, 3].map((i) => (
          <details key={i} className="group p-5 [&_summary::-webkit-details-marker]:hidden">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-slate-900">
              {t(`help.q${i}`)}
              <ChevronDown className="size-5 shrink-0 text-slate-400 transition group-open:rotate-180" aria-hidden />
            </summary>
            <p className="mt-3 text-slate-600">{t(`help.a${i}`)}</p>
          </details>
        ))}
      </div>
      {CONTACT_EMAIL && (
        <Card>
          <h2 className="font-semibold text-slate-900">{t('help.contactTitle')}</h2>
          <a href={`mailto:${CONTACT_EMAIL}`} className="mt-2 inline-block font-medium text-brand-600" dir="ltr">{CONTACT_EMAIL}</a>
        </Card>
      )}
    </div>
  )
}

/** Honest placeholder for sections whose backend isn't built yet (later phases). */
export function NotBuilt({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation()
  return (
    <div className="mx-auto max-w-xl py-10 text-center animate-fade-up">
      <div className="mx-auto grid size-16 place-items-center rounded-2xl bg-amber-50 text-amber-600">
        <Construction className="size-8" aria-hidden />
      </div>
      <h1 className="mt-5 text-2xl font-bold text-slate-900">{t(titleKey)}</h1>
      <p className="mt-2 font-medium text-amber-700">{t('notBuilt.title')}</p>
      <p className="mt-2 text-slate-600">{t('notBuilt.body')}</p>
      <Link to="/dashboard" className={buttonClasses('outline') + ' mt-6'}>{t('notBuilt.backToDashboard')}</Link>
    </div>
  )
}
