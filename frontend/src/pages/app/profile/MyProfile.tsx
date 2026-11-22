import { useMutation } from '@tanstack/react-query'
import { Activity, Apple, BadgeCheck, Brain, Camera, ClipboardList, FileHeart, HeartPulse, HelpCircle, History, Image as ImageIcon, Pencil, Settings, Shield, Sparkles, Trash2, UserCircle } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../../auth/AuthProvider'
import { Avatar } from '../../../components/nav'
import { Alert, Button, buttonClasses, Card } from '../../../components/ui'
import { intlLocale, LANGUAGES } from '../../../i18n/languages'
import { api, type User } from '../../../lib/api'
import { errorMessage } from '../../../lib/errors'

const HEADER_ICONS: [string, typeof Activity][] = [
  ['/symptoms', Activity], ['/assessments', ClipboardList], ['/hospitals', HeartPulse], ['/diet', Apple],
  ['/history/images', ImageIcon], ['/history', History], ['/chat/memory', Brain], ['/records', FileHeart],
  ['/profile/health', Activity], ['/profile/settings', Settings], ['/profile/security', Shield], ['/profile', UserCircle], ['/help', HelpCircle],
]

/** Page title banner used across the app; the icon follows the current section. */
export function PageHeader({ title, desc, action }: { title: string; desc?: string; action?: ReactNode }) {
  const { pathname } = useLocation()
  const Icon = HEADER_ICONS.find(([p]) => pathname.startsWith(p))?.[1] ?? Sparkles
  return (
    <div className="relative mb-6 overflow-hidden rounded-3xl bg-gradient-to-r from-brand-700 via-brand-600 to-teal-600 p-6 text-white shadow-lift sm:p-8">
      <div className="pointer-events-none absolute -end-10 -top-16 size-56 rounded-full bg-white/10 blur-2xl" aria-hidden />
      <div className="pointer-events-none absolute -bottom-20 end-32 size-48 rounded-full bg-teal-300/20 blur-2xl" aria-hidden />
      <Icon className="pointer-events-none absolute -bottom-6 end-6 size-36 text-white/10" strokeWidth={1.25} aria-hidden />
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25 backdrop-blur"><Icon className="size-6" aria-hidden /></span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
            {desc && <p className="mt-1 max-w-2xl text-brand-50/90">{desc}</p>}
          </div>
        </div>
        {action && <div className="relative shrink-0 [&_a]:shadow-sm [&_button]:shadow-sm">{action}</div>}
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3.5 sm:grid-cols-3 sm:gap-4">
      <dt className="text-sm font-medium text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-900 sm:col-span-2">{children}</dd>
    </div>
  )
}

export default function MyProfile() {
  const { t, i18n } = useTranslation()
  const { user, setUser } = useAuth()
  const fileRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<unknown>(null)

  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return api<User>('/api/profile/avatar', { method: 'PUT', body: fd })
    },
    onSuccess: (u) => {
      setUser(u)
      setError(null)
    },
    onError: setError,
  })
  const remove = useMutation({
    mutationFn: () => api<User>('/api/profile/avatar', { method: 'DELETE' }),
    onSuccess: setUser,
  })

  if (!user) return null
  const fmt = (d: string) => new Intl.DateTimeFormat(intlLocale(i18n.language), { dateStyle: 'long' }).format(new Date(d))
  const np = <span className="text-slate-400">{t('common.notProvided')}</span>

  return (
    <div className="mx-auto max-w-3xl animate-fade-up">
      <PageHeader
        title={t('profile.myProfile')}
        action={
          <Link to="/profile/personal" className={buttonClasses('outline', 'sm')}>
            <Pencil className="size-4" aria-hidden /> {t('profile.editDetails')}
          </Link>
        }
      />
      <Card>
        <div className="flex flex-col items-center gap-5 sm:flex-row">
          <Avatar size="lg" />
          <div className="text-center sm:text-start">
            <p className="text-xl font-semibold text-slate-900">{user.full_name}</p>
            <p className="text-sm text-slate-500" dir="ltr">{user.email}</p>
            <div className="mt-3 flex flex-wrap justify-center gap-2 sm:justify-start">
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) upload.mutate(f)
                  e.target.value = ''
                }}
              />
              <Button size="sm" variant="secondary" loading={upload.isPending} onClick={() => fileRef.current?.click()}>
                <Camera className="size-4" aria-hidden /> {t('profile.changePhoto')}
              </Button>
              {user.has_avatar && (
                <Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => remove.mutate()}>
                  <Trash2 className="size-4" aria-hidden /> {t('profile.removePhoto')}
                </Button>
              )}
            </div>
            <p className="mt-2 text-xs text-slate-500">{t('profile.photoHint')}</p>
          </div>
        </div>
        {error != null && <Alert kind="error" className="mt-4">{errorMessage(t, error)}</Alert>}

        <dl className="mt-6 divide-y divide-slate-100 border-t border-slate-100">
          <Row label={t('profile.fullName')}>{user.full_name}</Row>
          <Row label={t('profile.email')}>
            <span className="inline-flex flex-wrap items-center gap-2">
              <span dir="ltr">{user.email}</span>
              {user.email_verified ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-mint-50 px-2 py-0.5 text-xs font-medium text-green-700">
                  <BadgeCheck className="size-3.5" aria-hidden /> {t('profile.verified')}
                </span>
              ) : (
                <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">{t('profile.unverified')}</span>
              )}
            </span>
          </Row>
          <Row label={t('profile.phone')}>{user.phone ? <span dir="ltr">{user.phone}</span> : np}</Row>
          <Row label={t('profile.dob')}>{user.date_of_birth ? `${fmt(user.date_of_birth)} · ${t('profile.age')} ${user.age}` : np}</Row>
          <Row label={t('profile.gender')}>{user.gender ? t(`auth.gender.${user.gender}`) : np}</Row>
          <Row label={t('profile.preferredLanguage')}>{LANGUAGES.find((l) => l.code === user.ui_language)?.native}</Row>
          <Row label={t('profile.createdAt')}>{fmt(user.created_at)}</Row>
          <Row label={t('profile.authMethod')}>{user.auth_methods.map((m) => t(`profile.auth_${m}`)).join(', ')}</Row>
        </dl>
      </Card>
    </div>
  )
}
