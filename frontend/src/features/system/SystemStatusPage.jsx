import { useHealth } from '../../api/health.js';

const LABELS = { database: 'PostgreSQL', redis: 'Redis', storage: 'Object storage (S3)' };

/** @param {{ ok: boolean }} props */
function StatusDot({ ok }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? 'bg-ok' : 'bg-danger'}`}
      aria-label={ok ? 'healthy' : 'down'}
    />
  );
}

/** Live dependency check, shown in Admin → Overview. */
export function HealthCard() {
  const { data, error, isPending, dataUpdatedAt } = useHealth();

  return (
    <section className="space-y-2">

      {isPending && <p className="text-muted">Checking…</p>}

      {error && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">
          <p className="font-medium">API unreachable</p>
          <p className="mt-1 text-muted">
            Is the stack running? Try <code className="font-mono">docker compose up</code>.
          </p>
        </div>
      )}

      {data && (
        <div className="rounded-xl border border-border bg-surface shadow-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2 font-medium">
              <StatusDot ok={data.status === 'ok'} />
              {data.status === 'ok' ? 'All systems operational' : 'Degraded'}
            </div>
            <span className="text-xs text-muted">
              v{data.version} · {data.environment}
            </span>
          </div>
          <ul className="divide-y divide-border">
            {Object.entries(data.dependencies).map(([name, dep]) => (
              <li key={name} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <StatusDot ok={dep.status === 'ok'} />
                  <span>{LABELS[name] ?? name}</span>
                  {dep.error && <span className="truncate text-xs text-danger">{dep.error}</span>}
                </div>
                <span className="shrink-0 tabular-nums text-muted">{dep.latency_ms} ms</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {dataUpdatedAt > 0 && (
        <p className="text-xs text-muted">
          Last checked {new Date(dataUpdatedAt).toLocaleTimeString()} · refreshes every 10 s
        </p>
      )}
    </section>
  );
}
