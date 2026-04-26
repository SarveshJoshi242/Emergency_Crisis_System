import { motion } from 'motion/react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ArrowLeft } from 'lucide-react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Input } from '../components/Input';

export function GuestAuth() {
  const navigate = useNavigate();
  const [isSignUp, setIsSignUp] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    phone: '',
    roomId: ''
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Using the session/start endpoint as the proxy for login/signup since there's no auth
    const endpoint = 'http://localhost:8000/guest/session/start';

    try {
      if (isSignUp) {
        // Signup handler
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          // Sending form data as JSON
          body: JSON.stringify({ 
            room_id: formData.roomId,
            email: formData.email,
            phone: formData.phone
          })
        });

        if (!res.ok) throw new Error(`Signup failed with status ${res.status}`);
        
        const data = await res.json();
        console.log('Signup success. Response:', data);
        
        // Store minimal response in localStorage
        localStorage.setItem('guest_session_id', data.session_id || 'test-id');
        navigate('/dashboard');
      } else {
        // Login handler
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          // Sending required credentials
          body: JSON.stringify({ 
            room_id: formData.roomId,
            phone: formData.phone
          })
        });

        if (!res.ok) throw new Error(`Login failed with status ${res.status}`);
        
        const data = await res.json();
        console.log('Login success. Response:', data);

        // Store minimal response in localStorage
        localStorage.setItem('guest_session_id', data.session_id || 'test-id');
        navigate('/dashboard');
      }
    } catch (err: any) {
      console.error(err);
      alert(err.message || 'An error occurred while connecting to the backend.');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-gray-400 hover:text-white mb-8 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Home
        </button>

        <Card glowColor="blue">
          <motion.div
            key={isSignUp ? 'signup' : 'signin'}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <h2 className="text-3xl mb-2 text-white">
              Guest {isSignUp ? 'Sign Up' : 'Sign In'}
            </h2>
            <p className="text-gray-400 mb-8">
              {isSignUp
                ? 'Create an account to request assistance'
                : 'Welcome back! Sign in to continue'}
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              {!isSignUp && (
                <Input
                  label="Phone Number"
                  type="tel"
                  placeholder="+1 (555) 000-0000"
                  required
                  value={formData.phone}
                  onChange={(e) =>
                    setFormData({ ...formData, phone: e.target.value })
                  }
                />
              )}

              {isSignUp && (
                <>
                  <Input
                    label="Email"
                    type="email"
                    placeholder="guest@example.com"
                    required
                    value={formData.email}
                    onChange={(e) =>
                      setFormData({ ...formData, email: e.target.value })
                    }
                  />
                  <Input
                    label="Phone Number"
                    type="tel"
                    placeholder="+1 (555) 000-0000"
                    required
                    value={formData.phone}
                    onChange={(e) =>
                      setFormData({ ...formData, phone: e.target.value })
                    }
                  />
                </>
              )}

              <Input
                label="Room ID"
                type="text"
                placeholder="R-2024-1234"
                required
                value={formData.roomId}
                onChange={(e) =>
                  setFormData({ ...formData, roomId: e.target.value })
                }
              />

              <Button variant="primary" type="submit" className="w-full mt-6">
                {isSignUp ? 'Create Account' : 'Sign In'}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <button
                onClick={() => setIsSignUp(!isSignUp)}
                className="text-blue-400 hover:text-blue-300 transition-colors"
              >
                {isSignUp
                  ? 'Already have an account? Sign In'
                  : "Don't have an account? Sign Up"}
              </button>
            </div>
          </motion.div>
        </Card>
      </div>
    </div>
  );
}