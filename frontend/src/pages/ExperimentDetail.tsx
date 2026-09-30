import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, FileJson, FileSpreadsheet, FileText, RotateCcw, Trash2, VideoOff } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { activityColor } from '../lib/activityColors';
import { confidencePct, formatBytes, formatDuration, parseServerDate } from '../lib/format';
import { MESSAGES } from '../lib/messages';
import { diagnoseVideoError } from '../lib/video';
import { useApiData } from '../hooks/useApiData';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { DataState, StatusNotice } from '../components/StatusNotice';
import ExperimentTimeline from '../components/ExperimentTimeline';
import WorkflowPanel from '../components/WorkflowPanel';
import ProgressBar from '../components/ProgressBar';
import VideoStatusBadge from '../components/VideoStatusBadge';
import type { VideoInfo } from '../types/api';

const POLL_MS = 1500;

const REVIEW_TEXT: Record<string, string> = {
  auto: 'accepted',
  pending: 'needs review',
  confirmed: 'confirmed',
  reclassified: 'reclassified',
  rejected: 'rejected',
};

function previewNote(exp: VideoInfo): string | null {
  if (exp.playable) return null;
  switch (exp.preview_status) {
    case 'pending':
      return `This video's format (${exp.codec ?? 'unknown codec'}) can't be played in the browser. A playable preview is created when processing finishes.`;
    case 'unavailable':
      return `This video's format (${exp.codec ?? 'unknown codec'}) can't be played in the browser, and ffmpeg is not installed to create a preview. Analysis is unaffected.`;
    case 'failed':
      return 'Creating a browser-playable preview failed (see backend logs). Analysis is unaffected.';
    default:
      return null;
  }
}

