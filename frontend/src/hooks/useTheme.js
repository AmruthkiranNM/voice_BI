import { useEffect, useState } from 'react';

const STORAGE_KEY = 'voice_bi_theme';

function initialTheme() {
  return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
}

/** Persisted light/dark theme, applied via a `data-theme` attribute on <html> (see index.css). */
export function useTheme() {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    // Lets non-React consumers (e.g. ECharts option builders memoized outside
    // this hook) know the theme changed so they can recompute their colors.
    window.dispatchEvent(new CustomEvent('voice-bi-theme-change', { detail: theme }));
  }, [theme]);

  const toggleTheme = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'));

  return { theme, toggleTheme };
}

/** Re-renders the caller whenever the theme toggles — for consumers (like ECharts option builders) that read theme colors imperatively instead of via props. */
export function useThemeTick() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const onChange = () => setTick(t => t + 1);
    window.addEventListener('voice-bi-theme-change', onChange);
    return () => window.removeEventListener('voice-bi-theme-change', onChange);
  }, []);
  return tick;
}
