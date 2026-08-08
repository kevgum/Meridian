import { Shield, Lock, Eye, Download, Check } from 'lucide-react';

interface Badge {
  framework: string;
  detail: string;
  icon: React.ReactNode;
}

const BADGES: Badge[] = [
  {
    framework: 'APRA CPS 234',
    detail: 'Para 15–38 · Incident management, audit trail, information security controls',
    icon: <Shield size={13} aria-hidden="true" />,
  },
  {
    framework: 'PCI DSS v4.0',
    detail: 'Req 7–10 · RBAC, session timeout, immutable audit logs, network isolation',
    icon: <Lock size={13} aria-hidden="true" />,
  },
  {
    framework: 'Privacy Act 1988',
    detail: 'SHA-256 PII hashing at Logstash ingestion · Raw values never stored',
    icon: <Eye size={13} aria-hidden="true" />,
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
  const blob = new Blob([JSON.stringify(COMPLIANCE_EXPORT, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `meridian-compliance-report-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * The compliance rail.
 *
 * All three frameworks are in the same state, so the state gets one repeated
 * green marker rather than three differently-coloured icons — a colour that
 * varies without meaning is worse than no colour at all.
 */
export default function ComplianceBadges() {
  return (
    <aside
      aria-label="Compliance status"
      className="pane pane--rail w-full shrink-0 border-t border-rule lg:w-80 lg:border-l"
    >
      <div className="pane__head px-4 py-3">
        <p className="u-label">Compliance</p>
        <p className="mt-1 text-micro text-muted">Three frameworks in scope · all active</p>
      </div>

      <ul className="scrollbar-thin flex-1 overflow-y-auto">
        {BADGES.map((b) => (
          <li key={b.framework} className="border-b border-rule-2 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="shrink-0 text-ink-2">{b.icon}</span>
              <p className="min-w-0 flex-1 truncate text-xs font-semibold text-ink">
                {b.framework}
              </p>
              <span className="inline-flex shrink-0 items-center gap-1 text-micro font-semibold whitespace-nowrap text-pass">
                <Check size={10} aria-hidden="true" />
                ACTIVE
              </span>
            </div>
            <p className="mt-2 text-micro leading-snug text-muted">{b.detail}</p>
          </li>
        ))}
      </ul>

      <div className="shrink-0 space-y-2 border-t border-rule px-4 py-3">
        <p className="text-micro leading-snug text-muted">
          Full mapping:{' '}
          <span className="font-mono text-ink-2">compliance/control_mapping.md</span>
        </p>
        <p className="text-micro leading-snug text-muted">
          AES-256 at rest needs an Elasticsearch Platinum licence — carried as a
          documented production control.
        </p>
        <button
          type="button"
          onClick={handleExport}
          aria-label="Download the compliance report as JSON"
          className="btn btn--secondary w-full"
        >
          <Download size={12} aria-hidden="true" />
          Export report
        </button>
      </div>
    </aside>
  );
}
