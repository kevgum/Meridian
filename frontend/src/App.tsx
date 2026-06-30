import './index.css';
import TopBar from './components/TopBar';
import TransactionFeed from './components/TransactionFeed';
import DetectionPanel from './components/DetectionPanel';
import AlertQueue from './components/AlertQueue';
import HybridChart from './components/HybridChart';
import ComplianceBadges from './components/ComplianceBadges';
import {
  KPI_STATS,
  FEED_TRANSACTIONS,
  CUST18656_SIEM_RESULT,
  CUST18656_INCIDENT,
  HISTORY_EVENTS,
} from './data/mockData';

export default function App() {
  return (
    <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100">
      {/* Top bar — full width */}
      <TopBar stats={KPI_STATS} />

      {/* Main content — 3 columns */}
      <main className="flex flex-1 gap-3 p-3 min-h-0 overflow-hidden">
        <TransactionFeed transactions={FEED_TRANSACTIONS} />
        <DetectionPanel
          siemResult={CUST18656_SIEM_RESULT}
          lstmScore={CUST18656_INCIDENT.lstmScore}
          incident={CUST18656_INCIDENT}
        />
        <AlertQueue incident={CUST18656_INCIDENT} />
      </main>

      {/* Bottom row — chart + compliance */}
      <div className="flex gap-3 px-3 pb-3 shrink-0" style={{ height: 240 }}>
        <HybridChart events={HISTORY_EVENTS} />
        <ComplianceBadges />
      </div>
    </div>
  );
}
