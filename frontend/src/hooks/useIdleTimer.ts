import { useEffect, useRef, useCallback } from 'react';

const WARN_MS = 14 * 60 * 1000;  // 14 minutes
const LOGOUT_MS = 15 * 60 * 1000; // 15 minutes

const ACTIVITY_EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'] as const;

interface UseIdleTimerOptions {
  onWarn: () => void;
  onLogout: () => void;
  onReset: () => void;
}

/**
 * Tracks user inactivity. Fires onWarn at 14 min, onLogout at 15 min.
 * Calling the returned reset() function restarts both timers.
 */
export function useIdleTimer({ onWarn, onLogout, onReset }: UseIdleTimerOptions) {
  const warnTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logoutTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (warnTimer.current) clearTimeout(warnTimer.current);
    if (logoutTimer.current) clearTimeout(logoutTimer.current);
  }, []);

  const reset = useCallback(() => {
    clearTimers();
    onReset();
    warnTimer.current = setTimeout(onWarn, WARN_MS);
    logoutTimer.current = setTimeout(onLogout, LOGOUT_MS);
  }, [clearTimers, onWarn, onLogout, onReset]);

  useEffect(() => {
    reset();
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => {
      clearTimers();
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [reset, clearTimers]);

  return { reset };
}
