import { Check, X, Brain, Zap, AlertTriangle } from 'lucide-react';
import type { SIEMResult, Incident } from '../types';

interface Props {
  siemResult: SIEMResult;
  lstmScore: number;
  incident: Incident;
}

const RULE_EVIDENCE: Record<string, string> = {
  RULE_001: '$256.74 — under the $10,000 threshold',
  RULE_002: 'All six transactions in Darwin, NT — velocity 0 km/h',
  RULE_003: '14:00 ACST — inside the 08:00–22:00 window',
  RULE_004: 'M5732 is not in watchlist/merchants.json',
};

/**
 * The four fixed rules, one row each.
 *
 * Every verdict is carried by three channels at once — icon, word and colour —
 * so a reader who cannot separate red from green still reads the row correctly.
 */
function SecurityRules({ siemResult }: { siemResult: SIEMResult }) {
  return (
    <div className="min-w-0 flex-1">
      <div
        className="flex items-center gap-2"
        title="Fixed rules checked against every payment — amount limits, location jumps, timing and known-bad merchants"
      >
        <Zap size={13} className="shrink-0 text-accent-text" aria-hidden="true" />
        <p className="u-label">Security rules</p>
        <span className="font-mono text-micro text-muted">SIEM</span>
      </div>

      <ul className="mt-3">
        {siemResult.rules.map((rule) => (
          <li
            key={rule.ruleId}
            className="flex items-start gap-3 border-b border-rule-2 py-3 first:border-t first:border-rule-2"
          >
            {rule.triggered ? (
              <X size={14} className="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
            ) : (
              <Check size={14} className="mt-0.5 shrink-0 text-pass" aria-hidden="true" />
            )}

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-mono text-micro text-muted">{rule.ruleId}</span>
                <span className="text-xs font-semibold text-ink">{rule.name}</span>
              </div>
              <p className="mt-1 text-micro leading-snug text-ink-2">
                {RULE_EVIDENCE[rule.ruleId]}
              </p>
            </div>

            <span
              className={`shrink-0 text-micro font-semibold whitespace-nowrap ${
                rule.triggered ? 'text-warn' : 'text-pass'
              }`}
              title={
                rule.triggered
                  ? 'This rule was broken'
                  : 'This check passed — nothing unusual'
              }
            >
              {rule.triggered ? 'PROBLEM' : 'OK'}
            </span>
          </li>
        ))}
      </ul>

      <p className="note note--pass mt-4 px-3 py-2 text-micro text-pass-strong">
        <span className="font-semibold">
          <span className="font-mono">{siemResult.triggeredCount}</span> of 4 rules broken.
        </span>{' '}
        Every fixed check passed — nothing here looks wrong on the rules alone.
      </p>
    </div>
  );
}

/**
 * The behavioural side of the case: what the model thought, and why.
 *
 * The threshold marker is drawn on the meter itself so the reading is spatial —
 * the analyst sees how far short of, or past, the alert line the score sits.
 */