export default function ExperimentDetail() {
  const { id = '' } = useParams();
  const { online, status } = useSystemStatus();
  const modelReady = online && !!status?.model_ready;
  const { data, error, loading, reload } = useApiData(() => api.getExperiment(id), id);
  const exp = data?.experiment ?? null;
  const active = exp?.status === 'queued' || exp?.status === 'processing';

  useEffect(() => {
    if (!active) return;
    const t = setInterval(reload, POLL_MS);
    return () => clearInterval(t);
  }, [active, reload]);

  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [personFilter, setPersonFilter] = useState('');
  const [showRejected, setShowRejected] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const seek = useCallback((seconds: number, eventId?: string) => {
    const v = videoRef.current;
    if (v) {
      v.currentTime = seconds;
      v.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    setCurrentTime(seconds);
    setSelectedId(eventId ?? null);
  }, []);

  const navigate = useNavigate();
  const remove = async () => {
    if (!exp) return;
    const ok = window.confirm(
      `Delete "${exp.filename}" permanently?

Its video, activity events, review decisions and reports will be removed. This cannot be undone.`,
    );
    if (!ok) return;
    try {
      await api.deleteExperiment(id);
      navigate('/experiments');
    } catch (err) {
      setActionError(toApiError(err).message);
    }
  };

  const reprocess = async () => {
    setActionError(null);
    try {
      await api.processVideo(id);
      reload();
    } catch (err) {
      setActionError(toApiError(err).message);
    }
  };

  const events = (data?.events ?? []).filter(
    (e) => (showRejected || e.review_status !== 'rejected') && (!personFilter || e.person_id === personFilter),
  );
  const timelineEvents = (data?.events ?? []).filter((e) => e.review_status !== 'rejected');
  const nowIds = new Set(
    events
      .filter((e) => (e.start_seconds ?? 0) <= currentTime && currentTime < (e.end_seconds ?? 0))
      .map((e) => e.id),
  );
  const note = exp ? previewNote(exp) : null;

  return (
    <div className="space-y-6">
      <Link to="/experiments" className="inline-flex items-center gap-1 text-sm font-medium text-sky-blue hover:text-deep-blue">
        <ArrowLeft className="w-4 h-4" /> All experiments
      </Link>

      <DataState loading={loading} error={error} isEmpty={!data} onRetry={reload}>
        {data && exp && (
          <>
            {/* ── Header ─────────────────────────────────────────────────── */}
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold text-deep-blue truncate">{exp.filename}</h1>
                  <VideoStatusBadge status={exp.status} />
                </div>
                <p className="text-xs text-brand-secondary mt-1">
                  <span className="font-mono">{exp.video_id}</span>
                  {' · '}
                  {formatDuration(exp.duration_seconds)} video
                  {exp.file_size != null && ` · ${formatBytes(exp.file_size)}`}
                  {exp.created_at && ` · uploaded ${parseServerDate(exp.created_at).toLocaleString()}`}
                  {exp.processed_at && ` · processed ${parseServerDate(exp.processed_at).toLocaleString()}`}
                  {exp.processing_seconds != null && ` in ${exp.processing_seconds.toFixed(1)} s`}
                </p>
                {exp.engine && (
                  <p className="text-xs mt-1">
                    Activity engine: <span className="font-semibold text-amber-700">{exp.engine}</span>
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {exp.status === 'completed' && (
                  <>
                    <a href={api.reportUrl(id, 'pdf')} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-sky-blue hover:bg-[#2CA1D9] text-white text-xs font-bold">
                      <FileText className="w-3.5 h-3.5" /> PDF report
                    </a>
                    <a href={api.reportUrl(id, 'csv')} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-soft-blue bg-white text-deep-blue text-xs font-bold hover:bg-ice-blue">
                      <FileSpreadsheet className="w-3.5 h-3.5" /> CSV
                    </a>
                    <a href={api.reportUrl(id, 'json')} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-soft-blue bg-white text-deep-blue text-xs font-bold hover:bg-ice-blue">
                      <FileJson className="w-3.5 h-3.5" /> JSON
                    </a>
                  </>
                )}
                {!active && (
                  <button
                    onClick={reprocess}
                    disabled={!modelReady || !exp.file_exists}
                    title={!modelReady ? MESSAGES.modelMissing : undefined}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-soft-blue bg-white text-brand-success text-xs font-bold hover:bg-ice-blue disabled:text-brand-muted disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="w-3.5 h-3.5" /> {exp.status === 'uploaded' ? 'Process' : 'Re-process'}
                  </button>
                )}
                {!active && (
                  <button
                    onClick={remove}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-red-200 bg-white text-brand-alert text-xs font-bold hover:bg-red-50"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Delete
                  </button>
                )}
              </div>
            </div>

            {actionError && <StatusNotice tone="error">{actionError}</StatusNotice>}
            {active && (
              <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-5">
                <ProgressBar
                  value={exp.progress}
                  indeterminate={exp.status === 'queued'}
                  label={exp.status === 'queued' ? 'Queued…' : exp.message || 'Detecting, tracking and classifying people…'}
                />
              </div>
            )}
            {exp.status === 'failed' && (
              <StatusNotice tone="error" title="Video processing failed">
                {exp.message || MESSAGES.processingFailed}
              </StatusNotice>
            )}
            {exp.status === 'completed' && exp.message && (
              <StatusNotice tone={exp.events_count ? 'info' : 'warning'}>{exp.message}</StatusNotice>
            )}

            {/* ── Video + workflow ───────────────────────────────────────── */}
            <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
              <div className="xl:col-span-3 space-y-4">
                <div className="bg-black rounded-2xl overflow-hidden aspect-video relative">
                  {videoError ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/60 text-xs text-center px-6">
                      <VideoOff className="w-10 h-10 text-white/30" />
                      {videoError}
                    </div>
                  ) : (
                    <video
                      ref={videoRef}
                      src={api.videoUrl(id, exp.preview_status)}
                      className="w-full h-full object-contain"
                      controls
                      preload="metadata"
                      onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                      onSeeked={(e) => setCurrentTime(e.currentTarget.currentTime)}
                      onError={() => diagnoseVideoError(api.videoUrl(id, exp.preview_status)).then(setVideoError)}
                    />
                  )}
                </div>
                {note && <StatusNotice tone="warning">{note}</StatusNotice>}

                <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-deep-blue">Activity timeline</h3>
                    <span className="text-xs font-mono text-brand-secondary">{formatDuration(currentTime)}</span>
                  </div>
                  {data.people.length === 0 ? (
                    <p className="text-sm text-brand-secondary text-center py-4">{MESSAGES.noData}</p>
                  ) : (
                    <ExperimentTimeline
                      people={data.people}
                      events={timelineEvents}
                      duration={exp.duration_seconds ?? 0}
                      currentTime={currentTime}
                      selectedId={selectedId}
                      onSeek={seek}
                    />
                  )}
                </div>
              </div>

              <div className="xl:col-span-2">
                <WorkflowPanel experimentId={id} people={data.people} onSeek={(s) => seek(s)} />
              </div>
            </div>

            {/* ── Event table ────────────────────────────────────────────── */}
            <div className="bg-white rounded-2xl border border-soft-blue shadow-sm overflow-hidden">
              <div className="p-6 border-b border-soft-blue flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-lg font-bold text-deep-blue">Activity events ({events.length})</h3>
                <div className="flex items-center gap-3 text-xs">
                  <select
                    value={personFilter}
                    onChange={(e) => setPersonFilter(e.target.value)}
                    className="bg-ice-blue border border-soft-blue rounded-lg px-2 py-1 text-deep-blue"
                    aria-label="Filter by person"
                  >
                    <option value="">All people</option>
                    {data.people.map((p) => (
                      <option key={p.person_id} value={p.person_id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1.5 text-brand-secondary">
                    <input type="checkbox" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} />
                    show rejected
                  </label>
                  <Link to="/review" className="font-bold text-sky-blue underline">Review Queue</Link>
                </div>
              </div>
              {events.length === 0 ? (
                <p className="p-6 text-center text-sm text-brand-secondary">{MESSAGES.noData}</p>
              ) : (
                <div className="overflow-x-auto max-h-[28rem] overflow-y-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-ice-blue/60 text-brand-secondary text-xs sticky top-0">
                      <tr>
                        <th className="px-4 py-3 font-medium">Person</th>
                        <th className="px-4 py-3 font-medium">Activity</th>
                        <th className="px-4 py-3 font-medium">Start</th>
                        <th className="px-4 py-3 font-medium">End</th>
                        <th className="px-4 py-3 font-medium text-right">Duration</th>
                        <th className="px-4 py-3 font-medium text-right">Confidence</th>
                        <th className="px-4 py-3 font-medium">Review</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-soft-blue">
                      {events.map((e) => (
                        <tr
                          key={e.id}
                          onClick={() => seek(e.start_seconds ?? 0, e.id)}
                          className={`cursor-pointer ${
                            selectedId === e.id ? 'bg-sky-blue/15' : nowIds.has(e.id) ? 'bg-ice-blue' : 'hover:bg-ice-blue/50'
                          } ${e.review_status === 'rejected' ? 'opacity-50' : ''}`}
                        >
                          <td className="px-4 py-2.5 font-medium text-brand-primary">{e.person}</td>
                          <td className="px-4 py-2.5">
                            <span className="inline-flex items-center gap-2 text-brand-primary">
                              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(e.activity_type) }} />
                              {e.activity_type}
                              {e.original_activity && (
                                <span className="text-xs text-brand-muted">(model: {e.original_activity})</span>
                              )}
                              {e.note && e.activity_type === 'Unknown' && (
                                <span className="text-xs text-brand-muted">({e.note})</span>
                              )}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs text-brand-secondary">{e.start_time}</td>
                          <td className="px-4 py-2.5 font-mono text-xs text-brand-secondary">{e.end_time}</td>
                          <td className="px-4 py-2.5 text-right text-brand-secondary">{e.duration.toFixed(1)} s</td>
                          <td className="px-4 py-2.5 text-right text-brand-secondary">{confidencePct(e.confidence)}%</td>
                          <td className={`px-4 py-2.5 text-xs ${e.review_status === 'pending' ? 'text-brand-warning font-semibold' : 'text-brand-muted'}`}>
                            {REVIEW_TEXT[e.review_status] ?? e.review_status}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}
