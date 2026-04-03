// =============================================================================
// frontend/src/App.jsx
// =============================================================================
// WHAT THIS FILE DOES (Overall):
//   The entire React UI for ScholarPath. Single-file component architecture —
//   all screens (upload, loading, results) live here as conditional renders
//   based on the `result` state variable.
//
//   TWO SCREENS:
//     1. Upload Screen (result === null)
//        - ElectricBorder card with file input + "Make Roadmap" button
//        - Button shows real-time status + countdown timer while loading
//
//     2. Results Screen (result !== null)
//        - Trust Score display (color-coded by hsl mapping score → hue)
//        - ClaimsSection: expandable list of verified claims
//        - Learning Path: numbered reading order from roadmap
//        - "Analyze Another Paper" reset button
//
//   UI COMPONENT TREE:
//     <ClickSpark>           ← particle effect on every click
//       <ElectricBorder>     ← animated neon border around main card
//         <App>              ← state management + business logic
//           <ClaimsSection>  ← renders all claims with show-more
//             <ExpandableClaim> ← individual claim card (click to expand)
//
// CONNECTED TO:
//   → frontend/src/api.js           (all fetch calls: uploadPdf, analyzeDocument, etc.)
//   → frontend/src/ElectricBorder   (animated border wrapper)
//   → frontend/src/ClickSpark       (click particle effect)
//   → frontend/src/index.css        (CSS variables + glass-card / generate-btn classes)
//   ← backend/main.py               (API endpoints consumed via api.js)
// =============================================================================

import { useState, useEffect } from "react";
import ClickSpark from "./ClickSpark";
import ElectricBorder from "./ElectricBorder";
import "./index.css";
import {
  uploadPdf,          // Step 1: upload file, get doc_id
  analyzeDocument,    // Step 2: trigger PDF parsing + LLM claim extraction
  pollStatus,         // Step 3: poll /status until parsing completes
  runFullPipeline,    // Step 4: resolve citations + verify + generate roadmap
  getFinalReport,     // Utility: fetch cached final report by doc_id
} from "./api";


// =============================================================================
// Trust Color Helpers
// Single source of truth for the green / yellow / red color logic.
// Used by both the TrustBanner and each roadmap node card so they always match.
// =============================================================================

/**
 * getTrustColor
 * Maps a numeric trust score to a CSS-ready color token.
 * Thresholds mirror the backend TrustStatus enum:
 *   TRUSTED   ≥ 75  → green
 *   CAUTION   45-74 → yellow
 *   LOW_TRUST  < 45 → red
 *
 * @param {number} score - trust_score from trust_report (0-100)
 * @returns {{ border: string, bg: string, text: string, label: string, icon: string }}
 */
function getTrustColor(score) {
  if (score >= 75) {
    return {
      border: "#22c55e",                    // green-500
      bg: "rgba(34, 197, 94, 0.10)",        // green tint for banner background
      text: "#16a34a",                       // green-600 for readable text
      label: "Trusted",
      icon: "✅",
    };
  }
  if (score >= 45) {
    return {
      border: "#f59e0b",                    // amber-400
      bg: "rgba(245, 158, 11, 0.10)",       // amber tint
      text: "#b45309",                       // amber-700
      label: "Caution",
      icon: "⚠️",
    };
  }
  return {
    border: "#ef4444",                      // red-500
    bg: "rgba(239, 68, 68, 0.10)",          // red tint
    text: "#b91c1c",                         // red-700
    label: "Low Trust",
    icon: "❌",
  };
}


// =============================================================================
// Sub-component: TrustBanner
// Displays a colored summary banner above the roadmap node list.
// =============================================================================

/**
 * TrustBanner
 * Shows one of three banners based on the trust score:
 *   ✅ "This roadmap is based on a Trusted paper (Score: 82/100)"
 *   ⚠️ "Caution: This paper has partial verification (Score: 58/100)"
 *   ❌ "Warning: This roadmap is based on a Low Trust paper (Score: 31/100)"
 *
 * @param {number} score  - trust_score from result.trust_report
 * @param {string} status - trust_status e.g. "trusted" | "caution" | "low_trust"
 */
