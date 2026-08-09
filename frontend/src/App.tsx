import { useState, useCallback } from 'react';
import { ShieldCheck } from 'lucide-react';
import './index.css';
import TopBar from './components/TopBar';
import StatRail from './components/StatRail';
import TransactionFeed from './components/TransactionFeed';
import DetectionPanel from './components/DetectionPanel';
import AlertQueue from './components/AlertQueue';
import HybridChart from './components/HybridChart';
import ComplianceBadges from './components/ComplianceBadges';
import InvestigateDrawer from './components/InvestigateDrawer';
import SessionWarningModal from './components/SessionWarningModal';
import Toast, { type ToastMessage } from './components/Toast';
import { useElasticPolling } from './hooks/useElasticPolling';
import { useIdleTimer } from './hooks/useIdleTimer';
import { useA11yAnnouncer } from './hooks/useA11yAnnouncer';

type AppState = 'active' | 'warn' | 'expired';

export default function App() {
  const { transactions, incident, siemResult, history, kpiStats, isLive } = useElasticPolling();
  const { announce } = useA11yAnnouncer();

  const [appState, setAppState] = useState<AppState>('active');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const handleWarn = useCallback(() => setAppState('warn'), []);
  const handleLogout = useCallback(() => setAppState('expired'), []);
  const handleReset = useCallback(() => {
    if (appState === 'warn') setAppState('active');
  }, [appState]);

  const { reset: resetIdle } = useIdleTimer({
    onWarn: handleWarn,
    onLogout: handleLogout,
    onReset: handleReset,
  });

  const addToast = useCallback(
    (t: Omit<ToastMessage, 'id'>) => {
      const id = crypto.randomUUID();
      setToasts((prev) => [...prev, { ...t, id }]);
      announce(t.message);
    },
    [announce],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  if (appState === 'expired') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-paper-2 p-4">
        <div className="w-full max-w-sm rounded-md border border-rule bg-paper p-6 shadow-[var(--shadow-whisper)]">
          <ShieldCheck size={20} className="text-accent" aria-hidden="true" />
          <h1 className="u-display mt-3 text-lg text-ink">Session ended</h1>
          <p className="mt-2 text-xs leading-relaxed text-ink-2">
            You were signed out after 15 minutes of inactivity, per PCI DSS Req 8.2.8.
            Nothing was lost — the case is still open in the queue.
          </p>
          <button
            type="button"
            onClick={() => {
              setAppState('active');
              resetIdle();
            }}
            className="btn btn--primary mt-5 w-full"
          >
            Sign back in
          </button>
        </div>
      </main>
    );
  }

  return (
    <>
      <div className="flex min-h-screen flex-col bg-paper text-ink">
        <TopBar stats={kpiStats} isLive={isLive} />
        <StatRail stats={kpiStats} />

        {/* The workbench: feed on the left rail, the case in the middle, the
            queue and its actions on the right rail. Column widths are uneven
            on purpose — the case detail is what an analyst actually reads. */}
        <main
          id="main-content"
          className="flex min-h-0 flex-1 flex-col lg:flex-row"
        >
          <TransactionFeed transactions={transactions} />
          <DetectionPanel
            siemResult={siemResult}
            lstmScore={incident.lstmScore}
            incident={incident}
          />
          <AlertQueue
            incident={incident}
            transactions={transactions}
            onInvestigate={() => setDrawerOpen(true)}
            onToast={addToast}
          />
        </main>

        {/* Context strip — history and standing obligations, below the work. */}
        <div className="flex shrink-0 flex-col lg:h-56 lg:flex-row">
          <HybridChart events={history} />
          <ComplianceBadges />
        </div>

        {/* Ft2 — one inline line that closes the page. */}
        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-1 border-t border-rule bg-paper-2 px-4 py-3 text-micro text-muted sm:px-6">
          <p>
            <span className="u-display text-ink">Meridian Sentinel</span> — hybrid fraud
            detection for Meridian Financial Services
          </p>
          <p className="font-mono">
            threat = behaviour × 0.60 + rules × 0.40 · flag at 0.70 · v1.0.0-prototype
          </p>
        </footer>
      </div>

      {drawerOpen && (
        <InvestigateDrawer
          incident={incident}
          transactions={transactions}
          onClose={() => setDrawerOpen(false)}
        />
      )}

      {appState === 'warn' && (
        <SessionWarningModal
          onStayLoggedIn={() => {
            setAppState('active');
            resetIdle();
          }}
          onLogout={() => setAppState('expired')}
        />
      )}

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </>
  );
}
