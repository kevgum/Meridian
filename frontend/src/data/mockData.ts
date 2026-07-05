import type { Transaction, SIEMResult, Incident, KPIStats, HistoryEvent } from '../types';

// ---------------------------------------------------------------------------
// Top-bar KPI statistics
// ---------------------------------------------------------------------------

export const KPI_STATS: KPIStats = {
  transactionsToday: 184_299,
  detectionRate: 98.86, // overall accuracy at threshold 0.92 (results/final_metrics.json)
  fpr: 1.10,            // false positive rate at threshold 0.92
  activeAlerts: 3,
  analystName: 'Kevin Mugambi',
};

// ---------------------------------------------------------------------------
// CUST-18656 — Darwin NT, 6 transactions, all SIEM rules PASS, LSTM = 0.74
// ---------------------------------------------------------------------------

export const CUST18656_SIEM_RESULT: SIEMResult = {
  rules: [
    {
      ruleId: 'RULE_001',
      name: 'High-Value Transaction',
      triggered: false,
      severity: 'HIGH',
      evidence: { amount: 256.74, threshold: 10000 },
    },
    {
      ruleId: 'RULE_002',
      name: 'Impossible Geo-Velocity',
      triggered: false,
      severity: 'HIGH',
      evidence: { velocityKmh: 0, note: 'All transactions in Darwin, NT' },
    },
    {
      ruleId: 'RULE_003',
      name: 'Off-Hours Transaction',
      triggered: false,
      severity: 'MEDIUM',
      evidence: { localTime: '14:00', timezone: 'Australia/Darwin' },
    },
    {
      ruleId: 'RULE_004',
      name: 'Watchlist Merchant',
      triggered: false,
      severity: 'HIGH',
      evidence: { merchantId: 'M5732', note: 'Not in watchlist' },
    },
  ],
  siemScore: 0.00,
  triggeredCount: 0,
};

export const CUST18656_INCIDENT: Incident = {
  incidentId: 'INC-2026-18656',
  customerId: 'CUST-18656',
  action: 'LOCK_ACCOUNT',
  threatScore: 0.444,
  lstmScore: 0.74,
  siemScore: 0.00,
  triggerReason: 'LSTM_ALONE',
  severity: 'HIGH',
  status: 'OPEN',
  timestamp: '2026-06-30T14:00:00+09:30',
  totalAmount: 665.20,
  transactionCount: 6,
};

// ---------------------------------------------------------------------------
// Transaction feed — 10 clean background txns + 6 CUST-18656 transactions
// ---------------------------------------------------------------------------

const cleanTx = (
  id: string,
  amount: number,
  merchant: string,
  mcc: number,
  mccLabel: string,
  channel: 'Card' | 'Online',
  time: string,
): Transaction => ({
  id,
  customerId: `CUST-${id}`,
  amount,
  merchantId: `M${mcc}`,
  merchantName: merchant,
  mcc,
  mccLabel,
  channel,
  timestamp: `2026-06-30T${time}+10:00`,
  location: 'Sydney, NSW',
  siemPass: true,
  lstmScore: Math.random() * 0.25 + 0.03,
  isActive: false,
});

