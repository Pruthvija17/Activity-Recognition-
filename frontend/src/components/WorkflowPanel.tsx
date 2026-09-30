import { useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowLeftRight, ArrowUp, CheckCircle2, Pencil, Plus, Trash2, XCircle } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { ACTIVITIES, UNKNOWN, activityColor } from '../lib/activityColors';
import { formatDuration } from '../lib/format';
import { useApiData } from '../hooks/useApiData';
import { DataState, StatusNotice } from './StatusNotice';
import type { WorkflowDeviation, WorkflowStep } from '../types/api';

const STEP_ICON = {
  done: <CheckCircle2 className="w-4 h-4 text-brand-success" aria-label="done" />,
  missing: <XCircle className="w-4 h-4 text-brand-alert" aria-label="missing" />,
  out_of_order: <ArrowLeftRight className="w-4 h-4 text-brand-warning" aria-label="out of order" />,
} satisfies Record<WorkflowStep['status'], React.ReactNode>;

const STEP_TEXT: Record<WorkflowStep['status'], string> = {
  done: 'done',
  missing: 'missing',
  out_of_order: 'out of order',
};

const DEVIATION_TEXT: Record<WorkflowDeviation['type'], string> = {
  missing: 'Missing step',
  out_of_order: 'Out of order',
  unexpected: 'Unexpected activity',
  unknown: 'Unknown activity',
};

function TimeLink({ seconds, onSeek }: { seconds: number | null; onSeek: (s: number) => void }) {
  if (seconds == null) return <span className="text-brand-muted">—</span>;
  return (
    <button onClick={() => onSeek(seconds)} className="font-mono text-xs text-sky-blue hover:text-deep-blue underline">
      {formatDuration(seconds)}
    </button>
  );
}

