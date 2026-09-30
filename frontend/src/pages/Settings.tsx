import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sliders, Camera, Cpu, CheckCircle2, AlertCircle, Loader2, RefreshCw, Server } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { API_URL } from '../lib/config';
import { parseServerDate } from '../lib/format';
import { cameraSupported } from '../hooks/useCamera';
import { useApiData } from '../hooks/useApiData';
import { useSystemStatus } from '../hooks/useSystemStatus';
import type { SystemSettings } from '../types/api';

/** Real browser camera status: support, permission state and detected devices. */
function CameraStatus() {
  const [permission, setPermission] = useState<string>('checking…');
  const [cameras, setCameras] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    navigator.permissions
      ?.query({ name: 'camera' as PermissionName })
      .then((p) => {
        if (!alive) return;
        setPermission(p.state);
        p.onchange = () => setPermission(p.state);
      })
      .catch(() => alive && setPermission('unknown (browser does not report it)'));
    navigator.mediaDevices
      ?.enumerateDevices?.()
      .then((all) => alive && setCameras(all.filter((d) => d.kind === 'videoinput').length))
      .catch(() => alive && setCameras(0));
    return () => {
      alive = false;
    };
  }, []);

  const supported = cameraSupported();
  const permissionText: Record<string, string> = { granted: 'Allowed', denied: 'Blocked', prompt: 'Will ask when used' };
  return (
    <div className="space-y-1.5 text-sm">
      <div className="flex justify-between">
        <span className="text-brand-secondary">Browser camera support</span>
        <span className={`font-bold ${supported ? 'text-brand-success' : 'text-brand-alert'}`}>{supported ? 'Supported' : 'Not available'}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-brand-secondary">Camera permission</span>
        <span className={`font-bold ${permission === 'denied' ? 'text-brand-alert' : 'text-brand-primary'}`}>
          {permissionText[permission] ?? permission}
        </span>
      </div>
      <div className="flex justify-between">
        <span className="text-brand-secondary">Cameras detected</span>
        <span className="font-bold text-brand-primary">{cameras ?? '…'}</span>
      </div>
      <p className="text-xs text-brand-muted pt-1">
        Choose the camera and analysis rate on the <Link to="/live" className="text-sky-blue underline">Live Monitor</Link> page.
        {permission === 'denied' && ' Camera access is blocked: allow it in the site settings of this browser.'}
      </p>
    </div>
  );
}

export default function Settings() {
  const { connection, status } = useSystemStatus();

  // ── Local form state (mirrors backend) ──────────────────────────────────
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(60);
  const [unknownSensitivity, setUnknownSensitivity] = useState<string>('Medium');
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // ── Async state ──────────────────────────────────────────────────────────
  const settings = useApiData(() => api.getSettings());
  const hardware = useApiData(() => api.getHardware());
  const loadingSettings = settings.data === null;
  const hardwareStatus = hardware.data;
  const hardwareLoading = hardware.loading && !hardware.data;
  const [savingSettings, setSavingSettings] = useState(false);
  const [saveResult, setSaveResult] = useState<{ text: string; isError: boolean } | null>(null);

  // Copy freshly loaded backend settings into the form (adjusting state during render).
  const [syncedFrom, setSyncedFrom] = useState<SystemSettings | null>(null);
  if (settings.data && settings.data !== syncedFrom) {
    setSyncedFrom(settings.data);
    setConfidenceThreshold(settings.data.confidence_threshold);
    setUnknownSensitivity(settings.data.unknown_sensitivity);
    setSavedAt(settings.data.updated_at);
  }

  // ── Save settings to backend ─────────────────────────────────────────────
  const handleSave = async () => {
    setSavingSettings(true);
    setSaveResult(null);
    try {
      const data = await api.updateSettings({
        confidence_threshold: confidenceThreshold,
        unknown_sensitivity: unknownSensitivity,
        camera_source: settings.data?.camera_source ?? '',
      });
      setSavedAt(data.updated_at);
      setSaveResult({
        text: `Settings saved and applied to the live pipeline at ${new Date().toLocaleTimeString()}.`,
        isError: false,
      });
    } catch (err) {
      setSaveResult({ text: `Settings not saved: ${toApiError(err).message}`, isError: true });
    } finally {
      setSavingSettings(false);
      setTimeout(() => setSaveResult(null), 6000);
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return null;
    try {
      return parseServerDate(iso).toLocaleString();
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
              {settings.error ? (
                <span>{settings.error.kind === 'offline' ? 'Waiting for the backend…' : settings.error.message}</span>
              ) : (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading saved settings…
                </>
              )}
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
            <h3 className="text-lg font-bold text-deep-blue">Camera &amp; Hardware</h3>
          </div>

          <CameraStatus />

          {/* Hardware Acceleration Status */}
          <div className="p-4 bg-ice-blue/60 rounded-xl border border-soft-blue space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-brand-primary">
                <Cpu className="w-4 h-4 text-sky-blue" />
                Hardware Acceleration Status
              </div>
              <button
                onClick={hardware.reload}
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

        {/* ── Connection & model status ─────────────────────────────────────── */}
        <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm space-y-4 md:col-span-2">
          <div className="flex items-center gap-3 border-b border-soft-blue pb-4">
            <Server className="w-5 h-5 text-sky-blue" />
            <h3 className="text-lg font-bold text-deep-blue">Connection &amp; AI Model Status</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-brand-secondary">API URL</span>
              <span className="font-mono text-xs text-deep-blue">{API_URL}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-brand-secondary">Backend</span>
              <span className={`font-bold ${connection === 'online' ? 'text-brand-success' : 'text-brand-alert'}`}>
                {connection === 'online' ? `Connected (v${status?.version})` : connection === 'checking' ? 'Checking…' : 'Offline'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-brand-secondary">Person detector (YOLO pose)</span>
              <span className={`font-bold ${status?.yolo_model ? 'text-brand-success' : 'text-brand-alert'}`}>
                {status ? (status.yolo_model ? 'Ready' : 'Not loaded') : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-brand-secondary">Activity engine</span>
              <span className="font-bold text-amber-700">{status?.activity_engine ?? '—'}</span>
            </div>
            {status?.model_error && (
              <p className="md:col-span-2 text-xs text-brand-alert font-mono">{status.model_error}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
