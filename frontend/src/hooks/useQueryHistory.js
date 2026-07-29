import { useState, useCallback } from 'react';

const STORAGE_KEY = 'voice_bi_query_history';
const PINNED_KEY = 'voice_bi_pinned_queries';
const MAX_ITEMS = 20;

function load(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function loadHistory() {
  return load(STORAGE_KEY);
}

function saveHistory(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
}

function savePinned(items) {
  localStorage.setItem(PINNED_KEY, JSON.stringify(items));
}

/** Persist and retrieve past business questions in localStorage. */
export function useQueryHistory() {
  const [history, setHistory] = useState(loadHistory);
  const [pinned, setPinned] = useState(() => load(PINNED_KEY));

  const togglePin = useCallback((entry) => {
    setPinned(prev => {
      const exists = prev.some(p => p.query === entry.query);
      const next = exists
        ? prev.filter(p => p.query !== entry.query)
        : [{ id: entry.id ?? Date.now(), query: entry.query }, ...prev];
      savePinned(next);
      return next;
    });
  }, []);

  const addEntry = useCallback((entry) => {
    setHistory(prev => {
      const filtered = prev.filter(h => h.query !== entry.query);
      const next = [
        { id: Date.now(), at: new Date().toISOString(), ...entry },
        ...filtered,
      ].slice(0, MAX_ITEMS);
      saveHistory(next);
      return next;
    });
  }, []);

  const clearHistory = useCallback(() => {
    saveHistory([]);
    setHistory([]);
  }, []);

  const removeEntry = useCallback((id) => {
    setHistory(prev => {
      const next = prev.filter(h => h.id !== id);
      saveHistory(next);
      return next;
    });
  }, []);

  return { history, addEntry, clearHistory, removeEntry, pinned, togglePin };
}
