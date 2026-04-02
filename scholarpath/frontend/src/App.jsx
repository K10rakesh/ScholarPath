import { useState } from 'react';
import ClickSpark from './ClickSpark';
import ElectricBorder from './ElectricBorder';
import './index.css';

function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleMakeRoadmap = () => {
    if (!file) return;
    setLoading(true);
    console.log("Preparing to send", file.name, "to backend");
    setTimeout(() => {
      setLoading(false);
      alert('Paper processed! Ready to generate your roadmap.');
    }, 2000);
  };

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
              {loading ? 'Processing...' : 'Make Roadmap'}
            </button>
          </div>
        </ElectricBorder>
      </div>
    </ClickSpark>
  );
}

export default App;
