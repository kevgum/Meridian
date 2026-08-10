import { useState, useEffect, useMemo } from 'react';
import { AlertTriangle, Lock, Search, MapPin, DollarSign, Clock, ArrowUpCircle } from 'lucide-react';
import axios from 'axios';
import type { Incident, Transaction } from '../types';
import type { ToastMessage } from './Toast';
import { formatWindow } from '../lib/formatWindow';

type SeverityFilter = 'ALL' | 'HIGH' | 'MONITOR';
type ChannelFilter = 'ALL' | 'Online' | 'Card' | 'Mobile';
type TimeFilter = 'ALL' | '<1h' | '<6h' | '<24h';

interface MonitorAlert {
  id: string;
  channel: 'Online' | 'Card' | 'Mobile';
  ageMinutes: number;
  title: string;
  location: string;
}

/** MONITOR-tier alerts: transactions with a raised risk score that didn't
 * cross the 0.70 flag line — the queue's "worth a glance" tier. An empty
 * result means genuinely nothing is at that level right now; the queue
 * shows empty rather than substituting placeholder cases. */
function deriveMonitorAlerts(transactions: Transaction[]): MonitorAlert[] {
  const now = Date.now();
  return transactions
    .filter((t) => !t.isActive && (t.threatScore ?? 0) > 0 && (t.threatScore ?? 0) < 0.70)
    .slice(0, 6)
    .map((t) => {
      const ts = new Date(t.timestamp).getTime();
      return {
        id: t.customerId,
        channel: t.channel,
        ageMinutes: Number.isNaN(ts) ? 0 : Math.max(0, Math.round((now - ts) / 60_000)),
        title: `${t.merchantName || t.merchantId} charge`,
        location: t.location || 'Location unavailable',
      };
    });
}

const HIGH_ALERT_CHANNEL: ChannelFilter = 'Mobile';
const HIGH_ALERT_AGE_MINUTES = 14;

function timeLimit(f: TimeFilter): number {
  if (f === '<1h') return 60;
  if (f === '<6h') return 360;
  if (f === '<24h') return 1440;
  return Infinity;
}

function ageLabel(minutes: number): string {
  return minutes < 60 ? `${minutes}m ago` : `${Math.round(minutes / 60)}h ago`;
}

interface Props {
  incident: Incident;
  transactions: Transaction[];
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
  return {
    display: `${mins}:${secs.toString().padStart(2, '0')}`,
    isUrgent: remaining < 60,
  };
}

