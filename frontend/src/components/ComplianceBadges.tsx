import { Shield, Lock, Eye } from 'lucide-react';

interface Badge {
  framework: string;
  status: string;
  detail: string;
  icon: React.ReactNode;
  colour: string;
}

const BADGES: Badge[] = [
  {
    framework: 'APRA CPS 234',
    status: 'ACTIVE',
    detail: 'Para 15–38 · Incident management, audit trail, information security controls',
    icon: <Shield size={14} />,
    colour: 'text-green-400',
  },
  {
    framework: 'PCI DSS v4.0',
    status: 'ACTIVE',
    detail: 'Req 7–10 · RBAC, session timeout, immutable audit logs, network isolation',
    icon: <Lock size={14} />,
    colour: 'text-blue-400',
  },
  {
    framework: 'Privacy Act 1988',
    status: 'ACTIVE',
    detail: 'SHA-256 PII hashing at Logstash ingestion · Raw values never stored',
    icon: <Eye size={14} />,
    colour: 'text-purple-400',
  },
];

export default function ComplianceBadges() {
  return (
    <div className="w-72 shrink-0 bg-slate-800 border border-slate-700 rounded-lg p-4 flex flex-col">
      <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3 shrink-0">
        Compliance Status
      </p>

      <div className="space-y-3">
        {BADGES.map((b) => (
          <div
            key={b.framework}
            className="flex items-start gap-3 p-3 rounded-lg bg-slate-700/50 border border-slate-600/50"
          >
            <div className={`mt-0.5 shrink-0 ${b.colour}`}>{b.icon}</div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className={`text-xs font-bold ${b.colour}`}>{b.framework}</p>
                <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-green-900/40 text-green-400 border border-green-700/30">
                  {b.status}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 leading-snug">{b.detail}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Footer note */}
      <div className="mt-3 pt-3 border-t border-slate-700">
        <p className="text-xs text-slate-500 leading-snug">
          Full control mapping:{' '}
          <span className="text-slate-400 font-mono">compliance/control_mapping.md</span>
        </p>
        <p className="text-xs text-slate-600 mt-1">
          AES-256 at rest: requires ES Platinum — documented as production control
        </p>
      </div>
    </div>
  );
}
