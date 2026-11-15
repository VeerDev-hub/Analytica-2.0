import { useState } from 'react';
import { useChart } from '../../api/pipelineHooks.js';
import { Button, Card, ErrorBox, Select } from '../../components/ui.jsx';
import { Plot } from '../../components/Plot.jsx';

const KINDS = [
  ['histogram', 'Histogram', 'x'],
  ['bar', 'Bar', 'x'],
  ['box', 'Box plot', 'y'],
  ['violin', 'Violin', 'y'],
  ['scatter', 'Scatter', 'xy'],
  ['line', 'Line', 'xy'],
  ['pie', 'Pie', 'x'],
  ['heatmap', 'Correlation heatmap', ''],
];

/**
 * Chart builder: the API turns the spec into a Plotly figure (design D-12).
 * @param {{versionId: string, columns: any[]}} props
 */
export function ChartBuilder({ versionId, columns }) {
  const [spec, setSpec] = useState(/** @type {Record<string, any>} */ ({ kind: 'histogram', agg: 'count' }));
  const chart = useChart(versionId);
  const names = columns.map((c) => c.name).filter((n) => n !== '__split__');
  const kind = KINDS.find((k) => k[0] === spec.kind);
  const set = (/** @type {string} */ k) => (/** @type {any} */ e) => setSpec({ ...spec, [k]: e.target.value || undefined });

  const colSelect = (/** @type {string} */ k, /** @type {string} */ label, optional = false) => (
    <label className="text-xs text-muted">
      {label}
      <Select value={spec[k] ?? ''} onChange={set(k)} className="mt-0.5">
        <option value="">{optional ? '—' : 'Choose…'}</option>
        {names.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </Select>
    </label>
  );

  return (
    <Card title="Chart builder">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          <label className="text-xs text-muted">
            Chart
            <Select value={spec.kind} onChange={(e) => setSpec({ kind: e.target.value, agg: 'count' })} className="mt-0.5">
              {KINDS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </label>
          {kind?.[2] !== '' && colSelect('x', spec.kind === 'box' || spec.kind === 'violin' ? 'Group by (x)' : 'X', spec.kind === 'box' || spec.kind === 'violin')}
          {['xy', 'y'].includes(kind?.[2] ?? '') || ['bar', 'pie'].includes(spec.kind) ? colSelect('y', spec.kind === 'bar' || spec.kind === 'pie' ? 'Value (y)' : 'Y', ['bar', 'pie'].includes(spec.kind)) : null}
          {['bar', 'pie', 'line'].includes(spec.kind) && (
            <label className="text-xs text-muted">
              Aggregate
              <Select value={spec.agg} onChange={set('agg')} className="mt-0.5">
                {['count', 'sum', 'mean', 'median', 'min', 'max'].map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </Select>
            </label>
          )}
          {spec.kind !== 'heatmap' && spec.kind !== 'pie' && colSelect('color', 'Color by', true)}
          <div className="flex items-end">
            <Button variant="primary" className="w-full" loading={chart.isPending} onClick={() => chart.mutate(spec)}>
              Draw
            </Button>
          </div>
        </div>
        <ErrorBox error={chart.error} />
        {chart.data && (
          <>
            <Plot figure={chart.data} />
            {chart.data.meta?.sampled && <p className="text-xs text-muted">Showing a random sample of {chart.data.meta.rows.toLocaleString()} rows.</p>}
          </>
        )}
      </div>
    </Card>
  );
}
