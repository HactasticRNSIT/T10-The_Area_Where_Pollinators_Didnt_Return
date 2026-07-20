import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageCircle, X, Send, Bot, User } from 'lucide-react';
import { API_KEY } from '../api/client';

interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
}

export function Chatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 'msg-1', sender: 'bot', text: "Hi! I'm your Agri-Bot. Ask me about pollination, pesticide stress, or climate adaptations." }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) scrollToBottom();
  }, [messages, isOpen]);

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputValue.trim()) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text: inputValue.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsTyping(true);

    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const response = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({ message: userMessage.text })
      });

      if (!response.ok) throw new Error('API Error');

      const data = await response.json();
      
      // Artificial delay for better UX
      setTimeout(() => {
        setMessages((prev) => [
          ...prev, 
          { id: `msg-${Date.now()}`, sender: 'bot', text: data.reply }
        ]);
        setIsTyping(false);
      }, 600);

    } catch (err) {
      setTimeout(() => {
        setMessages((prev) => [
          ...prev, 
          { id: `msg-${Date.now()}`, sender: 'bot', text: "Sorry, I'm having trouble connecting right now." }
        ]);
        setIsTyping(false);
      }, 600);
    }
  };

  return (
    <>
      <AnimatePresence>
        {!isOpen && (
          <motion.button
            key="fab"
            className="chatbot-fab"
            onClick={() => setIsOpen(true)}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 260, damping: 20 }}
            aria-label="Open chat"
          >
            <MessageCircle size={28} color="#fff" />
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="chat-window"
            className="chat-window glass-panel"
            initial={{ opacity: 0, y: 50, scale: 0.9, transformOrigin: 'bottom right' }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 50, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
          >
            <div className="chat-header">
              <div className="chat-header-info">
                <div className="chat-avatar"><Bot size={20} /></div>
                <div>
                  <h3>Agri-Bot</h3>
                  <span className="chat-status"><span className="status-dot online"></span> Online</span>
                </div>
              </div>
              <button className="chat-close-btn" onClick={() => setIsOpen(false)} aria-label="Close chat">
                <X size={20} />
              </button>
            </div>

            <div className="chat-body scrollable-area">
              {messages.map((msg, idx) => (
                <motion.div 
                  key={msg.id} 
                  className={`chat-message-wrapper ${msg.sender}`}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx === messages.length - 1 ? 0.1 : 0 }}
                >
                  {msg.sender === 'bot' && <div className="chat-bubble-avatar"><Bot size={16}/></div>}
                  <div className={`chat-bubble ${msg.sender}`}>
                    {msg.text}
                  </div>
                  {msg.sender === 'user' && <div className="chat-bubble-avatar"><User size={16}/></div>}
                </motion.div>
              ))}
              
              {isTyping && (
                <motion.div 
                  className="chat-message-wrapper bot"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <div className="chat-bubble-avatar"><Bot size={16}/></div>
                  <div className="chat-bubble bot typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </motion.div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form className="chat-input-area" onSubmit={handleSendMessage}>
              <input
                type="text"
                placeholder="Ask a question..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                disabled={isTyping}
              />
              <button 
                type="submit" 
                className="chat-send-btn" 
                disabled={!inputValue.trim() || isTyping}
                aria-label="Send message"
              >
                <Send size={18} />
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
