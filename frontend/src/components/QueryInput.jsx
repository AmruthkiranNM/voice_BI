/**
 * QueryInput — Search bar with suggestion chips
 */
import { useState } from 'react';

const SUGGESTIONS = [
  'Show total sales',
  'Top 5 customers by revenue',
  'Sales by region this year',
  'Monthly sales trend',
  'Best selling products',
  'Revenue by product category',
];

export default function QueryInput({ onSubmit, isLoading }) {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isLoading) onSubmit(query.trim());
  };

  return (
    <div className="fade-up">
      {/* Search Bar */}
      <form onSubmit={handleSubmit}
        className="bg-card border border-border rounded-2xl p-5 flex gap-4 items-center
                   hover:border-border-hover transition-colors duration-200">
        <svg className="w-5 h-5 text-text-muted flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          id="query-input"
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ask a business question in natural language..."
          disabled={isLoading}
          className="flex-1 bg-transparent text-base text-text-primary placeholder:text-text-muted
                     outline-none disabled:opacity-50"
        />
        <button
          id="submit-btn"
          type="submit"
          disabled={!query.trim() || isLoading}
          className="px-6 py-2.5 rounded-xl text-sm font-bold text-white
                     bg-indigo hover:bg-indigo-light
                     disabled:opacity-30 disabled:cursor-not-allowed
                     transition-all duration-200 flex items-center gap-2 whitespace-nowrap"
        >
          {isLoading ? (
            <>
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" className="opacity-75" />
              </svg>
              Running...
            </>
          ) : (
            <>Analyze</>
          )}
        </button>
      </form>

      {/* Suggestion Chips */}
      <div className="flex flex-wrap gap-2 mt-4 px-2">
        <span className="text-[11px] text-text-muted self-center mr-1 font-medium">Try:</span>
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            onClick={() => { setQuery(s); if (!isLoading) onSubmit(s); }}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-lg text-xs text-text-secondary
                       bg-card border border-border
                       hover:text-indigo hover:border-indigo/40
                       disabled:opacity-30 transition-all duration-200"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
