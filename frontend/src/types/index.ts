export interface Transaction {
  id: string;
  customerId: string;
  amount: number;
  merchantId: string;
  merchantName: string;
  mcc: number;
  mccLabel: string;
  channel: 'Card' | 'Online';
  timestamp: string;
  location: string;
  siemPass: boolean;
  lstmScore: number;
  isActive: boolean; // true = part of the current investigation
}

export interface SIEMRule {
  ruleId: string;
  name: string;
  triggered: boolean;
  severity: 'HIGH' | 'MEDIUM';
  evidence: Record<string, unknown>;
}

export interface SIEMResult {
  rules: SIEMRule[];
  siemScore: number;
  triggeredCount: number;
}

export interface Incident {
  incidentId: string;
  customerId: string;
  action: string;
  threatScore: number;
  lstmScore: number;
  siemScore: number;
  triggerReason: 'HYBRID_THRESHOLD' | 'LSTM_ALONE' | 'NONE';
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  status: 'OPEN' | 'CONFIRMED' | 'CLOSED';
  timestamp: string;
  totalAmount: number;
  transactionCount: number;
}

export interface KPIStats {
  transactionsToday: number;
  detectionRate: number;
  fpr: number;
  activeAlerts: number;
  analystName: string;
}

export interface HistoryEvent {
  step: number;
  lstm: number;
  hybrid: number;
  flagged: boolean;
}
