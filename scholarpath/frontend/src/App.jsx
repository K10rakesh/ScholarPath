import { useState, useEffect } from 'react';
import ClickSpark from './ClickSpark';
import ElectricBorder from './ElectricBorder';
import './index.css';
import { uploadPdf, analyzeDocument, pollStatus, runFullPipeline, getFinalReport } from './api';

// ClaimsSection component with expandable claims
function ClaimsSection({ claims }) {
  const [expandedClaims, setExpandedClaims] = useState({});
  const [showAll, setShowAll] = useState(false);

  const toggleClaim = (claimId) => {
    setExpandedClaims(prev => ({
      ...prev,
      [claimId]: !prev[claimId]
    }));
  };

  const displayedClaims = showAll ? claims : (claims || []).slice(0, 5);

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ color: '#E8174A', marginBottom: '0.5rem' }}>Claims Verified</h3>
      <p style={{ color: 'var(--text-muted)' }}>
        {claims?.length || 0} claims analyzed
      </p>
      {displayedClaims?.map((claim) => (
        <ExpandableClaim
          key={claim.claim_id}
          claim={claim}
          isExpanded={!!expandedClaims[claim.claim_id]}
          onToggle={() => toggleClaim(claim.claim_id)}
        />
      ))}
      {claims && claims.length > 5 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          style={{
            marginTop: '0.5rem',
            padding: '0.5rem 1rem',
            background: 'transparent',
            border: '1px solid #E8174A',
            color: '#E8174A',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '0.85rem'
          }}
        >
          Show {claims.length - 5} more claims
        </button>
      )}
    </div>
  );
}

