import { expect, test } from '@playwright/test'
import te from '../src/i18n/locales/features/te.json' with { type: 'json' }
import { signUpAndLogin } from './helpers'

test('symptom checker: search, select, results with emergency guidance, saved to history', async ({ page }) => {
  await signUpAndLogin(page)
  await page.getByRole('link', { name: 'Symptom Checker' }).first().click()
  const search = page.getByPlaceholder('Search symptoms…')
  for (const s of ['High fever', 'Headache', 'Pain behind the eyes', 'Joint pain', 'Skin rash']) {
    await search.fill(s.split(' ')[0])
    await page.getByRole('checkbox', { name: s, exact: true }).check()
  }
  await expect(page.getByRole('heading', { name: 'Selected symptoms (5)' })).toBeVisible()
  await page.getByRole('button', { name: 'Check symptoms' }).click()
  await expect(page.getByRole('heading', { name: 'Closest matches' })).toBeVisible()
  await expect(page.locator('ol li').first()).toContainText('Dengue')
  await expect(page.getByRole('alert').filter({ hasText: 'Seek medical care urgently' })).toBeVisible()
  await expect(page.getByText(/not a percentage chance/)).toBeVisible()
  await expect(page.locator('ol li').first()).toContainText(/Strong match|Possible match|Weak match/)
  // Top match is expanded with the doctor to consult, precautions and urgent warning signs.
  const first = page.locator('ol li').first()
  await expect(first.getByText('Doctor to consult')).toBeVisible()
  await expect(first.getByText('General physician')).toBeVisible()
  await expect(first.getByText(/only paracetamol/)).toBeVisible()
  await expect(first.getByText('Get urgent medical help if:')).toBeVisible()
  // Each match collapses / expands on click.
  await first.locator('summary').click()
  await expect(first.getByText('Doctor to consult')).toBeHidden()
  await first.locator('summary').click()
  await expect(first.getByText('Doctor to consult')).toBeVisible()
  // Model card discloses synthetic data.
  await page.getByText('About this model').click()
  await expect(page.getByText(/Synthetic/).first()).toBeVisible()

  await page.goto('/history/predictions')
  await expect(page.getByText('Dengue').first()).toBeVisible()
})

test('heart assessment: profile prefill, validation, result with explanation, compare history', async ({ page }) => {
  await signUpAndLogin(page, { gender: 'male' })
  await page.goto('/assessments')
  await page.getByRole('link', { name: /Heart disease risk/ }).click()
  await expect(page.getByLabel(/^Age/)).toHaveValue(/\d+/) // prefilled from DOB
  await expect(page.getByLabel(/^Sex/)).toHaveValue('1') // prefilled from gender
  await page.getByRole('button', { name: 'Get estimate' }).click()
  await expect(page.getByText('This field is required.').first()).toBeVisible()

  const fill = async (bp: string, chol: string, hr: string, exang: string, cp: string, oldpeak: string) => {
    await page.getByLabel('Chest pain type').selectOption(cp)
    await page.getByLabel(/Resting blood pressure/).fill(bp)
    await page.getByLabel(/Total cholesterol/).fill(chol)
    await page.getByLabel(/Fasting blood sugar/).selectOption('0')
    await page.getByLabel(/Maximum heart rate/).fill(hr)
    await page.getByLabel('Chest pain during exercise').selectOption(exang)
    await page.getByLabel(/ST depression/).fill(oldpeak)
    await page.getByRole('button', { name: 'Get estimate' }).click()
  }
  await fill('160', '290', '115', '1', '4', '3')
  await expect(page.getByText('Your result')).toBeVisible()
  await expect(page.getByText(/estimated risk/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What influenced this result' })).toBeVisible()
  await expect(page.getByText(/Some optional values were left blank/)).toBeVisible()
  await page.getByText('About this model').click()
  await expect(page.getByText('Sensitivity (finds people who have it)')).toBeVisible()
  await expect(page.getByText(/95% CI/).first()).toBeVisible()

  await page.getByRole('button', { name: 'New assessment' }).click()
  await fill('118', '180', '175', '0', '3', '0')
  await expect(page.getByText('Your result')).toBeVisible()

  await page.goto('/history/predictions')
  const boxes = page.getByRole('checkbox', { name: 'Select to compare' })
  await expect(boxes).toHaveCount(2)
  await boxes.nth(0).check()
  await boxes.nth(1).check()
  await page.getByRole('button', { name: 'Compare' }).click()
  await expect(page.getByRole('heading', { name: 'Comparison' })).toBeVisible()
  await expect(page.locator('tr', { hasText: 'Total cholesterol' })).toContainText('180')
  await expect(page.locator('tr', { hasText: 'Total cholesterol' })).toContainText('290')

  // Detail page shows the past-estimate banner; delete works.
  await page.goto('/history/predictions')
  await page.getByRole('link', { name: /Heart disease risk/ }).first().click()
  await expect(page.getByText(/This is a past estimate from/)).toBeVisible()
  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: 'Delete' }).click()
  await expect(page).toHaveURL(/\/history\/predictions$/)
  await expect(page.getByRole('checkbox', { name: 'Select to compare' })).toHaveCount(1)
})

