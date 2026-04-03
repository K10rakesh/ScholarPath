import { useState } from "react";
import "./App.css";

function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    if (e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      alert("Please select a PDF file first.");
      return;
    }

    setLoading(true);
    setError("");
    setData(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to upload the file.");
      }

      const result = await res.json();
      console.log("Backend Output:", result);
      setData(result);
    } catch (err) {
      console.error(err);
      setError("An error occurred during upload. Please check the console.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h1>ScholarPath Upload</h1>
      
      <div className="upload-section">
        <input type="file" accept="application/pdf" onChange={handleFileChange} />
        <button onClick={handleUpload} disabled={loading || !file}>
          {loading ? "Processing..." : "Submit PDF"}
        </button>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {data && data.verification && (
        <div id="results-area">
          <h3>Verified Topics</h3>
          <div className="topics-grid">
            {data.verification
              .filter((item) => item.score > 0)
              .map((item, idx) => (
                <div key={idx} className={`topic-box ${item.color || "red"}`}>
                  <span>{item.topic !== "None" ? item.topic : "Generic Claim"}</span>
                  <span className="topic-score">{item.score}/100</span>
                </div>
              ))}
          </div>

          <h3>Agent-Generated Roadmap</h3>
          <div className="roadmap-grid">
            {data.roadmap && Array.isArray(data.roadmap) && data.roadmap.length > 0 ? (
              data.roadmap.map((step, idx) => (
                <div key={idx} className="roadmap-step">
                  <h4>
                    Step {step.step}: {step.topic}
                  </h4>
                  <p>{step.description}</p>
                  {step.recommended_paper && (
                    <div className="recommended-paper" style={{ marginTop: "15px", padding: "10px", backgroundColor: "#fff", borderLeft: "4px solid #3498db" }}>
                      <strong>Suggested Reading:</strong>
                      <br/>
                      <a href={step.recommended_paper.url} target="_blank" rel="noopener noreferrer" style={{ color: "#3498db", textDecoration: "none", fontWeight: "bold" }}>
                        {step.recommended_paper.title}
                      </a>
                      {step.recommended_paper.authors && step.recommended_paper.authors.length > 0 && (
                        <p style={{ fontSize: "0.85em", color: "#7f8c8d", margin: "4px 0 0 0" }}>
                          Authors: {step.recommended_paper.authors.join(", ")}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p>No roadmap could be generated.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