function BehaviourCheck({ lstmScore }: { lstmScore: number }) {
  const pct = Math.round(lstmScore * 100);
  const thresholdPct = 92;

  const signals = [
    'Rapid multi-merchant spend pattern',
    'Electronics and restaurant MCCs alternating',
    'Six transactions across 75 minutes',
    'Spending velocity well above this customer’s baseline',
  ];

  return (
    <div className="min-w-0 flex-1">
      <div
        className="flex items-center gap-2"
        title="A model trained on millions of past payments, looking for behaviour that does not fit this customer's normal pattern"
      >
        <Brain size={13} className="shrink-0 text-accent-text" aria-hidden="true" />
        <p className="u-label">Behaviour check</p>
        <span className="font-mono text-micro text-muted">LSTM</span>
      </div>

      <div className="well mt-3 px-4 py-3">
        <p className="text-micro text-ink-2">How unusual is this behaviour?</p>

        <div
          className="meter relative mt-2 h-3"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Behaviour score ${pct} percent against an alert level of ${thresholdPct} percent`}
        >
          <div
            className="meter__fill bg-accent"
            style={{ transform: `scaleX(${lstmScore})` }}
          />
          <span
            className="absolute inset-y-0 w-0.5 bg-warn"
            style={{ left: `${thresholdPct}%` }}
            aria-hidden="true"
          />
        </div>

        <div className="mt-2 flex flex-wrap justify-between gap-x-4 gap-y-1">
          <span className="font-mono text-micro font-bold text-accent-text">
            {pct}% unusual
          </span>
          <span className="font-mono text-micro text-warn">
            alert level {thresholdPct}%
          </span>
        </div>
      </div>

      <div className="note note--accent mt-3 px-3 py-2">
        <p className="text-micro font-semibold text-accent-text">Why it was flagged</p>
        <p className="mt-1 text-micro leading-snug text-ink-2">
          The model was confident enough on its own. It does not wait for the fixed rules
          to agree before raising a case for review.
        </p>
      </div>

      <div className="mt-3">
        <p className="u-label-muted">What looked unusual</p>
        <ul className="mt-2 space-y-2">
          {signals.map((signal) => (
            <li key={signal} className="flex items-start gap-2 text-micro text-ink-2">
              <span className="mt-0.5 shrink-0 font-mono text-accent" aria-hidden="true">
                ›
              </span>
              {signal}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** The line the analyst reads first if they read nothing else. */
function Verdict({ incident }: { incident: Incident }) {
  return (
    <div className="note note--accent mt-5 px-4 py-3">
      <div className="flex flex-wrap items-start gap-3">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-accent-text" aria-hidden="true" />

        <div className="min-w-0 flex-1">
          <p className="u-display text-sm text-ink">
            Flagged for review — {Math.round(incident.lstmScore * 100)}% suspicious
          </p>

          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-micro text-muted">
            <div className="flex gap-2" title="The final score, blending both checks">
              <dt>Overall risk</dt>
              <dd className="font-mono font-bold text-ink">
                {incident.threatScore.toFixed(2)}
              </dd>
            </div>
            <div className="flex gap-2" title="Score from the behaviour check">
              <dt>Behaviour</dt>
              <dd className="font-mono font-bold text-accent-text">
                {incident.lstmScore.toFixed(2)}
              </dd>
            </div>
            <div className="flex gap-2" title="Score from the fixed security rules">
              <dt>Rules</dt>
              <dd className="font-mono font-bold text-pass">
                {incident.siemScore.toFixed(2)}
              </dd>
            </div>
            <div className="flex gap-2" title="The automatic action the system took">
              <dt>Action taken</dt>
              <dd className="font-mono font-bold text-ink">{incident.action}</dd>
            </div>
          </dl>
        </div>

        <span className="shrink-0 rounded-xs border border-warn-edge bg-warn-wash px-2 py-1 text-micro font-bold whitespace-nowrap text-warn">
          {incident.severity}
        </span>
      </div>
    </div>
  );
}

export default function DetectionPanel({ siemResult, lstmScore, incident }: Props) {
  return (
    <section
      aria-label="Detection detail"
      className="pane min-w-0 flex-1 overflow-y-auto scrollbar-thin"
    >
      <div className="px-5 py-4 sm:px-6">
        <h1 className="u-display text-base text-ink">
          How case {incident.customerId} was checked
        </h1>
        <p className="mt-2 max-w-[68ch] text-xs leading-relaxed text-ink-2">
          Two independent checks run on every payment: a set of fixed security rules, and a
          model that has learned this customer’s normal behaviour.
        </p>
        <p className="mt-1 font-mono text-micro text-muted">
          Darwin, NT · {incident.transactionCount} transactions · A$
          {incident.totalAmount.toFixed(2)} · {incident.incidentId}
        </p>

        <div className="mt-6 flex flex-col gap-6 lg:flex-row lg:gap-8">
          <SecurityRules siemResult={siemResult} />
          <div className="hidden w-px shrink-0 self-stretch bg-rule lg:block" aria-hidden="true" />
          <BehaviourCheck lstmScore={lstmScore} />
        </div>

        <Verdict incident={incident} />
      </div>
    </section>
  );
}
