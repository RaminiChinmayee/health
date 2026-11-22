import { useMutation } from '@tanstack/react-query'
import { AudioLines, Mic, RotateCcw, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Button, Card } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { WavRecorder } from '../../lib/wavRecorder'
import type { PredictionRecord } from './shared'

const SECONDS = 6

/** Experimental: record a sustained "aaa" and let the server measure voice features with Praat. */
export function VoiceRecording({ onResult }: { onResult: (r: PredictionRecord) => void }) {
  const { t } = useTranslation()
  const [state, setState] = useState<'idle' | 'recording' | 'ready'>('idle')
  const [left, setLeft] = useState(SECONDS)
  const [level, setLevel] = useState(0)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<WavRecorder | null>(null)
  const timer = useRef<number | null>(null)
  useEffect(() => () => { rec.current?.cancel(); if (timer.current) window.clearInterval(timer.current) }, [])

  const analyse = useMutation({
    mutationFn: (b: Blob) => {
      const fd = new FormData()
      fd.append('file', b, 'vowel.wav')
      return api<PredictionRecord>('/api/predict/parkinsons/recording', { method: 'POST', body: fd })
    },
    onSuccess: onResult,
    onError: (e) => setError(e instanceof ApiError ? e.code : 'unknown'),
  })

  const start = async () => {
    setError(null)
    setBlob(null)
    const r = new WavRecorder()
    try {
      await r.start()
    } catch (e) {
      setError((e as Error).message)
      return
    }
    rec.current = r
    setState('recording')
    const t0 = Date.now()
    timer.current = window.setInterval(() => {
      const s = (Date.now() - t0) / 1000
      setLeft(Math.max(0, Math.ceil(SECONDS - s)))
      setLevel(r.level)
      if (s >= SECONDS) void stop()
    }, 100)
  }

  const stop = async () => {
    if (timer.current) window.clearInterval(timer.current)
    const r = rec.current
    if (!r) return
    rec.current = null
    const out = await r.stop() // keep full sample rate for voice-quality analysis
    setBlob(out.blob)
    setUrl(URL.createObjectURL(out.blob))
    setState('ready')
  }

  return (
    <Card className="mb-6 space-y-4 border-teal-200 bg-teal-50/30">
      <div className="flex items-start gap-3">
        <AudioLines className="mt-0.5 size-6 shrink-0 text-teal-600" aria-hidden />
        <div>
          <h2 className="font-semibold text-slate-900">{t('voiceTest.title')} <span className="ms-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800">{t('voiceTest.experimental')}</span></h2>
          <p className="mt-1 text-sm text-slate-600">{t('voiceTest.intro')}</p>
          <ol className="mt-2 list-decimal space-y-0.5 ps-5 text-sm text-slate-600">
            <li>{t('voiceTest.step1')}</li>
            <li>{t('voiceTest.step2', { seconds: SECONDS })}</li>
            <li>{t('voiceTest.step3')}</li>
          </ol>
        </div>
      </div>
      {state === 'recording' && (
        <div className="flex items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-red-700" role="status">
          <span className="text-2xl font-bold tabular-nums">{left}</span>
          <span className="text-sm">{t('voiceTest.sayAaa')}</span>
          <span className="h-2 flex-1 overflow-hidden rounded-full bg-red-100" aria-hidden><span className="block h-full bg-red-500" style={{ width: `${Math.min(100, level * 140)}%` }} /></span>
        </div>
      )}
      {url && state === 'ready' && <audio src={url} controls className="w-full" aria-label={t('voiceTest.preview')} />}
      {error && <Alert kind="warning">{t(`voiceTest.errors.${error}`, { defaultValue: t('chat.voice.errors.stt_failed') })}</Alert>}
      <div className="flex flex-wrap gap-2">
        {state === 'recording' ? (
          <Button variant="danger" onClick={stop}><Square className="size-4" aria-hidden />{t('chat.voice.stop')}</Button>
        ) : (
          <Button variant={state === 'ready' ? 'outline' : 'primary'} onClick={start} disabled={analyse.isPending}>{state === 'ready' ? <RotateCcw className="size-4" aria-hidden /> : <Mic className="size-4" aria-hidden />}{state === 'ready' ? t('voiceTest.again') : t('voiceTest.record')}</Button>
        )}
        {state === 'ready' && blob && <Button onClick={() => analyse.mutate(blob)} loading={analyse.isPending}>{t('voiceTest.analyse')}</Button>}
      </div>
      <p className="text-xs text-slate-500">{t('voiceTest.privacy')}</p>
    </Card>
  )
}
