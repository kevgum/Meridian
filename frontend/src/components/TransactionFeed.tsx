import { CreditCard, Globe, CheckCircle } from 'lucide-react';
import type { Transaction } from '../types';

interface Props {
  transactions: Transaction[];
}

function LSTMBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const colour =
    score >= 0.70 ? 'bg-amber-500' : score >= 0.50 ? 'bg-yellow-500' : 'bg-green-500';
  return (
    <div className="flex items-center gap-1.5 mt-1" role="presentation">
      <div
        className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`LSTM anomaly score ${pct}%`}
      >
        <div className={`h-full rounded-full ${colour}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 w-7 text-right font-mono" aria-hidden="true">
        {pct}%
      </span>
    </div>
  );
}

function TransactionRow({ tx }: { tx: Transaction }) {
  const isHighAlert = tx.isActive && tx.lstmScore >= 0.70;
  const label = `${tx.merchantName}, ${tx.mccLabel}, $${tx.amount.toFixed(2)}, SIEM PASS, LSTM ${Math.round(tx.lstmScore * 100)}%${tx.isActive ? ', active investigation' : ''}`;

  return (
    <div
      role="listitem"
      tabIndex={0}
      aria-label={label}
      className={`px-3 py-2.5 border-b transition-colors outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500 ${
        tx.isActive
          ? isHighAlert
            ? 'border-amber-700/60 bg-amber-950/30 hover:bg-amber-950/50'
            : 'border-blue-700/40 bg-blue-950/20 hover:bg-blue-950/40'
          : 'border-slate-700/50 hover:bg-slate-800/50'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`p-1 rounded shrink-0 ${tx.isActive ? 'text-amber-400' : 'text-slate-500'}`}
            aria-hidden="true"
          >
            {tx.channel === 'Card' ? <CreditCard size={13} /> : <Globe size={13} />}
          </div>
          <div className="min-w-0">
            <p className={`text-xs font-medium truncate ${tx.isActive ? 'text-amber-100' : 'text-slate-300'}`}>
              {tx.merchantName}
            </p>
            <p className="text-xs text-slate-500 truncate">{tx.mccLabel}</p>
          </div>
        </div>

        <div className="text-right shrink-0">
          <p className={`text-xs font-semibold tabular-nums ${tx.isActive ? 'text-amber-200' : 'text-slate-200'}`}>
            ${tx.amount.toFixed(2)}
          </p>
          <div className="flex items-center justify-end gap-1 mt-0.5" aria-hidden="true">
            <CheckCircle size={10} className="text-green-500" />
            <span className="text-xs text-green-500 font-medium">PASS</span>
          </div>
        </div>
      </div>

      <LSTMBar score={tx.lstmScore} />

      {tx.isActive && (
        <p className="text-xs text-amber-500/80 font-medium mt-1 truncate" aria-hidden="true">
          {tx.customerId} · {tx.location}
        </p>
      )}
    </div>
  );
}

export default function TransactionFeed({ transactions }: Props) {
  return (
    <aside
      aria-label="Live transaction feed"
      className="w-64 shrink-0 bg-slate-800 border border-slate-700 rounded-lg flex flex-col overflow-hidden"
    >
      <div className="px-3 py-2.5 border-b border-slate-700 shrink-0">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Live Transaction Feed
        </p>
        <p className="text-xs text-slate-500 mt-0.5">Real-time · {transactions.length} transactions</p>
      </div>

      <div
        className="flex-1 overflow-y-auto scrollbar-thin"
        role="list"
        aria-label="Transactions, most recent first"
        aria-live="polite"
        aria-relevant="additions"
      >
        {[...transactions].reverse().map((tx) => (
          <TransactionRow key={tx.id} tx={tx} />
        ))}
      </div>
    </aside>
  );
}
