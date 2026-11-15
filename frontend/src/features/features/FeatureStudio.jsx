import { useState } from 'react';
import { usePipeline, useSetSplit } from '../../api/pipelineHooks.js';
import { Button, Card, ErrorBox, Select } from '../../components/ui.jsx';

/** @param {{project: any, overview: any, onDone?: () => void}} props */
export function SplitCard({ project, overview, onDone }) {
  const { data: pl } = usePipeline(project.id);
  const setSplit = useSetSplit(project.id, pl?.id);
  const current = pl?.split_config;
  const [cfg, setCfg] = useState(
    /** @type {Record<string, any>} */ ({
      method: project.target_column ? 'stratified' : 'random',
      ratios: [0.7, 0.15, 0.15],
      seed: 42,
    }),
  );
  const cols = (overview?.columns ?? []).filter((/** @type {any} */ c) => c.name !== '__split__');
  const pct = (/** @type {number} */ i) => Math.round(cfg.ratios[i] * 100);
  const setPct = (/** @type {number} */ i, /** @type {string} */ v) => {
    const r = [...cfg.ratios];
    r[i] = Number(v) / 100;
    setCfg({ ...cfg, ratios: r });
  };
  const sumOk = Math.abs(cfg.ratios.reduce((/** @type {number} */ a, /** @type {number} */ b) => a + b, 0) - 1) < 0.001;

  return (
    <Card title="Train / validation / test split">
      <div className="space-y-3">
        <p className="text-sm text-muted">
          Every step after the split learns only from training rows, so your test score stays honest.
          {current && (
            <span className="ml-1 text-ok">
              Current: {current.method} {Math.round(current.ratios?.[0] * 100)}/{Math.round(current.ratios?.[1] * 100)}/{Math.round(current.ratios?.[2] * 100)}.
            </span>
          )}
        </p>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <label className="col-span-2 text-xs text-muted">
            Method
            <Select className="mt-0.5" value={cfg.method} onChange={(e) => setCfg({ ...cfg, method: e.target.value })}>
              <option value="stratified">Stratified (keeps class shares)</option>
              <option value="random">Random</option>
              <option value="time">Time-ordered (no future in train)</option>
              <option value="group">Grouped (no group in two parts)</option>
            </Select>
          </label>
          {['Train', 'Validation', 'Test'].map((l, i) => (
            <label key={l} className="text-xs text-muted">
              {l} %
              <input className="mt-0.5 h-9 w-full rounded-md border border-border bg-surface px-2 text-sm" type="number" min={0} max={100} value={pct(i)} onChange={(e) => setPct(i, e.target.value)} />
            </label>
          ))}
          {cfg.method === 'stratified' && (
            <label className="col-span-2 text-xs text-muted">
              Stratify by
              <Select className="mt-0.5" value={cfg.stratify_by ?? ''} onChange={(e) => setCfg({ ...cfg, stratify_by: e.target.value || undefined })}>
                <option value="">{project.target_column ? `Target (${project.target_column})` : 'Choose…'}</option>
                {cols.map((/** @type {any} */ c) => (
                  <option key={c.name}>{c.name}</option>
                ))}
              </Select>
            </label>
          )}
          {cfg.method === 'time' && (
            <label className="col-span-2 text-xs text-muted">
              Time column
              <Select className="mt-0.5" value={cfg.time_column ?? ''} onChange={(e) => setCfg({ ...cfg, time_column: e.target.value || undefined })}>
                <option value="">Choose…</option>
                {cols.map((/** @type {any} */ c) => (
                  <option key={c.name}>{c.name}</option>
                ))}
              </Select>
            </label>
          )}
          {cfg.method === 'group' && (
            <label className="col-span-2 text-xs text-muted">
              Group column
              <Select className="mt-0.5" value={cfg.group_column ?? ''} onChange={(e) => setCfg({ ...cfg, group_column: e.target.value || undefined })}>
                <option value="">Choose…</option>
                {cols.map((/** @type {any} */ c) => (
                  <option key={c.name}>{c.name}</option>
                ))}
              </Select>
            </label>
          )}
        </div>
        {!sumOk && <p className="text-xs text-danger">The three shares must add up to 100%.</p>}
        <ErrorBox error={setSplit.error} />
        <div className="flex justify-end">
          <Button variant="primary" disabled={!sumOk || !pl} loading={setSplit.isPending} onClick={() => setSplit.mutate(cfg, { onSuccess: onDone })}>
            {current ? 'Update split and re-run' : 'Split data'}
          </Button>
        </div>
      </div>
    </Card>
  );
}
