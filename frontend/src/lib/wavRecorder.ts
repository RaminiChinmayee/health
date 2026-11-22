/**
 * Microphone recorder that produces 16-bit PCM WAV in the browser (no server-side transcoding).
 * targetRate: resample to this rate (16 kHz for speech recognition); omit to keep the device rate
 * (needed for voice-quality analysis).
 */
export type RecorderError = 'permission_denied' | 'no_microphone' | 'unsupported' | 'unknown'

export class WavRecorder {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private node: ScriptProcessorNode | null = null
  private chunks: Float32Array[] = []
  private rate = 44100
  level = 0 // 0..1, for a live input meter

  static supported(): boolean {
    return typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && !!(window.AudioContext || (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext)
  }

  async start(): Promise<void> {
    if (!WavRecorder.supported()) throw new Error('unsupported' satisfies RecorderError)
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: false } })
    } catch (e) {
      const name = (e as DOMException)?.name
      throw new Error((name === 'NotAllowedError' || name === 'SecurityError' ? 'permission_denied' : name === 'NotFoundError' ? 'no_microphone' : 'unknown') satisfies RecorderError)
    }
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    this.ctx = new Ctx()
    this.rate = this.ctx.sampleRate
    const src = this.ctx.createMediaStreamSource(this.stream)
    this.node = this.ctx.createScriptProcessor(4096, 1, 1)
    this.chunks = []
    this.node.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0)
      this.chunks.push(new Float32Array(data))
      let peak = 0
      for (let i = 0; i < data.length; i += 16) peak = Math.max(peak, Math.abs(data[i]))
      this.level = peak
    }
    src.connect(this.node)
    this.node.connect(this.ctx.destination)
  }

  /** Stop and return a WAV blob, plus its duration in seconds. */
  async stop(targetRate?: number): Promise<{ blob: Blob; seconds: number }> {
    this.node?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    await this.ctx?.close()
    const total = this.chunks.reduce((n, c) => n + c.length, 0)
    const pcm = new Float32Array(total)
    let off = 0
    for (const c of this.chunks) {
      pcm.set(c, off)
      off += c.length
    }
    const out = targetRate && targetRate < this.rate ? resample(pcm, this.rate, targetRate) : pcm
    const rate = targetRate && targetRate < this.rate ? targetRate : this.rate
    this.chunks = []
    return { blob: encodeWav(out, rate), seconds: out.length / rate }
  }

  cancel() {
    this.node?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.ctx?.close().catch(() => {})
    this.chunks = []
  }
}

function resample(input: Float32Array, from: number, to: number): Float32Array {
  const ratio = from / to
  const out = new Float32Array(Math.floor(input.length / ratio))
  for (let i = 0; i < out.length; i++) {
    // Average the source samples that map to this output sample (simple anti-aliasing).
    const start = Math.floor(i * ratio)
    const end = Math.min(input.length, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    out[i] = sum / Math.max(1, end - start)
  }
  return out
}

function encodeWav(samples: Float32Array, rate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2)
  const v = new DataView(buf)
  const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)))
  str(0, 'RIFF')
  v.setUint32(4, 36 + samples.length * 2, true)
  str(8, 'WAVE')
  str(12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true) // PCM
  v.setUint16(22, 1, true) // mono
  v.setUint32(24, rate, true)
  v.setUint32(28, rate * 2, true)
  v.setUint16(32, 2, true)
  v.setUint16(34, 16, true)
  str(36, 'data')
  v.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buf], { type: 'audio/wav' })
}
