import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import te from '../src/i18n/locales/te.json' with { type: 'json' }
import hi from '../src/i18n/locales/hi.json' with { type: 'json' }
import hiF from '../src/i18n/locales/features/hi.json' with { type: 'json' }

const LOG = process.env.BACKEND_LOG!  // see helpers.ts
const PASSWORD = 'Monsoon-Garden-47!'
const unique = () => `e2e.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`

/** Read the newest link of a given kind for an address from the backend's console-email log. */
function linkFromLog(email: string, path: string): string {
  const log = readFileSync(LOG, 'utf8')
  const blocks = log.split('[EMAIL NOT SENT').filter((b) => b.includes(`To: ${email}`))
  for (const b of blocks.reverse()) {
    const m = b.match(new RegExp(`(http://localhost:5173${path}\\?token=[\\w-]+)`))
    if (m) return m[1]
  }
  throw new Error(`no ${path} link for ${email}`)
}

async function registerAndVerify(page: Page, email: string) {
  await page.goto('/register')
  await page.getByLabel('Full name').fill('Lakshmi Devi')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Date of birth').fill('1992-06-15')
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByLabel('Confirm password').fill(PASSWORD)
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  // Honest delivery status: console backend means no email was sent.
  await expect(page.getByText('email delivery is not configured')).toBeVisible()
  await page.goto(linkFromLog(email, '/verify-email').replace('http://localhost:5173', ''))
  await expect(page.getByText('Your email has been verified')).toBeVisible()
}

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('homepage renders all sections and is public', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your Personal AI-Powered Health & Lifestyle Assistant')
  for (const title of [
    'Intelligent Disease Prediction', 'AI Healthcare Chatbot', 'Multimodal Health Assistance', 'Nearby Hospital Finder',
    'Personalized Diet Planning', 'Health Records and Tracking', 'Multilingual Assistance', 'Explainable AI Insights',
  ]) await expect(page.getByRole('heading', { name: title })).toBeVisible()
  for (const id of ['features', 'how-it-works', 'privacy', 'languages', 'faq', 'about', 'contact']) {
    await expect(page.locator(`#${id}`)).toBeAttached()
  }
  await expect(page.getByRole('link', { name: 'Privacy Policy' })).toBeVisible()
  await page.getByRole('link', { name: 'Explore Features' }).click()
  await expect(page.locator('#features')).toBeInViewport()
})

test('language selector switches the UI, including RTL for Urdu', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Language/ }).first().click()
  await page.getByRole('menuitemradio', { name: /తెలుగు/ }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(te.home.hero.title)
  await expect(page.locator('html')).toHaveAttribute('lang', 'te')
  await page.reload() // persists on this device
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(te.home.hero.title)

  await page.getByRole('button', { name: /Language/ }).first().click()
  await page.getByRole('menuitemradio', { name: /اردو/ }).click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')

  await page.getByRole('button', { name: /Language/ }).first().click()
  await page.getByRole('menuitemradio', { name: /English/ }).click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
})

test('protected pages redirect to login', async ({ page }) => {
  await page.goto('/profile/health')
  await expect(page).toHaveURL(/\/login$/)
})

test('registration validates fields client-side', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel('Email address').fill('not-an-email')
  await page.getByLabel('Password', { exact: true }).fill('short')
  await page.getByLabel('Confirm password').fill('different')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByText('Enter your full name.')).toBeVisible()
  await expect(page.getByText('Enter a valid email address.')).toBeVisible()
  await expect(page.getByText('Use at least 10 characters.')).toBeVisible()
  await expect(page.getByText('Passwords do not match.')).toBeVisible()
  await expect(page.getByText('You must accept the terms to continue.')).toBeVisible()
})

