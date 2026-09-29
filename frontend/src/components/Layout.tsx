import { useEffect, useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { Activity, LayoutDashboard, MonitorPlay, FlaskConical, ClipboardList, BarChart2, FileText, Settings } from 'lucide-react';
import { api } from '../lib/api';

const navItems = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Live Monitor', path: '/live', icon: MonitorPlay },
  { name: 'Experiments', path: '/experiments', icon: FlaskConical },
  { name: 'Review Queue', path: '/review', icon: ClipboardList },
  { name: 'Analytics', path: '/analytics', icon: BarChart2 },
  { name: 'Reports', path: '/reports', icon: FileText },
];

export default function Layout() {
  const [backendOnline, setBackendOnline] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      const res = await api.getHealth();
      setBackendOnline(res.status === 'ok');
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

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
        {/* Top Header */}
        <header className="h-16 bg-white border-b border-soft-blue flex items-center justify-between px-8">
          <div className="flex items-center gap-2 text-sm font-medium text-brand-secondary">
            <span className={`w-2 h-2 rounded-full ${backendOnline ? 'bg-brand-success animate-pulse' : 'bg-brand-alert'}`}></span>
            {backendOnline ? 'Backend Online' : 'Backend Offline'}
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="px-3 py-1 rounded-full bg-soft-blue text-deep-blue font-medium">
              Demo Mode
            </span>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
