import { Shield, Lock, Eye, Download } from 'lucide-react';

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

const COMPLIANCE_EXPORT = {
  generated_at: new Date().toISOString(),
  system: 'Meridian Sentinel v1.0.0-prototype',
  frameworks: [
    {
      framework: 'APRA CPS 234',
      status: 'ACTIVE',
      paragraphs: 'Para 15–38',
      controls: ['Incident management', 'Audit trail', 'Information security controls'],
      evidence: 'results/acceptance_test_report.md',
    },
    {
      framework: 'PCI DSS v4.0',
      status: 'ACTIVE',
      requirements: 'Req 7–10',
      controls: ['RBAC (6 roles)', '15-min session timeout', 'Immutable audit logs', 'Network isolation'],
      evidence: 'compliance/control_mapping.md',
    },
    {
      framework: 'Australian Privacy Act 1988',
      status: 'ACTIVE',
      controls: ['SHA-256 PII hashing at Logstash ingestion', 'Raw PII never stored'],
      evidence: 'logstash/pipelines/transaction_ingest.conf',
    },
  ],
  note: 'AES-256 at rest requires Elasticsearch Platinum licence — documented as production control.',
};

function handleExport() {
  const blob = new Blob([JSON.stringify(COMPLIANCE_EXPORT, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `meridian-compliance-report-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

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

      {/* Footer note + US-12 export */}
      <div className="mt-3 pt-3 border-t border-slate-700 space-y-2">
        <p className="text-xs text-slate-500 leading-snug">
          Full control mapping:{' '}
          <span className="text-slate-400 font-mono">compliance/control_mapping.md</span>
        </p>
        <p className="text-xs text-slate-600">
          AES-256 at rest: requires ES Platinum — documented as production control
        </p>
        <button
          onClick={handleExport}
          aria-label="Export compliance report as JSON"
          className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs font-semibold transition-colors border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
        >
          <Download size={12} aria-hidden="true" />
          Export Compliance Report
        </button>
      </div>
    </div>
  );
}
