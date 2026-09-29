// User-facing messages for the common failure states (implementation plan, Phase 21).
export const MESSAGES = {
  backendOffline: 'Backend server is unavailable. Start FastAPI on port 8000 (start-backend.ps1).',
  modelMissing: 'Required AI model is missing. Check backend/weights/.',
  cameraUnavailable: 'Camera access is unavailable. Check browser permissions.',
  processingFailed: 'Video processing failed. Check backend logs.',
  noData: 'No activity data available. Process an experiment first.',
} as const;
