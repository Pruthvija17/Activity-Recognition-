import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { UploadCloud, FileVideo, CheckCircle2, AlertCircle, Loader2, X, Play, RotateCcw, Eye } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { MESSAGES } from '../lib/messages';
import { confidencePct, formatBytes, formatDuration, parseServerDate } from '../lib/format';
import { useApiData } from '../hooks/useApiData';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { DataState, StatusNotice } from '../components/StatusNotice';
import ProgressBar from '../components/ProgressBar';
import VideoStatusBadge from '../components/VideoStatusBadge';
import type { ActivityEvent, VideoInfo } from '../types/api';

const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.webm'];
const MAX_SIZE_MB = 500;
const POLL_MS = 1500;
const STEPS = ['Upload', 'Queued', 'Processing', 'Completed'] as const;

const isActive = (v: VideoInfo | null) => !!v && (v.status === 'queued' || v.status === 'processing');

function validateFile(file: File): string | null {
  const ext = '.' + (file.name.split('.').pop() ?? '').toLowerCase();
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `Invalid format '${ext}'. Only MP4, AVI, MOV and WebM files are allowed.`;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `File size (${formatBytes(file.size)}) exceeds the ${MAX_SIZE_MB} MB limit.`;
  }
  if (file.size === 0) return 'The selected file is empty.';
  return null;
}

/** Index of the active step for the pipeline stepper. */
function stepIndex(uploading: boolean, video: VideoInfo | null): number {
  if (uploading || !video) return 0;
  switch (video.status) {
    case 'uploaded':
    case 'queued':
      return 1;
    case 'processing':
    case 'live':
      return 2;
    case 'completed':
      return 3;
    case 'failed':
      return 2;
  }
}

function Stepper({ active, failed }: { active: number; failed: boolean }) {
  return (
    <ol className="flex items-center gap-2 text-xs font-medium">
      {STEPS.map((label, i) => {
        const done = i < active || (i === active && active === STEPS.length - 1);
        const current = i === active && !done;
        const color = failed && current
          ? 'bg-brand-alert text-white'
          : done
            ? 'bg-brand-success text-white'
            : current
              ? 'bg-sky-blue text-white'
              : 'bg-soft-blue text-brand-muted';
        return (
          <li key={label} className="flex items-center gap-2">
            <span className={`w-6 h-6 rounded-full flex items-center justify-center ${color}`}>
              {done ? '✓' : failed && current ? '!' : i + 1}
            </span>
            <span className={current || done ? 'text-brand-primary' : 'text-brand-muted'}>{label}</span>
            {i < STEPS.length - 1 && <span className="w-6 h-px bg-soft-blue" />}
          </li>
        );
      })}
    </ol>
  );
}

function ResultsPanel({ video, events }: { video: VideoInfo; events: ActivityEvent[] }) {
  const people = new Set(events.map((e) => e.person_id)).size;
  const review = events.filter((e) => e.status === 'Review').length;
  return (
    <div className="border border-soft-blue rounded-xl p-4 bg-white space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
        {[
          ['Activity events', String(events.length)],
          ['People tracked', String(people)],
          ['Needs review', String(review)],
          ['Video length', formatDuration(video.duration_seconds)],
          ['Processing time', video.processing_seconds != null ? `${video.processing_seconds.toFixed(1)} s` : '—'],
        ].map(([label, value]) => (
          <div key={label} className="bg-ice-blue/60 rounded-lg p-3">
            <div className="text-xs text-brand-muted">{label}</div>
            <div className="font-bold text-deep-blue text-lg">{value}</div>
          </div>
        ))}
      </div>
      {video.engine && (
        <p className="text-xs text-brand-secondary">
          Activity engine: <span className="font-semibold text-amber-700">{video.engine}</span>
        </p>
      )}
      {events.length > 0 && (
        <>
          <div className="divide-y divide-soft-blue/60 max-h-80 overflow-y-auto">
            {events.map((evt) => (
              <div key={evt.id} className="py-2 grid grid-cols-5 gap-2 items-center text-sm">
                <span className="font-medium text-brand-primary truncate">{evt.person_id.split('_').slice(-2).join(' ')}</span>
                <span
                  className={`px-2 py-0.5 rounded font-semibold text-xs truncate ${
                    evt.activity_type === 'Unknown' ? 'bg-red-50 text-brand-alert' : 'bg-ice-blue text-sky-700'
                  }`}
                >
                  {evt.activity_type}
                </span>
                <span className="text-xs text-brand-secondary font-mono">
                  {evt.start_time} – {evt.end_time}
                </span>
                <span className="text-xs font-mono text-brand-secondary">{confidencePct(evt.confidence)}% conf</span>
                <span className={`text-xs font-medium ${evt.status === 'Review' ? 'text-brand-warning' : 'text-brand-success'}`}>
                  {evt.status}
                </span>
              </div>
            ))}
          </div>
          <div className="flex gap-3 text-sm">
            <Link to={`/experiments/${video.video_id}`} className="text-sky-blue font-bold underline">Open experiment details</Link>
            <Link to="/review" className="text-sky-blue font-bold underline">Open Review Queue</Link>
            <Link to="/analytics" className="text-sky-blue font-bold underline">View Analytics</Link>
          </div>
        </>
      )}
    </div>
  );
}

