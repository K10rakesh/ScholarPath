// =============================================================================
// frontend/src/api.js
// =============================================================================
// WHAT THIS FILE DOES (Overall):
//   Service layer that encapsulates every HTTP call from the React frontend
//   to the FastAPI backend. All fetch() calls live here — App.jsx never
//   calls fetch() directly, it only imports from this file.
//
//   Each function is async, throws on HTTP errors (with backend error messages),
//   and returns parsed JSON on success.
//
// CONNECTED TO:
//   ← frontend/src/App.jsx   (imports uploadPdf, analyzeDocument, pollStatus,
//                              runFullPipeline, getFinalReport)
//   → backend/main.py        (the FastAPI endpoints being called)
// =============================================================================

// API base URL — empty string means "same origin" (works when Vite proxy is configured
// or when frontend and backend are served from the same origin in production).
// To target a different host: const API_BASE_URL = 'http://localhost:8000';
const API_BASE_URL = 'http://localhost:8001';

/**
 * STEP 1: Upload a PDF file to the backend.
 *
 * WHY FormData:
 *   PDF is binary data. FormData with multipart/form-data is the correct
 *   HTTP encoding for file uploads — fetch handles the Content-Type boundary
 *   automatically when body is a FormData instance.
 *
 * @param {File} file - The PDF File object from the file input
 * @returns {Promise<{doc_id: string, status: string, file_name: string}>}
 */
export async function uploadPdf(file) {
  const formData = new FormData();
  formData.append('file', file);  // 'file' must match the FastAPI parameter name

  const response = await fetch(`${API_BASE_URL}/upload-pdf`, {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type header — browser sets it automatically with boundary
  });

  if (!response.ok) {
    // Extract the backend's error message (FastAPI uses {"detail": "..."} format)
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

/**
 * STEP 2: Trigger the analysis pipeline for an uploaded document.
 *
 * WHY THIS IS SEPARATE FROM UPLOAD:
 *   Parsing is slow (1-3 min for LLM claim extraction). Separating upload from
 *   analysis lets the UI show progressive feedback — upload confirmed instantly,
 *   then analysis starts separately with its own loading state.
 *
 * @param {string} docId - The doc_id returned from uploadPdf()
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
 * STEP 3a: Check the processing status of a document (single check).
 *
 * Returns the current status string:
 *   "uploaded"    → not started
 *   "processing"  → currently being parsed
 *   "success"     → parsed successfully
 *   "partial"     → parsed with some errors (citation integrity violations)
 *   "failed"      → hard failure (corrupt PDF, etc.)
 *
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
 * STEP 3b: Get full parsed paper results after analysis completes.
 *
 * Returns the full Contract 01 (ParsedPaper) JSON including all claims,
 * references, sections, and metadata.
 *
 * @param {string} docId - The document ID
 * @returns {Promise<Object>} - The parsed paper data (Contract 01)
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
 * STEP 4: Run the full Member 2 pipeline in a single call.
 *
 * This triggers three sequential stages on the backend:
 *   1. Citation resolution (Semantic Scholar + arXiv)
 *   2. LangGraph claim verification (3-agent workflow)
 *   3. Roadmap generation (LLM + heuristic fallback)
 *
 * Returns Contract 06 (FinalReportOutput) — the complete combined report.
 *
 * WHY ONE ENDPOINT:
 *   The frontend doesn't need to orchestrate the three stages individually.
 *   POST /full-pipeline runs them all and returns the combined result.
 *   This simplifies the frontend state machine.
 *
 * NOTE: This is the slowest call — can take 2-10 minutes depending on
 *   how many claims/references the paper has and LLM speed.
 *
 * @param {string} docId - The document ID
 * @returns {Promise<Object>} - Contract 06: FinalReportOutput JSON
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
 * Get the cached final report without re-running the pipeline.
 *
 * WHY NEEDED:
 *   If the user refreshes the page after /full-pipeline completed, the
 *   results are cached in-memory on the backend. This endpoint fetches
 *   them without re-running the expensive pipeline.
 *
 * @param {string} docId - The document ID
 * @returns {Promise<Object>} - Contract 06: FinalReportOutput JSON
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
 * POLLING HELPER: Repeatedly checks /status until the document is done processing.
 *
 * WHY NEEDED:
 *   POST /analyze is synchronous on the backend and takes 1-3 minutes.
 *   The frontend can't just "await" that long without the connection timing out.
 *   Instead, /analyze returns immediately after starting, and this function
 *   polls /status every `intervalMs` milliseconds until done.
 *
 * DESIGN:
 *   - Resolves when status is "done", "success", or "partial"
 *   - Rejects when status is "failed" or timeout is exceeded
 *   - Default: poll every 2 seconds, timeout after 3 minutes
 *
 * @param {string} docId - The document ID
 * @param {number} intervalMs - Polling interval (default: 2000ms)
 * @param {number} timeoutMs - Max wait time (default: 120000ms = 2 min)
 * @returns {Promise<{doc_id: string, status: string}>}
 */
export async function pollStatus(docId, intervalMs = 2000, timeoutMs = 120000) {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    const status = await getStatus(docId);

    // Resolve on any "done" state — "partial" means some citations failed
    // but we still have enough to proceed with the pipeline
    if (status.status === 'done' || status.status === 'success' || status.status === 'partial') {
      return status;
    }

    // Hard failure — reject immediately, no point polling further
    if (status.status === 'failed') {
      throw new Error('Document processing failed');
    }

    // Still processing — wait before next poll
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  // Timeout exceeded
  throw new Error('Processing timeout - document is still being processed');
}
