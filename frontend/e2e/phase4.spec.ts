import { expect, test, type Page } from '@playwright/test'
import { signUpAndLogin } from './helpers'

// Chrome's fake microphone (a test tone) lets us exercise real recording code.
test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] } })

const CONV = '00000000-0000-4000-8000-000000000001'

function sse(events: [string, unknown][]) {
  return events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('')
}

/** Stub the LLM-backed endpoints so tests are deterministic and don't use API quota. */
async function stubChat(page: Page, opts: { emergency?: boolean; selfHarm?: boolean; answer?: string } = {}) {
  const answer = opts.answer ?? 'Rest and drink plenty of fluids [1]. **See a doctor** if:\n- the fever lasts more than 3 days\n- you notice bleeding'
  const msgs: unknown[] = []
  await page.route('**/api/chat/message', async (route) => {
    const body = route.request().postDataJSON()
    const user = { id: 'u1', role: 'user', message_type: body.message_type, content: body.content, detected_language: 'en', reply_language: body.reply_language, citations: [], safety: {}, status: 'complete', created_at: new Date().toISOString() }
    const bot = { id: 'a1', role: 'assistant', message_type: 'text', content: answer, detected_language: null, reply_language: body.reply_language, citations: [{ n: 1, title: 'Fever', url: 'https://medlineplus.gov/fever.html', source: 'MedlinePlus' }], safety: {}, status: 'complete', created_at: new Date().toISOString() }
    msgs.push(user, bot)
    await route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: sse([
        ['meta', { conversation_id: CONV, user_message_id: 'u1', detected_language: 'en', reply_language: body.reply_language, safety: { emergency: !!opts.emergency, self_harm: !!opts.selfHarm } }],
        ['delta', { text: answer.slice(0, 20) }],
        ['delta', { text: answer.slice(20) }],
        ['done', { assistant_message: bot, context: { sources: 1 } }],
      ]),
    })
  })
  await page.route(`**/api/chat/conversations/${CONV}`, (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ json: { id: CONV, title: 'Fever questions', reply_language: 'en', message_count: msgs.length, created_at: new Date().toISOString(), last_message_at: new Date().toISOString(), messages: msgs } })
      : route.fulfill({ json: { id: CONV, title: 'Renamed', reply_language: 'en', message_count: 2, created_at: '', last_message_at: '' } }),
  )
}

test('chat: send, stream, citations, rich text, saved conversation', async ({ page }) => {
  await signUpAndLogin(page)
  await stubChat(page)
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: 'How can I help with your health today?' })).toBeVisible()
  await page.getByLabel('Ask a health question…').fill('I have a fever since yesterday')
  await page.getByLabel('Ask a health question…').press('Enter')
  await expect(page.getByText('I have a fever since yesterday')).toBeVisible()
  await expect(page.locator('strong', { hasText: 'See a doctor' })).toBeVisible()
  await expect(page.getByRole('listitem').filter({ hasText: 'the fever lasts more than 3 days' })).toBeVisible()
  await expect(page.getByText('Sources')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Fever' })).toHaveAttribute('href', 'https://medlineplus.gov/fever.html')
  await expect(page).toHaveURL(new RegExp(`/chat/${CONV}$`))
})

test('chat: emergency and self-harm banners show helplines', async ({ page }) => {
  await signUpAndLogin(page)
  await stubChat(page, { emergency: true })
  await page.goto('/chat')
  await page.getByLabel('Ask a health question…').fill('I have severe chest pain')
  await page.getByRole('button', { name: 'Send' }).click()
  const alert = page.getByRole('alert').filter({ hasText: 'This may be an emergency' })
  await expect(alert).toBeVisible()
  await expect(alert.getByRole('link', { name: '112' })).toHaveAttribute('href', 'tel:112')

  await page.unrouteAll()
  await stubChat(page, { selfHarm: true })
  await page.goto('/chat')
  await page.getByLabel('Ask a health question…').fill('I feel like ending my life')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByRole('alert').getByRole('link', { name: '14416' })).toHaveAttribute('href', 'tel:14416')
})

