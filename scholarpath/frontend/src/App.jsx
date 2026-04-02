import { useState } from 'react';
import ClickSpark from './ClickSpark';
import ElectricBorder from './ElectricBorder';
import './index.css';
import { uploadPdf, analyzeDocument, pollStatus, runFullPipeline, getFinalReport } from './api';

function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

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
      await analyzeDocument(docId);

      // Step 3: Poll for completion
      setStatus('Processing claims and citations...');
      await pollStatus(docId, 2000, 180000);

      // Step 4: Run full pipeline (citation resolution + verification + roadmap)
      setStatus('Generating roadmap...');
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

              <div style={{ marginBottom: '1.5rem' }}>
                <h3 style={{ color: '#E8174A', marginBottom: '0.5rem' }}>Claims Verified</h3>
                <p style={{ color: 'var(--text-muted)' }}>
                  {result.claims_overview?.length || 0} claims analyzed
                </p>
                {result.claims_overview && result.claims_overview.slice(0, 3).map((claim, idx) => (
                  <div
                    key={claim.claim_id}
                    style={{
                      padding: '0.75rem',
                      background: 'rgba(255,255,255,0.3)',
                      borderRadius: '8px',
                      marginBottom: '0.5rem',
                      fontSize: '0.9rem'
                    }}
                  >
                    <span style={{
                      display: 'inline-block',
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: claim.verdict === 'supported' ? '#22c55e' :
                                 claim.verdict === 'partially_supported' ? '#f59e0b' : '#ef4444',
                      marginRight: '8px'
                    }} />
                    {claim.claim_text.substring(0, 100)}...
                  </div>
                ))}
              </div>

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
              {loading ? status : 'Make Roadmap'}
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
