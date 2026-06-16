import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Text-to-speech via the browser's Web Speech API (free, no backend).
 * Returns play/pause/stop controls and the current speaking state.
 * Gracefully reports unsupported environments.
 */
export function useSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const [paused, setPaused] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const supported =
    typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
    setPaused(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || !text) return;
      window.speechSynthesis.cancel();

      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1.0;
      u.pitch = 1.0;
      // Prefer a natural English voice when available.
      const voices = window.speechSynthesis.getVoices();
      const preferred =
        voices.find((v) => /en-US/i.test(v.lang) && /natural|google|samantha|aria/i.test(v.name)) ||
        voices.find((v) => /en-US/i.test(v.lang)) ||
        voices.find((v) => /^en/i.test(v.lang));
      if (preferred) u.voice = preferred;

      u.onend = () => { setSpeaking(false); setPaused(false); };
      u.onerror = () => { setSpeaking(false); setPaused(false); };

      utteranceRef.current = u;
      window.speechSynthesis.speak(u);
      setSpeaking(true);
      setPaused(false);
    },
    [supported]
  );

  const pause = useCallback(() => {
    if (!supported || !speaking) return;
    window.speechSynthesis.pause();
    setPaused(true);
  }, [supported, speaking]);

  const resume = useCallback(() => {
    if (!supported || !paused) return;
    window.speechSynthesis.resume();
    setPaused(false);
  }, [supported, paused]);

  // Stop narration if the component unmounts.
  useEffect(() => () => { if (supported) window.speechSynthesis.cancel(); }, [supported]);

  return { supported, speaking, paused, speak, pause, resume, stop };
}
