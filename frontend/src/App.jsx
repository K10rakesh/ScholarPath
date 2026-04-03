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

