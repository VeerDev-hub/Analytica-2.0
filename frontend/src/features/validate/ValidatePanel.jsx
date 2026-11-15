import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFetch } from '../../api/client.js';
import { isTerminal, keys, useJob } from '../../api/hooks.js';
import { Badge, Button, Card, ErrorBox, ProgressBar, Select, Spinner, fmt } from '../../components/ui.jsx';

const STATUS = /** @type {const} */ ({ pass: ['ok', '✓'], warn: ['warn', '!'], fail: ['danger', '✕'] });

const EXPORTS = [
  { kind: 'dataset', formats: ['csv', 'parquet', 'xlsx', 'npy'], label: 'Prepared dataset', hint: 'train / val / test files' },
  { kind: 'script', label: 'Python script', hint: 'pandas code for every step' },
  { kind: 'notebook', label: 'Jupyter notebook', hint: 'one cell per step' },
  { kind: 'pipeline', label: 'Pipeline JSON', hint: 'steps + learned values' },
  { kind: 'pytorch', label: 'PyTorch starter', hint: 'Dataset, DataLoader, model' },
  { kind: 'tensorflow', label: 'TensorFlow starter', hint: 'tf.data + Keras model' },
  { kind: 'report', label: 'HTML report', hint: 'quality + readiness' },
];

