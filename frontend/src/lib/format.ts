/** Confidence as a whole percentage. The backend stores 0–1; tolerate legacy 0–100 values. */
export function confidencePct(confidence: number): number {
  return Math.round(confidence > 1 ? confidence : confidence * 100);
}

export function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** Backend timestamps are UTC; older ones lack a zone suffix, which browsers would read as local time. */
export function parseServerDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

/** Seconds as m:ss (or h:mm:ss for long videos). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h ? String(m).padStart(2, '0') : String(m);
  return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}
