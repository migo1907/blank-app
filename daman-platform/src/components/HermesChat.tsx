import { useState, useEffect, useRef } from 'react';
import { Sparkles, Send, User, Trash2, MessageSquare, Mic } from 'lucide-react';
import { streamChat, ChatTurn } from '../services/aiChatService';
import { buildChatContext } from '../services/marketContext';

const STORAGE_KEY = 'hermes_chat_history';
const MAX_PERSISTED = 50; // keep history bounded

const SUGGESTED = [
  'What is the market tone today and why?',
  'Give me a swing-trade idea with risk levels.',
  'Analyze the risk in my current portfolio.',
  'What do rising yields mean for growth stocks?',
];

function loadHistory(): ChatTurn[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ChatTurn[]) : [];
  } catch {
    return [];
  }
}

/**
 * Reusable "Ask Hermes" chat. Streams Claude's reply (live typing), persists
 * history across sessions, and sends fresh market + portfolio context every turn
 * so follow-ups stay portfolio-aware.
 */
export default function HermesChat({ compact = false, seedPrompt }: { compact?: boolean; seedPrompt?: string }) {
  const [messages, setMessages] = useState<ChatTurn[]>(loadHistory);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const seededRef = useRef<string | null>(null);
  const recognitionRef = useRef<{ stop: () => void } | null>(null);
  const [listening, setListening] = useState(false);

  // Voice input via the Web Speech API (no backend). Feature-detected.
  const SpeechRecognition =
    typeof window !== 'undefined'
      ? (window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown }).SpeechRecognition ||
        (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition
      : undefined;
  const voiceSupported = Boolean(SpeechRecognition);

  const toggleVoice = () => {
    if (!voiceSupported) return;
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rec = new (SpeechRecognition as any)();
    rec.lang = 'en-US';
    rec.interimResults = true;
    rec.continuous = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = (e: any) => {
      const text = Array.from(e.results).map((r: any) => r[0].transcript).join('');
      setInput(text);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  };

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Persist (bounded) whenever the conversation changes and isn't mid-stream.
  useEffect(() => {
    if (streaming) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_PERSISTED)));
    } catch {
      /* ignore quota errors */
    }
  }, [messages, streaming]);

  useEffect(() => () => abortRef.current?.(), []);

  // Auto-send a seeded question (e.g. "Ask Hermes about AAPL") exactly once.
  useEffect(() => {
    if (seedPrompt && seedPrompt !== seededRef.current && !streaming) {
      seededRef.current = seedPrompt;
      send(seedPrompt);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedPrompt]);

  const clear = () => {
    abortRef.current?.();
    setStreaming(false);
    setMessages([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || streaming) return;
    setInput('');

    const history: ChatTurn[] = [...messages, { role: 'user', content }];
    setMessages([...history, { role: 'assistant', content: '' }]);
    setStreaming(true);

    const context = await buildChatContext();

    abortRef.current = streamChat(history, context, {
      onToken: (t) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: next[next.length - 1].content + t };
          return next;
        }),
      onDone: () => setStreaming(false),
      onError: (msg) => {
        setStreaming(false);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: `⚠️ ${msg}` };
          return next;
        });
      },
    });
  };

  return (
    <div className={`bg-white dark:bg-slate-800 flex flex-col ${compact ? 'h-full' : 'h-[70vh] rounded-xl border border-slate-200 dark:border-slate-700'}`}>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 p-3 rounded-xl mb-3">
              <MessageSquare className="h-7 w-7 text-white" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Ask Hermes anything</h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm mb-5 max-w-md">
              Tickers, macro, strategy, or your portfolio — fundamentals + technicals, streamed live.
            </p>
            <div className={`grid gap-2 w-full max-w-2xl ${compact ? 'grid-cols-1' : 'sm:grid-cols-2'}`}>
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-sm bg-slate-50 dark:bg-slate-900 hover:bg-daman-blue-50 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-slate-700 dark:text-slate-300 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${m.role === 'user' ? 'bg-slate-200 dark:bg-slate-700' : 'bg-gradient-to-br from-daman-blue-600 to-daman-blue-800'}`}>
              {m.role === 'user' ? <User className="h-4 w-4 text-slate-600 dark:text-slate-300" /> : <Sparkles className="h-4 w-4 text-white" />}
            </div>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
              m.role === 'user' ? 'bg-daman-blue-600 text-white' : 'bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200'
            }`}>
              {m.content || (streaming && i === messages.length - 1 ? <span className="inline-block animate-pulse">▍</span> : '')}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="border-t border-slate-200 dark:border-slate-700 p-3">
        <div className="flex gap-2 items-center">
          {messages.length > 0 && (
            <button
              onClick={clear}
              title="Clear conversation"
              className="shrink-0 p-2.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              aria-label="Clear conversation"
            >
              <Trash2 className="h-5 w-5" />
            </button>
          )}
          {voiceSupported && (
            <button
              onClick={toggleVoice}
              title={listening ? 'Stop listening' : 'Speak to Hermes'}
              aria-label="Voice input"
              className={`shrink-0 p-2.5 rounded-lg transition-colors ${
                listening
                  ? 'bg-rose-500 text-white animate-pulse'
                  : 'text-slate-400 hover:text-daman-blue-600 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
            >
              <Mic className="h-5 w-5" />
            </button>
          )}
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder={listening ? 'Listening…' : 'Ask Hermes…'}
            className="flex-1 px-4 py-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white focus:outline-none focus:border-daman-blue-500"
          />
          <button
            onClick={() => send(input)}
            disabled={streaming || !input.trim()}
            className="shrink-0 bg-daman-blue-600 hover:bg-daman-blue-700 disabled:opacity-50 text-white px-4 py-2.5 rounded-lg transition-colors"
            aria-label="Send"
          >
            <Send className="h-5 w-5" />
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mt-2 text-center">
          Hermes is an AI assistant. Educational only — not financial advice.
        </p>
      </div>
    </div>
  );
}
