import { useMemo, useState } from 'react';
import { DataGrid } from '../datasets/DataGrid.jsx';
import { ColumnInspector } from '../datasets/ColumnInspector.jsx';
import { ColumnRelation } from '../eda/ColumnRelation.jsx';
import { SectionHeader, useProjectCtx } from './ProjectLayout.jsx';

export function DataPage() {
  const ctx = useProjectCtx();
  const [selected, setSelected] = useState(/** @type {string | null} */ (null));
  const profile = useMemo(() => ctx.overview?.columns.find((/** @type {any} */ c) => c.name === selected), [ctx.overview, selected]);

  return (
    <div>
      <SectionHeader section="data" ctx={ctx} showTarget />
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          <DataGrid versionId={ctx.version.id} profiles={ctx.overview?.columns ?? []} onSelectColumn={setSelected} selected={selected} />
        </div>
        {profile && (
          <div className="fixed inset-y-0 right-0 z-40 w-full max-w-sm overflow-y-auto border-l border-border bg-bg p-3 shadow-2xl xl:static xl:z-auto xl:max-h-[calc(100vh-150px)] xl:w-80 xl:border-0 xl:p-0 xl:shadow-none">
            <ColumnInspector
              key={`${profile.id}:${profile.description ?? ''}`}
              profile={profile}
              alerts={ctx.overview.alerts.filter((/** @type {any} */ a) => a.column === profile.name)}
              onClose={() => setSelected(null)}
            >
              <ColumnRelation versionId={ctx.version.id} name={profile.name} />
              <QuickActions ctx={ctx} p={profile} />
            </ColumnInspector>
          </div>
        )}
      </div>
    </div>
  );
}

/** @param {{ctx: any, p: any}} props */
function QuickActions({ ctx, p }) {
  /** @type {[string, string, object, boolean?][]} */
  const actions = [
    ...(p.missing_count > 0 ? [['Fill missing', 'impute', { columns: [p.name], strategy: p.semantic_type === 'numeric' ? 'median' : 'most_frequent' }]] : []),
    ['Change type', 'change_type', { columns: [p.name], to: p.semantic_type === 'numeric' ? 'text' : 'numeric' }],
    ...(['nominal', 'boolean'].includes(p.semantic_type) ? [['One-hot encode', 'one_hot', { columns: [p.name] }]] : []),
    ...(p.semantic_type === 'numeric' ? [['Handle outliers', 'outliers', { columns: [p.name] }]] : []),
    ...(p.semantic_type === 'datetime' ? [['Date parts', 'datetime_features', { columns: [p.name] }]] : []),
    ['Rename', 'rename_columns', { mapping: { [p.name]: p.name } }],
    ['Drop', 'drop_columns', { columns: [p.name] }, true],
  ];
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted">Quick steps (open in Clean / Features with a preview)</div>
      <div className="flex flex-wrap gap-1.5">
        {actions.map(([label, type, params, danger]) => (
          <button
            key={label}
            onClick={() => ctx.openStep(type, params)}
            className={`rounded border border-border px-2 py-0.5 text-xs hover:border-accent ${danger ? 'hover:text-danger' : 'hover:text-accent'}`}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
