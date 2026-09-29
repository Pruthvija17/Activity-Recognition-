export default function ProgressBar({
  value,
  tone = 'sky',
  indeterminate = false,
  label,
}: {
  value: number;
  tone?: 'sky' | 'green' | 'red';
  indeterminate?: boolean;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  const fill = tone === 'green' ? 'bg-brand-success' : tone === 'red' ? 'bg-brand-alert' : 'bg-sky-blue';
  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between text-xs text-brand-secondary mb-1">
          <span>{label}</span>
          {!indeterminate && <span className="font-mono">{pct.toFixed(0)}%</span>}
        </div>
      )}
      <div
        className="h-2 w-full bg-soft-blue rounded-full overflow-hidden"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : Math.round(pct)}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${fill} ${indeterminate ? 'animate-pulse w-full opacity-60' : ''}`}
          style={indeterminate ? undefined : { width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
