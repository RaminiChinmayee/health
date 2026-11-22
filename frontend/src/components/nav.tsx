import clsx from 'clsx'
import {
  Activity,
  Apple,
  Check,
  ChevronDown,
  ClipboardList,
  FileHeart,
  Globe,
  HeartPulse,
  HelpCircle,
  History,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Settings,
  Shield,
  User as UserIcon,
  UserCircle,
  Utensils,
} from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { LANGUAGES, type LanguageCode } from '../i18n/languages'
import { fetchObjectUrl } from '../lib/api'

export function Logo({ className, light }: { className?: string; light?: boolean }) {
  const { t } = useTranslation()
  return (
    <span className={clsx('inline-flex items-center gap-2.5', className)}>
      <span className={clsx('grid size-9 place-items-center rounded-xl text-white shadow-sm', light ? 'bg-white/15 ring-1 ring-white/25' : 'bg-gradient-to-br from-brand-600 to-teal-600')} aria-hidden>
        <HeartPulse className="size-5" strokeWidth={2.25} />
      </span>
      <span className={clsx('whitespace-nowrap text-base font-bold tracking-tight sm:text-lg', light ? 'text-white' : 'text-slate-900')} dir="ltr">
        Health<span className={light ? 'text-brand-200' : 'text-brand-600'}>Assist</span> <span className={light ? 'text-teal-200' : 'text-teal-600'}>AI</span>
      </span>
      <span className="sr-only">{t('common.appName')}</span>
    </span>
  )
}

/** Generic accessible dropdown: Escape/outside click closes, arrow keys move focus. */
function useDropdown() {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    // Move focus into the menu when it opens.
    requestAnimationFrame(() => root.current?.querySelector<HTMLElement>('[role="menuitem"],[role="menuitemradio"]')?.focus())
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  const onMenuKey = (e: KeyboardEvent) => {
    const items = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"],[role="menuitemradio"]') ?? [])
    const i = items.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'Escape') {
      setOpen(false)
      button.current?.focus()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      items[(i + 1) % items.length]?.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      items[(i - 1 + items.length) % items.length]?.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      items[0]?.focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      items[items.length - 1]?.focus()
    } else if (e.key === 'Tab') setOpen(false)
  }
  return { open, setOpen, root, button, onMenuKey }
}