/** One filter group. Rendered three times; the label column keeps them aligned. */
function FilterRow<T extends string>({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={legend} className="flex items-center gap-2">
      <span className="u-label-muted w-14 shrink-0">{legend}</span>
      <div className="flex flex-wrap gap-1">
        {options.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            aria-pressed={value === v}
            className="chip"
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function AlertQueue({ incident, transactions, onInvestigate, onToast }: Props) {
  const sla = useSlaCountdown(248);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL');
  const [channelFilter, setChannelFilter] = useState<ChannelFilter>('ALL');
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('ALL');
  const [escalated, setEscalated] = useState(false);

  const monitorAlerts = useMemo(() => deriveMonitorAlerts(transactions), [transactions]);

  const caseTxns = useMemo(
    () => transactions.filter((t) => t.customerId === incident.customerId),
    [transactions, incident.customerId],
  );
  const caseWindow = formatWindow(caseTxns);

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
    (channelFilter === 'ALL' || channelFilter === HIGH_ALERT_CHANNEL) &&
    HIGH_ALERT_AGE_MINUTES <= limit;

  const visibleMonitor = monitorAlerts.filter(
    (a) =>
      (severityFilter === 'ALL' || severityFilter === 'MONITOR') &&
      (channelFilter === 'ALL' || a.channel === channelFilter) &&
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
      // Silent success: the button itself switches to "Threat confirmed", so a
      // toast would only restate what the analyst can already see.
      setConfirmed(true);
    } catch {
      // The write to Elasticsearch failed. The incident is confirmed locally so
      // the analyst can keep working, but the audit trail did NOT record it —
      // say so plainly rather than reporting a success that did not happen.
      setConfirmed(true);
      onToast({
        message: `Incident ${incident.incidentId} confirmed locally — audit log NOT updated (Elasticsearch unreachable)`,
        variant: 'error',
      });
    } finally {
      setConfirming(false);
    }
  }

  return (
    <aside
      aria-label="Alert queue"
      className="pane pane--rail w-full shrink-0 border-t border-rule lg:w-80 lg:border-t-0 lg:border-l"
    >
      {/* Head + filters */}
      <div className="pane__head space-y-3 px-4 py-3">
        <div>
          <p className="u-label">Alert queue</p>
          {/* The one live region in this rail. Changing a filter re-announces
              the count, which is the only thing a filter actually changes. */}
          <p className="mt-1 text-micro text-muted" aria-live="polite" aria-atomic="true">
            <span className="font-mono">{totalVisible}</span> active ·{' '}
            <span className="font-mono">{showHighAlert ? 1 : 0}</span> needing a decision
          </p>
        </div>

        <FilterRow
          legend="Severity"
          options={['ALL', 'HIGH', 'MONITOR'] as const}
          value={severityFilter}
          onChange={setSeverityFilter}
        />
        <FilterRow
          legend="Channel"
          options={['ALL', 'Online', 'Card', 'Mobile'] as const}
          value={channelFilter}
          onChange={setChannelFilter}
        />
        <FilterRow
          legend="Time"
          options={['ALL', '<1h', '<6h', '<24h'] as const}
          value={timeFilter}
          onChange={setTimeFilter}
        />
      </div>

      <div className="scrollbar-thin flex min-h-0 flex-1 flex-col overflow-y-auto">
        {/* MONITOR alerts — below the fold of attention, so they stay quiet */}
        {visibleMonitor.map((a) => (
          <div key={a.id} className="border-b border-rule-2 px-4 py-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-mono text-micro text-ink-2">{a.id}</span>
              <span className="text-micro font-semibold whitespace-nowrap text-muted">
                MONITOR
              </span>
            </div>
            <p className="mt-1 text-micro text-ink-2">
              {a.title} · {a.location}
            </p>
            <p className="mt-0.5 text-micro text-muted">
              {a.channel} · {ageLabel(a.ageMinutes)}
            </p>
          </div>
        ))}

        {totalVisible === 0 && (
          <div className="flex flex-1 items-center justify-center p-6">
            <p className="text-center text-micro text-muted">
              No alerts match the selected filters
            </p>
          </div>
        )}

        {/* The open case */}
        <div
          className={`flex flex-1 flex-col gap-4 px-4 py-4${showHighAlert ? '' : ' hidden'}`}
          role="region"
          aria-label="Open case detail"
          aria-hidden={!showHighAlert}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <AlertTriangle size={14} className="shrink-0 text-warn" aria-hidden="true" />
              <span className="u-display truncate text-sm text-ink">{incident.customerId}</span>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="rounded-xs border border-warn-edge bg-warn-wash px-2 py-0.5 text-micro font-bold whitespace-nowrap text-warn">
                {incident.severity}
              </span>
              <span
                className={`rounded-xs border px-2 py-0.5 text-micro font-bold whitespace-nowrap ${
                  confirmed
                    ? 'border-pass-edge bg-pass-wash text-pass-strong'
                    : 'border-rule bg-paper text-ink-2'
                }`}
              >
                {confirmed ? 'CONFIRMED' : incident.status}
              </span>
            </div>
          </div>

          <p className="font-mono text-micro text-muted">{incident.incidentId}</p>

          <dl className="space-y-2 text-micro text-ink-2">
            <div className="flex items-start gap-2">
              <MapPin size={12} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
              <dt className="sr-only">Location</dt>
              <dd>{incident.location || 'Location unavailable'}</dd>
            </div>
            <div className="flex items-start gap-2">
              <DollarSign size={12} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
              <dt className="sr-only">Value</dt>
              <dd>
                <span className="font-mono">A${incident.totalAmount.toFixed(2)}</span> across{' '}
                <span className="font-mono">{incident.transactionCount}</span> transaction
                {incident.transactionCount === 1 ? '' : 's'}
              </dd>
            </div>
            <div className="flex items-start gap-2">
              <Clock size={12} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
              <dt className="sr-only">Window</dt>
              <dd>{caseWindow}</dd>
            </div>
          </dl>

          {/* Score triptych */}
          <div className="well grid grid-cols-3 divide-x divide-rule px-1 py-3 text-center">
            <div title="How unusual the model thinks this is">
              <p className="u-label-muted">Model</p>
              <p className="u-figure mt-1 text-base text-accent-text">
                {Math.round(incident.lstmScore * 100)}%
              </p>
            </div>
            <div title="How many of the four security rules were broken">
              <p className="u-label-muted">Rules</p>
              <p className="u-figure mt-1 text-base text-pass">
                {Math.round(incident.siemScore * 100)}%
              </p>
            </div>
            <div title="The blended risk score">
              <p className="u-label-muted">Overall</p>
              <p className="u-figure mt-1 text-base text-ink">
                {Math.round(incident.threatScore * 100)}%
              </p>
            </div>
          </div>

          <div className="note note--accent px-3 py-2">
            <p className="text-micro font-semibold text-accent-text">
              {incident.triggerReason === 'LSTM_ALONE'
                ? 'Raised by the model alone'
                : 'Raised by the blended score'}
            </p>
            <p className="mt-1 text-micro leading-snug text-ink-2">
              {incident.triggerReason === 'LSTM_ALONE'
                ? 'The blended score sat below the usual flag line, but the model on its own was confident enough to raise this for review.'
                : 'Behaviour and rules together crossed the 0.70 flag line — neither check alone was enough.'}
            </p>
          </div>

          {/* SLA — the one countdown on the page, so it earns the red */}
          <div
            className={`flex items-center justify-between gap-3 rounded-sm px-3 py-2 ${
              sla.isUrgent ? 'note note--warn' : 'well'
            }`}
          >
            <div>
              <p
                className={`text-micro font-semibold ${
                  sla.isUrgent ? 'text-warn' : 'text-ink-2'
                }`}
              >
                Response SLA
              </p>
              <p className="text-micro text-muted">Time left to decide</p>
            </div>
            {/* Deliberately not a live region. A countdown announced once a
                second is 248 interruptions; the value stays queryable, and the
                surrounding note turns red when it goes urgent. */}
            <p
              className={`u-figure text-lg ${sla.isUrgent ? 'text-warn' : 'text-ink'}`}
              aria-label={`${sla.display} remaining`}
            >
              {sla.display}
            </p>
          </div>

          <div className="flex-1" />

          {/* Actions, in the order an analyst uses them */}
          <div className="mt-auto space-y-2">
            <button
              type="button"
              onClick={handleConfirmThreat}
              disabled={confirming || confirmed}
              aria-label={
                confirmed
                  ? 'Threat confirmed'
                  : `Confirm threat for ${incident.customerId} and lock the account`
              }
              className={`btn w-full ${confirmed ? 'btn--settled' : 'btn--primary'}`}
            >
              <Lock size={13} aria-hidden="true" />
              {confirming ? 'Confirming…' : confirmed ? 'Threat confirmed' : 'Confirm threat'}
            </button>

            <button
              type="button"
              onClick={onInvestigate}
              aria-label={`Open the investigation detail for ${incident.customerId}`}
              className="btn btn--secondary w-full"
            >
              <Search size={13} aria-hidden="true" />
              Investigate
            </button>

            <button
              type="button"
              onClick={handleEscalate}
              disabled={escalated}
              aria-label={
                escalated
                  ? 'Escalated to Senior Security Engineer'
                  : 'Escalate to Senior Security Engineer'
              }
              className={`btn w-full ${escalated ? 'btn--settled' : 'btn--quiet'}`}
            >
              <ArrowUpCircle size={13} aria-hidden="true" />
              {escalated ? 'Escalated' : 'Escalate'}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
