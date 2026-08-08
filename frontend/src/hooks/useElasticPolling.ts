import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { FEED_TRANSACTIONS, CUST18656_INCIDENT } from '../data/mockData';
import type { Transaction, Incident } from '../types';

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
  };
}

function mapEsHitToIncident(hit: Record<string, unknown>): Incident {
  const src = (hit['_source'] as Record<string, unknown>) ?? {};
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
    totalAmount: Number(src['total_amount'] ?? 0),
    transactionCount: Number(src['transaction_count'] ?? 0),
  };
}

interface PollingState {
  transactions: Transaction[];
  incident: Incident;
  isLive: boolean;
}

export function useElasticPolling(): PollingState {
  const [state, setState] = useState<PollingState>({
    transactions: FEED_TRANSACTIONS,
    incident: CUST18656_INCIDENT,
    isLive: false,
  });

  const isMounted = useRef(true);

  const poll = useCallback(async () => {
    // `allSettled`, not `all`: the two queries are independent, and one of them
    // failing should not blank the other. Under `all`, a single rejected query
    // dropped the whole poll into the catch block and pinned the dashboard to
    // mock data with no visible reason.
    const [txResult, incResult] = await Promise.allSettled([
      axios.get(ES_TRANSACTIONS_URL, { timeout: 3_000 }),
      axios.get(ES_INCIDENTS_URL, { timeout: 3_000 }),
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

    setState((prev) => ({
      ...prev,
      transactions: txHits.length > 0 ? txHits.map(mapEsHitToTransaction) : prev.transactions,
      incident: incHits.length > 0 ? mapEsHitToIncident(incHits[0]) : prev.incident,
      isLive: reachedCluster,
    }));
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
