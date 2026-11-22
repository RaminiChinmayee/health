import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  Activity, ArrowRight, Brain, Camera, ClipboardList, Flame, HeartPulse, ListChecks, MapPin, MessageSquare, Phone, ScanFace,
  Sparkles, Utensils, UserCog,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/AuthProvider'
import { Avatar } from '../../components/nav'
import { Alert, buttonClasses, Spinner } from '../../components/ui'
import { intlLocale } from '../../i18n/languages'
import { api } from '../../lib/api'
import { BAND_STYLE, symptomStrength } from '../../features/predict/shared'

type Dash = {
  profile: { completeness: number; missing: string[]; age: number | null; bmi: number | null; bmi_category: string | null }
  counts: { predictions: number; conversations: number; diet_plans: number; image_analyses: number }
  latest_predictions: { id: string; type: string; label: string; score: number | null; display: string; at: string }[]
  nutrition_today: { kcal: number; protein_g: number; meals: number; target_kcal: number | null; target_protein_g: number | null }
  nutrition_week: { date: string; kcal: number }[]
  recent_chats: { id: string; title: string; at: string }[]
  activity: { kind: string; type?: string; label?: string; title?: string; status?: string; kcal?: number; at: string; id: string }[]
}

function Ring({ value, size = 88, stroke = 9, color = 'text-teal-500', children }: { value: number; size?: number; stroke?: number; color?: string; children?: ReactNode }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const v = Math.max(0, Math.min(1, value))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-slate-100" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} strokeLinecap="round" className={clsx('stroke-current transition-[stroke-dashoffset] duration-700', color)} strokeDasharray={c} strokeDashoffset={c * (1 - v)} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  )
}

