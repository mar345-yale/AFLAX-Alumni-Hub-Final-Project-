import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent, ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, rankAbbr } from '../api'
import type { ChatMessage, IntroEmail, MentorCard } from '../api'
import { useAuth } from '../useAuth'
import Avatar from '../components/Avatar'

const CADET_STARTERS = [
  "I'm a sophomore and have no idea which AFSC fits me. Where do I start?",
  'What is pilot training really like, and who can I talk to?',
  'Compare Space Operations and Cyberspace Operations for me.',
  'What are the pros and cons of Hill AFB?',
]
const ALUMNI_STARTERS = [
  'How many AFLAX alumni are developmental engineers, and where are they?',
  'Which bases have the most AFLAX alumni right now?',
  'What should I tell a cadet who is torn between Intel and Acquisition?',
  'Tell me about life at Ramstein AB.',
]

// Light formatting for agent replies: paragraphs, bullet/numbered lists, **bold**.
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
  )
}

function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let list: string[] = []
  let ordered = false
  const flush = () => {
    if (!list.length) return
    const items = list.map((l, i) => <li key={i}>{inline(l)}</li>)
    blocks.push(ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>)
    list = []
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    const numbered = line.match(/^\d+[.)]\s+(.*)$/)
    if (bullet || numbered) {
      if (list.length && ordered !== Boolean(numbered)) flush()
      ordered = Boolean(numbered)
      list.push((bullet ?? numbered)![1])
      continue
    }
    flush()
    if (line) blocks.push(<p key={blocks.length}>{inline(line.replace(/^#+\s*/, ''))}</p>)
  }
  flush()
  return <>{blocks}</>
}

function MentorCards({ mentors }: { mentors: MentorCard[] }) {
  if (!mentors.length) return null
  return (
    <div className="mentor-cards">
      {mentors.map((m) => (
        <article key={m.id} className="mentor-card">
          <header>
            <Avatar first={m.first_name} last={m.last_name} photo={m.photo_url} size={44} />
            <div>
              <strong>{m.rank && m.status !== 'Civilian' ? `${rankAbbr[m.rank] ?? m.rank} ` : ''}{m.first_name} {m.last_name}</strong>
              <small>Class of {m.grad_year} · {m.status}</small>
            </div>
          </header>
          <p className="mentor-job">{m.job || m.afsc_title}</p>
          <p className="muted small">
            {m.afsc && <>{m.afsc} · {m.afsc_title}<br /></>}
            {m.location}
          </p>
          <div className="mentor-contact">
            <a className="btn btn-primary btn-sm" href={`mailto:${m.email}`}>Email</a>
            {m.phone && <a className="btn btn-outline btn-sm" href={`tel:${m.phone.replace(/[^\d+]/g, '')}`}>{m.phone}</a>}
          </div>
        </article>
      ))}
    </div>
  )
}

function IntroEmailCard({ intro }: { intro: IntroEmail }) {
  const [copied, setCopied] = useState(false)
  const mailto = `mailto:${intro.to}?subject=${encodeURIComponent(intro.subject)}&body=${encodeURIComponent(intro.body)}`
  async function copy() {
    await navigator.clipboard.writeText(`Subject: ${intro.subject}\n\n${intro.body}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <div className="intro-card">
      <div className="intro-head">
        <span>✉️ Draft intro email</span>
        <small>To: {intro.to}</small>
      </div>
      <p className="intro-subject"><strong>Subject:</strong> {intro.subject}</p>
      <pre className="intro-body">{intro.body}</pre>
      <div className="intro-actions">
        <a className="btn btn-primary btn-sm" href={mailto}>Open in email app</a>
        <button className="btn btn-outline btn-sm" onClick={copy}>{copied ? 'Copied!' : 'Copy text'}</button>
      </div>
    </div>
  )
}

export default function Mentorship() {
  const { user } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [params] = useSearchParams()
  // "Ask Falcon Mentor" links from the Explorer pre-fill (but don't send) a question.
  const [input, setInput] = useState(() => params.get('q') ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const starters = user?.status === 'Cadet' ? CADET_STARTERS : ALUMNI_STARTERS

  useEffect(() => {
    api.chatHistory()
      .then(setMessages)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoaded(true))
  }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  async function send(text: string) {
    const message = text.trim()
    if (!message || busy) return
    setError('')
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: message, mentors: [], intro_email: null }])
    setBusy(true)
    try {
      const res = await api.chat(message)
      setMessages((m) => [...m, { role: 'assistant', content: res.reply, mentors: res.mentors, intro_email: res.intro_email }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setMessages((m) => m.slice(0, -1))
      setInput(message)
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    send(input)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  async function newConversation() {
    if (!confirm('Start a new conversation? Your current chat will be cleared.')) return
    await api.resetChat().catch(() => undefined)
    setMessages([])
  }

  return (
    <div className="page mentor-page">
      <header className="page-head mentor-head">
        <div>
          <p className="eyebrow">Cadet Mentorship</p>
          <h1>Falcon Mentor</h1>
          <p className="muted">
            Ask about any AFSC or base. Falcon Mentor answers using official career-field descriptions and our base guide, then
            connects you with AFLAX alumni who've been there.
          </p>
        </div>
        {messages.length > 0 && <button className="btn btn-ghost btn-sm" onClick={newConversation}>New conversation</button>}
      </header>

      <div className="chat card">
        <div className="chat-log" aria-live="polite">
          {loaded && messages.length === 0 && (
            <div className="chat-welcome">
              <div className="chat-welcome-logo"><img src="/afa-bird.png" alt="" /></div>
              <h3>Hey {user?.first_name}, how can I help?</h3>
              <p className="muted">Try one of these to get started:</p>
              <div className="starters">
                {starters.map((s) => (
                  <button key={s} className="starter" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg msg-${m.role}`}>
              {m.role === 'assistant' && <div className="msg-avatar"><img src="/afa-bird.png" alt="" /></div>}
              <div className="msg-body">
                <div className="bubble">{m.role === 'assistant' ? <RichText text={m.content} /> : m.content}</div>
                <MentorCards mentors={m.mentors} />
                {m.intro_email && <IntroEmailCard intro={m.intro_email} />}
              </div>
            </div>
          ))}
          {busy && (
            <div className="msg msg-assistant">
              <div className="msg-avatar"><img src="/afa-bird.png" alt="" /></div>
              <div className="bubble typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {error && <div className="alert alert-error chat-error">{error}</div>}

        <form className="chat-input" onSubmit={onSubmit}>
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            maxLength={2000}
            placeholder="Ask about an AFSC, a base, or who to talk to…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={busy}
          />
          <button className="btn btn-gold" disabled={busy || !input.trim()}>Send</button>
        </form>
      </div>
      <p className="muted small center">
        Falcon Mentor is an AI guide. Confirm official details like training timelines and commitments with your AOC or AFPC.
      </p>
    </div>
  )
}
