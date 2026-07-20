import { type FC, useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SendHorizontal } from 'lucide-react'
import { ChatMessage, TypingIndicator } from '../components/ChatMessage'
import { useReducedMotion } from '../hooks/useReducedMotion'
import { postChat, type ChatMessage as ChatMsg, ApiError } from '../api/client'

const MAX_HISTORY = 20

export const Chat: FC = () => {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const reduced = useReducedMotion()

  useEffect(() => () => { abortRef.current?.abort() }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' })
  }, [messages, typing, reduced])

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || typing) return

    // Optimistic update — show user message immediately
    const userMsg: ChatMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setTyping(true)
    setError(null)

    abortRef.current?.abort()
    abortRef.current = new AbortController()

    try {
      const history = [...messages, userMsg].slice(-MAX_HISTORY)
      const res = await postChat(text, history, abortRef.current.signal)
      setMessages(prev => [...prev, { role: 'assistant', content: res.reply }])
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        const msg = err instanceof ApiError
          ? `Error ${err.status}: ${err.message}`
          : 'Could not reach the assistant. Check backend connection.'
        setError(msg)
        // Remove the optimistic user message on hard failure
        setMessages(prev => prev.slice(0, -1))
      }
    } finally {
      setTyping(false)
    }
  }, [input, messages, typing])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="chat">
      <motion.h1
        className="view-title"
        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        Chat
      </motion.h1>

      <div className="chat__window">
        <div className="chat__messages">
          {messages.length === 0 && !typing && (
            <div className="chat__empty">
              <p>Ask anything about your zones or analysis results.</p>
            </div>
          )}

          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <ChatMessage key={i} message={msg} />
            ))}
          </AnimatePresence>

          {typing && <TypingIndicator />}

          {error && (
            <motion.div
              className="chat__error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              {error}
            </motion.div>
          )}

          <div ref={bottomRef} />
        </div>

        <div className="chat__input-bar">
          <textarea
            className="chat__input"
            placeholder="Message…"
            rows={1}
            value={input}
            onChange={e => {
              setInput(e.target.value)
              // Auto-resize
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
            onKeyDown={handleKeyDown}
            disabled={typing}
            aria-label="Chat message input"
          />
          <button
            className="chat__send"
            onClick={sendMessage}
            disabled={!input.trim() || typing}
            aria-label="Send message"
          >
            <SendHorizontal size={16} strokeWidth={2} />
          </button>
        </div>
      </div>

      <style>{`
        .chat { display: flex; flex-direction: column; gap: 12px; height: 100%; }
        .chat__window {
          display: flex;
          flex-direction: column;
          flex: 1;
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          border-radius: var(--radius);
          overflow: hidden;
          min-height: 0;
        }
        .chat__messages {
          flex: 1;
          overflow-y: auto;
          padding: 20px 20px 12px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          min-height: 0;
        }
        .chat__empty {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--color-text-muted);
          font-size: 13px;
          text-align: center;
          padding: 40px;
        }
        .chat__error {
          align-self: center;
          font-size: 12px;
          color: var(--color-error);
          background: rgba(255,107,107,0.08);
          border: 1px solid rgba(255,107,107,0.2);
          border-radius: var(--radius-sm);
          padding: 8px 12px;
          max-width: 80%;
          text-align: center;
        }
        .chat__input-bar {
          display: flex;
          align-items: flex-end;
          gap: 8px;
          padding: 12px 16px;
          border-top: 1px solid var(--color-border);
          background: var(--color-surface);
        }
        .chat__input {
          flex: 1;
          padding: 9px 12px;
          resize: none;
          border-radius: var(--radius);
          max-height: 120px;
          overflow-y: auto;
          line-height: 1.5;
          font-size: 13.5px;
        }
        .chat__input:disabled { opacity: 0.6; }
        .chat__send {
          width: 36px;
          height: 36px;
          background: var(--color-accent);
          color: #fff;
          border-radius: var(--radius);
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          transition: opacity var(--transition-fast), transform var(--transition-fast);
        }
        .chat__send:hover:not(:disabled) { opacity: 0.85; transform: translateY(-1px); }
        .chat__send:disabled { opacity: 0.35; cursor: not-allowed; }
      `}</style>
    </div>
  )
}
