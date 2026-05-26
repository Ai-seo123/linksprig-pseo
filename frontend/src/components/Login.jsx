import { useState } from 'react';
import { Lock, Loader2 } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const Login = ({ onLogin }) => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [captchaToken, setCaptchaToken] = useState('');
  
  // A simple simulated Captcha for local testing since Turnstile keys aren't configured yet.
  // In production, replace this with @marsidev/react-turnstile or similar.
  const handleCaptchaVerify = () => {
    setCaptchaToken('dev-captcha-token');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!captchaToken) {
      setError('Please complete the CAPTCHA verification');
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: 'POST',

        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, captchaToken })
      });
      
      const data = await response.json();
      
      if (response.ok && data.token) {
        onLogin(data.token);
      } else {
        setError(data.detail || 'Invalid password');
      }
    } catch (err) {
      setError('Cannot connect to the server. Is it running?');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel">
      <div className="text-center">
        <h1>LinkSprig Engine</h1>
        <p className="subtitle">Secure AI Processing Portal</p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="input-group">
          <label htmlFor="password">Administrator Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter secure password"
            required
            autoFocus
          />
        </div>

        {/* Simulated CAPTCHA Block */}
        <div className="captcha-container">
          {!captchaToken ? (
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
              <input type="checkbox" onChange={handleCaptchaVerify} style={{ width: 'auto' }} />
              I am human (Local CAPTCHA Bypass)
            </label>
          ) : (
            <span style={{ color: '#34d399', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              ✓ Verification complete
            </span>
          )}
        </div>

        {error && <p className="text-error text-center mb-4">{error}</p>}

        <button type="submit" className="primary-btn mt-4" disabled={loading}>
          {loading ? <Loader2 className="animate-spin" size={20} /> : <Lock size={20} />}
          {loading ? 'Authenticating...' : 'Secure Login'}
        </button>
      </form>
    </div>
  );
};

export default Login;
