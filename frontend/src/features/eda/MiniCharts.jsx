// Lightweight inline-SVG charts for profiles (no chart library needed for these).
import { fmt } from '../../components/ui.jsx';

/** @param {{histogram: {edges: number[], counts: number[]}, height?: number}} props */
export function MiniHistogram({ histogram, height = 72 }) {
  const { edges, counts } = histogram;
  if (!counts?.length) return null;
  const max = Math.max(...counts, 1);
  const w = 100 / counts.length;
  return (
    <figure>
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="h-[72px] w-full" role="img" aria-label="Distribution histogram">
        {counts.map((c, i) => {
          const h = (c / max) * (height - 2);
          return (
            <rect key={i} x={i * w + 0.3} y={height - h} width={Math.max(w - 0.6, 0.4)} height={h} className="fill-info/70">
              <title>{`${fmt.num(edges[i])} – ${fmt.num(edges[i + 1])}: ${c}`}</title>
            </rect>
          );
        })}
      </svg>
      <figcaption className="flex justify-between text-[11px] tabular-nums text-muted">
        <span>{fmt.num(edges[0])}</span>
        <span>{fmt.num(edges[edges.length - 1])}</span>
      </figcaption>
    </figure>
  );
}

/** @param {{values: {value: string, count: number}[], total?: number, limit?: number}} props */
export function TopValues({ values, total, limit = 8 }) {
  const max = Math.max(...values.map((v) => v.count), 1);
  return (
    <ul className="space-y-1 text-sm">
      {values.slice(0, limit).map((v) => (
        <li key={v.value} className="relative overflow-hidden rounded px-2 py-0.5">
          <span className="absolute inset-y-0 left-0 bg-accent/15" style={{ width: `${(v.count / max) * 100}%` }} aria-hidden />
          <span className="relative flex justify-between gap-2">
            <span className="truncate">{v.value}</span>
            <span className="shrink-0 tabular-nums text-muted">
              {fmt.int(v.count)}
              {total ? ` · ${((100 * v.count) / total).toFixed(0)}%` : ''}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
