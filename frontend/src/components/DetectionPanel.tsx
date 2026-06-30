import { CheckCircle, XCircle, AlertTriangle, Brain, Zap } from 'lucide-react';
import type { SIEMResult, Incident } from '../types';

interface Props {
  siemResult: SIEMResult;
  lstmScore: number;
  incident: Incident;
}

const RULE_EVIDENCE: Record<string, string> = {
  RULE_001: '$256.74 < $10,000 threshold',
  RULE_002: 'All transactions in Darwin, NT — velocity 0 km/h',
  RULE_003: 'Txn time 14:00 ACST — within 08:00–22:00 window',
  RULE_004: 'M5732 not in watchlist/merchants.json',
};

const SEVERITY_COLOUR: Record<string, string> = {
  HIGH: 'text-red-400',
  MEDIUM: 'text-amber-400',
};

function SIEMRulesColumn({ siemResult }: { siemResult: SIEMResult }) {
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-3">
        <Zap size={14} className="text-blue-400" />
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          SIEM Rule Engine
        </p>
      </div>

      <div className="space-y-2">
        {siemResult.rules.map((rule) => (
          <div
            key={rule.ruleId}
            className="flex items-start gap-2.5 p-2.5 rounded-lg bg-slate-700/50 border border-slate-600/50"
          >
            {rule.triggered ? (
              <XCircle size={15} className="text-red-500 shrink-0 mt-0.5" />
            ) : (
              <CheckCircle size={15} className="text-green-500 shrink-0 mt-0.5" />
            )}
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-400">{rule.ruleId}</span>
                <span className={`text-xs font-semibold ${SEVERITY_COLOUR[rule.severity]}`}>
                  {rule.severity}
                </span>
              </div>
              <p className="text-xs text-slate-200 font-medium mt-0.5">{rule.name}</p>
              <p className="text-xs text-slate-400 mt-0.5 leading-snug">
                {RULE_EVIDENCE[rule.ruleId]}
              </p>
            </div>
            <span
              className={`ml-auto text-xs font-bold shrink-0 ${
                rule.triggered ? 'text-red-400' : 'text-green-400'
              }`}
            >
              {rule.triggered ? 'TRIGGER' : 'PASS'}
            </span>
          </div>
        ))}
      </div>

      {/* SIEM score summary */}
      <div className="mt-3 p-2.5 rounded-lg bg-green-900/20 border border-green-700/30">
        <p className="text-xs text-green-400 font-semibold">
          SIEM Score: {siemResult.siemScore.toFixed(2)} — {siemResult.triggeredCount}/4 rules triggered
        </p>
        <p className="text-xs text-green-300/70 mt-0.5">All SIEM signals within normal range</p>
      </div>
    </div>
  );
}

function LSTMColumn({ lstmScore }: { lstmScore: number }) {
  const pct = Math.round(lstmScore * 100);
  const threshold = 90; // decision threshold in percent

  const behavioural = [
    'Rapid multi-merchant spend pattern',
    'Electronics + restaurant alternating MCC',
    '6 transactions across 75 minutes',
    'Unusual spending velocity vs. customer baseline',
  ];

  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-3">
        <Brain size={14} className="text-blue-400" />
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          LSTM Analysis
        </p>
      </div>

      {/* Anomaly probability */}
      <div className="p-3 rounded-lg bg-slate-700/50 border border-slate-600/50">
        <p className="text-xs text-slate-400 mb-2">Anomaly Probability</p>

        {/* Bar */}
        <div className="relative h-4 bg-slate-600 rounded-full overflow-hidden mb-1">
          <div
            className="h-full bg-blue-500 rounded-full transition-all"
            style={{ width: `${pct}%` }}
          />
          {/* Threshold marker */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-red-400 opacity-80"
            style={{ left: `${threshold}%` }}
          />
        </div>

        <div className="flex justify-between text-xs">
          <span className="text-blue-300 font-bold font-mono">{pct}% anomalous</span>
          <span className="text-red-400 font-mono">threshold: {threshold}%</span>
        </div>
      </div>

      {/* Trigger path */}
      <div className="mt-2 p-2.5 rounded-lg bg-amber-900/20 border border-amber-700/40">
        <p className="text-xs text-amber-400 font-semibold">Trigger Path: LSTM_ALONE</p>
        <p className="text-xs text-amber-300/70 mt-0.5 leading-snug">
          lstm_score ≥ 0.70 fires playbook independently of SIEM score
        </p>
      </div>

      {/* Behavioural signals */}
      <div className="mt-2 p-2.5 rounded-lg bg-slate-700/50 border border-slate-600/50">
        <p className="text-xs text-slate-400 font-semibold mb-1.5">Behavioural Signals</p>
        <ul className="space-y-1">
          {behavioural.map((signal) => (
            <li key={signal} className="text-xs text-slate-300 flex items-start gap-1.5">
              <span className="text-blue-400 mt-0.5 shrink-0">›</span>
              {signal}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function VerdictBanner({ incident }: { incident: Incident }) {
  return (
    <div className="mt-4 p-3 rounded-lg bg-amber-900/30 border border-amber-600/50">
      <div className="flex items-center gap-2">
        <AlertTriangle size={16} className="text-amber-400 shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-bold text-amber-300">
            FLAGGED — LSTM ALONE · {Math.round(incident.lstmScore * 100)}% SUSPICIOUS
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
            <span className="text-xs text-slate-400">
              Hybrid score:{' '}
              <span className="text-slate-200 font-mono">{incident.threatScore.toFixed(3)}</span>
            </span>
            <span className="text-xs text-slate-400">
              LSTM:{' '}
              <span className="text-blue-300 font-mono">{incident.lstmScore.toFixed(2)}</span>
            </span>
            <span className="text-xs text-slate-400">
              SIEM:{' '}
              <span className="text-green-300 font-mono">{incident.siemScore.toFixed(2)}</span>
            </span>
            <span className="text-xs text-slate-400">
              Playbook:{' '}
              <span className="text-amber-300 font-semibold">{incident.action}</span>
            </span>
          </div>
        </div>
        <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-600/40 text-amber-200 border border-amber-500/40 shrink-0">
          {incident.severity}
        </span>
      </div>
    </div>
  );
}

export default function DetectionPanel({ siemResult, lstmScore, incident }: Props) {
  return (
    <div className="flex-1 min-w-0 bg-slate-800 border border-slate-700 rounded-lg flex flex-col p-4 overflow-y-auto">
      {/* Header */}
      <div className="mb-4 shrink-0">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Detection Comparison — CUST-18656
        </p>
        <p className="text-xs text-slate-500 mt-0.5">Darwin, NT · 6 transactions · A$665.20 total</p>
      </div>

      {/* Two-column detection grid */}
      <div className="flex gap-4 flex-1 min-h-0">
        <SIEMRulesColumn siemResult={siemResult} />
        <div className="w-px bg-slate-700 shrink-0" />
        <LSTMColumn lstmScore={lstmScore} />
      </div>

      {/* Verdict banner */}
      <div className="shrink-0">
        <VerdictBanner incident={incident} />
      </div>
    </div>
  );
}
