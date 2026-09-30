import { Brain, Download } from 'lucide-react';
import { api } from '../lib/api';
import { activityColor } from '../lib/activityColors';
import { useApiData } from '../hooks/useApiData';
import { DataState, StatusNotice } from './StatusNotice';

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`);

/** Which activity engine is active, and how much reviewed data exists to train a model. */
export default function TrainingPanel() {
  const { data: t, error, loading, reload } = useApiData(() => api.getTrainingSummary());

  return (
    <div className="bg-white p-6 rounded-2xl border border-soft-blue shadow-sm space-y-4 md:col-span-2">
      <div className="flex items-center gap-3 border-b border-soft-blue pb-4">
        <Brain className="w-5 h-5 text-sky-blue" />
        <h3 className="text-lg font-bold text-deep-blue">Activity Model &amp; Training Data</h3>
      </div>

      <DataState loading={loading} error={error} isEmpty={!t} onRetry={reload}>
        {t && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 text-sm">
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-brand-secondary">Engine in use</span>
                <span className="font-bold text-amber-700 text-right">{t.engine}</span>
              </div>
              {t.trained_model ? (
                <div className="space-y-1.5 bg-ice-blue/60 rounded-xl p-3 text-xs">
                  <div className="flex justify-between"><span>Trained</span><span>{t.trained_model.trained_at.slice(0, 10)}</span></div>
                  <div className="flex justify-between"><span>Test accuracy</span><span className="font-bold">{pct(t.trained_model.metrics.test_accuracy)}</span></div>
                  <div className="flex justify-between"><span>Test macro F1</span><span className="font-bold">{pct(t.trained_model.metrics.test_macro_f1)}</span></div>
                  <div className="flex justify-between">
                    <span>Data split</span>
                    <span>
                      {t.trained_model.data.split} ({t.trained_model.data.train_videos.length}/
                      {t.trained_model.data.val_videos.length}/{t.trained_model.data.test_videos.length} videos)
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-brand-secondary">
                  No trained model yet: activities come from transparent pose rules. A model trained on your own
                  labelled footage is used automatically once it exists (see docs/TRAINING.md).
                </p>
              )}
              {t.model_error && <StatusNotice tone="error">{t.model_error}</StatusNotice>}
              <div className="bg-slate-50 rounded-lg p-3 font-mono text-[11px] text-brand-primary space-y-1">
                <div className="text-brand-muted"># from the backend folder</div>
                <div>..\.venv\Scripts\python -m training.labels export --out data\labels.csv</div>
                <div>..\.venv\Scripts\python -m training.train --labels data\labels.csv</div>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-brand-primary">
                  Reviewed segments ({t.labelled_segments} from {t.videos} video{t.videos === 1 ? '' : 's'})
                </span>
                <a href={api.trainingLabelsUrl()} className="flex items-center gap-1 text-xs font-bold text-sky-blue hover:text-deep-blue">
                  <Download className="w-3.5 h-3.5" /> labels CSV
                </a>
              </div>
              <table className="w-full text-xs">
                <tbody className="divide-y divide-soft-blue">
                  {t.per_activity.map((a) => {
                    const target = t.recommended_segments_per_activity;
                    const known = a.activity !== 'Unknown';
                    return (
                      <tr key={a.activity}>
                        <td className="py-1.5">
                          <span className="inline-flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: activityColor(a.activity) }} />
                            {a.activity}
                          </span>
                        </td>
                        <td className="py-1.5 w-28">
                          {known && (
                            <div className="h-1.5 bg-soft-blue rounded-full overflow-hidden">
                              <div className="h-full bg-sky-blue" style={{ width: `${Math.min(100, (a.segments / target) * 100)}%` }} />
                            </div>
                          )}
                        </td>
                        <td className={`py-1.5 pl-3 text-right ${known && a.segments < target ? 'text-brand-warning font-semibold' : 'text-brand-secondary'}`}>
                          {a.segments}
                          {known ? ` / ${target}` : ''}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-xs text-brand-muted mt-2">
                Every event an operator confirms or reclassifies in the Review Queue becomes a training label.
                {t.ready
                  ? ' Enough data to train.'
                  : ` Needed before training: at least ${t.min_videos} videos and ${t.recommended_segments_per_activity} segments per activity.`}
              </p>
            </div>
          </div>
        )}
      </DataState>
    </div>
  );
}
