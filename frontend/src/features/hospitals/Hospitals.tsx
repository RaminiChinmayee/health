import 'leaflet/dist/leaflet.css'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import L from 'leaflet'
import { Crosshair, ExternalLink, Globe, Hospital, MapPin, Navigation, Phone, Pill, Search, ShieldPlus, Siren, Stethoscope } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { CircleMarker, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import { Alert, Button, Card, Input, Select, Spinner } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { PageHeader } from '../../pages/app/profile/MyProfile'

type Kind = 'hospital' | 'clinic' | 'pharmacy'
type Place = { id: string; name: string | null; name_en: string | null; kind: Kind; lat: number; lon: number; distance_km: number; address: string | null; phone: string | null; website: string | null; emergency: boolean; opening_hours: string | null; directions_url: string; osm_url: string }
type Resp = { results: Place[]; count: number; attribution: string }
type Center = { lat: number; lon: number }

const KIND_COLOR: Record<Kind, string> = { hospital: '#e11d48', clinic: '#0b5cab', pharmacy: '#16a34a' }

function pin(kind: Kind, active: boolean) {
  const c = KIND_COLOR[kind]
  const s = active ? 34 : 26
  return L.divIcon({
    className: '',
    iconSize: [s, s],
    iconAnchor: [s / 2, s],
    html: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z" fill="${c}" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="10" r="2.6" fill="#fff"/></svg>`,
  })
}

function FitBounds({ center, places }: { center: Center; places: Place[] }) {
  const map = useMap()
  useEffect(() => {
    const pts: [number, number][] = [[center.lat, center.lon], ...places.slice(0, 25).map((p) => [p.lat, p.lon] as [number, number])]
    if (pts.length > 1) map.fitBounds(pts, { padding: [30, 30], maxZoom: 15 })
    else map.setView([center.lat, center.lon], 14)
  }, [center, places, map])
  return null
}

function FlyTo({ target }: { target: Place | null }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lon], Math.max(map.getZoom(), 15), { duration: 0.6 })
  }, [target, map])
  return null
}

