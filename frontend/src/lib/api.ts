import { API_URL, WS_URL } from './config';
import { MESSAGES } from './messages';
import type {
  ActivityEvent,
  Analytics,
  CsvReport,
  Experiment,
  HardwareStatus,
  ProcessResponse,
  ReportItem,
  SystemSettings,
  SystemSettingsUpdate,
  SystemStatus,
  UploadResponse,
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
  uploadVideo: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<UploadResponse>('/api/videos/upload', { method: 'POST', body: form });
  },
  processVideo: (videoId: string) =>
    request<ProcessResponse>(`/api/videos/process/${encodeURIComponent(videoId)}`, { method: 'POST' }),
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
