import clsx from 'clsx'
import { AlertCircle, CheckCircle2, Eye, EyeOff, Info, Loader2, X } from 'lucide-react'
import {
  forwardRef,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react'
import { useTranslation } from 'react-i18next'

// ------------------------------------------------------------------ Button
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export function buttonClasses(variant: ButtonProps['variant'] = 'primary', size: ButtonProps['size'] = 'md') {
  return clsx(
    'inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none whitespace-nowrap active:scale-[0.98] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-200',
    {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2.5 text-sm',
      lg: 'px-6 py-3.5 text-base',
    }[size],
    {
      primary: 'bg-gradient-to-r from-brand-600 to-teal-600 text-white shadow-md shadow-brand-600/25 hover:shadow-lg hover:shadow-brand-600/30 hover:brightness-110',
      secondary: 'bg-brand-50 text-brand-700 ring-1 ring-brand-100 hover:bg-brand-100',
      outline: 'border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-700',
      ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
      danger: 'bg-gradient-to-r from-red-600 to-rose-600 text-white shadow-md shadow-red-600/25 hover:brightness-110',
    }[variant],
  )
}

export function Button({ variant, size, loading, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button className={clsx(buttonClasses(variant, size), className)} disabled={disabled || loading} {...rest}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

// ------------------------------------------------------------------ Field wrapper
type FieldProps = { label: ReactNode; error?: string; hint?: ReactNode; optional?: boolean; children: (id: string, describedBy?: string) => ReactNode }

export function Field({ label, error, hint, optional, children }: FieldProps) {
  const id = useId()
  const { t } = useTranslation()
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
        {optional && <span className="ms-1 font-normal text-slate-400">({t('common.optional')})</span>}
      </label>
      {children(id, describedBy)}
      {error ? (
        <p id={`${id}-err`} className="flex items-start gap-1 text-sm text-red-600" role="alert">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  )
}

const inputBase =
  'block w-full rounded-xl border bg-slate-50/80 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 transition hover:bg-white focus:bg-white focus:outline-none focus:ring-4'

function inputState(invalid?: boolean) {
  return invalid
    ? 'border-red-400 focus:border-red-500 focus:ring-red-100'
    : 'border-slate-200 hover:border-slate-300 focus:border-brand-400 focus:ring-brand-100/80'
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  function Input({ invalid, className, ...rest }, ref) {
    return <input ref={ref} aria-invalid={invalid || undefined} className={clsx(inputBase, inputState(invalid), className)} {...rest} />
  },
)

export function Select({ invalid, className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select aria-invalid={invalid || undefined} className={clsx(inputBase, inputState(invalid), 'pe-9', className)} {...rest}>
      {children}
    </select>
  )
}

export function PasswordInput(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const [show, setShow] = useState(false)
  const { t } = useTranslation()
  return (
    <div className="relative">
      <Input {...props} type={show ? 'text' : 'password'} className="pe-11" />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute inset-y-0 end-0 flex items-center px-3 text-slate-500 hover:text-slate-800"
        aria-label={show ? t('auth.hidePassword') : t('auth.showPassword')}
        aria-pressed={show}
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  )
}

export function Checkbox({ label, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-sm text-slate-700">
      <input type="checkbox" className="mt-0.5 size-4 shrink-0 rounded border-slate-300 text-brand-600 accent-brand-600" {...rest} />
      <span>{label}</span>
    </label>
  )
}

// ------------------------------------------------------------------ Tags (allergies, conditions)
export function TagInput({ value, onChange, placeholder, id, describedBy }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; id?: string; describedBy?: string }) {
  const [draft, setDraft] = useState('')
  const { t } = useTranslation()
  const add = () => {
    const v = draft.trim()
    if (v && !value.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...value, v])
    setDraft('')
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add()
    } else if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1))
  }
  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50/80 p-2 transition focus-within:border-brand-400 focus-within:bg-white focus-within:ring-4 focus-within:ring-brand-100/80">
      {value.map((item) => (
        <span key={item} className="inline-flex items-center gap-1 rounded-lg bg-teal-50 px-2.5 py-1 text-sm text-teal-700">
          {item}
          <button type="button" onClick={() => onChange(value.filter((x) => x !== item))} aria-label={t('health.remove', { item })} className="rounded hover:text-teal-900">
            <X className="size-3.5" />
          </button>
        </span>
      ))}
      <input
        id={id}
        aria-describedby={describedBy}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={add}
        placeholder={placeholder}
        className="min-w-32 flex-1 border-0 bg-transparent px-1.5 py-1 text-sm outline-none focus:outline-none"
      />
    </div>
  )
}

// ------------------------------------------------------------------ Feedback
export function Alert({ kind = 'info', children, className }: { kind?: 'info' | 'success' | 'error' | 'warning'; children: ReactNode; className?: string }) {
  const Icon = kind === 'success' ? CheckCircle2 : kind === 'error' || kind === 'warning' ? AlertCircle : Info
  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className={clsx(
        'flex items-start gap-3 rounded-xl border border-s-4 px-4 py-3 text-sm',
        {
          info: 'border-brand-100 border-s-brand-500 bg-brand-50/70 text-brand-800',
          success: 'border-mint-100 border-s-mint-500 bg-mint-50 text-green-800',
          error: 'border-red-100 border-s-red-500 bg-red-50 text-red-800',
          warning: 'border-amber-100 border-s-amber-500 bg-amber-50 text-amber-900',
        }[kind],
        className,
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  const customPad = /(^|\s)p-\d/.test(className ?? '')
  return <div className={clsx('rounded-3xl bg-white shadow-card ring-1 ring-slate-900/[0.04] transition-shadow', !customPad && 'p-6', className)}>{children}</div>
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx('animate-spin text-brand-600', className ?? 'size-6')} aria-hidden />
}

export function FullPageSpinner() {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-[60vh] items-center justify-center" role="status">
      <Spinner className="size-8" />
      <span className="sr-only">{t('common.loading')}</span>
    </div>
  )
}

// ------------------------------------------------------------------ Password strength (client hint only; server is authoritative)
export function PasswordStrength({ password }: { password: string }) {
  const { t } = useTranslation()
  if (!password) return <p className="text-xs text-slate-500">{t('auth.strength.rules')}</p>
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(password)).length
  let score = 0
  if (password.length >= 10 && classes >= 3) score = 2
  if (password.length >= 12 && classes >= 3) score = 3
  if (password.length >= 14 && classes === 4) score = 4
  if (score === 0 && password.length >= 8) score = 1
  const labels = ['weak', 'weak', 'fair', 'good', 'strong']
  const colors = ['bg-red-500', 'bg-red-500', 'bg-amber-500', 'bg-teal-500', 'bg-mint-600']
  return (
    <div className="space-y-1" aria-live="polite">
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className={clsx('h-1.5 flex-1 rounded-full', i <= score ? colors[score] : 'bg-slate-200')} />
        ))}
      </div>
      <p className="text-xs text-slate-500">
        {t('auth.strength.label')}: <span className="font-medium">{t(`auth.strength.${labels[score]}`)}</span> · {t('auth.strength.rules')}
      </p>
    </div>
  )
}
