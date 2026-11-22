import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, refreshSession, setAccessToken, setOnAuthLost, type TokenResponse, type User } from '../lib/api'
import i18n, { changeLanguage } from '../i18n'
import { isLanguageCode, type LanguageCode } from '../i18n/languages'

type Status = 'loading' | 'authenticated' | 'anonymous'

type AuthState = {
  status: Status
  user: User | null
  sessionExpired: boolean
  login: (email: string, password: string, remember: boolean) => Promise<User>
  completeExternalLogin: () => Promise<User | null>
  logout: () => Promise<void>
  setUser: (u: User) => void
  setLanguage: (code: LanguageCode) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUserState] = useState<User | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)
  const qc = useQueryClient()

  const adopt = useCallback(async (data: TokenResponse) => {
    setAccessToken(data.access_token)
    setUserState(data.user)
    setStatus('authenticated')
    setSessionExpired(false)
    // The account's saved language wins over the device's on sign-in.
    if (isLanguageCode(data.user.ui_language) && data.user.ui_language !== i18n.language) {
      await changeLanguage(data.user.ui_language)
    }
    return data.user
  }, [])

  const clear = useCallback(() => {
    setAccessToken(null)
    setUserState(null)
    setStatus('anonymous')
    qc.clear() // never leave one user's cached data around for the next
  }, [qc])

  useEffect(() => {
    setOnAuthLost(() => {
      clear()
      setSessionExpired(true)
    })
    refreshSession().then((data) => {
      if (data) void adopt(data)
      else clear()
    })
  }, [adopt, clear])

  const login = useCallback(
    async (email: string, password: string, remember: boolean) => {
      const data = await api<TokenResponse>('/api/auth/login', {
        method: 'POST',
        auth: false,
        body: { email, password, remember_me: remember },
      })
      return adopt(data)
    },
    [adopt],
  )

  const completeExternalLogin = useCallback(async () => {
    const data = await refreshSession()
    return data ? adopt(data) : null
  }, [adopt])

  const logout = useCallback(async () => {
    try {
      await api('/api/auth/logout', { method: 'POST', auth: false })
    } finally {
      clear()
    }
  }, [clear])

  const setLanguage = useCallback(
    async (code: LanguageCode) => {
      await changeLanguage(code)
      if (status === 'authenticated') {
        const updated = await api<User>('/api/profile/language', { method: 'PUT', body: { ui_language: code } })
        setUserState(updated)
      }
    },
    [status],
  )

  const value = useMemo(
    () => ({ status, user, sessionExpired, login, completeExternalLogin, logout, setUser: setUserState, setLanguage }),
    [status, user, sessionExpired, login, completeExternalLogin, logout, setLanguage],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