export const FEED_TRANSACTIONS: Transaction[] = [
  cleanTx('88211', 42.50,  'Coles Supermarkets',    5411, 'Grocery Stores',      'Card',   '13:48'),
  cleanTx('73940', 129.00, 'JB Hi-Fi',              5732, 'Electronics',         'Online', '13:51'),
  cleanTx('61038', 18.90,  'BP Fuel Station',       5541, 'Service Stations',    'Card',   '13:54'),
  cleanTx('52817', 56.20,  'Uber Eats',             5812, 'Restaurants',         'Online', '13:57'),
  cleanTx('44209', 310.00, 'Qantas Airways',        4511, 'Airlines',            'Online', '13:59'),
  cleanTx('37651', 23.40,  'McDonald\'s',           5814, 'Fast Food',           'Card',   '14:01'),
  cleanTx('29884', 89.95,  'Kmart Australia',       5311, 'Department Stores',   'Card',   '14:04'),
  cleanTx('18423', 14.50,  'Woolworths Metro',      5411, 'Grocery Stores',      'Card',   '14:07'),
  cleanTx('09712', 199.00, 'Apple Online Store',    5732, 'Electronics',         'Online', '14:09'),
  cleanTx('05531', 67.80,  'Chemist Warehouse',     5912, 'Drug Stores',         'Card',   '14:11'),
  // CUST-18656 transactions (Darwin, NT — active investigation)
  {
    id: '18656-1',
    customerId: 'CUST-18656',
    amount: 256.74,
    merchantId: 'M5732',
    merchantName: 'Harvey Norman Darwin',
    mcc: 5732,
    mccLabel: 'Electronics Stores',
    channel: 'Online',
    timestamp: '2026-06-30T14:00:00+09:30',
    location: 'Darwin, NT',
    siemPass: true,
    lstmScore: 0.74,
    isActive: true,
  },
  {
    id: '18656-2',
    customerId: 'CUST-18656',
    amount: 71.28,
    merchantId: 'M5812',
    merchantName: 'Darwin Noodle House',
    mcc: 5812,
    mccLabel: 'Restaurants',
    channel: 'Card',
    timestamp: '2026-06-30T14:15:00+09:30',
    location: 'Darwin, NT',
    siemPass: true,
    lstmScore: 0.71,
    isActive: true,
  },
  {
    id: '18656-3',
    customerId: 'CUST-18656',
    amount: 61.59,
    merchantId: 'M5732',
    merchantName: 'JB Hi-Fi Darwin',
    mcc: 5732,
    mccLabel: 'Electronics Stores',
    channel: 'Online',
    timestamp: '2026-06-30T14:30:00+09:30',
    location: 'Darwin, NT',
    siemPass: true,
    lstmScore: 0.68,
    isActive: true,
  },
  {
    id: '18656-4',
    customerId: 'CUST-18656',
    amount: 69.46,
    merchantId: 'M5812',
    merchantName: 'Hanuman Restaurant',
    mcc: 5812,
    mccLabel: 'Restaurants',
    channel: 'Card',
    timestamp: '2026-06-30T14:45:00+09:30',
    location: 'Darwin, NT',
    siemPass: true,
    lstmScore: 0.70,
    isActive: true,
  },
  {
    id: '18656-5',
    customerId: 'CUST-18656',
    amount: 59.53,
    merchantId: 'M5732',
    merchantName: 'Harvey Norman Darwin',
    mcc: 5732,
    mccLabel: 'Electronics Stores',
    channel: 'Online',
    timestamp: '2026-06-30T15:00:00+09:30',
    location: 'Darwin, NT',
    siemPass: true,
    lstmScore: 0.72,
    isActive: true,
  },
  {
    id: '18656-6',
    customerId: 'CUST-18656',
    amount: 146.60,
    merchantId: 'M5732',
    merchantName: 'JB Hi-Fi Darwin',
    mcc: 5732,
    mccLabel: 'Electronics Stores',
    channel: 'Online',
    timestamp: '2026-06-30T15:15:00+09:30',
    location: 'Darwin, NT',
    siemPass: true,
    lstmScore: 0.74,
    isActive: true,
  },
];

// ---------------------------------------------------------------------------
// 30-event history for the Hybrid Performance chart
// Ends with CUST-18656 (step 30): lstm=0.74, hybrid=0.444
// ---------------------------------------------------------------------------

const h = (step: number, lstm: number, siemScore: number): HistoryEvent => ({
  step,
  lstm: Math.round(lstm * 1000) / 1000,
  hybrid: Math.round((lstm * 0.6 + siemScore * 0.4) * 1000) / 1000,
  flagged: lstm * 0.6 + siemScore * 0.4 >= 0.70 || lstm >= 0.70,
});

export const HISTORY_EVENTS: HistoryEvent[] = [
  h(1,  0.08, 0.00), h(2,  0.12, 0.00), h(3,  0.31, 0.00),
  h(4,  0.09, 0.00), h(5,  0.21, 0.33), h(6,  0.15, 0.00),
  h(7,  0.44, 0.00), h(8,  0.07, 0.00), h(9,  0.18, 0.00),
  h(10, 0.33, 0.33), h(11, 0.11, 0.00), h(12, 0.28, 0.00),
  h(13, 0.52, 0.00), h(14, 0.09, 0.00), h(15, 0.82, 0.67), // flagged — HYBRID
  h(16, 0.14, 0.00), h(17, 0.22, 0.33), h(18, 0.08, 0.00),
  h(19, 0.36, 0.00), h(20, 0.19, 0.00), h(21, 0.41, 0.33),
  h(22, 0.11, 0.00), h(23, 0.27, 0.00), h(24, 0.55, 0.00),
  h(25, 0.13, 0.00), h(26, 0.24, 0.00), h(27, 0.38, 0.33),
  h(28, 0.16, 0.00), h(29, 0.29, 0.00),
  // Step 30 = CUST-18656: lstm=0.74, siem=0.00 → hybrid=0.444, LSTM_ALONE trigger
  { step: 30, lstm: 0.74, hybrid: 0.444, flagged: true },
];
