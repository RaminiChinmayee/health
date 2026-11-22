import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthProvider'
import { FullPageSpinner } from '../components/ui'

/** Requires a signed-in user; sends Google sign-ups through onboarding first. */
export function RequireAuth() {
  const { status, user } = useAuth()
  const loc = useLocation()
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  if (user?.needs_onboarding && loc.pathname !== '/onboarding') return <Navigate to="/onboarding" replace />
  return <Outlet />
}

/** Login/register pages: signed-in users go straight to the dashboard. */
export function GuestOnly() {
  const { status } = useAuth()
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'authenticated') return <Navigate to="/dashboard" replace />
  return <Outlet />
}
