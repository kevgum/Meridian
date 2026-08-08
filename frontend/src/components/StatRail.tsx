import { AlertTriangle } from 'lucide-react';
import type { KPIStats } from '../types';
import { useCountUp } from '../hooks/useCountUp';

interface Props {
  stats: KPIStats;
}

interface CellProps {
  label: string;
  value: number;
  format: (n: number) => string;
  note: string;
  tooltip: string;
  /** Only the queue cell is urgent, and only because a case is waiting. */
  urgent?: boolean;
}

function StatCell({ label, value, format, note, tooltip, urgent }: CellProps) {
  const shown = useCountUp(value);

  return (
    <div
      className={`flex flex-col justify-center gap-1 px-4 py-3 sm:px-6 ${
        urgent ? 'bg-warn-wash' : ''
      }`}
      title={tooltip}
    >
      <p className="u-label-muted">{label}</p>
      <div className="flex items-baseline gap-2">
        {urgent && (
          <AlertTriangle
            size={16}
            className="shrink-0 self-center text-warn"
            aria-hidden="true"
          />
        )}
        {/* The visible figure is hidden from assistive tech while it counts —
            a live region here would announce every frame of the animation.
            The settled value is exposed once, beside it. */}
        <p
          className={`u-figure text-xl sm:text-2xl ${urgent ? 'text-warn' : 'text-ink'}`}
          aria-hidden="true"
        >
          {format(shown)}
        </p>
        <span className="sr-only">{format(value)}</span>
      </div>
      <p className={`text-micro ${urgent ? 'text-warn-strong' : 'text-muted'}`}>{note}</p>
    </div>
  );
}

/**
 * The four figures that describe the shift, given their own rail rather than
 * squeezed into the top bar.
 *
 * Cells are separated by hairlines and sized unevenly — the queue cell is the
 * one an analyst acts on, so it gets the extra width, the warning wash and an
 * icon, and it is the only cell that ever carries red.
 */
export default function StatRail({ stats }: Props) {
  return (
    <section
      aria-label="Shift summary"
      className="grid shrink-0 grid-cols-2 divide-x divide-y divide-rule border-b border-rule bg-paper sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.3fr)] sm:divide-y-0"
    >
      <StatCell
        label="Payments checked"
        value={stats.transactionsToday}
        format={(n) => Math.round(n).toLocaleString('en-AU')}
        note="today, across every channel"
        tooltip="Total payments the system reviewed today"
      />
      <StatCell
        label="Correct decisions"
        value={stats.detectionRate}
        format={(n) => `${n.toFixed(2)}%`}
        note="flag-or-allow accuracy"
        tooltip="How often the system's decision — flag or allow — is correct overall"
      />
      <StatCell
        label="False alarms"
        value={stats.fpr}
        format={(n) => `${n.toFixed(2)}%`}
        note="normal payments flagged in error"
        tooltip="How often a normal payment is wrongly flagged as suspicious"
      />
      <StatCell
        label="Cases to review"
        value={stats.activeAlerts}
        format={(n) => String(Math.round(n))}
        note="waiting on a human decision"
        tooltip="Flagged cases waiting for an analyst to check"
        urgent={stats.activeAlerts > 0}
      />
    </section>
  );
}
