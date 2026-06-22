/**
 * API Service — backend communication for Voice BI
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Submit a business question to the analysis pipeline
 */
export async function submitQuery(query, options = {}) {
  const {
    model = null,
    tableName = null,
    cacheMode = true,
    fastMode = false,
    skipInsight = false,
  } = options;

  try {
    const { data } = await api.post('/query', {
      query,
      model: model || null,
      table_name: tableName || null,
      cache_mode: cacheMode,
      fast_mode: fastMode,
      skip_insight: skipInsight,
    });
    return data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data?.detail || `Server error: ${error.response.status}`, { cause: error });
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

/** Get uploaded datasets and tailored suggestions */
export async function getDatasets() {
  try {
    const { data } = await api.get('/datasets');
    return data;
  } catch {
    return { has_data: false, tables: [], suggestions: [] };
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
