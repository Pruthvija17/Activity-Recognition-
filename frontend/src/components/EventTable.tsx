import { CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { confidencePct } from '../lib/format';
import { useApiData } from '../hooks/useApiData';

export default function EventTable() {
  const { data, error } = useApiData(() => api.getEvents());
  const events = data ?? [];

  return (
    <div className="bg-white rounded-2xl border border-soft-blue shadow-sm overflow-hidden">
      <div className="p-6 border-b border-soft-blue flex justify-between items-center">
        <h3 className="text-lg font-bold text-deep-blue">Activity Events Log</h3>
        <span className="text-xs text-brand-secondary bg-ice-blue px-3 py-1 rounded-full font-medium">
          {events.length} Events Total
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-ice-blue/50 text-brand-secondary font-medium">
            <tr>
              <th className="px-6 py-4">Person ID</th>
              <th className="px-6 py-4">Activity</th>
              <th className="px-6 py-4">Start</th>
              <th className="px-6 py-4">End</th>
              <th className="px-6 py-4">Duration</th>
              <th className="px-6 py-4">Confidence</th>
              <th className="px-6 py-4">Status</th>
              <th className="px-6 py-4">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-soft-blue">
            {events.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-8 text-center text-brand-secondary text-xs">
                  {error && !data
                    ? error.message
                    : 'No activity events logged yet. Upload and process a video experiment to generate activity logs.'}
                </td>
              </tr>
            ) : (
              events.map((event) => {
                const confPct = confidencePct(event.confidence);
                return (
                  <tr key={event.id} className="hover:bg-ice-blue/30 transition-colors">
                    <td className="px-6 py-4 font-medium">{event.person_id}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                        event.activity_type === 'Unknown' ? 'bg-red-50 text-brand-alert font-bold' : 'bg-sky-blue/10 text-deep-blue'
                      }`}>
                        {event.activity_type === 'Unknown' && <AlertCircle className="w-3.5 h-3.5" />}
                        {event.activity_type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-brand-secondary font-mono text-xs">{event.start_time}</td>
                    <td className="px-6 py-4 text-brand-secondary font-mono text-xs">{event.end_time}</td>
                    <td className="px-6 py-4 text-brand-secondary">{event.duration}s</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-ice-blue rounded-full overflow-hidden">
                          <div 
                            className={`h-full ${confPct > 80 ? 'bg-brand-success' : 'bg-brand-warning'}`}
                            style={{ width: `${confPct}%` }}
                          />
                        </div>
                        <span className="text-xs text-brand-secondary">{confPct}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {event.status === 'Confirmed' ? (
                        <span className="flex items-center gap-1.5 text-brand-success text-xs font-medium">
                          <CheckCircle2 className="w-4 h-4" />
                          Confirmed
                        </span>
                      ) : event.status === 'Rejected' ? (
                        <span className="flex items-center gap-1.5 text-brand-muted text-xs font-medium line-through">
                          Rejected
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-brand-warning text-xs font-medium">
                          <AlertTriangle className="w-4 h-4" />
                          Review
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {event.status === 'Review' ? (
                        <Link to="/review" className="text-sky-blue hover:text-deep-blue font-bold text-xs underline transition-colors">
                          Review Event
                        </Link>
                      ) : (
                        <span className="text-brand-muted text-xs">Logged</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
