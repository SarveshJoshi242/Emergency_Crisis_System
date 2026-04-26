import { motion } from 'motion/react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ArrowLeft } from 'lucide-react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Input } from '../components/Input';

export function StaffAuth() {
  const navigate = useNavigate();
  const [isSignUp, setIsSignUp] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    password: ''
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/staff/dashboard');
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

        <Card glowColor="rose">
          <motion.div
            key={isSignUp ? 'signup' : 'signin'}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <h2 className="text-3xl mb-2 text-white">
              Staff {isSignUp ? 'Sign Up' : 'Sign In'}
            </h2>
            <p className="text-gray-400 mb-8">
              {isSignUp
                ? 'Create a staff account to manage assistance requests'
                : 'Access the staff portal'}
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              {isSignUp && (
                <Input
                  label="Full Name"
                  type="text"
                  placeholder="John Doe"
                  required
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                />
              )}

              <Input
                label="Email"
                type="email"
                placeholder="staff@example.com"
                required
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
              />

              {isSignUp && (
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

              <Input
                label="Password"
                type="password"
                placeholder="••••••••"
                required
                value={formData.password}
                onChange={(e) =>
                  setFormData({ ...formData, password: e.target.value })
                }
              />

              <Button variant="danger" type="submit" className="w-full mt-6">
                {isSignUp ? 'Create Account' : 'Sign In'}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <button
                onClick={() => setIsSignUp(!isSignUp)}
                className="text-rose-400 hover:text-rose-300 transition-colors"
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
