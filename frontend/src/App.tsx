import { useState, useCallback } from 'react';
import './index.css';
import TopBar from './components/TopBar';
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
import { CUST18656_SIEM_RESULT, HISTORY_EVENTS } from './data/mockData';
import { KPI_STATS } from './data/mockData';

type AppState = 'active' | 'warn' | 'expired';

export default function App() {
  const { transactions, incident, isLive } = useElasticPolling();
  const { announce } = useA11yAnnouncer();

  const [appState, setAppState] = useState<AppState>('active');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  // Idle timer callbacks
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

  // Toast helpers
  const addToast = useCallback((t: Omit<ToastMessage, 'id'>) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...t, id }]);
    announce(t.message);
  }, [announce]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Session expired screen
  if (appState === 'expired') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-center space-y-4 p-8 bg-slate-800 border border-slate-700 rounded-xl max-w-sm">
          <p className="text-2xl font-bold text-slate-100">Session Expired</p>
          <p className="text-sm text-slate-400">
            Your session was terminated after 15 minutes of inactivity to comply
            with PCI DSS Req 8.2.8.
          </p>
          <button
            onClick={() => { setAppState('active'); resetIdle(); }}
            className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            Log In Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100">
        <TopBar stats={KPI_STATS} isLive={isLive} />

        <main id="main-content" className="flex flex-1 gap-3 p-3 min-h-0 overflow-hidden">
          <TransactionFeed transactions={transactions} />
          <DetectionPanel
            siemResult={CUST18656_SIEM_RESULT}
            lstmScore={incident.lstmScore}
            incident={incident}
          />
          <AlertQueue
            incident={incident}
            onInvestigate={() => setDrawerOpen(true)}
            onToast={addToast}
          />
        </main>

        <div className="flex gap-3 px-3 pb-3 shrink-0" style={{ height: 240 }}>
          <HybridChart events={HISTORY_EVENTS} />
          <ComplianceBadges />
        </div>
      </div>

      {/* Overlays */}
      {drawerOpen && (
        <InvestigateDrawer
          incident={incident}
          onClose={() => setDrawerOpen(false)}
        />
      )}

      {appState === 'warn' && (
        <SessionWarningModal
          onStayLoggedIn={() => { setAppState('active'); resetIdle(); }}
          onLogout={() => setAppState('expired')}
        />
      )}

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </>
  );
}