test('chat: LLM unavailable shows an honest error, no fake answer', async ({ page }) => {
  await signUpAndLogin(page)
  await page.route('**/api/chat/message', (route) =>
    route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: sse([['meta', { conversation_id: CONV, user_message_id: 'u1', detected_language: 'en', reply_language: 'en', safety: {} }], ['error', { code: 'llm_rate_limited', retry_after: 30 }]]) }),
  )
  await page.goto('/chat')
  await page.getByLabel('Ask a health question…').fill('hello')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText(/try again in about 30 seconds/)).toBeVisible()
  await expect(page.getByText('Sources')).toHaveCount(0)
})

test('voice input: record with microphone, transcript is editable before sending', async ({ page }) => {
  await signUpAndLogin(page)
  await stubChat(page)
  let uploaded = 0
  await page.route('**/api/chat/speech-to-text', async (route) => {
    const buf = route.request().postDataBuffer()!
    uploaded = buf.length
    expect(buf.includes(Buffer.from('WAVE'))).toBe(true) // the browser sent real WAV audio
    await route.fulfill({ json: { transcription_id: 't1', text: 'I have a cough', language: 'en', duration_seconds: 2 } })
  })
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Speak your question' }).click()
  await expect(page.getByText(/Recording…/)).toBeVisible()
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: 'Stop recording' }).click()
  await expect(page.getByLabel('Ask a health question…')).toHaveValue('I have a cough')
  expect(uploaded).toBeGreaterThan(10000)
  await expect(page.getByText('Check the text and edit it before sending.')).toBeVisible()
  await page.getByLabel('Ask a health question…').fill('I have a dry cough at night')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText('I have a dry cough at night')).toBeVisible()
  await expect(page.getByText('Voice').first()).toBeVisible() // sent as a voice message
})

test('voice input: speech service unavailable offers browser recognition', async ({ page }) => {
  await signUpAndLogin(page)
  await page.route('**/api/chat/speech-to-text', (route) => route.fulfill({ status: 503, json: { detail: { code: 'llm_unavailable' } } }))
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Speak your question' }).click()
  await page.waitForTimeout(900)
  await page.getByRole('button', { name: 'Stop recording' }).click()
  await expect(page.getByText("The assistant couldn't respond just now.")).toBeVisible()
  await expect(page.getByRole('button', { name: "Use this browser's speech recognition instead" })).toBeVisible()
})

test('text-to-speech: play, pause, resume, stop', async ({ page }) => {
  await signUpAndLogin(page)
  await stubChat(page)
  // 1 s of silence as WAV
  const rate = 8000, n = rate
  const wav = Buffer.alloc(44 + n * 2)
  wav.write('RIFF', 0); wav.writeUInt32LE(36 + n * 2, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22)
  wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * 2, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(n * 2, 40)
  let ttsCalls = 0
  await page.route('**/api/chat/text-to-speech', (route) => { ttsCalls++; return route.fulfill({ status: 200, headers: { 'content-type': 'audio/wav' }, body: wav }) })
  await page.goto('/chat')
  await page.getByLabel('Ask a health question…').fill('fever?')
  await page.getByRole('button', { name: 'Send' }).click()
  await page.getByRole('button', { name: 'Read aloud' }).click()
  await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()
  expect(ttsCalls).toBe(1)
  await page.getByRole('button', { name: 'Pause' }).click()
  await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible()
  await page.getByRole('button', { name: 'Stop' }).click()
  await expect(page.getByRole('button', { name: 'Read aloud' })).toBeVisible()
})

test('memory page: consent, add, edit, disable, delete, clear (real backend)', async ({ page }) => {
  await signUpAndLogin(page)
  await page.goto('/chat/memory')
  await expect(page.getByText('Nothing saved yet.')).toBeVisible()
  const consent = page.getByRole('checkbox', { name: 'Allow the assistant to remember details' })
  await consent.click()
  await expect(consent).toBeChecked()
  await expect(page.getByText(/^Allowed on/)).toBeVisible()
  await page.getByLabel('Category').selectOption('allergy')
  await page.getByLabel(/Add something to remember/).fill('Allergic to peanuts')
  await page.getByRole('button', { name: 'Add' }).click()
  await expect(page.getByText('Allergic to peanuts')).toBeVisible()
  await page.getByRole('button', { name: 'Edit' }).click()
  await page.getByLabel('Edit').fill('Allergic to peanuts and cashews')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Allergic to peanuts and cashews')).toBeVisible()
  await page.getByRole('checkbox', { name: 'Use this' }).click()
  await expect(page.locator('p.line-through', { hasText: 'cashews' })).toBeVisible()
  await page.reload() // persisted in PostgreSQL
  await expect(page.locator('p.line-through', { hasText: 'cashews' })).toBeVisible()
  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: 'Clear memory' }).click()
  await expect(page.getByText('Nothing saved yet.')).toBeVisible()
})

