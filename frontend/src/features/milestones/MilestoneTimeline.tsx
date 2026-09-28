import { useMemo, useState } from "react";

import { RISK_COLOURS, RISK_LABELS, formatDate } from "./labels";
import type { Milestone } from "./types";

/**
 * A dependency-free Gantt.
 *
 * Same stance as features/analytics/NetworkGraph: plain SVG rather than a
 * charting library. Recharts has no Gantt primitive -- it would have to be
 * faked with a stacked bar whose first segment is transparent -- and a
 * dedicated Gantt package brings its own styling to fight with. Laid out by
 * hand it is about a hundred lines, themes with the rest of the app, and
 * renders identically every time.
 *
 * It is hidden below `md` and the list underneath carries the same
 * information in words: five months of columns cannot be read on a phone, and
 * a chart nobody can read is worse than no chart.
 */

const ROW_HEIGHT = 30;
const BAR_HEIGHT = 14;
const LABEL_WIDTH = 168;
const RIGHT_PAD = 16;
const TOP_PAD = 26;
const MIN_PLOT_WIDTH = 360;

interface Bounds {
  start: number;
  end: number;
}

function dayOf(iso: string): number {
  return new Date(`${iso}T00:00:00`).getTime();
}

const DAY = 86_400_000;

export function MilestoneTimeline({ milestones }: { milestones: Milestone[] }) {
  const [focused, setFocused] = useState<string | null>(null);

  const bounds: Bounds | null = useMemo(() => {
    if (milestones.length === 0) return null;
    const dates = milestones.map((m) => dayOf(m.due_date));
    const today = Date.now();
    // Always include today, so the marker is never off the edge, and pad a
    // little either side so the first and last bars aren't flush to the frame.
    const start = Math.min(...dates, today) - 3 * DAY;
    const end = Math.max(...dates, today) + 3 * DAY;
    return { start, end: end === start ? start + DAY : end };
  }, [milestones]);

  if (!bounds || milestones.length === 0) return null;

  const plotWidth = Math.max(MIN_PLOT_WIDTH, milestones.length * 34);
  const width = LABEL_WIDTH + plotWidth + RIGHT_PAD;
  const height = TOP_PAD + milestones.length * ROW_HEIGHT + 8;
  const span = bounds.end - bounds.start;

  const x = (iso: string | number): number => {
    const value = typeof iso === "number" ? iso : dayOf(iso);
    return LABEL_WIDTH + ((value - bounds.start) / span) * plotWidth;
  };

  const rowY = (index: number): number => TOP_PAD + index * ROW_HEIGHT;
  const positions = new Map(milestones.map((m, index) => [m.id, index]));
  const todayX = x(Date.now());

  // A bar starts at the milestone it waits on, or at the left edge when it
  // waits on nothing -- so its length reads as the time it actually has.
  const barStart = (milestone: Milestone): number => {
    const upstream = milestone.depends_on
      .map((d) => dayOf(d.due_date))
      .filter((value) => value < dayOf(milestone.due_date));
    return upstream.length > 0 ? Math.max(...upstream) : bounds.start;
  };

  return (
    <figure className="hidden md:block" aria-label="Milestone timeline">
      <div className="overflow-x-auto">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Timeline of ${milestones.length} milestones`}
          className="min-w-full"
        >
          <line
            x1={todayX}
            x2={todayX}
            y1={TOP_PAD - 16}
            y2={height - 4}
            stroke="#b74a09"
            strokeWidth={1.5}
            strokeDasharray="3 3"
          />
          <text x={todayX + 4} y={TOP_PAD - 20} fontSize={10} fill="#b74a09">
            today
          </text>

          {milestones.map((milestone, index) => {
            const isFocused = focused === milestone.id;
            const dimmed = focused !== null && !isFocused;
            const left = x(barStart(milestone));
            const right = x(milestone.due_date);
            const y = rowY(index);
            return (
              <g
                key={milestone.id}
                opacity={dimmed ? 0.35 : 1}
                onMouseEnter={() => setFocused(milestone.id)}
                onMouseLeave={() => setFocused(null)}
              >
                <title>
                  {`${milestone.title} — due ${formatDate(milestone.due_date)} — ${
                    RISK_LABELS[milestone.risk]
                  }`}
                </title>
                <text x={0} y={y + BAR_HEIGHT} fontSize={11} fill="currentColor">
                  {milestone.title.length > 24
                    ? `${milestone.title.slice(0, 23)}…`
                    : milestone.title}
                </text>
                <rect
                  x={Math.min(left, right - 6)}
                  y={y + 2}
                  width={Math.max(6, right - left)}
                  height={BAR_HEIGHT}
                  rx={3}
                  fill={RISK_COLOURS[milestone.risk]}
                />
              </g>
            );
          })}

          {/* Dependency arrows last, so they sit above the bars. The chain
              that is actually blocking is drawn solid; the rest stay faint. */}
          {milestones.flatMap((milestone) =>
            milestone.depends_on.map((upstream) => {
              const fromIndex = positions.get(upstream.id);
              const toIndex = positions.get(milestone.id);
              if (fromIndex === undefined || toIndex === undefined) return null;
              const blocking = milestone.blocked_by.some((b) => b.id === upstream.id);
              const involved = focused === milestone.id || focused === upstream.id;
              return (
                <path
                  key={`${milestone.id}-${upstream.id}`}
                  d={`M ${x(upstream.due_date)} ${rowY(fromIndex) + BAR_HEIGHT / 2 + 2}
                      L ${x(upstream.due_date) + 8} ${rowY(toIndex) + BAR_HEIGHT / 2 + 2}`}
                  stroke={blocking ? "#c53030" : "#9aa3ad"}
                  strokeWidth={blocking || involved ? 1.6 : 0.8}
                  opacity={focused === null || involved ? 1 : 0.25}
                  fill="none"
                />
              );
            }),
          )}
        </svg>
      </div>
      <figcaption className="mt-2 flex flex-wrap gap-3 text-xs text-ink-muted">
        {(["on_track", "at_risk", "overdue", "blocked", "none"] as const).map((risk) => (
          <span key={risk} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: RISK_COLOURS[risk] }}
            />
            {RISK_LABELS[risk]}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
