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
