export const LANGUAGES = [
  { code: 'en', native: 'English', english: 'English', dir: 'ltr' },
  { code: 'hi', native: 'हिन्दी', english: 'Hindi', dir: 'ltr' },
  { code: 'bn', native: 'বাংলা', english: 'Bengali', dir: 'ltr' },
  { code: 'mr', native: 'मराठी', english: 'Marathi', dir: 'ltr' },
  { code: 'te', native: 'తెలుగు', english: 'Telugu', dir: 'ltr' },
  { code: 'ta', native: 'தமிழ்', english: 'Tamil', dir: 'ltr' },
  { code: 'gu', native: 'ગુજરાતી', english: 'Gujarati', dir: 'ltr' },
  { code: 'ur', native: 'اردو', english: 'Urdu', dir: 'rtl' },
  { code: 'kn', native: 'ಕನ್ನಡ', english: 'Kannada', dir: 'ltr' },
  { code: 'or', native: 'ଓଡ଼ିଆ', english: 'Odia', dir: 'ltr' },
  { code: 'ml', native: 'മലയാളം', english: 'Malayalam', dir: 'ltr' },
] as const

export type LanguageCode = (typeof LANGUAGES)[number]['code']

export function isLanguageCode(v: string): v is LanguageCode {
  return LANGUAGES.some((l) => l.code === v)
}

/** Locale tag for Intl date/number formatting. */
export function intlLocale(code: string): string {
  return code === 'en' ? 'en-IN' : `${code}-IN`
}