export default function Experiments() {
  const { online, status } = useSystemStatus();
  const modelReady = online && !!status?.model_ready;

  const videos = useApiData(() => api.listVideos());
  const list = videos.data ?? [];
  const anyActive = list.some(isActive);
  const { reload: reloadVideos } = videos;

  // Poll only while something is queued or processing.
  useEffect(() => {
    if (!anyActive) return;
    const id = setInterval(reloadVideos, POLL_MS);
    return () => clearInterval(id);
  }, [anyActive, reloadVideos]);

  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const uploading = uploadPct !== null;
  const current = list.find((v) => v.video_id === currentId) ?? null;

  const results = useApiData(
    () => (currentId && current?.status === 'completed' ? api.getEvents(currentId) : Promise.resolve([])),
    `${currentId}|${current?.status}|${current?.processed_at}`,
  );

  const selectFile = (f: File | undefined) => {
    setActionError(null);
    if (!f) return;
    const err = validateFile(f);
    setFileError(err);
    setFile(err ? null : f);
  };

  const startProcessing = async (videoId: string) => {
    setActionError(null);
    setCurrentId(videoId);
    try {
      await api.processVideo(videoId);
    } catch (err) {
      setActionError(`Could not start processing: ${toApiError(err).message}`);
    } finally {
      reloadVideos();
    }
  };

  const handleUploadAndProcess = async () => {
    if (!file) return;
    setActionError(null);
    setCurrentId(null);
    setUploadPct(0);
    const controller = new AbortController();
    abortRef.current = controller;
    let uploaded: VideoInfo;
    try {
      uploaded = await api.uploadVideo(file, setUploadPct, controller.signal);
    } catch (err) {
      const e = toApiError(err);
      if (e.name !== 'AbortError') setActionError(`Upload failed: ${e.message}`);
      return;
    } finally {
      setUploadPct(null);
      abortRef.current = null;
    }
    setFile(null);
    await startProcessing(uploaded.video_id);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (!uploading) selectFile(e.dataTransfer.files?.[0]);
  };

  const failed = current?.status === 'failed';

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-deep-blue">Experiments</h1>

      {/* ── Upload & process ─────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl p-8 border border-soft-blue shadow-sm space-y-6">
        <h3 className="text-lg font-bold text-deep-blue">Upload &amp; Process Experiment Video</h3>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center transition-colors ${
            dragOver ? 'border-sky-blue bg-ice-blue' : 'border-soft-blue hover:bg-ice-blue/50'
          }`}
        >
          <div className="bg-ice-blue p-4 rounded-full mb-4">
            <UploadCloud className="w-8 h-8 text-sky-blue" />
          </div>
          <h4 className="text-brand-primary font-medium mb-1">Drop a video here, or select a file</h4>
          <p className="text-sm text-brand-secondary mb-6">
            MP4, AVI, MOV or WebM · max {MAX_SIZE_MB} MB · fixed camera with people fully in view works best
          </p>
          <input
            type="file"
            accept=".mp4,.avi,.mov,.webm,video/mp4,video/x-msvideo,video/quicktime,video/webm"
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              selectFile(e.target.files?.[0]);
              e.target.value = '';
            }}
            disabled={uploading}
            className="hidden"
            id="video-upload"
          />
          <label
            htmlFor="video-upload"
            className={`bg-white border border-soft-blue px-6 py-2 rounded-lg text-sm font-medium text-brand-primary shadow-sm transition-colors ${
              uploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-ice-blue'
            }`}
          >
            Select Video
          </label>
        </div>

        {fileError && <StatusNotice tone="error">{fileError}</StatusNotice>}

        {file && !uploading && (
          <div className="p-4 bg-ice-blue rounded-xl border border-soft-blue flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <FileVideo className="w-6 h-6 text-sky-blue flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-brand-primary truncate">{file.name}</p>
                <p className="text-xs text-brand-secondary">{formatBytes(file.size)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFile(null)}
                className="p-2 rounded-lg text-brand-secondary hover:bg-soft-blue"
                title="Remove file"
              >
                <X className="w-4 h-4" />
              </button>
              <button
                onClick={handleUploadAndProcess}
                disabled={!modelReady}
                title={!modelReady ? (online ? MESSAGES.modelMissing : MESSAGES.backendOffline) : undefined}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold text-white shadow-sm transition-colors ${
                  modelReady ? 'bg-brand-success hover:bg-green-600' : 'bg-brand-secondary cursor-not-allowed'
                }`}
              >
                <Play className="w-4 h-4" />
                Upload &amp; Process
              </button>
            </div>
          </div>
        )}

        {/* ── Pipeline progress for the current video ─────────────────────── */}
        {(uploading || current) && (
          <div className="p-5 rounded-xl border border-soft-blue space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Stepper active={stepIndex(uploading, current)} failed={failed} />
              {current && <span className="text-xs text-brand-muted font-mono">{current.video_id}</span>}
            </div>

            {uploading && (
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <ProgressBar value={uploadPct ?? 0} label={`Uploading ${file?.name ?? ''}`} />
                </div>
                <button
                  onClick={() => abortRef.current?.abort()}
                  className="text-xs font-bold text-brand-alert underline"
                >
                  Cancel
                </button>
              </div>
            )}

            {current?.status === 'queued' && (
              <ProgressBar value={0} indeterminate label="Waiting for the processing worker…" />
            )}
            {current?.status === 'processing' && (
              <ProgressBar value={current.progress} label="Detecting, tracking and classifying people…" />
            )}
            {current?.status === 'uploaded' && !actionError && (
              <p className="text-sm text-brand-secondary flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Starting…
              </p>
            )}
            {failed && (
              <StatusNotice tone="error" title="Video processing failed">
                {current?.message || MESSAGES.processingFailed}
              </StatusNotice>
            )}
            {current?.status === 'completed' && (
              <>
                <StatusNotice tone={current.events_count ? 'info' : 'warning'} title="Processing complete">
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4 text-brand-success" />
                    {current.message}
                  </span>
                </StatusNotice>
                <DataState
                  loading={results.loading}
                  error={results.error}
                  isEmpty={!results.data}
                  onRetry={results.reload}
                >
                  <ResultsPanel video={current} events={results.data ?? []} />
                </DataState>
              </>
            )}
          </div>
        )}

        {actionError && (
          <StatusNotice tone="error">
            <span className="flex items-center gap-1">
              <AlertCircle className="w-4 h-4" /> {actionError}
            </span>
          </StatusNotice>
        )}
      </div>

      {/* ── All experiments ──────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-soft-blue shadow-sm overflow-hidden">
        <div className="p-6 border-b border-soft-blue flex justify-between items-center">
          <h3 className="text-lg font-bold text-deep-blue">All Experiments</h3>
          <span className="text-xs text-brand-secondary bg-ice-blue px-3 py-1 rounded-full font-medium">
            {list.length} total
          </span>
        </div>
        <DataState
          loading={videos.loading}
          error={videos.error}
          isEmpty={list.length === 0}
          onRetry={reloadVideos}
          emptyMessage="No experiments yet. Upload a video above to create one."
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-ice-blue/50 text-brand-secondary font-medium">
                <tr>
                  <th className="px-6 py-3">Video</th>
                  <th className="px-6 py-3">Uploaded</th>
                  <th className="px-6 py-3">Length</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Events</th>
                  <th className="px-6 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-soft-blue">
                {list.map((v) => {
                  const canProcess = modelReady && !isActive(v) && v.file_exists;
                  return (
                    <tr key={v.video_id} className={v.video_id === currentId ? 'bg-ice-blue/40' : 'hover:bg-ice-blue/20'}>
                      <td className="px-6 py-3">
                        <div className="font-medium text-brand-primary truncate max-w-xs">{v.filename}</div>
                        <div className="text-xs text-brand-muted font-mono">
                          {v.video_id}
                          {v.file_size != null && ` · ${formatBytes(v.file_size)}`}
                        </div>
                      </td>
                      <td className="px-6 py-3 text-xs text-brand-secondary whitespace-nowrap">
                        {v.created_at ? parseServerDate(v.created_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-6 py-3 text-brand-secondary">{formatDuration(v.duration_seconds)}</td>
                      <td className="px-6 py-3 min-w-40">
                        <div className="space-y-1">
                          <VideoStatusBadge status={v.status} />
                          {v.status === 'processing' && <ProgressBar value={v.progress} />}
                          {v.status === 'failed' && v.message && (
                            <div className="text-xs text-brand-alert max-w-xs truncate" title={v.message}>
                              {v.message}
                            </div>
                          )}
                          {!v.file_exists && <div className="text-xs text-brand-alert">Video file missing</div>}
                        </div>
                      </td>
                      <td className="px-6 py-3 text-brand-secondary">
                        {v.status === 'completed' ? v.events_count : '—'}
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-3 text-xs font-bold">
                          <Link
                            to={`/experiments/${v.video_id}`}
                            className="flex items-center gap-1 text-sky-blue hover:text-deep-blue"
                          >
                            <Eye className="w-3.5 h-3.5" /> Details
                          </Link>
                          {!isActive(v) && (
                            <button
                              onClick={() => startProcessing(v.video_id)}
                              disabled={!canProcess}
                              title={!modelReady ? MESSAGES.modelMissing : undefined}
                              className="flex items-center gap-1 text-brand-success hover:text-green-700 disabled:text-brand-muted disabled:cursor-not-allowed"
                            >
                              {v.status === 'uploaded' ? (
                                <>
                                  <Play className="w-3.5 h-3.5" /> Process
                                </>
                              ) : (
                                <>
                                  <RotateCcw className="w-3.5 h-3.5" /> {v.status === 'failed' ? 'Retry' : 'Re-process'}
                                </>
                              )}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </DataState>
      </div>
    </div>
  );
}
