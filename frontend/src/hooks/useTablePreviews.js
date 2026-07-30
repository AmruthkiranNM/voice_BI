import { useEffect, useState } from 'react';
import { getTablePreview } from '../services/api';

/**
 * Fetches sample rows + a quality report for every table name given, in
 * parallel, so the Data Source and Data Quality views can show every
 * imported table instead of just the last one uploaded.
 */
export function useTablePreviews(tableNames) {
  const [previews, setPreviews] = useState({});
  const [loading, setLoading] = useState(false);
  const key = tableNames.join('|');

  useEffect(() => {
    if (!tableNames.length) {
      setPreviews({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all(
      tableNames.map(name =>
        getTablePreview(name)
          .then(data => [name, data])
          .catch(() => [name, null]),
      ),
    ).then(entries => {
      if (cancelled) return;
      setPreviews(Object.fromEntries(entries));
      setLoading(false);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { previews, loading };
}
