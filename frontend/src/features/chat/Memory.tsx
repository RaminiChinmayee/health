import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Brain, Check, MessageSquare, Pencil, Plus, Search, ShieldCheck, Trash2, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Alert, Button, buttonClasses, Card, Checkbox, Field, FullPageSpinner, Input, Select } from '../../components/ui'
import { api } from '../../lib/api'
import { PageHeader } from '../../pages/app/profile/MyProfile'
import { useDate } from '../predict/shared'

type Item = { id: string; category: string; content: string; status: 'active' | 'pending' | 'disabled'; source: string; expires_at: string | null; created_at: string }
type State = { settings: { memory_enabled: boolean; use_profile: boolean; response_style: string; consent_at: string | null }; items: Item[]; retention: { health_context_days: number } }
const CATEGORIES = ['language', 'diet', 'allergy', 'meal_preference', 'health_context', 'response_style', 'other'] as const

export function ChatMemory() {
  const { t } = useTranslation()
  const date = useDate()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['chat-memory'], queryFn: () => api<State>('/api/chat/memory') })
  const summaries = useQuery({ queryKey: ['chat-summaries'], queryFn: () => api<{ id: string; conversation_id: string; summary: string; created_at: string }[]>('/api/chat/summaries') })
  const set = (d: State) => qc.setQueryData(['chat-memory'], d)
  // Optimistic: toggles respond instantly; rolled back if the server rejects the change.
  const settings = useMutation({
    mutationFn: (body: Partial<State['settings']>) => api<State>('/api/chat/memory', { method: 'PUT', body }),
    onMutate: (body) => {
      const prev = qc.getQueryData<State>(['chat-memory'])
      if (prev) set({ ...prev, settings: { ...prev.settings, ...body } })
      return { prev }
    },
    onError: (_e, _b, ctx) => ctx?.prev && set(ctx.prev),
    onSuccess: set,
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ['chat-memory'] })
  const patch = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => api(`/api/chat/memory/items/${id}`, { method: 'PATCH', body }), onSuccess: refresh })
  const del = useMutation({ mutationFn: (id: string) => api(`/api/chat/memory/items/${id}`, { method: 'DELETE' }), onSuccess: refresh })
  const add = useMutation({ mutationFn: (body: { category: string; content: string }) => api('/api/chat/memory/items', { method: 'POST', body }), onSuccess: () => { refresh(); setNewText('') } })
  const clear = useMutation({ mutationFn: () => api('/api/chat/memory', { method: 'DELETE' }), onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ['chat-summaries'] }) } })
  const [newCat, setNewCat] = useState<string>('diet')
  const [newText, setNewText] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  if (q.isLoading || !q.data) return <FullPageSpinner />
  const s = q.data.settings
  const pending = q.data.items.filter((i) => i.status === 'pending')
  const others = q.data.items.filter((i) => i.status !== 'pending')

  const row = (i: Item) => (
    <li key={i.id} className="flex items-start gap-3 py-3">
      <span className="mt-0.5 shrink-0 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{t(`chat.memory.categories.${i.category}`)}</span>
      <div className="min-w-0 flex-1">
        {editing === i.id ? (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); patch.mutate({ id: i.id, body: { content: editText } }); setEditing(null) }}>
            <Input value={editText} onChange={(e) => setEditText(e.target.value)} maxLength={500} aria-label={t('chat.memory.edit')} />
            <button type="submit" className="rounded p-2 text-green-700 hover:bg-green-50" aria-label={t('common.save')}><Check className="size-4" /></button>
            <button type="button" onClick={() => setEditing(null)} className="rounded p-2 text-slate-500 hover:bg-slate-100" aria-label={t('common.cancel')}><X className="size-4" /></button>
          </form>
        ) : (
          <>
            <p className={clsx('text-sm', i.status === 'disabled' ? 'text-slate-400 line-through' : 'text-slate-800')} dir="auto">{i.content}</p>
            <p className="text-xs text-slate-400">{t(`chat.memory.source.${i.source}`)} · {date(i.created_at)}{i.expires_at ? ` · ${t('chat.memory.expires', { date: date(i.expires_at) })}` : ''}</p>
          </>
        )}
      </div>
      {editing !== i.id && (
        <div className="flex shrink-0 items-center">
          <label className="me-1 flex items-center gap-1 text-xs text-slate-500" title={t('chat.memory.useThis')}>
            <input type="checkbox" className="size-4 accent-brand-600" checked={i.status === 'active'} onChange={(e) => patch.mutate({ id: i.id, body: { status: e.target.checked ? 'active' : 'disabled' } })} aria-label={t('chat.memory.useThis')} />
          </label>
          <button type="button" onClick={() => { setEditing(i.id); setEditText(i.content) }} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label={t('chat.memory.edit')}><Pencil className="size-4" /></button>
          <button type="button" onClick={() => del.mutate(i.id)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label={t('chat.memory.delete')}><Trash2 className="size-4" /></button>
        </div>
      )}
    </li>
  )

  const submitNew = (e: FormEvent) => { e.preventDefault(); if (newText.trim().length >= 2) add.mutate({ category: newCat, content: newText.trim() }) }

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
      <PageHeader title={t('chat.memory.title')} desc={t('chat.memory.subtitle')} action={<Link to="/chat" className={buttonClasses('outline', 'sm')}><MessageSquare className="size-4" aria-hidden />{t('nav.chatbot')}</Link>} />

      <Card className="space-y-4">
        <div className="flex items-start gap-3">
          <Brain className="mt-0.5 size-6 shrink-0 text-brand-600" aria-hidden />
          <div className="flex-1">
            <h2 className="font-semibold text-slate-900">{t('chat.memory.enableTitle')}</h2>
            <p className="mt-1 text-sm text-slate-600">{t('chat.memory.enableBody', { days: q.data.retention.health_context_days })}</p>
            <div className="mt-3"><Checkbox checked={s.memory_enabled} onChange={(e) => settings.mutate({ memory_enabled: e.target.checked })} label={<span className="font-medium">{t('chat.memory.enable')}</span>} /></div>
            {s.consent_at && s.memory_enabled && <p className="mt-1 text-xs text-slate-500">{t('chat.memory.consentGiven', { date: date(s.consent_at) })}</p>}
          </div>
        </div>
        <div className="flex items-start gap-3 border-t border-slate-100 pt-4">
          <ShieldCheck className="mt-0.5 size-6 shrink-0 text-teal-600" aria-hidden />
          <div className="flex-1">
            <h2 className="font-semibold text-slate-900">{t('chat.memory.profileTitle')}</h2>
            <p className="mt-1 text-sm text-slate-600">{t('chat.memory.profileBody')}</p>
            <div className="mt-3"><Checkbox checked={s.use_profile} onChange={(e) => settings.mutate({ use_profile: e.target.checked })} label={<span className="font-medium">{t('chat.memory.useProfile')}</span>} /></div>
          </div>
        </div>
        <div className="border-t border-slate-100 pt-4">
          <Field label={t('chat.memory.style')}>
            {(id) => (
              <Select id={id} value={s.response_style} onChange={(e) => settings.mutate({ response_style: e.target.value })} className="sm:w-64">
                {['brief', 'balanced', 'detailed'].map((v) => <option key={v} value={v}>{t(`chat.memory.styles.${v}`)}</option>)}
              </Select>
            )}
          </Field>
        </div>
      </Card>

      {pending.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/40">
          <h2 className="font-semibold text-slate-900">{t('chat.memory.pendingTitle')}</h2>
          <p className="mt-1 text-sm text-slate-600">{t('chat.memory.pendingBody')}</p>
          <ul className="mt-3 divide-y divide-amber-100">
            {pending.map((i) => (
              <li key={i.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-800" dir="auto">{i.content}</p>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" onClick={() => patch.mutate({ id: i.id, body: { status: 'active' } })}><Check className="size-4" aria-hidden />{t('chat.memory.remember')}</Button>
                  <Button size="sm" variant="outline" onClick={() => del.mutate(i.id)}>{t('chat.memory.dontRemember')}</Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <h2 className="font-semibold text-slate-900">{t('chat.memory.itemsTitle')}</h2>
        {!s.memory_enabled && <Alert kind="info" className="mt-3">{t('chat.memory.offNote')}</Alert>}
        {others.length === 0 ? <p className="mt-3 text-sm text-slate-500">{t('chat.memory.empty')}</p> : <ul className="mt-2 divide-y divide-slate-100">{others.map(row)}</ul>}
        <form onSubmit={submitNew} className="mt-4 flex flex-col gap-2 border-t border-slate-100 pt-4 sm:flex-row">
          <Select value={newCat} onChange={(e) => setNewCat(e.target.value)} aria-label={t('chat.memory.category')} className="sm:w-48">
            {CATEGORIES.map((c) => <option key={c} value={c}>{t(`chat.memory.categories.${c}`)}</option>)}
          </Select>
          <Input value={newText} onChange={(e) => setNewText(e.target.value)} placeholder={t('chat.memory.addPlaceholder')} aria-label={t('chat.memory.addPlaceholder')} maxLength={500} />
          <Button type="submit" variant="secondary" disabled={newText.trim().length < 2} loading={add.isPending}><Plus className="size-4" aria-hidden />{t('chat.memory.add')}</Button>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold text-slate-900">{t('chat.memory.summariesTitle')}</h2>
        <p className="mt-1 text-sm text-slate-600">{t('chat.memory.summariesBody')}</p>
        {!summaries.data?.length ? <p className="mt-3 text-sm text-slate-500">{t('chat.memory.noSummaries')}</p> : (
          <ul className="mt-3 space-y-3">
            {summaries.data.map((x) => (
              <li key={x.id} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                <p lang="en" dir="ltr">{x.summary}</p>
                <Link to={`/chat/${x.conversation_id}`} className="mt-1 inline-block text-xs font-medium text-brand-600">{date(x.created_at)} · {t('chat.memory.openChat')}</Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="border-red-200">
        <h2 className="font-semibold text-red-700">{t('chat.memory.clearTitle')}</h2>
        <p className="mt-1 text-sm text-slate-600">{t('chat.memory.clearBody')}</p>
        <Button variant="danger" className="mt-3" onClick={() => window.confirm(t('chat.memory.clearConfirm')) && clear.mutate()}><Trash2 className="size-4" aria-hidden />{t('chat.memory.clear')}</Button>
      </Card>
    </div>
  )
}

export function ChatHistoryPage() {
  const { t } = useTranslation()
  const date = useDate()
  const [q, setQ] = useState('')
  const list = useQuery({ queryKey: ['chats', 'page', q], queryFn: () => api<{ total: number; items: { id: string; title: string; preview: string | null; message_count: number; last_message_at: string }[] }>(`/api/history/chats?limit=100${q ? `&q=${encodeURIComponent(q)}` : ''}`) })
  return (
    <div className="mx-auto max-w-3xl animate-fade-up">
      <PageHeader title={t('profileMenu.chatHistory')} desc={t('chat.historySubtitle')} action={<Link to="/chat" className={buttonClasses('primary', 'sm')}>{t('chat.newChat')}</Link>} />
      <div className="relative mb-4">
        <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('chat.search')} aria-label={t('chat.search')} className="ps-9" />
      </div>
      {list.isLoading ? <FullPageSpinner /> : !list.data?.items.length ? (
        <Card className="py-12 text-center text-slate-500"><MessageSquare className="mx-auto mb-3 size-10 text-slate-300" aria-hidden />{q ? t('chat.noSearchResults') : t('chat.noChats')}</Card>
      ) : (
        <ul className="space-y-3">
          {list.data.items.map((c) => (
            <li key={c.id}>
              <Link to={`/chat/${c.id}`} className="block rounded-2xl border border-slate-200 bg-white p-4 shadow-card hover:border-brand-200">
                <p className="font-semibold text-slate-900">{c.title || t('chat.untitled')}</p>
                {c.preview && <p className="mt-0.5 truncate text-sm text-slate-600" dir="auto">{c.preview}</p>}
                <p className="mt-1 text-xs text-slate-400">{date(c.last_message_at, true)} · {t('chat.messages', { count: c.message_count })}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
