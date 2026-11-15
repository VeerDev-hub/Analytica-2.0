import { useState } from 'react';
import { Badge, Input, Select, TYPE_TONE, inputClass } from '../../components/ui.jsx';

const FILTER_TYPES = {
  numeric: ['numeric'],
  categorical: ['nominal', 'ordinal', 'boolean'],
  datetime: ['datetime'],
  text: ['text', 'nominal'],
};
const TOKENS = [
  ['@numeric', 'all numeric'],
  ['@categorical', 'all categorical'],
  ['@datetime', 'all dates'],
  ['@text', 'all text'],
];

/**
 * One form control generated from a catalog param spec.
 * @param {{spec: any, value: any, onChange: (v: any) => void, columns: {name: string, semantic_type: string}[], error?: string}} props
 */
export function ParamField({ spec, value, onChange, columns, error }) {
  const id = `p-${spec.name}`;
  const label = (
    <label htmlFor={id} className="block text-sm font-medium">
      {spec.label}
      {spec.required && <span className="text-danger"> *</span>}
    </label>
  );
  const help = spec.help && <p className="text-xs text-muted">{spec.help}</p>;
  const err = error && <p className="text-xs text-danger">{error}</p>;

  let control;
  switch (spec.type) {
    case 'columns':
      control = <ColumnsPicker id={id} value={value ?? []} onChange={onChange} columns={columns} filter={spec.column_filter} />;
      break;
    case 'column':
      control = (
        <Select id={id} value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">—</option>
          {sortByFilter(columns, spec.column_filter).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name} ({c.semantic_type})
            </option>
          ))}
        </Select>
      );
      break;
    case 'select':
      control = (
        <Select id={id} value={value ?? spec.default ?? ''} onChange={(e) => onChange(e.target.value)}>
          {spec.options.map((/** @type {string} */ o) => (
            <option key={o} value={o}>
              {o.replaceAll('_', ' ')}
            </option>
          ))}
        </Select>
      );
      break;
    case 'multiselect':
      control = (
        <div id={id} className="flex flex-wrap gap-1.5">
          {spec.options.map((/** @type {string} */ o) => {
            const on = (value ?? spec.default ?? []).includes(o);
            return (
              <button
                type="button"
                key={o}
                onClick={() => {
                  const cur = value ?? spec.default ?? [];
                  onChange(on ? cur.filter((/** @type {string} */ x) => x !== o) : [...cur, o]);
                }}
                className={`rounded-full border px-2.5 py-0.5 text-xs ${on ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-fg'}`}
                aria-pressed={on}
              >
                {o.replaceAll('_', ' ')}
              </button>
            );
          })}
        </div>
      );
      break;
    case 'number':
    case 'integer':
      control = (
        <Input
          id={id}
          type="number"
          step={spec.type === 'integer' ? 1 : 'any'}
          min={spec.min}
          max={spec.max}
          value={value ?? ''}
          placeholder={spec.default != null ? String(spec.default) : ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
      );
      break;
    case 'boolean':
      return (
        <label className="flex items-center gap-2 text-sm">
          <input id={id} type="checkbox" checked={value ?? spec.default ?? false} onChange={(e) => onChange(e.target.checked)} />
          {spec.label}
          {spec.help && <span className="text-xs text-muted">— {spec.help}</span>}
        </label>
      );
    case 'mapping':
      control = <MappingEditor id={id} value={value ?? {}} onChange={onChange} columns={columns} />;
      break;
    case 'ratios': {
      const r = value ?? spec.default ?? [0.7, 0.15, 0.15];
      control = (
        <div id={id} className="grid grid-cols-3 gap-2">
          {['Train', 'Validation', 'Test'].map((l, i) => (
            <label key={l} className="text-xs text-muted">
              {l} %
              <Input
                type="number"
                min={0}
                max={100}
                value={Math.round(r[i] * 100)}
                onChange={(e) => {
                  const next = [...r];
                  next[i] = Number(e.target.value) / 100;
                  onChange(next);
                }}
              />
            </label>
          ))}
          {Math.abs(r.reduce((/** @type {number} */ a, /** @type {number} */ b) => a + b, 0) - 1) > 0.001 && (
            <p className="col-span-3 text-xs text-danger">Must add up to 100%</p>
          )}
        </div>
      );
      break;
    }
    case 'expression':
      control = <Input id={id} className="font-mono" value={value ?? ''} onChange={(e) => onChange(e.target.value)} placeholder="price * quantity" />;
      break;
    default:
      control = <Input id={id} value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} placeholder={spec.default ?? ''} />;
  }
  return (
    <div className="space-y-1">
      {label}
      {control}
      {help}
      {err}
    </div>
  );
}

