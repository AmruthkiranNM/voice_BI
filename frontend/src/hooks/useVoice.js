import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Browser speech-to-text for voice queries (Web Speech API).
 *
 * Supports interim (live) transcripts via onInterim, so the UI can show
 * words as they're spoken. Callbacks are held in a ref so the recognition
 * object is created once and never re-initialised on re-render.
 */
export function useVoiceInput({ onResult, onError, onInterim } = {}) {
  const [isListening, setIsListening] = useState(false);
  const [isSupported] = useState(() => {
    if (typeof window === 'undefined') return false;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    return !!SpeechRecognition;
  });
  const recognitionRef = useRef(null);
  const cbs = useRef({});

  useEffect(() => {
    cbs.current = { onResult, onError, onInterim };
  }, [onResult, onError, onInterim]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let finalText = '';
      let interimText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const seg = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += seg;
        else interimText += seg;
      }
      if (interimText) cbs.current.onInterim?.(interimText);
      if (finalText.trim()) cbs.current.onResult?.(finalText.trim());
    };

    recognition.onerror = (event) => {
      setIsListening(false);
      const messages = {
        'not-allowed': 'Microphone access denied. Allow microphone permission in your browser.',
        'no-speech': 'No speech detected. Please try again.',
        'network': 'Voice recognition requires an internet connection in some browsers.',
      };
      // "aborted"/"no-speech" are routine when stopping a hands-free loop —
      // don't surface them as errors.
      if (event.error !== 'aborted') {
        cbs.current.onError?.(messages[event.error] || `Voice error: ${event.error}`);
      }
    };

    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;

    return () => {
      recognition.abort();
    };
  }, []);

  const startListening = useCallback(() => {
    if (!recognitionRef.current || isListening) return;
    try {
      recognitionRef.current.start();
      setIsListening(true);
    } catch {
      // start() throws if already started — ignore.
    }
  }, [isListening]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  return { isListening, isSupported, startListening, stopListening };
}

/**
 * Text-to-speech for reading business insights and chat replies aloud.
 * speak() accepts an optional onEnd callback so callers can chain actions
 * (e.g. re-open the mic for a hands-free conversation loop).
 */
export function useSpeechOutput() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const utteranceRef = useRef(null);

  const isSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const speak = useCallback((text, { onEnd } = {}) => {
    if (!isSupported || !text?.trim()) {
      onEnd?.();
      return;
    }

    window.speechSynthesis.cancel();
    // Strip markdown so "**" / list markers aren't read aloud.
    const spoken = text.replace(/\*\*/g, '').replace(/^\s*\d+\.\s/gm, '');
    const utterance = new SpeechSynthesisUtterance(spoken);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.lang = 'en-US';

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => { setIsSpeaking(false); onEnd?.(); };
    utterance.onerror = () => { setIsSpeaking(false); onEnd?.(); };

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, [isSupported]);

  const stop = useCallback(() => {
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
  }, []);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  return { speak, stop, isSpeaking, isSupported };
}
