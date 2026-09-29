import { useEffect, useState } from 'react';
import ActivityTimeline from '../components/ActivityTimeline';
import EventTable from '../components/EventTable';

interface RecentEvent {
  person_id: string;
  activity: string;
  confidence: number;
  start_time: string;
  end_time: string;
  status: string;
}

interface StatusPayload {
  type: string;
  timestamp: string;
  backend_online: boolean;
  model_ready: boolean;
  last_experiment_id: string | null;
  last_experiment_name: string | null;
  last_experiment_status: string | null;
  recent_events: RecentEvent[];
  live_detections: never[];
  note: string;
}

export default function LiveMonitor() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  useEffect(() => {
    let ws: WebSocket | null = null;

    try {
      ws = new WebSocket('ws://localhost:8000/ws/live');
      ws.onopen = () => setIsConnected(true);
      ws.onmessage = (evt) => {
        try {
          const data: StatusPayload = JSON.parse(evt.data);
          setStatus(data);
        } catch (e) {
          console.error('Error parsing WS message:', e);
        }
      };
      ws.onclose = () => setIsConnected(false);
      ws.onerror = () => setIsConnected(false);
    } catch {
      setIsConnected(false);
    }

    return () => {
      if (ws) ws.close();
    };
  }, []);

  const recentEvents = status?.recent_events || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-deep-blue">Live Monitor</h1>
        <div className="flex items-center gap-2 text-sm font-medium text-brand-secondary bg-white px-4 py-2 rounded-lg border border-soft-blue">
          <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-brand-success animate-pulse' : 'bg-brand-warning'}`}></span>
          {isConnected ? 'Live WebSocket Connected' : 'WebSocket Disconnected'}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* System Status Panel */}
        <div className="xl:col-span-2 bg-slate-950 rounded-2xl overflow-hidden aspect-video relative flex flex-col items-center justify-center border-4 border-white shadow-sm gap-3 px-8">
          <p className="font-bold text-lg text-sky-blue">BAS Real-Time Camera Stream</p>
          <p className="text-xs font-mono text-white/50">
            {status
              ? `Backend: Online | Model: ${status.model_ready ? 'Ready' : 'Weights Missing'} | ${status.timestamp}`
              : 'Awaiting connection…'}
          </p>
          {status?.last_experiment_name && (
            <p className="text-xs font-mono text-white/40">
              Last Experiment: <span className="text-white/70">{status.last_experiment_name}</span>
              {' '}({status.last_experiment_status})
            </p>
          )}
          {!status?.model_ready && status && (
            <div className="mt-2 bg-red-900/40 border border-red-500/50 text-red-300 text-xs rounded-lg px-4 py-2 text-center max-w-sm">
              ⚠ AI model weights are missing. Upload model files to <span className="font-mono">backend/weights/</span> to enable live inference.
            </div>
          )}
          <p className="text-[10px] text-white/20 mt-2">{status?.note}</p>
        </div>

        {/* Recent Events Panel */}
        <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6">
          <h3 className="text-lg font-bold text-deep-blue mb-4">Recent Activity Events</h3>

          <div className="space-y-4">
            {recentEvents.length === 0 ? (
              <div className="p-4 text-center text-xs text-brand-secondary">
                No recent activity events. Process a video experiment to see results here.
              </div>
            ) : (
              recentEvents.map((evt, idx) => {
                const isUnknown = evt.activity === 'Unknown';
                const confPct = Math.round(evt.confidence > 1 ? evt.confidence : evt.confidence * 100);
                return (
                  <div
                    key={idx}
                    className={`p-4 rounded-xl border transition-all ${
                      isUnknown ? 'bg-red-50/70 border-red-200' : 'bg-ice-blue border-soft-blue'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-1">
                      <span className="text-xs font-bold text-brand-secondary">{evt.person_id}</span>
                      <span className={`text-xs font-bold ${isUnknown ? 'text-brand-alert' : 'text-sky-blue'}`}>
                        {confPct}%
                      </span>
                    </div>
                    <div className={`text-lg font-bold ${isUnknown ? 'text-brand-alert' : 'text-deep-blue'}`}>
                      {evt.activity} {isUnknown && '⚠'}
                    </div>
                    <div className="text-xs text-brand-muted mt-1 font-mono">
                      {evt.start_time} – {evt.end_time}
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${
                        evt.status === 'Confirmed' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                      }`}>
                        {evt.status}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      <ActivityTimeline />
      <EventTable />
    </div>
  );
}
