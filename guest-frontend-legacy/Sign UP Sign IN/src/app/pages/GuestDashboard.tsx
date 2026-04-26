import { motion } from 'motion/react';
import { useNavigate } from 'react-router';
import { LogOut } from 'lucide-react';
import { Button } from '../components/Button';

export function GuestDashboard() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 flex flex-col">
      <div className="flex justify-between items-center px-8 py-5 border-b border-gray-800/60">
        <span className="text-gray-400 text-sm tracking-widest uppercase">Guest Portal</span>
        <Button variant="outline" onClick={() => navigate('/')}>
          <LogOut className="w-4 h-4 mr-2" />
          Sign Out
        </Button>
      </div>

      <div className="flex flex-1 items-center justify-center p-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center"
        >
          <h1 className="text-4xl text-white mb-4">Dashboard</h1>
          <p className="text-gray-500">Dashboard content will be added later.</p>
        </motion.div>
      </div>
    </div>
  );
}
