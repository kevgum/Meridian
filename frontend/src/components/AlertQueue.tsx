import { useState, useEffect } from 'react';
import { AlertTriangle, Lock, Search, MapPin, DollarSign, Clock, ArrowUpCircle } from 'lucide-react';
import axios from 'axios';
import type { Incident } from '../types';
import type { ToastMessage } from './Toast';

type SeverityFilter = 'ALL' | 'HIGH' | 'MONITOR';
type ChannelFilter  = 'ALL' | 'Online' | 'Card' | 'Mobile';
type TimeFilter     = 'ALL' | '<1h' | '<6h' | '<24h';

interface MonitorAlert {
  id: string;
  channel: 'Online' | 'Card' | 'Mobile';
  ageMinutes: number;
  title: string;
  location: string;
}

const MONITOR_ALERTS: MonitorAlert[] = [
  { id: 'CUST-44209', channel: 'Online', ageMinutes: 140, title: 'Qantas charge',       location: 'Sydney, NSW'    },
  { id: 'CUST-73940', channel: 'Card',   ageMinutes: 370, title: 'Electronics purchase', location: 'Melbourne, VIC' },
];

const HIGH_ALERT_CHANNEL: ChannelFilter = 'Mobile';
const HIGH_ALERT_AGE_MINUTES = 14;

function timeLimit(f: TimeFilter): number {
  if (f === '<1h')  return 60;
  if (f === '<6h')  return 360;
  if (f === '<24h') return 1440;
  return Infinity;
}

interface Props {
  incident: Incident;
  onInvestigate: () => void;
  onToast: (t: Omit<ToastMessage, 'id'>) => void;
}

function useSlaCountdown(initialSeconds: number) {
  const [remaining, setRemaining] = useState(initialSeconds);
  useEffect(() => {
    const id = setInterval(() => setRemaining((s) => Math.max(0, s - 1)), 1_000);
    return () => clearInterval(id);
  }, []);
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const isUrgent = remaining < 60;
  return { display: `${mins}:${secs.toString().padStart(2, '0')}`, isUrgent, remaining };
}

function chipClass(active: boolean) {
  return `px-2 py-0.5 rounded text-[10px] font-semibold transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400 ${
    active
      ? 'bg-blue-600 text-white'
      : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-200'
  }`;
}

function ageLabel(minutes: number): string {
  return minutes < 60 ? `${minutes}m ago` : `${Math.round(minutes / 60)}h ago`;
}

