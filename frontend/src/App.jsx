import { useState, useEffect } from "react";
import Auth from "./components/Auth";
import RoadmapFlow from "./components/RoadmapFlow";
import ParticlesBackground from "./components/ParticlesBackground";
import { supabase } from "./supabaseClient";
import "./App.css";

function App() {
  const [session, setSession] = useState(null);
  const [history, setHistory] = useState([]);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let interval = null;
    if (loading) {
      interval = setInterval(() => {
        setElapsedTime((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(interval);
      setElapsedTime(0);
    }
    return () => clearInterval(interval);
  }, [loading]);

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
      const backendUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/upload`, {
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
      <ParticlesBackground />
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
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '40px', overflowY: 'auto', position: 'relative', zIndex: 10, marginLeft: '250px' }}>
        <div className="container" style={{ width: '100%', maxWidth: '1000px', height: 'fit-content' }}>
          <h1>ScholarPath Upload</h1>
          
          <div className="upload-section">
          <input type="file" accept="application/pdf" onChange={handleFileChange} />
          <button onClick={handleUpload} disabled={loading || !file}>
            {loading ? `Processing... (${elapsedTime}s)` : "Submit PDF"}
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
          <div className="roadmap-grid" style={{ marginBottom: "30px" }}>
            {data.roadmap && Array.isArray(data.roadmap) && data.roadmap.length > 0 ? (
              <RoadmapFlow roadmap={data.roadmap} />
            ) : (
              <p>No roadmap could be generated.</p>
            )}
          </div>
        </div>
      )}
        </div>
      </div>
    </div>
  );
}

export default App;