test('Parkinson’s voice test: records and analyses a sustained vowel', async ({ page }) => {
  await signUpAndLogin(page)
  await page.goto('/assessments/parkinsons')
  await expect(page.getByRole('heading', { name: /Record your voice/ })).toBeVisible()
  await page.getByRole('button', { name: 'Start recording' }).click()
  await expect(page.getByText(/Say “aaa” steadily/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Analyse recording' })).toBeVisible({ timeout: 12000 })
  await page.getByRole('button', { name: 'Analyse recording' }).click()
  // Chrome's fake microphone is a pure tone, not a voice: the server must refuse, not guess.
  await expect(page.getByText(/didn't sound like one steady|outside the range seen in the study|too quiet/)).toBeVisible()
})

test('dashboard shows summary, quick actions and emergency box', async ({ page }) => {
  await signUpAndLogin(page)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Good (morning|afternoon|evening), Lakshmi/)
  await expect(page.getByText(/Health profile \d+% complete/)).toBeVisible()
  for (const a of ['Symptom Checker', 'Health Assessments', 'Health Chat', 'Skin check', 'Hospitals', 'Diet Planner']) {
    await expect(page.getByRole('heading', { name: 'Quick actions' }).locator('..').locator('..').getByRole('link', { name: a })).toBeVisible()
  }
  await expect(page.locator('#main').getByRole('link', { name: '112' })).toHaveAttribute('href', 'tel:112')
})

test('image upload: preview, consent, result card (image model stubbed)', async ({ page }) => {
  await signUpAndLogin(page)
  await page.route('**/api/chat/image', async (route) => {
    const now = new Date().toISOString()
    const analysis = { id: 'img1', status: 'ok', model_version: '1.0.0', predicted_class: 'mel', probability: 0.55, probabilities: { mel: 0.55, nv: 0.3, bkl: 0.05, bcc: 0.04, akiec: 0.03, df: 0.02, vasc: 0.01 }, gate: { checked: true }, safety: { prompt_review: true }, attachment_id: null, conversation_id: CONV, created_at: now }
    await route.fulfill({ json: {
      conversation_id: CONV,
      user_message: { id: 'u1', role: 'user', message_type: 'image', content: 'Is this mole ok?', detected_language: 'en', reply_language: 'en', citations: [], safety: {}, status: 'complete', created_at: now, attachment_id: null },
      assistant_message: { id: 'a1', role: 'assistant', message_type: 'text', content: 'Please see a dermatologist soon.', detected_language: null, reply_language: 'en', citations: [], safety: { image_concern: true }, status: 'complete', created_at: now, image_analysis: analysis },
      analysis,
    } })
  })
  await page.route(`**/api/chat/conversations/${CONV}`, (route) => route.fulfill({ status: 404, json: { detail: { code: 'not_found' } } }))
  await page.goto('/chat')
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
  await page.locator('input[type=file][accept^="image"]').setInputFiles({ name: 'spot.png', mimeType: 'image/png', buffer: png })
  await expect(page.getByAltText('Selected photo')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send' })).toBeDisabled() // consent required first
  await page.getByRole('checkbox', { name: /I agree that this photo is stored privately/ }).check()
  await page.getByLabel('Ask a health question…').fill('Is this mole ok?')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText('Image analysis (AI estimate)')).toBeVisible()
  await expect(page.getByText('Melanoma').first()).toBeVisible()
  await expect(page.getByRole('alert').filter({ hasText: 'checked by a dermatologist soon' })).toBeVisible()
  await expect(page.getByText(/not a diagnosis/).first()).toBeVisible()
})

test('image upload rejects unsupported files before sending', async ({ page }) => {
  await signUpAndLogin(page)
  await page.goto('/chat')
  await page.locator('input[type=file][accept^="image"]').setInputFiles({ name: 'doc.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') })
  await expect(page.getByText('Please choose a JPG, PNG or WEBP image.')).toBeVisible()
})
