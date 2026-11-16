import { useSearchParams } from 'react-router-dom';
import { Badge, Card, SEVERITY_TONE, Spinner, Stat, TYPE_TONE, fmt } from '../../components/ui.jsx';
import { Icon } from '../../components/icons.jsx';
import { MiniHistogram, TopValues } from '../eda/MiniCharts.jsx';
import { ChartBuilder } from '../eda/ChartBuilder.jsx';
import { SectionHeader, useProjectCtx } from './ProjectLayout.jsx';

const VIEWS = [
  { id: 'summary', label: 'Summary', icon: 'summary' },
  { id: 'columns', label: 'Columns', icon: 'columns' },
  { id: 'charts', label: 'Charts', icon: 'chart' },
];

/** @param {{value: string, onChange: (v: string) => void, options: {id: string, label: string, icon?: any}[]}} props */
export function Segmented({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-xl border border-border bg-surface shadow-card p-0.5" role="tablist">
      {options.map((o) => (
        <button
          key={o.id}
          role="tab"
          aria-selected={value === o.id}
          onClick={() => onChange(o.id)}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${value === o.id ? 'bg-accent/10 font-medium text-accent' : 'text-muted hover:text-fg'}`}
        >
          {o.icon && <Icon name={o.icon} size={15} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ExplorePage() {
  const ctx = useProjectCtx();
  const [params, setParams] = useSearchParams();
  const view = params.get('view') ?? 'summary';
  const ov = ctx.overview;

  return (
    <div>
      <SectionHeader section="explore" ctx={ctx} showTarget />
      <div className="mb-4">
        <Segmented value={view} onChange={(v) => setParams({ view: v }, { replace: true })} options={VIEWS} />
      </div>
      {!ov ? (
        <Spinner />
      ) : view === 'summary' ? (
        <Summary ov={ov} ctx={ctx} />
      ) : view === 'columns' ? (
        <Columns ov={ov} />
      ) : (
        <ChartBuilder versionId={ctx.version.id} columns={ov.columns} />
      )}
    </div>
  );
}

function Summary({ ov, ctx }) {
  const s = ov.summary ?? {};
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <div className="space-y-4 xl:col-span-1">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Rows" value={fmt.int(s.row_count)} />
          <Stat label="Columns" value={fmt.int(s.column_count)} />
          <Stat label="Missing cells" value={fmt.pct(s.missing_pct)} sub={`${fmt.int(s.missing_cells)} cells`} />
          <Stat label="Duplicate rows" value={fmt.int(s.duplicate_rows)} sub={fmt.pct(s.duplicate_pct)} />
        </div>
        <Card title="Column types">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(s.type_counts ?? {}).map(([t, n]) => (
              <Badge key={t} tone={TYPE_TONE[t]}>
                {n} {t}
              </Badge>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">
            Types are detected from the values: <b>id</b> columns are almost all unique, <b>nominal</b> are categories, <b>text</b> is free writing.
          </p>
        </Card>
        {ov.load_notes?.length > 0 && (
          <Card title="Changes made while loading">
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted">
              {ov.load_notes.map((/** @type {string} */ n, /** @type {number} */ i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </Card>
        )}
      </div>
      <Card title={`Quality alerts · ${ov.alerts.length}`} padded={false} className="xl:col-span-2">
        {ov.alerts.length === 0 ? (
          <p className="p-4 text-sm text-muted">No issues found. Nice data.</p>
        ) : (
          <ul className="max-h-[calc(100vh-260px)] divide-y divide-border overflow-y-auto">
            {ov.alerts.map((/** @type {any} */ a, /** @type {number} */ i) => (
              <li key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <Badge tone={SEVERITY_TONE[/** @type {'high'} */ (a.severity)]}>{a.severity}</Badge>
                <span className="min-w-0 flex-1">
                  {a.column && <b className="mr-1">{a.column}</b>}
                  <span className="text-muted">{a.message.replace(`'${a.column}' `, '')}</span>
                </span>
                {a.suggestion && (
                  <button
                    className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:border-accent hover:text-accent"
                    onClick={() => ctx.openStep(a.suggestion.step_type, a.suggestion.params)}
                    title="Opens the step with a preview; nothing changes until you apply it"
                  >
                    Fix: {a.suggestion.step_type.replaceAll('_', ' ')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Columns({ ov }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {ov.columns
        .filter((/** @type {any} */ c) => c.name !== '__split__')
        .map((/** @type {any} */ c) => (
          <div key={c.id} className="rounded-xl border border-border bg-surface shadow-card p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium" title={c.name}>
                {c.name}
              </span>
              <Badge tone={TYPE_TONE[c.semantic_type]}>{c.semantic_type}</Badge>
            </div>
            <div className="mb-2 mt-0.5 text-xs text-muted">
              {fmt.pct(c.stats?.missing_pct)} missing · {fmt.int(c.unique_count)} unique
              {c.stats?.mean !== undefined && ` · mean ${fmt.num(c.stats.mean)}`}
            </div>
            {c.stats?.histogram ? <MiniHistogram histogram={c.stats.histogram} /> : c.stats?.top_values ? <TopValues values={c.stats.top_values} total={c.stats.count} limit={4} /> : null}
          </div>
        ))}
    </div>
  );
}
