import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../lib/api';
import { activityColor } from '../lib/activityColors';
import { confidencePct, formatDuration } from '../lib/format';
import { useApiData } from '../hooks/useApiData';
import { DataState } from '../components/StatusNotice';
import type { Analytics as AnalyticsData } from '../types/api';

// Recessive chart chrome; text uses text tokens, never series colours.
const GRID = '#E0F2FE';
const AXIS_TEXT = '#475569';
const SEQUENTIAL = '#2a78d6';
const tick = { fill: AXIS_TEXT, fontSize: 12 };

const pct = (v: number | null) => (v == null ? '—' : `${confidencePct(v)}%`);

function Tile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-2xl p-5 border border-soft-blue shadow-sm">
      <div className="text-xs font-medium text-brand-secondary">{label}</div>
      <div className="text-2xl font-bold text-brand-primary mt-1">{value}</div>
      {sub && <div className="text-xs text-brand-muted mt-1">{sub}</div>}
    </div>
  );
}

function Panel({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm">
      <h3 className="text-lg font-bold text-deep-blue">{title}</h3>
      {note && <p className="text-xs text-brand-muted mt-1">{note}</p>}
      <div className="mt-4">{children}</div>
    </div>
  );
}

function ActivityCharts({ a }: { a: AnalyticsData }) {
  const dist = a.activity_distribution;
  const height = Math.max(160, dist.length * 40);
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <Panel title="Time per activity" note="Total duration of events for each activity (rejected events excluded).">
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dist} layout="vertical" margin={{ left: 8, right: 56, top: 4, bottom: 4 }}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" tick={tick} tickFormatter={(v) => formatDuration(Number(v))} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={190} tick={tick} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: '#EFF9FF' }}
                formatter={(v) => [formatDuration(Number(v)), 'Time']}
                labelStyle={{ color: '#0F172A', fontWeight: 600 }}
              />
              <Bar dataKey="seconds" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                {dist.map((d) => (
                  <Cell key={d.name} fill={activityColor(d.name)} />
                ))}
                <LabelList
                  dataKey="seconds"
                  position="right"
                  formatter={(v) => formatDuration(Number(v))}
                  style={{ fill: AXIS_TEXT, fontSize: 12 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel title="Activity summary">
        <table className="w-full text-sm">
          <thead className="text-xs text-brand-muted text-left">
            <tr>
              <th className="py-2 px-3 font-medium">Activity</th>
              <th className="py-2 px-3 font-medium text-right">Events</th>
              <th className="py-2 px-3 font-medium text-right">Time</th>
              <th className="py-2 px-3 font-medium text-right">Share</th>
              <th className="py-2 px-3 font-medium text-right">Avg conf.</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-soft-blue">
            {dist.map((d) => (
              <tr key={d.name}>
                <td className="py-2 px-3">
                  <span className="inline-flex items-center gap-2 text-brand-primary">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(d.name) }} />
                    {d.name}
                  </span>
                </td>
                <td className="py-2 px-3 text-right text-brand-secondary">{d.count}</td>
                <td className="py-2 px-3 text-right text-brand-secondary">{formatDuration(d.seconds)}</td>
                <td className="py-2 px-3 text-right text-brand-secondary">
                  {a.total_activity_seconds ? `${Math.round((d.seconds / a.total_activity_seconds) * 100)}%` : '—'}
                </td>
                <td className="py-2 px-3 text-right text-brand-secondary">{pct(d.avg_confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

function PersonCharts({ a }: { a: AnalyticsData }) {
  const activities = a.activity_distribution.map((d) => d.name);
  const rows = a.person_stats.map((p) => ({ name: p.name, ...p.seconds_by_activity }));
  const height = Math.max(140, rows.length * 44 + 60);
  return (
    <Panel title="Person-wise statistics" note="Each person's time split by activity. People are numbered per video in order of appearance.">
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
            <CartesianGrid horizontal={false} stroke={GRID} />
            <XAxis type="number" tick={tick} tickFormatter={(v) => formatDuration(Number(v))} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={190} tick={tick} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: '#EFF9FF' }} formatter={(v, n) => [formatDuration(Number(v)), n]} />
            <Legend wrapperStyle={{ fontSize: 12, color: AXIS_TEXT }} />
            {activities.map((act, i) => (
              <Bar
                key={act}
                dataKey={act}
                stackId="time"
                fill={activityColor(act)}
                stroke="#ffffff"
                strokeWidth={2}
                barSize={20}
                radius={i === activities.length - 1 ? [0, 4, 4, 0] : 0}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className="w-full text-sm mt-6">
        <thead className="text-xs text-brand-muted text-left">
          <tr>
            <th className="py-2 px-3 font-medium">Person</th>
            <th className="py-2 px-3 font-medium text-right">Events</th>
            <th className="py-2 px-3 font-medium text-right">Active time</th>
            <th className="py-2 px-3 font-medium">Main activity</th>
            <th className="py-2 px-3 font-medium text-right">Unknown</th>
            <th className="py-2 px-3 font-medium text-right">Avg conf.</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-soft-blue">
          {a.person_stats.map((p) => (
            <tr key={p.person_id}>
              <td className="py-2 px-3 font-medium text-brand-primary">{p.name}</td>
              <td className="py-2 px-3 text-right text-brand-secondary">{p.events}</td>
              <td className="py-2 px-3 text-right text-brand-secondary">{formatDuration(p.active_seconds)}</td>
              <td className="py-2 px-3 text-brand-secondary">{p.top_activity ?? '—'}</td>
              <td className={`py-2 text-right ${p.unknowns ? 'text-brand-alert font-semibold' : 'text-brand-secondary'}`}>{p.unknowns}</td>
              <td className="py-2 px-3 text-right text-brand-secondary">{pct(p.avg_confidence)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function ConfidenceChart({ a }: { a: AnalyticsData }) {
  return (
    <Panel title="Confidence distribution" note="Number of events per confidence band. Low bands are candidates for review.">
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={a.confidence_histogram} margin={{ left: 0, right: 8, top: 16, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="bucket" tick={tick} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} width={32} />
            <Tooltip cursor={{ fill: '#EFF9FF' }} formatter={(v) => [v, 'Events']} />
            <Bar dataKey="count" fill={SEQUENTIAL} barSize={36} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              <LabelList dataKey="count" position="top" style={{ fill: AXIS_TEXT, fontSize: 12 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export default function Analytics() {
  const [experimentId, setExperimentId] = useState('');
  const videos = useApiData(() => api.listVideos());
  const completed = (videos.data ?? []).filter((v) => v.status === 'completed');
  const { data: a, error, loading, reload } = useApiData(
    () => api.getAnalytics(experimentId || undefined),
    experimentId,
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-deep-blue">Analytics</h1>
        <div className="flex items-center gap-3">
          <select
            value={experimentId}
            onChange={(e) => setExperimentId(e.target.value)}
            className="bg-white border border-soft-blue rounded-lg px-3 py-2 text-sm text-deep-blue"
            aria-label="Filter by experiment"
          >
            <option value="">All experiments</option>
            {completed.map((v) => (
              <option key={v.video_id} value={v.video_id}>
                {v.filename} ({v.video_id})
              </option>
            ))}
          </select>
          <Link
            to="/reports"
            className="bg-white border border-soft-blue px-4 py-2 rounded-lg text-sm font-medium text-brand-primary hover:bg-ice-blue shadow-sm"
          >
            Go to Reports
          </Link>
        </div>
      </div>

      <DataState
        loading={loading}
        error={error}
        isEmpty={!a || a.total_events === 0}
        onRetry={reload}
        emptyMessage="No activity data available. Process an experiment first."
      >
        {a && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
              <Tile label="Total activity time" value={formatDuration(a.total_activity_seconds)} />
              <Tile
                label="Activity events"
                value={a.total_events}
                sub={a.rejected_events ? `${a.rejected_events} rejected, excluded` : undefined}
              />
              <Tile label="People tracked" value={a.people_count} sub={`in ${a.experiments_count} experiment(s)`} />
              <Tile label="Unknown events" value={a.unknown_events} />
              <Tile label="Pending review" value={a.pending_review} sub={`${a.reviewed_events} reviewed`} />
              <Tile label="Avg confidence" value={pct(a.avg_confidence)} sub={a.activity_engine} />
            </div>
            <ActivityCharts a={a} />
            <PersonCharts a={a} />
            <ConfidenceChart a={a} />
          </>
        )}
      </DataState>
    </div>
  );
}
