import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import Card from '../components/Card';
import ProgressBar from '../components/ProgressBar';
import { DataState } from '../components/StatusNotice';
import { useApiData } from '../hooks/useApiData';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { api } from '../lib/api';
import { activityColor } from '../lib/activityColors';
import { confidencePct } from '../lib/format';

const JOB_POLL_MS = 2000;

function StatusRow({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex justify-between py-2 text-sm">
      <span className="text-brand-secondary">{label}</span>
      <span className={`font-semibold ${ok ? 'text-brand-success' : 'text-brand-alert'}`}>{value}</span>
    </div>
  );
}

export default function Dashboard() {
  const { online, status } = useSystemStatus();
  const { data, error, loading, reload } = useApiData(() => api.getDashboard());
  const jobActive = !!data?.current_job;

  // Keep the current-job card live while something is processing.
  useEffect(() => {
    if (!jobActive) return;
    const id = setInterval(reload, JOB_POLL_MS);
    return () => clearInterval(id);
  }, [jobActive, reload]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-deep-blue">Dashboard</h1>

      <DataState loading={loading} error={error} isEmpty={!data} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card
                title={`Experiments (${data.experiments.active} active, ${data.experiments.completed} completed)`}
                value={data.experiments.total}
              />
              <Card title="People Detected" value={data.people_detected} />
              <Card title="Pending Review" value={data.pending_review} alert={data.pending_review > 0} />
              <Card
                title="Avg Confidence"
                value={data.avg_confidence == null ? '—' : `${confidencePct(data.avg_confidence)}%`}
              />
            </div>

            {data.current_job && (
              <div className="bg-white rounded-2xl p-6 border border-soft-blue shadow-sm space-y-3">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-bold text-deep-blue">Processing now</h3>
                  <Link to="/experiments" className="text-sm font-bold text-sky-blue underline">Open Experiments</Link>
                </div>
                <ProgressBar
                  value={data.current_job.progress}
                  indeterminate={data.current_job.status === 'queued'}
                  label={`${data.current_job.filename} — ${data.current_job.status}`}
                />
              </div>
            )}

            <div className="bg-white rounded-2xl border border-soft-blue shadow-sm overflow-hidden">
              <div className="p-6 border-b border-soft-blue flex justify-between items-center">
                <h3 className="text-lg font-bold text-deep-blue">Recent Activity Events</h3>
                {data.pending_review > 0 && (
                  <Link to="/review" className="flex items-center gap-1 text-sm font-bold text-brand-warning">
                    <AlertTriangle className="w-4 h-4" /> {data.pending_review} to review
                  </Link>
                )}
              </div>
              {data.recent_events.length === 0 ? (
                <p className="p-6 text-center text-sm text-brand-secondary">
                  No activity data available. Process an experiment first.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-soft-blue">
                    {data.recent_events.map((e) => (
                      <tr key={e.id}>
                        <td className="px-6 py-3 text-brand-secondary truncate max-w-48">{e.video}</td>
                        <td className="px-6 py-3 font-medium text-brand-primary whitespace-nowrap">{e.person}</td>
                        <td className="px-6 py-3">
                          <span className="inline-flex items-center gap-2 text-brand-primary">
                            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(e.activity) }} />
                            {e.activity}
                          </span>
                        </td>
                        <td className="px-6 py-3 font-mono text-xs text-brand-secondary whitespace-nowrap">
                          {e.start_time} – {e.end_time}
                        </td>
                        <td className="px-6 py-3 text-xs text-brand-secondary">{confidencePct(e.confidence)}%</td>
                        <td className="px-6 py-3 text-xs">
                          {e.review_status === 'pending' ? (
                            <span className="text-brand-warning font-semibold">Needs review</span>
                          ) : (
                            <span className="text-brand-muted capitalize">{e.review_status === 'auto' ? 'accepted' : e.review_status}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </DataState>

      <div className="bg-white rounded-2xl p-6 border border-soft-blue shadow-sm">
        <h3 className="text-lg font-bold text-deep-blue mb-2">System Status</h3>
        {online && status ? (
          <div className="divide-y divide-soft-blue">
            <StatusRow label="Backend" ok value={`Connected (v${status.version})`} />
            <StatusRow label="Database" ok={status.database} value={status.database ? 'Connected' : 'Error'} />
            <StatusRow
              label="Person detector (YOLO pose)"
              ok={status.yolo_model}
              value={status.yolo_model ? 'Ready' : 'Not loaded'}
            />
            <StatusRow label="Activity engine" ok={status.activity_model} value={status.activity_engine} />
            <StatusRow
              label="Trained activity model"
              ok={status.trained_activity_model}
              value={status.trained_activity_model ? 'Loaded' : 'Not trained yet (using rule-based baseline)'}
            />
            <StatusRow label="Compute" ok value={status.cuda ? `GPU — ${status.device}` : 'CPU (no CUDA GPU)'} />
          </div>
        ) : (
          <p className="text-sm text-brand-secondary">Status unavailable while the backend is offline.</p>
        )}
      </div>
    </div>
  );
}
