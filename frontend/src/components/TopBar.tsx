import { useEffect, useState } from 'react';
import { ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import type { KPIStats } from '../types';

interface Props {
  stats: KPIStats;
  isLive: boolean;
}

/**
 * The console clock. Rendered here rather than passed in, because it is the one
 * value on the bar that has to keep moving on its own.
 */
function useConsoleClock(): string {
  const format = () =>
    new Date().toLocaleTimeString('en-AU', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZoneName: 'short',
    });

  const [now, setNow] = useState(format);

  useEffect(() => {
    const id = setInterval(() => setNow(format()), 1_000);
    return () => clearInterval(id);
  }, []);

  return now;
}

/**
 * N9 edge-aligned bar: identity hard-left, session state hard-right, nothing
 * competing in the middle. The KPI figures that used to crowd this row now live
 * in their own rail directly beneath it.
 */
export default function TopBar({ stats, isLive }: Props) {
  const now = useConsoleClock();

  return (
    <header
      className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-rule bg-paper px-4 sm:px-6"
      style={{ height: 'var(--bar-height)' }}
    >
      {/* Identity */}
      <div className="flex min-w-0 items-center gap-2">
        <ShieldCheck size={18} className="shrink-0 text-accent" aria-hidden="true" />
        <div className="min-w-0 leading-none">
          <p className="u-display truncate text-sm leading-none text-ink">Meridian Sentinel</p>
          <p className="mt-1 hidden text-micro leading-none text-muted sm:block">
            Fraud monitoring console · v1.0.0
          </p>
        </div>
      </div>

      {/* Session state */}
      <div className="flex shrink-0 items-center gap-4">
        <span
          className={`inline-flex items-center gap-2 rounded-pill border px-2 py-1 text-micro font-semibold leading-none whitespace-nowrap ${
            isLive
              ? 'border-pass-edge bg-pass-wash text-pass-strong'
              : 'border-rule bg-paper-2 text-muted'
          }`}
          title={
            isLive
              ? 'Connected to live Elasticsearch'
              : 'Demo mode — reading bundled sample data'
          }
        >
          {isLive ? (
            <Wifi size={11} aria-hidden="true" />
          ) : (
            <WifiOff size={11} aria-hidden="true" />
          )}
          {isLive ? 'Live' : 'Demo'}
        </span>

        {/* Below 640px the bar carries identity and connection state only —
            there is not room for the analyst and the clock without the
            wordmark truncating to nothing. */}
        <div className="hidden items-center gap-4 sm:flex">
          <div className="text-right leading-none">
            <p className="u-label-muted">Analyst on duty</p>
            <p className="mt-1 text-xs font-semibold leading-none text-ink">
              {stats.analystName}
            </p>
          </div>

          <p
            className="font-mono text-xs leading-none whitespace-nowrap text-muted"
            aria-label={`Console time ${now}`}
          >
            {now}
          </p>
        </div>
      </div>
    </header>
  );
}
