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
  }, [theme]);

  const toggleTheme = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'));

  return { theme, toggleTheme };
}