test('diet planner: needs profile, generates plan, feedback and meal logging', async ({ page }) => {
  await signUpAndLogin(page)
  await page.goto('/diet')
  await expect(page.getByText(/Complete these in your health profile first/)).toBeVisible()
  await page.getByRole('link', { name: 'Edit health profile' }).click()
  await page.getByLabel('Height (cm)').fill('162')
  await page.getByLabel('Weight (kg)').fill('58')
  await page.getByLabel('Activity level').selectOption('light')
  await page.getByLabel('Dietary preference').selectOption('vegetarian')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Changes saved')).toBeVisible()

  await page.goto('/diet')
  await expect(page.getByText('Daily targets')).toBeVisible()
  await page.getByRole('button', { name: 'Generate plan' }).click()
  await expect(page.getByText('Saved to My Saved Diet Plans.')).toBeVisible()
  await expect(page.getByRole('tab', { name: /Day/ })).toHaveCount(7)
  for (const slot of ['Breakfast', 'Lunch', 'Snack', 'Dinner']) await expect(page.getByText(slot, { exact: true }).first()).toBeVisible()
  // Vegetarian: no chicken/fish/egg dishes anywhere in the plan.
  for (let i = 0; i < 7; i++) {
    await page.getByRole('tab', { name: `Day ${i + 1}` }).click()
    await expect(page.getByRole('tabpanel')).not.toContainText(/Chicken|Fish|Egg/)
  }
  await page.getByRole('button', { name: 'Mark as eaten' }).first().click()
  await expect(page.getByRole('button', { name: 'Logged' }).first()).toBeVisible()
  await page.getByRole('button', { name: "Don't show again" }).first().click()
  await expect(page.getByRole('button', { name: "Don't show again" }).first()).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('tab', { name: 'Tracker' }).click()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
  await expect(page.getByText('Nothing logged for this day.')).toHaveCount(0)

  await page.goto('/history/diets')
  await expect(page.getByText(/7 days/)).toBeVisible()
})