/** @param {{name: string, semantic_type: string}[]} columns @param {string | undefined} filter */
function sortByFilter(columns, filter) {
  const want = filter ? FILTER_TYPES[/** @type {keyof FILTER_TYPES} */ (filter)] : null;
  if (!want) return columns;
  return [...columns].sort((a, b) => Number(want.includes(b.semantic_type)) - Number(want.includes(a.semantic_type)));
}

/** @param {{id: string, value: string[], onChange: (v: string[]) => void, columns: {name: string, semantic_type: string}[], filter?: string}} props */
function ColumnsPicker({ id, value, onChange, columns, filter }) {
  const [q, setQ] = useState('');
  const [showAll, setShowAll] = useState(!filter);
  const want = filter ? FILTER_TYPES[/** @type {keyof FILTER_TYPES} */ (filter)] : null;
  const visible = columns.filter(
    (c) => c.name !== '__split__' && (showAll || !want || want.includes(c.semantic_type)) && c.name.toLowerCase().includes(q.toLowerCase()),
  );
  const toggle = (/** @type {string} */ name) => onChange(value.includes(name) ? value.filter((v) => v !== name) : [...value, name]);
  return (
    <div id={id} className="rounded-md border border-border">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border p-1.5">
        <input className="h-7 min-w-24 flex-1 bg-transparent px-1.5 text-sm outline-none" placeholder="Search columns" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search columns" />
        {TOKENS.map(([t, l]) => (
          <button
            key={t}
            type="button"
            onClick={() => toggle(t)}
            className={`rounded-full border px-2 py-0.5 text-[11px] ${value.includes(t) ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted'}`}
            title={`Selects ${l} columns at run time (the target is excluded)`}
          >
            {l}
          </button>
        ))}
      </div>
      <ul className="max-h-44 overflow-y-auto p-1 text-sm">
        {visible.map((c) => (
          <li key={c.name}>
            <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-0.5 hover:bg-subtle">
              <input type="checkbox" checked={value.includes(c.name)} onChange={() => toggle(c.name)} />
              <span className="truncate">{c.name}</span>
              <span className="ml-auto">
                <Badge tone={TYPE_TONE[c.semantic_type]}>{c.semantic_type}</Badge>
              </span>
            </label>
          </li>
        ))}
        {visible.length === 0 && <li className="px-2 py-1 text-xs text-muted">No matching columns</li>}
      </ul>
      <div className="flex items-center justify-between border-t border-border px-2 py-1 text-xs text-muted">
        <span>{value.length} selected</span>
        {want && (
          <button type="button" className="hover:text-fg" onClick={() => setShowAll(!showAll)}>
            {showAll ? `Only ${filter}` : 'Show all columns'}
          </button>
        )}
      </div>
    </div>
  );
}

/** @param {{id: string, value: Record<string, any>, onChange: (v: Record<string, any>) => void, columns: any[]}} props */
function MappingEditor({ id, value, onChange }) {
  const entries = Object.entries(value);
  const [k, setK] = useState('');
  const [v, setV] = useState('');
  const set = (/** @type {[string, any][]} */ es) => onChange(Object.fromEntries(es));
  return (
    <div id={id} className="space-y-1.5">
      {entries.map(([key, val], i) => (
        <div key={i} className="flex items-center gap-1.5">
          <input className={`${inputClass} w-full`} value={key} onChange={(e) => set(entries.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))} aria-label="From" />
          <span className="text-muted">→</span>
          <input
            className={`${inputClass} w-full`}
            value={Array.isArray(val) ? val.join(', ') : String(val ?? '')}
            onChange={(e) => set(entries.map((x, j) => (j === i ? [x[0], e.target.value] : x)))}
            aria-label="To"
          />
          <button type="button" className="px-1 text-muted hover:text-danger" onClick={() => set(entries.filter((_, j) => j !== i))} aria-label="Remove">
            ✕
          </button>
        </div>
      ))}
      <div className="flex items-center gap-1.5">
        <input className={`${inputClass} w-full`} placeholder="from" value={k} onChange={(e) => setK(e.target.value)} aria-label="New from" />
        <span className="text-muted">→</span>
        <input
          className={`${inputClass} w-full`}
          placeholder="to"
          value={v}
          onChange={(e) => setV(e.target.value)}
          aria-label="New to"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && k) {
              e.preventDefault();
              set([...entries, [k, v]]);
              setK('');
              setV('');
            }
          }}
        />
        <button
          type="button"
          className="rounded border border-border px-2 py-1 text-xs hover:border-accent"
          disabled={!k}
          onClick={() => {
            set([...entries, [k, v]]);
            setK('');
            setV('');
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}
