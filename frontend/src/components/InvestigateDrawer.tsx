import { useEffect, useRef } from 'react';
import { X, MapPin, Clock, DollarSign, Brain, Zap, AlertTriangle } from 'lucide-react';
import type { Incident } from '../types';
import { FEED_TRANSACTIONS } from '../data/mockData';

interface Props {
  incident: Incident;
  onClose: () => void;
}

export default function InvestigateDrawer({ incident, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const activeTxns = FEED_TRANSACTIONS.filter((t) => t.isActive);

  // Focus close button on open
  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  // Close on Escape; trap focus inside drawer
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab') {
        const focusable = drawerRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusable || focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const drawerRef = useRef<HTMLDivElement>(null);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-slate-900 border-l border-slate-700 shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700 shrink-0">
          <div className="flex items-center gap-3">
            <AlertTriangle size={16} className="text-amber-400" />
            <div>
              <h2 id="drawer-title" className="text-sm font-bold text-slate-100">
                {incident.customerId} — Investigation
              </h2>
              <p className="text-xs text-slate-500 font-mono">{incident.incidentId}</p>
            </div>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close investigation drawer"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-5">
          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
              <MapPin size={14} className="text-slate-500 mx-auto mb-1" />
              <p className="text-xs text-slate-400">Location</p>
              <p className="text-xs font-semibold text-slate-200 mt-0.5">Darwin, NT</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
              <Clock size={14} className="text-slate-500 mx-auto mb-1" />
              <p className="text-xs text-slate-400">Window</p>
              <p className="text-xs font-semibold text-slate-200 mt-0.5">75 minutes</p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
              <DollarSign size={14} className="text-slate-500 mx-auto mb-1" />
              <p className="text-xs text-slate-400">Total</p>
              <p className="text-xs font-semibold text-slate-200 mt-0.5">
                A${incident.totalAmount.toFixed(2)}
              </p>
            </div>
          </div>

          {/* Transaction timeline */}
          <div>
            <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Transaction Timeline
            </p>
            <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
              <table className="w-full text-xs" role="table" aria-label="CUST-18656 transaction timeline">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/80">
                    <th scope="col" className="text-left px-3 py-2 text-slate-400 font-semibold">Time</th>
                    <th scope="col" className="text-left px-3 py-2 text-slate-400 font-semibold">Merchant</th>
                    <th scope="col" className="text-right px-3 py-2 text-slate-400 font-semibold">Amount</th>
                    <th scope="col" className="text-right px-3 py-2 text-slate-400 font-semibold">LSTM</th>
                  </tr>
                </thead>
                <tbody>
                  {activeTxns.map((tx, i) => (
                    <tr
                      key={tx.id}
                      className={`border-b border-slate-700/50 ${i % 2 === 0 ? '' : 'bg-slate-800/30'}`}
                    >
                      <td className="px-3 py-2 text-slate-400 font-mono whitespace-nowrap">
                        {new Date(tx.timestamp).toLocaleTimeString('en-AU', {
                          hour: '2-digit',
                          minute: '2-digit',
                          hour12: false,
                        })}
                      </td>
                      <td className="px-3 py-2 text-slate-200 truncate max-w-32">{tx.merchantName}</td>
                      <td className="px-3 py-2 text-slate-200 text-right tabular-nums font-mono">
                        ${tx.amount.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={`font-mono font-semibold ${tx.lstmScore >= 0.70 ? 'text-amber-400' : 'text-slate-400'}`}>
                          {Math.round(tx.lstmScore * 100)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Hybrid score breakdown */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Brain size={13} className="text-blue-400" />
              <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Hybrid Score Breakdown
              </p>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-2 font-mono text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">LSTM score</span>
                <span className="text-blue-300">{incident.lstmScore.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>× LSTM weight</span>
                <span>× 0.60</span>
              </div>
              <div className="flex justify-between border-t border-slate-700 pt-2">
                <span className="text-slate-400">LSTM contribution</span>
                <span className="text-blue-300">{(incident.lstmScore * 0.6).toFixed(3)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">SIEM score</span>
                <span className="text-green-300">{incident.siemScore.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>× SIEM weight</span>
                <span>× 0.40</span>
              </div>
              <div className="flex justify-between border-t border-slate-700 pt-2">
                <span className="text-slate-400">SIEM contribution</span>
                <span className="text-green-300">{(incident.siemScore * 0.4).toFixed(3)}</span>
              </div>
              <div className="flex justify-between border-t border-slate-600 pt-2 text-sm">
                <span className="text-slate-200 font-semibold">Hybrid score</span>
                <span className="text-amber-300 font-bold">{incident.threatScore.toFixed(3)}</span>
              </div>
            </div>
          </div>

          {/* Trigger path */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Zap size={13} className="text-amber-400" />
              <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Trigger Path
              </p>
            </div>
            <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-3 space-y-2 text-xs">
              <p className="text-amber-300 font-semibold">LSTM_ALONE</p>
              <p className="text-slate-300 leading-snug">
                Hybrid score 0.444 is below the 0.70 combined threshold. However,
                lstm_score 0.74 ≥ 0.70 activates the LSTM_ALONE path, which fires
                the playbook independently of the SIEM score.
              </p>
              <div className="border-t border-amber-700/30 pt-2">
                <p className="text-slate-400">
                  Playbook action:{' '}
                  <span className="text-amber-300 font-semibold">{incident.action}</span>
                </p>
                <p className="text-slate-400 mt-0.5">
                  Severity:{' '}
                  <span className="text-amber-300 font-semibold">{incident.severity}</span>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-700 shrink-0">
          <button
            onClick={onClose}
            className="w-full py-2.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm font-semibold transition-colors border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            Close Investigation
          </button>
        </div>
      </div>
    </>
  );
}
