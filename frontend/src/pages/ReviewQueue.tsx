import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Play, CheckCircle2, AlertCircle, VideoOff, XCircle, Tag } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { confidencePct, formatDuration } from '../lib/format';
import { ACTIVITIES, UNKNOWN, activityColor } from '../lib/activityColors';
import { diagnoseVideoError } from '../lib/video';
import { useApiData } from '../hooks/useApiData';
import { DataState } from '../components/StatusNotice';
import type { ReviewActionName, ReviewEvent } from '../types/api';

const CHOICES = [...ACTIVITIES, UNKNOWN];
type Tab = 'pending' | 'reviewed';

const decisionText: Record<string, string> = {
  confirmed: 'Confirmed',
  rejected: 'Rejected (false detection)',
  reclassified: 'Reclassified',
};

function ActivityLabel({ name }: { name: string }) {
  const unknown = name === UNKNOWN;
  return (
    <span className={`inline-flex items-center gap-1.5 font-bold ${unknown ? 'text-brand-alert' : 'text-deep-blue'}`}>
      {unknown ? <AlertTriangle className="w-4 h-4" /> : <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(name) }} />}
      {unknown ? 'Unknown / Unexpected' : name}
    </span>
  );
}

export default function ReviewQueue() {
  const [tab, setTab] = useState<Tab>('pending');
  const [experimentId, setExperimentId] = useState('');
  const videos = useApiData(() => api.listVideos());
  const completed = (videos.data ?? []).filter((v) => v.status === 'completed');

  const { data, error, loading, reload } = useApiData(
    () => api.getReviewEvents({ experimentId: experimentId || undefined, status: tab }),
    `${tab}|${experimentId}`,
  );
  const queue = useMemo(() => data ?? [], [data]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedIndex = Math.max(0, queue.findIndex((e) => e.id === selectedId));
  const selectedEvent: ReviewEvent | null = queue[selectedIndex] ?? null;
  const [choice, setChoice] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError: boolean } | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoLoading, setVideoLoading] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Reset per-event UI state when the selection changes (during render, not in an effect).
  const [shownEventId, setShownEventId] = useState<string | null>(null);
  if ((selectedEvent?.id ?? null) !== shownEventId) {
    setShownEventId(selectedEvent?.id ?? null);
    setChoice('');
    setVideoError(null);
    setVideoLoading(!!selectedEvent);
  }

  // ── Load the event's video and seek to its start ────────────────────────
  useEffect(() => {
    const video = videoRef.current;
    if (!selectedEvent || !video) return;
    const src = api.videoUrl(selectedEvent.video_id);
    const seekTo = selectedEvent.start_seconds ?? 0;
    const onLoaded = () => {
      setVideoLoading(false);
      video.currentTime = seekTo;
      video.pause();
    };
    const onError = () => {
      setVideoLoading(false);
      diagnoseVideoError(src).then(setVideoError);
    };
    video.addEventListener('loadedmetadata', onLoaded);
    video.addEventListener('error', onError);
    if (video.src !== src) {
      video.src = src;
      video.load();
    } else if (video.readyState >= 1) {
      onLoaded();
    }
    return () => {
      video.removeEventListener('loadedmetadata', onLoaded);
      video.removeEventListener('error', onError);
    };
  }, [selectedEvent]);

  const playClip = useCallback(() => {
    const video = videoRef.current;
    if (!video || !selectedEvent) return;
    const start = selectedEvent.start_seconds ?? 0;
    const end = selectedEvent.end_seconds ?? start + 5;
    video.currentTime = start;
    const stopAtEnd = () => {
      if (video.currentTime >= end) {
        video.pause();
        video.removeEventListener('timeupdate', stopAtEnd);
      }
    };
    video.addEventListener('timeupdate', stopAtEnd);
    video.play().catch(() => setVideoError('Playback was blocked by the browser. Press play on the video.'));
  }, [selectedEvent]);

  // ── Decisions ────────────────────────────────────────────────────────────
  const decide = useCallback(
    async (action: ReviewActionName, activity?: string) => {
      if (!selectedEvent || busy) return;
      setBusy(true);
      setStatusMessage(null);
      const next = queue[selectedIndex + 1] ?? queue[selectedIndex - 1] ?? null;
      try {
        const updated = await api.reviewEvent(selectedEvent.id, action, activity);
        const what =
          action === 'reject'
            ? 'rejected as a false detection'
            : updated.review_status === 'reclassified'
              ? `reclassified as "${updated.activity_type}"`
              : `confirmed as "${updated.activity_type}"`;
        setStatusMessage({ text: `${updated.person} ${updated.start_time}–${updated.end_time} ${what}.`, isError: false });
        if (tab === 'pending') setSelectedId(next?.id ?? null);
        reload();
      } catch (err) {
        setStatusMessage({ text: toApiError(err).message, isError: true });
      } finally {
        setBusy(false);
      }
    },
    [busy, queue, reload, selectedEvent, selectedIndex, tab, setBusy, setSelectedId, setStatusMessage],
  );

  const canReclassify = !!selectedEvent && !!choice && choice !== selectedEvent.activity_type;

  // ── Keyboard shortcuts ──────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
      // A focused button already handles Enter/Space itself; don't fire a second action.
      if (target.tagName === 'BUTTON' && (e.key === 'Enter' || e.key === ' ')) return;
      const n = Number(e.key);
      if (n >= 1 && n <= CHOICES.length) {
        setChoice(CHOICES[n - 1]);
      } else if (e.key === 'c' || e.key === 'C') {
        decide('confirm');
      } else if (e.key === 'x' || e.key === 'X') {
        decide('reject');
      } else if (e.key === 'Enter' && canReclassify) {
        decide('reclassify', choice);
      } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const i = selectedIndex + (e.key === 'ArrowDown' ? 1 : -1);
        if (queue[i]) {
          e.preventDefault();
          setSelectedId(queue[i].id);
        }
      } else if (e.key === ' ' && selectedEvent) {
        e.preventDefault();
        playClip();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canReclassify, choice, decide, playClip, queue, selectedEvent, selectedIndex]);

  return (
    <div className="space-y-6">
      {/* ── Header & filters ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-deep-blue">Review Queue</h1>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={experimentId}
            onChange={(e) => {
              setExperimentId(e.target.value);
              setSelectedId(null);
            }}
            className="bg-white border border-soft-blue rounded-lg px-3 py-2 text-sm text-deep-blue"
            aria-label="Filter by experiment"
          >
            <option value="">All experiments</option>
            {completed.map((v) => (
              <option key={v.video_id} value={v.video_id}>
                {v.filename} ({v.video_id})
              </option>
            ))}
          </select>
          <div className="flex bg-white border border-soft-blue rounded-lg p-1 text-sm font-medium">
            {(['pending', 'reviewed'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => {
                  setTab(t);
                  setSelectedId(null);
                  setStatusMessage(null);
                }}
                className={`px-3 py-1 rounded-md capitalize ${tab === t ? 'bg-sky-blue text-white' : 'text-brand-secondary hover:bg-ice-blue'}`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {statusMessage && (
        <div
          className={`p-4 rounded-xl border flex items-center gap-2 text-sm font-medium ${
            statusMessage.isError ? 'bg-red-50 text-brand-alert border-red-200' : 'bg-green-50 text-brand-success border-green-100'
          }`}
        >
          {statusMessage.isError ? <AlertCircle className="w-5 h-5 flex-shrink-0" /> : <CheckCircle2 className="w-5 h-5 flex-shrink-0" />}
          {statusMessage.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        {/* ── Left: event list ─────────────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-3">
          <h3 className="text-sm font-bold text-brand-secondary">
            {queue.length} {tab === 'pending' ? 'events pending review' : 'reviewed events'}
          </h3>
          <DataState
            loading={loading}
            error={error}
            isEmpty={queue.length === 0}
            onRetry={reload}
            emptyMessage={
              tab === 'pending'
                ? 'No events pending review. Unknown and low-confidence events appear here after processing.'
                : 'No reviewed events yet.'
            }
          >
            <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
              {queue.map((item) => {
                const isSelected = selectedEvent?.id === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setSelectedId(item.id);
                      setStatusMessage(null);
                    }}
                    className={`w-full text-left bg-white rounded-xl p-4 border shadow-sm transition-all ${
                      isSelected ? 'border-sky-blue ring-2 ring-sky-blue/30' : 'border-soft-blue hover:border-sky-blue/50'
                    }`}
                  >
                    <div className="flex justify-between items-start gap-2 mb-2 text-sm">
                      <ActivityLabel name={item.activity_type} />
                      <span className="text-xs font-mono text-brand-secondary whitespace-nowrap">
                        {confidencePct(item.confidence)}%
                      </span>
                    </div>
                    {item.note && <div className="text-xs text-brand-alert/80 mb-1">Why: {item.note}</div>}
                    <div className="text-xs text-brand-secondary flex flex-wrap gap-x-3 gap-y-1">
                      <span className="font-semibold text-brand-primary">{item.person}</span>
                      <span className="font-mono">
                        {item.start_time}–{item.end_time}
                      </span>
                      <span className="truncate max-w-40">{item.video}</span>
                    </div>
                    {tab === 'reviewed' && (
                      <div className="mt-2 text-xs text-brand-muted">
                        {decisionText[item.review_status] ?? item.review_status}
                        {item.original_activity && ` · model said: ${item.original_activity}`}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </DataState>
        </div>

        {/* ── Right: video + decision ──────────────────────────────────────── */}
        <div className="lg:col-span-3">
          {selectedEvent ? (
            <div className="bg-white rounded-2xl border border-soft-blue shadow-sm overflow-hidden sticky top-0">
              <div className="aspect-video bg-black relative flex items-center justify-center">
                {videoLoading && !videoError && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/80 z-20 text-white/60 text-xs font-mono">
                    Loading video…
                  </div>
                )}
                {videoError && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950 z-10">
                    <VideoOff className="w-10 h-10 text-white/30" />
                    <p className="text-white/60 text-xs text-center max-w-sm px-4">{videoError}</p>
                  </div>
                )}
                <video ref={videoRef} className="w-full h-full object-contain" controls preload="metadata" />
                <div className="absolute top-3 left-3 z-20 bg-black/70 text-white text-[11px] font-bold px-2 py-1 rounded">
                  {selectedEvent.person} · {selectedEvent.start_time}–{selectedEvent.end_time} (
                  {formatDuration(selectedEvent.duration)})
                </div>
                {!videoError && !videoLoading && (
                  <button
                    onClick={playClip}
                    className="absolute bottom-14 right-4 z-20 flex items-center gap-1.5 bg-sky-blue hover:bg-[#2CA1D9] text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow"
                  >
                    <Play className="w-3.5 h-3.5" /> Play event clip
                  </button>
                )}
              </div>

              <div className="p-6 space-y-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <div className="text-xs text-brand-muted mb-1">Model prediction</div>
                    <div className="text-lg">
                      <ActivityLabel name={selectedEvent.original_activity ?? selectedEvent.activity_type} />
                    </div>
                    {selectedEvent.note && (
                      <div className="text-xs text-brand-secondary mt-1">Reason: {selectedEvent.note}</div>
                    )}
                  </div>
                  <div className="text-right text-sm">
                    <div className="text-xs text-brand-muted">Confidence</div>
                    <div className="font-bold text-brand-primary">{confidencePct(selectedEvent.confidence)}%</div>
                  </div>
                </div>
                {selectedEvent.review_status !== 'pending' && (
                  <p className="text-xs text-brand-secondary bg-ice-blue rounded-lg p-2">
                    Current decision: <strong>{decisionText[selectedEvent.review_status] ?? selectedEvent.review_status}</strong>
                    {selectedEvent.review_status === 'reclassified' && ` → ${selectedEvent.activity_type}`}. You can change it.
                  </p>
                )}

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => decide('confirm')}
                    disabled={busy}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold text-white bg-brand-success hover:bg-green-600 disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-4 h-4" /> Confirm <kbd className="text-[10px] opacity-80">C</kbd>
                  </button>
                  <button
                    onClick={() => decide('reject')}
                    disabled={busy}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold text-brand-alert border border-red-200 bg-red-50 hover:bg-red-100 disabled:opacity-50"
                    title="Not a real activity (e.g. a false detection)"
                  >
                    <XCircle className="w-4 h-4" /> Reject <kbd className="text-[10px] opacity-80">X</kbd>
                  </button>
                </div>

                <div>
                  <div className="text-xs font-bold text-brand-secondary mb-2 flex items-center gap-1">
                    <Tag className="w-3.5 h-3.5" /> Or reclassify as
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {CHOICES.map((activity, i) => (
                      <button
                        key={activity}
                        onClick={() => setChoice(activity)}
                        className={`flex items-center gap-2 px-3 py-2 text-xs font-medium border rounded-lg text-left transition-colors ${
                          choice === activity
                            ? 'border-sky-blue bg-sky-blue/10 text-deep-blue font-bold'
                            : 'border-soft-blue text-brand-primary hover:border-sky-blue hover:bg-ice-blue'
                        }`}
                      >
                        <kbd className="text-[10px] text-brand-muted w-3">{i + 1}</kbd>
                        <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: activityColor(activity) }} />
                        {activity === UNKNOWN ? 'Unknown / Unexpected' : activity}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={() => decide('reclassify', choice)}
                    disabled={!canReclassify || busy}
                    className={`mt-3 w-full py-2.5 text-sm font-bold text-white rounded-lg transition-colors ${
                      canReclassify && !busy ? 'bg-sky-blue hover:bg-[#2CA1D9]' : 'bg-gray-300 cursor-not-allowed'
                    }`}
                  >
                    {canReclassify ? `Reclassify as "${choice}"` : 'Select a different activity to reclassify'}{' '}
                    <kbd className="text-[10px] opacity-80">Enter</kbd>
                  </button>
                </div>
                <p className="text-[11px] text-brand-muted">
                  Keys: 1–8 choose · C confirm · X reject · Enter reclassify · ↑/↓ next/previous · Space play clip
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-12 text-center text-sm text-brand-secondary">
              {queue.length ? 'Select an event to review it.' : 'Nothing to review.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
