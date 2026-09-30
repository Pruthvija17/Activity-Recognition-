import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Camera, CameraOff, Play, Square, Radio, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { ACTIVITY_COLORS, activityColor } from '../lib/activityColors';
import { MESSAGES } from '../lib/messages';
import { useCamera } from '../hooks/useCamera';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { StatusNotice } from '../components/StatusNotice';
import type { LivePerson, LiveResult, LiveSummary } from '../types/api';

type MonitorState = 'idle' | 'starting' | 'running' | 'stopping';

const CAPTURE_WIDTH = 640; // frames are downscaled before sending: enough for pose, light on bandwidth
const JPEG_QUALITY = 0.7;
const STOP_TIMEOUT_MS = 15000;
const CAMERA_KEY = 'bas.cameraDeviceId';
const PICK_OR_PLACE = 'Picking up / placing an object';

function readPref(): string {
  try {
    return localStorage.getItem(CAMERA_KEY) ?? '';
  } catch {
    return '';
  }
}

function writePref(value: string) {
  try {
    localStorage.setItem(CAMERA_KEY, value);
  } catch {
    /* storage unavailable: preference just isn't remembered */
  }
}

const personColor = (p: LivePerson) =>
  p.unknown ? ACTIVITY_COLORS.Unknown : p.activity === PICK_OR_PLACE ? ACTIVITY_COLORS['Picking up an object'] : activityColor(p.activity);

const personLabel = (p: LivePerson) =>
  p.unknown ? `${p.person} — ⚠ Unknown Activity` : `${p.person} — ${p.activity} — ${Math.round(p.confidence * 100)}%`;

