import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { FEED_TRANSACTIONS, CUST18656_INCIDENT, CUST18656_SIEM_RESULT, HISTORY_EVENTS, KPI_STATS } from '../data/mockData';
import type { Transaction, Incident, SIEMResult, SIEMRule, HistoryEvent, KPIStats } from '../types';

const POLL_INTERVAL_MS = 5_000;

// In dev: Vite proxy forwards /api/* → http://localhost:9200/*
// On Vercel: request will fail → graceful fallback to mock data
//
// Incidents sort on `timestamp`, NOT `@timestamp`. Every incident the playbook
// engine has ever written carries `timestamp`; none of the older ones carry
// `@timestamp`. Elasticsearch rejects a sort on a field no index in the pattern
// maps — the whole request 400s — so sorting on `@timestamp` here meant the
// incident query failed against every existing record.
const ES_TRANSACTIONS_URL =
  '/api/meridian-transactions-*/_search?sort=%40timestamp:desc&size=16';
const ES_INCIDENTS_URL =
  '/api/meridian-incidents-*/_search?sort=timestamp:desc&size=10&q=status:OPEN';
const ES_OPEN_INCIDENT_COUNT_URL =
  '/api/meridian-incidents-*/_count?q=status:OPEN';

// Friendly names — the served rules only carry rule_id, triggered, severity
// and evidence (src/siem/rule_engine.py). This is the one place that names
// them, so both the live path and the bundled mock fallback read the same
// four labels.
const RULE_NAMES: Record<string, string> = {
  RULE_001: 'High-Value Transaction',
  RULE_002: 'Impossible Geo-Velocity',
  RULE_003: 'Off-Hours Transaction',
  RULE_004: 'Watchlist Merchant',
};

/** Today's transaction index name, matching the backend's own UTC convention
 * (`datetime.now(tz=timezone.utc):%Y.%m.%d` in generate_transaction_batch.py
 * / live_stream.py) — daily rollover means "today's count" is just this one
 * index's document count, not a date-range query. */
function todayTransactionCountUrl(): string {
  const d = new Date();
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `/api/meridian-transactions-${yyyy}.${mm}.${dd}/_count`;
}

function mapEsHitToTransaction(hit: Record<string, unknown>): Transaction {
  const src = (hit['_source'] as Record<string, unknown>) ?? {};
  return {
    id: String(hit['_id'] ?? ''),
    customerId: String(src['customer_id'] ?? ''),
    amount: Number(src['amount'] ?? 0),
    merchantId: String(src['merchant_id'] ?? ''),
    merchantName: String(src['merchant_name'] ?? src['merchant_id'] ?? ''),
    mcc: Number(src['merchant_category_code'] ?? 0),
    mccLabel: String(src['mcc_label'] ?? ''),
    channel: (src['channel'] as 'Card' | 'Online') ?? 'Card',
    timestamp: String(src['@timestamp'] ?? src['timestamp'] ?? ''),
    location: String(src['location'] ?? ''),
    siemPass: Boolean(src['siem_pass'] ?? true),
    lstmScore: Number(src['lstm_score'] ?? 0),
    isActive: false,
    siemScore: Number(src['siem_score'] ?? 0),
    threatScore: Number(src['threat_score'] ?? 0),
  };
}

function mapEsHitToIncident(hit: Record<string, unknown>): Incident {
  const src = (hit['_source'] as Record<string, unknown>) ?? {};
  const evidence = (src['evidence'] as Record<string, unknown>) ?? {};
  return {
    incidentId: String(src['incident_id'] ?? hit['_id'] ?? ''),
    customerId: String(src['customer_id'] ?? ''),
    action: String(src['action'] ?? 'LOCK_ACCOUNT'),
    threatScore: Number(src['threat_score'] ?? 0),
    lstmScore: Number(src['lstm_score'] ?? 0),
    siemScore: Number(src['siem_score'] ?? 0),
    triggerReason:
      (src['trigger_reason'] as Incident['triggerReason']) ?? 'LSTM_ALONE',
    severity: (src['severity'] as Incident['severity']) ?? 'HIGH',
    status: (src['status'] as Incident['status']) ?? 'OPEN',
    timestamp: String(src['timestamp'] ?? ''),
    totalAmount: Number(src['total_amount'] ?? evidence['amount'] ?? 0),
    transactionCount: Number(src['transaction_count'] ?? 1),
    location: String(evidence['location'] ?? ''),
  };
}

/** Builds the "how it was checked" panel's data straight from the incident
 * that fired it — `siem_rules` is written in full by PlaybookEngine
 * (src/siem/playbook_engine.py), so no second query is needed. */
