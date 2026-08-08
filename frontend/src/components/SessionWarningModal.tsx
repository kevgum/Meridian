import { useState, useEffect, useRef } from 'react';
import { Clock, LogOut } from 'lucide-react';

interface Props {
  onStayLoggedIn: () => void;
  onLogout: () => void;
}

export default function SessionWarningModal({ onStayLoggedIn, onLogout }: Props) {
  const [countdown, setCountdown] = useState(60);
  const stayBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    stayBtnRef.current?.focus();
  }, []);

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
      className="anim-backdrop fixed inset-0 flex items-center justify-center bg-ink/35 p-4"
      style={{ zIndex: 'var(--z-modal)' }}
    >
      <div className="anim-dialog w-full max-w-sm rounded-md border border-warn-edge bg-paper p-6 shadow-[var(--shadow-overlay)]">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-warn-wash text-warn">
            <Clock size={18} aria-hidden="true" />
          </span>
          <h2 id="session-warning-title" className="u-display text-base text-ink">
            Session expiring
          </h2>
        </div>

        <p id="session-warning-desc" className="mt-4 text-xs leading-relaxed text-ink-2">
          This session has been idle for 14 minutes. You will be signed out in{' '}
          <span className="font-mono font-bold text-warn" aria-live="off">
            {countdown}s
          </span>{' '}
          to satisfy the PCI DSS session-security requirement.
        </p>

        {/* Stacks below 640px — two nowrap labels will not sit side by side in
            a 240px-wide dialog. */}
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <button
            ref={stayBtnRef}
            type="button"
            onClick={onStayLoggedIn}
            className="btn btn--primary flex-1"
          >
            Stay signed in
          </button>
          <button type="button" onClick={onLogout} className="btn btn--secondary">
            <LogOut size={13} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
