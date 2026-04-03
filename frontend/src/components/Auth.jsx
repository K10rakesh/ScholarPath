import { useState } from 'react'
import { supabase } from '../supabaseClient'

export default function Auth() {
  const [loading, setLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    if (error) alert(error.message)
    setLoading(false)
  }

  const handleSignUp = async (e) => {
    e.preventDefault()
    setLoading(true)
    const { error } = await supabase.auth.signUp({
      email,
      password,
    })
    if (error) alert(error.message)
    else alert('Check your email for the login link!')
    setLoading(false)
  }

  return (
    <div className="auth-container">
      <h2>Welcome to ScholarPath</h2>
      <p>Log in or sign up to save your research roadmap history.</p>
      <form>
        <input
          type="email"
          placeholder="Your email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          type="password"
          placeholder="Your password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <div style={{ display: 'flex', gap: '10px', marginTop: '10px', width: '100%' }}>
          <button onClick={handleLogin} disabled={loading || !email || !password} style={{ flex: 1 }}>
            {loading ? '...' : 'Log In'}
          </button>
          <button onClick={handleSignUp} disabled={loading || !email || !password} style={{ flex: 1, backgroundColor: '#2ecc71' }}>
            {loading ? '...' : 'Sign Up'}
          </button>
        </div>
      </form>
    </div>
  )
}