import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  AlertTriangle, BookOpen, Brain, Check, ImagePlus, Loader2, MessageSquarePlus, Mic, Pause, Pencil, Phone, Play, Search, Send, Settings2,
  Square, Trash2, Volume2, X,
} from 'lucide-react'
import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, Select, Spinner } from '../../components/ui'
import { LANGUAGES } from '../../i18n/languages'
import { api, ApiError, streamSSE } from '../../lib/api'
import { WavRecorder } from '../../lib/wavRecorder'
import { useDate } from '../predict/shared'
import { browserRecognitionSupported, SERVER_VOICES, startBrowserRecognition, useSpeaker } from './speech'
import { AnalysisCard, PrivateImage, type ImageAnalysis } from './ImageParts'

type Citation = { n: number; title: string; url: string; source: string }
type Msg = { id: string; role: 'user' | 'assistant'; message_type: string; content: string; detected_language: string | null; reply_language: string | null; citations: Citation[]; safety: { emergency?: boolean; self_harm?: boolean; error?: string; image_concern?: boolean }; status: string; created_at: string; streaming?: boolean; attachment_id?: string | null; image_analysis?: ImageAnalysis | null; localPreview?: string }
type Conv = { id: string; title: string; reply_language: string | null; message_count: number; last_message_at: string; preview?: string | null }

// ------------------------------------------------------------------ safe mini-markdown
function inline(text: string, citations: Citation[], key: string): ReactNode[] {
  // **bold** and [n] citation markers → elements. No HTML is ever injected.
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|\[\d{1,2}\])/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) out.push(<strong key={`${key}-${i++}`}>{tok.slice(2, -2)}</strong>)
    else {
      const n = Number(tok.slice(1, -1))
      const c = citations.find((x) => x.n === n)
      out.push(c ? <a key={`${key}-${i++}`} href={c.url} target="_blank" rel="noreferrer" className="mx-0.5 rounded bg-brand-50 px-1 text-[0.7rem] font-semibold text-brand-700 no-underline align-super" title={c.title}>{n}</a> : null)
    }
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function RichText({ text, citations }: { text: string; citations: Citation[] }) {
  const blocks: ReactNode[] = []
  const lines = text.split('\n')
  let list: { ordered: boolean; items: string[] } | null = null
  const flush = (k: number) => {
    if (!list) return
    const L = list.ordered ? 'ol' : 'ul'
    blocks.push(<L key={`l${k}`} className={clsx('my-2 space-y-1 ps-5', list.ordered ? 'list-decimal' : 'list-disc')}>{list.items.map((it, j) => <li key={j}>{inline(it, citations, `l${k}-${j}`)}</li>)}</L>)
    list = null
  }
  lines.forEach((raw, k) => {
    const line = raw.trimEnd()
    const ul = /^\s*[-*•]\s+(.*)/.exec(line)
    const ol = /^\s*\d+[.)]\s+(.*)/.exec(line)
    if (ul || ol) {
      const ordered = !!ol
      if (!list || list.ordered !== ordered) { flush(k); list = { ordered, items: [] } }
      list.items.push((ul ?? ol)![1])
      return
    }
    flush(k)
    if (!line.trim()) return
    const h = /^#{1,4}\s+(.*)/.exec(line)
    blocks.push(h ? <p key={k} className="mt-2 font-semibold">{inline(h[1], citations, `h${k}`)}</p> : <p key={k} className="my-1.5">{inline(line, citations, `p${k}`)}</p>)
  })
  flush(lines.length)
  return <>{blocks}</>
}

