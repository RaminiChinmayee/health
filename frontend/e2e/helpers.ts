import { expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

export const PASSWORD = 'Monsoon-Garden-47!'
export const unique = () => `e2e.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`

export function linkFromLog(email: string, path: string): string {
  const log = readFileSync(process.env.BACKEND_LOG!, 'utf8')
  const blocks = log.split('[EMAIL NOT SENT').filter((b) => b.includes(`To: ${email}`))
  for (const b of blocks.reverse()) {
    const m = b.match(new RegExp(`(http://localhost:5173${path}\\?token=[\\w-]+)`))
    if (m) return m[1]
  }
  throw new Error(`no ${path} link for ${email}`)
}

/** Register via API (fast), verify via the emailed link, then log in through the UI. */
export async function signUpAndLogin(page: Page, opts: { gender?: string } = {}) {
  const email = unique()
  const r = await page.request.post('/api/auth/register', {
    data: { full_name: 'Lakshmi Devi', email, password: PASSWORD, confirm_password: PASSWORD, date_of_birth: '1985-06-15', gender: opts.gender ?? 'female', accept_terms: true, language: 'en' },
  })
  expect(r.status()).toBe(201)
  const token = new URL(linkFromLog(email, '/verify-email')).searchParams.get('token')
  expect((await page.request.post('/api/auth/verify-email', { data: { token } })).status()).toBe(200)
  await page.goto('/login')
  await page.locator('input[type=email]').fill(email)
  await page.locator('input[type=password]').fill(PASSWORD)
  await page.locator('form button[type=submit]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
  return email
}
