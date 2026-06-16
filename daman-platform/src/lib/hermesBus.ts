// Tiny global event bus so any component can pop open the floating "Ask Hermes"
// chat with a pre-seeded question (e.g. "Ask Hermes about AAPL").

const EVENT = 'hermes:open';

export function askHermes(prompt: string) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { prompt } }));
}

export function onAskHermes(handler: (prompt: string) => void): () => void {
  const listener = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail?.prompt) handler(detail.prompt);
  };
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
