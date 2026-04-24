/**
 * API Service
 * Handles all backend communication
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 minutes timeout for local Ollama inference
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Submit a query to the BI pipeline
 * @param {string} query - Natural language question
 * @param {string} llmMode - 'mock' or 'gemini'
 */
export async function submitQuery(query, llmMode = 'mock') {
  try {
    const { data } = await api.post('/query', {
      query,
      llm_mode: llmMode,
    });
    return data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data?.detail || `Server error: ${error.response.status}`);
    }
    if (error.request) {
      throw new Error('Cannot reach backend. Is it running on port 8000?');
    }
    throw new Error(error.message);
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
