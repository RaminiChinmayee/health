import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { FullPageSpinner } from './components/ui'

// Leaflet is large: load the map page only when visited.
const Hospitals = lazy(() => import('./features/hospitals/Hospitals'))
import { GuestOnly, RequireAuth } from './auth/guards'
import { AppLayout, AuthLayout, PublicLayout } from './components/layouts'
import Login from './pages/auth/Login'
import { AuthCallback, ForgotPassword, Onboarding, ResetPassword, VerifyEmail } from './pages/auth/Recovery'
import Register from './pages/auth/Register'
import Dashboard from './pages/app/Dashboard'
import { Help, NotBuilt } from './pages/app/Misc'
import HealthProfilePage from './pages/app/profile/HealthProfile'
import MyProfile from './pages/app/profile/MyProfile'
import PersonalInfo from './pages/app/profile/PersonalInfo'
import { AccountSettings, LanguagePreferences, PrivacySecurity } from './pages/app/profile/Settings'
import Home from './pages/public/Home'
import { AssessmentForm, AssessmentsHub } from './features/predict/Assessments'
import SymptomChecker from './features/predict/SymptomChecker'
import { DietHistory, PredictionCompare, PredictionDetail, PredictionHistory, Records } from './features/history/History'
import Diet from './features/diet/Diet'
import Chat from './features/chat/Chat'
import { ChatHistoryPage, ChatMemory } from './features/chat/Memory'
import ImageHistory from './features/chat/ImageHistory'
import Legal from './pages/public/Legal'

export default function App() {
  return (
    <Routes>
      {/* Public site */}
      <Route element={<PublicLayout />}>
        <Route index element={<Home />} />
        <Route path="privacy" element={<Legal kind="privacy" />} />
        <Route path="terms" element={<Legal kind="terms" />} />
        <Route path="disclaimer" element={<Legal kind="disclaimer" />} />
      </Route>

      {/* Auth pages */}
      <Route element={<AuthLayout />}>
        <Route element={<GuestOnly />}>
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
        </Route>
        <Route path="reset-password" element={<ResetPassword />} />
        <Route path="verify-email" element={<VerifyEmail />} />
        <Route path="auth/callback" element={<AuthCallback />} />
      </Route>

      {/* Authenticated app */}
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="onboarding" element={<Onboarding />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="profile" element={<MyProfile />} />
          <Route path="profile/personal" element={<PersonalInfo />} />
          <Route path="profile/health" element={<HealthProfilePage />} />
          <Route path="profile/language" element={<LanguagePreferences />} />
          <Route path="profile/security" element={<PrivacySecurity />} />
          <Route path="profile/settings" element={<AccountSettings />} />
          <Route path="help" element={<Help />} />
          <Route path="symptoms" element={<SymptomChecker />} />
          <Route path="assessments" element={<AssessmentsHub />} />
          <Route path="assessments/:type" element={<AssessmentForm />} />
          <Route path="hospitals" element={<Suspense fallback={<FullPageSpinner />}><Hospitals /></Suspense>} />
          <Route path="diet" element={<Diet />} />
          <Route path="records" element={<Records />} />
          <Route path="history/predictions" element={<PredictionHistory />} />
          <Route path="history/predictions/compare/:a/:b" element={<PredictionCompare />} />
          <Route path="history/predictions/:id" element={<PredictionDetail />} />
          <Route path="history/diets" element={<DietHistory />} />
          <Route path="chat" element={<Chat />} />
          <Route path="chat/memory" element={<ChatMemory />} />
          <Route path="chat/:id" element={<Chat />} />
          <Route path="history/chats" element={<ChatHistoryPage />} />
          <Route path="history/images" element={<ImageHistory />} />
        </Route>
      </Route>

      <Route element={<PublicLayout />}>
        <Route path="*" element={<NotBuilt titleKey="common.somethingWrong" />} />
      </Route>
    </Routes>
  )
}
