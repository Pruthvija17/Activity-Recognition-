import { Link } from 'react-router-dom';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { api } from '../lib/api';
import { useApiData } from '../hooks/useApiData';
import { StatusNotice } from '../components/StatusNotice';

export default function Analytics() {
  const { data, error } = useApiData(() => api.getAnalytics());
  const activityData = data?.activity_distribution ?? [];
  const personData = data?.person_stats ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-deep-blue">Analytics</h1>
        <Link
          to="/reports"
          className="bg-white border border-soft-blue px-4 py-2 rounded-lg text-sm font-medium text-brand-primary hover:bg-ice-blue transition-colors shadow-sm"
        >
          Go to Reports
        </Link>
      </div>

      {error && error.kind === 'http' && (
        <StatusNotice tone="error" title="Could not load analytics">
          {error.message}
        </StatusNotice>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm">
          <h3 className="text-lg font-bold text-deep-blue mb-6">Activity Distribution</h3>
          <div className="h-80">
            {activityData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-brand-secondary">
                No activity data recorded yet.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={activityData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {activityData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm">
          <h3 className="text-lg font-bold text-deep-blue mb-6">Person-wise Statistics</h3>
          <div className="h-80">
            {personData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-brand-secondary">
                No person statistics recorded yet.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={personData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E0F2FE" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} />
                  <YAxis axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: '#EFF9FF' }} />
                  <Legend />
                  <Bar dataKey="activities" name="Known Activities" fill="#38BDF8" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="unknowns" name="Unknown Events" fill="#EF4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
