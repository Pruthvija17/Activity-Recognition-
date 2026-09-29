import { Outlet, NavLink } from 'react-router-dom';
import { Activity, LayoutDashboard, MonitorPlay, FlaskConical, ClipboardList, BarChart2, FileText, Settings, Cpu } from 'lucide-react';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { StatusNotice } from './StatusNotice';
import { MESSAGES } from '../lib/messages';

const navItems = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Live Monitor', path: '/live', icon: MonitorPlay },
  { name: 'Experiments', path: '/experiments', icon: FlaskConical },
  { name: 'Review Queue', path: '/review', icon: ClipboardList },
  { name: 'Analytics', path: '/analytics', icon: BarChart2 },
  { name: 'Reports', path: '/reports', icon: FileText },
];

type Level = 'ok' | 'bad' | 'pending';

const dotClass: Record<Level, string> = {
  ok: 'bg-brand-success',
  bad: 'bg-brand-alert',
  pending: 'bg-brand-warning animate-pulse',
};

function StatusPill({ label, value, level }: { label: string; value: string; level: Level }) {
  return (
    <div className="flex items-center gap-2 text-xs whitespace-nowrap">
      <span className={`w-2 h-2 rounded-full ${dotClass[level]}`} />
      <span className="text-brand-muted">{label}:</span>
      <span className="font-semibold text-brand-primary">{value}</span>
    </div>
  );
}

export default function Layout() {
  const { connection, status, refresh } = useSystemStatus();
  const checking = connection === 'checking';
  const online = connection === 'online';

  const backendLevel: Level = checking ? 'pending' : online ? 'ok' : 'bad';
  const dbLevel: Level = !online ? (checking ? 'pending' : 'bad') : status?.database ? 'ok' : 'bad';
  const modelLevel: Level = !online ? (checking ? 'pending' : 'bad') : status?.model_ready ? 'ok' : 'bad';
  const unknownText = checking ? 'Checking…' : 'Unknown';

  return (
    <div className="flex h-screen bg-ice-blue overflow-hidden font-sans text-brand-primary">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-soft-blue flex flex-col">
        <div className="p-6 flex items-center gap-3 border-b border-soft-blue">
          <div className="bg-deep-blue p-2 rounded-lg">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-deep-blue leading-tight">BAS AI</h1>
            <p className="text-xs text-brand-secondary">Activity Intelligence</p>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-soft-blue text-sky-blue'
                    : 'text-brand-secondary hover:bg-ice-blue hover:text-brand-primary'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-soft-blue">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-soft-blue text-sky-blue'
                  : 'text-brand-secondary hover:bg-ice-blue hover:text-brand-primary'
              }`
            }
          >
            <Settings className="w-5 h-5" />
            Settings
          </NavLink>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header: every value here comes from /api/system/status */}
        <header className="h-16 bg-white border-b border-soft-blue flex items-center justify-between px-8 gap-4">
          <div className="flex items-center gap-6">
            <StatusPill
              label="Backend"
              value={checking ? 'Checking…' : online ? 'Connected' : 'Offline'}
              level={backendLevel}
            />
            <StatusPill
              label="Database"
              value={online ? (status?.database ? 'Connected' : 'Error') : unknownText}
              level={dbLevel}
            />
            <StatusPill
              label="AI Models"
              value={online ? (status?.model_ready ? 'Ready' : 'Not ready') : unknownText}
              level={modelLevel}
            />
          </div>
          {online && status && (
            <div className="flex items-center gap-2 text-xs">
              <span
                className="px-3 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 font-semibold whitespace-nowrap"
                title={
                  status.trained_activity_model
                    ? 'Activity labels come from a trained model.'
                    : 'No trained activity model yet: labels come from transparent rules on pose keypoints.'
                }
              >
                {status.activity_engine}
              </span>
              <span className="flex items-center gap-1 px-3 py-1 rounded-full bg-soft-blue text-deep-blue font-medium whitespace-nowrap">
                <Cpu className="w-3.5 h-3.5" />
                {status.cuda ? status.device : 'CPU'}
              </span>
            </div>
          )}
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-8 space-y-6">
          {connection === 'offline' && (
            <StatusNotice
              tone="error"
              title="Backend Offline"
              action={
                <button onClick={refresh} className="text-xs font-bold underline whitespace-nowrap">
                  Retry now
                </button>
              }
            >
              {MESSAGES.backendOffline} Pages reconnect automatically.
            </StatusNotice>
          )}
          {online && status && !status.database && (
            <StatusNotice tone="error" title="Database unavailable">
              The backend cannot reach its database. Check the backend logs.
            </StatusNotice>
          )}
          {online && status && !status.model_ready && (
            <StatusNotice tone="warning" title="AI model not ready">
              {MESSAGES.modelMissing}
              {status.model_error && <span className="block mt-1 font-mono text-xs">{status.model_error}</span>}
            </StatusNotice>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