function Stat({ icon, tone, label, value, sub, to }: { icon: ReactNode; tone: string; label: string; value: ReactNode; sub?: ReactNode; to?: string }) {
  const body = (
    <div className="flex h-full items-start gap-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
      <span className={clsx('grid size-11 shrink-0 place-items-center rounded-xl text-white shadow-sm', tone)}>{icon}</span>
      <div className="min-w-0">
        <p className="text-sm text-slate-500">{label}</p>
        <p className="mt-0.5 text-2xl font-bold text-slate-900">{value}</p>
        {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  )
  return to ? <Link to={to} className="block">{body}</Link> : body
}

function Section({ title, action, children, className }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx('rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card', className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-semibold text-slate-900">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

const BMI_SCALE = [
  { upTo: 18.5, cls: 'bg-sky-400' },
  { upTo: 25, cls: 'bg-mint-500' },
  { upTo: 30, cls: 'bg-amber-400' },
  { upTo: 40, cls: 'bg-red-400' },
]

export default function Dashboard() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const q = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dash>('/api/dashboard') })
  if (!user) return null
  const loc = intlLocale(i18n.language)
  const hour = new Date().getHours()
  const greet = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'
  const firstName = user.full_name.split(' ')[0]
  const d = q.data
  const fmtDate = (iso: string) => new Intl.DateTimeFormat(loc, { day: 'numeric', month: 'short' }).format(new Date(iso))
  const num = (n: number) => new Intl.NumberFormat(loc).format(n)
  const nt = d?.nutrition_today
  const kcalPct = nt?.target_kcal ? nt.kcal / nt.target_kcal : 0
  const week = (() => {
    const out: { date: string; kcal: number }[] = []
    for (let i = 6; i >= 0; i--) {
      const day = new Date()
      day.setDate(day.getDate() - i)
      const key = day.toLocaleDateString('en-CA')
      out.push({ date: key, kcal: d?.nutrition_week.find((w) => w.date === key)?.kcal ?? 0 })
    }
    return out
  })()
  const weekMax = Math.max(nt?.target_kcal ?? 0, ...week.map((w) => w.kcal), 1)

  const quick = [
    { to: '/symptoms', icon: ListChecks, label: t('nav.symptomChecker'), tone: 'from-brand-500 to-brand-700' },
    { to: '/assessments', icon: ClipboardList, label: t('nav2.assessments'), tone: 'from-indigo-500 to-brand-600' },
    { to: '/chat', icon: MessageSquare, label: t('nav.chatbot'), tone: 'from-teal-500 to-teal-700' },
    { to: '/chat?image=1', icon: Camera, label: t('dash.skinCheck'), tone: 'from-fuchsia-500 to-purple-600' },
    { to: '/hospitals', icon: MapPin, label: t('nav.hospitals'), tone: 'from-rose-500 to-rose-600' },
    { to: '/diet', icon: Utensils, label: t('nav.diet'), tone: 'from-mint-500 to-green-700' },
  ]

  return (
    <div className="space-y-6 animate-fade-up">
      {/* ------------------------------------------------ hero */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-brand-700 to-teal-600 p-6 text-white shadow-lift sm:p-8">
        <div className="absolute -end-16 -top-20 size-72 rounded-full bg-white/10 blur-2xl" aria-hidden />
        <div className="absolute -bottom-24 start-1/3 size-72 rounded-full bg-teal-300/20 blur-3xl" aria-hidden />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="hidden rounded-full ring-4 ring-white/20 sm:block"><Avatar size="lg" /></div>
            <div>
              <p className="text-sm text-brand-100">{new Intl.DateTimeFormat(loc, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())}</p>
              <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{t(`dash.greeting.${greet}`, { name: firstName })}</h1>
              <p className="mt-1 text-brand-50">{t('dash.subtitle')}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/chat" className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-brand-700 shadow-sm hover:bg-brand-50">
              <Brain className="size-4" aria-hidden /> {t('dash.askAssistant')}
            </Link>
            <Link to="/assessments" className="inline-flex items-center gap-2 rounded-xl bg-white/15 px-4 py-2.5 text-sm font-semibold text-white ring-1 ring-white/30 hover:bg-white/25">
              <Sparkles className="size-4" aria-hidden /> {t('dash.startCheck')}
            </Link>
          </div>
        </div>
      </section>

      {!user.email_verified && <Alert kind="warning">{t('dashboard.verifyEmail')}</Alert>}
      {q.isLoading && <div className="flex justify-center py-10"><Spinner className="size-8" /></div>}

      {d && (
        <>
          {/* ------------------------------------------------ profile + stats */}
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,2fr)]">
            <section className="flex items-center gap-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card">
              <Ring value={d.profile.completeness / 100} color={d.profile.completeness === 100 ? 'text-mint-500' : 'text-brand-500'}>
                <span className="text-lg font-bold text-slate-900">{d.profile.completeness}%</span>
              </Ring>
              <div className="min-w-0">
                <p className="font-semibold text-slate-900">{d.profile.completeness === 100 ? t('dash.profileDone') : t('dash.profileComplete', { pct: d.profile.completeness })}</p>
                {d.profile.missing.length > 0 && (
                  <>
                    <p className="mt-1 text-sm text-slate-500">{d.profile.missing.map((m) => t(`dash.missing.${m}`)).join(' · ')}</p>
                    <Link to="/profile/health" className={clsx(buttonClasses('secondary', 'sm'), 'mt-3')}><UserCog className="size-4" aria-hidden />{t('dash.completeIt')}</Link>
                  </>
                )}
              </div>
            </section>
            <div className="grid gap-4 sm:grid-cols-2">
              <Stat to="/profile/health" icon={<Activity className="size-5" />} tone="bg-gradient-to-br from-sky-500 to-brand-600" label={t('dash.bmi')}
                value={d.profile.bmi ? num(d.profile.bmi) : '—'}
                sub={d.profile.bmi ? (
                  <span className="mt-1 block">
                    <span className="flex h-1.5 w-40 overflow-hidden rounded-full" aria-hidden>{BMI_SCALE.map((b) => <span key={b.upTo} className={clsx('flex-1', b.cls)} />)}</span>
                    <span className="relative block h-2 w-40" aria-hidden><span className="absolute -top-0.5 size-2 rounded-full bg-slate-900 ring-2 ring-white" style={{ insetInlineStart: `${Math.min(97, Math.max(0, ((d.profile.bmi - 15) / 25) * 100))}%` }} /></span>
                    {t(`health.bmiCategories.${d.profile.bmi_category}`)}
                  </span>
                ) : t('dash.bmiNone')} />
              <Link to="/diet" className="flex items-center gap-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
                <Ring value={kcalPct} size={72} stroke={8} color={kcalPct > 1.1 ? 'text-amber-500' : 'text-mint-500'}>
                  <Flame className="size-5 text-orange-500" aria-hidden />
                </Ring>
                <div className="min-w-0">
                  <p className="text-sm text-slate-500">{t('dash.today')}</p>
                  <p className="text-xl font-bold text-slate-900">{num(nt!.kcal)} <span className="text-sm font-normal text-slate-500">{t('units.kcal')}</span></p>
                  <p className="text-xs text-slate-500">{nt!.target_kcal ? t('dash.kcalOf', { target: num(nt!.target_kcal) }) : t('dash.noTarget')} · {t('dash.meals', { count: nt!.meals })}</p>
                </div>
              </Link>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Stat to="/history/predictions" icon={<HeartPulse className="size-5" />} tone="bg-gradient-to-br from-brand-500 to-indigo-600" label={t('dash.assessments')} value={num(d.counts.predictions)} />
            <Stat to="/history/chats" icon={<MessageSquare className="size-5" />} tone="bg-gradient-to-br from-teal-500 to-teal-700" label={t('dash.conversations')} value={num(d.counts.conversations)} />
            <Stat to="/history/images" icon={<ScanFace className="size-5" />} tone="bg-gradient-to-br from-fuchsia-500 to-purple-600" label={t('dash.images')} value={num(d.counts.image_analyses)} />
          </div>

          {/* ------------------------------------------------ quick actions */}
          <Section title={t('dash.quick')}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {quick.map((x) => (
                <Link key={x.to} to={x.to} className="group flex flex-col items-center gap-2 rounded-2xl border border-slate-100 bg-slate-50/60 p-4 text-center transition hover:-translate-y-0.5 hover:border-brand-200 hover:bg-white hover:shadow-card">
                  <span className={clsx('grid size-12 place-items-center rounded-2xl bg-gradient-to-br text-white shadow-sm transition group-hover:scale-105', x.tone)}><x.icon className="size-6" aria-hidden /></span>
                  <span className="text-sm font-medium text-slate-800">{x.label}</span>
                </Link>
              ))}
            </div>
          </Section>

          {/* ------------------------------------------------ insights */}
          <div className="grid gap-4 lg:grid-cols-3">
            <Section title={t('dash.week')} action={<Link to="/diet" className="text-sm font-medium text-brand-600">{t('dash.viewAll')}</Link>}>
              {week.every((w) => !w.kcal) && <p className="mb-2 text-xs text-slate-500">{t('dash.weekEmpty')}</p>}
              <div className="flex h-36 items-end gap-2" role="img" aria-label={t('dash.week')}>
                {week.map((w) => (
                  <div key={w.date} className="flex flex-1 flex-col items-center gap-1.5">
                    <div className="relative flex w-full flex-1 items-end">
                      {nt?.target_kcal && <div className="absolute inset-x-0 border-t border-dashed border-teal-400" style={{ bottom: `${(nt.target_kcal / weekMax) * 100}%` }} />}
                      <div className={clsx('w-full rounded-t-lg', w.kcal ? 'bg-gradient-to-t from-brand-500 to-teal-400' : 'bg-slate-100')} style={{ height: `${Math.max(3, (w.kcal / weekMax) * 100)}%` }} title={`${num(w.kcal)} ${t('units.kcal')}`} />
                    </div>
                    <span className="text-[10px] text-slate-500">{new Intl.DateTimeFormat(loc, { weekday: 'narrow' }).format(new Date(w.date + 'T12:00'))}</span>
                  </div>
                ))}
              </div>
            </Section>

            <Section title={t('dash.latest')} action={<Link to="/history/predictions" className="text-sm font-medium text-brand-600">{t('dash.viewAll')}</Link>}>
              {!d.latest_predictions.length ? (
                <div className="py-6 text-center text-sm text-slate-500">{t('dash.noChecks')}<div className="mt-3"><Link to="/assessments" className={buttonClasses('secondary', 'sm')}>{t('dash.startCheck')}</Link></div></div>
              ) : (
                <ul className="space-y-2.5">
                  {d.latest_predictions.map((p) => (
                    <li key={p.id}>
                      <Link to={`/history/predictions/${p.id}`} className="flex items-center justify-between gap-3 rounded-xl px-2 py-1.5 hover:bg-slate-50">
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium text-slate-800">{t(`assess.types.${p.type}.title`)}</span>
                          <span className="text-xs text-slate-500">{fmtDate(p.at)}</span>
                        </span>
                        <span className={clsx('shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium', p.type === 'symptoms' ? 'border-slate-200 bg-slate-50 text-slate-700' : BAND_STYLE[p.label])}>
                          {p.type === 'symptoms' ? `${t(`diseases.${p.label}`)} · ${t(`checker_extra.strength.${symptomStrength(p.score)}`)}` : t(`assess.similarity.${p.type}.${p.label}`, { defaultValue: t(`assess.bands.${p.label}`) })}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title={t('dash.recentChats')} action={<Link to="/history/chats" className="text-sm font-medium text-brand-600">{t('dash.viewAll')}</Link>}>
              {!d.recent_chats.length ? (
                <div className="py-6 text-center text-sm text-slate-500">{t('chat.noChats')}<div className="mt-3"><Link to="/chat" className={buttonClasses('secondary', 'sm')}>{t('dash.askAssistant')}</Link></div></div>
              ) : (
                <ul className="space-y-1">
                  {d.recent_chats.map((c) => (
                    <li key={c.id}>
                      <Link to={`/chat/${c.id}`} className="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-slate-50">
                        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-teal-50 text-teal-600"><MessageSquare className="size-4" aria-hidden /></span>
                        <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-slate-800" dir="auto">{c.title || t('chat.untitled')}</span><span className="text-xs text-slate-500">{fmtDate(c.at)}</span></span>
                        <ArrowRight className="size-4 shrink-0 text-slate-300 rtl:rotate-180" aria-hidden />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>

          {/* ------------------------------------------------ activity + emergency */}
          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Section title={t('dash.activity')}>
              {!d.activity.length ? <p className="text-sm text-slate-500">{t('dash.noActivity')}</p> : (
                <ol className="relative space-y-4 border-s-2 border-slate-100 ps-5">
                  {d.activity.map((a) => (
                    <li key={`${a.kind}-${a.id}`} className="relative">
                      <span className={clsx('absolute -start-[1.72rem] top-1 size-3 rounded-full ring-4 ring-white', { prediction: 'bg-brand-500', chat: 'bg-teal-500', image: 'bg-fuchsia-500', diet_plan: 'bg-mint-500' }[a.kind])} aria-hidden />
                      <p className="text-sm text-slate-800">
                        {a.kind === 'prediction' && t('dash.activityKinds.prediction', { what: t(`assess.types.${a.type}.title`) })}
                        {a.kind === 'chat' && t('dash.activityKinds.chat', { what: a.title || t('chat.untitled') })}
                        {a.kind === 'image' && t('dash.activityKinds.image')}
                        {a.kind === 'diet_plan' && t('dash.activityKinds.diet_plan', { kcal: a.kcal })}
                      </p>
                      <p className="text-xs text-slate-500">{new Intl.DateTimeFormat(loc, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(a.at))}</p>
                    </li>
                  ))}
                </ol>
              )}
            </Section>
            <section className="flex flex-col justify-between gap-4 rounded-2xl border border-red-200 bg-gradient-to-br from-red-50 to-white p-5">
              <div>
                <p className="flex items-center gap-2 font-semibold text-red-800"><Phone className="size-5" aria-hidden />{t('dash.emergencyTitle')}</p>
                <p className="mt-2 text-sm text-red-900/80">{t('dash.emergencyBody')}</p>
              </div>
              <div className="flex gap-2">
                <a href="tel:112" className={buttonClasses('danger', 'sm')}><Phone className="size-4" aria-hidden />112</a>
                <Link to="/hospitals" className={buttonClasses('outline', 'sm')}><MapPin className="size-4" aria-hidden />{t('nav.hospitals')}</Link>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
