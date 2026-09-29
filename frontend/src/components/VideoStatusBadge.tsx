import type { VideoStatus } from '../types/api';

const styles: Record<VideoStatus, string> = {
  uploaded: 'bg-soft-blue text-deep-blue',
  queued: 'bg-amber-50 text-amber-700 border border-amber-200',
  processing: 'bg-sky-blue/15 text-sky-700 border border-sky-blue/40 animate-pulse',
  completed: 'bg-green-50 text-brand-success border border-green-200',
  failed: 'bg-red-50 text-brand-alert border border-red-200',
};

const labels: Record<VideoStatus, string> = {
  uploaded: 'Uploaded',
  queued: 'Queued',
  processing: 'Processing',
  completed: 'Completed',
  failed: 'Failed',
};

export default function VideoStatusBadge({ status }: { status: VideoStatus }) {
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap ${styles[status] ?? styles.uploaded}`}>
      {labels[status] ?? status}
    </span>
  );
}
