import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface ActivityCount {
  name: string;
  value: number;
  color: string;
}

interface PersonStat {
  name: string;
  activities: number;
  unknowns: number;
  avg_confidence: number;
}

export default function Analytics() {
  const [activityData, setActivityData] = useState<ActivityCount[]>([]);
  const [personData, setPersonData] = useState<PersonStat[]>([]);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/analytics');
        if (res.ok) {
          const data = await res.json();
          setActivityData(data.activity_distribution || []);
          setPersonData(data.person_stats || []);
        }
      } catch (err) {
        console.error('Failed to fetch analytics:', err);
      }
    };
    fetchAnalytics();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-deep-blue">Analytics</h1>
        <button className="bg-white border border-soft-blue px-4 py-2 rounded-lg text-sm font-medium text-brand-primary hover:bg-ice-blue transition-colors shadow-sm">
          Export Report
        </button>
      </div>

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
