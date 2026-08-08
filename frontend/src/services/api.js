/**
 * API Service — backend communication for Voice BI
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
  headers: { 'Content-Type': 'application/json' },
});

const TOKEN_KEY = 'voice_bi_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

api.interceptors.request.use(config => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// A session that's expired or been revoked server-side should drop the user
// back to the login screen instead of showing confusing per-request errors.
api.interceptors.response.use(
  res => res,
  error => {
    if (error.response?.status === 401) {
      setToken(null);
      window.dispatchEvent(new CustomEvent('auth:logout'));
    }
    return Promise.reject(error);
  },
);

/** Register a new account */
export async function register(email, password) {
  try {
    const { data } = await api.post('/auth/register', { email, password });
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Registration failed.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Log in with an existing account */
export async function login(email, password) {
  try {
    const { data } = await api.post('/auth/login', { email, password });
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Login failed.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/**
 * Submit a business question to the analysis pipeline
 */
export async function submitQuery(query, options = {}) {
  const {
    model = null,
    tableName = null,
    tableNames = null,
    cacheMode = true,
    fastMode = false,
    skipInsight = false,
  } = options;

  try {
    const { data } = await api.post('/query', {
      query,
      model: model || null,
      table_name: tableName || null,
      table_names: tableNames && tableNames.length ? tableNames : null,
      cache_mode: cacheMode,
      fast_mode: fastMode,
      skip_insight: skipInsight,
    });
    return data;
  } catch (error) {
    if (error.response) {
      const detail = error.response.data?.detail;
      let errMsg = `Server error: ${error.response.status}`;
      if (typeof detail === 'string') {
        errMsg = detail;
      } else if (Array.isArray(detail)) {
        errMsg = `Validation failed: ${detail.map(d => `${d.loc?.join('.') || 'field'}: ${d.msg}`).join(' | ')}`;
      } else if (typeof detail === 'object' && detail !== null) {
        errMsg = JSON.stringify(detail);
      }
      throw new Error(errMsg, { cause: error });
    }
    if (error.request) {
      throw new Error('Cannot reach backend. Is it running on port 8000?', { cause: error });
    }
    throw new Error(error.message, { cause: error });
  }
}

/** Upload a business CSV dataset */
export async function uploadDataset(file) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const { data } = await api.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  } catch (error) {
    const msg =
      error.response?.data?.detail ||
      error.message ||
      'Upload failed. Check backend connection.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Ask a conversational follow-up about an existing query result */
export async function sendChatMessage(message, { query, sql, result, insight, history = [], model = null, tableName = null, tableNames = null } = {}) {
  try {
    const { data } = await api.post('/chat', {
      message,
      query,
      sql: sql || null,
      result,
      insight: insight || null,
      history: history.map(h => ({ role: h.role, content: h.content })),
      model: model || null,
      table_name: tableName || null,
      table_names: tableNames && tableNames.length ? tableNames : null,
    });
    return data;
  } catch (error) {
    if (error.response) {
      const detail = error.response.data?.detail;
      let errMsg = `Server error: ${error.response.status}`;
      if (typeof detail === 'string') {
        errMsg = detail;
      } else if (Array.isArray(detail)) {
        errMsg = `Validation failed: ${detail.map(d => `${d.loc?.join('.') || 'field'}: ${d.msg}`).join(' | ')}`;
      } else if (typeof detail === 'object' && detail !== null) {
        errMsg = JSON.stringify(detail);
      }
      throw new Error(errMsg, { cause: error });
    }
    if (error.request) {
      throw new Error('Cannot reach backend. Is it running on port 8000?', { cause: error });
    }
    throw new Error(error.message, { cause: error });
  }
}

/** Autonomously drill into why an already-answered query's result looks the way it does */
export async function investigateQuery(query, { sql, result, model = null, tableNames = null } = {}) {
  try {
    const { data } = await api.post('/investigate', {
      query,
      sql: sql || null,
      result,
      model: model || null,
      table_names: tableNames && tableNames.length ? tableNames : null,
    });
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Investigation failed.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Get uploaded datasets and tailored suggestions */
export async function getDatasets() {
  try {
    const { data } = await api.get('/datasets');
    return data;
  } catch {
    return { has_data: false, tables: [], suggestions: [] };
  }
}

/** Sample rows + a fresh quality report for one already-ingested table */
export async function getTablePreview(tableName) {
  const { data } = await api.get(`/datasets/${encodeURIComponent(tableName)}/preview`);
  return data;
}

/** Remove one uploaded table from the workspace */
export async function deleteDataset(tableName) {
  try {
    const { data } = await api.delete(`/datasets/${encodeURIComponent(tableName)}`);
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Failed to remove table.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Test a Postgres-compatible connection string and list its tables */
export async function testDbConnection(connectionString) {
  try {
    const { data } = await api.post('/connections/test', { connection_string: connectionString });
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Connection failed.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Import selected tables from a connected external database */
export async function importDbTables(connectionString, tables) {
  try {
    const { data } = await api.post('/connections/import', { connection_string: connectionString, tables });
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Import failed.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Remove an entire data source (all its tables) */
export async function deleteSource(sourceId) {
  try {
    const { data } = await api.delete(`/sources/${encodeURIComponent(sourceId)}`);
    return data;
  } catch (error) {
    const msg = error.response?.data?.detail || error.message || 'Failed to remove source.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg), { cause: error });
  }
}

/** Clear server-side query cache */
export async function clearCache() {
  try {
    const { data } = await api.delete('/cache');
    return data;
  } catch {
    return { success: false };
  }
}

/** Health check */
export async function checkHealth() {
  try {
    const { data } = await api.get('/health');
    return data;
  } catch {
    return { status: 'offline' };
  }
}

/** Fetch available local Ollama models */
export async function getModels() {
  try {
    const { data } = await api.get('/models');
    return data.models || [];
  } catch {
    return [];
  }
}
