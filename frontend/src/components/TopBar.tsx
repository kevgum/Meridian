import { Shield, Activity, AlertTriangle, TrendingDown, User, Wifi, WifiOff } from 'lucide-react';
import type { KPIStats } from '../types';

interface Props {
  stats: KPIStats;
  isLive: boolean;
}

interface KPITileProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  highlight?: boolean;
}

function KPITile({ label, value, sub, icon, highlight }: KPITileProps) {
  return (
    <div className={`flex items-center gap-3 px-5 py-3 rounded-lg border ${
      highlight
        ? 'bg-red-950/40 border-red-700/50'
        : 'bg-slate-800 border-slate-700'
    }`}>
      <div className={`p-2 rounded-md ${highlight ? 'text-red-400' : 'text-blue-400'}`}>
        {icon}
      </div>
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wider font-medium">{label}</p>
        <p className={`text-xl font-bold leading-tight ${highlight ? 'text-red-400' : 'text-slate-100'}`}>
          {value}
        </p>
        {sub && <p className="text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}

export default function TopBar({ stats, isLive }: Props) {
  const now = new Date().toLocaleTimeString('en-AU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  });

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-slate-900 border-b border-slate-700 gap-4 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0">
        <Shield className="text-blue-500" size={22} />
        <div>
          <p className="text-sm font-bold text-slate-100 tracking-tight leading-none">
            MERIDIAN SENTINEL
          </p>
          <p className="text-xs text-slate-500 leading-none mt-0.5">v3.2 — SOC Dashboard</p>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="flex items-center gap-3 flex-1 justify-center flex-wrap">
        <KPITile
          label="Transactions Today"
          value={stats.transactionsToday.toLocaleString()}
          icon={<Activity size={16} />}
        />
        <KPITile
          label="Detection Rate"
          value={`${stats.detectionRate}%`}
          sub="at threshold 0.90"
          icon={<TrendingDown size={16} />}
        />
        <KPITile
          label="False Positive Rate"
          value={`${stats.fpr}%`}
          icon={<TrendingDown size={16} />}
        />
        <KPITile
          label="Active Alerts"
          value={String(stats.activeAlerts)}
          icon={<AlertTriangle size={16} />}
          highlight
        />
      </div>

      {/* LIVE / DEMO indicator + analyst */}
      <div className="flex items-center gap-3 shrink-0">
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold border ${
            isLive
              ? 'bg-green-900/40 border-green-600/50 text-green-400'
              : 'bg-slate-700/60 border-slate-600/50 text-slate-400'
          }`}
          aria-label={isLive ? 'Connected to live Elasticsearch' : 'Demo mode — using mock data'}
          title={isLive ? 'Connected to live Elasticsearch' : 'Demo mode — mock data'}
        >
          {isLive ? <Wifi size={11} aria-hidden="true" /> : <WifiOff size={11} aria-hidden="true" />}
          {isLive ? 'LIVE' : 'DEMO'}
        </div>

        <div className="text-right">
          <p className="text-xs text-slate-400 leading-none">Analyst</p>
          <p className="text-sm font-semibold text-slate-100 leading-tight">
            {stats.analystName}
          </p>
          <p className="text-xs text-slate-500 leading-none mt-0.5 font-mono">{now}</p>
        </div>
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center" aria-hidden="true">
          <User size={14} className="text-white" />
        </div>
      </div>
    </header>
  );
}