export function LanguageSelector({ compact = false }: { compact?: boolean }) {
  const { t, i18n } = useTranslation()
  const { setLanguage } = useAuth()
  const { open, setOpen, root, button, onMenuKey } = useDropdown()
  const current = LANGUAGES.find((l) => l.code === i18n.language) ?? LANGUAGES[0]
  const choose = async (code: LanguageCode) => {
    setOpen(false)
    await setLanguage(code)
    button.current?.focus()
  }
  return (
    <div className="relative" ref={root}>
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={i18n.language === 'en' ? `Language: ${current.english}` : `${t('nav.language')} (Language): ${current.english}`}
        className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
      >
        <Globe className="size-4" aria-hidden />
        {!compact && <span className="max-sm:hidden">{current.native}</span>}
        <ChevronDown className="size-3.5" aria-hidden />
      </button>
      {open && (
        <div role="menu" aria-label={t('nav.language')} onKeyDown={onMenuKey} className="absolute end-0 z-50 mt-2 max-h-[70vh] w-56 overflow-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-lift animate-pop">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              role="menuitemradio"
              aria-checked={l.code === current.code}
              lang={l.code}
              dir={l.dir}
              onClick={() => choose(l.code)}
              className={clsx(
                'flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-start text-sm hover:bg-brand-50 focus:bg-brand-50 focus:outline-none',
                l.code === current.code ? 'font-semibold text-brand-700' : 'text-slate-700',
              )}
            >
              <span>{l.native}</span>
              <span className="flex items-center gap-2 text-xs text-slate-400" dir="ltr">
                {l.english}
                {l.code === current.code && <Check className="size-4 text-brand-600" aria-hidden />}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function Avatar({ size = 'md' }: { size?: 'md' | 'lg' }) {
  const { user } = useAuth()
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let revoked: string | null = null
    setUrl(null)
    if (user?.has_avatar) {
      fetchObjectUrl('/api/profile/avatar')
        .then((u) => {
          revoked = u
          setUrl(u)
        })
        .catch(() => setUrl(null))
    }
    return () => {
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [user?.has_avatar, user?.id])
  const initials = (user?.full_name ?? '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
  const dim = size === 'lg' ? 'size-24 text-2xl' : 'size-9 text-sm'
  return url ? (
    <img src={url} alt="" className={clsx(dim, 'rounded-full object-cover ring-2 ring-white')} />
  ) : (
    <span className={clsx(dim, 'grid place-items-center rounded-full bg-gradient-to-br from-brand-500 to-teal-500 font-semibold text-white ring-2 ring-white')} aria-hidden>
      {initials}
    </span>
  )
}

type MenuItem = { to: string; icon: ReactNode; label: string } | 'divider'

export function ProfileMenu() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { open, setOpen, root, button, onMenuKey } = useDropdown()
  const ic = 'size-4 text-slate-400'
  const items: MenuItem[] = [
    { to: '/profile', icon: <UserCircle className={ic} />, label: t('profileMenu.myProfile') },
    { to: '/profile/personal', icon: <UserIcon className={ic} />, label: t('profileMenu.personalInfo') },
    { to: '/profile/health', icon: <Activity className={ic} />, label: t('profileMenu.healthProfile') },
    'divider',
    { to: '/records', icon: <FileHeart className={ic} />, label: t('profileMenu.healthRecords') },
    { to: '/history/predictions', icon: <History className={ic} />, label: t('profileMenu.predictionHistory') },
    { to: '/history/chats', icon: <MessageSquare className={ic} />, label: t('profileMenu.chatHistory') },
    { to: '/history/diets', icon: <Utensils className={ic} />, label: t('profileMenu.dietPlans') },
    'divider',
    { to: '/profile/language', icon: <Globe className={ic} />, label: t('profileMenu.language') },
    { to: '/profile/security', icon: <Shield className={ic} />, label: t('profileMenu.privacy') },
    { to: '/profile/settings', icon: <Settings className={ic} />, label: t('profileMenu.settings') },
    { to: '/help', icon: <HelpCircle className={ic} />, label: t('profileMenu.help') },
  ]
  if (!user) return null
  return (
    <div className="relative" ref={root}>
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('profileMenu.label')}
        className="flex items-center gap-1.5 rounded-full p-0.5 pe-1.5 hover:bg-slate-100"
      >
        <Avatar />
        <ChevronDown className="size-4 text-slate-500" aria-hidden />
      </button>
      {open && (
        <div role="menu" aria-label={t('profileMenu.label')} onKeyDown={onMenuKey} className="absolute end-0 z-50 mt-2 w-72 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-lift animate-pop">
          <div className="flex items-center gap-3 px-3 py-3">
            <Avatar />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">{user.full_name}</p>
              <p className="truncate text-xs text-slate-500" dir="ltr">{user.email}</p>
            </div>
          </div>
          <div className="my-1 h-px bg-slate-100" />
          {items.map((it, i) =>
            it === 'divider' ? (
              <div key={i} className="my-1 h-px bg-slate-100" role="separator" />
            ) : (
              <Link
                key={it.to}
                to={it.to}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-brand-50 hover:text-brand-700 focus:bg-brand-50 focus:outline-none"
              >
                {it.icon}
                {it.label}
              </Link>
            ),
          )}
          <div className="my-1 h-px bg-slate-100" role="separator" />
          <button
            role="menuitem"
            onClick={async () => {
              setOpen(false)
              navigate('/', { replace: true })
              await logout()
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-start text-sm font-medium text-red-600 hover:bg-red-50 focus:bg-red-50 focus:outline-none"
          >
            <LogOut className="size-4" />
            {t('profileMenu.logout')}
          </button>
        </div>
      )}
    </div>
  )
}

export const APP_LINKS = [
  { to: '/dashboard', key: 'nav.dashboard', icon: LayoutDashboard },
  { to: '/symptoms', key: 'nav.symptomChecker', icon: Activity },
  { to: '/assessments', key: 'nav2.assessments', icon: ClipboardList },
  { to: '/chat', key: 'nav.chatbot', icon: MessageSquare },
  { to: '/hospitals', key: 'nav.hospitals', icon: HeartPulse },
  { to: '/diet', key: 'nav.diet', icon: Apple },
] as const