export default function LiveMonitor() {
  const { online, status } = useSystemStatus();
  const modelReady = online && !!status?.model_ready;
  const cam = useCamera();

  const [deviceId, setDeviceId] = useState(readPref);
  const [fps, setFps] = useState(5);
  const [mon, setMon] = useState<MonitorState>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [result, setResult] = useState<LiveResult | null>(null);
  const [stats, setStats] = useState({ frames: 0, fps: 0, rtt: 0, inference: 0 });
  const [summary, setSummary] = useState<LiveSummary | null>(null);
  const [monError, setMonError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const captureRef = useRef<HTMLCanvasElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const runningRef = useRef(false);
  const monRef = useRef<MonitorState>('idle');
  const fpsRef = useRef(fps);
  const sentAtRef = useRef(0);
  const recvTimesRef = useRef<number[]>([]);
  const framesRef = useRef(0);
  const timerRef = useRef<number | undefined>(undefined);
  const stopTimerRef = useRef<number | undefined>(undefined);
  const resultRef = useRef<LiveResult | null>(null);
  const sendFrameRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    monRef.current = mon;
  }, [mon]);
  useEffect(() => {
    fpsRef.current = fps;
  }, [fps]);

  // Show the camera stream in the <video>.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.srcObject = cam.stream;
    if (cam.stream) v.play().catch(() => undefined);
  }, [cam.stream]);

  // ── Overlay ──────────────────────────────────────────────────────────────
  const draw = useCallback((res: LiveResult | null) => {
    const canvas = overlayRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;
    const cw = video.clientWidth;
    const ch = video.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!res || !video.videoWidth) return;

    // The video is letterboxed (object-contain): map normalised boxes into the drawn area.
    const scale = Math.min(cw / video.videoWidth, ch / video.videoHeight);
    const dw = video.videoWidth * scale;
    const dh = video.videoHeight * scale;
    const ox = (cw - dw) / 2;
    const oy = (ch - dh) / 2;

    ctx.font = '600 13px Inter, Manrope, sans-serif';
    for (const p of res.people) {
      const [bx1, by1, bx2, by2] = p.box;
      const x = ox + bx1 * dw;
      const y = oy + by1 * dh;
      const w = (bx2 - bx1) * dw;
      const h = (by2 - by1) * dh;
      const color = personColor(p);
      ctx.lineWidth = 3;
      ctx.strokeStyle = color;
      ctx.setLineDash(p.unknown ? [8, 5] : []);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);

      const text = personLabel(p);
      const tw = ctx.measureText(text).width;
      const lx = Math.min(Math.max(0, x), Math.max(0, cw - tw - 26));
      const ly = y >= 24 ? y - 24 : y + 2;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
      ctx.fillRect(lx, ly, tw + 24, 22);
      ctx.fillStyle = color;
      ctx.fillRect(lx + 6, ly + 6, 10, 10);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(text, lx + 20, ly + 15);
    }
  }, []);

  useEffect(() => {
    resultRef.current = result;
    draw(result);
  }, [result, draw]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => draw(resultRef.current));
    ro.observe(video);
    return () => ro.disconnect();
  }, [draw]);

  // ── Frame loop ───────────────────────────────────────────────────────────
  const sendFrame = useCallback(() => {
    const ws = wsRef.current;
    const video = videoRef.current;
    if (!runningRef.current || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (!video || !video.videoWidth) {
      timerRef.current = window.setTimeout(() => sendFrameRef.current(), 200);
      return;
    }
    const canvas = captureRef.current ?? (captureRef.current = document.createElement('canvas'));
    const scale = Math.min(1, CAPTURE_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob || !runningRef.current || ws.readyState !== WebSocket.OPEN) return;
        sentAtRef.current = performance.now();
        ws.send(blob);
      },
      'image/jpeg',
      JPEG_QUALITY,
    );
  }, []);

  useEffect(() => {
    sendFrameRef.current = sendFrame;
  }, [sendFrame]);

  const scheduleNext = useCallback(() => {
    if (!runningRef.current) return;
    const wait = Math.max(0, 1000 / fpsRef.current - (performance.now() - sentAtRef.current));
    timerRef.current = window.setTimeout(sendFrame, wait);
  }, [sendFrame]);

  const finish = useCallback(() => {
    runningRef.current = false;
    window.clearTimeout(timerRef.current);
    window.clearTimeout(stopTimerRef.current);
    wsRef.current = null;
    setMon('idle');
    setResult(null);
  }, []);

  const startMonitoring = async () => {
    if (!cam.stream) return;
    setMonError(null);
    setWarning(null);
    setSummary(null);
    setMon('starting');
    let info;
    try {
      info = await api.startLive(fps);
    } catch (err) {
      setMonError(toApiError(err).message);
      setMon('idle');
      return;
    }
    setSessionId(info.experiment_id);
    framesRef.current = 0;
    recvTimesRef.current = [];
    setStats({ frames: 0, fps: 0, rtt: 0, inference: 0 });

    const ws = new WebSocket(api.liveSocketUrl(info.ws_path));
    wsRef.current = ws;
    ws.onopen = () => {
      runningRef.current = true;
      setMon('running');
      sendFrame();
    };
    ws.onmessage = (ev) => {
      let msg: LiveResult | LiveSummary | { type: 'error'; message: string };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === 'result') {
        const now = performance.now();
        framesRef.current += 1;
        const times = [...recvTimesRef.current, now].slice(-10);
        recvTimesRef.current = times;
        const achieved = times.length > 1 ? ((times.length - 1) * 1000) / (times[times.length - 1] - times[0]) : 0;
        setResult(msg);
        setStats({ frames: framesRef.current, fps: achieved, rtt: now - sentAtRef.current, inference: msg.avg_inference_ms });
        scheduleNext();
      } else if (msg.type === 'error') {
        setWarning(msg.message);
        scheduleNext();
      } else if (msg.type === 'summary') {
        setSummary(msg);
        finish();
      }
    };
    ws.onclose = () => {
      if (monRef.current === 'running' || monRef.current === 'starting') {
        setMonError('Connection to the backend was lost. Frames received up to that point were saved as an experiment.');
      }
      finish();
    };
  };

  const stopMonitoring = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    runningRef.current = false;
    window.clearTimeout(timerRef.current);
    setMon('stopping');
    if (ws.readyState === WebSocket.OPEN) ws.send('stop');
    // Fallback if the summary never arrives (e.g. the socket died mid-stop).
    const id = sessionId;
    stopTimerRef.current = window.setTimeout(async () => {
      if (id) {
        try {
          const s = await api.stopLive(id);
          setSummary({ ...s, type: 'summary' });
        } catch {
          /* already finalised by the server on disconnect */
        }
      }
      ws.close();
      finish();
    }, STOP_TIMEOUT_MS);
  }, [finish, sessionId]);

  // Camera turned off or unplugged while monitoring -> end the session cleanly.
  useEffect(() => {
    if (!cam.stream && (monRef.current === 'running' || monRef.current === 'starting')) stopMonitoring();
  }, [cam.stream, stopMonitoring]);

  // Leaving the page ends the session (the server saves it on disconnect).
  useEffect(
    () => () => {
      runningRef.current = false;
      window.clearTimeout(timerRef.current);
      window.clearTimeout(stopTimerRef.current);
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send('stop');
      ws?.close();
    },
    [],
  );

  const running = mon === 'running';
  const busy = mon === 'starting' || mon === 'stopping';
  const people = result?.people ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-deep-blue">Live Monitor</h1>
        <div className="flex items-center gap-2 text-sm font-medium bg-white px-4 py-2 rounded-lg border border-soft-blue">
          <Radio className={`w-4 h-4 ${running ? 'text-brand-alert animate-pulse' : 'text-brand-muted'}`} />
          {running ? `AI monitoring live · ${stats.fps.toFixed(1)} fps` : cam.stream ? 'Camera on · AI monitoring off' : 'Camera off'}
        </div>
      </div>

      {/* ── Controls ───────────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-4 flex flex-wrap items-center gap-3">
        <select
          value={deviceId}
          onChange={(e) => {
            setDeviceId(e.target.value);
            writePref(e.target.value);
            if (cam.stream) cam.start(e.target.value || undefined);
          }}
          disabled={busy || running}
          className="bg-ice-blue border border-soft-blue rounded-lg px-3 py-2 text-sm text-deep-blue max-w-xs"
          aria-label="Camera"
        >
          <option value="">Default camera</option>
          {cam.devices.map((d, i) => (
            <option key={d.deviceId || i} value={d.deviceId}>
              {d.label || `Camera ${i + 1}`}
            </option>
          ))}
        </select>
        {cam.stream ? (
          <button
            onClick={cam.stop}
            disabled={busy || running}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-soft-blue text-sm font-bold text-brand-secondary hover:bg-ice-blue disabled:opacity-50"
          >
            <CameraOff className="w-4 h-4" /> Stop camera
          </button>
        ) : (
          <button
            onClick={() => cam.start(deviceId || undefined)}
            disabled={cam.starting}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-deep-blue text-white text-sm font-bold hover:opacity-90 disabled:opacity-50"
          >
            <Camera className="w-4 h-4" /> {cam.starting ? 'Starting camera…' : 'Start camera'}
          </button>
        )}

        <div className="h-8 w-px bg-soft-blue mx-1" />

        <label className="flex items-center gap-2 text-sm text-brand-secondary">
          Analyse
          <select
            value={fps}
            onChange={(e) => setFps(Number(e.target.value))}
            disabled={busy || running}
            className="bg-ice-blue border border-soft-blue rounded-lg px-2 py-2 text-sm text-deep-blue"
            aria-label="Frames per second to analyse"
          >
            {[1, 2, 3, 5, 8, 10].map((n) => (
              <option key={n} value={n}>
                {n} fps
              </option>
            ))}
          </select>
        </label>
        {running || mon === 'stopping' ? (
          <button
            onClick={stopMonitoring}
            disabled={mon === 'stopping'}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-alert text-white text-sm font-bold hover:opacity-90 disabled:opacity-60"
          >
            <Square className="w-4 h-4" /> {mon === 'stopping' ? 'Saving session…' : 'Stop AI monitoring'}
          </button>
        ) : (
          <button
            onClick={startMonitoring}
            disabled={!cam.stream || !modelReady || busy}
            title={!cam.stream ? 'Start the camera first' : !modelReady ? MESSAGES.modelMissing : undefined}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-success text-white text-sm font-bold hover:bg-green-600 disabled:bg-brand-secondary disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" /> {mon === 'starting' ? 'Starting…' : 'Start AI monitoring'}
          </button>
        )}
      </div>

      {!cam.supported && (
        <StatusNotice tone="error" title="Camera not supported">
          This browser can't access cameras on this page. Use a current Chrome/Edge/Firefox on http://localhost.
        </StatusNotice>
      )}
      {cam.error && <StatusNotice tone="error" title="Camera unavailable">{cam.error}</StatusNotice>}
      {monError && <StatusNotice tone="error" title="AI monitoring stopped">{monError}</StatusNotice>}
      {warning && running && <StatusNotice tone="warning">{warning}</StatusNotice>}

      {summary && (
        <StatusNotice
          tone="info"
          title="Live session saved"
          action={
            <Link to={`/experiments/${summary.experiment_id}`} className="text-xs font-bold text-sky-blue underline whitespace-nowrap">
              Open experiment
            </Link>
          }
        >
          <span className="flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-brand-success" /> {summary.message}
          </span>
        </StatusNotice>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* ── Video + overlay ──────────────────────────────────────────── */}
        <div className="xl:col-span-2 bg-slate-950 rounded-2xl overflow-hidden aspect-video relative">
          <video ref={videoRef} className="w-full h-full object-contain" muted playsInline />
          <canvas ref={overlayRef} className="absolute inset-0 w-full h-full pointer-events-none" />
          {!cam.stream && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/60 text-sm text-center px-8">
              <CameraOff className="w-10 h-10 text-white/30" />
              Camera is off. Press <strong className="text-white/80">Start camera</strong> and allow camera access when the
              browser asks.
            </div>
          )}
          {running && (
            <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/70 text-white text-xs font-bold px-2.5 py-1 rounded">
              <span className="w-2 h-2 rounded-full bg-brand-alert animate-pulse" /> LIVE · AI
            </div>
          )}
        </div>

        {/* ── Side panel ───────────────────────────────────────────────── */}
        <div className="space-y-6">
          <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6">
            <h3 className="text-lg font-bold text-deep-blue mb-3">People in view</h3>
            {!running ? (
              <p className="text-sm text-brand-secondary">Start AI monitoring to see live detections.</p>
            ) : people.length === 0 ? (
              <p className="text-sm text-brand-secondary">No people detected in the current frame.</p>
            ) : (
              <ul className="space-y-2">
                {people.map((p) => (
                  <li
                    key={p.track_id}
                    className={`p-3 rounded-xl border ${p.unknown ? 'bg-red-50/70 border-red-200' : 'bg-ice-blue border-soft-blue'}`}
                  >
                    <div className="flex justify-between text-xs font-bold text-brand-secondary">
                      <span>{p.person}</span>
                      <span>{Math.round(p.confidence * 100)}%</span>
                    </div>
                    <div className={`mt-1 flex items-center gap-2 font-bold ${p.unknown ? 'text-brand-alert' : 'text-deep-blue'}`}>
                      {p.unknown ? (
                        <AlertTriangle className="w-4 h-4" />
                      ) : (
                        <span className="w-2.5 h-2.5 rounded-sm" style={{ background: personColor(p) }} />
                      )}
                      {p.unknown ? 'Unknown Activity' : p.activity}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6">
            <h3 className="text-lg font-bold text-deep-blue mb-3">Session</h3>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-brand-secondary">Session</dt>
              <dd className="text-right font-mono text-xs text-brand-primary">{sessionId ?? '—'}</dd>
              <dt className="text-brand-secondary">Frames analysed</dt>
              <dd className="text-right text-brand-primary">{stats.frames}</dd>
              <dt className="text-brand-secondary">Session time</dt>
              <dd className="text-right text-brand-primary">{(stats.frames / fps).toFixed(1)} s</dd>
              <dt className="text-brand-secondary">Achieved rate</dt>
              <dd className="text-right text-brand-primary">
                {stats.fps.toFixed(1)} / {fps} fps
              </dd>
              <dt className="text-brand-secondary">Round-trip latency</dt>
              <dd className="text-right text-brand-primary">{Math.round(stats.rtt)} ms</dd>
              <dt className="text-brand-secondary">Inference (server)</dt>
              <dd className="text-right text-brand-primary">{Math.round(stats.inference)} ms</dd>
            </dl>
            <p className="text-xs text-brand-muted mt-3">
              Frames are downscaled to {CAPTURE_WIDTH}px and sent one at a time; if the server is slower than the chosen
              rate, fewer frames are analysed rather than queueing up. The session is recorded and saved as an experiment
              when monitoring stops.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
