import { useMemo, useState } from 'react';
import { useAddStep, usePatchStep, usePreviewStep } from '../../api/pipelineHooks.js';
import { Badge, Button, Card, ErrorBox, fmt } from '../../components/ui.jsx';
import { useWorkspaceStore } from '../../store/workspace.js';
import { ParamField } from './ParamField.jsx';

/** Normalise ordinal "order" mapping values typed as "S, M, L" into arrays. */
function cleanParams(/** @type {any} */ spec, /** @type {Record<string, any>} */ params) {
  const out = { ...params };
  for (const p of spec.params) {
    if (p.name === 'order' && out.order) {
      out.order = Object.fromEntries(
        Object.entries(out.order).map(([k, v]) => [k, Array.isArray(v) ? v : String(v).split(',').map((s) => s.trim()).filter(Boolean)]),
      );
    }
    if (out[p.name] === '' || out[p.name] === undefined) delete out[p.name];
  }
  return out;
}

/**
 * Configure → preview on a 1,000-row sample → apply (design 4.3).
 * @param {{spec: any, project: any, pipelineId: string, columns: any[], initial?: object, editStepId?: string}} props
 */
export function StepEditor({ spec, project, pipelineId, columns, initial, editStepId }) {
  const [params, setParams] = useState(() => ({ ...(initial ?? {}) }));
  const preview = usePreviewStep(pipelineId);
  const add = useAddStep(project.id, pipelineId);
  const patch = usePatchStep(project.id);
  const close = useWorkspaceStore((s) => s.closeDraft);
  const fieldErrors = useMemo(() => {
    /** @type {Record<string, string>} */
    const m = {};
    const err = /** @type {any} */ (preview.error ?? add.error ?? patch.error);
    for (const d of err?.details ?? []) if (d.field) m[d.field] = d.message;
    return m;
  }, [preview.error, add.error, patch.error]);

  const body = { step_type: spec.step_type, params: cleanParams(spec, params) };
  const pv = preview.data;
  const apply = () => {
    if (editStepId) patch.mutate({ id: editStepId, params: body.params }, { onSuccess: close });
    else add.mutate(body, { onSuccess: close });
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          {editStepId ? 'Edit step: ' : ''}
          {spec.label}
          <Badge tone={spec.phase === 'post_split' ? 'info' : spec.phase === 'split' ? 'accent' : 'neutral'}>{spec.phase.replace('_', ' ')}</Badge>
        </span>
      }
      actions={
        <button onClick={close} className="rounded px-2 text-muted hover:bg-subtle" aria-label="Close editor">
          ✕
        </button>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-muted">{spec.explain}</p>
        {spec.warnings?.map((/** @type {string} */ w) => (
          <p key={w} className="text-xs text-warn">
            ⚠ {w}
          </p>
        ))}
        <div className="grid gap-4 md:grid-cols-2">
          {spec.params.map((/** @type {any} */ p) => (
            <div key={p.name} className={['columns', 'mapping'].includes(p.type) ? 'md:col-span-2' : ''}>
              <ParamField spec={p} value={/** @type {any} */ (params)[p.name]} onChange={(v) => setParams({ ...params, [p.name]: v })} columns={columns} error={fieldErrors[p.name]} />
            </div>
          ))}
        </div>
        <ErrorBox error={preview.error ?? add.error ?? patch.error} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button onClick={() => preview.mutate(body)} loading={preview.isPending}>
            Preview on sample
          </Button>
          <Button variant="primary" onClick={apply} loading={add.isPending || patch.isPending}>
            {editStepId ? 'Save and re-run' : 'Apply to full data'}
          </Button>
        </div>
        {pv && <PreviewResult pv={pv} />}
      </div>
    </Card>
  );
}

/** @param {{pv: any}} props */
function PreviewResult({ pv }) {
  const s = pv.summary;
  return (
    <div className="space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="font-medium">{pv.describe}</span>
        <span className="text-muted">
          Rows {fmt.int(s.rows_before)} → <b className="text-fg">{fmt.int(s.rows_after)}</b> (sample of {fmt.int(pv.sample_rows)})
        </span>
        <span className="text-muted">
          Columns {s.cols_before} → <b className="text-fg">{s.cols_after}</b>
        </span>
        {pv.split_counts && (
          <span className="text-muted">
            {Object.entries(pv.split_counts)
              .map(([k, v]) => `${k} ${v}`)
              .join(' · ')}
          </span>
        )}
      </div>
      {s.added_columns.length > 0 && <p className="text-xs text-ok">+ {s.added_columns.slice(0, 12).join(', ')}{s.added_columns.length > 12 ? ` +${s.added_columns.length - 12} more` : ''}</p>}
      {s.dropped_columns.length > 0 && <p className="text-xs text-danger">− {s.dropped_columns.join(', ')}</p>}
      {pv.warnings.map((/** @type {any} */ w, /** @type {number} */ i) => (
        <p key={i} className="text-xs text-warn">
          ⚠ {w.message}
        </p>
      ))}
      {pv.column_changes.length > 0 && (
        <table className="text-xs">
          <thead className="text-muted">
            <tr>
              <th className="pr-4 text-left font-normal">Column</th>
              <th className="pr-4 text-left font-normal">Missing</th>
              <th className="text-left font-normal">Type</th>
            </tr>
          </thead>
          <tbody>
            {pv.column_changes.map((/** @type {any} */ c) => (
              <tr key={c.column}>
                <td className="pr-4">{c.column}</td>
                <td className="pr-4 tabular-nums">
                  {c.missing_before} → {c.missing_after}
                </td>
                <td>
                  {c.type_before}
                  {c.type_after !== c.type_before && ` → ${c.type_after}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        <SampleTable title="Before" data={pv.before} />
        <SampleTable title="After" data={pv.after} />
      </div>
    </div>
  );
}

/** @param {{title: string, data: {columns: string[], rows: any[][]}}} props */
function SampleTable({ title, data }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 text-xs font-medium text-muted">{title}</div>
      <div className="max-h-64 overflow-auto rounded border border-border">
        <table className="grid-table w-max min-w-full border-separate border-spacing-0 text-xs">
          <thead className="sticky top-0 bg-subtle">
            <tr>
              {data.columns.map((c) => (
                <th key={c} className="px-2 py-1 text-left font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j} className="max-w-48 truncate px-2 py-0.5">
                    {v == null ? <span className="italic text-muted/60">null</span> : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
