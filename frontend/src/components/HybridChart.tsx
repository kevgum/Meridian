import { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
  ResponsiveContainer,
} from 'recharts';
import type { HistoryEvent } from '../types';

interface Props {
  events: HistoryEvent[];
}

interface TooltipPayload {
  dataKey: string;
  value: number;
}

/** The token names the chart draws from. Nothing here is a literal colour. */
const CHART_TOKENS = [
  '--color-chart-hybrid',
  '--color-chart-lstm',
  '--color-chart-threshold',
  '--color-chart-grid',
  '--color-chart-axis',
  '--color-paper',
] as const;

type ChartToken = (typeof CHART_TOKENS)[number];

/**
 * Resolves the chart's design tokens to concrete values.
 *
 * Recharts writes colours as SVG presentation attributes, which do not resolve
 * `var()`. Reading the computed custom properties once keeps the chart on the
 * same palette as the rest of the console without hard-coding a single value.
 */
function useChartTokens(): Record<ChartToken, string> | null {
  const [tokens, setTokens] = useState<Record<ChartToken, string> | null>(null);

  useEffect(() => {
    const styles = getComputedStyle(document.documentElement);
    const resolved = Object.fromEntries(
      CHART_TOKENS.map((name) => [name, styles.getPropertyValue(name).trim()]),
    ) as Record<ChartToken, string>;
    setTokens(resolved);
  }, []);

  return tokens;
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: number;
}) {
  if (!active || !payload?.length) return null;

  const read = (key: string) => payload.find((p) => p.dataKey === key)?.value;
  const hybrid = read('hybrid');
  const lstm = read('lstm');

  return (
    <div className="rounded-sm border border-rule bg-paper px-3 py-2 shadow-[var(--shadow-overlay)]">
      <p className="u-label-muted">Payment {label}</p>
      <dl className="mt-2 space-y-1 text-micro">
        {hybrid !== undefined && (
          <div className="flex items-center justify-between gap-4">
            <dt className="text-ink-2">Overall risk</dt>
            <dd className="font-mono font-bold text-accent-text">{hybrid.toFixed(2)}</dd>
          </div>
        )}
        {lstm !== undefined && (
          <div className="flex items-center justify-between gap-4">
            <dt className="text-ink-2">Behaviour score</dt>
            <dd className="font-mono font-bold text-ink">{lstm.toFixed(2)}</dd>
          </div>
        )}
      </dl>
      {label === 30 && (
        <p className="mt-2 border-t border-rule-2 pt-2 text-micro font-semibold text-accent-text">
          CUST-18656 — raised by the model
        </p>
      )}
    </div>
  );
}

/**
 * Thirty payments of history against the flag line.
 *
 * The blended score is the headline series and wears the accent; the behaviour
 * score is context and stays recessive ink. The two are also separated by dash
 * pattern, so the pair survives greyscale printing and colour-vision deficiency
 * — the validated colour distance carries the reading, the dashes back it up.
 */
export default function HybridChart({ events }: Props) {
  const t = useChartTokens();
  const flagged = events.find((e) => e.step === 30);

  return (
    <section
      aria-label="Risk score history"
      className="pane min-w-0 flex-1 border-t border-rule"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 px-5 pt-4 sm:px-6">
        <div>
          <p className="u-label">Risk over the last 30 payments</p>
          <p className="mt-1 text-micro text-muted">
            Anything above the flag line goes to a human.
          </p>
        </div>

        {/* Legend — always present for two series, so identity is never colour
            alone. Each key repeats its series' dash pattern. */}
        <ul className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <li className="flex items-center gap-2 text-micro text-ink-2">
            <span className="h-0.5 w-5 shrink-0 rounded-pill bg-accent" aria-hidden="true" />
            Overall risk
          </li>
          <li className="flex items-center gap-2 text-micro text-ink-2">
            <span
              className="h-0.5 w-5 shrink-0 bg-[repeating-linear-gradient(to_right,var(--color-ink-2)_0_6px,transparent_6px_10px)]"
              aria-hidden="true"
            />
            Behaviour score
          </li>
          <li className="flex items-center gap-2 text-micro text-ink-2">
            <span
              className="h-0.5 w-5 shrink-0 bg-[repeating-linear-gradient(to_right,var(--color-warn)_0_3px,transparent_3px_6px)]"
              aria-hidden="true"
            />
            Flag line 0.70
          </li>
        </ul>
      </div>

      <div className="min-h-0 flex-1 px-2 pb-3 sm:px-3" style={{ minHeight: 168 }}>
        {t && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={events} margin={{ top: 12, right: 20, left: -20, bottom: 4 }}>
              <CartesianGrid
                stroke={t['--color-chart-grid']}
                strokeDasharray="2 4"
                vertical={false}
              />
              <XAxis
                dataKey="step"
                tick={{ fill: t['--color-chart-axis'], fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: t['--color-chart-grid'] }}
              />
              <YAxis
                domain={[0, 1]}
                tick={{ fill: t['--color-chart-axis'], fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => v.toFixed(1)}
              />
              <Tooltip
                content={<ChartTooltip />}
                cursor={{ stroke: t['--color-chart-axis'], strokeDasharray: '3 3' }}
              />

              <ReferenceLine
                y={0.7}
                stroke={t['--color-chart-threshold']}
                strokeDasharray="4 4"
                strokeWidth={1.5}
              />

              {/* Context series — recessive ink, dashed. */}
              <Line
                type="monotone"
                dataKey="lstm"
                stroke={t['--color-chart-lstm']}
                strokeWidth={1.5}
                strokeDasharray="6 4"
                dot={false}
                activeDot={{
                  r: 4,
                  fill: t['--color-chart-lstm'],
                  stroke: t['--color-paper'],
                  strokeWidth: 2,
                }}
                isAnimationActive={false}
              />

              {/* Headline series — accent, solid, drawn last so it sits on top. */}
              <Line
                type="monotone"
                dataKey="hybrid"
                stroke={t['--color-chart-hybrid']}
                strokeWidth={2}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: t['--color-chart-hybrid'],
                  stroke: t['--color-paper'],
                  strokeWidth: 2,
                }}
                isAnimationActive={false}
              />

              {/* The one point worth naming outright. */}
              {flagged && (
                <ReferenceDot
                  x={30}
                  y={flagged.lstm}
                  r={4.5}
                  fill={t['--color-chart-hybrid']}
                  stroke={t['--color-paper']}
                  strokeWidth={2}
                  label={{
                    value: '18656',
                    position: 'top',
                    fill: t['--color-chart-hybrid'],
                    fontSize: 10,
                  }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
