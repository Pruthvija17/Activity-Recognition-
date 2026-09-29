import Card from '../components/Card';
import { DataState } from '../components/StatusNotice';
import { useApiData } from '../hooks/useApiData';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { api } from '../lib/api';
import { confidencePct } from '../lib/format';
import type { ActivityEvent, Experiment } from '../types/api';

function summarise(experiments: Experiment[], events: ActivityEvent[]) {
  const unknowns = events.filter((e) => e.activity_type === 'Unknown' || e.status === 'Review').length;
  const people = new Set(events.map((e) => e.person_id)).size;
  const avg =
    events.length > 0
      ? `${Math.round(events.reduce((sum, e) => sum + confidencePct(e.confidence), 0) / events.length)}%`
      : '—';
  const processed = experiments.filter((e) => e.status === 'processed' || e.status === 'completed').length;
  return { unknowns, people, avg, processed };
}

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
  const { data, error, loading, reload } = useApiData(async () => {
    const [experiments, events] = await Promise.all([api.getExperiments(), api.getEvents()]);
    return { experiments, events };
  });

  const s = data ? summarise(data.experiments, data.events) : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-deep-blue">Dashboard</h1>

      <DataState loading={loading} error={error} isEmpty={!data} onRetry={reload}>
        {data && s && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <Card title={`Experiments (${s.processed} processed)`} value={data.experiments.length} />
            <Card title="People Detected" value={s.people} />
            <Card title="Unknown / Review Events" value={s.unknowns} alert={s.unknowns > 0} />
            <Card title="Avg Confidence" value={s.avg} />
          </div>
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
