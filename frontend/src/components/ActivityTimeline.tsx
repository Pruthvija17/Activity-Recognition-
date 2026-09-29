import { useEffect, useState } from 'react';

interface ActivityEvent {
  id: string;
  person_id: string;
  activity_type: string;
  start_time: string;
  end_time: string;
  duration: number;
  confidence: number;
  status: string;
}

export default function ActivityTimeline() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const res = await fetch('http://localhost:8000/events/');
        if (res.ok) {
          const data = await res.json();
          setEvents(data);
        }
      } catch (err) {
        console.error('Error fetching timeline events:', err);
      }
    };
    fetchEvents();
  }, []);

  // Group events by person_id
  const personEventsMap: Record<string, ActivityEvent[]> = {};
  events.forEach((evt) => {
    if (!personEventsMap[evt.person_id]) {
      personEventsMap[evt.person_id] = [];
    }
    personEventsMap[evt.person_id].push(evt);
  });

  const personIds = Object.keys(personEventsMap);

  return (
    <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm">
      <h3 className="text-lg font-bold text-deep-blue mb-4">Activity Timeline</h3>
      
      <div className="space-y-6">
        {personIds.length === 0 ? (
          <div className="p-4 text-center text-xs text-brand-secondary">
            No activity events recorded for timeline view yet.
          </div>
        ) : (
          personIds.map((personId) => (
            <div key={personId}>
              <div className="text-sm font-medium text-brand-secondary mb-2">{personId}</div>
              <div className="relative h-12 bg-ice-blue rounded-lg overflow-hidden flex">
                {personEventsMap[personId].map((evt) => {
                  const isUnknown = evt.activity_type === 'Unknown';
                  return (
                    <div 
                      key={evt.id}
                      className={`h-full border-r border-white/40 flex items-center justify-center text-xs font-medium px-2 ${
                        isUnknown ? 'bg-brand-alert/20 text-brand-alert animate-pulse' : 'bg-sky-blue/20 text-sky-blue'
                      }`}
                      style={{ flex: Math.max(1, evt.duration) }}
                    >
                      {evt.activity_type} {isUnknown && '⚠'} ({evt.start_time}-{evt.end_time})
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
        
        {/* Time axis */}
        <div className="flex justify-between text-xs text-brand-muted px-2 pt-2 border-t border-soft-blue mt-4">
          <span>00:00</span>
          <span>01:15</span>
          <span>02:30</span>
          <span>03:45</span>
          <span>05:00+</span>
        </div>
      </div>
    </div>
  );
}
