import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import enFeatures from './locales/features/en.json'
import { LANGUAGES, type LanguageCode, isLanguageCode } from './languages'

const STORAGE_KEY = 'healthai.lang'

// Every non-English locale is a separate chunk, loaded only when selected.
const loaders = import.meta.glob<{ default: Record<string, unknown> }>(['./locales/*.json', '!./locales/en.json'])
// Feature strings (symptoms, diseases, dishes, forms…) live in a second file per language.
const featureLoaders = import.meta.glob<{ default: Record<string, unknown> }>(['./locales/features/*.json', '!./locales/features/en.json'])

function storedLanguage(): LanguageCode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v && isLanguageCode(v) ? v : null
  } catch {
    return null
  }
}

function browserLanguage(): LanguageCode {
  for (const l of navigator.languages ?? [navigator.language]) {
    const base = l.toLowerCase().split('-')[0]
    if (isLanguageCode(base)) return base
  }
  return 'en'
}

function applyDocumentLanguage(code: LanguageCode) {
  const meta = LANGUAGES.find((l) => l.code === code)!
  document.documentElement.lang = code
  document.documentElement.dir = meta.dir
}

async function ensureLoaded(code: LanguageCode) {
  if (i18n.hasResourceBundle(code, 'translation')) return
  const load = loaders[`./locales/${code}.json`]
  if (!load) return // missing locale falls back to English
  const featureLoad = featureLoaders[`./locales/features/${code}.json`]
  const [mod, feat] = await Promise.all([load(), featureLoad ? featureLoad() : Promise.resolve({ default: {} })])
  i18n.addResourceBundle(code, 'translation', { ...mod.default, ...feat.default }, true, true)
}

export async function changeLanguage(code: LanguageCode) {
  await ensureLoaded(code)
  await i18n.changeLanguage(code)
  applyDocumentLanguage(code)
  try {
    localStorage.setItem(STORAGE_KEY, code)
  } catch {
    /* storage unavailable — preference still saved to the account when signed in */
  }
}

export async function initI18n() {
  await i18n.use(initReactI18next).init({
    resources: { en: { translation: { ...en, ...enFeatures } } },
    lng: 'en',
    fallbackLng: 'en',
    interpolation: { escapeValue: false }, // React already escapes
    returnNull: false,
  })
  const initial = storedLanguage() ?? browserLanguage()
  if (initial !== 'en') await changeLanguage(initial)
  else applyDocumentLanguage('en')
}

export default i18n
