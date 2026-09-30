import type { MouseEvent } from 'react';
import { activityColor, UNKNOWN } from '../lib/activityColors';
import { formatDuration } from '../lib/format';
import type { ReviewEvent } from '../types/api';

const MAX_TICKS = 7;
const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];

/** Tick positions at a round interval so labels never repeat. */
function ticks(span: number): number[] {
  const step = STEPS.find((s) => span / s <= MAX_TICKS - 1) ?? Math.ceil(span / (MAX_TICKS - 1));
  const out: number[] = [];
  for (let t = 0; t <= span + 1e-6; t += step) out.push(t);
  return out;
}

/**
 * Per-person activity timeline on the real video time axis. Clicking a segment selects and
 * seeks to that event; clicking empty track space seeks to that moment.
 */
export default function ExperimentTimeline({
  people,
  events,
  duration,
  currentTime,
  selectedId,
  onSeek,
}: {
  people: { person_id: string; label: string }[];
  events: ReviewEvent[];
  duration: number;
  currentTime: number;
  selectedId: string | null;
  onSeek: (seconds: number, eventId?: string) => void;
}) {
  const span = Math.max(duration, ...events.map((e) => e.end_seconds ?? 0), 1);
  const pct = (s: number) => `${Math.min(100, Math.max(0, (s / span) * 100))}%`;
  const used = Array.from(new Set(events.map((e) => e.activity_type)));

  const seekFromClick = (e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - rect.left) / rect.width) * span);
  };

  return (
    <div className="space-y-3">
      {people.map((p) => {
        const mine = events.filter((e) => e.person_id === p.person_id);
        return (
          <div key={p.person_id} className="flex items-center gap-3">
            <div className="w-24 text-xs font-semibold text-brand-secondary truncate" title={p.label}>
              {p.label}
            </div>
            <div
              className="relative flex-1 h-9 bg-ice-blue rounded-md cursor-pointer overflow-hidden"
              onClick={seekFromClick}
              role="presentation"
            >
              {mine.map((e) => {
                const start = e.start_seconds ?? 0;
                const end = e.end_seconds ?? start + e.duration;
                const pending = e.review_status === 'pending';
                return (
                  <button
                    key={e.id}
                    type="button"
                    title={`${e.activity_type} · ${e.start_time}–${e.end_time} · ${Math.round(e.confidence * 100)}%${pending ? ' · needs review' : ''}`}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      onSeek(start, e.id);
                    }}
                    className={`absolute top-1 bottom-1 rounded-[3px] border-2 transition-opacity ${
                      selectedId === e.id ? 'ring-2 ring-deep-blue ring-offset-1 z-10' : 'hover:opacity-80'
                    } ${pending ? 'border-brand-warning border-dashed' : 'border-white'}`}
                    style={{
                      left: pct(start),
                      width: `max(4px, calc(${pct(end - start)}))`,
                      background: activityColor(e.activity_type),
                    }}
                    aria-label={`${p.label}: ${e.activity_type} from ${e.start_time} to ${e.end_time}`}
                  />
                );
              })}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-brand-primary pointer-events-none z-20"
                style={{ left: pct(currentTime) }}
              />
            </div>
          </div>
        );
      })}

      <div className="flex items-center gap-3">
        <div className="w-24" />
        <div className="flex-1 relative h-4 text-[11px] text-brand-muted">
          {ticks(span).map((t) => (
            <span key={t} className="absolute -translate-x-1/2" style={{ left: pct(t) }}>
              {formatDuration(t)}
            </span>
          ))}
        </div>
      </div>

      {used.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-xs text-brand-secondary">
          {used.map((a) => (
            <span key={a} className="inline-flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(a) }} />
              {a === UNKNOWN ? 'Unknown / Unexpected' : a}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-2.5 rounded-sm border-2 border-dashed border-brand-warning" />
            needs review
          </span>
        </div>
      )}
    </div>
  );
}