function TrustBanner({ score, status }) {
  const trust = getTrustColor(score);

  // Build the banner message based on trust level
  const message = (() => {
    if (score >= 75)
      return `This roadmap is based on a Trusted paper (Score: ${score}/100)`;
    if (score >= 45)
      return `Caution: This paper has partial verification (Score: ${score}/100)`;
    return `Warning: This roadmap is based on a Low Trust paper (Score: ${score}/100)`;
  })();

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        padding: "0.65rem 1rem",
        marginBottom: "1rem",
        borderRadius: "8px",
        border: `1px solid ${trust.border}`,
        background: trust.bg,
        fontSize: "0.875rem",
        fontWeight: "600",
        color: trust.text,
        letterSpacing: "0.01em",
      }}
    >
      <span style={{ fontSize: "1.1rem", lineHeight: 1 }}>{trust.icon}</span>
      <span>{message}</span>
    </div>
  );
}


// =============================================================================
// Sub-component: ClaimsSection
// Renders the full list of verified claims with "show more" pagination.
// =============================================================================

/**
 * ClaimsSection
 * Renders a list of ExpandableClaim cards for all verified claims.
 *
 * WHY "show more" AT 5 CLAIMS:
 *   Papers often have 10-30+ claims. Showing all at once overwhelms the UI.
 *   5 is enough to demonstrate the feature; user can expand on demand.
 *
 * @param {Array} claims - Array of ClaimsOverviewItem objects from Contract 06
 */
function ClaimsSection({ claims }) {
  // Track which claims are expanded (by claim_id key)
  const [expandedClaims, setExpandedClaims] = useState({});
  // Controls whether we show all claims or just the first 5
  const [showAll, setShowAll] = useState(false);

  // Toggle a single claim's expanded state
  const toggleClaim = (claimId) => {
    setExpandedClaims((prev) => ({
      ...prev,
      [claimId]: !prev[claimId],   // flip the boolean for this claim
    }));
  };

  // Show only 5 claims initially; show all when "Show N more" is clicked
  const displayedClaims = showAll ? claims : (claims || []).slice(0, 5);

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h3 style={{ color: "#E8174A", marginBottom: "0.5rem" }}>
        Claims Verified
      </h3>
      <p style={{ color: "var(--text-muted)" }}>
        {claims?.length || 0} claims analyzed
      </p>

      {/* Render each claim as an expandable card */}
      {displayedClaims?.map((claim) => (
        <ExpandableClaim
          key={claim.claim_id}
          claim={claim}
          isExpanded={!!expandedClaims[claim.claim_id]}
          onToggle={() => toggleClaim(claim.claim_id)}
        />
      ))}

      {/* "Show N more" button — only visible if there are more than 5 claims */}
      {claims && claims.length > 5 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          style={{
            marginTop: "0.5rem",
            padding: "0.5rem 1rem",
            background: "transparent",
            border: "1px solid #E8174A",
            color: "#E8174A",
            borderRadius: "6px",
            cursor: "pointer",
            fontSize: "0.85rem",
          }}
        >
          Show {claims.length - 5} more claims
        </button>
      )}
    </div>
  );
}


// =============================================================================
// Sub-component: ExpandableClaim
// A single claim card — collapsed by default, click to see full details.
// =============================================================================

/**
 * ExpandableClaim
 * Renders one verified claim with color-coded verdict indicator.
 *
 * VERDICT COLOR MAPPING:
 *   supported           → green  (#22c55e)
 *   partially_supported → yellow (#f59e0b)
 *   anything else       → red    (#ef4444) — unsupported / insufficient / unresolved
 *
 * COLLAPSED STATE: Shows first 150 chars of claim text + colored dot
 * EXPANDED STATE:  Shows full claim text + section, type, confidence %, explanation
 *
 * @param {Object} claim      - ClaimsOverviewItem from Contract 06
 * @param {boolean} isExpanded - Whether this card is currently expanded
 * @param {Function} onToggle  - Callback to toggle expanded state
 */
