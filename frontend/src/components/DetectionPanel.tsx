import { Check, X, Brain, Zap, AlertTriangle } from 'lucide-react';
import type { SIEMResult, Incident } from '../types';

interface Props {
  siemResult: SIEMResult;
  lstmScore: number;
  incident: Incident;
}

/**
 * Turns a rule's real evidence object (ElasticSIEMCorrelator.evaluate() —
 * src/siem/rule_engine.py) into one line of prose.
 */
function formatRuleEvidence(ruleId: string, evidence: Record<string, unknown>): string {
  if (typeof evidence.error === 'string') return `Could not check — ${evidence.error}`;

  const num = (key: string) => Number(evidence[key] ?? 0);
  const money = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  switch (ruleId) {
    case 'RULE_001':
      return `${money(num('amount'))} — threshold ${money(num('threshold'))}`;
    case 'RULE_002': {
      const v = num('velocity_kmh');
      return v === 0
        ? 'No location change since the previous transaction — 0 km/h'
        : `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} km/h between consecutive transactions — threshold ${num('threshold_kmh')} km/h`;
    }
    case 'RULE_003': {
      const zone = String(evidence.timezone ?? 'Australia/Sydney').split('/').pop();
      const window = String(evidence.off_hours_window ?? 'before 08:00 or at/after 22:00');
      return `${evidence.local_time ?? '—'} ${zone} — flags ${window}`;
    }
    case 'RULE_004': {
      const merchantId = String(evidence.merchant_id ?? '');
      const size = num('watchlist_size');
      return merchantId
        ? `${merchantId} — checked against ${size || 'the'} watchlisted merchant${size === 1 ? '' : 's'}`
        : 'No merchant on this transaction';
    }
    default:
      return '';
  }
}

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
                {formatRuleEvidence(rule.ruleId, rule.evidence)}
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

      <p
        className={`note mt-4 px-3 py-2 text-micro ${
          siemResult.triggeredCount === 0 ? 'note--pass text-pass-strong' : 'note--warn text-warn'
        }`}
      >
        <span className="font-semibold">
          <span className="font-mono">{siemResult.triggeredCount}</span> of 4 rules broken.
        </span>{' '}
        {siemResult.triggeredCount === 0
          ? 'Every fixed check passed — nothing here looks wrong on the rules alone.'
          : 'On its own this raises the risk score part-way — it takes either several rules together or agreement from the behaviour check to flag the case.'}
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
function BehaviourCheck({
  lstmScore,
  triggerReason,
}: {
  lstmScore: number;
  triggerReason: Incident['triggerReason'];
}) {
  const pct = Math.round(lstmScore * 100);
  // The system's own LSTM_ALONE trigger (src/siem/hybrid_scorer.py,
  // _LSTM_ALONE_THRESHOLD) — not the model's 0.92 evaluation threshold from
  // training, which measures a different thing (accuracy/FPR against
  // ground truth) and would mislabel the line an analyst actually cares about.
  const thresholdPct = 70;

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
          {triggerReason === 'LSTM_ALONE'
            ? "The model was confident enough on its own. It does not wait for the fixed rules to agree before raising a case for review."
            : 'The blended score — behaviour weighted 60%, rules weighted 40% — crossed the 0.70 flag line on its own; the two checks agreed.'}
        </p>
      </div>

      <div className="mt-3">
        <p className="u-label-muted">What looked unusual</p>
        <p className="mt-2 text-micro leading-snug text-ink-2">
          The score above is the model's own confidence, learned from this customer's
          transaction history — not a checklist. Feature-level attribution (exactly which
          signals drove it) isn't available in this prototype; see MODEL_CARD.md,
          Known Limitations.
        </p>
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
            Flagged for review —{' '}
            {Math.round(
              (incident.triggerReason === 'LSTM_ALONE' ? incident.lstmScore : incident.threatScore) * 100,
            )}
            % suspicious
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
          {incident.location || 'Location unavailable'} · {incident.transactionCount} transaction
          {incident.transactionCount === 1 ? '' : 's'} · A${incident.totalAmount.toFixed(2)} ·{' '}
          {incident.incidentId}
        </p>

        <div className="mt-6 flex flex-col gap-6 lg:flex-row lg:gap-8">
          <SecurityRules siemResult={siemResult} />
          <div className="hidden w-px shrink-0 self-stretch bg-rule lg:block" aria-hidden="true" />
          <BehaviourCheck lstmScore={lstmScore} triggerReason={incident.triggerReason} />
        </div>

        <Verdict incident={incident} />
      </div>
    </section>
  );
}
