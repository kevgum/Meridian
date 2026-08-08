import { CreditCard, Globe, Check } from 'lucide-react';
import type { Transaction } from '../types';

interface Props {
  transactions: Transaction[];
}

/**
 * The AI risk meter on a feed row.
 *
 * Colour alone would not carry the reading, so the percentage is always printed
 * beside the bar. The bar scales rather than resizing, so a live-polling feed
 * never triggers layout.
 */
function RiskMeter({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const tone =
    score >= 0.7 ? 'bg-accent' : score >= 0.5 ? 'bg-accent-edge' : 'bg-pass-edge';

  return (
    <div className="mt-2 flex items-center gap-2">
      <div
        className="meter h-1 flex-1"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`AI risk score ${pct} percent`}
        title={`AI risk score: ${pct}% — how unusual this payment looks`}
      >
        <div
          className={`meter__fill ${tone}`}
          style={{ transform: `scaleX(${score})` }}
        />
      </div>
      <span className="w-8 shrink-0 text-right font-mono text-micro text-muted" aria-hidden="true">
        {pct}%
      </span>
    </div>
  );
}

function TransactionRow({ tx }: { tx: Transaction }) {
  const label =
    `${tx.merchantName}, ${tx.mccLabel}, ${tx.amount.toFixed(2)} dollars, ` +
    `passed security rules, AI risk ${Math.round(tx.lstmScore * 100)} percent` +
    (tx.isActive ? ', part of the open investigation' : '');

  return (
    <div
      role="listitem"
      tabIndex={0}
      aria-label={label}
      className={`row-focus border-b border-rule-2 px-4 py-3 transition-[background-color] duration-200 ease-out ${
        tx.isActive ? 'bg-accent-wash hover:bg-accent-wash' : 'hover:bg-paper-3'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {tx.channel === 'Card' ? (
            <CreditCard
              size={13}
              className={`shrink-0 ${tx.isActive ? 'text-accent-text' : 'text-muted'}`}
              aria-hidden="true"
            />
          ) : (
            <Globe
              size={13}
              className={`shrink-0 ${tx.isActive ? 'text-accent-text' : 'text-muted'}`}
              aria-hidden="true"
            />
          )}
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold text-ink">{tx.merchantName}</p>
            <p className="truncate text-micro text-muted">{tx.mccLabel}</p>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <p className="font-mono text-xs font-semibold text-ink">${tx.amount.toFixed(2)}</p>
          {/* Icon plus word, never colour alone — green is unreliable for
              roughly one reader in twelve. */}
          <span
            className="mt-1 inline-flex items-center gap-1 text-micro font-semibold text-pass"
            title="Passed all four security rules"
          >
            <Check size={10} aria-hidden="true" />
            OK
          </span>
        </div>
      </div>

      <RiskMeter score={tx.lstmScore} />

      {tx.isActive && (
        <p className="mt-2 truncate font-mono text-micro text-accent-text">
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
      className="pane pane--rail w-full shrink-0 border-b border-rule lg:w-68 lg:border-b-0 lg:border-r"
    >
      <div className="pane__head px-4 py-3">
        <p className="u-label">Transaction feed</p>
        <p className="mt-1 text-micro text-muted">
          Newest first · <span className="font-mono">{transactions.length}</span> in window
        </p>
      </div>

      <div
        className="scrollbar-thin max-h-72 flex-1 overflow-y-auto lg:max-h-none"
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