function ExpandableClaim({ claim, isExpanded, onToggle }) {
  const isSupported = claim.verdict === "supported";
  const isPartial = claim.verdict === "partially_supported";

  // Color-code the indicator dot based on verdict
  const statusColor = isSupported
    ? "#22c55e"    // green  — citation fully supports the claim
    : isPartial
      ? "#f59e0b"  // yellow — citation partially supports
      : "#ef4444"; // red    — unsupported / insufficient / unresolved

  return (
    <div
      style={{
        padding: "0.75rem",
        background: "rgba(255,255,255,0.3)",
        borderRadius: "8px",
        marginBottom: "0.5rem",
        cursor: "pointer",
        border: `1px solid ${statusColor}40`,   // 40 = 25% opacity hex
        transition: "background 0.2s",
      }}
      onClick={onToggle}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}>
        {/* Colored verdict dot */}
        <span
          style={{
            minWidth: "8px",
            height: "8px",
            borderRadius: "50%",
            background: statusColor,
            marginRight: "4px",
            marginTop: "4px",
            flexShrink: 0,
          }}
        />
        <div style={{ flex: 1 }}>
          {/* Claim text: truncated when collapsed, full when expanded */}
          <p style={{ margin: 0, fontSize: "0.9rem" }}>
            {isExpanded
              ? claim.claim_text
              : `${claim.claim_text.substring(0, 150)}${claim.claim_text.length > 150 ? "..." : ""}`}
          </p>

          {/* Expanded detail panel — only visible when isExpanded */}
          {isExpanded && (
            <div
              style={{
                marginTop: "0.5rem",
                fontSize: "0.8rem",
                color: "var(--text-muted)",
              }}
            >
              {/* Citations field — shows which reference ([1], [3], etc.) */}
              <div>
                <strong>Section:</strong> {claim.citations?.[0] || "N/A"}
              </div>
              {/* Claim type: result / background / method / comparative */}
              <div>
                <strong>Type:</strong> {claim.claim_type || "N/A"}
              </div>
              {/* Confidence percentage — rounds confidence_score (0-100) */}
              <div>
                <strong>Confidence:</strong>{" "}
                {Math.round(
                  claim.confidence_score ?? (claim.confidence || 0) * 100,
                )}
                %
              </div>
              {/* LLM's reasoning for its verdict */}
              {claim.explanation && (
                <div style={{ marginTop: "0.25rem" }}>
                  <strong>Explanation:</strong> {claim.explanation}
                </div>
              )}
            </div>
          )}

          {/* Expand/collapse hint text */}
          <div
            style={{
              marginTop: "0.25rem",
              fontSize: "0.75rem",
              color: "var(--text-muted)",
            }}
          >
            {isExpanded ? "▼ Click to collapse" : "▲ Click to expand"}
          </div>
        </div>
      </div>
    </div>
  );
}


// =============================================================================
// Main Component: App
// Manages all state, orchestrates the 4-step pipeline, renders both screens
// =============================================================================

