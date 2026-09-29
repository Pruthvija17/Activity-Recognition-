import { API_URL, WS_URL } from './config';
import { MESSAGES } from './messages';
import type {
  ActivityEvent,
  Analytics,
  CsvReport,
  Experiment,
  HardwareStatus,
  ReportItem,
  SystemSettings,
  SystemSettingsUpdate,
  SystemStatus,
  VideoInfo,
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
  videoUrl: (videoId: string) => `${API_URL}/api/videos/${encodeURIComponent(videoId)}`,

  // Experiments & events
  getExperiments: () => request<Experiment[]>('/experiments/'),
  getEvents: (experimentId?: string) =>
    request<ActivityEvent[]>(
      experimentId ? `/events/?experiment_id=${encodeURIComponent(experimentId)}` : '/events/',
    ),
  reclassifyEvent: (eventId: string, activityType: string) =>
    request<ActivityEvent>(`/events/${encodeURIComponent(eventId)}`, json('PUT', { activity_type: activityType })),

  // Analytics & reports
  getAnalytics: () => request<Analytics>('/api/analytics'),
  getReports: () => request<ReportItem[]>('/api/reports'),
  getReportCsv: (experimentId: string) =>
    request<CsvReport>(`/api/reports/${encodeURIComponent(experimentId)}/csv`),

  // Live
  liveSocketUrl: () => `${WS_URL}/ws/live`,
};
