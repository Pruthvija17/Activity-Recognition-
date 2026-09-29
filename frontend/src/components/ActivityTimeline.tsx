import { api } from '../lib/api';
import { useApiData } from '../hooks/useApiData';
import { DataState } from './StatusNotice';
import type { ActivityEvent } from '../types/api';

const TICKS = 5;

const fmt = (sec: number) => {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

const startOf = (e: ActivityEvent) => e.start_seconds ?? 0;
const endOf = (e: ActivityEvent) => e.end_seconds ?? startOf(e) + e.duration;

export default function ActivityTimeline() {
  const { data, error, loading, reload } = useApiData(() => api.getEvents());
  const events = data ?? [];

  // Group events by person_id
  const personEventsMap: Record<string, ActivityEvent[]> = {};
  events.forEach((evt) => {
    (personEventsMap[evt.person_id] ??= []).push(evt);
  });
  const personIds = Object.keys(personEventsMap);

  // Axis spans the real extent of the events (at least 10 s so short clips stay readable).
  const maxEnd = Math.max(10, ...events.map(endOf));

  return (
    <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm">
      <h3 className="text-lg font-bold text-deep-blue mb-4">Activity Timeline</h3>

      <DataState
        loading={loading}
        error={error}
        isEmpty={personIds.length === 0}
        onRetry={reload}
        emptyMessage="No activity events recorded for timeline view yet."
      >
        <div className="space-y-6">
          {personIds.map((personId) => (
            <div key={personId}>
              <div className="text-sm font-medium text-brand-secondary mb-2">{personId}</div>
              <div className="relative h-12 bg-ice-blue rounded-lg overflow-hidden">
                {personEventsMap[personId].map((evt) => {
                  const isUnknown = evt.activity_type === 'Unknown';
                  const left = (startOf(evt) / maxEnd) * 100;
                  const width = Math.max(0.5, ((endOf(evt) - startOf(evt)) / maxEnd) * 100);
                  return (
                    <div
                      key={evt.id}
                      title={`${evt.activity_type} (${evt.start_time}–${evt.end_time})`}
                      className={`absolute top-0 h-full border-r border-white/60 flex items-center justify-center text-xs font-medium px-1 overflow-hidden whitespace-nowrap ${
                        isUnknown ? 'bg-brand-alert/20 text-brand-alert' : 'bg-sky-blue/20 text-deep-blue'
                      }`}
                      style={{ left: `${left}%`, width: `${width}%` }}
                    >
                      {evt.activity_type} {isUnknown && '⚠'}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {/* Time axis scaled to the data */}
          <div className="flex justify-between text-xs text-brand-muted px-1 pt-2 border-t border-soft-blue">
            {Array.from({ length: TICKS }, (_, i) => (
              <span key={i}>{fmt((maxEnd * i) / (TICKS - 1))}</span>
            ))}
          </div>
        </div>
      </DataState>
    </div>
  );
}
