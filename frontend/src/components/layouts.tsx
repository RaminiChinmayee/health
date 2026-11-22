import clsx from 'clsx'
import { Activity, FileHeart, HelpCircle, History, Image as ImageIcon, MapPin, Menu, MessagesSquare, Phone, Settings, ShieldCheck, Sparkles, Utensils, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { APP_LINKS, LanguageSelector, Logo, ProfileMenu } from './nav'
import { buttonClasses } from './ui'

function SkipLink() {
  const { t } = useTranslation()
  return (
    <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:shadow-lift">
      {t('common.skipToContent')}
    </a>
  )
}

/** Scroll to top on route change, or to the #hash target if present. */
function ScrollManager() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [pathname, hash])
  return null
}

// ------------------------------------------------------------------ Public site
export function PublicLayout() {
  const { t } = useTranslation()
  const { status } = useAuth()
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const loc = useLocation()
  useEffect(() => setOpen(false), [loc])
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8)
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])

  const links = [
    { to: '/', label: t('nav.home') },
    { to: '/#features', label: t('nav.features') },
    { to: '/#how-it-works', label: t('nav.howItWorks') },
    { to: '/#about', label: t('nav.about') },
    { to: '/#contact', label: t('nav.contact') },
  ]
  const authed = status === 'authenticated'

  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <ScrollManager />
      <header className={clsx('sticky top-0 z-40 transition-all', scrolled ? 'border-b border-slate-200/70 bg-white/90 backdrop-blur-md' : 'bg-white/60 backdrop-blur-sm')}>
        <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8" aria-label="Main">
          <Link to="/" aria-label={t('common.appName')}>
            <Logo />
          </Link>
          <div className="hidden items-center gap-1 lg:flex">
            {links.map((l) => (
              <Link key={l.to} to={l.to} className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900">
                {l.label}
              </Link>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <LanguageSelector compact={false} />
            {authed ? (
              <>
                <Link to="/dashboard" className={clsx(buttonClasses('secondary', 'sm'), 'max-sm:hidden')}>
                  {t('nav.dashboard')}
                </Link>
                <ProfileMenu />
              </>
            ) : (
              <>
                <Link to="/login" className={clsx(buttonClasses('ghost', 'sm'), 'max-sm:hidden')}>
                  {t('nav.login')}
                </Link>
                <Link to="/register" className={clsx(buttonClasses('primary', 'sm'), 'max-sm:hidden')}>
                  {t('nav.getStarted')}
                </Link>
              </>
            )}
            <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? t('nav.closeMenu') : t('nav.openMenu')}>
              {open ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </nav>
        {open && (
          <div className="border-t border-slate-200 bg-white px-4 pb-4 lg:hidden">
            {links.map((l) => (
              <Link key={l.to} to={l.to} className="block rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
                {l.label}
              </Link>
            ))}
            {!authed && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Link to="/login" className={buttonClasses('outline')}>{t('nav.login')}</Link>
                <Link to="/register" className={buttonClasses('primary')}>{t('nav.getStarted')}</Link>
              </div>
            )}
          </div>
        )}
      </header>
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

// ------------------------------------------------------------------ Authenticated app
const RECORD_LINKS = [
  { to: '/history/predictions', key: 'profileMenu.predictionHistory', icon: History },
  { to: '/history/chats', key: 'profileMenu.chatHistory', icon: MessagesSquare },
  { to: '/history/diets', key: 'profileMenu.dietPlans', icon: Utensils },
  { to: '/history/images', key: 'skin.historyTitle', icon: ImageIcon },
  { to: '/records', key: 'profileMenu.healthRecords', icon: FileHeart },
] as const

function SideLink({ to, icon: Icon, label }: { to: string; icon: typeof History; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          'group relative flex items-center gap-3 rounded-xl px-3 py-1.5 text-sm font-medium transition',
          isActive ? 'bg-white/15 text-white shadow-inner' : 'text-brand-100/80 hover:bg-white/10 hover:text-white',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute inset-y-2 start-0 w-1 rounded-full bg-teal-300" aria-hidden />}
          <span className={clsx('grid size-7 shrink-0 place-items-center rounded-lg transition', isActive ? 'bg-gradient-to-br from-teal-400 to-brand-400 text-white shadow' : 'bg-white/5 text-brand-100 group-hover:bg-white/10')}>
            <Icon className="size-4" aria-hidden />
          </span>
          <span className="truncate">{label}</span>
        </>
      )}
    </NavLink>
  )
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-gradient-to-b from-brand-900 via-brand-800 to-teal-700 text-white" onClick={(e) => (e.target as HTMLElement).closest('a') && onNavigate?.()}>
      <div className="pointer-events-none absolute -end-24 -top-24 size-64 rounded-full bg-teal-400/20 blur-3xl" aria-hidden />
      <div className="pointer-events-none absolute -bottom-20 -start-16 size-56 rounded-full bg-brand-400/20 blur-3xl" aria-hidden />
      <Link to="/dashboard" aria-label={t('nav.dashboard')} className="relative flex h-16 shrink-0 items-center px-5">
        <Logo light />
      </Link>
      <nav className="relative flex-1 space-y-5 overflow-y-auto px-3 py-3" aria-label="Main">
        <div>
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-brand-200/70">{t('shell.tools')}</p>
          <div className="space-y-1">
            {APP_LINKS.map((l) => <SideLink key={l.to} to={l.to} icon={l.icon} label={t(l.key)} />)}
          </div>
        </div>
        <div>
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-brand-200/70">{t('shell.records')}</p>
          <div className="space-y-1">
            {RECORD_LINKS.map((l) => <SideLink key={l.to} to={l.to} icon={l.icon} label={t(l.key)} />)}
          </div>
        </div>
        <div className="space-y-1">
          <SideLink to="/profile/settings" icon={Settings} label={t('profileMenu.settings')} />
          <SideLink to="/help" icon={HelpCircle} label={t('profileMenu.help')} />
        </div>
      </nav>
      <div className="relative m-3 rounded-2xl bg-white/10 p-3 ring-1 ring-white/15 backdrop-blur">
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-red-500 text-white shadow-lg shadow-red-900/30"><Phone className="size-5" aria-hidden /></span>
          <div className="min-w-0">
            <p className="text-xs text-brand-100/80">{t('shell.emergency')}</p>
            <a href="tel:112" className="text-xl font-bold tracking-wide text-white hover:underline" dir="ltr">112</a>
          </div>
        </div>
      </div>
    </div>
  )
}

