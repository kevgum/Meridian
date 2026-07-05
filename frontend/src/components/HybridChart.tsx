import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
  ReferenceDot,
} from 'recharts';
import type { HistoryEvent } from '../types';

interface Props {
  events: HistoryEvent[];
}

interface TooltipPayload {
  color: string;
  name: string;
  value: number;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: number;
}) {
  if (!active || !payload?.length) return null;

  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg p-2.5 text-xs shadow-xl">
      <p className="text-slate-400 mb-1.5">Payment #{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }} className="font-mono">
          {p.name === 'lstm' ? 'AI behaviour' : 'Overall risk'}: {p.value.toFixed(2)}
        </p>
      ))}
      {label === 30 && (
        <p className="text-amber-400 mt-1 font-semibold">Customer CUST-18656 — flagged by the AI</p>
      )}
    </div>
  );
}

export default function HybridChart({ events }: Props) {
  // Mark CUST-18656 (step 30) for the annotation dot
  const cust18656 = events.find((e) => e.step === 30);

  return (
    <div className="flex-1 bg-slate-800 border border-slate-700 rounded-lg p-4 flex flex-col min-w-0">
      <div className="mb-3 shrink-0">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Risk Score Over the Last 30 Payments
        </p>
        <p className="text-xs text-slate-500 mt-0.5">
          Any payment above the red line is flagged for a human to review.
        </p>
      </div>

      <div className="flex-1 min-h-0" style={{ minHeight: 160 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={events} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="step"
              tick={{ fill: '#64748b', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#475569' }}
              label={{ value: 'Payment', position: 'insideBottomRight', fill: '#64748b', fontSize: 10, offset: -4 }}
            />
            <YAxis
              domain={[0, 1]}
              tick={{ fill: '#64748b', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#475569' }}
              tickFormatter={(v: number) => v.toFixed(1)}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 11, color: '#94a3b8', paddingTop: 8 }}
              formatter={(value: string) =>
                value === 'lstm' ? 'AI behaviour score' : 'Overall risk score'
              }
            />

            {/* Trigger threshold reference line */}
            <ReferenceLine
              y={0.70}
              stroke="#ef4444"
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{ value: 'Flag line', position: 'insideTopLeft', fill: '#ef4444', fontSize: 10 }}
            />

            {/* LSTM score line */}
            <Line
              type="monotone"
              dataKey="lstm"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#3b82f6' }}
            />

            {/* Hybrid score line */}
            <Line
              type="monotone"
              dataKey="hybrid"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#f59e0b' }}
            />

            {/* CUST-18656 annotation dot (step 30) */}
            {cust18656 && (
              <ReferenceDot
                x={30}
                y={cust18656.lstm}
                r={5}
                fill="#f59e0b"
                stroke="#fde68a"
                strokeWidth={2}
                label={{ value: '18656', position: 'top', fill: '#fde68a', fontSize: 9 }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
