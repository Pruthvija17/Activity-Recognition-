// Shapes returned by the FastAPI backend.

export interface SystemStatus {
  backend: boolean;
  version: string;
  database: boolean;
  yolo_model: boolean;
  activity_model: boolean;
  trained_activity_model: boolean;
  activity_engine: string;
  model_ready: boolean;
  model_error: string | null;
  missing_packages: string[];
  cuda: boolean;
  device: string;
  timestamp: string;
}

export interface ActivityEvent {
  id: string;
  experiment_id: string;
  person_id: string;
  video_id: string | null;
  activity_type: string;
  start_time: string;
  end_time: string;
  start_seconds: number | null;
  end_seconds: number | null;
  duration: number;
  confidence: number;
  status: string;
  zone: string | null;
  frame_number: number | null;
}

export interface Experiment {
  id: string;
  name: string;
  status: string;
  start_time: string;
  video_filename: string | null;
  video_path: string | null;
}

export interface UploadResponse {
  video_id: string;
  filename: string;
  file_size: number;
  status: string;
}

export interface ProcessedEvent {
  person_id: string;
  activity: string;
  confidence: number;
  start: string;
  end: string;
  duration: number;
  status: string;
}

export interface ProcessResponse {
  video_id: string;
  status: string;
  model_ready: boolean;
  events_count: number;
  results: ProcessedEvent[];
  metadata: Record<string, unknown>;
  message: string;
}

export interface ActivityCount {
  name: string;
  value: number;
  color: string;
}

export interface PersonStat {
  name: string;
  activities: number;
  unknowns: number;
  avg_confidence: number;
}

export interface Analytics {
  experiment_id: string | null;
  total_events: number;
  confirmed_events: number;
  unknown_events: number;
  sequence_deviations: number;
  avg_confidence: number;
  experiment_duration_seconds: number;
  activity_distribution: ActivityCount[];
  person_stats: PersonStat[];
  model_ready: boolean;
}

export interface ReportItem {
  id: string;
  experiment_id: string;
  experiment: string;
  date: string;
  events_count: number;
  confirmed_count: number;
  unknown_count: number;
  deviations: number;
  avg_confidence_pct: number;
  status: string;
}

export interface CsvReport {
  experiment_id: string;
  rows: string[][];
}

export interface SystemSettings {
  confidence_threshold: number;
  unknown_sensitivity: string;
  camera_source: string;
  updated_at: string | null;
}

export type SystemSettingsUpdate = Omit<SystemSettings, 'updated_at'>;

export interface HardwareStatus {
  cuda_available: boolean;
  cuda_device_name: string | null;
  cuda_device_count: number;
  backend: string;
  opencv_available: boolean;
  torch_available: boolean;
}

export interface LiveRecentEvent {
  person_id: string;
  activity: string;
  confidence: number;
  start_time: string;
  end_time: string;
  status: string;
}

export interface LiveStatusPayload {
  type: string;
  timestamp: string;
  backend_online: boolean;
  model_ready: boolean;
  last_experiment_id: string | null;
  last_experiment_name: string | null;
  last_experiment_status: string | null;
  recent_events: LiveRecentEvent[];
  live_detections: unknown[];
  note: string;
}
