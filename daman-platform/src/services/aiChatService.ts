// Streaming client for the "Ask Hermes" chat (ai-chat edge function).
// Reads the plain-text token stream and invokes onToken for each chunk so the
// UI can render a live typing effect.

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

const FN_URL = () => {
  const base = import.meta.env.VITE_SUPABASE_URL;
  return base ? `${base}/functions/v1/ai-chat` : null;
};

export interface StreamHandlers {
  onToken: (text: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

/**
 * Streams an assistant reply. Returns a function to abort the stream.
 * Falls back to a clear message if the backend isn't configured.
 */
export function streamChat(
  messages: ChatTurn[],
  context: unknown,
  handlers: StreamHandlers
): () => void {
  const url = FN_URL();
  const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
  const controller = new AbortController();

  if (!url || !key) {
    handlers.onToken(
      "Ask Hermes runs on Claude via your backend. Connect Supabase and set ANTHROPIC_API_KEY to chat live. " +
        "(This is a demo placeholder reply.)"
    );
    handlers.onDone?.();
    return () => {};
  }

  (async () => {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, context }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        handlers.onError?.(`Chat service error (${res.status}).`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        handlers.onToken(decoder.decode(value, { stream: true }));
      }
      handlers.onDone?.();
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        handlers.onError?.(`Could not reach the chat service: ${(e as Error).message}`);
      }
    }
  })();

  return () => controller.abort();
}
