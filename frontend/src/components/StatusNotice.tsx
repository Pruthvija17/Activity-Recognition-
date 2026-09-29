import type { ReactNode } from 'react';
import { AlertCircle, AlertTriangle, Info, Loader2, WifiOff } from 'lucide-react';
import type { ApiError } from '../lib/api';
import { MESSAGES } from '../lib/messages';

type Tone = 'error' | 'warning' | 'info';

const toneStyles: Record<Tone, string> = {
  error: 'bg-red-50 border-red-200 text-brand-alert',
  warning: 'bg-amber-50 border-amber-200 text-amber-700',
  info: 'bg-white border-soft-blue text-brand-secondary',
};

const toneIcons = { error: AlertCircle, warning: AlertTriangle, info: Info };

export function StatusNotice({
  tone,
  title,
  children,
  action,
}: {
  tone: Tone;
  title?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  const Icon = toneIcons[tone];
  return (
    <div className={`p-4 rounded-xl border flex items-start gap-3 text-sm ${toneStyles[tone]}`}>
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        <div className={title ? 'opacity-90' : ''}>{children}</div>
      </div>
      {action}
    </div>
  );
}

/**
 * Standard loading / error / empty handling for a data-driven section.
 * Offline errors are shown compactly because the layout already shows a global offline banner.
 */
export function DataState({
  loading,
  error,
  isEmpty,
  emptyMessage = MESSAGES.noData,
  onRetry,
  children,
}: {
  loading: boolean;
  error: ApiError | null;
  isEmpty: boolean;
  emptyMessage?: string;
  onRetry?: () => void;
  children: ReactNode;
}) {
  if (error && isEmpty) {
    if (error.kind === 'offline') {
      return (
        <div className="p-6 flex items-center justify-center gap-2 text-sm text-brand-secondary">
          <WifiOff className="w-4 h-4" /> Waiting for the backend…
        </div>
      );
    }
    return (
      <StatusNotice
        tone="error"
        title="Could not load data"
        action={
          onRetry && (
            <button onClick={onRetry} className="text-xs font-bold underline whitespace-nowrap">
              Retry
            </button>
          )
        }
      >
        {error.message}
      </StatusNotice>
    );
  }
  if (loading && isEmpty) {
    return (
      <div className="p-6 flex items-center justify-center gap-2 text-sm text-brand-secondary">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (isEmpty) {
    return <div className="p-6 text-center text-sm text-brand-secondary">{emptyMessage}</div>;
  }
  return <>{children}</>;
}