// ExpandableClaim component for displaying claims with expand/collapse
function ExpandableClaim({ claim, isExpanded, onToggle }) {
  const isSupported = claim.verdict === 'supported';
  const isPartial = claim.verdict === 'partially_supported';
  const statusColor = isSupported ? '#22c55e' : isPartial ? '#f59e0b' : '#ef4444';

  return (
    <div
      style={{
        padding: '0.75rem',
        background: 'rgba(255,255,255,0.3)',
        borderRadius: '8px',
        marginBottom: '0.5rem',
        cursor: 'pointer',
        border: `1px solid ${statusColor}40`,
        transition: 'background 0.2s'
      }}
      onClick={onToggle}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
        <span style={{
          minWidth: '8px',
          height: '8px',
          borderRadius: '50%',
          background: statusColor,
          marginRight: '4px',
          marginTop: '4px',
          flexShrink: 0
        }} />
        <div style={{ flex: 1 }}>
          <p style={{ margin: 0, fontSize: '0.9rem' }}>
            {isExpanded ? claim.claim_text : `${claim.claim_text.substring(0, 150)}${claim.claim_text.length > 150 ? '...' : ''}`}
          </p>
          {isExpanded && (
            <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              <div><strong>Section:</strong> {claim.citations?.[0] || 'N/A'}</div>
              <div><strong>Type:</strong> {claim.claim_type || 'N/A'}</div>
              <div><strong>Confidence:</strong> {(claim.confidence * 100).toFixed(0)}%</div>
              {claim.explanation && (
                <div style={{ marginTop: '0.25rem' }}><strong>Explanation:</strong> {claim.explanation}</div>
              )}
            </div>
          )}
          <div style={{ marginTop: '0.25rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {isExpanded ? '▼ Click to collapse' : '▲ Click to expand'}
          </div>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [etaSeconds, setEtaSeconds] = useState(0);

  useEffect(() => {
    let timer;
    if (loading && etaSeconds > 0) {
      timer = setInterval(() => {
        setEtaSeconds(prev => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [loading, etaSeconds]);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setResult(null);
    }
  };

  const handleMakeRoadmap = async () => {
    if (!file) return;

    setLoading(true);
    setStatus('Uploading paper...');
    setError(null);
    setResult(null);

    try {
      // Step 1: Upload PDF
      const uploadRes = await uploadPdf(file);
      const docId = uploadRes.doc_id;
      setStatus('Analyzing paper...');

      // Step 2: Start analysis
      setEtaSeconds(120); // Average fallback estimate for LLM basic parsing boundary
      const analyzeRes = await analyzeDocument(docId);

      // Step 3: Poll for completion
      setStatus('Processing claims and citations...');
      await pollStatus(docId, 2000, 180000);

      // Step 4: Run full pipeline (citation resolution + verification + roadmap)
      setStatus('Generating roadmap...');
      
      // Safety calculation for exactly predicting API delays and context processing speeds
      const estSecs = Math.ceil((analyzeRes.num_references * 3.5) + (analyzeRes.num_claims * 8) + 20);
      setEtaSeconds(estSecs);
      
      const finalReport = await runFullPipeline(docId);

      setResult(finalReport);
      setStatus('done');
    } catch (err) {
      console.error('Pipeline error:', err);
      setError(err.message);
      setStatus('error');
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <ClickSpark
        sparkColor='#E8174A'
        sparkSize={20}
        sparkRadius={30}
        sparkCount={8}
        duration={500}
      >
        <div className="container">
          <ElectricBorder
            color="#E8174A"
            speed={1}
            chaos={0.12}
            borderRadius={16}
            style={{ width: '90%', maxWidth: '800px' }}
          >
            <div className="glass-card" style={{ textAlign: 'left' }}>
              <h1 className="title">Roadmap Generated</h1>
              <p className="subtitle">Analysis complete for: {result.paper?.title || 'Unknown'}</p>

              <div style={{ marginBottom: '1.5rem' }}>
                <h3 style={{ color: '#E8174A', marginBottom: '0.5rem' }}>Trust Score</h3>
                <div style={{
                  fontSize: '2rem',
                  fontWeight: '800',
                  color: result.trust_report?.status === 'trusted' ? '#22c55e' :
                         result.trust_report?.status === 'caution' ? '#f59e0b' : '#ef4444'
                }}>
                  {result.trust_report?.trust_score || 'N/A'}%
                </div>
                <p style={{ color: 'var(--text-muted)' }}>
                  {result.trust_report?.summary || 'No summary available'}
                </p>
              </div>

              <ClaimsSection claims={result.claims_overview} />

              <div style={{ marginBottom: '1.5rem' }}>
                <h3 style={{ color: '#E8174A', marginBottom: '0.5rem' }}>Learning Path</h3>
                <p style={{ color: 'var(--text-muted)' }}>
                  {result.roadmap?.nodes?.length || 0} topics to master
                </p>
                {result.roadmap?.reading_order && result.roadmap.reading_order.map((topic, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.5rem 0.75rem',
                      background: 'rgba(255,255,255,0.3)',
                      borderRadius: '6px',
                      marginBottom: '0.35rem',
                      fontSize: '0.9rem',
                      display: 'flex',
                      alignItems: 'center'
                    }}
                  >
                    <span style={{
                      minWidth: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      background: '#E8174A',
                      color: 'white',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.75rem',
                      marginRight: '10px'
                    }}>
                      {idx + 1}
                    </span>
                    {topic}
                  </div>
                ))}
              </div>

              <button
                className="generate-btn"
                onClick={() => {
                  setResult(null);
                  setFile(null);
                  setStatus('');
                }}
                style={{ marginTop: '1rem' }}
              >
                Analyze Another Paper
              </button>
            </div>
          </ElectricBorder>
        </div>
      </ClickSpark>
    );
  }

  return (
    <ClickSpark
      sparkColor='#E8174A'
      sparkSize={20}
      sparkRadius={30}
      sparkCount={8}
      duration={500}
    >
      <div className="container">
        {/* ElectricBorder wraps the entire center card */}
        <ElectricBorder
          color="#E8174A"
          speed={1}
          chaos={0.12}
          borderRadius={16}
          style={{ width: '90%', maxWidth: '600px' }}
        >
          <div className="glass-card">
            <h1 className="title">ScholarPath</h1>
            <p className="subtitle">Upload a research paper to generate your learning roadmap.</p>

            <div className="upload-area">
              <input
                type="file"
                id="file-upload"
                accept=".pdf"
                onChange={handleFileChange}
              />
              <label htmlFor="file-upload" className="upload-label">
                {file ? (
                  <span className="file-name">{file.name}</span>
                ) : (
                  <span className="placeholder">Drag &amp; drop or Click to upload PDF</span>
                )}
              </label>
            </div>

            <button
              className={`generate-btn ${loading ? 'loading' : ''} ${!file ? 'disabled' : ''}`}
              onClick={handleMakeRoadmap}
              disabled={!file || loading}
            >
              {loading ? `${status} ${etaSeconds > 0 ? `(~${Math.floor(etaSeconds / 60)}m ${etaSeconds % 60}s)` : ''}` : 'Make Roadmap'}
            </button>

            {error && (
              <p style={{ color: '#ef4444', marginTop: '1rem', fontSize: '0.9rem' }}>
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
