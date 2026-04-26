import { motion } from 'motion/react';
import { useNavigate } from 'react-router';
import { Shield, Users } from 'lucide-react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';

export function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 mb-6 shadow-[0_0_60px_rgba(59,130,246,0.3)]">
            <Shield className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-5xl mb-4 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
            Emergency Assistance System
          </h1>
          <p className="text-gray-400 text-lg">
            Real-time coordination between guests and staff
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            <Card glowColor="blue" className="h-full flex flex-col">
              <div className="flex-1">
                <div className="w-14 h-14 rounded-xl bg-blue-500/10 flex items-center justify-center mb-6 border border-blue-500/20">
                  <Users className="w-7 h-7 text-blue-400" />
                </div>
                <h2 className="text-3xl mb-3 text-white">Guest Access</h2>
                <p className="text-gray-400 mb-8">
                  Request assistance and connect with staff for immediate support
                </p>
              </div>
              <Button
                variant="primary"
                className="w-full"
                onClick={() => navigate('/guest/auth')}
              >
                Continue as Guest
              </Button>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
          >
            <Card glowColor="rose" className="h-full flex flex-col">
              <div className="flex-1">
                <div className="w-14 h-14 rounded-xl bg-rose-500/10 flex items-center justify-center mb-6 border border-rose-500/20">
                  <Shield className="w-7 h-7 text-rose-400" />
                </div>
                <h2 className="text-3xl mb-3 text-white">Staff Portal</h2>
                <p className="text-gray-400 mb-8">
                  Monitor and respond to assistance requests in real-time
                </p>
              </div>
              <Button
                variant="danger"
                className="w-full"
                onClick={() => navigate('/staff/auth')}
              >
                Continue as Staff
              </Button>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
