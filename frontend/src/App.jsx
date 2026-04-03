import { useState, useEffect } from "react";
import Auth from "./components/Auth";
import { supabase } from "./supabaseClient";
import "./App.css";

function App() {
  const [session, setSession] = useState(null);
  const [history, setHistory] = useState([]);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) fetchHistory();
    });

    supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) fetchHistory();
    });
  }, []);

  const fetchHistory = async () => {
    const { data: dbHistory, error } = await supabase
      .from('uploads_history')
      .select('*')
      .order('created_at', { ascending: false });
    
    if (error) console.error("Error fetching history:", error);
    else setHistory(dbHistory || []);
  };

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
    setActiveHistoryId(null);

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
      
      // Save to Supabase
      if (session?.user) {
        const { error: dbError } = await supabase
          .from('uploads_history')
          .insert([
            { 
              user_id: session.user.id, 
              filename: file.name, 
              analysis_data: result 
            }
          ]);
        if (dbError) console.error("Failed to save history:", dbError);
        else fetchHistory(); // Refresh history
      }

    } catch (err) {
      console.error(err);
      setError("An error occurred during upload. Please check the console.");
    } finally {
      setLoading(false);
    }
  };

  const [activeHistoryId, setActiveHistoryId] = useState(null);

  const loadHistoryItem = (item) => {
    setData(item.analysis_data);
    setActiveHistoryId(item.id);
    setError("");
  };

  if (!session) {
    return <Auth />;
  }

  return (
    <div className="layout-container">
      {/* Sidebar for History */}
      <aside className="sidebar">
        <h3>History</h3>
        <div className="history-list">
          {history.length > 0 ? (
            history.map((record) => (
              <div 
                key={record.id} 
                className={`history-item ${activeHistoryId === record.id ? 'active' : ''}`} 
                onClick={() => loadHistoryItem(record)}
              >
                <div className="history-filename">{record.filename}</div>
                <div className="history-date">
                  {new Date(record.created_at).toLocaleDateString()}
                </div>
              </div>
            ))
          ) : (
            <p>No history found.</p>
          )}
        </div>
        <button 
          className="logout-btn" 
          onClick={() => supabase.auth.signOut()}
        >
          Sign Out
        </button>
      </aside>

      {/* Main Content Area */}
      <div className="container main-content">
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
    </div>
  );
}

export default App;

