import { useState } from 'react';
import { TbLoader2 } from 'react-icons/tb';
import { login, register } from '../services/api';

export default function LoginPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login'); // 'login' or 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const action = mode === 'login' ? login : register;
      const data = await action(email.trim(), password);
      onAuthenticated(data.token, data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm surface-card p-8">
        <h1 className="font-serif text-2xl text-zinc-100 text-center mb-1">Voice BI</h1>
        <p className="text-sm text-zinc-500 text-center mb-6">
          {mode === 'login' ? 'Log in to your workspace' : 'Create your workspace'}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="text-sm text-zinc-400 block mb-1.5">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoComplete="email"
              className="w-full bg-[#F7F3EA] border border-black/10 rounded-lg px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-[#9C4A2A]/50 transition-colors"
              placeholder="you@business.com"
            />
          </label>

          <label className="block">
            <span className="text-sm text-zinc-400 block mb-1.5">Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className="w-full bg-[#F7F3EA] border border-black/10 rounded-lg px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-[#9C4A2A]/50 transition-colors"
              placeholder="••••••••"
            />
          </label>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={isLoading}
            className="btn-primary w-full py-2.5 rounded-full text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading && <TbLoader2 className="w-4 h-4 animate-spin" />}
            {mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null); }}
          className="w-full text-center text-sm text-zinc-500 hover:text-[#9C4A2A] transition-colors mt-5"
        >
          {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Log in'}
        </button>
      </div>
    </div>
  );
}
