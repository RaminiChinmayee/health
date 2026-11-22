import type { TFunction } from 'i18next'
import { ApiError } from './api'

/** Translate an API error into a user-facing message. */
export function errorMessage(t: TFunction, err: unknown): string {
  if (err instanceof ApiError) {
    const key = `errors.${err.code}`
    return t(key, { defaultValue: t('errors.unknown') })
  }
  return t('errors.unknown')
}

/** Map server field errors (codes) to translated messages keyed by field. */
export function fieldErrors(t: TFunction, err: unknown): Record<string, string> {
  if (!(err instanceof ApiError)) return {}
  const out: Record<string, string> = {}
  for (const [field, code] of Object.entries(err.fields)) {
    out[field] = t(`validation.${code}`, { defaultValue: t('validation.value_error') })
  }
  if (err.code === 'weak_password' && err.problems.length) {
    out.password = err.problems.map((p) => t(`validation.${p}`)).join(' ')
  }
  return out
}
