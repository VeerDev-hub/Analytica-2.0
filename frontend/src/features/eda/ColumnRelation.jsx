import { useColumnDetail } from '../../api/pipelineHooks.js';
import { Spinner, fmt } from '../../components/ui.jsx';

/**
 * Column vs target summary shown inside the column inspector.
 * @param {{versionId: string, name: string}} props
 */
export function ColumnRelation({ versionId, name }) {
  const { data, isPending } = useColumnDetail(versionId, name);
  if (isPending) return <Spinner size={14} />;
  if (!data) return null;
  const rel = data.vs_target;
  return (
    <div className="space-y-2 text-sm">
      {data.outliers && (
        <p className="text-xs text-muted">
          Outliers: {data.outliers.low} low, {data.outliers.high} high (outside {fmt.num(data.outliers.bounds[0])} … {fmt.num(data.outliers.bounds[1])})
        </p>
      )}
      {rel && (
        <div className="rounded border border-border p-2">
          <div className="mb-1 text-xs font-medium">vs target “{rel.target}”</div>
          {rel.correlation != null && <p className="text-xs">Correlation r = {fmt.num(rel.correlation, 3)}</p>}
          {rel.by_class && (
            <table className="w-full text-xs">
              <tbody>
                {rel.by_class.map((/** @type {any} */ r) => (
                  <tr key={r.class}>
                    <td className="truncate pr-2">{r.class}</td>
                    <td className="text-right tabular-nums">mean {fmt.num(r.mean)}</td>
                    <td className="text-right tabular-nums text-muted">n={r.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {rel.target_mean_by_value && (
            <table className="w-full text-xs">
              <tbody>
                {rel.target_mean_by_value.slice(0, 8).map((/** @type {any} */ r) => (
                  <tr key={r.value}>
                    <td className="truncate pr-2">{r.value}</td>
                    <td className="text-right tabular-nums">{fmt.num(r.mean)}</td>
                    <td className="text-right tabular-nums text-muted">n={r.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {rel.class_share_by_value && (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted">
                  <th className="text-left font-normal">value</th>
                  {rel.class_share_by_value.classes.slice(0, 4).map((/** @type {string} */ c) => (
                    <th key={c} className="text-right font-normal">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rel.class_share_by_value.values.slice(0, 8).map((/** @type {string} */ v, /** @type {number} */ i) => (
                  <tr key={v}>
                    <td className="truncate pr-2">{v}</td>
                    {rel.class_share_by_value.matrix[i].slice(0, 4).map((/** @type {number} */ x, /** @type {number} */ j) => (
                      <td key={j} className="text-right tabular-nums">
                        {fmt.pct(x * 100, 0)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
