import type { FC } from 'react'
import { motion } from 'framer-motion'
import type { ChatMessage as ChatMsg } from '../api/client'
import { useReducedMotion } from '../hooks/useReducedMotion'

interface Props {
  message: ChatMsg
}

export const ChatMessage: FC<Props> = ({ message }) => {
  const reduced = useReducedMotion()
  const isUser = message.role === 'user'

  return (
    <motion.div
      className={`chat-msg chat-msg--${message.role}`}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 260, damping: 20 }}
    >
      <div className="chat-msg__label">{isUser ? 'You' : 'Assistant'}</div>
      <div className="chat-msg__bubble">
        {message.content}
      </div>

      <style>{`
        .chat-msg {
          display: flex;
          flex-direction: column;
          gap: 4px;
          max-width: 82%;
        }

        .chat-msg--user {
          align-self: flex-end;
          align-items: flex-end;
        }

        .chat-msg--assistant {
          align-self: flex-start;
          align-items: flex-start;
        }

        .chat-msg__label {
          font-size: 11px;
          font-weight: 600;
          color: var(--color-text-muted);
          letter-spacing: 0.04em;
          text-transform: uppercase;
          padding: 0 2px;
        }

        .chat-msg__bubble {
          padding: 10px 14px;
          border-radius: var(--radius);
          font-size: 13.5px;
          line-height: 1.6;
          white-space: pre-wrap;
          word-break: break-word;
        }

        .chat-msg--user .chat-msg__bubble {
          background: rgba(108,111,209,0.14);
          border: 1px solid rgba(108,111,209,0.25);
          color: var(--color-text);
        }

        .chat-msg--assistant .chat-msg__bubble {
          background: var(--color-card);
          border: 1px solid var(--color-border-strong);
          color: var(--color-text);
        }
      `}</style>
    </motion.div>
  )
}

export const TypingIndicator: FC = () => (
  <div className="typing">
    <div className="typing__label">Assistant</div>
    <div className="typing__bubble">
      <span /><span /><span />
    </div>
    <style>{`
      .typing {
        display: flex;
        flex-direction: column;
        gap: 4px;
        align-self: flex-start;
      }
      .typing__label {
        font-size: 11px;
        font-weight: 600;
        color: var(--color-text-muted);
        letter-spacing: 0.04em;
        text-transform: uppercase;
        padding: 0 2px;
      }
      .typing__bubble {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 12px 16px;
        background: var(--color-card);
        border: 1px solid var(--color-border-strong);
        border-radius: var(--radius);
      }
      .typing__bubble span {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--color-text-muted);
        display: block;
        animation: typing-dot 1.2s ease-in-out infinite;
      }
      .typing__bubble span:nth-child(2) { animation-delay: 0.2s; }
      .typing__bubble span:nth-child(3) { animation-delay: 0.4s; }
      @keyframes typing-dot {
        0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
        30% { opacity: 1; transform: translateY(-3px); }
      }
    `}</style>
  </div>
)
