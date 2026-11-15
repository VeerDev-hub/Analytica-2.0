import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client.js';
import { useAuthStore } from '../../store/auth.js';
import { Badge, Button, Card, ErrorBox, Input, Select, Spinner, Stat, fmt } from '../../components/ui.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { Avatar } from '../../app/AppShell.jsx';
import { Segmented } from '../project/ExplorePage.jsx';
import { useSearchParams, Navigate } from 'react-router-dom';
import { HealthCard } from '../system/SystemStatusPage.jsx';
import { fmtBytes } from '../../app/AppShell.jsx';

const TABS = [
  { id: 'overview', label: 'Overview', icon: 'status' },
  { id: 'users', label: 'Users', icon: 'user' },
  { id: 'settings', label: 'Settings', icon: 'admin' },
];

export function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'overview';
  if (user && user.role !== 'admin') return <Navigate to="/projects" replace />;
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Admin" description="See how the app is used, manage who has access, and change settings without redeploying." />
      <div className="mb-5">
        <Segmented value={tab} onChange={(t) => setParams({ tab: t }, { replace: true })} options={/** @type {any} */ (TABS)} />
      </div>
      {tab === 'overview' && <Overview />}
      {tab === 'users' && <Users />}
      {tab === 'settings' && <Settings />}
    </div>
  );
}

