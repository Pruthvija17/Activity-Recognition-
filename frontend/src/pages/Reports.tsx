import { useState } from 'react';
import { Download, Printer, FileSpreadsheet, FileCheck } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { useApiData } from '../hooks/useApiData';
import { DataState, StatusNotice } from '../components/StatusNotice';

const csvCell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;

export default function Reports() {
  const { data, error, loading, reload } = useApiData(() => api.getReports());
  const reports = data ?? [];
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const downloadCSV = async (expId: string) => {
    setDownloadError(null);
    try {
      const csv = await api.getReportCsv(expId);
      const csvStr = (csv.rows || []).map((r) => r.map(csvCell).join(',')).join('\n');
      const blob = new Blob([csvStr], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `report_${expId}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(`CSV export failed: ${toApiError(err).message}`);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between print:hidden">
        <h1 className="text-2xl font-bold text-deep-blue">Automated Experiment Reports</h1>
        <button
          onClick={handlePrint}
          className="flex items-center gap-2 bg-white border border-soft-blue text-deep-blue font-medium px-4 py-2 rounded-lg hover:bg-ice-blue transition-colors shadow-sm text-sm"
        >
          <Printer className="w-4 h-4" />
          Print / PDF Export
        </button>
      </div>

      {downloadError && <StatusNotice tone="error">{downloadError}</StatusNotice>}

      <div className="grid grid-cols-1 gap-6">
        <DataState
          loading={loading}
          error={error}
          isEmpty={reports.length === 0}
          onRetry={reload}
          emptyMessage="No experiment reports found. Process an experiment video to generate reports."
        >
          {reports.map((rep) => (
            <div key={rep.id} className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between border-b border-soft-blue pb-4 gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <FileCheck className="w-5 h-5 text-sky-blue" />
                    <h3 className="text-lg font-bold text-deep-blue">{rep.experiment}</h3>
                  </div>
                  <p className="text-xs text-brand-secondary mt-1">Generated: {rep.date} | Report ID: {rep.id}</p>
                </div>

                <div className="flex items-center gap-3 print:hidden">
                  <button
                    onClick={() => downloadCSV(rep.experiment_id)}
                    className="flex items-center gap-2 bg-ice-blue hover:bg-soft-blue text-deep-blue font-medium px-3 py-1.5 rounded-lg text-xs transition-colors"
                  >
                    <FileSpreadsheet className="w-3.5 h-3.5 text-brand-success" />
                    Export CSV
                  </button>
                  <button
                    onClick={handlePrint}
                    className="flex items-center gap-2 bg-sky-blue hover:bg-[#2CA1D9] text-white font-medium px-3 py-1.5 rounded-lg text-xs transition-colors shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download Summary
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm bg-ice-blue/40 p-4 rounded-xl border border-soft-blue">
                <div>
                  <div className="text-xs text-brand-muted mb-1">Total Logged Events</div>
                  <div className="font-bold text-deep-blue text-base">{rep.events_count}</div>
                </div>
                <div>
                  <div className="text-xs text-brand-muted mb-1">Workflow Deviations</div>
                  <div className={`font-bold text-base ${rep.deviations > 0 ? 'text-brand-alert' : 'text-brand-success'}`}>
                    {rep.deviations} Flagged
                  </div>
                </div>
                <div>
                  <div className="text-xs text-brand-muted mb-1">Audit Status</div>
                  <div className="font-bold text-brand-success text-base">{rep.status}</div>
                </div>
                <div>
                  <div className="text-xs text-brand-muted mb-1">Avg Confidence</div>
                  <div className="font-bold text-deep-blue text-base">{rep.avg_confidence_pct}%</div>
                </div>
              </div>
            </div>
          ))}
        </DataState>
      </div>
    </div>
  );
}