function mapEsHitToSiemResult(hit: Record<string, unknown>): SIEMResult | null {
  const src = (hit['_source'] as Record<string, unknown>) ?? {};
  const rawRules = src['siem_rules'] as Record<string, unknown>[] | undefined;
  if (!rawRules || rawRules.length === 0) return null;

  const rules: SIEMRule[] = rawRules.map((r) => {
    const ruleId = String(r['rule_id'] ?? '');
    return {
      ruleId,
      name: RULE_NAMES[ruleId] ?? ruleId,
      triggered: Boolean(r['triggered']),
      severity: (r['severity'] as SIEMRule['severity']) ?? 'HIGH',
      evidence: (r['evidence'] as Record<string, unknown>) ?? {},
    };
  });

  return {
    rules,
    siemScore: Number(src['siem_score'] ?? 0),
    triggeredCount: rules.filter((r) => r.triggered).length,
  };
}

/** The risk-history chart reads the same 16 transactions the feed shows,
 * oldest first, rather than a separate query — the two panels then always
 * agree on what "recent" means. */
function deriveHistory(transactions: Transaction[]): HistoryEvent[] {
  const ascending = [...transactions].reverse();
  return ascending.map((t, i) => {
    const hybrid = t.threatScore ?? Math.round(t.lstmScore * 0.6 * 1000) / 1000;
    return {
      step: i + 1,
      lstm: Math.round(t.lstmScore * 1000) / 1000,
      hybrid: Math.round(hybrid * 1000) / 1000,
      flagged: hybrid >= 0.70 || t.lstmScore >= 0.70,
      customerId: t.customerId,
    };
  });
}

interface PollingState {
  transactions: Transaction[];
  incident: Incident;
  siemResult: SIEMResult;
  history: HistoryEvent[];
  kpiStats: KPIStats;
  isLive: boolean;
}

export function useElasticPolling(): PollingState {
  const [state, setState] = useState<PollingState>({
    transactions: FEED_TRANSACTIONS,
    incident: CUST18656_INCIDENT,
    siemResult: CUST18656_SIEM_RESULT,
    history: HISTORY_EVENTS,
    kpiStats: KPI_STATS,
    isLive: false,
  });

  const isMounted = useRef(true);

  const poll = useCallback(async () => {
    // `allSettled`, not `all`: the four queries are independent, and one of
    // them failing (most often the today's-count query, on the first
    // transaction of a new day before its index exists) should not blank the
    // others. Under `all`, a single rejected query dropped the whole poll
    // into the catch block and pinned the dashboard to mock data with no
    // visible reason.
    const [txResult, incResult, txCountResult, openCountResult] = await Promise.allSettled([
      axios.get(ES_TRANSACTIONS_URL, { timeout: 3_000 }),
      axios.get(ES_INCIDENTS_URL, { timeout: 3_000 }),
      axios.get(todayTransactionCountUrl(), { timeout: 3_000 }),
      axios.get(ES_OPEN_INCIDENT_COUNT_URL, { timeout: 3_000 }),
    ]);

    if (!isMounted.current) return;

    const txHits: Record<string, unknown>[] =
      txResult.status === 'fulfilled' ? (txResult.value.data?.hits?.hits ?? []) : [];
    const incHits: Record<string, unknown>[] =
      incResult.status === 'fulfilled' ? (incResult.value.data?.hits?.hits ?? []) : [];

    // Live means at least one query reached Elasticsearch and came back. Both
    // failing is the expected case on Vercel, where there is no cluster to
    // reach — fall back to the bundled sample data without complaint.
    const reachedCluster =
      txResult.status === 'fulfilled' || incResult.status === 'fulfilled';

    setState((prev) => {
      const transactions = txHits.length > 0 ? txHits.map(mapEsHitToTransaction) : prev.transactions;
      const incident = incHits.length > 0 ? mapEsHitToIncident(incHits[0]) : prev.incident;
      const siemResult =
        incHits.length > 0 ? (mapEsHitToSiemResult(incHits[0]) ?? prev.siemResult) : prev.siemResult;
      const history = txHits.length > 0 ? deriveHistory(transactions) : prev.history;

      return {
        transactions,
        incident,
        siemResult,
        history,
        kpiStats: {
          transactionsToday:
            txCountResult.status === 'fulfilled'
              ? Number(txCountResult.value.data?.count ?? prev.kpiStats.transactionsToday)
              : prev.kpiStats.transactionsToday,
          // Validated model performance (models/MODEL_CARD.md) — a fixed,
          // real number, not something recomputed per poll: live traffic has
          // no ground-truth labels to score accuracy against.
          detectionRate: KPI_STATS.detectionRate,
          fpr: KPI_STATS.fpr,
          activeAlerts:
            openCountResult.status === 'fulfilled'
              ? Number(openCountResult.value.data?.count ?? prev.kpiStats.activeAlerts)
              : prev.kpiStats.activeAlerts,
          analystName: KPI_STATS.analystName,
        },
        isLive: reachedCluster,
      };
    });
  }, []);

  useEffect(() => {
    isMounted.current = true;
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      isMounted.current = false;
      clearInterval(id);
    };
  }, [poll]);

  return state;
}