/** @param {{project: any, version: any, onFix: (stepType: string, params: object) => void}} props */
export function ReadinessCard({ project, version, onFix }) {
  const [framework, setFramework] = useState('sklearn');
  const readiness = useQuery({
    queryKey: [...keys.readiness(project.id), framework, version.id],
    queryFn: () => api.get(`/projects/${project.id}/readiness?framework=${framework}`),
  });
  const r = readiness.data;

  return (
      <Card
        title="ML readiness"
        actions={
          <Select aria-label="Framework" className="h-8 w-40" value={framework} onChange={(e) => setFramework(e.target.value)}>
            <option value="sklearn">scikit-learn</option>
            <option value="xgboost">XGBoost / trees</option>
            <option value="pytorch">PyTorch</option>
            <option value="tensorflow">TensorFlow</option>
          </Select>
        }
      >
        {readiness.isPending && <Spinner />}
        <ErrorBox error={readiness.error} />
        {r && (
          <div className="space-y-3">
            <div className="flex items-center gap-4">
              <div className={`text-3xl font-semibold tabular-nums ${r.ready ? 'text-ok' : 'text-warn'}`}>{r.score}%</div>
              <div className="text-sm">
                <div className="font-medium">{r.ready ? 'Ready to train' : 'Not ready yet'}</div>
                <div className="text-muted">
                  {fmt.int(r.rows)} rows · {r.features} features · target {r.target ?? '—'}
                </div>
              </div>
            </div>
            <ul className="divide-y divide-border rounded-md border border-border">
              {r.checks.map((/** @type {any} */ c) => {
                const [tone, icon] = STATUS[/** @type {'pass'} */ (c.status)];
                return (
                  <li key={c.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                    <Badge tone={tone}>{icon}</Badge>
                    <span className="font-medium">{c.label}</span>
                    <span className="min-w-0 flex-1 text-muted">{c.detail}</span>
                    {c.fix && c.status !== 'pass' && (
                      <button
                        className="rounded border border-border px-2 py-0.5 text-xs hover:border-accent hover:text-accent"
                        onClick={() => onFix(c.fix.step_type, c.fix.params)}
                      >
                        Fix: {c.fix.step_type.replaceAll('_', ' ')}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="text-xs text-muted">“Fix” opens the step in Clean or Features with a preview; nothing changes until you apply it.</p>
          </div>
        )}
      </Card>
  );
}

/** @param {{project: any}} props */
export function BaselineCard({ project }) {
  const [jobId, setJobId] = useState(/** @type {string | null} */ (null));
  const run = useMutation({ mutationFn: () => api.post(`/projects/${project.id}/baseline`), onSuccess: (r) => setJobId(r.job_id) });
  const job = useJob(jobId).data;
  const res = job?.status === 'succeeded' ? job.result : null;
  const metrics = res ? Object.keys(res.results[0]).filter((k) => k !== 'model') : [];
  return (
    <Card
      title="Baseline model"
      actions={
        <Button size="sm" variant="primary" disabled={!project.target_column} loading={run.isPending || (!!job && !isTerminal(job.status))} onClick={() => run.mutate()}>
          Train baseline
        </Button>
      }
    >
      {!project.target_column && <p className="text-sm text-muted">Choose a target column at the top of the page first.</p>}
      {project.target_column && !job && <p className="text-sm text-muted">Trains quick reference models on the training rows and scores them on validation rows, so you know what “good” looks like.</p>}
      <ErrorBox error={run.error} />
      {job && !isTerminal(job.status) && <ProgressBar value={job.progress} />}
      {job?.status === 'failed' && <ErrorBox error={{ message: job.error }} />}
      {res && (
        <div className="space-y-3">
          <p className="text-xs text-muted">
            {res.task} · trained on {fmt.int(res.train_rows)} rows · scored on {res.evaluated_on} ({fmt.int(res.eval_rows)} rows) · {res.features_used} features
            {res.features_dropped.length > 0 && ` · ignored non-numeric: ${res.features_dropped.slice(0, 5).join(', ')}`}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1 text-left font-normal">Model</th>
                  {metrics.map((m) => (
                    <th key={m} className={`py-1 text-right font-normal ${m === res.primary_metric ? 'text-fg' : ''}`}>
                      {m.replaceAll('_', ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {res.results.map((/** @type {any} */ row) => (
                  <tr key={row.model} className="border-t border-border">
                    <td className="py-1">{row.model}</td>
                    {metrics.map((m) => (
                      <td key={m} className="py-1 text-right tabular-nums">
                        {fmt.num(row[m], 3)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {res.importances.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium text-muted">Most useful features (permutation importance)</div>
              <ul className="space-y-0.5 text-sm">
                {res.importances.slice(0, 8).map((/** @type {any} */ f) => {
                  const max = Math.max(...res.importances.map((/** @type {any} */ x) => Math.abs(x.importance)), 1e-9);
                  return (
                    <li key={f.feature} className="relative overflow-hidden rounded px-2 py-0.5">
                      <span className="absolute inset-y-0 left-0 bg-info/15" style={{ width: `${(Math.max(f.importance, 0) / max) * 100}%` }} aria-hidden />
                      <span className="relative flex justify-between">
                        <span className="truncate">{f.feature}</span>
                        <span className="tabular-nums text-muted">{fmt.num(f.importance, 4)}</span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** @param {{project: any}} props */
export function ExportsCard({ project }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: keys.exports(project.id), queryFn: () => api.get(`/projects/${project.id}/exports`) });
  const [fmtSel, setFmtSel] = useState('csv');
  const [jobId, setJobId] = useState(/** @type {string | null} */ (null));
  const job = useJob(jobId).data;
  const create = useMutation({
    mutationFn: (/** @type {{kind: string, format?: string}} */ body) => api.post(`/projects/${project.id}/exports`, body),
    onSuccess: (r) => {
      setJobId(r.job_id);
      qc.invalidateQueries({ queryKey: keys.exports(project.id) });
    },
  });
  const jobStatus = job?.status;
  useEffect(() => {
    if (isTerminal(jobStatus)) qc.invalidateQueries({ queryKey: keys.exports(project.id) });
  }, [jobStatus, qc, project.id]);

  const download = async (/** @type {any} */ e) => {
    const res = await apiFetch(`/exports/${e.id}/download`, { raw: true });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      window.alert(body?.error?.message ?? 'Download failed');
      return;
    }
    const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? `${e.kind}.${e.format}`;
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card title="Export">
      <div className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {EXPORTS.map((x) => (
            <div key={x.kind} className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <div>
                <div className="font-medium">{x.label}</div>
                <div className="text-xs text-muted">{x.hint}</div>
              </div>
              <div className="mt-auto flex gap-2">
                {x.formats && (
                  <Select className="h-8" value={fmtSel} onChange={(e) => setFmtSel(e.target.value)} aria-label="Format">
                    {x.formats.map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </Select>
                )}
                <Button size="sm" className="shrink-0" onClick={() => create.mutate({ kind: x.kind, format: x.formats ? fmtSel : undefined })}>
                  Create
                </Button>
              </div>
            </div>
          ))}
        </div>
        <ErrorBox error={create.error} />
        {job && !isTerminal(job.status) && <ProgressBar value={job.progress} />}
        {job?.status === 'failed' && <ErrorBox error={{ message: job.error }} />}
        {list.data?.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-border text-sm">
            {list.data.map((/** @type {any} */ e) => (
              <li key={e.id} className="flex items-center gap-3 px-3 py-2">
                <span className="font-medium">{e.kind}</span>
                <Badge>{e.format}</Badge>
                <span className="text-xs text-muted">{new Date(e.created_at).toLocaleString()}</span>
                <span className="ml-auto">
                  {e.status === 'ready' ? (
                    <Button size="sm" onClick={() => download(e)}>
                      Download
                    </Button>
                  ) : (
                    <Badge tone={e.status === 'failed' ? 'danger' : 'warn'}>{e.status}</Badge>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted">Exports are kept for 7 days.</p>
      </div>
    </Card>
  );
}