function Overview() {
  const { data: s, isPending, error, dataUpdatedAt } = useQuery({ queryKey: ['admin', 'stats'], queryFn: () => api.get('/admin/stats'), refetchInterval: 30_000 });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const jobs = s.jobs_7d.by_status;
  const totalJobs = Object.values(jobs).reduce((/** @type {number} */ a, /** @type {any} */ b) => a + b, 0);
  // Always 14 slots (oldest → today) so one busy day doesn't become one giant bar.
  const byDay = Object.fromEntries(s.users.signups_14d.map((/** @type {any} */ d) => [d.day, d.count]));
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date(dataUpdatedAt - (13 - i) * 86_400_000).toISOString().slice(0, 10);
    return { day: d, count: byDay[d] ?? 0 };
  });
  const maxSign = Math.max(1, ...days.map((d) => d.count));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Users" value={fmt.int(s.users.total)} sub={`${s.users.new_7d} new · ${s.users.active_7d} active this week`} />
        <Stat label="Projects" value={fmt.int(s.projects.total)} sub={`${fmt.int(s.projects.steps)} steps applied`} />
        <Stat label="Storage" value={fmt.bytes(s.projects.storage_bytes)} sub={`${fmt.int(s.projects.versions)} dataset versions`} />
        <Stat label="Chat cost" value={`$${s.chat.cost_usd.toFixed(2)}`} sub={`$${s.chat.cost_usd_7d.toFixed(2)} this week · estimate`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Sign-ups (14 days)">
          <div className="flex h-28 items-end gap-1 border-b border-border">
            {days.map((d) => (
              <div key={d.day} className="flex h-full flex-1 flex-col justify-end" title={`${d.day}: ${d.count}`}>
                <div className="rounded-t bg-accent/70" style={{ height: `${Math.max((d.count / maxSign) * 100, d.count ? 4 : 0)}%` }} />
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-muted">
            <span>{days[0].day.slice(5)}</span>
            <span>today</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {Object.entries(s.users.by_method).map(([m, n]) => (
              <Badge key={m}>
                {m}: {String(n)}
              </Badge>
            ))}
          </div>
        </Card>
        <Card title="Jobs this week">
          <p className="mb-2 text-2xl font-semibold tabular-nums">{fmt.int(totalJobs)}</p>
          <div className="space-y-1 text-sm">
            {Object.entries(jobs).map(([k, n]) => (
              <div key={k} className="flex justify-between">
                <span className={k === 'failed' ? 'text-danger' : 'text-muted'}>{k}</span>
                <span className="tabular-nums">{String(n)}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Assistant usage">
          <div className="space-y-1 text-sm">
            <Row k="Answers" v={fmt.int(s.chat.messages)} />
            <Row k="Input tokens" v={fmt.int(s.chat.tokens_in)} />
            <Row k="Output tokens" v={fmt.int(s.chat.tokens_out)} />
          </div>
          <p className="mt-3 text-xs text-muted">
            Cost uses ${s.chat.price_per_mtok[0]} / ${s.chat.price_per_mtok[1]} per million input/output tokens.
          </p>
        </Card>
      </div>
      <HealthCard />
      <Card title="Recent failed jobs" padded={false}>
        {s.jobs_7d.recent_failures.length === 0 ? (
          <p className="p-4 text-sm text-muted">Nothing has failed. 🎉</p>
        ) : (
          <ul className="divide-y divide-border text-sm">
            {s.jobs_7d.recent_failures.map((/** @type {any} */ f) => (
              <li key={f.id} className="flex flex-wrap gap-x-3 px-4 py-2">
                <Badge tone="danger">{f.type}</Badge>
                <span className="text-muted">{f.user}</span>
                <span className="text-xs text-muted">{new Date(f.at).toLocaleString()}</span>
                <span className="w-full truncate text-xs" title={f.error}>
                  {f.error}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

const Row = ({ k, v }) => (
  <div className="flex justify-between">
    <span className="text-muted">{k}</span>
    <span className="tabular-nums">{v}</span>
  </div>
);

function Users() {
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const { data, isFetching, error } = useQuery({
    queryKey: ['admin', 'users', q, offset],
    queryFn: () => api.get(`/admin/users?q=${encodeURIComponent(q)}&offset=${offset}&limit=25`),
    placeholderData: keepPreviousData,
  });
  const patch = useMutation({
    mutationFn: (/** @type {{id: string, body: object}} */ { id, body }) => api.patch(`/admin/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
  });
  return (
    <Card
      title={`Users · ${data?.total ?? '…'}`}
      actions={<Input className="h-8 w-56" placeholder="Search name or email" value={q} onChange={(e) => (setQ(e.target.value), setOffset(0))} aria-label="Search users" />}
      padded={false}
    >
      <ErrorBox error={error ?? patch.error} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2 font-normal">User</th>
              <th className="px-2 py-2 font-normal">Sign-in</th>
              <th className="px-2 py-2 font-normal">Projects</th>
              <th className="px-2 py-2 font-normal">Storage</th>
              <th className="px-2 py-2 font-normal">Last active</th>
              <th className="px-2 py-2 font-normal">Role</th>
              <th className="px-4 py-2 text-right font-normal">Access</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data?.items.map((/** @type {any} */ u) => (
              <tr key={u.id} className={u.is_active ? '' : 'opacity-60'}>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2.5">
                    <Avatar user={u} size={28} />
                    <div className="min-w-0">
                      <div className="truncate font-medium">{u.display_name}</div>
                      <div className="truncate text-xs text-muted">{u.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-2 py-2">
                  <div className="flex gap-1">
                    {u.methods.map((/** @type {string} */ m) => (
                      <Badge key={m}>{m}</Badge>
                    ))}
                  </div>
                </td>
                <td className="px-2 py-2 tabular-nums">{u.projects}</td>
                <td className="px-2 py-2">
                  <QuotaCell u={u} onChange={(mb) => patch.mutate({ id: u.id, body: { storage_quota_mb: mb } })} />
                </td>
                <td className="px-2 py-2 text-xs text-muted">{u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'never'}</td>
                <td className="px-2 py-2">
                  <Select className="h-8 w-28" value={u.role} disabled={u.id === me?.id} onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })} aria-label={`Role for ${u.email}`}>
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </Select>
                </td>
                <td className="px-4 py-2 text-right">
                  <Button size="sm" variant={u.is_active ? 'secondary' : 'primary'} disabled={u.id === me?.id} onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                    {u.is_active ? 'Disable' : 'Enable'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-2 text-xs text-muted">
        {isFetching && <Spinner size={12} />}
        {data && `${offset + 1}–${Math.min(offset + 25, data.total)} of ${data.total}`}
        <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(offset - 25)}>
          ‹
        </Button>
        <Button size="sm" variant="ghost" disabled={!data || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>
          ›
        </Button>
      </div>
    </Card>
  );
}

const QUOTAS = [
  [0, 'Default'],
  [1024, '1 GB'],
  [5120, '5 GB'],
  [10240, '10 GB'],
  [25600, '25 GB'],
  [51200, '50 GB'],
  [102400, '100 GB'],
];

/** Usage bar plus a per-user limit picker ("Default" = the app-wide setting). */
function QuotaCell({ u, onChange }) {
  const pct = Math.min(100, (100 * u.storage_used) / Math.max(u.storage_quota, 1));
  const options = QUOTAS.some(([v]) => v === u.custom_quota_mb) || !u.custom_quota_mb ? QUOTAS : [...QUOTAS, [u.custom_quota_mb, `${u.custom_quota_mb} MB`]];
  return (
    <div className="w-52">
      <div className="flex items-center justify-between gap-2 whitespace-nowrap text-[11px] text-muted">
        <span className="tabular-nums">{fmtBytes(u.storage_used)}</span>
        <Select
          aria-label={`Storage limit for ${u.email}`}
          className="h-6 w-auto border-0 bg-transparent p-0 pr-5 text-[11px]"
          value={u.custom_quota_mb ?? 0}
          onChange={(e) => onChange(Number(e.target.value))}
        >
          {options.map(([v, l]) => (
            <option key={v} value={v}>
              {v === 0 ? `Default (${fmtBytes(u.custom_quota_mb ? 0 : u.storage_quota)})` : l}
            </option>
          ))}
        </Select>
      </div>
      <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-subtle">
        <div className={`h-full ${pct >= 90 ? 'bg-danger' : pct >= 75 ? 'bg-warn' : 'bg-accent'}`} style={{ width: `${Math.max(pct, 1)}%` }} />
      </div>
    </div>
  );
}

function Settings() {
  const qc = useQueryClient();
  const { data, isPending, error } = useQuery({ queryKey: ['admin', 'settings'], queryFn: () => api.get('/admin/settings') });
  const [draft, setDraft] = useState(/** @type {Record<string, any> | null} */ (null));
  const save = useMutation({
    mutationFn: (/** @type {object} */ body) => api.put('/admin/settings', body),
    onSuccess: () => {
      setDraft(null);
      qc.invalidateQueries({ queryKey: ['admin', 'settings'] });
      qc.invalidateQueries({ queryKey: ['meta'] });
      qc.invalidateQueries({ queryKey: ['chatStatus'] });
    },
  });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const values = { ...data.values, ...(draft ?? {}) };
  const set = (/** @type {string} */ k, /** @type {any} */ v) => setDraft({ ...(draft ?? {}), [k]: v });
  const env = data.environment;

  return (
    <div className="grid items-start gap-4 lg:grid-cols-3">
      <Card
        title="App settings"
        className="lg:col-span-2"
        actions={
          <Button size="sm" variant="primary" disabled={!draft} loading={save.isPending} onClick={() => save.mutate(draft)}>
            Save changes
          </Button>
        }
        padded={false}
      >
        <ErrorBox error={save.error} />
        <ul className="divide-y divide-border">
          {Object.entries(data.schema).map(([key, spec]) => (
            <li key={key} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0 max-w-md">
                <div className="text-sm font-medium">{/** @type {any} */ (spec).label}</div>
                <div className="text-xs text-muted">{/** @type {any} */ (spec).help}</div>
              </div>
              <SettingControl spec={spec} value={values[key]} onChange={(v) => set(key, v)} />
            </li>
          ))}
        </ul>
        {save.isSuccess && !draft && <p className="px-4 pb-3 text-xs text-ok">Saved. Changes apply within a few seconds.</p>}
      </Card>
      <div className="space-y-4">
        <Card title="Sign-in providers">
          <div className="space-y-3 text-sm">
            {Object.entries(env.oauth).map(([p, info]) => (
              <div key={p}>
                <div className="flex items-center justify-between">
                  <span className="font-medium capitalize">{p}</span>
                  <Badge tone={/** @type {any} */ (info).configured ? 'ok' : 'neutral'}>{/** @type {any} */ (info).configured ? 'active' : 'not set up'}</Badge>
                </div>
                {!(/** @type {any} */ (info).configured) && (
                  <p className="mt-1 text-xs text-muted">
                    Create an OAuth app ({p === 'google' ? 'Google Cloud Console → APIs & Services → Credentials' : 'GitHub → Settings → Developer settings → OAuth Apps'}), set the
                    callback URL below, then put <code className="font-mono">{p.toUpperCase()}_CLIENT_ID</code> and <code className="font-mono">{p.toUpperCase()}_CLIENT_SECRET</code> in <code className="font-mono">.env</code> and restart.
                  </p>
                )}
                <code className="mt-1 block break-all rounded bg-subtle px-2 py-1 font-mono text-[11px]">{/** @type {any} */ (info).redirect_uri}</code>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Server">
          <div className="space-y-1 text-sm">
            <Row k="Environment" v={env.environment} />
            <Row k="Chat API key" v={env.chat_api_key_set ? 'set' : 'missing'} />
            <Row k="App URL" v={env.public_app_url} />
          </div>
          <p className="mt-3 text-xs text-muted">
            Bootstrap admins (<code className="font-mono">ADMIN_EMAILS</code>): {env.admin_emails.join(', ') || 'none'}. They become admins whenever they sign in.
          </p>
        </Card>
      </div>
    </div>
  );
}

/** @param {{spec: any, value: any, onChange: (v: any) => void}} props */
function SettingControl({ spec, value, onChange }) {
  if (spec.type === 'bool') {
    return (
      <button
        role="switch"
        aria-checked={!!value}
        onClick={() => onChange(!value)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${value ? 'bg-accent' : 'bg-border'}`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${value ? 'left-[22px]' : 'left-0.5'}`} />
      </button>
    );
  }
  if (spec.type === 'select') {
    return (
      <Select className="w-48" value={value} onChange={(e) => onChange(e.target.value)}>
        {spec.options.map((/** @type {string} */ o) => (
          <option key={o}>{o}</option>
        ))}
      </Select>
    );
  }
  if (spec.type === 'int') {
    return <Input className="w-28" type="number" min={spec.min} max={spec.max} value={value} onChange={(e) => onChange(Number(e.target.value))} />;
  }
  return (
    <div className="flex w-full gap-2 sm:w-auto">
      <Input className="sm:w-72" placeholder="No banner" value={value?.text ?? ''} onChange={(e) => onChange({ ...value, text: e.target.value })} />
      <Select className="w-24" value={value?.tone ?? 'info'} onChange={(e) => onChange({ ...value, tone: e.target.value })}>
        <option value="info">info</option>
        <option value="warn">warning</option>
        <option value="ok">success</option>
      </Select>
    </div>
  );
}