export default function WorkflowPanel({
  experimentId,
  people,
  onSeek,
}: {
  experimentId: string;
  people: { person_id: string; label: string }[];
  onSeek: (seconds: number) => void;
}) {
  const [scope, setScope] = useState('');
  const [version, setVersion] = useState(0);
  const { data: wf, error, loading, reload } = useApiData(
    () => api.getWorkflow(experimentId, scope || undefined),
    `${experimentId}|${scope}|${version}`,
  );

  const [draft, setDraft] = useState<string[] | null>(null);
  const [adding, setAdding] = useState<string>(ACTIVITIES[0]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const move = (i: number, d: number) =>
    setDraft((s) => {
      if (!s || i + d < 0 || i + d >= s.length) return s;
      const next = [...s];
      [next[i], next[i + d]] = [next[i + d], next[i]];
      return next;
    });

  const save = async (reset = false) => {
    if (!draft && !reset) return;
    setSaving(true);
    setSaveError(null);
    try {
      if (reset) await api.resetWorkflow(experimentId);
      else await api.setWorkflow(experimentId, draft!);
      setDraft(null);
      setVersion((v) => v + 1);
    } catch (err) {
      setSaveError(toApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-soft-blue shadow-sm p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-bold text-deep-blue">Workflow</h3>
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="bg-ice-blue border border-soft-blue rounded-lg px-2 py-1 text-xs text-deep-blue"
          aria-label="Workflow scope"
        >
          <option value="">All people (combined)</option>
          {people.map((p) => (
            <option key={p.person_id} value={p.person_id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <DataState loading={loading} error={error} isEmpty={!wf} onRetry={reload}>
        {wf && !draft && (
          <>
            <StatusNotice tone={wf.is_compliant ? 'info' : 'warning'}>
              <span className="flex items-center gap-1.5 font-medium">
                {wf.is_compliant ? (
                  <CheckCircle2 className="w-4 h-4 text-brand-success" />
                ) : (
                  <AlertTriangle className="w-4 h-4" />
                )}
                {wf.message}
              </span>
              <span className="block text-xs mt-1">
                {wf.completed_steps}/{wf.expected_sequence.length} steps done
                {wf.next_expected_step && ` · next expected: ${wf.next_expected_step}`}
              </span>
            </StatusNotice>

            <ol className="space-y-1.5">
              {wf.steps.map((s) => (
                <li key={s.index} className="flex items-center gap-2 text-sm">
                  {STEP_ICON[s.status]}
                  <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: activityColor(s.activity) }} />
                  <span className="flex-1 text-brand-primary">
                    {s.index + 1}. {s.activity}
                  </span>
                  <span className="text-xs text-brand-muted">{STEP_TEXT[s.status]}</span>
                  <TimeLink seconds={s.time} onSeek={onSeek} />
                </li>
              ))}
            </ol>

            {wf.deviations.length > 0 && (
              <div>
                <div className="text-xs font-bold text-brand-secondary mb-1">Deviations</div>
                <ul className="divide-y divide-soft-blue text-xs">
                  {wf.deviations.map((d, i) => (
                    <li key={i} className="py-1.5 flex items-start gap-2">
                      <span className="font-semibold text-brand-primary whitespace-nowrap">{DEVIATION_TEXT[d.type]}</span>
                      <span className="flex-1 text-brand-secondary">
                        {d.detail}
                        {d.person && ` (${d.person})`}
                      </span>
                      <TimeLink seconds={d.time} onSeek={onSeek} />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex items-center justify-between pt-1">
              <span className="text-xs text-brand-muted">
                {wf.configured ? 'Custom workflow for this experiment' : 'Default workflow (not configured yet)'}
              </span>
              <button
                onClick={() => setDraft([...wf.expected_sequence])}
                className="flex items-center gap-1 text-xs font-bold text-sky-blue hover:text-deep-blue"
              >
                <Pencil className="w-3.5 h-3.5" /> Edit steps
              </button>
            </div>
          </>
        )}

        {draft && (
          <div className="space-y-3">
            <ol className="space-y-1.5">
              {draft.map((step, i) => (
                <li key={`${step}-${i}`} className="flex items-center gap-2 text-sm bg-ice-blue/60 rounded-lg px-2 py-1">
                  <span className="w-5 text-xs text-brand-muted">{i + 1}.</span>
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(step) }} />
                  <span className="flex-1 text-brand-primary">{step}</span>
                  <button onClick={() => move(i, -1)} disabled={i === 0} className="p-1 disabled:opacity-30" aria-label="Move up">
                    <ArrowUp className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => move(i, 1)}
                    disabled={i === draft.length - 1}
                    className="p-1 disabled:opacity-30"
                    aria-label="Move down"
                  >
                    <ArrowDown className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setDraft(draft.filter((_, k) => k !== i))}
                    className="p-1 text-brand-alert"
                    aria-label="Remove step"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </li>
              ))}
            </ol>
            <div className="flex gap-2">
              <select
                value={adding}
                onChange={(e) => setAdding(e.target.value)}
                className="flex-1 bg-white border border-soft-blue rounded-lg px-2 py-1.5 text-xs"
                aria-label="Activity to add"
              >
                {[...ACTIVITIES, UNKNOWN].map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </select>
              <button
                onClick={() => setDraft([...draft, adding])}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-soft-blue text-xs font-bold text-deep-blue hover:bg-ice-blue"
              >
                <Plus className="w-3.5 h-3.5" /> Add step
              </button>
            </div>
            {saveError && <StatusNotice tone="error">{saveError}</StatusNotice>}
            <div className="flex flex-wrap gap-2 justify-end">
              <button onClick={() => save(true)} disabled={saving} className="px-3 py-1.5 text-xs font-bold text-brand-secondary hover:underline">
                Reset to default
              </button>
              <button onClick={() => setDraft(null)} disabled={saving} className="px-3 py-1.5 text-xs font-bold text-brand-secondary">
                Cancel
              </button>
              <button
                onClick={() => save()}
                disabled={saving || draft.length === 0}
                className="px-4 py-1.5 rounded-lg text-xs font-bold text-white bg-sky-blue hover:bg-[#2CA1D9] disabled:opacity-50"
              >
                Save workflow
              </button>
            </div>
          </div>
        )}
      </DataState>
    </div>
  );
}
