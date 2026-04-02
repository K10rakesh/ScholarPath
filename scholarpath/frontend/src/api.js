// frontend/src/api.js
// API service layer for ScholarPath backend

const API_BASE_URL = '';

/**
 * Upload a PDF file to the backend
 * @param {File} file - The PDF file to upload
 * @returns {Promise<{doc_id: string, status: string, file_name: string}>}
 */
export async function uploadPdf(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/upload-pdf`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

/**
 * Trigger the analysis pipeline for a document
 * @param {string} docId - The document ID
 * @returns {Promise<{doc_id: string, status: string, num_claims: number, num_references: number}>}
 */
export async function analyzeDocument(docId) {
  const response = await fetch(`${API_BASE_URL}/analyze/${docId}`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Analysis failed' }));
    throw new Error(error.detail || 'Analysis failed');
  }

  return response.json();
}

/**
 * Check the processing status of a document
 * @param {string} docId - The document ID
 * @returns {Promise<{doc_id: string, status: string}>}
 */
export async function getStatus(docId) {
  const response = await fetch(`${API_BASE_URL}/status/${docId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Status check failed' }));
    throw new Error(error.detail || 'Status check failed');
  }

  return response.json();
}

/**
 * Get the full results for a processed document
 * @param {string} docId - The document ID
 * @returns {Promise<Object>} - The parsed paper data
 */
export async function getResults(docId) {
  const response = await fetch(`${API_BASE_URL}/results/${docId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Results not found' }));
    throw new Error(error.detail || 'Results not found');
  }

  return response.json();
}

/**
 * Run the full pipeline (citation resolution + verification + roadmap)
 * @param {string} docId - The document ID
 * @returns {Promise<Object>} - The final report
 */
export async function runFullPipeline(docId) {
  const response = await fetch(`${API_BASE_URL}/full-pipeline/${docId}`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Pipeline failed' }));
    throw new Error(error.detail || 'Pipeline failed');
  }

  return response.json();
}

/**
 * Get the final report for a document
 * @param {string} docId - The document ID
 * @returns {Promise<Object>} - The final report
 */
export async function getFinalReport(docId) {
  const response = await fetch(`${API_BASE_URL}/final-report/${docId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Report not found' }));
    throw new Error(error.detail || 'Report not found');
  }

  return response.json();
}

/**
 * Poll for document status until it's done or error
 * @param {string} docId - The document ID
 * @param {number} intervalMs - Polling interval in milliseconds
 * @param {number} timeoutMs - Maximum time to wait
 * @returns {Promise<{doc_id: string, status: string}>}
 */
export async function pollStatus(docId, intervalMs = 2000, timeoutMs = 120000) {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    const status = await getStatus(docId);

    if (status.status === 'done' || status.status === 'success' || status.status === 'partial') {
      return status;
    }

    if (status.status === 'failed') {
      throw new Error('Document processing failed');
    }

    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  throw new Error('Processing timeout - document is still being processed');
}
