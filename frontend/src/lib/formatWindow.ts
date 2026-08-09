import type { Transaction } from '../types';

/** "37 min" / "1h 15m" from the span between a set of transactions' first and
 * last timestamp — replaces a fixed duration that only ever described one
 * specific incident. */
export function formatWindow(txns: Transaction[]): string {
  if (txns.length < 2) return txns.length === 1 ? 'single transaction' : '—';
  const times = txns.map((t) => new Date(t.timestamp).getTime()).filter((n) => !Number.isNaN(n));
  if (times.length < 2) return '—';
  const minutes = Math.round((Math.max(...times) - Math.min(...times)) / 60_000);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
