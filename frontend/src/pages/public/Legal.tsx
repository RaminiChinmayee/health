import { useTranslation } from 'react-i18next'

const UPDATED = '2026-11-21'

export default function Legal({ kind }: { kind: 'privacy' | 'terms' | 'disclaimer' }) {
  const { t, i18n } = useTranslation()
  const paragraphs = t(`legal.${kind}Body`).split('\n').filter(Boolean)
  const date = new Intl.DateTimeFormat(i18n.language === 'en' ? 'en-IN' : `${i18n.language}-IN`, { dateStyle: 'long' }).format(new Date(UPDATED))
  return (
    <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{t(`legal.${kind}Title`)}</h1>
      <p className="mt-2 text-sm text-slate-500">{t('legal.lastUpdated', { date })}</p>
      <div className="mt-8 space-y-5 text-base leading-relaxed text-slate-700">
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>
    </article>
  )
}
