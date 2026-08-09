import { useEffect, useRef } from 'react';
import { X, MapPin, Clock, DollarSign, Brain, Zap } from 'lucide-react';
import type { Incident, Transaction } from '../types';
import { formatWindow } from '../lib/formatWindow';

interface Props {
  incident: Incident;
  transactions: Transaction[];
  onClose: () => void;
}

/**
 * One fact about the case.
 *
 * The icon sits inline with the label rather than stacked above it — icon-over-
 * label-over-value in three equal columns is the shape every generated
 * dashboard reaches for, and it wastes vertical space in a 448px drawer.
 */
function SummaryCell({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="px-3 py-3">
      <p className="u-label-muted flex items-center gap-1">
        <span className="shrink-0 text-muted">{icon}</span>
        {label}
      </p>
      <p className="mt-1 font-mono text-xs font-semibold text-ink">{value}</p>
    </div>
  );
}

export default function InvestigateDrawer({ incident, transactions, onClose }: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  // Falls back to the isActive-flagged mock rows when the live feed hasn't
  // (yet) surfaced this specific customer among its most recent transactions.
  const matching = transactions.filter((t) => t.customerId === incident.customerId);
  const activeTxns = matching.length > 0 ? matching : transactions.filter((t) => t.isActive);
  const caseWindow = formatWindow(activeTxns);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  // Escape closes; Tab cycles within the drawer.
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;

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
    };

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const lstmContribution = incident.lstmScore * 0.6;
  const siemContribution = incident.siemScore * 0.4;

  return (
    <>
      <div
        className="anim-backdrop fixed inset-0 bg-ink/25"
        style={{ zIndex: 'var(--z-modal)' }}
        aria-hidden="true"
        onClick={onClose}
      />

      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className="anim-drawer pane fixed inset-y-0 right-0 w-full max-w-md border-l border-rule shadow-[var(--shadow-overlay)]"
        style={{ zIndex: 'var(--z-modal)' }}
      >
        <div className="pane__head flex items-center justify-between gap-3 px-5 py-4">
          <div className="min-w-0">
            <h2 id="drawer-title" className="u-display text-sm text-ink">
              {incident.customerId} — investigation
            </h2>
            <p className="mt-0.5 font-mono text-micro text-muted">{incident.incidentId}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close the investigation panel"
            className="btn btn--quiet shrink-0 px-2"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto">
          {/* Summary strip */}
          <div className="grid grid-cols-3 divide-x divide-rule border-b border-rule bg-paper-2">
            <SummaryCell
              icon={<MapPin size={13} aria-hidden="true" />}
              label="Location"
              value={incident.location || 'Unavailable'}
            />
            <SummaryCell
              icon={<Clock size={13} aria-hidden="true" />}
              label="Window"
              value={caseWindow}
            />
            <SummaryCell
              icon={<DollarSign size={13} aria-hidden="true" />}
              label="Total"
              value={`A$${incident.totalAmount.toFixed(2)}`}
            />
          </div>

          <section className="px-5 py-5">
            <p className="u-label">Transaction timeline</p>
            {/* Four columns of data will not compress below ~300px. The table
                scrolls inside its own container rather than pushing the page
                sideways. */}
            <div className="scrollbar-thin mt-3 overflow-x-auto">
              <table className="w-full min-w-72 text-micro" aria-label="Transactions in this case">
              <thead>
                <tr className="border-b border-rule">
                  <th scope="col" className="u-label-muted py-2 text-left">
                    Time
                  </th>
                  <th scope="col" className="u-label-muted py-2 text-left">
                    Merchant
                  </th>
                  <th scope="col" className="u-label-muted py-2 text-right">
                    Amount
                  </th>
                  <th scope="col" className="u-label-muted py-2 text-right">
                    Risk
                  </th>
                </tr>
              </thead>
              <tbody>
                {activeTxns.map((tx) => (
                  <tr key={tx.id} className="border-b border-rule-2">
                    <td className="py-2 pr-2 font-mono whitespace-nowrap text-muted">
                      {new Date(tx.timestamp).toLocaleTimeString('en-AU', {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false,
                      })}
                    </td>
                    <td className="max-w-32 truncate py-2 pr-2 text-ink">{tx.merchantName}</td>
                    <td className="py-2 pr-2 text-right font-mono text-ink">
                      ${tx.amount.toFixed(2)}
                    </td>
                    <td
                      className={`py-2 text-right font-mono font-bold ${
                        tx.lstmScore >= 0.7 ? 'text-accent-text' : 'text-muted'
                      }`}
                    >
                      {Math.round(tx.lstmScore * 100)}%
                    </td>
                  </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="border-t border-rule px-5 py-5">
            <div className="flex items-center gap-2">
              <Brain size={13} className="shrink-0 text-accent-text" aria-hidden="true" />
              <p className="u-label">How the score adds up</p>
            </div>
            <p className="mt-2 text-micro leading-snug text-ink-2">
              The blended score is the behaviour check weighted at 60% plus the security
              rules weighted at 40%.
            </p>

            <dl className="well mt-3 px-4 py-3 font-mono text-micro">
              <div className="flex justify-between py-1">
                <dt className="text-ink-2">Behaviour score</dt>
                <dd className="text-accent-text">{incident.lstmScore.toFixed(2)}</dd>
              </div>
              <div className="flex justify-between py-1 text-muted">
                <dt>weighted</dt>
                <dd>× 0.60</dd>
              </div>
              <div className="flex justify-between border-t border-rule py-1 pt-2">
                <dt className="text-ink-2">Behaviour contributes</dt>
                <dd className="font-bold text-accent-text">{lstmContribution.toFixed(2)}</dd>
              </div>

              <div className="flex justify-between pt-3 pb-1">
                <dt className="text-ink-2">Rules score</dt>
                <dd className="text-pass">{incident.siemScore.toFixed(2)}</dd>
              </div>
              <div className="flex justify-between py-1 text-muted">
                <dt>weighted</dt>
                <dd>× 0.40</dd>
              </div>
              <div className="flex justify-between border-t border-rule py-1 pt-2">
                <dt className="text-ink-2">Rules contribute</dt>
                <dd className="font-bold text-pass">{siemContribution.toFixed(2)}</dd>
              </div>

              <div className="mt-2 flex justify-between border-t-2 border-ink pt-2 text-xs">
                <dt className="font-sans font-semibold text-ink">Overall risk</dt>
                <dd className="font-bold text-ink">{incident.threatScore.toFixed(2)}</dd>
              </div>
            </dl>
          </section>

          <section className="border-t border-rule px-5 py-5">
            <div className="flex items-center gap-2">
              <Zap size={13} className="shrink-0 text-accent-text" aria-hidden="true" />
              <p className="u-label">Why it was flagged</p>
            </div>

            <div className="note note--accent mt-3 px-4 py-3">
              <p className="text-micro font-semibold text-accent-text">
                {incident.triggerReason === 'LSTM_ALONE'
                  ? 'Raised by the model alone'
                  : 'Raised by the blended score'}
              </p>
              <p className="mt-2 text-micro leading-snug text-ink-2">
                {incident.triggerReason === 'LSTM_ALONE' ? (
                  <>
                    The blended score of{' '}
                    <span className="font-mono">{incident.threatScore.toFixed(2)}</span> sits below
                    the usual flag line of <span className="font-mono">0.70</span>. The behaviour
                    score alone —{' '}
                    <span className="font-mono">{incident.lstmScore.toFixed(2)}</span> — was high
                    enough to raise the case anyway. The system does not wait for the fixed rules
                    to agree when the model is this confident.
                  </>
                ) : (
                  <>
                    The blended score of{' '}
                    <span className="font-mono">{incident.threatScore.toFixed(2)}</span> crossed the{' '}
                    <span className="font-mono">0.70</span> flag line on its own — behaviour weighted
                    60%, security rules weighted 40%. Neither check alone was enough; together they
                    were.
                  </>
                )}
              </p>
              <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 border-t border-accent-edge pt-2 text-micro">
                <div className="flex gap-2">
                  <dt className="text-muted">Action taken</dt>
                  <dd className="font-mono font-bold text-ink">{incident.action}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-muted">Urgency</dt>
                  <dd className="font-mono font-bold text-warn">{incident.severity}</dd>
                </div>
              </dl>
            </div>
          </section>
        </div>

        <div className="shrink-0 border-t border-rule px-5 py-4">
          <button type="button" onClick={onClose} className="btn btn--secondary w-full">
            Close
          </button>
        </div>
      </div>
    </>
  );
}
