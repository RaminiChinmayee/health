import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, ChefHat, ChevronDown, Coffee, Cookie, Heart, Moon, Salad, Info, Sparkles, Star, ThumbsDown, ThumbsUp, Trash2, UserCog } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { Alert, Button, buttonClasses, Card, Field, FullPageSpinner, Select } from '../../components/ui'
import { intlLocale } from '../../i18n/languages'
import { api, ApiError } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { PageHeader } from '../../pages/app/profile/MyProfile'

type Nutrients = { kcal: number; protein_g: number; fat_g: number; carbs_g: number; fiber_g: number }
type Targets = Nutrients & { bmr: number; tdee: number }
type Meal = { slot: 'breakfast' | 'lunch' | 'snack' | 'dinner'; dish: string; servings: number; nutrients: Nutrients; omit: string[]; extra?: boolean }
type Plan = { id: string; title: string; targets: Targets; is_favorite: boolean; created_at: string; plan: { days: { day: number; meals: Meal[]; totals: Nutrients }[]; notes: { code: string; items?: string[]; days?: number[] }[] } }
type Meta = { missing: string[]; targets: Targets | null; profile: { dietary_preference: string | null }; catalogue?: { dishes: Record<string, { ingredients: Record<string, number> }> } }
type Recipes = Record<string, Record<string, number>>
type Feedback = Record<string, { rating: number; favorite: boolean }>
type LogRow = { id: string; log_date: string; slot: string; dish_key: string; servings: number; nutrients: Nutrients }
type Summary = { days: Record<string, Nutrients & { meals: number }>; average_logged_day: Nutrients | null; targets: Targets | null; days_logged: number }

const today = () => new Date().toLocaleDateString('en-CA') // YYYY-MM-DD in local time
const weekStart = () => {
  const d = new Date()
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7)) // Monday
  return d.toLocaleDateString('en-CA')
}

function useFmt() {
  const { i18n } = useTranslation()
  return (n: number, d = 0) => new Intl.NumberFormat(intlLocale(i18n.language), { maximumFractionDigits: d }).format(n)
}

function TargetGrid({ targets }: { targets: Targets }) {
  const { t } = useTranslation()
  const f = useFmt()
  const items = [
    ['kcal', `${f(targets.kcal)} ${t('units.kcal')}`],
    ['protein', `${f(targets.protein_g)} ${t('units.g')}`],
    ['carbs', `${f(targets.carbs_g)} ${t('units.g')}`],
    ['fat', `${f(targets.fat_g)} ${t('units.g')}`],
    ['fiber', `${f(targets.fiber_g)} ${t('units.g')}`],
  ]
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {items.map(([k, v]) => (
        <div key={k} className={clsx('rounded-2xl p-3 ring-1', TARGET_TONE[k])}>
          <p className="text-xs font-medium opacity-80">{t(`diet.${k}`)}</p>
          <p className="text-lg font-semibold text-slate-900">{v}</p>
        </div>
      ))}
    </div>
  )
}

const TARGET_TONE: Record<string, string> = {
  kcal: 'bg-coral-50 text-coral-600 ring-coral-100',
  protein: 'bg-brand-50 text-brand-700 ring-brand-100',
  carbs: 'bg-amber-50 text-amber-700 ring-amber-100',
  fat: 'bg-violet-50 text-violet-700 ring-violet-100',
  fiber: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
}

const SLOT = {
  breakfast: { icon: Coffee, bar: 'from-amber-300 to-orange-400', tile: 'bg-amber-50 text-amber-600', text: 'text-amber-700' },
  lunch: { icon: Salad, bar: 'from-emerald-300 to-teal-500', tile: 'bg-emerald-50 text-emerald-600', text: 'text-emerald-700' },
  snack: { icon: Cookie, bar: 'from-pink-300 to-coral-500', tile: 'bg-coral-50 text-coral-600', text: 'text-coral-600' },
  dinner: { icon: Moon, bar: 'from-indigo-300 to-brand-500', tile: 'bg-indigo-50 text-indigo-600', text: 'text-indigo-700' },
} as const