test('hospital finder: geolocation, list sorted by distance, map markers, call/directions', async ({ page, context }) => {
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 19.0402, longitude: 72.8616 })
  // Third-party OSM servers are stubbed for a deterministic UI test (the backend path is unit-tested).
  await page.route('**/api/hospitals?*', (route) =>
    route.fulfill({ json: { count: 2, attribution: '© OpenStreetMap contributors', results: [
      { id: 'way/2', name: 'Near Clinic', name_en: null, kind: 'clinic', lat: 19.041, lon: 72.862, distance_km: 0.12, address: 'MG Road, Mumbai', phone: '+91 22 1234 5678', website: null, emergency: false, opening_hours: 'Mo-Sa 09:00-18:00', directions_url: 'https://www.google.com/maps/dir/?api=1&destination=19.041,72.862', osm_url: 'https://www.openstreetmap.org/way/2' },
      { id: 'node/1', name: 'City Hospital', name_en: null, kind: 'hospital', lat: 19.045, lon: 72.862, distance_km: 0.55, address: null, phone: null, website: 'example.org', emergency: true, opening_hours: null, directions_url: 'https://www.google.com/maps/dir/?api=1&destination=19.045,72.862', osm_url: 'https://www.openstreetmap.org/node/1' },
    ] } }),
  )
  await signUpAndLogin(page)
  await page.goto('/hospitals')
  await expect(page.getByText('In an emergency, call 112.')).toBeVisible()
  await page.getByRole('button', { name: 'Use my location' }).click()
  await expect(page.getByText('2 places found')).toBeVisible()
  const cards = page.locator('article')
  await expect(cards.nth(0)).toContainText('Near Clinic')
  await expect(cards.nth(1)).toContainText('Emergency services')
  await expect(cards.nth(0).getByRole('link', { name: 'Call' })).toHaveAttribute('href', 'tel:+912212345678')
  await expect(cards.nth(0).getByRole('link', { name: 'Directions' })).toHaveAttribute('href', /google\.com\/maps\/dir/)
  await expect(page.locator('.leaflet-marker-icon')).toHaveCount(2)
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap')
})

test('Telugu: symptom names and assessment forms are translated', async ({ page }) => {
  await signUpAndLogin(page)
  await page.getByRole('button', { name: /Language/ }).click()
  const saved = page.waitForResponse((r) => r.url().endsWith('/api/profile/language') && r.status() === 200)
  await page.getByRole('menuitemradio', { name: /తెలుగు/ }).click()
  await saved // the preference is saved to the account before we reload the page
  await expect(page.locator('html')).toHaveAttribute('lang', 'te')
  await page.goto('/symptoms')
  await expect(page.getByRole('button', { name: te.symptoms.high_fever })).toBeVisible()
  await page.goto('/assessments/heart')
  await expect(page.getByText(te.fields.heart.cp.label)).toBeVisible()
})

test('kidney and lung assessments: forms, results and similarity display', async ({ page }) => {
  await signUpAndLogin(page)
  await page.goto('/assessments')
  await page.getByRole('link', { name: /Chronic kidney disease risk/ }).click()
  await page.getByLabel(/Blood pressure \(lower number\)/).fill('90')
  await page.getByLabel(/Serum creatinine/).fill('4.5')
  await page.getByLabel(/Haemoglobin/).fill('8.5')
  await page.getByLabel(/Urine albumin/).selectOption('4')
  await page.getByLabel('Appetite').selectOption('1')
  for (const q of [/high blood pressure/, /diabetes\?/, /Swelling of the feet/, /anaemia/]) {
    await page.getByRole('radiogroup', { name: q }).getByRole('radio', { name: 'Yes' }).click()
  }
  await page.getByRole('button', { name: 'Get estimate' }).click()
  await expect(page.getByText('Your result')).toBeVisible()
  await expect(page.getByText(/estimated risk/).first()).toBeVisible()

  await page.goto('/assessments')
  await page.getByRole('link', { name: /Lung cancer symptom screening/ }).click()
  await expect(page.getByRole('radiogroup')).toHaveCount(12)
  for (const g of await page.getByRole('radiogroup').all()) await g.getByRole('radio', { name: 'No' }).click()
  await page.getByRole('button', { name: 'Get estimate' }).click()
  await expect(page.getByText(/Answers resemble|Inconclusive/).first()).toBeVisible()
  await expect(page.getByText(/not a risk percentage/)).toBeVisible()
})
