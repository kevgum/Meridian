import type { KPIStats } from '../types';

// Real, validated constants that do not come from a live poll — not mock
// transaction data. `detectionRate`/`fpr` are the trained model's measured
// performance (results/final_metrics.json), not something recomputable per
// poll: live traffic has no ground-truth fraud labels to score accuracy
// against. `transactionsToday`/`activeAlerts` are placeholders here only
// until the first live poll resolves (useElasticPolling.ts), then are
// overwritten with real counts and never fall back to these again.
export const KPI_STATS: KPIStats = {
  transactionsToday: 0,
  detectionRate: 99.96, // accuracy at threshold 0.90, 13-feature geo-velocity model, post ratio-clip fix (results/final_metrics.json)
  fpr: 0.03,             // false positive rate at threshold 0.90
  activeAlerts: 0,
  analystName: 'Kevin Mugambi',
};
