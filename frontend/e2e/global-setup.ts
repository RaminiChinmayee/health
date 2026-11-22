/** Safety guard: refuse to run browser tests against a backend that sends real email —
 *  the tests register many throwaway accounts. Start the backend with EMAIL_BACKEND=console. */
export default async function globalSetup() {
  const r = await fetch('http://127.0.0.1:8000/api/auth/config')
  const cfg = (await r.json()) as { email_delivery_configured: boolean }
  if (cfg.email_delivery_configured) {
    throw new Error('Backend has real email delivery enabled. Restart it with EMAIL_BACKEND=console FRONTEND_URL=http://localhost:5173 before running e2e tests.')
  }
}
