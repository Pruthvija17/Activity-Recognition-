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
  review_status?: ReviewStatus;
  original_activity?: string | null;
}

export interface Experiment {
  id: string;
  name: string;
  status: string;
  start_time: string;
  video_filename: string | null;
  video_path: string | null;
}

export type VideoStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed';

/** Upload + processing state of one experiment video (GET /api/videos/{id}/status). */
export interface VideoInfo {
  video_id: string;
  filename: string;
  status: VideoStatus;
  progress: number;
  message: string | null;
  source: string;
  file_size: number | null;
  duration_seconds: number | null;
  fps: number | null;
  frame_count: number | null;
  engine: string | null;
  created_at: string | null;
  processed_at: string | null;
  processing_seconds: number | null;
  events_count: number | null;
  file_exists: boolean;
  codec: string | null;
  preview_status: 'not_needed' | 'pending' | 'ready' | 'failed' | 'unavailable' | null;
  playable: boolean;
}

export interface WorkflowStep {
  index: number;
  activity: string;
  status: 'done' | 'missing' | 'out_of_order';
  time: number | null;
  person: string | null;
}

export interface WorkflowDeviation {
  type: 'missing' | 'out_of_order' | 'unexpected' | 'unknown';
  step_index: number | null;
  activity: string;
  time: number | null;
  person: string | null;
  detail: string;
}

export interface WorkflowResult {
  expected_sequence: string[];
  observed_sequence: string[];
  steps: WorkflowStep[];
  deviations: WorkflowDeviation[];
  notes: { type: string; activity: string; time: number; person: string }[];
  deviation_count: number;
  completed_steps: number;
  completion: number;
  next_expected_step: string | null;
  is_compliant: boolean;
  message: string;
  configured: boolean;
  scope: string;
}

export interface ExperimentDetail {
  experiment: VideoInfo;
  people: { person_id: string; label: string; events: number; first_seen: number | null }[];
  events: ReviewEvent[];
  workflow: WorkflowResult;
}

export interface ActivityStat {
  name: string;
  count: number;
  seconds: number;
  avg_confidence: number | null;
  color: string;
}

export interface PersonStat {
  person_id: string;
  name: string;
  experiment_id: string;
  events: number;
  unknowns: number;
  active_seconds: number;
  avg_confidence: number | null;
  top_activity: string | null;
  seconds_by_activity: Record<string, number>;
}

export interface Analytics {
  experiment_id: string | null;
  experiments_count: number;
  people_count: number;
  total_events: number;
  rejected_events: number;
  pending_review: number;
  reviewed_events: number;
  unknown_events: number;
  avg_confidence: number | null;
  total_activity_seconds: number;
  activity_distribution: ActivityStat[];
  person_stats: PersonStat[];
  confidence_histogram: { bucket: string; count: number }[];
  activity_engine: string;
}

export type ReviewStatus = 'auto' | 'pending' | 'confirmed' | 'rejected' | 'reclassified';
export type ReviewActionName = 'confirm' | 'reject' | 'reclassify';

export interface ReviewEvent {
  id: string;
  experiment_id: string;
  video_id: string;
  video: string | null;
  person_id: string;
  person: string;
  activity_type: string;
  original_activity: string | null;
  start_time: string;
  end_time: string;
  start_seconds: number | null;
  end_seconds: number | null;
  duration: number;
  confidence: number;
  status: string;
  review_status: ReviewStatus;
  reviewed_at: string | null;
}

export interface DashboardSummary {
  experiments: { total: number; active: number; completed: number; failed: number; uploaded: number };
  people_detected: number;
  total_events: number;
  pending_review: number;
  unknown_events: number;
  avg_confidence: number | null;
  current_job: { video_id: string; filename: string; status: string; progress: number } | null;
  recent_events: {
    id: string;
    experiment_id: string;
    video: string | null;
    person: string;
    activity: string;
    start_time: string;
    end_time: string;
    confidence: number;
    review_status: ReviewStatus;
  }[];
}

export interface ReportItem {
  report_id: string;
  experiment_id: string;
  video: string;
  processed_at: string | null;
  duration_seconds: number | null;
  events: number;
  people: number;
  unknown_events: number;
  pending_review: number;
  avg_confidence: number | null;
  workflow_deviations: number;
  workflow_compliant: boolean;
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
