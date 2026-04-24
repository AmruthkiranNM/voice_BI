/**
 * API Service
 * Handles all backend communication
 */
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 120000,
});

/**
 * Submit a query to the BI pipeline
 * @param {string} query - Natural language question
 */
export async function submitQuery(query) {
  try {
    const { data } = await api.post('/query', { query });
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

/**
 * Upload a CSV dataset
 * @param {File} file - CSV file object
 */
export async function uploadDataset(file) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const { data } = await axios.post('http://localhost:8000/api/upload', formData);
    return data;
  } catch (error) {
    const msg =
      error.response?.data?.detail ||
      error.message ||
      'Upload failed. Check backend connection.';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
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