export default function AlertQueue({ incident, onInvestigate, onToast }: Props) {
  const sla = useSlaCountdown(248);
  const [confirming, setConfirming]         = useState(false);
  const [confirmed, setConfirmed]           = useState(false);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL');
  const [channelFilter, setChannelFilter]   = useState<ChannelFilter>('ALL');
  const [timeFilter, setTimeFilter]         = useState<TimeFilter>('ALL');
  const [escalated, setEscalated]           = useState(false);

  function handleEscalate() {
    setEscalated(true);
    onToast({
      message: `Incident ${incident.incidentId} escalated to Senior Security Engineer`,
      variant: 'success',
    });
  }

  const limit = timeLimit(timeFilter);

  const showHighAlert =
    (severityFilter === 'ALL' || severityFilter === 'HIGH') &&
    (channelFilter  === 'ALL' || channelFilter  === HIGH_ALERT_CHANNEL) &&
    HIGH_ALERT_AGE_MINUTES <= limit;

  const visibleMonitor = MONITOR_ALERTS.filter(
    (a) =>
      (severityFilter === 'ALL' || severityFilter === 'MONITOR') &&
      (channelFilter  === 'ALL' || a.channel === channelFilter) &&
      a.ageMinutes <= limit,
  );

  const totalVisible = (showHighAlert ? 1 : 0) + visibleMonitor.length;

  async function handleConfirmThreat() {
    setConfirming(true);
    const payload = {
      status: 'CONFIRMED',
      analyst_id: 'kevin.mugambi',
      confirmed_at: new Date().toISOString(),
      action: incident.action,
    };
    try {
      await axios.post(
        `/api/meridian-incidents-${new Date().toISOString().slice(0, 10).replace(/-/g, '.')}/_doc/${incident.incidentId}`,
        payload,
        { timeout: 3_000 },
      );
      setConfirmed(true);
      onToast({ message: `Incident ${incident.incidentId} confirmed — audit log updated`, variant: 'success' });
    } catch {
      setConfirmed(true);
      onToast({ message: `Incident ${incident.incidentId} confirmed (demo mode)`, variant: 'success' });
    } finally {
      setConfirming(false);
    }
  }

  return (
    <aside
      aria-label="Alert queue"
      className="w-72 shrink-0 bg-slate-800 border border-slate-700 rounded-lg flex flex-col overflow-hidden"
    >
      {/* Header + filters */}
      <div className="px-3 py-2.5 border-b border-slate-700 shrink-0 space-y-2">
        <div>
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Alert Queue</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {totalVisible} active · {showHighAlert ? 1 : 0} requiring action
          </p>
        </div>

        {/* US-08 — severity filter */}
        <div role="group" aria-label="Filter by severity" className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-500 w-11 shrink-0">Severity</span>
          {(['ALL', 'HIGH', 'MONITOR'] as SeverityFilter[]).map((v) => (
            <button
              key={v}
              onClick={() => setSeverityFilter(v)}
              aria-pressed={severityFilter === v}
              className={chipClass(severityFilter === v)}
            >
              {v}
            </button>
          ))}
        </div>

        {/* US-08 — channel filter */}
        <div role="group" aria-label="Filter by channel" className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-500 w-11 shrink-0">Channel</span>
          {(['ALL', 'Online', 'Card', 'Mobile'] as ChannelFilter[]).map((v) => (
            <button
              key={v}
              onClick={() => setChannelFilter(v)}
              aria-pressed={channelFilter === v}
              className={chipClass(channelFilter === v)}
            >
              {v}
            </button>
          ))}
        </div>

        {/* US-08 — time filter */}
        <div role="group" aria-label="Filter by time window" className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-500 w-11 shrink-0">Time</span>
          {(['ALL', '<1h', '<6h', '<24h'] as TimeFilter[]).map((v) => (
            <button
              key={v}
              onClick={() => setTimeFilter(v)}
              aria-pressed={timeFilter === v}
              className={chipClass(timeFilter === v)}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* MONITOR alerts — filtered */}
      {visibleMonitor.map((a) => (
        <div key={a.id} className="px-3 py-2 border-b border-slate-700/50 opacity-50">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">{a.id}</span>
            <span className="text-xs text-blue-400 font-semibold">MONITOR</span>
          </div>
          <p className="text-xs text-slate-500">{a.title} · {a.location}</p>
          <p className="text-[10px] text-slate-600 mt-0.5">
            {a.channel} · {ageLabel(a.ageMinutes)}
          </p>
        </div>
      ))}

      {/* Empty state */}
      {totalVisible === 0 && (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-slate-500 text-center">No alerts match the selected filters</p>
        </div>
      )}

      {/* Active HIGH alert — CSS-hidden when filtered out */}
      <div
        className={`flex-1 p-3 flex flex-col gap-3 overflow-y-auto${showHighAlert ? '' : ' hidden'}`}
        aria-live="polite"
        aria-atomic="false"
        aria-label="Active alert details"
        aria-hidden={!showHighAlert}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-400" aria-hidden="true" />
            <span className="text-sm font-bold text-amber-300">{incident.customerId}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-600/30 text-amber-300 border border-amber-500/40">
              {incident.severity}
            </span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-red-900/40 text-red-300 border border-red-600/30">
              {confirmed ? 'CONFIRMED' : incident.status}
            </span>
          </div>
        </div>

        <p className="text-xs font-mono text-slate-400">{incident.incidentId}</p>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <MapPin size={12} className="text-slate-500 shrink-0" aria-hidden="true" />
            <span>Darwin, NT · All 6 transactions local</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <DollarSign size={12} className="text-slate-500 shrink-0" aria-hidden="true" />
            <span>A${incident.totalAmount.toFixed(2)} total · {incident.transactionCount} transactions</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <Clock size={12} className="text-slate-500 shrink-0" aria-hidden="true" />
            <span>75 minutes window · 14:00–15:15 ACST</span>
          </div>
        </div>

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

        <div className="rounded-lg bg-blue-900/20 border border-blue-700/30 p-2.5">
          <p className="text-xs text-blue-300 font-semibold">Trigger: LSTM_ALONE</p>
          <p className="text-xs text-blue-200/60 mt-0.5 leading-snug">
            Hybrid score (0.444) below 0.70 — LSTM_ALONE fires because lstm ≥ 0.70
          </p>
        </div>

        {/* SLA countdown */}
        <div
          className={`rounded-lg p-2.5 border flex items-center justify-between ${
            sla.isUrgent ? 'bg-red-900/30 border-red-600/40' : 'bg-slate-700/50 border-slate-600/50'
          }`}
          aria-label={`SLA countdown: ${sla.display} remaining`}
        >
          <div>
            <p className={`text-xs font-semibold ${sla.isUrgent ? 'text-red-400' : 'text-slate-400'}`}>
              SLA Countdown
            </p>
            <p className="text-xs text-slate-500">Response required</p>
          </div>
          <p
            className={`text-xl font-bold font-mono tabular-nums ${sla.isUrgent ? 'text-red-400' : 'text-amber-300'}`}
            aria-live="polite"
            aria-label={`${sla.display} remaining`}
          >
            {sla.display}
          </p>
        </div>

        <div className="flex-1" />

        {/* Action buttons */}
        <div className="space-y-2 mt-auto shrink-0">
          <button
            onClick={handleConfirmThreat}
            disabled={confirming || confirmed}
            aria-label={confirmed ? 'Threat confirmed' : 'Confirm threat for CUST-18656 and lock account'}
            className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400 ${
              confirmed
                ? 'bg-green-700 text-green-100 cursor-default'
                : 'bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-60 disabled:cursor-wait'
            }`}
          >
            <Lock size={14} aria-hidden="true" />
            {confirming ? 'Confirming…' : confirmed ? 'Threat Confirmed' : 'Confirm Threat'}
          </button>
          <button
            onClick={onInvestigate}
            aria-label="Open investigation drawer for CUST-18656"
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm font-semibold transition-colors border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <Search size={14} aria-hidden="true" />
            Investigate
          </button>
          {/* US-11: escalate to Senior Security Engineer */}
          <button
            onClick={handleEscalate}
            disabled={escalated}
            aria-label={escalated ? 'Escalated to Senior Security Engineer' : 'Escalate to Senior Security Engineer'}
            className={`w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-xs font-semibold transition-colors border focus:outline-none focus:ring-2 focus:ring-purple-400 ${
              escalated
                ? 'bg-purple-900/40 border-purple-700/40 text-purple-300 cursor-default'
                : 'bg-slate-700/50 border-slate-600 text-slate-400 hover:bg-slate-600 hover:text-slate-200'
            }`}
          >
            <ArrowUpCircle size={13} aria-hidden="true" />
            {escalated ? 'Escalated' : 'Escalate to Senior Engineer'}
          </button>
        </div>
      </div>
    </aside>
  );
}
