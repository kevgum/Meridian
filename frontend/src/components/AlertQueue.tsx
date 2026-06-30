import { useState, useEffect } from 'react';
import { AlertTriangle, Lock, Search, MapPin, DollarSign, Clock } from 'lucide-react';
import type { Incident } from '../types';

interface Props {
  incident: Incident;
}

function useSlaCountdown(initialSeconds: number) {
  const [remaining, setRemaining] = useState(initialSeconds);

  useEffect(() => {
    const id = setInterval(() => setRemaining((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const isUrgent = remaining < 60;
  return { display: `${mins}:${secs.toString().padStart(2, '0')}`, isUrgent };
}

export default function AlertQueue({ incident }: Props) {
  const sla = useSlaCountdown(248); // 4m 08s

  return (
    <aside className="w-72 shrink-0 bg-slate-800 border border-slate-700 rounded-lg flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-slate-700 shrink-0">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Alert Queue
        </p>
        <p className="text-xs text-slate-500 mt-0.5">3 active · 1 requiring action</p>
      </div>

      {/* Background alerts (dimmed) */}
      <div className="px-3 py-2 border-b border-slate-700/50 opacity-40">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">CUST-44209</span>
          <span className="text-xs text-blue-400 font-semibold">MONITOR</span>
        </div>
        <p className="text-xs text-slate-500">Qantas charge · Sydney, NSW</p>
      </div>
      <div className="px-3 py-2 border-b border-slate-700/50 opacity-40">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">CUST-73940</span>
          <span className="text-xs text-blue-400 font-semibold">MONITOR</span>
        </div>
        <p className="text-xs text-slate-500">Electronics purchase · Melbourne, VIC</p>
      </div>

      {/* Active alert — CUST-18656 */}
      <div className="flex-1 p-3 flex flex-col gap-3 overflow-y-auto">
        {/* Severity header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-400" />
            <span className="text-sm font-bold text-amber-300">{incident.customerId}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-600/30 text-amber-300 border border-amber-500/40">
              {incident.severity}
            </span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-red-900/40 text-red-300 border border-red-600/30">
              {incident.status}
            </span>
          </div>
        </div>

        {/* Incident ID */}
        <p className="text-xs font-mono text-slate-400">{incident.incidentId}</p>

        {/* Evidence summary */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <MapPin size={12} className="text-slate-500 shrink-0" />
            <span>Darwin, NT · All 6 transactions local</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <DollarSign size={12} className="text-slate-500 shrink-0" />
            <span>A${incident.totalAmount.toFixed(2)} total · {incident.transactionCount} transactions</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <Clock size={12} className="text-slate-500 shrink-0" />
            <span>75 minutes window · 14:00–15:15 ACST</span>
          </div>
        </div>

        {/* Scores */}
        <div className="rounded-lg bg-slate-700/50 border border-slate-600/50 p-2.5 grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-xs text-slate-400">LSTM</p>
            <p className="text-sm font-bold text-blue-300 font-mono">
              {Math.round(incident.lstmScore * 100)}%
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400">SIEM</p>
            <p className="text-sm font-bold text-green-300 font-mono">0%</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Hybrid</p>
            <p className="text-sm font-bold text-amber-300 font-mono">
              {Math.round(incident.threatScore * 100)}%
            </p>
          </div>
        </div>

        {/* Trigger path note */}
        <div className="rounded-lg bg-blue-900/20 border border-blue-700/30 p-2.5">
          <p className="text-xs text-blue-300 font-semibold">Trigger: LSTM_ALONE</p>
          <p className="text-xs text-blue-200/60 mt-0.5 leading-snug">
            Hybrid score (0.444) below 0.70 threshold — LSTM_ALONE path fires because lstm ≥ 0.70
          </p>
        </div>

        {/* SLA countdown */}
        <div className={`rounded-lg p-2.5 border flex items-center justify-between ${
          sla.isUrgent
            ? 'bg-red-900/30 border-red-600/40'
            : 'bg-slate-700/50 border-slate-600/50'
        }`}>
          <div>
            <p className={`text-xs font-semibold ${sla.isUrgent ? 'text-red-400' : 'text-slate-400'}`}>
              SLA Countdown
            </p>
            <p className="text-xs text-slate-500">Response required</p>
          </div>
          <p className={`text-xl font-bold font-mono tabular-nums ${
            sla.isUrgent ? 'text-red-400' : 'text-amber-300'
          }`}>
            {sla.display}
          </p>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Action buttons */}
        <div className="space-y-2 mt-auto shrink-0">
          <button
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400"
            onClick={() => console.log('Confirm threat — will POST to ES in Day 11')}
            aria-label="Confirm threat for CUST-18656 and lock account"
          >
            <Lock size={14} />
            Confirm Threat
          </button>
          <button
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm font-semibold transition-colors border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
            onClick={() => console.log('Investigate — will open incident timeline in Day 11')}
            aria-label="Open investigation view for CUST-18656"
          >
            <Search size={14} />
            Investigate
          </button>
        </div>
      </div>
    </aside>
  );
}
