import { useEffect, useState } from 'react';
import Card from '../components/Card';

interface EventData {
  id: string;
  person_id: string;
  activity_type: string;
  confidence: number;
  status: string;
}

export default function Dashboard() {
  const [experimentsCount, setExperimentsCount] = useState<number>(0);
  const [peopleCount, setPeopleCount] = useState<number>(0);
  const [unknownCount, setUnknownCount] = useState<number>(0);
  const [avgConfidence, setAvgConfidence] = useState<string>('0%');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const expRes = await fetch('http://localhost:8000/experiments/');
        if (expRes.ok) {
          const expData = await expRes.json();
          setExperimentsCount(expData.length);
        }

        const evtRes = await fetch('http://localhost:8000/events/');
        if (evtRes.ok) {
          const evtData: EventData[] = await evtRes.json();

          const unknowns = evtData.filter(e => e.activity_type === 'Unknown' || e.status === 'Review');
          setUnknownCount(unknowns.length);

          const uniquePeople = new Set(evtData.map(e => e.person_id));
          setPeopleCount(uniquePeople.size);

          if (evtData.length > 0) {
            const sumConf = evtData.reduce((acc, curr) => acc + (curr.confidence > 1 ? curr.confidence / 100 : curr.confidence), 0);
            const avg = Math.round((sumConf / evtData.length) * 100);
            setAvgConfidence(`${avg}%`);
          }
        }
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
      }
    };

    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-deep-blue">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card title="Active Experiments" value={experimentsCount} />
        <Card title="People Detected" value={peopleCount} />
        <Card title="Unknown Events" value={unknownCount} alert={unknownCount > 0} />
        <Card title="Avg Confidence" value={avgConfidence} />
      </div>

      <div className="bg-white rounded-2xl p-6 border border-soft-blue shadow-sm">
        <h3 className="text-lg font-bold text-deep-blue mb-4">Live System Status</h3>
        <p className="text-sm text-brand-secondary">
          Connected to local FastAPI backend. Automated telemetry logging & open-set unknown activity detection active.
        </p>
      </div>
    </div>
  );
}
