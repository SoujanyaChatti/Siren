import { useRef, useState } from 'react'
import { apiUrl } from '../api'

/** Speech-to-text: browser Web Speech API (Chrome) first, Groq Whisper on the backend as fallback. */
export function useSpeech(lang: 'en' | 'es', onText: (t: string) => void) {
  const [listening, setListening] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)

  const start = async () => {
    setErr(null)
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (SR) {
      const r = new SR()
      r.lang = lang === 'es' ? 'es-US' : 'en-US'
      r.interimResults = false
      r.maxAlternatives = 1
      r.onresult = (e: any) => onText(e.results[0][0].transcript)
      r.onerror = (e: any) => setErr(e.error === 'network' ? 'Speech service unavailable — type instead' : e.error)
      r.onend = () => setListening(false)
      setListening(true)
      r.start()
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => chunks.push(e.data)
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setListening(false)
        const fd = new FormData()
        fd.append('audio', new Blob(chunks, { type: rec.mimeType }), 'q.webm')
        fd.append('language', lang)
        const res = await fetch(apiUrl('/api/transcribe'), { method: 'POST', body: fd })
        if (res.ok) onText((await res.json()).text)
        else setErr('Voice input unavailable — please type your question')
      }
      recRef.current = rec
      rec.start()
      setListening(true)
      window.setTimeout(() => rec.state === 'recording' && rec.stop(), 6000)
    } catch {
      setErr('Microphone unavailable — please type your question')
    }
  }
  const stop = () => recRef.current?.state === 'recording' && recRef.current.stop()
  return { listening, err, start, stop }
}

/** Plays a cached ElevenLabs clip; falls back to the browser voice so the alert is never silent. */
export function speak(text: string, lang: 'en' | 'es', audioUrl: string | null): HTMLAudioElement | null {
  if (audioUrl) {
    const a = new Audio(apiUrl(audioUrl))
    a.play().catch(() => browserSpeak(text, lang))
    return a
  }
  browserSpeak(text, lang)
  return null
}

function browserSpeak(text: string, lang: 'en' | 'es') {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.lang = lang === 'es' ? 'es-US' : 'en-US'
  u.rate = 0.95
  window.speechSynthesis.speak(u)
}

/** Generate (or reuse a cached) ElevenLabs clip only when someone taps Play; browser voice otherwise. */
export async function speakOnDemand(text: string, lang: 'en' | 'es'): Promise<'elevenlabs' | 'browser'> {
  try {
    const r = await fetch(apiUrl('/api/tts'), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, language: lang }) })
    const v = r.ok ? await r.json() : null
    speak(text, lang, v?.audio_url ?? null)
    return v?.audio_url ? 'elevenlabs' : 'browser'
  } catch {
    speak(text, lang, null)
    return 'browser'
  }
}