export function AppLayout() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => setOpen(false), [loc])
  useEffect(() => {
    if (!open) return
    const onKey = (e: globalThis.KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])
  const isChat = loc.pathname.startsWith('/chat') && loc.pathname !== '/chat/memory'
  return (
    <div className="min-h-screen bg-[#f4f7fb]">
      <SkipLink />
      <ScrollManager />
      {/* Left sidebar (desktop) */}
      <aside className="fixed inset-y-0 start-0 z-40 hidden w-64 lg:block">
        <Sidebar />
      </aside>
      {/* Off-canvas sidebar (mobile) */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <button className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" aria-label={t('nav.closeMenu')} onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 start-0 w-72 max-w-[85vw] animate-pop shadow-2xl">
            <Sidebar onNavigate={() => setOpen(false)} />
            <button className="absolute end-3 top-4 rounded-lg p-1.5 text-white/80 hover:bg-white/10" onClick={() => setOpen(false)} aria-label={t('nav.closeMenu')}>
              <X className="size-5" />
            </button>
          </aside>
        </div>
      )}
      <div className="flex min-h-screen flex-col lg:ps-64">
        {/* Slim top bar: language selector + profile/avatar menu stay top-right on every page. */}
        <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/80 backdrop-blur-md">
          <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-2">
              <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-expanded={open} aria-label={t('nav.openMenu')}>
                <Menu className="size-5" />
              </button>
              <Link to="/dashboard" className="lg:hidden" aria-label={t('nav.dashboard')}>
                <Logo />
              </Link>
              <p className="hidden text-sm text-slate-500 lg:block">{new Intl.DateTimeFormat(document.documentElement.lang || 'en', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())}</p>
            </div>
            <div className="flex items-center gap-1.5">
              <LanguageSelector compact />
              <ProfileMenu />
            </div>
          </div>
        </header>
        <main id="main" className="relative w-full flex-1 px-4 py-8 sm:px-6 lg:px-8">
          {!isChat && (
            <>
              <div className="bg-dots pointer-events-none absolute inset-x-0 top-0 h-96 [mask-image:linear-gradient(to_bottom,black,transparent)]" aria-hidden />
              <div className="pointer-events-none absolute inset-x-0 top-0 h-96 bg-[radial-gradient(60%_100%_at_15%_0%,rgb(31_116_211/0.10),transparent),radial-gradient(50%_80%_at_90%_0%,rgb(20_184_166/0.10),transparent),radial-gradient(40%_60%_at_60%_10%,rgb(249_115_98/0.06),transparent)]" aria-hidden />
            </>
          )}
          <div className="relative mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
        {!isChat && (
          <footer className="border-t border-slate-200 bg-white py-5 text-center text-xs text-slate-500">
            <p className="mx-auto max-w-3xl px-4">{t('footer.medicalNote')}</p>
          </footer>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ Auth pages (split screen)
const AUTH_FEATURES = [
  { key: 'prediction', icon: Activity },
  { key: 'chatbot', icon: MessagesSquare },
  { key: 'diet', icon: Utensils },
  { key: 'hospitals', icon: MapPin },
] as const

export function AuthLayout() {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-screen bg-white">
      <SkipLink />
      <ScrollManager />
      {/* Brand panel */}
      <aside className="relative hidden w-[46%] max-w-2xl overflow-hidden bg-gradient-to-br from-brand-900 via-brand-700 to-teal-600 p-10 text-white lg:flex lg:flex-col xl:p-14">
        <div className="pointer-events-none absolute -end-32 -top-32 size-96 rounded-full bg-teal-300/25 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -bottom-40 -start-24 size-[28rem] rounded-full bg-brand-400/30 blur-3xl" aria-hidden />
        <svg className="pointer-events-none absolute inset-x-0 bottom-28 w-full text-white/15" viewBox="0 0 600 80" fill="none" aria-hidden>
          <path d="M0 40h170l18-30 22 60 20-45 14 15h356" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <Link to="/" className="relative"><Logo light /></Link>
        <div className="relative my-auto max-w-md py-10">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium ring-1 ring-white/20">
            <Sparkles className="size-3.5 text-teal-200" aria-hidden /> {t('home.hero.badge')}
          </span>
          <h2 className="mt-5 text-3xl font-bold leading-tight tracking-tight xl:text-4xl">{t('home.hero.title')}</h2>
          <ul className="mt-8 space-y-3">
            {AUTH_FEATURES.map((f) => (
              <li key={f.key} className="flex items-center gap-3 rounded-xl bg-white/10 p-3 ring-1 ring-white/10 backdrop-blur-sm">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/15"><f.icon className="size-4.5" aria-hidden /></span>
                <span className="text-sm font-medium">{t(`home.features.${f.key}.title`)}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative flex items-center gap-2 text-xs text-brand-100/80"><ShieldCheck className="size-4" aria-hidden /> {t('home.hero.note')}</p>
      </aside>
      {/* Form side */}
      <div className="relative flex flex-1 flex-col bg-gradient-to-br from-slate-50 via-white to-brand-50/60">
        <div className="pointer-events-none absolute end-0 top-0 size-72 rounded-full bg-teal-100/50 blur-3xl" aria-hidden />
        <header className="relative flex h-16 w-full items-center justify-between px-4 sm:px-8">
          <Link to="/" className="lg:invisible"><Logo /></Link>
          <LanguageSelector />
        </header>
        <main id="main" className="relative flex flex-1 items-start justify-center px-4 py-8 sm:items-center">
          <div className="w-full max-w-md animate-fade-up">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ Footer
export function Footer() {
  const { t } = useTranslation()
  const year = new Date().getFullYear()
  return (
    <footer className="border-t border-slate-200 bg-slate-950 text-slate-300">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-4 lg:px-8">
        <div className="md:col-span-2">
          <div className="inline-flex items-center gap-2 text-lg font-bold text-white" dir="ltr">
            Health<span className="text-brand-300">Assist</span> <span className="text-teal-500">AI</span>
          </div>
          <p className="mt-3 max-w-sm text-sm text-slate-400">{t('footer.tagline')}</p>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">{t('footer.product')}</h3>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link to="/#features" className="hover:text-white">{t('nav.features')}</Link></li>
            <li><Link to="/#how-it-works" className="hover:text-white">{t('nav.howItWorks')}</Link></li>
            <li><Link to="/#faq" className="hover:text-white">{t('home.faq.eyebrow')}</Link></li>
            <li><Link to="/#contact" className="hover:text-white">{t('nav.contact')}</Link></li>
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">{t('footer.legal')}</h3>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link to="/privacy" className="hover:text-white">{t('footer.privacy')}</Link></li>
            <li><Link to="/terms" className="hover:text-white">{t('footer.terms')}</Link></li>
            <li><Link to="/disclaimer" className="hover:text-white">{t('footer.disclaimer')}</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-slate-800">
        <div className="mx-auto max-w-7xl space-y-2 px-4 py-6 text-xs text-slate-500 sm:px-6 lg:px-8">
          <p>{t('footer.medicalNote')}</p>
          <p>{t('footer.rights', { year })}</p>
        </div>
      </div>
    </footer>
  )
}