function App() {
  // ── State Variables ────────────────────────────────────────────────────────

  const [file, setFile] = useState(null);          // the selected PDF File object
  const [loading, setLoading] = useState(false);    // true while any pipeline step runs
  const [status, setStatus] = useState("");         // human-readable step label shown on button
  const [result, setResult] = useState(null);       // FinalReportOutput (Contract 06) when done
  const [error, setError] = useState(null);         // error message string if pipeline fails
  const [etaSeconds, setEtaSeconds] = useState(0);  // countdown timer (estimated wait seconds)

  // ── ETA Countdown Timer ────────────────────────────────────────────────────
  // Runs a 1-second interval while loading and etaSeconds > 0.
  // Displayed on the button as "(~2m 30s)" to reduce user frustration
  // during long-running pipeline steps.
  useEffect(() => {
    let timer;
    if (loading && etaSeconds > 0) {
      timer = setInterval(() => {
        setEtaSeconds((prev) => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(timer);  // cleanup on unmount or when loading stops
  }, [loading, etaSeconds]);


  // ── File Input Handler ─────────────────────────────────────────────────────
  /**
   * Called when user selects a file via the file input.
   * Stores the File object in state and resets any previous results/errors.
   */
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setResult(null);
    }
  };


  // ── Main Pipeline Handler ──────────────────────────────────────────────────
  /**
   * THE MAIN FLOW — triggered when user clicks "Make Roadmap".
   *
   * SEQUENCE OF 4 API CALLS:
   *   Step 1: uploadPdf()       → POST /upload-pdf      → get doc_id
   *   Step 2: analyzeDocument() → POST /analyze/:id     → trigger parsing + LLM
   *   Step 3: pollStatus()      → GET /status/:id loop  → wait for "success/partial"
   *   Step 4: runFullPipeline() → POST /full-pipeline/:id → resolve+verify+roadmap
   *
   * ETA CALCULATION:
   *   After step 2, we know num_references and num_claims.
   *   Heuristic formula: num_references * 3.5s (API throttle) + num_claims * 8s (LLM) + 20s buffer
   *   This drives the countdown timer shown on the button.
   *
   * ERROR HANDLING:
   *   Any thrown error is caught, displayed as red text below the button,
   *   and loading is reset. The user can retry without refreshing.
   */
  const handleMakeRoadmap = async () => {
    if (!file) return;

    setLoading(true);
    setStatus("Uploading paper...");
    setError(null);
    setResult(null);

    try {
      // ── Step 1: Upload the PDF file ────────────────────────────────────────
      const uploadRes = await uploadPdf(file);
      const docId = uploadRes.doc_id;
      setStatus("Analyzing paper...");

      // ── Step 2: Trigger PDF parsing + LLM claim extraction ─────────────────
      // This returns quickly (just starts the background task).
      // Set an initial ETA of 120s as a placeholder before we know the real size.
      setEtaSeconds(120);
      const analyzeRes = await analyzeDocument(docId);

      // ── Step 3: Poll /status until parsing completes ───────────────────────
      // Polling every 2 seconds, timeout after 3 minutes
      setStatus("Processing claims and citations...");
      await pollStatus(docId, 2000, 180000);

      // ── Step 4: Run the full Member 2 pipeline ─────────────────────────────
      // Now we know num_references and num_claims from the analyze response,
      // so we can give an accurate ETA for this slower step.
      setStatus("Generating roadmap...");
      const estSecs = Math.ceil(
        analyzeRes.num_references * 3.5 +  // ~3.5s per API call (Semantic Scholar throttle)
        analyzeRes.num_claims * 8 +         // ~8s per claim (LangGraph + Ollama verification)
        20,                                  // 20s fixed overhead buffer
      );
      setEtaSeconds(estSecs);

      // Call POST /full-pipeline — resolve citations → verify → roadmap → Contract 06
      const finalReport = await runFullPipeline(docId);

      // Success — switch to results screen
      setResult(finalReport);
      setStatus("done");
    } catch (err) {
      console.error("Pipeline error:", err);
      setError(err.message);
      setStatus("error");
    } finally {
      setLoading(false);  // always reset loading state, whether success or failure
    }
  };


  // =============================================================================
  // RESULTS SCREEN — shown when result state is populated
  // =============================================================================
  if (result) {
    return (
      // ClickSpark: adds particle burst on every mouse click for visual delight
      <ClickSpark
        sparkColor="#E8174A"
        sparkSize={20}
        sparkRadius={30}
        sparkCount={8}
        duration={500}
      >
        <div className="container">
          {/* ElectricBorder: animated neon frame around the results card */}
          <ElectricBorder
            color="#E8174A"
            speed={1}
            chaos={0.12}
            borderRadius={16}
            style={{ width: "90%", maxWidth: "800px" }}
          >
            <div className="glass-card" style={{ textAlign: "left" }}>
              <h1 className="title">Roadmap Generated</h1>
              <p className="subtitle">
                Analysis complete for: {result.paper?.title || "Unknown"}
              </p>

              {/* ── Trust Score Section ──────────────────────────────────────── */}
              {/* Color is computed by mapping trust_score (0-100) to hsl hue
                  score=0  → hsl(0, 100%, 45%)   = red (low trust)
                  score=83 → hsl(100, 100%, 45%) = green (trusted)
                  This gives a smooth red→yellow→green visual gradient */}
              <div style={{ marginBottom: "1.5rem" }}>
                <h3 style={{ color: "#E8174A", marginBottom: "0.5rem" }}>
                  Trust Score
                </h3>
                <div
                  style={{
                    fontSize: "2rem",
                    fontWeight: "800",
                    color: `hsl(${(result.trust_report?.trust_score || 0) * 1.2}, 100%, 45%)`,
                  }}
                >
                  {result.trust_report?.trust_score || "N/A"}%
                </div>
                <p style={{ color: "var(--text-muted)" }}>
                  {result.trust_report?.summary || "No summary available"}
                </p>
              </div>

              {/* ── Claims Section ────────────────────────────────────────────── */}
              {/* ClaimsSection renders all verified claims as expandable cards */}
              <ClaimsSection claims={result.claims_overview} />

              {/* ── Learning Path Section ─────────────────────────────────────── */}
              {/* Renders the roadmap's reading_order as a numbered sequential list.
                  Each topic card has a colored left border driven by getTrustColor().
                  Node order and layout are unchanged — only the color indicator is new. */}
              <div style={{ marginBottom: "1.5rem" }}>
                <h3 style={{ color: "#E8174A", marginBottom: "0.5rem" }}>
                  Learning Path
                </h3>
                <p style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                  {result.roadmap?.nodes?.length || 0} topics to master
                </p>

                {/* Trust summary banner — green / yellow / red based on score */}
                <TrustBanner
                  score={result.trust_report?.trust_score ?? result.trust_report?.overall_score ?? 0}
                  status={result.trust_report?.status ?? result.trust_report?.trust_status ?? ""}
                />

                {result.roadmap?.reading_order &&
                  result.roadmap.reading_order.map((topic, idx) => {
                    // Derive the trust color once per card so border + dot always match
                    const score =
                      result.trust_report?.trust_score ??
                      result.trust_report?.overall_score ??
                      0;
                    const trust = getTrustColor(score);

                    return (
                      <div
                        key={idx}
                        style={{
                          padding: "0.5rem 0.75rem",
                          background: "rgba(255,255,255,0.3)",
                          borderRadius: "6px",
                          marginBottom: "0.35rem",
                          fontSize: "0.9rem",
                          display: "flex",
                          alignItems: "center",
                          // ← colored left border: the only visual change to each node
                          borderLeft: `4px solid ${trust.border}`,
                          transition: "border-color 0.2s",
                        }}
                      >
                        {/* Step number circle */}
                        <span
                          style={{
                            minWidth: "24px",
                            height: "24px",
                            borderRadius: "50%",
                            background: "#E8174A",
                            color: "white",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "0.75rem",
                            marginRight: "10px",
                            flexShrink: 0,
                          }}
                        >
                          {idx + 1}
                        </span>

                        {/* Topic label */}
                        <span style={{ flex: 1 }}>{topic}</span>

                        {/* Small trust color dot on the right — quick visual cue */}
                        <span
                          style={{
                            width: "8px",
                            height: "8px",
                            borderRadius: "50%",
                            background: trust.border,
                            marginLeft: "10px",
                            flexShrink: 0,
                            opacity: 0.85,
                          }}
                          title={`${trust.label} (${score}/100)`}
                        />
                      </div>
                    );
                  })}
              </div>

              {/* ── Reset Button ───────────────────────────────────────────────── */}
              {/* Clears result, file, and status — takes user back to upload screen */}
              <button
                className="generate-btn"
                onClick={() => {
                  setResult(null);
                  setFile(null);
                  setStatus("");
                }}
                style={{ marginTop: "1rem" }}
              >
                Analyze Another Paper
              </button>
            </div>
          </ElectricBorder>
        </div>
      </ClickSpark>
    );
  }


  // =============================================================================
  // UPLOAD SCREEN — shown when result === null (initial state)
  // =============================================================================
  return (
    <ClickSpark
      sparkColor="#E8174A"
      sparkSize={20}
      sparkRadius={30}
      sparkCount={8}
      duration={500}
    >
      <div className="container">
        {/* ElectricBorder wraps the entire center upload card */}
        <ElectricBorder
          color="#E8174A"
          speed={1}
          chaos={0.12}
          borderRadius={16}
          style={{ width: "90%", maxWidth: "600px" }}
        >
          <div className="glass-card">
            <h1 className="title">ScholarPath</h1>
            <p className="subtitle">
              Upload a research paper to generate your learning roadmap.
            </p>

            {/* ── File Upload Area ───────────────────────────────────────────── */}
            {/* Hidden native file input + styled label (common accessible pattern).
                The label acts as a clickable drag-area; clicking it triggers the input. */}
            <div className="upload-area">
              <input
                type="file"
                id="file-upload"
                accept=".pdf"             // restrict to PDF files only
                onChange={handleFileChange}
              />
              <label htmlFor="file-upload" className="upload-label">
                {file ? (
                  // Show selected filename when a file is chosen
                  <span className="file-name">{file.name}</span>
                ) : (
                  // Show placeholder prompt when no file selected
                  <span className="placeholder">
                    Drag &amp; drop or Click to upload PDF
                  </span>
                )}
              </label>
            </div>

            {/* ── Generate Button ────────────────────────────────────────────── */}
            {/* Shows dynamic label during loading:
                - "Uploading paper..."            (step 1)
                - "Analyzing paper... (~2m 5s)"  (step 2 + countdown)
                - "Generating roadmap... (~4m)"  (step 4 + countdown)
                Disabled when no file selected or while loading */}
            <button
              className={`generate-btn ${loading ? "loading" : ""} ${!file ? "disabled" : ""}`}
              onClick={handleMakeRoadmap}
              disabled={!file || loading}
            >
              {loading
                ? `${status} ${etaSeconds > 0 ? `(~${Math.floor(etaSeconds / 60)}m ${etaSeconds % 60}s)` : ""}`
                : "Make Roadmap"}
            </button>

            {/* ── Error Display ─────────────────────────────────────────────── */}
            {/* Shows backend error messages in red below the button.
                Cleared automatically when a new file is selected. */}
            {error && (
              <p
                style={{
                  color: "#ef4444",
                  marginTop: "1rem",
                  fontSize: "0.9rem",
                }}
              >
                Error: {error}
              </p>
            )}
          </div>
        </ElectricBorder>
      </div>
    </ClickSpark>
  );
}

export default App;