function HowTo({ dish, servings, omit, ingredients }: { dish: string; servings: number; omit: string[]; ingredients?: Record<string, number> }) {
  const { t } = useTranslation()
  const steps = t(`recipes.${dish}`, { returnObjects: true, defaultValue: {} }) as Record<string, string> | string
  const list = typeof steps === 'object' ? Object.keys(steps).sort((a, b) => +a - +b).map((k) => steps[k]) : []
  if (!ingredients && !list.length) return null
  return (
    <details className="group mt-3 rounded-xl bg-slate-50 px-3 py-2 text-sm">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 font-medium text-brand-700">
        <ChefHat className="size-4" aria-hidden /> {t('diet.howTo')}
        <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      {ingredients && (
        <>
          <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('diet.ingredientsTitle', { n: servings })}</p>
          <ul className="mt-1 grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
            {Object.entries(ingredients).filter(([k]) => !omit.includes(k)).map(([k, g]) => (
              <li key={k} className="flex justify-between gap-2 border-b border-dashed border-slate-200 py-0.5">
                <span className="text-slate-700">{t(`ingredients.${k}`, { defaultValue: k.replace(/_/g, ' ') })}</span>
                <span className="tabular-nums text-slate-500">{Math.round(g * servings)} {t('units.g')}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {!!list.length && (
        <>
          <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('diet.stepsTitle')}</p>
          <ol className="mt-1 list-decimal space-y-1 ps-5 text-slate-700">{list.map((x, i) => <li key={i}>{x}</li>)}</ol>
        </>
      )}
      <p className="mt-2 text-xs text-slate-500">{t('diet.saltNote')}</p>
    </details>
  )
}

function PlanView({ plan, feedback, onFeedback, onLog, logged, recipes }: { recipes: Recipes; plan: Plan; feedback: Feedback; onFeedback: (dish: string, fb: { rating: number; favorite: boolean }) => void; onLog: (m: Meal) => void; logged: Set<string> }) {
  const { t } = useTranslation()
  const f = useFmt()
  const [day, setDay] = useState(0)
  const d = plan.plan.days[Math.min(day, plan.plan.days.length - 1)]
  const isToday = (m: Meal) => logged.has(`${m.slot}:${m.dish}`)
  return (
    <div className="space-y-4">
      {plan.plan.notes.map((n, i) => (
        <Alert key={i} kind={n.code === 'check_with_professional' ? 'warning' : 'info'}>
          {t(`diet.notes.${n.code}`, { items: n.items?.join(', '), days: n.days?.join(', ') })}
        </Alert>
      ))}
      <div className="flex gap-2 overflow-x-auto pb-1" role="tablist">
        {plan.plan.days.map((x, i) => (
          <button key={x.day} role="tab" aria-selected={i === day} onClick={() => setDay(i)} className={clsx('shrink-0 rounded-xl px-4 py-2 text-sm font-medium', i === day ? 'bg-brand-600 text-white' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-brand-300')}>
            {t('diet.day', { n: x.day })}
          </button>
        ))}
      </div>
      <div className="space-y-3" role="tabpanel">
        {d.meals.map((m, i) => {
          const fb = feedback[m.dish] ?? { rating: 0, favorite: false }
          return (
            <Card key={i} className="relative overflow-hidden p-4 ps-5 hover:shadow-lift">
              <span className={clsx('absolute inset-y-0 start-0 w-1.5 bg-gradient-to-b', SLOT[m.slot].bar)} aria-hidden />
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 gap-4">
                <span className={clsx('grid size-12 shrink-0 place-items-center rounded-2xl', SLOT[m.slot].tile)} aria-hidden>{(() => { const I = SLOT[m.slot].icon; return <I className="size-6" /> })()}</span>
                <div className="min-w-0">
                  <p className={clsx('text-xs font-semibold uppercase tracking-wide', SLOT[m.slot].text)}>{t(`diet.slots.${m.slot}`)}{m.extra && <span className="ms-2 rounded bg-teal-50 px-1.5 py-0.5 normal-case tracking-normal">{t('diet.extra')}</span>}</p>
                  <p className="mt-0.5 text-lg font-semibold text-slate-900">{t(`dishes.${m.dish}`)}</p>
                  <p className="text-sm text-slate-600">{t('diet.servings', { n: f(m.servings, 2) })} · {f(m.nutrients.kcal)} {t('units.kcal')} · {t('diet.protein')} {f(m.nutrients.protein_g)}{t('units.g')} · {t('diet.carbs')} {f(m.nutrients.carbs_g)}{t('units.g')} · {t('diet.fat')} {f(m.nutrients.fat_g)}{t('units.g')}</p>
                  {!!m.omit.length && <p className="mt-1 text-xs text-amber-700">{t('diet.omit', { items: m.omit.map((x) => t(`ingredients.${x}`)).join(', ') })}</p>}
                </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button type="button" aria-pressed={fb.rating === 1} aria-label={t('diet.like')} title={t('diet.like')} onClick={() => onFeedback(m.dish, { ...fb, rating: fb.rating === 1 ? 0 : 1 })} className={clsx('rounded-lg p-2 hover:bg-slate-100', fb.rating === 1 ? 'text-brand-600' : 'text-slate-400')}><ThumbsUp className="size-4" /></button>
                  <button type="button" aria-pressed={fb.rating === -1} aria-label={t('diet.dislike')} title={t('diet.dislike')} onClick={() => onFeedback(m.dish, { ...fb, rating: fb.rating === -1 ? 0 : -1 })} className={clsx('rounded-lg p-2 hover:bg-slate-100', fb.rating === -1 ? 'text-red-600' : 'text-slate-400')}><ThumbsDown className="size-4" /></button>
                  <button type="button" aria-pressed={fb.favorite} aria-label={t('diet.favorite')} title={t('diet.favorite')} onClick={() => onFeedback(m.dish, { ...fb, favorite: !fb.favorite })} className={clsx('rounded-lg p-2 hover:bg-slate-100', fb.favorite ? 'text-rose-500' : 'text-slate-400')}><Heart className={clsx('size-4', fb.favorite && 'fill-current')} /></button>
                  <Button size="sm" variant={isToday(m) ? 'secondary' : 'outline'} disabled={isToday(m)} onClick={() => onLog(m)} className="ms-1">
                    <Check className="size-4" aria-hidden /> {isToday(m) ? t('diet.logged') : t('diet.eaten')}
                  </Button>
                </div>
              </div>
              <HowTo dish={m.dish} servings={m.servings} omit={m.omit} ingredients={recipes[m.dish]} />
            </Card>
          )
        })}
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-slate-100 px-4 py-3 text-sm">
          <span className="font-semibold text-slate-800">{t('diet.dayTotal')}: {f(d.totals.kcal)} {t('units.kcal')} · {t('diet.protein')} {f(d.totals.protein_g)}{t('units.g')} · {t('diet.fiber')} {f(d.totals.fiber_g)}{t('units.g')}</span>
          <span className="text-slate-500">{t('diet.target', { kcal: f(plan.targets.kcal) })}</span>
        </div>
      </div>
    </div>
  )
}

function Tracker({ logs, summary, onRemove }: { logs: LogRow[]; summary?: Summary; onRemove: (id: string) => void }) {
  const { t, i18n } = useTranslation()
  const f = useFmt()
  const target = summary?.targets?.kcal
  const days = summary ? Object.entries(summary.days) : []
  const max = Math.max(target ?? 0, ...days.map(([, d]) => d.kcal), 1)
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <h3 className="font-semibold text-slate-900">{t('diet.tracker.today')}</h3>
        {!logs.length ? <p className="mt-3 text-sm text-slate-500">{t('diet.tracker.logEmpty')}</p> : (
          <ul className="mt-3 divide-y divide-slate-100">
            {logs.map((l) => (
              <li key={l.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span><span className="text-xs text-slate-500">{t(`diet.slots.${l.slot}`)} · </span>{t(`dishes.${l.dish_key}`)} <span className="text-slate-500">({f(l.nutrients.kcal)} {t('units.kcal')})</span></span>
                <button type="button" onClick={() => onRemove(l.id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label={t('diet.tracker.remove')}><Trash2 className="size-4" /></button>
              </li>
            ))}
          </ul>
        )}
        {!!logs.length && <p className="mt-3 text-sm font-semibold text-slate-800">{f(logs.reduce((s, l) => s + l.nutrients.kcal, 0))} {t('units.kcal')}{target ? ` / ${f(target)}` : ''}</p>}
      </Card>
      <Card>
        <h3 className="font-semibold text-slate-900">{t('diet.tracker.week')}</h3>
        {!target && <p className="mt-2 text-xs text-slate-500">{t('diet.tracker.noPlan')}</p>}
        <div className="mt-4 flex h-40 items-end gap-2" role="img" aria-label={t('diet.tracker.week')}>
          {days.map(([date, d]) => (
            <div key={date} className="flex flex-1 flex-col items-center gap-1">
              <div className="relative flex w-full flex-1 items-end">
                {target && <div className="absolute inset-x-0 border-t border-dashed border-teal-500" style={{ bottom: `${(target / max) * 100}%` }} />}
                <div className={clsx('w-full rounded-t-md', d.kcal ? 'bg-brand-500' : 'bg-slate-100')} style={{ height: `${Math.max(2, (d.kcal / max) * 100)}%` }} title={`${f(d.kcal)} ${t('units.kcal')}`} />
              </div>
              <span className="text-[10px] text-slate-500">{new Intl.DateTimeFormat(intlLocale(i18n.language), { weekday: 'short' }).format(new Date(date + 'T12:00'))}</span>
            </div>
          ))}
        </div>
        {summary?.average_logged_day && (
          <p className="mt-3 text-sm text-slate-700">{t('diet.tracker.avg')}: {f(summary.average_logged_day.kcal)} {t('units.kcal')} · {t('diet.tracker.daysLogged', { count: summary.days_logged })}</p>
        )}
      </Card>
    </div>
  )
}

export default function Diet() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const planId = params.get('plan')
  const [tab, setTab] = useState<'plan' | 'tracker'>('plan')
  const [goal, setGoal] = useState<'lose' | 'maintain' | 'gain'>('maintain')
  const [days, setDays] = useState(7)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [justSaved, setJustSaved] = useState(false)

  const meta = useQuery({ queryKey: ['diet-meta', goal], queryFn: () => api<Meta>(`/api/diet/meta?goal=${goal}`) })
  const existing = useQuery({ queryKey: ['diet-plan', planId], queryFn: () => api<Plan>(`/api/diet/plans/${planId}`), enabled: !!planId })
  const feedback = useQuery({ queryKey: ['diet-feedback'], queryFn: () => api<Feedback>('/api/diet/feedback') })
  const logs = useQuery({ queryKey: ['diet-logs', today()], queryFn: () => api<LogRow[]>(`/api/diet/logs?date_from=${today()}&date_to=${today()}`) })
  const summary = useQuery({ queryKey: ['diet-summary', weekStart()], queryFn: () => api<Summary>(`/api/diet/summary?week_start=${weekStart()}`) })

  useEffect(() => {
    if (existing.data) setPlan(existing.data)
  }, [existing.data])

  const create = useMutation({
    mutationFn: () => api<Plan>('/api/diet/plans', { method: 'POST', body: { goal, days } }),
    onSuccess: (p) => {
      setPlan(p)
      setJustSaved(true)
      setParams({ plan: p.id }, { replace: true })
      qc.invalidateQueries({ queryKey: ['diet-history'] })
      qc.invalidateQueries({ queryKey: ['diet-summary'] })
    },
  })
  const fb = useMutation({
    mutationFn: ({ dish, v }: { dish: string; v: { rating: number; favorite: boolean } }) => api(`/api/diet/feedback/${dish}`, { method: 'PUT', body: v }),
    onMutate: ({ dish, v }) => qc.setQueryData<Feedback>(['diet-feedback'], (old) => ({ ...(old ?? {}), [dish]: v })),
  })
  const log = useMutation({
    mutationFn: (m: Meal) => api('/api/diet/logs', { method: 'POST', body: { log_date: today(), slot: m.slot, dish_key: m.dish, servings: m.servings, plan_id: plan?.id } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['diet-logs'] }); qc.invalidateQueries({ queryKey: ['diet-summary'] }) },
  })
  const removeLog = useMutation({
    mutationFn: (id: string) => api(`/api/history/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['diet-logs'] }); qc.invalidateQueries({ queryKey: ['diet-summary'] }) },
  })
  const fav = useMutation({
    mutationFn: () => api<Plan>(`/api/diet/plans/${plan!.id}`, { method: 'PATCH', body: { is_favorite: !plan!.is_favorite } }),
    onSuccess: (p) => { setPlan(p); qc.invalidateQueries({ queryKey: ['diet-history'] }) },
  })

  if (meta.isLoading) return <FullPageSpinner />
  const m = meta.data
  const loggedToday = new Set((logs.data ?? []).map((l) => `${l.slot}:${l.dish_key}`))
  const createErr = create.error instanceof ApiError ? t(`diet.errors.${create.error.code}`, { defaultValue: errorMessage(t, create.error) }) : create.error ? errorMessage(t, create.error) : null

  return (
    <div className="mx-auto max-w-5xl animate-fade-up">
      <PageHeader title={t('diet.title')} desc={t('diet.subtitle')} />
      <div className="mb-5 flex gap-2" role="tablist">
        {(['plan', 'tracker'] as const).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={clsx('rounded-xl px-4 py-2 text-sm font-semibold', tab === k ? 'bg-gradient-to-r from-brand-600 to-teal-600 text-white shadow-md' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-brand-300')}>{t(`diet.tabs.${k}`)}</button>
        ))}
      </div>

      {tab === 'tracker' ? (
        <Tracker logs={logs.data ?? []} summary={summary.data} onRemove={(id) => removeLog.mutate(id)} />
      ) : (
        <div className="space-y-6">
          <Card className="space-y-5">
            <h2 className="font-semibold text-slate-900">{t('diet.profileTitle')}</h2>
            {m && m.missing.length ? (
              <Alert kind="warning">
                {t('diet.missing', { fields: m.missing.map((x) => t(`diet.missingFields.${x}`)).join(', ') })}
                <Link to="/profile/health" className={clsx(buttonClasses('outline', 'sm'), 'mt-3')}><UserCog className="size-4" aria-hidden /> {t('diet.editProfile')}</Link>
              </Alert>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t('diet.goal')}>
                    {(id) => (
                      <Select id={id} value={goal} onChange={(e) => setGoal(e.target.value as typeof goal)}>
                        {(['lose', 'maintain', 'gain'] as const).map((g) => <option key={g} value={g}>{t(`diet.goals.${g}`)}</option>)}
                      </Select>
                    )}
                  </Field>
                  <Field label={t('diet.days')}>
                    {(id) => (
                      <Select id={id} value={days} onChange={(e) => setDays(Number(e.target.value))}>
                        {[1, 3, 5, 7].map((n) => <option key={n} value={n}>{t('diet.daysN', { count: n })}</option>)}
                      </Select>
                    )}
                  </Field>
                </div>
                {m?.targets && (
                  <div>
                    <p className="mb-2 text-sm font-medium text-slate-700">{t('diet.targets')}</p>
                    <TargetGrid targets={m.targets} />
                  </div>
                )}
                <details className="text-sm text-slate-600">
                  <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-brand-700"><Info className="size-4" aria-hidden />{t('diet.method')}</summary>
                  <p className="mt-2">{t('diet.methodBody')}</p>
                  {m?.targets && <p className="mt-1 text-xs text-slate-500">{t('diet.bmr')}: {m.targets.bmr} {t('units.kcal')} · {t('diet.tdee')}: {m.targets.tdee} {t('units.kcal')}</p>}
                </details>
                {createErr && <Alert kind="error">{createErr}</Alert>}
                <div className="flex flex-wrap items-center gap-3">
                  <Button size="lg" loading={create.isPending} onClick={() => create.mutate()}>
                    <Sparkles className="size-4" aria-hidden /> {create.isPending ? t('diet.generating') : t('diet.generate')}
                  </Button>
                  <Link to="/history/diets" className="text-sm font-medium text-brand-600">{t('dietHistory.title')}</Link>
                </div>
              </>
            )}
          </Card>

          {plan && (
            <section aria-label={t('diet.tabs.plan')}>
              <div className="mb-3 flex items-center justify-between gap-3">
                {justSaved ? <Alert kind="success" className="flex-1">{t('diet.saved')}</Alert> : <span />}
                <button type="button" onClick={() => fav.mutate()} aria-pressed={plan.is_favorite} className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-slate-700 hover:bg-amber-50">
                  <Star className={clsx('size-4', plan.is_favorite ? 'fill-amber-400 text-amber-400' : 'text-slate-400')} aria-hidden />
                  {plan.is_favorite ? t('dietHistory.unfavorite') : t('dietHistory.favorite')}
                </button>
              </div>
              <PlanView plan={plan} feedback={feedback.data ?? {}} onFeedback={(dish, v) => fb.mutate({ dish, v })} onLog={(meal) => log.mutate(meal)} logged={loggedToday} recipes={Object.fromEntries(Object.entries(meta.data?.catalogue?.dishes ?? {}).map(([k, v]) => [k, v.ingredients]))} />
            </section>
          )}
          <p className="text-xs text-slate-500">{t('diet.source')}</p>
          <p className="text-xs text-slate-500">{t('diet.disclaimer')}</p>
        </div>
      )}
    </div>
  )
}
