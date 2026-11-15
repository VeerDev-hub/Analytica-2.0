import { useMemo, useState } from 'react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { useRows } from '../../api/hooks.js';
import { Badge, Button, ErrorBox, Input, Select, Spinner, TYPE_TONE, fmt } from '../../components/ui.jsx';

const PAGE = 100;
const OPS = [
  ['contains', 'contains'],
  ['eq', '='],
  ['neq', '≠'],
  ['gt', '>'],
  ['gte', '≥'],
  ['lt', '<'],
  ['lte', '≤'],
  ['is_null', 'is empty'],
  ['not_null', 'is not empty'],
];

/**
 * Server-paged grid: the browser only ever holds one page (design: 100k+ rows lazily).
 * @param {{versionId: string, profiles: any[], onSelectColumn?: (name: string) => void, selected?: string | null, height?: string}} props
 */
export function DataGrid({ versionId, profiles, onSelectColumn, selected, height = 'calc(100vh - 260px)' }) {
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState(/** @type {string | undefined} */ (undefined));
  const [filters, setFilters] = useState(/** @type {{column: string, op: string, value?: string}[]} */ ([]));
  const [draft, setDraft] = useState({ column: '', op: 'contains', value: '' });
  const q = useMemo(() => ({ offset, limit: PAGE, sort, filter: filters }), [offset, sort, filters]);
  const { data, isFetching, error } = useRows(versionId, q);
  const byName = useMemo(() => Object.fromEntries((profiles ?? []).map((p) => [p.name, p])), [profiles]);

  const columns = useMemo(
    () =>
      (data?.columns ?? []).map((/** @type {{name: string}} */ c, /** @type {number} */ i) => ({
        id: c.name,
        accessorFn: (/** @type {any[]} */ row) => row[i],
        header: c.name,
      })),
    [data?.columns],
  );
  const rows = data?.rows ?? [];
  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel(), manualPagination: true, manualSorting: true });

  const toggleSort = (/** @type {string} */ name) => {
    setOffset(0);
    if (sort === `${name}:asc`) setSort(`${name}:desc`);
    else if (sort === `${name}:desc`) setSort(undefined);
    else setSort(`${name}:asc`);
  };

  const addFilter = () => {
    if (!draft.column) return;
    setFilters([...filters, { ...draft }]);
    setDraft({ ...draft, value: '' });
    setOffset(0);
  };

  const total = data?.total ?? 0;
  const pageEnd = Math.min(offset + PAGE, total);

  return (
    <div className="flex min-h-0 flex-col rounded-lg border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <Select aria-label="Filter column" className="w-44" value={draft.column} onChange={(e) => setDraft({ ...draft, column: e.target.value })}>
          <option value="">Filter column…</option>
          {(data?.columns ?? []).map((/** @type {any} */ c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </Select>
        <Select aria-label="Operator" className="w-32" value={draft.op} onChange={(e) => setDraft({ ...draft, op: e.target.value })}>
          {OPS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
        {!['is_null', 'not_null'].includes(draft.op) && (
          <Input
            aria-label="Value"
            className="w-44"
            placeholder="value"
            value={draft.value}
            onChange={(e) => setDraft({ ...draft, value: e.target.value })}
            onKeyDown={(e) => e.key === 'Enter' && addFilter()}
          />
        )}
        <Button size="sm" onClick={addFilter} disabled={!draft.column}>
          Add filter
        </Button>
        {filters.map((f, i) => (
          <button
            key={i}
            className="rounded-full border border-border bg-subtle px-2.5 py-0.5 text-xs hover:border-danger"
            onClick={() => {
              setFilters(filters.filter((_, j) => j !== i));
              setOffset(0);
            }}
            title="Remove filter"
          >
            {f.column} {OPS.find(([v]) => v === f.op)?.[1]} {f.value} ✕
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-sm text-muted">
          {isFetching && <Spinner size={14} />}
          <span className="tabular-nums">
            {total ? `${fmt.int(offset + 1)}–${fmt.int(pageEnd)} of ${fmt.int(total)}` : '0 rows'}
          </span>
          <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} aria-label="Previous page">
            ‹
          </Button>
          <Button size="sm" variant="ghost" disabled={pageEnd >= total} onClick={() => setOffset(offset + PAGE)} aria-label="Next page">
            ›
          </Button>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="overflow-auto" style={{ height }}>
        <table className="grid-table w-max min-w-full border-separate border-spacing-0 text-sm">
          <thead className="sticky top-0 z-10 bg-surface">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                <th className="sticky left-0 z-20 w-14 bg-subtle px-2 py-1.5 text-right text-xs font-normal text-muted">#</th>
                {hg.headers.map((h) => {
                  const name = h.column.id;
                  const p = byName[name];
                  const dir = sort === `${name}:asc` ? '↑' : sort === `${name}:desc` ? '↓' : '';
                  return (
                    <th
                      key={h.id}
                      className={`min-w-32 max-w-72 bg-subtle px-2 py-1.5 text-left align-top font-medium ${selected === name ? 'outline outline-2 -outline-offset-2 outline-accent' : ''}`}
                    >
                      <button className="flex w-full items-center gap-1 truncate text-left hover:text-accent" onClick={() => toggleSort(name)} title="Sort">
                        <span className="truncate">{flexRender(h.column.columnDef.header, h.getContext())}</span>
                        <span className="text-accent">{dir}</span>
                      </button>
                      {p && (
                        <button className="mt-0.5 flex items-center gap-1" onClick={() => onSelectColumn?.(name)} title="Inspect column">
                          <Badge tone={TYPE_TONE[p.semantic_type]}>{p.semantic_type}</Badge>
                          {p.missing_count > 0 && <span className="text-[11px] font-normal text-warn">{fmt.pct(p.stats?.missing_pct, 0)} empty</span>}
                        </button>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r, i) => (
              <tr key={r.id} className="hover:bg-subtle/60">
                <td className="sticky left-0 bg-surface px-2 py-1 text-right text-xs tabular-nums text-muted">{(data?.row_ids?.[i] ?? 0) + 1}</td>
                {r.getVisibleCells().map((c) => {
                  const v = c.getValue();
                  return (
                    <td key={c.id} className={`max-w-72 truncate px-2 py-1 ${typeof v === 'number' ? 'text-right tabular-nums' : ''}`} title={v == null ? '' : String(v)}>
                      {v == null ? <span className="text-muted/60 italic">null</span> : String(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {!isFetching && rows.length === 0 && <p className="p-6 text-center text-sm text-muted">No rows match.</p>}
      </div>
    </div>
  );
}
