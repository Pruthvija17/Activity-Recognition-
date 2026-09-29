import { useEffect, useState } from 'react';
import { Download, Printer, FileSpreadsheet, FileCheck } from 'lucide-react';

interface ReportItem {
  id: string;
  experiment_id: string;
  experiment: string;
  date: string;
  events_count: number;
  confirmed_count: number;
  unknown_count: number;
  deviations: number;
  avg_confidence_pct: number;
  status: string;
}

export default function Reports() {
  const [reports, setReports] = useState<ReportItem[]>([]);

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/reports');
        if (res.ok) {
          const data = await res.json();
          setReports(data);
        }
      } catch (err) {
        console.error('Failed to fetch reports:', err);
      }
    };
    fetchReports();
  }, []);

  const downloadCSV = async (expId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/reports/${expId}/csv`);
      if (!res.ok) return;
      const data = await res.json();
      const rows: string[][] = data.rows || [];
      const csvStr = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n');
      const blob = new Blob([csvStr], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `report_${expId}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      console.error('CSV download error:', err);
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

      <div className="grid grid-cols-1 gap-6">
        {reports.length === 0 ? (
          <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6 text-center text-sm text-brand-secondary">
            No experiment reports found. Process an experiment video to generate reports.
          </div>
        ) : (
          reports.map((rep) => (
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
          ))
        )}
      </div>
    </div>
  );
}
