import { useState, useEffect, useRef } from 'react';
import { Clock, LogOut } from 'lucide-react';

interface Props {
  onStayLoggedIn: () => void;
  onLogout: () => void;
}

export default function SessionWarningModal({ onStayLoggedIn, onLogout }: Props) {
  const [countdown, setCountdown] = useState(60);
  const stayBtnRef = useRef<HTMLButtonElement>(null);

  // Focus the "Stay logged in" button when modal appears
  useEffect(() => {
    stayBtnRef.current?.focus();
  }, []);

  // Count down from 60
  useEffect(() => {
    const id = setInterval(() => {
      setCountdown((s) => {
        if (s <= 1) {
          clearInterval(id);
          onLogout();
          return 0;
        }
        return s - 1;
      });
    }, 1_000);
    return () => clearInterval(id);
  }, [onLogout]);

  // Trap focus inside modal and handle Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onStayLoggedIn();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onStayLoggedIn]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-warning-title"
      aria-describedby="session-warning-desc"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
    >
      <div className="bg-slate-800 border border-amber-600/50 rounded-xl p-6 shadow-2xl max-w-sm w-full mx-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-lg bg-amber-900/40">
            <Clock size={20} className="text-amber-400" />
          </div>
          <h2 id="session-warning-title" className="text-base font-bold text-amber-300">
            Session Expiring
          </h2>
        </div>

        <p id="session-warning-desc" className="text-sm text-slate-300 leading-relaxed mb-4">
          Your session has been idle for 14 minutes. You will be automatically
          logged out in{' '}
          <span className="font-bold text-amber-300 tabular-nums font-mono">
            {countdown}s
          </span>{' '}
          to comply with PCI DSS session security requirements.
        </p>

        <div className="flex gap-3">
          <button
            ref={stayBtnRef}
            onClick={onStayLoggedIn}
            className="flex-1 py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            Stay Logged In
          </button>
          <button
            onClick={onLogout}
            className="flex items-center gap-2 py-2.5 px-4 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-semibold transition-colors border border-slate-600 focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <LogOut size={14} />
            Log Out
          </button>
        </div>
      </div>
    </div>
  );
}
