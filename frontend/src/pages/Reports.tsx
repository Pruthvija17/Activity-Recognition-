import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, FileCheck, FileJson, FileSpreadsheet, FileText } from 'lucide-react';
import { api } from '../lib/api';
import { confidencePct, formatDuration, parseServerDate } from '../lib/format';
import { useApiData } from '../hooks/useApiData';
import { DataState } from '../components/StatusNotice';

function Figure({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'alert' | 'ok' }) {
  const color = tone === 'alert' ? 'text-brand-alert' : tone === 'ok' ? 'text-brand-success' : 'text-deep-blue';
  return (
    <div>
      <div className="text-xs text-brand-muted mb-1">{label}</div>
      <div className={`font-bold text-base ${color}`}>{value}</div>
    </div>
  );
}

export default function Reports() {
  const { data, error, loading, reload } = useApiData(() => api.getReports());
  const reports = data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-deep-blue">Experiment Reports</h1>
        <p className="text-sm text-brand-secondary mt-1">
          One report per completed experiment: experiment information, participants, activity summary and log,
          exceptions (unknown, low-confidence, workflow deviations) and review status.
        </p>
      </div>

      <DataState
        loading={loading}
        error={error}
        isEmpty={reports.length === 0}
        onRetry={reload}
        emptyMessage="No experiment reports found. Process an experiment video to generate reports."
      >
        <div className="grid grid-cols-1 gap-6">
          {reports.map((rep) => (
            <div key={rep.report_id} className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between border-b border-soft-blue pb-4 gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <FileCheck className="w-5 h-5 text-sky-blue flex-shrink-0" />
                    <Link to={`/experiments/${rep.experiment_id}`} className="text-lg font-bold text-deep-blue hover:underline truncate">
                      {rep.video}
                    </Link>
                  </div>
                  <p className="text-xs text-brand-secondary mt-1">
                    {rep.report_id}
                    {rep.processed_at && ` · processed ${parseServerDate(rep.processed_at).toLocaleString()}`}
                    {` · ${formatDuration(rep.duration_seconds)} video`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <a href={api.reportUrl(rep.experiment_id, 'pdf')} className="flex items-center gap-1.5 bg-sky-blue hover:bg-[#2CA1D9] text-white font-bold px-3 py-1.5 rounded-lg text-xs">
                    <FileText className="w-3.5 h-3.5" /> PDF
                  </a>
                  <a href={api.reportUrl(rep.experiment_id, 'csv')} className="flex items-center gap-1.5 bg-ice-blue hover:bg-soft-blue text-deep-blue font-bold px-3 py-1.5 rounded-lg text-xs">
                    <FileSpreadsheet className="w-3.5 h-3.5" /> CSV
                  </a>
                  <a href={api.reportUrl(rep.experiment_id, 'json')} className="flex items-center gap-1.5 bg-ice-blue hover:bg-soft-blue text-deep-blue font-bold px-3 py-1.5 rounded-lg text-xs">
                    <FileJson className="w-3.5 h-3.5" /> JSON
                  </a>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-6 gap-4 text-sm bg-ice-blue/40 p-4 rounded-xl border border-soft-blue">
                <Figure label="Activity events" value={rep.events} />
                <Figure label="People" value={rep.people} />
                <Figure label="Unknown events" value={rep.unknown_events} tone={rep.unknown_events ? 'alert' : undefined} />
                <Figure label="Pending review" value={rep.pending_review} tone={rep.pending_review ? 'alert' : undefined} />
                <Figure label="Avg confidence" value={rep.avg_confidence == null ? '—' : `${confidencePct(rep.avg_confidence)}%`} />
                <Figure
                  label="Workflow"
                  tone={rep.workflow_compliant ? 'ok' : 'alert'}
                  value={
                    <span className="inline-flex items-center gap-1">
                      {rep.workflow_compliant ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                      {rep.workflow_compliant ? 'Matches' : `${rep.workflow_deviations} deviations`}
                    </span>
                  }
                />
              </div>
            </div>
          ))}
        </div>
      </DataState>
    </div>
  );
}
