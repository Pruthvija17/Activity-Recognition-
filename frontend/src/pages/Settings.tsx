import { useEffect, useState } from 'react';
import { Sliders, Camera, Cpu, CheckCircle2, AlertCircle, Loader2, RefreshCw } from 'lucide-react';

interface SystemSettings {
  confidence_threshold: number;
  unknown_sensitivity: string;
  camera_source: string;
  updated_at: string | null;
}

interface HardwareStatus {
  cuda_available: boolean;
  cuda_device_name: string | null;
  cuda_device_count: number;
  backend: string;
  opencv_available: boolean;
  torch_available: boolean;
}

const CAMERA_SOURCES = [
  'Camera 01 (Overhead Station)',
  'Camera 02 (Workbench Side Feed)',
  'RTSP Network Stream (rtsp://192.168.1.100/live)',
];

export default function Settings() {
  // ── Local form state (mirrors backend) ──────────────────────────────────
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(60);
  const [unknownSensitivity, setUnknownSensitivity] = useState<string>('Medium');
  const [cameraSource, setCameraSource] = useState<string>(CAMERA_SOURCES[0]);

  // ── Async state ──────────────────────────────────────────────────────────
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [hardwareStatus, setHardwareStatus] = useState<HardwareStatus | null>(null);
  const [hardwareLoading, setHardwareLoading] = useState(true);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<{ text: string; isError: boolean } | null>(null);

  // ── Load settings from backend on mount ──────────────────────────────────
  const loadSettings = async () => {
    setLoadingSettings(true);
    try {
      const res = await fetch('http://localhost:8000/api/settings');
      if (res.ok) {
        const data: SystemSettings = await res.json();
        setConfidenceThreshold(data.confidence_threshold);
        setUnknownSensitivity(data.unknown_sensitivity);
        setCameraSource(data.camera_source);
        setSavedAt(data.updated_at);
      }
    } catch (err) {
      console.error('Failed to load settings:', err);
    } finally {
      setLoadingSettings(false);
    }
  };

  // ── Load hardware status ──────────────────────────────────────────────────
  const loadHardware = async () => {
    setHardwareLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/model/hardware');
      if (res.ok) {
        const data: HardwareStatus = await res.json();
        setHardwareStatus(data);
      }
    } catch (err) {
      console.error('Failed to load hardware status:', err);
    } finally {
      setHardwareLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
    loadHardware();
  }, []);

  // ── Save settings to backend ─────────────────────────────────────────────
  const handleSave = async () => {
    setSavingSettings(true);
    setSaveResult(null);
    try {
      const res = await fetch('http://localhost:8000/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confidence_threshold: confidenceThreshold,
          unknown_sensitivity: unknownSensitivity,
          camera_source: cameraSource,
        }),
      });

      if (res.ok) {
        const data: SystemSettings = await res.json();
        setSavedAt(data.updated_at);
        setSaveResult({
          text: `Settings saved and applied to the live pipeline at ${new Date().toLocaleTimeString()}.`,
          isError: false,
        });
      } else {
        const err = await res.json().catch(() => ({}));
        setSaveResult({ text: err.detail || 'Failed to save settings.', isError: true });
      }
    } catch {
      setSaveResult({ text: 'Backend offline — settings not saved.', isError: true });
    } finally {
      setSavingSettings(false);
      setTimeout(() => setSaveResult(null), 6000);
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-deep-blue">System Settings &amp; Calibration</h1>
        <button
          onClick={handleSave}
          disabled={savingSettings || loadingSettings}
          className={`flex items-center gap-2 text-white font-bold px-4 py-2 rounded-lg transition-colors shadow-sm text-sm ${
            savingSettings || loadingSettings
              ? 'bg-brand-secondary cursor-not-allowed'
              : 'bg-sky-blue hover:bg-[#2CA1D9]'
          }`}
        >
          {savingSettings && <Loader2 className="w-4 h-4 animate-spin" />}
          {savingSettings ? 'Saving…' : 'Save Configuration'}
        </button>
      </div>

      {/* ── Save result toast ───────────────────────────────────────────────── */}
      {saveResult && (
        <div
          className={`p-4 rounded-xl border flex items-center gap-2 text-sm font-medium ${
            saveResult.isError
              ? 'bg-red-50 text-brand-alert border-red-200'
              : 'bg-green-50 text-brand-success border-green-100'
          }`}
        >
          {saveResult.isError ? (
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
          ) : (
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          )}
          {saveResult.text}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* ── AI Thresholds ──────────────────────────────────────────────────── */}
        <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm space-y-6">
          <div className="flex items-center gap-3 border-b border-soft-blue pb-4">
            <Sliders className="w-5 h-5 text-sky-blue" />
            <h3 className="text-lg font-bold text-deep-blue">AI Classification Thresholds</h3>
          </div>

          {loadingSettings ? (
            <div className="flex items-center gap-2 text-sm text-brand-secondary py-4">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading saved settings…
            </div>
          ) : (
            <>
              {/* Confidence Threshold Slider */}
              <div>
                <div className="flex justify-between text-sm font-medium mb-2">
                  <span className="text-brand-primary">Minimum Confidence Cutoff</span>
                  <span className="text-sky-blue font-bold">{confidenceThreshold}%</span>
                </div>
                <input
                  type="range"
                  min="50"
                  max="95"
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                  className="w-full h-2 bg-ice-blue rounded-lg appearance-none cursor-pointer accent-sky-blue"
                />
                <p className="text-xs text-brand-secondary mt-2">
                  Detections below this threshold will automatically be sent to the Human Review Queue.
                  Currently set to <strong>{confidenceThreshold}%</strong>. Applied to the live pipeline on save.
                </p>
              </div>

              {/* Unknown Sensitivity */}
              <div>
                <label className="block text-sm font-medium text-brand-primary mb-2">
                  Unknown Activity Sensitivity
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {['Low', 'Medium', 'High'].map((sens) => (
                    <button
                      key={sens}
                      onClick={() => setUnknownSensitivity(sens)}
                      className={`py-2 rounded-lg text-xs font-bold transition-all border ${
                        unknownSensitivity === sens
                          ? 'bg-sky-blue text-white border-sky-blue shadow-sm'
                          : 'bg-white text-brand-primary border-soft-blue hover:bg-ice-blue'
                      }`}
                    >
                      {sens}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-brand-secondary mt-2">
                  {unknownSensitivity === 'Low' &&
                    'Low: Only flag activities with very high ambiguity entropy (>2.5). Fewer false unknowns.'}
                  {unknownSensitivity === 'Medium' &&
                    'Medium: Balanced detection (entropy >1.75). Recommended for BAS operations.'}
                  {unknownSensitivity === 'High' &&
                    'High: Aggressive flagging of any ambiguous activity (entropy >1.0). More review events.'}
                </p>
              </div>

              {savedAt && (
                <p className="text-xs text-brand-muted pt-2 border-t border-soft-blue">
                  Last saved: {formatDate(savedAt)}
                </p>
              )}
            </>
          )}
        </div>

        {/* ── Camera Source + Hardware ───────────────────────────────────────── */}
        <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm space-y-6">
          <div className="flex items-center gap-3 border-b border-soft-blue pb-4">
            <Camera className="w-5 h-5 text-sky-blue" />
            <h3 className="text-lg font-bold text-deep-blue">Camera Stream Input</h3>
          </div>

          <div>
            <label className="block text-sm font-medium text-brand-primary mb-2">
              Active Camera Hardware
            </label>
            <select
              value={cameraSource}
              onChange={(e) => setCameraSource(e.target.value)}
              disabled={loadingSettings}
              className="w-full bg-ice-blue border border-soft-blue rounded-lg px-4 py-2.5 text-sm font-medium text-deep-blue focus:outline-none focus:ring-2 focus:ring-sky-blue disabled:opacity-50"
            >
              {CAMERA_SOURCES.map((src) => (
                <option key={src}>{src}</option>
              ))}
            </select>
          </div>

          {/* Hardware Acceleration Status */}
          <div className="p-4 bg-ice-blue/60 rounded-xl border border-soft-blue space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-brand-primary">
                <Cpu className="w-4 h-4 text-sky-blue" />
                Hardware Acceleration Status
              </div>
              <button
                onClick={loadHardware}
                disabled={hardwareLoading}
                className="text-sky-blue hover:text-deep-blue transition-colors"
                title="Refresh hardware status"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${hardwareLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {hardwareLoading ? (
              <p className="text-xs text-brand-secondary flex items-center gap-2">
                <Loader2 className="w-3 h-3 animate-spin" /> Detecting hardware…
              </p>
            ) : hardwareStatus ? (
              <div className="space-y-1.5 text-xs">
                {/* CUDA */}
                <div className="flex justify-between">
                  <span className="text-brand-secondary">CUDA / GPU Acceleration</span>
                  {hardwareStatus.cuda_available ? (
                    <span className="font-bold text-brand-success">
                      Enabled — {hardwareStatus.cuda_device_name ?? 'Unknown GPU'}
                    </span>
                  ) : (
                    <span className="font-bold text-brand-warning">Not Available (CPU mode)</span>
                  )}
                </div>

                {/* PyTorch */}
                <div className="flex justify-between">
                  <span className="text-brand-secondary">PyTorch</span>
                  <span className={`font-bold ${hardwareStatus.torch_available ? 'text-brand-success' : 'text-brand-secondary'}`}>
                    {hardwareStatus.torch_available ? 'Installed' : 'Not installed'}
                  </span>
                </div>

                {/* OpenCV */}
                <div className="flex justify-between">
                  <span className="text-brand-secondary">OpenCV (cv2)</span>
                  <span className={`font-bold ${hardwareStatus.opencv_available ? 'text-brand-success' : 'text-brand-secondary'}`}>
                    {hardwareStatus.opencv_available ? 'Installed' : 'Not installed'}
                  </span>
                </div>

                {/* Backend */}
                <div className="flex justify-between pt-1 border-t border-soft-blue">
                  <span className="text-brand-secondary">Inference Backend</span>
                  <span className={`font-bold uppercase ${hardwareStatus.backend === 'cuda' ? 'text-sky-blue' : 'text-brand-secondary'}`}>
                    {hardwareStatus.backend}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-brand-alert">
                Could not reach backend. Ensure FastAPI is running on port 8000.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
