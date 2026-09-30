import { API_URL, WS_URL } from './config';
import { MESSAGES } from './messages';
import type {
  ActivityEvent,
  Analytics,
  DashboardSummary,
  ExperimentDetail,
  HardwareStatus,
  LiveSessionInfo,
  LiveSummary,
  ReportItem,
  ReviewActionName,
  ReviewEvent,
  SystemSettings,
  SystemSettingsUpdate,
  SystemStatus,
  TrainingSummary,
  VideoInfo,
  WorkflowResult,
} from '../types/api';

/** `offline`: the backend could not be reached at all. `http`: it answered with an error. */
export type ApiErrorKind = 'offline' | 'http';

export class ApiError extends Error {
  kind: ApiErrorKind;
  status: number;

  constructor(kind: ApiErrorKind, message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
  }
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError('http', err instanceof Error ? err.message : String(err));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError('offline', MESSAGES.backendOffline);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail =
      body && typeof body.detail === 'string' ? body.detail : `Request failed (HTTP ${res.status}).`;
    throw new ApiError('http', detail, res.status);
  }
  return (await res.json()) as T;
}

function errorFromResponse(status: number, bodyText: string): ApiError {
  let detail = `Request failed (HTTP ${status}).`;
  try {
    const body = JSON.parse(bodyText);
    if (body && typeof body.detail === 'string') detail = body.detail;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError('http', detail, status);
}

/**
 * Upload with progress reporting (fetch cannot report upload progress, XHR can).
 * Rejects with an AbortError-named ApiError when `signal` aborts.
 */
function uploadWithProgress(file: File, onProgress?: (pct: number) => void, signal?: AbortSignal) {
  return new Promise<VideoInfo>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}/api/videos/upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress((e.loaded / e.total) * 100);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as VideoInfo);
        } catch {
          reject(new ApiError('http', 'Unexpected response from the server.', xhr.status));
        }
      } else {
        reject(errorFromResponse(xhr.status, xhr.responseText));
      }
    };
    xhr.onerror = () => reject(new ApiError('offline', MESSAGES.backendOffline));
    xhr.onabort = () => {
      const err = new ApiError('http', 'Upload cancelled.');
      err.name = 'AbortError';
      reject(err);
    };
    signal?.addEventListener('abort', () => xhr.abort());
    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const api = {
  // System
  getSystemStatus: () => request<SystemStatus>('/api/system/status'),
  getHardware: () => request<HardwareStatus>('/api/model/hardware'),

  // Settings
  getSettings: () => request<SystemSettings>('/api/settings'),
  updateSettings: (body: SystemSettingsUpdate) => request<SystemSettings>('/api/settings', json('PUT', body)),

  // Videos
  uploadVideo: uploadWithProgress,
  processVideo: (videoId: string) =>
    request<VideoInfo>(`/api/videos/${encodeURIComponent(videoId)}/process`, { method: 'POST' }),
  getVideoStatus: (videoId: string) =>
    request<VideoInfo>(`/api/videos/${encodeURIComponent(videoId)}/status`),
  listVideos: () => request<VideoInfo[]>('/api/videos'),
  /** `version` (e.g. the preview status) changes the URL when the served file changes. */
  videoUrl: (videoId: string, version?: string | null) =>
    `${API_URL}/api/videos/${encodeURIComponent(videoId)}` + (version ? `?v=${encodeURIComponent(version)}` : ''),

  // Experiments & events
  getEvents: (experimentId?: string) =>
    request<ActivityEvent[]>(
      experimentId ? `/events/?experiment_id=${encodeURIComponent(experimentId)}` : '/events/',
    ),

  // Review
  getReviewEvents: (opts: { experimentId?: string; status?: 'pending' | 'reviewed' | 'all' } = {}) => {
    const q = new URLSearchParams({ status: opts.status ?? 'pending' });
    if (opts.experimentId) q.set('experiment_id', opts.experimentId);
    return request<ReviewEvent[]>(`/api/review/events?${q}`);
  },
  reviewEvent: (eventId: string, action: ReviewActionName, activity?: string) =>
    request<ReviewEvent>(`/api/review/events/${encodeURIComponent(eventId)}`, json('POST', { action, activity })),

  // Dashboard, analytics & reports
  getDashboard: () => request<DashboardSummary>('/api/dashboard/summary'),
  getAnalytics: (experimentId?: string) =>
    request<Analytics>(experimentId ? `/api/analytics?experiment_id=${encodeURIComponent(experimentId)}` : '/api/analytics'),
  getReports: () => request<ReportItem[]>('/api/reports'),
  reportUrl: (experimentId: string, format: 'json' | 'csv' | 'pdf') => {
    const base = `${API_URL}/api/reports/${encodeURIComponent(experimentId)}`;
    return format === 'json' ? `${base}?download=true` : `${base}/${format}`;
  },

  // Experiment detail & workflow
  getExperiment: (experimentId: string) =>
    request<ExperimentDetail>(`/api/experiments/${encodeURIComponent(experimentId)}`),
  getWorkflow: (experimentId: string, personId?: string) =>
    request<WorkflowResult>(
      `/api/experiments/${encodeURIComponent(experimentId)}/workflow` +
        (personId ? `?person_id=${encodeURIComponent(personId)}` : ''),
    ),
  setWorkflow: (experimentId: string, steps: string[]) =>
    request<WorkflowResult>(
      `/api/experiments/${encodeURIComponent(experimentId)}/workflow`,
      json('PUT', { expected_sequence: steps }),
    ),
  deleteExperiment: (experimentId: string) =>
    request<{ deleted: string; files_removed: number }>(`/api/experiments/${encodeURIComponent(experimentId)}`, {
      method: 'DELETE',
    }),
  resetWorkflow: (experimentId: string) =>
    request<WorkflowResult>(`/api/experiments/${encodeURIComponent(experimentId)}/workflow`, { method: 'DELETE' }),

  // Training data
  getTrainingSummary: () => request<TrainingSummary>('/api/training/summary'),
  trainingLabelsUrl: () => `${API_URL}/api/training/labels.csv`,

  // Live camera monitoring
  startLive: (fps: number, name?: string) =>
    request<LiveSessionInfo>('/api/live/sessions', json('POST', { fps, name })),
  stopLive: (experimentId: string) =>
    request<LiveSummary>(`/api/live/sessions/${encodeURIComponent(experimentId)}/stop`, { method: 'POST' }),
  liveSocketUrl: (wsPath: string) => `${WS_URL}${wsPath}`,
};