// ------------------------------------------------------------------ banners
function SafetyBanner({ kind }: { kind: 'emergency' | 'self_harm' }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="mb-3 flex flex-col gap-3 rounded-2xl border-2 border-red-300 bg-red-50 p-4 text-red-900 sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-start gap-2 text-sm font-semibold"><AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />{t(kind === 'emergency' ? 'chat.emergency' : 'chat.selfHarm')}</p>
      <div className="flex shrink-0 gap-2">
        {kind === 'self_harm' && <a href="tel:14416" className="inline-flex items-center gap-1.5 rounded-xl bg-red-600 px-3 py-2 text-sm font-semibold text-white"><Phone className="size-4" aria-hidden />14416</a>}
        <a href="tel:112" className="inline-flex items-center gap-1.5 rounded-xl bg-red-600 px-3 py-2 text-sm font-semibold text-white"><Phone className="size-4" aria-hidden />112</a>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ message bubble
function Bubble({ m, speaker, voice }: { m: Msg; speaker: ReturnType<typeof useSpeaker>; voice: string }) {
  const { t } = useTranslation()
  const date = useDate()
  const mine = m.role === 'user'
  const active = speaker.activeId === m.id
  const lang = LANGUAGES.find((l) => l.code === (m.reply_language ?? 'en'))
  if (m.status === 'failed' && !m.image_analysis) return null
  return (
    <div className={clsx('flex', mine ? 'justify-end' : 'justify-start')}>
      <div className={clsx('max-w-[92%] sm:max-w-[80%]', mine ? 'items-end' : 'items-start')}>
        {mine && m.message_type === 'image' && (m.attachment_id || m.localPreview) && (
          <div className="mb-1.5 flex justify-end">
            {m.localPreview ? <img src={m.localPreview} alt={t('skin.yourPhoto')} className="size-40 rounded-2xl object-cover shadow-sm" /> : <PrivateImage attachmentId={m.attachment_id!} alt={t('skin.yourPhoto')} className="size-40 rounded-2xl shadow-sm" />}
          </div>
        )}
        {(m.content && m.content !== '[image]') || m.streaming ? (
        <div dir="auto" className={clsx('rounded-2xl px-4 py-3 text-[0.95rem] leading-relaxed shadow-sm', mine ? 'rounded-ee-md bg-brand-600 text-white' : 'rounded-es-md border border-slate-200 bg-white text-slate-800')}>
          {mine ? <p className="whitespace-pre-wrap">{m.content}</p> : <RichText text={m.content} citations={m.citations} />}
          {m.streaming && <span className="ms-1 inline-block h-4 w-1.5 animate-pulse bg-brand-400 align-middle" aria-hidden />}
        </div>
        ) : null}
        {!mine && m.image_analysis && <AnalysisCard a={m.image_analysis} />}
        <div className={clsx('mt-1 flex flex-wrap items-center gap-2 px-1 text-[0.7rem] text-slate-400', mine && 'justify-end')}>
          {m.message_type === 'voice' && <span className="inline-flex items-center gap-1"><Mic className="size-3" aria-hidden />{t('chat.viaVoice')}</span>}
          <span>{date(m.created_at, true)}</span>
          {!mine && !m.streaming && m.content && (
            <span className="inline-flex items-center gap-1">
              {active && speaker.state === 'loading' ? <Loader2 className="size-3.5 animate-spin" aria-label={t('chat.tts.loading')} /> :
                active && speaker.state === 'playing' ? (
                  <button type="button" onClick={speaker.pause} className="rounded p-1 hover:bg-slate-100 hover:text-slate-700" aria-label={t('chat.tts.pause')}><Pause className="size-3.5" /></button>
                ) : active && speaker.state === 'paused' ? (
                  <button type="button" onClick={speaker.resume} className="rounded p-1 hover:bg-slate-100 hover:text-slate-700" aria-label={t('chat.tts.resume')}><Play className="size-3.5" /></button>
                ) : (
                  <button type="button" onClick={() => speaker.play(m.id, m.content, m.reply_language ?? 'en', voice)} className="inline-flex items-center gap-1 rounded p-1 hover:bg-slate-100 hover:text-slate-700" aria-label={t('chat.tts.play')}><Volume2 className="size-3.5" />{t('chat.tts.listen')}</button>
                )}
              {active && speaker.state !== 'idle' && <button type="button" onClick={speaker.stop} className="rounded p-1 hover:bg-slate-100 hover:text-slate-700" aria-label={t('chat.tts.stop')}><Square className="size-3" /></button>}
              {active && speaker.engine === 'browser' && <span title={t('chat.tts.browserNote')}>· {t('chat.tts.device')}</span>}
            </span>
          )}
          {!mine && lang && <span dir="ltr">{lang.native}</span>}
        </div>
        {!mine && m.citations.length > 0 && (
          <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-600"><BookOpen className="size-3.5" aria-hidden />{t('chat.sources')}</p>
            <ol className="mt-1 space-y-0.5 text-xs">
              {m.citations.map((c) => (
                <li key={c.n}><span className="font-semibold text-brand-700">[{c.n}]</span> <a href={c.url} target="_blank" rel="noreferrer" className="text-slate-700 underline decoration-slate-300 hover:text-brand-700" dir="ltr">{c.title}</a> <span className="text-slate-400">· {c.source}</span></li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ composer with voice input
function Composer({ onSend, onSendImage, busy, replyLang, setReplyLang, conversationId, openImage }: { onSend: (text: string, type: 'text' | 'voice') => void; onSendImage: (file: File, text: string) => void; busy: boolean; replyLang: string; setReplyLang: (l: string) => void; conversationId: string | null; openImage?: boolean }) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [image, setImage] = useState<{ file: File; url: string } | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const [consent, setConsent] = useState(() => { try { return localStorage.getItem('healthai.imageConsent') === '1' } catch { return false } })
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => { if (openImage) fileInput.current?.click() }, [openImage])
  const pickImage = (f: File | undefined) => {
    setImageError(null)
    if (!f) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) { setImageError('unsupported_image_type'); return }
    if (f.size > 8 * 1024 * 1024) { setImageError('file_too_large'); return }
    setImage({ file: f, url: URL.createObjectURL(f) })
  }
  const [voiceUsed, setVoiceUsed] = useState(false)
  const [rec, setRec] = useState<'idle' | 'recording' | 'transcribing' | 'browser'>('idle')
  const [secs, setSecs] = useState(0)
  const [level, setLevel] = useState(0)
  const [preview, setPreview] = useState<string | null>(null)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const recorder = useRef<WavRecorder | null>(null)
  const stopBrowser = useRef<(() => void) | null>(null)
  const timer = useRef<number | null>(null)
  const area = useRef<HTMLTextAreaElement>(null)

  useEffect(() => () => { recorder.current?.cancel(); if (timer.current) window.clearInterval(timer.current) }, [])

  const startRecording = async () => {
    setVoiceError(null)
    setPreview(null)
    const r = new WavRecorder()
    try {
      await r.start()
    } catch (e) {
      setVoiceError(`chat.voice.errors.${(e as Error).message}`)
      return
    }
    recorder.current = r
    setRec('recording')
    setSecs(0)
    const t0 = Date.now()
    timer.current = window.setInterval(() => {
      const s = (Date.now() - t0) / 1000
      setSecs(s)
      setLevel(r.level)
      if (s >= 60) void stopRecording()
    }, 100)
  }

  const stopRecording = async () => {
    if (timer.current) window.clearInterval(timer.current)
    const r = recorder.current
    if (!r) return
    recorder.current = null
    const { blob, seconds } = await r.stop(16000)
    setPreview(URL.createObjectURL(blob))
    if (seconds < 0.5) {
      setRec('idle')
      setVoiceError('chat.voice.errors.audio_too_short')
      return
    }
    setRec('transcribing')
    const fd = new FormData()
    fd.append('file', blob, 'speech.wav')
    fd.append('language', replyLang)
    if (conversationId) fd.append('conversation_id', conversationId)
    try {
      const out = await api<{ text: string; language: string }>('/api/chat/speech-to-text', { method: 'POST', body: fd })
      setText((cur) => (cur ? `${cur} ${out.text}` : out.text))
      setVoiceUsed(true)
      area.current?.focus()
    } catch (err) {
      setVoiceError(`chat.voice.errors.${err instanceof ApiError ? err.code : 'stt_failed'}`)
    } finally {
      setRec('idle')
    }
  }

  const useBrowserRecognition = () => {
    setVoiceError(null)
    setRec('browser')
    stopBrowser.current = startBrowserRecognition(replyLang, (tx) => { setText(tx); setVoiceUsed(true) }, (code) => setVoiceError(`chat.voice.errors.${code}`), () => setRec('idle'))
  }

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const v = text.trim()
    if (image) {
      if (!consent || busy) return
      onSendImage(image.file, v)
      setImage(null)
      setText('')
      return
    }
    if (!v || busy) return
    onSend(v, voiceUsed ? 'voice' : 'text')
    setText('')
    setVoiceUsed(false)
    setPreview(null)
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit() }
  }
  const sttUnavailable = voiceError && /llm_|stt_failed|network/.test(voiceError)

  return (
    <form onSubmit={submit} className="border-t border-slate-200 bg-white p-3 sm:p-4">
      {voiceError && (
        <Alert kind="warning" className="mb-2">
          {t(voiceError, { defaultValue: t('chat.voice.errors.stt_failed') })}
          {sttUnavailable && browserRecognitionSupported() && <button type="button" onClick={useBrowserRecognition} className="mt-1 block font-semibold underline">{t('chat.voice.useBrowser')}</button>}
        </Alert>
      )}
      {rec === 'recording' && (
        <div className="mb-2 flex items-center gap-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="status">
          <span className="relative flex size-3"><span className="absolute inline-flex size-full animate-ping rounded-full bg-red-400 opacity-75" /><span className="relative inline-flex size-3 rounded-full bg-red-600" /></span>
          {t('chat.voice.recording')} {Math.floor(secs)}s
          <span className="h-2 flex-1 overflow-hidden rounded-full bg-red-100" aria-hidden><span className="block h-full bg-red-500 transition-[width]" style={{ width: `${Math.min(100, level * 140)}%` }} /></span>
        </div>
      )}
      {rec === 'transcribing' && <p className="mb-2 flex items-center gap-2 text-sm text-slate-600" role="status"><Spinner className="size-4" />{t('chat.voice.transcribing')}</p>}
      {rec === 'browser' && <p className="mb-2 flex items-center gap-2 text-sm text-slate-600" role="status"><Mic className="size-4 text-red-600" />{t('chat.voice.listening')}</p>}
      {imageError && <Alert kind="warning" className="mb-2">{t(`skin.errors.${imageError}`)}</Alert>}
      {image && (
        <div className="mb-2 flex items-start gap-3 rounded-xl border border-fuchsia-200 bg-fuchsia-50/40 p-2.5">
          <div className="relative shrink-0">
            <img src={image.url} alt={t('skin.preview')} className="size-20 rounded-lg object-cover" />
            <button type="button" onClick={() => setImage(null)} aria-label={t('skin.remove')} className="absolute -end-2 -top-2 grid size-6 place-items-center rounded-full bg-slate-900 text-white shadow"><X className="size-3.5" /></button>
          </div>
          <div className="min-w-0 text-xs text-slate-700">
            <p className="font-semibold text-slate-900">{t('skin.attachTitle')}</p>
            <p className="mt-0.5">{t('skin.attachHint')}</p>
            <label className="mt-2 flex items-start gap-2">
              <input type="checkbox" className="mt-0.5 size-4 accent-brand-600" checked={consent} onChange={(e) => { setConsent(e.target.checked); try { localStorage.setItem('healthai.imageConsent', e.target.checked ? '1' : '0') } catch { /* ignore */ } }} />
              <span>{t('skin.consent')}</span>
            </label>
          </div>
        </div>
      )}
      {preview && rec === 'idle' && (
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <span>{t('chat.voice.preview')}</span>
          <audio src={preview} controls className="h-8 max-w-60" />
          {voiceUsed && <span>{t('chat.voice.editHint')}</span>}
        </div>
      )}
      <div className="flex items-end gap-2">
        <div className="flex-1 rounded-2xl border border-slate-300 bg-white focus-within:border-brand-500 focus-within:ring-4 focus-within:ring-brand-100">
          <textarea ref={area} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} rows={Math.min(6, Math.max(1, text.split('\n').length))} maxLength={4000}
            placeholder={t('chat.placeholder')} aria-label={t('chat.placeholder')} dir="auto"
            className="block w-full resize-none rounded-2xl border-0 bg-transparent px-4 py-3 text-sm outline-none focus:outline-none" />
          <div className="flex items-center justify-between gap-2 px-2 pb-2">
            <label className="flex items-center gap-1.5 text-xs text-slate-500">
              <span className="max-sm:sr-only">{t('chat.replyIn')}</span>
              <Select value={replyLang} onChange={(e) => setReplyLang(e.target.value)} aria-label={t('chat.replyIn')} className="w-auto min-w-28 py-1 text-xs">
                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
              </Select>
            </label>
            <span className="text-[0.7rem] text-slate-400 max-sm:hidden">{t('chat.enterHint')}</span>
          </div>
        </div>
        <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => { pickImage(e.target.files?.[0]); e.target.value = '' }} />
        <Button type="button" variant="outline" onClick={() => fileInput.current?.click()} disabled={busy || rec !== 'idle'} aria-label={t('skin.attach')} title={t('skin.attach')} className="size-12 rounded-full p-0"><ImagePlus className="size-5" /></Button>
        {rec === 'recording' ? (
          <Button type="button" variant="danger" onClick={stopRecording} aria-label={t('chat.voice.stop')} className="size-12 rounded-full p-0"><Square className="size-5" /></Button>
        ) : rec === 'browser' ? (
          <Button type="button" variant="danger" onClick={() => stopBrowser.current?.()} aria-label={t('chat.voice.stop')} className="size-12 rounded-full p-0"><Square className="size-5" /></Button>
        ) : (
          <Button type="button" variant="outline" onClick={startRecording} disabled={rec === 'transcribing' || busy} aria-label={t('chat.voice.start')} title={t('chat.voice.start')} className="size-12 rounded-full p-0"><Mic className="size-5" /></Button>
        )}
        <Button type="submit" disabled={(image ? !consent : !text.trim()) || busy || rec !== 'idle'} aria-label={t('chat.send')} className="size-12 rounded-full p-0">
          {busy ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5 rtl:rotate-180" />}
        </Button>
      </div>
    </form>
  )
}

// ------------------------------------------------------------------ sidebar
function Sidebar({ activeId, onNew }: { activeId: string | null; onNew: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const list = useQuery({ queryKey: ['chats', q], queryFn: () => api<{ total: number; items: Conv[] }>(`/api/history/chats?limit=50${q ? `&q=${encodeURIComponent(q)}` : ''}`) })
  const rename = useMutation({ mutationFn: ({ id, title }: { id: string; title: string }) => api(`/api/chat/conversations/${id}`, { method: 'PATCH', body: { title } }), onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey: ['chats'] }) } })
  const del = useMutation({ mutationFn: (id: string) => api(`/api/chat/conversations/${id}`, { method: 'DELETE' }), onSuccess: (_d, id) => { qc.invalidateQueries({ queryKey: ['chats'] }); if (id === activeId) navigate('/chat') } })
  const clearAll = useMutation({ mutationFn: () => api('/api/chat/conversations', { method: 'DELETE' }), onSuccess: () => { qc.invalidateQueries({ queryKey: ['chats'] }); navigate('/chat') } })
  return (
    <aside className="flex h-full flex-col border-e border-slate-200 bg-slate-50/80" aria-label={t('chat.history')}>
      <div className="space-y-2 p-3">
        <Button onClick={onNew} className="w-full"><MessageSquarePlus className="size-4" aria-hidden />{t('chat.newChat')}</Button>
        <div className="relative">
          <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('chat.search')} aria-label={t('chat.search')} className="w-full rounded-xl border border-slate-200 bg-white py-2 pe-3 ps-9 text-sm outline-none focus:border-brand-400" />
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {list.isLoading ? <div className="flex justify-center py-6"><Spinner /></div> : !list.data?.items.length ? (
          <p className="px-3 py-6 text-center text-sm text-slate-500">{q ? t('chat.noSearchResults') : t('chat.noChats')}</p>
        ) : list.data.items.map((c) => (
          <div key={c.id} className={clsx('group mb-1 flex items-center rounded-xl', c.id === activeId ? 'bg-white shadow-card ring-1 ring-brand-200' : 'hover:bg-white')}>
            {editing === c.id ? (
              <form className="flex flex-1 items-center gap-1 p-1.5" onSubmit={(e) => { e.preventDefault(); if (title.trim()) rename.mutate({ id: c.id, title: title.trim() }) }}>
                <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-label={t('chat.rename')} className="min-w-0 flex-1 rounded-lg border border-brand-300 px-2 py-1 text-sm outline-none" />
                <button type="submit" className="rounded p-1 text-green-700 hover:bg-green-50" aria-label={t('common.save')}><Check className="size-4" /></button>
                <button type="button" onClick={() => setEditing(null)} className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label={t('common.cancel')}><X className="size-4" /></button>
              </form>
            ) : (
              <>
                <Link to={`/chat/${c.id}`} className="min-w-0 flex-1 px-3 py-2.5">
                  <p className="truncate text-sm font-medium text-slate-800">{c.title || c.preview || t('chat.untitled')}</p>
                  {c.title && c.preview && <p className="truncate text-xs text-slate-500" dir="auto">{c.preview}</p>}
                </Link>
                <div className="flex shrink-0 pe-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                  <button type="button" onClick={() => { setEditing(c.id); setTitle(c.title || '') }} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label={t('chat.rename')}><Pencil className="size-3.5" /></button>
                  <button type="button" onClick={() => window.confirm(t('chat.confirmDelete')) && del.mutate(c.id)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label={t('chat.delete')}><Trash2 className="size-3.5" /></button>
                </div>
              </>
            )}
          </div>
        ))}
      </nav>
      <div className="space-y-1 border-t border-slate-200 p-3 text-sm">
        <Link to="/chat/memory" className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-slate-600 hover:bg-white hover:text-brand-700"><Brain className="size-4" aria-hidden />{t('chat.memoryLink')}</Link>
        {!!list.data?.total && <button type="button" onClick={() => window.confirm(t('chat.confirmClearAll')) && clearAll.mutate()} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-red-600 hover:bg-red-50"><Trash2 className="size-4" aria-hidden />{t('chat.clearAll')}</button>}
      </div>
    </aside>
  )
}

// ------------------------------------------------------------------ page
export default function Chat() {
  const { id } = useParams()
  const [search] = useSearchParams()
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const speaker = useSpeaker()
  const [messages, setMessages] = useState<Msg[]>([])
  const [convId, setConvId] = useState<string | null>(id ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ code: string; retry_after?: number | null } | null>(null)
  const [banner, setBanner] = useState<'emergency' | 'self_harm' | null>(null)
  const [replyLang, setReplyLang] = useState(user?.chatbot_language ?? 'en')
  const [voice, setVoice] = useState<string>(() => { try { return localStorage.getItem('healthai.voice') ?? 'Kore' } catch { return 'Kore' } })
  const [showSettings, setShowSettings] = useState(false)
  const [mobileList, setMobileList] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController | null>(null)

  const conv = useQuery({
    queryKey: ['conversation', id],
    queryFn: () => api<Conv & { messages: Msg[] }>(`/api/chat/conversations/${id}`),
    enabled: !!id,
  })
  useEffect(() => {
    if (!id) { setMessages([]); setConvId(null); setBanner(null); setError(null); return }
    if (conv.data && !busy) {
      setMessages(conv.data.messages)
      setConvId(conv.data.id)
      if (conv.data.reply_language) setReplyLang(conv.data.reply_language)
      const lastUser = [...conv.data.messages].reverse().find((m) => m.role === 'user')
      setBanner(lastUser?.safety.self_harm ? 'self_harm' : lastUser?.safety.emergency ? 'emergency' : null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, conv.data])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages])
  useEffect(() => () => abort.current?.abort(), [])

  const send = useCallback(async (text: string, type: 'text' | 'voice') => {
    setError(null)
    setBusy(true)
    speaker.stop()
    const now = new Date().toISOString()
    const tempUser: Msg = { id: `u-${now}`, role: 'user', message_type: type, content: text, detected_language: null, reply_language: replyLang, citations: [], safety: {}, status: 'complete', created_at: now }
    const tempBot: Msg = { id: `a-${now}`, role: 'assistant', message_type: 'text', content: '', detected_language: null, reply_language: replyLang, citations: [], safety: {}, status: 'complete', created_at: now, streaming: true }
    setMessages((m) => [...m, tempUser, tempBot])
    abort.current = new AbortController()
    let newConv: string | null = null
    try {
      await streamSSE('/api/chat/message', { content: text, conversation_id: convId, reply_language: replyLang, message_type: type }, (ev, data) => {
        const d = data as Record<string, unknown>
        if (ev === 'meta') {
          newConv = d.conversation_id as string
          setConvId(newConv)
          const s = d.safety as { emergency: boolean; self_harm: boolean }
          setBanner(s.self_harm ? 'self_harm' : s.emergency ? 'emergency' : null)
          setMessages((m) => m.map((x) => (x.id === tempUser.id ? { ...x, id: d.user_message_id as string, detected_language: d.detected_language as string, safety: s } : x)))
        } else if (ev === 'delta') {
          setMessages((m) => m.map((x) => (x.id === tempBot.id ? { ...x, content: x.content + (d.text as string) } : x)))
        } else if (ev === 'done') {
          const final = d.assistant_message as Msg
          setMessages((m) => m.map((x) => (x.id === tempBot.id ? final : x)))
        } else if (ev === 'error') {
          setError({ code: d.code as string, retry_after: d.retry_after as number | null })
          setMessages((m) => m.filter((x) => x.id !== tempBot.id))
        }
      }, abort.current.signal)
    } catch (e) {
      if ((e as DOMException)?.name !== 'AbortError') {
        setError({ code: e instanceof ApiError ? e.code : 'unknown' })
        setMessages((m) => m.filter((x) => x.id !== tempBot.id))
      }
    } finally {
      setBusy(false)
      qc.invalidateQueries({ queryKey: ['chats'] })
      if (newConv && newConv !== id) navigate(`/chat/${newConv}`, { replace: true })
    }
  }, [convId, replyLang, id, navigate, qc, speaker])

  const sendImage = useCallback(async (file: File, text: string) => {
    setError(null)
    setBusy(true)
    speaker.stop()
    const now = new Date().toISOString()
    const local = URL.createObjectURL(file)
    const tempUser: Msg = { id: `u-${now}`, role: 'user', message_type: 'image', content: text || '[image]', detected_language: null, reply_language: replyLang, citations: [], safety: {}, status: 'complete', created_at: now, localPreview: local }
    const tempBot: Msg = { id: `a-${now}`, role: 'assistant', message_type: 'text', content: t('skin.analysing'), detected_language: null, reply_language: replyLang, citations: [], safety: {}, status: 'complete', created_at: now, streaming: true }
    setMessages((m) => [...m, tempUser, tempBot])
    const fd = new FormData()
    fd.append('file', file)
    if (text) fd.append('question', text)
    if (convId) fd.append('conversation_id', convId)
    fd.append('reply_language', replyLang)
    fd.append('consent', 'true')
    try {
      const r = await api<{ conversation_id: string; user_message: Msg; assistant_message: Msg }>('/api/chat/image', { method: 'POST', body: fd })
      setConvId(r.conversation_id)
      setMessages((m) => m.map((x) => (x.id === tempUser.id ? { ...r.user_message, localPreview: local } : x.id === tempBot.id ? r.assistant_message : x)))
      if (r.conversation_id !== id) navigate(`/chat/${r.conversation_id}`, { replace: true })
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== tempBot.id && x.id !== tempUser.id))
      setError({ code: e instanceof ApiError ? e.code : 'unknown' })
    } finally {
      setBusy(false)
      qc.invalidateQueries({ queryKey: ['chats'] })
    }
  }, [convId, replyLang, id, navigate, qc, speaker, t])

  const newChat = () => { abort.current?.abort(); setMobileList(false); navigate('/chat') }
  const changeLang = (l: string) => { setReplyLang(l); if (convId) void api(`/api/chat/conversations/${convId}`, { method: 'PATCH', body: { reply_language: l } }) }

  const suggestions = ['s1', 's2', 's3', 's4'].map((k) => t(`chat.suggestions.${k}`))

  return (
    <div className="-mx-4 -my-8 flex h-[calc(100dvh-4rem)] sm:-mx-6 lg:-mx-8">
      <div className={clsx('w-72 shrink-0', mobileList ? 'fixed inset-y-16 start-0 z-30 block shadow-lift' : 'hidden md:block')}>
        <Sidebar activeId={convId} onNew={newChat} />
      </div>
      {mobileList && <button aria-label={t('common.close')} className="fixed inset-0 top-16 z-20 bg-black/20 md:hidden" onClick={() => setMobileList(false)} />}

      <section className="flex min-w-0 flex-1 flex-col bg-white" aria-label={t('nav.chatbot')}>
        <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <button type="button" className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 md:hidden" onClick={() => setMobileList(true)} aria-label={t('chat.history')}><MessageSquarePlus className="size-5" /></button>
            <h1 className="truncate font-semibold text-slate-900">{conv.data?.title || t('nav.chatbot')}</h1>
          </div>
          <div className="relative">
            <button type="button" onClick={() => setShowSettings((s) => !s)} aria-expanded={showSettings} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label={t('chat.settings')}><Settings2 className="size-5" /></button>
            {showSettings && (
              <div className="absolute end-0 z-20 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-4 shadow-lift">
                <label className="block text-sm font-medium text-slate-700">{t('chat.tts.voice')}
                  <Select value={voice} onChange={(e) => { setVoice(e.target.value); try { localStorage.setItem('healthai.voice', e.target.value) } catch { /* ignore */ } }} className="mt-1">
                    {SERVER_VOICES.map((v) => <option key={v} value={v}>{v}</option>)}
                  </Select>
                </label>
                <Link to="/chat/memory" className="mt-3 flex items-center gap-2 text-sm font-medium text-brand-600"><Brain className="size-4" aria-hidden />{t('chat.memoryLink')}</Link>
              </div>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6" aria-live="polite">
          <div className="mx-auto max-w-3xl space-y-5">
            {banner && <SafetyBanner kind={banner} />}
            {id && conv.isLoading ? <div className="flex justify-center py-10"><Spinner className="size-8" /></div> : messages.length === 0 ? (
              <div className="py-10 text-center">
                <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-600 to-teal-600 text-white shadow-lift"><Brain className="size-7" aria-hidden /></div>
                <h2 className="mt-4 text-xl font-semibold text-slate-900">{t('chat.welcomeTitle')}</h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">{t('chat.welcomeBody')}</p>
                <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                  {suggestions.map((s) => <button key={s} type="button" onClick={() => send(s, 'text')} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-start text-sm text-slate-700 hover:border-brand-300 hover:bg-brand-50">{s}</button>)}
                </div>
              </div>
            ) : messages.map((m) => <Fragment key={m.id}><Bubble m={m} speaker={speaker} voice={voice} /></Fragment>)}
            {error && (
              <Alert kind="error">
                {t(`skin.errors.${error.code}`, { defaultValue: t(`chat.errors.${error.code}`, { defaultValue: t('chat.errors.llm_unavailable'), seconds: error.retry_after ?? 60 }) })}
              </Alert>
            )}
            {speaker.error && <Alert kind="info">{t(`chat.tts.${speaker.error}`)}</Alert>}
            <div ref={bottom} />
          </div>
        </div>
        <p className="px-4 pb-1 text-center text-[0.7rem] text-slate-400">{t('chat.disclaimer')}</p>
        <div className="mx-auto w-full max-w-3xl">
          <Composer onSend={send} onSendImage={sendImage} busy={busy} replyLang={replyLang} setReplyLang={changeLang} conversationId={convId} openImage={search.get('image') === '1'} />
        </div>
      </section>
    </div>
  )
}