test('register → verify → login → profile menu → health profile → language persists → logout', async ({ page }) => {
  const email = unique()
  await registerAndVerify(page, email)

  // Unverified login is blocked before verification; here we're verified so login works.
  await login(page, email)
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), Lakshmi/ })).toBeVisible()

  // Profile menu in the top-right with all 12 entries.
  const menuButton = page.getByRole('button', { name: 'Account menu' })
  const box = await menuButton.boundingBox()
  const vw = page.viewportSize()!.width
  expect(box!.x).toBeGreaterThan(vw * 0.75)
  expect(box!.y).toBeLessThan(80)
  await menuButton.click()
  const menu = page.getByRole('menu', { name: 'Account menu' })
  for (const item of [
    'My Profile', 'Personal Information', 'Health Profile', 'My Health Records', 'My Prediction History', 'My Chat History',
    'My Saved Diet Plans', 'Language Preferences', 'Privacy and Security', 'Account Settings', 'Help and Support', 'Log out',
  ]) await expect(menu.getByRole('menuitem', { name: item })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(menu).toBeHidden()

  // Health profile persists.
  await menuButton.click()
  await menu.getByRole('menuitem', { name: 'Health Profile' }).click()
  await page.getByLabel('Height (cm)').fill('158')
  await page.getByLabel('Weight (kg)').fill('55')
  await page.getByLabel('Activity level').selectOption('moderate')
  await page.getByLabel('Dietary preference').selectOption('vegetarian')
  const allergies = page.getByLabel(/Food allergies/)
  await allergies.fill('Peanuts')
  await allergies.press('Enter')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Changes saved')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Height (cm)')).toHaveValue('158')
  await expect(page.getByText('Peanuts')).toBeVisible()
  await expect(page.getByText('22', { exact: false }).first()).toBeVisible()

  // Change language while signed in → saved to the account.
  await page.getByRole('button', { name: /Language/ }).click()
  await page.getByRole('menuitemradio', { name: /हिन्दी/ }).click()
  await expect(page.getByRole('heading', { name: hi.health.title })).toBeVisible()

  // Log out, clear device preference, log back in → account language restored.
  await page.getByRole('button', { name: hi.profileMenu.label }).click()
  await page.getByRole('menuitem', { name: hi.profileMenu.logout }).click()
  await expect(page).toHaveURL('/')
  await page.evaluate(() => localStorage.clear())
  await page.goto('/login')
  await page.reload()
  await page.locator('input[type=email]').fill(email)
  await page.locator('input[type=password]').fill(PASSWORD)
  await page.locator('form button[type=submit]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.locator('html')).toHaveAttribute('lang', 'hi')
  const hiGreetings = Object.values(hiF.dash.greeting).map((g) => (g as string).replace('{{name}}', 'Lakshmi'))
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(new RegExp(hiGreetings.join('|')))
})

test('session survives reload; logout blocks protected pages', async ({ page }) => {
  const email = unique()
  await registerAndVerify(page, email)
  await login(page, email)
  await page.reload()
  await expect(page).toHaveURL(/\/dashboard$/) // refresh cookie restored the session
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
})

test('forgot password → reset via link → login with new password', async ({ page }) => {
  const email = unique()
  await registerAndVerify(page, email)
  await page.goto('/forgot-password')
  await page.getByLabel('Email address').fill(email)
  await page.getByRole('button', { name: 'Send reset link' }).click()
  await expect(page.getByText('If an account exists for that email')).toBeVisible()

  const link = linkFromLog(email, '/reset-password').replace('http://localhost:5173', '')
  await page.goto(link)
  const NEW = 'Fresh-Lotus-Pond-93'
  await page.getByLabel('New password').fill(NEW)
  await page.getByLabel('Confirm password').fill(NEW)
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByText('Your password has been reset')).toBeVisible()

  // Reusing the link fails.
  await page.goto(link)
  await page.getByLabel('New password').fill(NEW + 'x')
  await page.getByLabel('Confirm password').fill(NEW + 'x')
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByText('This link is invalid or has expired.')).toBeVisible()

  await page.goto('/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(NEW)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
})

test('Google button is hidden when the server has no Google credentials', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()
  await expect(page.getByText('Continue with Google')).toHaveCount(0)
})

test('mobile layout: no horizontal scroll on homepage', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await page.goto('/')
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})