export default function Hospitals() {
  const { t, i18n } = useTranslation()
  const [center, setCenter] = useState<Center | null>(null)
  const [locating, setLocating] = useState(false)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [radius, setRadius] = useState(5)
  const [kinds, setKinds] = useState<Kind[]>(['hospital', 'clinic'])
  const [place, setPlace] = useState('')
  const [placeResults, setPlaceResults] = useState<{ name: string; lat: number; lon: number }[] | null>(null)
  const [placeBusy, setPlaceBusy] = useState(false)
  const [active, setActive] = useState<Place | null>(null)

  const params = useMemo(() => {
    if (!center) return null
    const p = new URLSearchParams({ lat: center.lat.toFixed(6), lon: center.lon.toFixed(6), radius_km: String(radius) })
    kinds.forEach((k) => p.append('kinds', k))
    return p.toString()
  }, [center, radius, kinds])

  const q = useQuery({ queryKey: ['hospitals', params], queryFn: () => api<Resp>(`/api/hospitals?${params}`), enabled: !!params && kinds.length > 0, staleTime: 5 * 60_000 })

  const locate = () => {
    setGeoError(null)
    if (!('geolocation' in navigator)) {
      setGeoError(t('hospitals.errors.unsupported'))
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        setPlaceResults(null)
        setCenter({ lat: pos.coords.latitude, lon: pos.coords.longitude })
      },
      (err) => {
        setLocating(false)
        setGeoError(err.code === err.PERMISSION_DENIED ? t('hospitals.errors.denied') : t('hospitals.errors.unavailable'))
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    )
  }

  const searchPlace = async (e: FormEvent) => {
    e.preventDefault()
    if (place.trim().length < 2) return
    setPlaceBusy(true)
    setGeoError(null)
    try {
      const r = await api<{ results: { name: string; lat: number; lon: number }[] }>(`/api/geocode?q=${encodeURIComponent(place.trim())}&lang=${i18n.language}`)
      if (!r.results.length) setGeoError(t('hospitals.errors.noPlace'))
      else if (r.results.length === 1) {
        setCenter({ lat: r.results[0].lat, lon: r.results[0].lon })
        setPlaceResults(null)
      } else setPlaceResults(r.results)
    } catch {
      setGeoError(t('hospitals.errors.service'))
    } finally {
      setPlaceBusy(false)
    }
  }

  const toggleKind = (k: Kind) => setKinds((cur) => (cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]))
  const results = q.data?.results ?? []
  const fmtKm = (km: number) => new Intl.NumberFormat(i18n.language === 'en' ? 'en-IN' : `${i18n.language}-IN`, { maximumFractionDigits: 1 }).format(km)

  return (
    <div className="animate-fade-up">
      <PageHeader title={t('hospitals.title')} desc={t('hospitals.subtitle')} />
      <a href="tel:112" className="mb-5 flex items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 hover:bg-red-100">
        <Siren className="size-5" aria-hidden /> {t('hospitals.emergencyBanner')}
      </a>

      <Card className="mb-5 space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <Button onClick={locate} loading={locating} className="shrink-0">
            <Crosshair className="size-4" aria-hidden /> {locating ? t('hospitals.locating') : t('hospitals.useLocation')}
          </Button>
          <form onSubmit={searchPlace} className="flex flex-1 gap-2">
            <label className="sr-only" htmlFor="place-q">{t('hospitals.searchPlace')}</label>
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
              <Input id="place-q" value={place} onChange={(e) => setPlace(e.target.value)} placeholder={t('hospitals.searchPlaceholder')} className="ps-9" />
            </div>
            <Button type="submit" variant="outline" loading={placeBusy}>{t('hospitals.search')}</Button>
          </form>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {(['hospital', 'clinic', 'pharmacy'] as Kind[]).map((k) => (
            <button key={k} type="button" aria-pressed={kinds.includes(k)} onClick={() => toggleKind(k)}
              className={clsx('inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm', kinds.includes(k) ? 'border-slate-800 bg-slate-800 text-white' : 'border-slate-300 bg-white text-slate-700')}>
              <span className="size-2.5 rounded-full" style={{ background: KIND_COLOR[k] }} aria-hidden />
              {t(`hospitals.kinds.${k}`)}
            </button>
          ))}
          <label className="ms-auto flex items-center gap-2 text-sm text-slate-600">
            {t('hospitals.radius')}
            <Select value={radius} onChange={(e) => setRadius(Number(e.target.value))} className="w-28 py-1.5">
              {[2, 5, 10, 20].map((r) => <option key={r} value={r}>{t('hospitals.km', { n: r })}</option>)}
            </Select>
          </label>
        </div>
        {placeResults && (
          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">{t('hospitals.chooseLocation')}</p>
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
              {placeResults.map((p, i) => (
                <li key={i}><button type="button" className="w-full px-4 py-2.5 text-start text-sm hover:bg-slate-50" onClick={() => { setCenter({ lat: p.lat, lon: p.lon }); setPlaceResults(null) }}>{p.name}</button></li>
              ))}
            </ul>
          </div>
        )}
        {geoError && <Alert kind="warning">{geoError}</Alert>}
        <p className="text-xs text-slate-500">{t('hospitals.privacy')}</p>
      </Card>

      {!center ? (
        <Card className="py-14 text-center text-slate-500">
          <MapPin className="mx-auto mb-3 size-10 text-slate-300" aria-hidden />
          {t('hospitals.start')}
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_24rem]">
          <div className="relative z-0 h-[420px] overflow-hidden rounded-2xl border border-slate-200 lg:h-[640px]">
            <MapContainer center={[center.lat, center.lon]} zoom={14} className="size-full" scrollWheelZoom>
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <CircleMarker center={[center.lat, center.lon]} radius={8} pathOptions={{ color: '#fff', weight: 3, fillColor: '#0b5cab', fillOpacity: 1 }}>
                <Popup>{t('hospitals.youAreHere')}</Popup>
              </CircleMarker>
              {results.map((p) => (
                <Marker key={p.id} position={[p.lat, p.lon]} icon={pin(p.kind, active?.id === p.id)} eventHandlers={{ click: () => setActive(p) }}>
                  <Popup><strong>{p.name ?? t('hospitals.unnamed')}</strong><br />{t('hospitals.distance', { km: fmtKm(p.distance_km) })}</Popup>
                </Marker>
              ))}
              <FitBounds center={center} places={results} />
              <FlyTo target={active} />
            </MapContainer>
          </div>

          <div className="space-y-3 lg:max-h-[640px] lg:overflow-y-auto lg:pe-1" aria-live="polite">
            {q.isFetching ? (
              <div className="flex justify-center py-10"><Spinner /></div>
            ) : q.isError ? (
              <Alert kind="error">
                {q.error instanceof ApiError && q.error.code === 'places_unavailable' ? t('hospitals.errors.service') : t('common.somethingWrong')}
                {/* Never leave someone looking for care without an option. */}
                <a href={`https://www.google.com/maps/search/hospitals/@${center.lat},${center.lon},14z`} target="_blank" rel="noreferrer" className="mt-2 flex items-center gap-1.5 font-semibold underline">
                  <ExternalLink className="size-4" aria-hidden /> {t('hospitals.fallback')}
                </a>
              </Alert>
            ) : (
              <>
                <p className="text-sm font-medium text-slate-600">{t('hospitals.results', { count: results.length })}</p>
                {!results.length && <Card className="text-sm text-slate-500">{t('hospitals.none')}</Card>}
                {results.map((p) => (
                  <article key={p.id} onClick={() => setActive(p)} className={clsx('cursor-pointer rounded-2xl border bg-white p-4 shadow-card transition hover:-translate-y-0.5', active?.id === p.id ? 'border-brand-400 ring-4 ring-brand-100' : 'border-transparent hover:border-brand-200')}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 gap-3">
                      <span className="grid size-11 shrink-0 place-items-center rounded-xl text-white shadow-sm" style={{ background: `linear-gradient(135deg, ${KIND_COLOR[p.kind]}cc, ${KIND_COLOR[p.kind]})` }} aria-hidden>
                        {p.kind === 'hospital' ? <Hospital className="size-5" /> : p.kind === 'pharmacy' ? <Pill className="size-5" /> : <Stethoscope className="size-5" />}
                      </span>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-slate-900">{p.name ?? t('hospitals.unnamed')}</h3>
                        {p.name_en && p.name_en !== p.name && <p className="text-xs text-slate-500">{p.name_en}</p>}
                        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
                          <span className="size-2 rounded-full" style={{ background: KIND_COLOR[p.kind] }} aria-hidden />
                          {t(`hospitals.kinds.${p.kind}`)} · <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700">{t('hospitals.distance', { km: fmtKm(p.distance_km) })}</span>
                        </p>
                      </div>
                      </div>
                      {p.emergency && <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700"><ShieldPlus className="size-3.5" aria-hidden />{t('hospitals.emergency')}</span>}
                    </div>
                    {p.address && <p className="mt-2 text-sm text-slate-600">{p.address}</p>}
                    {p.opening_hours && <p className="mt-1 text-xs text-slate-500" dir="ltr">{t('hospitals.hours')}: {p.opening_hours}</p>}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {p.phone && <a onClick={(e) => e.stopPropagation()} href={`tel:${p.phone.split(';')[0].replace(/\s+/g, '')}`} className="inline-flex items-center gap-1.5 rounded-lg bg-mint-50 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-mint-100"><Phone className="size-3.5" aria-hidden />{t('hospitals.call')}</a>}
                      <a onClick={(e) => e.stopPropagation()} href={p.directions_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-100"><Navigation className="size-3.5" aria-hidden />{t('hospitals.directions')}</a>
                      {p.website && <a onClick={(e) => e.stopPropagation()} href={p.website.startsWith('http') ? p.website : `https://${p.website}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200"><Globe className="size-3.5" aria-hidden />{t('hospitals.website')}</a>}
                      <a onClick={(e) => e.stopPropagation()} href={p.osm_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 px-1 py-1.5 text-xs text-slate-400 hover:text-slate-600" aria-label="OpenStreetMap"><ExternalLink className="size-3.5" aria-hidden /></a>
                    </div>
                  </article>
                ))}
                <p className="text-xs text-slate-500">{t('hospitals.dataNote')}</p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
