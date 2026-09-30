import { useCallback, useEffect, useRef, useState } from 'react';

/** Human-readable reason for a getUserMedia failure. */
export function cameraErrorMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : '';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Camera permission was denied. Allow camera access for this site in the browser (address bar → site settings) and try again.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No camera was found. Connect a camera, or pick a different one.';
    case 'NotReadableError':
    case 'AbortError':
      return 'The camera is in use by another application (e.g. Teams, Zoom, another tab). Close it and try again.';
    default:
      return `Camera access is unavailable. Check browser permissions.${err instanceof Error ? ` (${err.message})` : ''}`;
  }
}

export const cameraSupported = () =>
  typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && window.isSecureContext;

export function useCamera() {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const all = await navigator.mediaDevices.enumerateDevices();
    setDevices(all.filter((d) => d.kind === 'videoinput'));
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStream(null);
  }, []);

  const start = useCallback(
    async (deviceId?: string) => {
      if (!cameraSupported()) {
        setError('This browser cannot access cameras here (it needs a modern browser and a secure page such as localhost).');
        return;
      }
      setStarting(true);
      setError(null);
      try {
        const size = { width: { ideal: 1280 }, height: { ideal: 720 } };
        const s = await navigator.mediaDevices.getUserMedia({
          video: deviceId ? { deviceId: { exact: deviceId }, ...size } : size,
          audio: false,
        });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = s;
        s.getVideoTracks()[0]?.addEventListener('ended', () => {
          setError('The camera was disconnected.');
          setStream(null);
        });
        setStream(s);
        await refreshDevices(); // labels become available after permission is granted
      } catch (err) {
        setError(cameraErrorMessage(err));
      } finally {
        setStarting(false);
      }
    },
    [refreshDevices],
  );

  useEffect(() => {
    const md = navigator.mediaDevices;
    let alive = true;
    const load = () => {
      md?.enumerateDevices?.()
        .then((all) => {
          if (alive) setDevices(all.filter((d) => d.kind === 'videoinput'));
        })
        .catch(() => undefined);
    };
    load();
    md?.addEventListener?.('devicechange', load);
    return () => {
      alive = false;
      md?.removeEventListener?.('devicechange', load);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return { stream, devices, error, starting, start, stop, supported: cameraSupported() };
}
