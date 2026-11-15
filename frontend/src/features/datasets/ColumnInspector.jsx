import { useState } from 'react';
import { usePatchColumn } from '../../api/hooks.js';
import { Badge, Button, TYPE_TONE, fmt, inputClass } from '../../components/ui.jsx';
import { MiniHistogram, TopValues } from '../eda/MiniCharts.jsx';

/**
 * Side panel describing one column: stats, distribution, notes and flags.
 * Give it `key={profile.id}` so the description draft resets when the column changes.
 * @param {{profile: any, alerts: any[], onClose: () => void, children?: import('react').ReactNode}} props
 */
export function ColumnInspector({ profile, alerts, onClose, children }) {
  const patch = usePatchColumn();
  const [desc, setDesc] = useState(profile.description ?? '');
  const s = profile.stats ?? {};
  const isNum = s.mean !== undefined;

  /** @type {[string, any][]} */
  const rows = isNum
    ? [
        ['Mean', fmt.num(s.mean)],
        ['Std dev', fmt.num(s.std)],
        ['Min', fmt.num(s.min)],
        ['Q1', fmt.num(s.q1)],
        ['Median', fmt.num(s.median)],
        ['Q3', fmt.num(s.q3)],
        ['Max', fmt.num(s.max)],
        ['Skew', fmt.num(s.skew, 2)],
        ['Zeros', fmt.int(s.zeros)],
        ['Outliers (1.5×IQR)', fmt.int(s.outliers_iqr)],
      ]
    : [
        ...(s.min !== undefined ? [['Earliest', s.min], ['Latest', s.max]] : []),
        ...(s.avg_length !== undefined ? [['Avg length', fmt.num(s.avg_length, 1)]] : []),
      ];

  return (
    <aside className="flex w-full flex-col gap-4 rounded-lg border border-border bg-surface p-4 lg:w-80" aria-label={`Column ${profile.name}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-semibold" title={profile.name}>
            {profile.name}
          </h3>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone={TYPE_TONE[profile.semantic_type]}>{profile.semantic_type}</Badge>
            <Badge>{profile.dtype}</Badge>
            {profile.is_target && <Badge tone="accent">target</Badge>}
            {profile.is_private && <Badge tone="danger">private</Badge>}
          </div>
        </div>
        <button onClick={onClose} className="rounded px-1.5 text-muted hover:bg-subtle" aria-label="Close inspector">
          ✕
        </button>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded bg-subtle p-2">
          <dt className="text-[11px] text-muted">Missing</dt>
          <dd className="text-sm font-semibold tabular-nums">{fmt.pct(s.missing_pct)}</dd>
        </div>
        <div className="rounded bg-subtle p-2">
          <dt className="text-[11px] text-muted">Unique</dt>
          <dd className="text-sm font-semibold tabular-nums">{fmt.int(profile.unique_count)}</dd>
        </div>
        <div className="rounded bg-subtle p-2">
          <dt className="text-[11px] text-muted">Filled</dt>
          <dd className="text-sm font-semibold tabular-nums">{fmt.int(s.count)}</dd>
        </div>
      </dl>

      {s.histogram && <MiniHistogram histogram={s.histogram} />}
      {s.top_values && <TopValues values={s.top_values} total={s.count} />}

      {rows.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="text-right tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {alerts.length > 0 && (
        <ul className="space-y-1.5 text-sm">
          {alerts.map((a, i) => (
            <li key={i} className="rounded border border-border px-2 py-1.5">
              <Badge tone={a.severity === 'high' ? 'danger' : a.severity === 'medium' ? 'warn' : 'info'}>{a.severity}</Badge>{' '}
              {a.message}
            </li>
          ))}
        </ul>
      )}

      {children}

      <div className="space-y-2 border-t border-border pt-3">
        <label className="block text-sm font-medium" htmlFor="col-desc">
          Description <span className="font-normal text-muted">(used by chat)</span>
        </label>
        <textarea id="col-desc" className={`${inputClass} h-20 w-full py-2`} value={desc} onChange={(e) => setDesc(e.target.value)} />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={profile.is_private}
              onChange={(e) => patch.mutate({ id: profile.id, body: { is_private: e.target.checked } })}
            />
            Private (masked from chat)
          </label>
          <Button size="sm" loading={patch.isPending} disabled={desc === (profile.description ?? '')} onClick={() => patch.mutate({ id: profile.id, body: { description: desc } })}>
            Save
          </Button>
        </div>
      </div>
    </aside>
  );
}
