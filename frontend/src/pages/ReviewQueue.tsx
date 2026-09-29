import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Play, CheckCircle2, AlertCircle, VideoOff } from 'lucide-react';

const ACTIVITIES = [
  'Standing',
  'Sitting',
  'Walking',
  'Reaching',
  'Picking up an object',
  'Placing an object',
  'Handling experimental equipment',
];

interface EventItem {
  id: string;
  person_id: string;
  activity_type: string;
  start_time: string;
  end_time: string;
  start_seconds: number | null;
  end_seconds: number | null;
  confidence: number;
  status: string;
  video_id: string | null;
  experiment_id: string;
}

export default function ReviewQueue() {
  const [queue, setQueue] = useState<EventItem[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<string>('');
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError: boolean } | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoLoading, setVideoLoading] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // ── Fetch pending review events ──────────────────────────────────────────
  const fetchEvents = async () => {
    try {
      const res = await fetch('http://localhost:8000/events/');
      if (res.ok) {
        const data: EventItem[] = await res.json();
        const pending = data.filter(
          (e) => e.status === 'Review' || e.activity_type === 'Unknown'
        );
        setQueue(pending);
        if (pending.length > 0) {
          setSelectedEvent(pending[0]);
        } else {
          setSelectedEvent(null);
        }
      } else {
        setQueue([]);
        setSelectedEvent(null);
      }
    } catch {
      setQueue([]);
      setSelectedEvent(null);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  // ── Video seek when selected event changes ───────────────────────────────
  useEffect(() => {
    setVideoError(null);
    setVideoLoading(false);
    if (!selectedEvent) return;

    const video = videoRef.current;
    if (!video) return;

    const videoId = selectedEvent.video_id || selectedEvent.experiment_id;
    const seekTo = selectedEvent.start_seconds ?? 0;

    setVideoLoading(true);
    video.src = `http://localhost:8000/api/videos/${videoId}`;
    video.load();

    const onLoaded = () => {
      setVideoLoading(false);
      video.currentTime = seekTo;
      video.pause();
    };
    const onError = () => {
      setVideoLoading(false);
      setVideoError('Video file is not available. The source file may have been moved or deleted.');
    };

    video.addEventListener('loadedmetadata', onLoaded);
    video.addEventListener('error', onError);
    return () => {
      video.removeEventListener('loadedmetadata', onLoaded);
      video.removeEventListener('error', onError);
    };
  }, [selectedEvent]);

  // ── Play just the event clip ─────────────────────────────────────────────
  const handlePlayClip = () => {
    const video = videoRef.current;
    if (!video || !selectedEvent) return;
    const endAt = selectedEvent.end_seconds ?? (selectedEvent.start_seconds ?? 0) + 5;
    video.currentTime = selectedEvent.start_seconds ?? 0;

    const stopAtEnd = () => {
      if (video.currentTime >= endAt) {
        video.pause();
        video.removeEventListener('timeupdate', stopAtEnd);
      }
    };
    video.addEventListener('timeupdate', stopAtEnd);
    video.play().catch(() => {
      setVideoError('Playback failed. Check browser autoplay permissions.');
    });
  };

  // ── Confirm classification via backend ───────────────────────────────────
  const handleConfirm = async () => {
    if (!selectedEvent || !selectedActivity) return;

    try {
      const res = await fetch(
        `http://localhost:8000/events/${selectedEvent.id}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ activity_type: selectedActivity }),
        }
      );

      if (res.ok) {
        setStatusMessage({
          text: `Event "${selectedEvent.id.slice(0, 8)}…" reclassified as "${selectedActivity}".`,
          isError: false,
        });
        setSelectedActivity('');
        await fetchEvents();
      } else {
        const err = await res.json().catch(() => ({}));
        setStatusMessage({
          text: err.detail || 'Failed to update classification.',
          isError: true,
        });
      }
    } catch {
      setStatusMessage({ text: 'Backend offline — cannot update classification.', isError: true });
    }

    // Auto-clear status after 5 s
    setTimeout(() => setStatusMessage(null), 5000);
  };

  const confPct = (c: number) => Math.round(c > 1 ? c : c * 100);

  return (
    <div className="space-y-6">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-deep-blue">Review Queue</h1>
        <div className="flex items-center gap-2 text-sm font-medium text-brand-secondary bg-white px-4 py-2 rounded-lg border border-soft-blue">
          <span className="w-2 h-2 rounded-full bg-brand-warning"></span>
          {queue.length} Events Pending Review
        </div>
      </div>

      {/* ── Status toast ──────────────────────────────────────────────────── */}
      {statusMessage && (
        <div
          className={`p-4 rounded-xl border flex items-center gap-2 text-sm font-medium ${
            statusMessage.isError
              ? 'bg-red-50 text-brand-alert border-red-200'
              : 'bg-green-50 text-brand-success border-green-100'
          }`}
        >
          {statusMessage.isError ? (
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
          ) : (
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          )}
          {statusMessage.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* ── Left: Event list ──────────────────────────────────────────────── */}
        <div className="space-y-4">
          <h3 className="text-lg font-bold text-deep-blue">Pending Events</h3>

          {queue.length === 0 ? (
            <div className="bg-white rounded-xl p-6 border border-soft-blue text-center text-sm text-brand-secondary">
              No events pending review. All activity detections are confirmed.
            </div>
          ) : (
            queue.map((item) => {
              const isSelected = selectedEvent?.id === item.id;
              return (
                <div
                  key={item.id}
                  onClick={() => {
                    setSelectedEvent(item);
                    setSelectedActivity('');
                    setStatusMessage(null);
                  }}
                  className={`bg-white rounded-xl p-4 border shadow-sm cursor-pointer transition-all ${
                    isSelected
                      ? 'border-sky-blue ring-2 ring-sky-blue/30'
                      : 'border-soft-blue hover:border-sky-blue/50'
                  }`}
                >
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2 text-brand-alert font-bold text-sm">
                      <AlertTriangle className="w-4 h-4" />
                      {item.activity_type.toUpperCase()} ACTIVITY
                    </div>
                    <div className="text-xs font-medium bg-ice-blue text-brand-secondary px-2 py-1 rounded">
                      {item.id.slice(0, 8)}…
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                    <div>
                      <div className="text-brand-muted text-xs mb-1">Person ID</div>
                      <div className="font-medium text-brand-primary truncate">{item.person_id}</div>
                    </div>
                    <div>
                      <div className="text-brand-muted text-xs mb-1">Confidence</div>
                      <div className="font-medium text-brand-primary">{confPct(item.confidence)}%</div>
                    </div>
                    <div className="col-span-2">
                      <div className="text-brand-muted text-xs mb-1">Timestamp Window</div>
                      <div className="font-medium text-brand-primary font-mono text-xs">
                        {item.start_time} – {item.end_time}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedEvent(item);
                      setSelectedActivity('');
                      setTimeout(handlePlayClip, 300);
                    }}
                    className="w-full flex items-center justify-center gap-2 bg-ice-blue hover:bg-soft-blue text-deep-blue font-medium py-2 rounded-lg transition-colors text-xs"
                  >
                    <Play className="w-3.5 h-3.5" />
                    Inspect Video Clip
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* ── Right: Video + classifier ─────────────────────────────────────── */}
        <div>
          {selectedEvent ? (
            <div className="bg-white rounded-2xl border border-soft-blue shadow-sm overflow-hidden sticky top-8">
              {/* Video Player */}
              <div className="aspect-video bg-black relative flex items-center justify-center">
                {videoLoading && !videoError && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/80 z-20">
                    <div className="text-white/60 text-xs font-mono">Loading video…</div>
                  </div>
                )}

                {videoError ? (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950 z-10">
                    <VideoOff className="w-10 h-10 text-white/30" />
                    <p className="text-white/50 text-xs text-center max-w-xs px-4">{videoError}</p>
                  </div>
                ) : (
                  <video
                    ref={videoRef}
                    className="w-full h-full object-contain"
                    controls
                    preload="metadata"
                    onError={() => {
                      setVideoLoading(false);
                      setVideoError('Video file is not available. The source file may have been moved or deleted.');
                    }}
                  />
                )}

                {/* Event overlay label */}
                <div className="absolute top-3 left-3 z-20 bg-brand-warning/90 text-white text-[10px] font-bold px-2 py-1 rounded">
                  {selectedEvent.person_id} ·{' '}
                  {selectedEvent.start_time}–{selectedEvent.end_time}
                </div>

                {!videoError && !videoLoading && (
                  <button
                    onClick={handlePlayClip}
                    className="absolute bottom-4 right-4 z-20 flex items-center gap-1.5 bg-sky-blue hover:bg-[#2CA1D9] text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow transition-colors"
                  >
                    <Play className="w-3.5 h-3.5" />
                    Play Clip
                  </button>
                )}

                <div className="absolute inset-0 border-4 border-brand-warning/50 z-10 pointer-events-none" />
              </div>

              {/* Classification Panel */}
              <div className="p-6">
                <h3 className="text-lg font-bold text-deep-blue mb-1">
                  Classify Event ({selectedEvent.id.slice(0, 8)}…)
                </h3>
                <p className="text-xs text-brand-secondary mb-4">
                  Select the correct activity observed in the video snippet above.
                </p>

                <div className="grid grid-cols-2 gap-2.5 mb-6">
                  {ACTIVITIES.map((activity) => (
                    <button
                      key={activity}
                      onClick={() => setSelectedActivity(activity)}
                      className={`px-3 py-2 text-xs font-medium border rounded-lg transition-colors text-left ${
                        selectedActivity === activity
                          ? 'border-sky-blue bg-sky-blue/10 text-deep-blue font-bold'
                          : 'border-soft-blue text-brand-primary hover:border-sky-blue hover:bg-ice-blue'
                      }`}
                    >
                      {activity}
                    </button>
                  ))}

                  <button
                    onClick={() => setSelectedActivity('Unknown')}
                    className={`px-3 py-2 text-xs font-medium border rounded-lg transition-colors text-left ${
                      selectedActivity === 'Unknown'
                        ? 'border-brand-alert bg-red-50 text-brand-alert font-bold'
                        : 'border-brand-alert/30 bg-red-50/30 text-brand-alert hover:bg-red-50'
                    }`}
                  >
                    Keep Unknown / Unexpected
                  </button>
                </div>

                <button
                  onClick={handleConfirm}
                  disabled={!selectedActivity}
                  className={`w-full py-3 text-sm font-bold text-white rounded-lg transition-colors shadow-sm ${
                    selectedActivity ? 'bg-sky-blue hover:bg-[#2CA1D9]' : 'bg-gray-300 cursor-not-allowed'
                  }`}
                >
                  Confirm Classification
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-12 text-center text-sm text-brand-secondary">
              Select an event from the left panel to review and classify it.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
