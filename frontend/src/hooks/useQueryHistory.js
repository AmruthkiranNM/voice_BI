import { useState, useCallback } from 'react';

const STORAGE_KEY = 'voice_bi_query_history';
const MAX_ITEMS = 20;

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
}

/** Persist and retrieve past business questions in localStorage. */
export function useQueryHistory() {
  const [history, setHistory] = useState(loadHistory);

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

  return { history, addEntry, clearHistory, removeEntry };
}
