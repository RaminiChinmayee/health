import clsx from 'clsx'
import {
  Activity,
  ArrowRight,
  Brain,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileHeart,
  Globe,
  HeartPulse,
  KeyRound,
  Languages,
  Layers,
  Lightbulb,
  Lock,
  Mail,
  MapPin,
  MessageSquare,
  Mic,
  Navigation,
  Phone,
  ShieldCheck,
  Sparkles,
  UserCog,
  UserPlus,
  Utensils,
  TrendingUp,
  ClipboardCheck,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { buttonClasses } from '../../components/ui'
import { LANGUAGES } from '../../i18n/languages'

const CONTACT_EMAIL = import.meta.env.VITE_CONTACT_EMAIL as string | undefined

function SectionHeader({ eyebrow, title, subtitle, center = true }: { eyebrow: string; title: string; subtitle?: string; center?: boolean }) {
  return (
    <div className={clsx('max-w-3xl', center && 'mx-auto text-center')}>
      <p className="text-sm font-semibold uppercase tracking-wider text-teal-600">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{title}</h2>
      {subtitle && <p className="mt-4 text-lg leading-relaxed text-slate-600">{subtitle}</p>}
    </div>
  )
}

function Section({ id, children, className }: { id?: string; children: ReactNode; className?: string }) {
  return (
    <section id={id} className={clsx('scroll-mt-20 py-20 sm:py-24', className)}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">{children}</div>
    </section>
  )
}

// ------------------------------------------------------------------ Hero visual
/** Illustrative product preview. Not real user data, and labelled as such for screen readers. */
function DashboardPreview() {
  const { t } = useTranslation()
  return (
    <div className="relative" role="img" aria-label={t('home.hero.previewLabel')}>
      <div className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-gradient-to-br from-brand-200/50 via-teal-100/50 to-mint-100/50 blur-2xl" />
      <div className="rounded-3xl border border-white/80 bg-white/90 p-5 shadow-lift backdrop-blur" aria-hidden>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-500">HealthAssist AI</p>
            <p className="text-lg font-semibold text-slate-900">{t('home.hero.previewGreeting')}</p>
          </div>
          <div className="size-10 rounded-full bg-gradient-to-br from-brand-500 to-teal-500" />
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-gradient-to-br from-brand-600 to-brand-700 p-4 text-white">
            <div className="flex items-center gap-2 text-xs text-brand-100">
              <Activity className="size-3.5" /> {t('home.hero.previewBmi')}
            </div>
            <p className="mt-2 text-3xl font-bold">22.4</p>
            <p className="text-xs text-brand-100">{t('home.hero.previewBmiValue')}</p>
            <svg viewBox="0 0 120 30" className="mt-2 h-7 w-full">
              <polyline fill="none" stroke="rgb(255 255 255 / .7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points="0,22 15,20 30,24 45,16 60,18 75,12 90,14 105,8 120,10" />
            </svg>
          </div>
          <div className="space-y-3">
            <div className="rounded-2xl bg-mint-50 p-3">
              <div className="flex items-center gap-2 text-xs font-medium text-green-700">
                <Utensils className="size-3.5" /> {t('home.hero.previewMeals')}
              </div>
              <p className="mt-1 text-sm font-semibold text-slate-800">{t('home.hero.previewMealsValue')}</p>
            </div>
            <div className="rounded-2xl bg-teal-50 p-3">
              <div className="flex items-center gap-2 text-xs font-medium text-teal-700">
                <MapPin className="size-3.5" /> {t('home.hero.previewHospitals')}
              </div>
              <p className="mt-1 text-sm font-semibold text-slate-800">{t('home.hero.previewHospitalsValue')}</p>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-2xl border border-slate-100 bg-slate-50 p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <MessageSquare className="size-3.5" /> {t('home.hero.previewChat')}
          </div>
          <div className="mt-3 flex justify-end">
            <p className="max-w-[85%] rounded-2xl rounded-ee-md bg-brand-600 px-3.5 py-2 text-sm text-white">{t('home.hero.previewChatSample')}</p>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <span className="size-2 animate-pulse rounded-full bg-teal-500" />
            <span className="size-2 animate-pulse rounded-full bg-teal-500 [animation-delay:150ms]" />
            <span className="size-2 animate-pulse rounded-full bg-teal-500 [animation-delay:300ms]" />
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
            <div className="h-2 flex-1 rounded bg-slate-100" />
            <Mic className="size-4 text-slate-400" />
          </div>
        </div>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ FAQ
function Faq() {
  const { t } = useTranslation()
  return (
    <div className="mx-auto mt-12 max-w-3xl divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <details key={i} className="group p-5 [&_summary::-webkit-details-marker]:hidden">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-start font-semibold text-slate-900">
            {t(`home.faq.q${i}`)}
            <ChevronDown className="size-5 shrink-0 text-slate-400 transition group-open:rotate-180" aria-hidden />
          </summary>
          <p className="mt-3 leading-relaxed text-slate-600">{t(`home.faq.a${i}`)}</p>
        </details>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ Page
export default function Home() {
  const { t } = useTranslation()

  const features = [
    { key: 'prediction', icon: Brain, tone: 'from-brand-500 to-brand-700' },
    { key: 'chatbot', icon: MessageSquare, tone: 'from-teal-500 to-teal-700' },
    { key: 'multimodal', icon: Mic, tone: 'from-indigo-500 to-brand-600' },
    { key: 'hospitals', icon: MapPin, tone: 'from-rose-500 to-rose-600' },
    { key: 'diet', icon: Utensils, tone: 'from-mint-500 to-green-700' },
    { key: 'records', icon: FileHeart, tone: 'from-sky-500 to-brand-600' },
    { key: 'multilingual', icon: Languages, tone: 'from-amber-500 to-orange-600' },
    { key: 'explainable', icon: Lightbulb, tone: 'from-violet-500 to-purple-600' },
  ]
  const steps = [
    { icon: UserPlus, n: 1 },
    { icon: UserCog, n: 2 },
    { icon: Sparkles, n: 3 },
    { icon: ClipboardCheck, n: 4 },
    { icon: TrendingUp, n: 5 },
  ]
  const benefits = [
    { icon: Layers, n: 1 },
    { icon: HeartPulse, n: 2 },
    { icon: Globe, n: 3 },
    { icon: Clock, n: 4 },
  ]
  const protections = [
    { icon: KeyRound, n: 1 },
    { icon: Lock, n: 2 },
    { icon: UserCog, n: 3 },
    { icon: ShieldCheck, n: 4 },
  ]

  return (
    <>
      {/* ---------------------------------------------------------- Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-brand-50/80 via-white to-white" />
        <div className="absolute -top-40 end-[-10%] -z-10 size-[36rem] rounded-full bg-teal-100/60 blur-3xl" aria-hidden />
        <div className="absolute -start-40 top-40 -z-10 size-[28rem] rounded-full bg-brand-100/60 blur-3xl" aria-hidden />
        <div className="mx-auto grid max-w-7xl items-center gap-14 px-4 pb-20 pt-12 sm:px-6 sm:pt-20 lg:grid-cols-2 lg:px-8 lg:pb-28">
          <div className="animate-fade-up">
            <span className="inline-flex items-center gap-2 rounded-full border border-teal-200 bg-white/80 px-3 py-1 text-xs font-semibold text-teal-700 shadow-sm">
              <Sparkles className="size-3.5" aria-hidden />
              {t('home.hero.badge')}
            </span>
            <h1 className="mt-6 text-4xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-5xl lg:text-[3.4rem]">
              {t('home.hero.title')}
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">{t('home.hero.subtitle')}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className={buttonClasses('primary', 'lg')}>
                {t('home.hero.ctaPrimary')}
                <ArrowRight className="size-5 rtl:rotate-180" aria-hidden />
              </Link>
              <a href="#features" className={buttonClasses('outline', 'lg')}>
                {t('home.hero.ctaSecondary')}
              </a>
            </div>
            <p className="mt-5 flex items-center gap-2 text-sm text-slate-500">
              <ShieldCheck className="size-4 text-teal-600" aria-hidden />
              {t('home.hero.note')}
            </p>
          </div>
          <div className="animate-fade-up [animation-delay:150ms]">
            <DashboardPreview />
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- Features */}
      <Section id="features" className="bg-white">
        <SectionHeader eyebrow={t('home.features.eyebrow')} title={t('home.features.title')} subtitle={t('home.features.subtitle')} />
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {features.map(({ key, icon: Icon, tone }) => (
            <article key={key} className="group rounded-2xl border border-slate-200/80 bg-white p-6 shadow-card transition hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift">
              <div className={clsx('grid size-12 place-items-center rounded-xl bg-gradient-to-br text-white shadow-sm', tone)}>
                <Icon className="size-6" aria-hidden />
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-900">{t(`home.features.${key}.title`)}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{t(`home.features.${key}.desc`)}</p>
            </article>
          ))}
        </div>
      </Section>

      {/* ---------------------------------------------------------- How it works */}
      <Section id="how-it-works" className="bg-gradient-to-b from-slate-50 to-white">
        <SectionHeader eyebrow={t('home.how.eyebrow')} title={t('home.how.title')} />
        <ol className="relative mt-14 grid gap-6 md:grid-cols-5">
          <div className="absolute inset-x-[10%] top-7 hidden h-0.5 bg-gradient-to-r from-brand-200 via-teal-200 to-mint-100 md:block" aria-hidden />
          {steps.map(({ icon: Icon, n }) => (
            <li key={n} className="relative text-center">
              <div className="relative mx-auto grid size-14 place-items-center rounded-2xl border-4 border-white bg-brand-600 text-white shadow-lift">
                <Icon className="size-6" aria-hidden />
                <span className="absolute -end-2 -top-2 grid size-6 place-items-center rounded-full bg-teal-500 text-xs font-bold text-white ring-2 ring-white">{n}</span>
              </div>
              <h3 className="mt-5 font-semibold text-slate-900">{t(`home.how.step${n}.title`)}</h3>
              <p className="mt-2 text-sm text-slate-600">{t(`home.how.step${n}.desc`)}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* ---------------------------------------------------------- Benefits */}
      <Section className="bg-white">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <SectionHeader center={false} eyebrow={t('home.benefits.eyebrow')} title={t('home.benefits.title')} />
          <div className="grid gap-4 sm:grid-cols-2">
            {benefits.map(({ icon: Icon, n }) => (
              <div key={n} className="rounded-2xl bg-gradient-to-br from-brand-50 to-teal-50 p-6">
                <Icon className="size-7 text-brand-600" aria-hidden />
                <h3 className="mt-4 font-semibold text-slate-900">{t(`home.benefits.b${n}.title`)}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{t(`home.benefits.b${n}.desc`)}</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* ---------------------------------------------------------- Privacy */}
      <Section id="privacy" className="bg-slate-950 text-white">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-sm font-semibold uppercase tracking-wider text-teal-400">{t('home.privacy.eyebrow')}</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{t('home.privacy.title')}</h2>
          <p className="mt-4 text-lg text-slate-400">{t('home.privacy.subtitle')}</p>
        </div>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {protections.map(({ icon: Icon, n }) => (
            <div key={n} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
              <div className="grid size-11 place-items-center rounded-xl bg-teal-500/15 text-teal-400">
                <Icon className="size-5" aria-hidden />
              </div>
              <h3 className="mt-4 font-semibold">{t(`home.privacy.p${n}.title`)}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{t(`home.privacy.p${n}.desc`)}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ---------------------------------------------------------- Languages */}
      <Section id="languages" className="bg-white">
        <SectionHeader eyebrow={t('home.languages.eyebrow')} title={t('home.languages.title')} subtitle={t('home.languages.subtitle')} />
        <ul className="mx-auto mt-12 flex max-w-4xl flex-wrap justify-center gap-3">
          {LANGUAGES.map((l) => (
            <li key={l.code} lang={l.code} dir={l.dir} className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-center shadow-card">
              <span className="block text-lg font-semibold text-slate-900">{l.native}</span>
              <span className="block text-xs text-slate-500" dir="ltr">{l.english}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* ---------------------------------------------------------- Facilities */}
      <Section className="bg-gradient-to-br from-teal-50 via-white to-brand-50">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <SectionHeader center={false} eyebrow={t('home.facilities.eyebrow')} title={t('home.facilities.title')} subtitle={t('home.facilities.desc')} />
            <ul className="mt-6 space-y-3">
              {[1, 2, 3].map((n) => (
                <li key={n} className="flex items-center gap-3 text-slate-700">
                  <CheckCircle2 className="size-5 text-teal-600" aria-hidden />
                  {t(`home.facilities.point${n}`)}
                </li>
              ))}
            </ul>
            <p className="mt-6 inline-flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-700">
              <Phone className="size-4" aria-hidden />
              {t('home.facilities.emergency')}
            </p>
          </div>
          {/* Abstract map illustration */}
          <div className="relative aspect-[4/3] overflow-hidden rounded-3xl border border-white bg-white shadow-lift" aria-hidden>
            <svg viewBox="0 0 400 300" className="absolute inset-0 size-full">
              <rect width="400" height="300" fill="#f1f7fb" />
              <path d="M0 210 C80 190 120 240 200 215 S320 170 400 190" stroke="#dbeafe" strokeWidth="26" fill="none" />
              <path d="M140 0 L170 300" stroke="#e2e8f0" strokeWidth="14" />
              <path d="M0 90 L400 120" stroke="#e2e8f0" strokeWidth="14" />
              <path d="M290 0 L260 300" stroke="#e2e8f0" strokeWidth="10" />
              <rect x="30" y="20" width="80" height="50" rx="8" fill="#dcfce7" />
              <rect x="190" y="140" width="50" height="40" rx="8" fill="#dcfce7" />
              <circle cx="200" cy="150" r="70" fill="#0b5cab" opacity=".07" />
              <circle cx="200" cy="150" r="40" fill="#0b5cab" opacity=".1" />
            </svg>
            <div className="absolute start-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rtl:translate-x-1/2">
              <span className="relative flex size-5">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-400 opacity-60" />
                <span className="relative inline-flex size-5 rounded-full border-4 border-white bg-brand-600 shadow" />
              </span>
            </div>
            {[
              ['18%', '22%'],
              ['70%', '30%'],
              ['62%', '72%'],
              ['25%', '68%'],
            ].map(([x, y], i) => (
              <div key={i} className="absolute grid size-9 place-items-center rounded-full bg-white text-rose-600 shadow-card" style={{ insetInlineStart: x, top: y }}>
                <HeartPulse className="size-5" />
              </div>
            ))}
            <div className="absolute bottom-4 start-4 end-4 flex items-center gap-3 rounded-2xl bg-white/95 p-3 shadow-card">
              <div className="grid size-9 place-items-center rounded-xl bg-rose-50 text-rose-600">
                <MapPin className="size-5" />
              </div>
              <div className="flex-1 space-y-1.5">
                <div className="h-2.5 w-2/3 rounded bg-slate-200" />
                <div className="h-2 w-1/3 rounded bg-slate-100" />
              </div>
              <Navigation className="size-5 text-brand-600" />
            </div>
          </div>
        </div>
      </Section>

      {/* ---------------------------------------------------------- FAQ */}
      <Section id="faq" className="bg-slate-50">
        <SectionHeader eyebrow={t('home.faq.eyebrow')} title={t('home.faq.title')} />
        <Faq />
      </Section>

      {/* ---------------------------------------------------------- About + Contact */}
      <Section id="about" className="bg-white">
        <div className="grid gap-12 lg:grid-cols-2">
          <div>
            <SectionHeader center={false} eyebrow={t('home.about.eyebrow')} title={t('home.about.title')} />
            <p className="mt-6 leading-relaxed text-slate-600">{t('home.about.p1')}</p>
            <p className="mt-4 leading-relaxed text-slate-600">{t('home.about.p2')}</p>
          </div>
          <div id="contact" className="scroll-mt-24 rounded-3xl bg-gradient-to-br from-brand-600 to-teal-600 p-8 text-white shadow-lift sm:p-10">
            <p className="text-sm font-semibold uppercase tracking-wider text-brand-100">{t('home.contact.eyebrow')}</p>
            <h2 className="mt-2 text-3xl font-bold">{t('home.contact.title')}</h2>
            <p className="mt-4 text-brand-50">{t('home.contact.desc')}</p>
            {CONTACT_EMAIL ? (
              <>
                <a href={`mailto:${CONTACT_EMAIL}`} className="mt-6 inline-flex items-center gap-3 rounded-xl bg-white/15 px-4 py-3 font-medium hover:bg-white/25">
                  <Mail className="size-5" aria-hidden />
                  <span className="sr-only">{t('home.contact.emailLabel')}: </span>
                  <span dir="ltr">{CONTACT_EMAIL}</span>
                </a>
                <p className="mt-4 text-sm text-brand-100">{t('home.contact.signedInHelp')}</p>
              </>
            ) : (
              <p className="mt-6 text-sm text-brand-100">{t('home.contact.noEmail')}</p>
            )}
          </div>
        </div>
      </Section>

      {/* ---------------------------------------------------------- CTA */}
      <section className="bg-white pb-20">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl border border-brand-100 bg-gradient-to-br from-brand-50 via-white to-mint-50 px-6 py-12 text-center sm:px-12">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900">{t('home.cta.title')}</h2>
            <p className="mt-3 text-lg text-slate-600">{t('home.cta.desc')}</p>
            <Link to="/register" className={clsx(buttonClasses('primary', 'lg'), 'mt-8')}>
              {t('home.cta.button')}
              <ArrowRight className="size-5 rtl:rotate-180" aria-hidden />
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
