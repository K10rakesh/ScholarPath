import { useState } from "react";
import { supabase } from "../supabaseClient";
import ParticlesBackground from "./ParticlesBackground";
import "./Auth.css";

export default function Auth() {
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLogin, setIsLogin] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const handleAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg("");
    setSuccessMsg("");

    if (isLogin) {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (error) setErrorMsg(error.message || "Failed to log in.");
    } else {
      const { error } = await supabase.auth.signUp({
        email,
        password,
      });
      if (error) setErrorMsg(error.message || "Failed to sign up.");
      else {
        setSuccessMsg("Success! Check your email to confirm your account.");
        setIsLogin(true);
        setPassword("");
      }
    }
    setLoading(false);
  };

  return (
    <div className="auth-page">
      <ParticlesBackground />

      <div className="auth-card" style={{ zIndex: 10, position: "relative" }}>
        <div className="auth-header">
          <h2>{isLogin ? "Welcome Back" : "Create an Account"}</h2>
          <p>
            {isLogin
              ? "Sign in to continue to ScholarPath"
              : "Join ScholarPath to save your research roadmaps"}
          </p>
        </div>

        {errorMsg && <div className="auth-error">{errorMsg}</div>}
        {successMsg && <div className="auth-success">{successMsg}</div>}

        <form onSubmit={handleAuth} className="auth-form">
          <div className="input-group">
            <label>Email Address</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="input-group">
            <label>Password</label>
            <input
              type="password"
              placeholder="��������"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength="6"
            />
          </div>
          
          <button
            type="submit"
            className="auth-primary-btn"
            disabled={loading || !email || !password}
          >
            {loading ? "Processing..." : isLogin ? "Sign In" : "Create Account"}
          </button>
        </form>

        <div className="auth-footer">
          {isLogin ? (
            <p>
              Don&#39;t have an account?{" "}
              <span onClick={() => { setIsLogin(false); setErrorMsg(""); setSuccessMsg(""); }}>Sign up</span>
            </p>
          ) : (
            <p>
              Already have an account?{" "}
              <span onClick={() => { setIsLogin(true); setErrorMsg(""); setSuccessMsg(""); }}>Log in</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

