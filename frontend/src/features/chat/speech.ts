import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'

export const BCP47: Record<string, string> = {
  en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN', mr: 'mr-IN', te: 'te-IN', ta: 'ta-IN', gu: 'gu-IN', ur: 'ur-IN', kn: 'kn-IN', or: 'or-IN', ml: 'ml-IN',
}
export const SERVER_VOICES = ['Kore', 'Puck', 'Charon', 'Aoede', 'Leda', 'Orus'] as const

/** Strip markdown and citation markers before speaking. */
export function speakableText(md: string): string {
  return md.replace(/\[(\d{1,2})\]/g, '').replace(/\*\*/g, '').replace(/^\s*[-*]\s+/gm, '').replace(/\s+/g, ' ').trim()
}

type State = 'idle' | 'loading' | 'playing' | 'paused'

/**
 * Plays a message aloud. Uses the server's multilingual TTS; if that is unavailable, falls back to
 * the browser's speech synthesis (voice quality and language coverage depend on the device).
 */
export function useSpeaker() {
  const [state, setState] = useState<State>('idle')
  const [activeId, setActiveId] = useState<string | null>(null)
  const [engine, setEngine] = useState<'server' | 'browser' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const urls = useRef<Map<string, string>>(new Map())

  const stop = useCallback(() => {
    audio.current?.pause()
    if (audio.current) audio.current.currentTime = 0
    window.speechSynthesis?.cancel()
    setState('idle')
    setActiveId(null)
  }, [])

  useEffect(() => () => {
    stop()
    urls.current.forEach((u) => URL.revokeObjectURL(u))
  }, [stop])

  const browserSpeak = useCallback((text: string, lang: string, voiceName?: string) => {
    if (!('speechSynthesis' in window)) {
      setError('tts_unsupported')
      setState('idle')
      return
    }
    const u = new SpeechSynthesisUtterance(text)
    u.lang = BCP47[lang] ?? 'en-IN'
    const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang))
    const chosen = voices.find((v) => v.name === voiceName) ?? voices[0]
    if (chosen) u.voice = chosen
    else if (lang !== 'en') setError('tts_no_browser_voice')
    u.onend = () => { setState('idle'); setActiveId(null) }
    u.onerror = () => { setState('idle'); setActiveId(null) }
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
    setEngine('browser')
    setState('playing')
  }, [])

  const play = useCallback(async (id: string, markdown: string, lang: string, voice: string) => {
    stop()
    setError(null)
    setActiveId(id)
    const text = speakableText(markdown)
    setState('loading')
    try {
      let url = urls.current.get(`${id}|${voice}`)
      if (!url) {
        const blob = await api<Blob>('/api/chat/text-to-speech', { method: 'POST', body: { text: text.slice(0, 3000), voice } })
        url = URL.createObjectURL(blob)
        urls.current.set(`${id}|${voice}`, url)
      }
      const a = audio.current ?? new Audio()
      audio.current = a
      a.src = url
      a.onended = () => { setState('idle'); setActiveId(null) }
      await a.play()
      setEngine('server')
      setState('playing')
    } catch {
      // Server TTS unavailable (not configured, rate-limited, offline): use the device instead.
      browserSpeak(text, lang)
    }
  }, [stop, browserSpeak])

  const pause = useCallback(() => {
    if (engine === 'server') audio.current?.pause()
    else window.speechSynthesis?.pause()
    setState('paused')
  }, [engine])

  const resume = useCallback(() => {
    if (engine === 'server') void audio.current?.play()
    else window.speechSynthesis?.resume()
    setState('playing')
  }, [engine])

  return { state, activeId, engine, error, play, pause, resume, stop }
}

// ------------------------------------------------------------------ browser speech recognition (fallback)
type SR = { lang: string; interimResults: boolean; continuous: boolean; start: () => void; stop: () => void; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: ((e: { error: string }) => void) | null; onend: (() => void) | null }

export function browserRecognitionSupported(): boolean {
  return typeof window !== 'undefined' && !!((window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition)
}

export function startBrowserRecognition(lang: string, onText: (t: string) => void, onError: (code: string) => void, onEnd: () => void): () => void {
  const Ctor = (window as unknown as { SpeechRecognition?: new () => SR }).SpeechRecognition || (window as unknown as { webkitSpeechRecognition: new () => SR }).webkitSpeechRecognition
  const r = new Ctor()
  r.lang = BCP47[lang] ?? 'en-IN'
  r.interimResults = true
  r.continuous = false
  r.onresult = (e) => onText(Array.from(e.results).map((res) => res[0].transcript).join(' '))
  r.onerror = (e) => onError(e.error === 'not-allowed' ? 'permission_denied' : e.error === 'no-speech' ? 'no_speech_detected' : 'stt_failed')
  r.onend = onEnd
  r.start()
  return () => r.stop()
}
