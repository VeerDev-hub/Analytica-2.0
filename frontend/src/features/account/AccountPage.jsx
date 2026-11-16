import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFetch } from '../../api/client.js';
import { useAuthStore } from '../../store/auth.js';
import { useThemeStore } from '../../store/theme.js';
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, Spinner } from '../../components/ui.jsx';
import { GitHubIcon, GoogleIcon, Icon } from '../../components/icons.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { Avatar, fmtBytes, useStorage } from '../../app/AppShell.jsx';
import { PasswordField } from '../../components/PasswordField.jsx';
import { PlanCards, planName } from '../plans/PlanCards.jsx';
import { Segmented } from '../project/ExplorePage.jsx';

export function AccountPage() {
  const user = useAuthStore((s) => s.user);
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: () => api.get('/auth/me') });
  const u = me ?? user;
  if (!u) return <Spinner />;
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Account" description="Your profile, how you sign in, how the app looks, and how much storage you use." />
      <div className="mb-4">
        <PlanCard u={u} />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <ProfileCard u={u} />
          <AppearanceCard />
          <SignInCard u={u} />
        </div>
        <div className="space-y-4">
          <StorageCard />
          <DangerCard u={u} />
        </div>
      </div>
    </div>
  );
}

function ProfileCard({ u }) {
  const qc = useQueryClient();
  const setSession = useAuthStore((s) => s.setSession);
  const token = useAuthStore((s) => s.accessToken);
  const [name, setName] = useState(u.display_name);
  const save = useMutation({
    mutationFn: () => api.patch('/auth/me', { display_name: name }),
    onSuccess: (me) => {
      qc.setQueryData(['me'], me);
      setSession({ access_token: token ?? '', user: me });
    },
  });
  return (
    <Card title="Profile">
      <div className="flex items-center gap-4">
        <AvatarEditor u={u} />
        <div className="min-w-0">
          <div className="truncate text-sm text-muted">{u.email}</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge tone={u.role === 'admin' ? 'accent' : 'neutral'}>{u.role}</Badge>
            <Badge>joined {new Date(u.created_at).toLocaleDateString()}</Badge>
          </div>
        </div>
      </div>
      <form
        className="mt-4 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="flex-1">
          <Field label="Display name">{(id) => <Input id={id} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />}</Field>
        </div>
        <Button type="submit" disabled={!name.trim() || name === u.display_name} loading={save.isPending}>
          Save
        </Button>
      </form>
      {save.isSuccess && <p className="mt-2 text-xs text-ok">Saved.</p>}
      <ErrorBox error={save.error} />
      <p className="mt-3 text-xs text-muted">Your email is your sign-in name and can’t be changed here.</p>
    </Card>
  );
}

/** Center-crops an image file to a square WebP (falls back to PNG) so uploads are small and EXIF-free. */
async function toSquareImage(/** @type {File} */ file, size = 256) {
  const bmp = await createImageBitmap(file);
  const side = Math.min(bmp.width, bmp.height);
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = /** @type {CanvasRenderingContext2D} */ (canvas.getContext('2d'));
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(bmp, (bmp.width - side) / 2, (bmp.height - side) / 2, side, side, 0, 0, size, size);
  bmp.close();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/webp', 0.9));
  if (blob && /** @type {Blob} */ (blob).type === 'image/webp') return /** @type {Blob} */ (blob);
  return /** @type {Blob} */ (await new Promise((resolve) => canvas.toBlob(resolve, 'image/png')));
}

/** Profile picture with upload / remove. */
function AvatarEditor({ u }) {
  const qc = useQueryClient();
  const setSession = useAuthStore((s) => s.setSession);
  const token = useAuthStore((s) => s.accessToken);
  const input = useRef(/** @type {HTMLInputElement | null} */ (null));
  const [error, setError] = useState(/** @type {any} */ (null));
  const apply = (/** @type {any} */ me) => {
    qc.setQueryData(['me'], me);
    setSession({ access_token: token ?? '', user: me });
  };
  const upload = useMutation({
    mutationFn: async (/** @type {File} */ file) => {
      if (!file.type.startsWith('image/')) throw new Error('Choose an image file (PNG, JPEG, WebP…).');
      if (file.size > 15 * 1024 * 1024) throw new Error('That image is over 15 MB. Pick a smaller one.');
      let blob;
      try {
        blob = await toSquareImage(file);
      } catch {
        throw new Error('Could not read that image. Try a PNG or JPEG.');
      }
      const form = new FormData();
      form.append('file', blob, blob.type === 'image/webp' ? 'avatar.webp' : 'avatar.png');
      return apiFetch('/auth/me/avatar', { method: 'POST', body: form });
    },
    onMutate: () => setError(null),
    onSuccess: apply,
    onError: (e) => setError(e),
  });
  const remove = useMutation({ mutationFn: () => api.del('/auth/me/avatar'), onSuccess: apply, onError: (e) => setError(e) });
  const busy = upload.isPending || remove.isPending;
  return (
    <div className="flex shrink-0 flex-col items-center gap-1.5">
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className="group relative rounded-full focus-visible:outline-offset-4"
        title="Change profile picture"
        aria-label="Change profile picture"
      >
        <Avatar user={u} size={72} />
        <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
          {busy ? <Spinner size={18} /> : <Icon name="camera" size={20} />}
        </span>
        <span className="absolute -bottom-0.5 -right-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-accent-fg shadow-card ring-2 ring-surface transition group-hover:scale-110">
          <Icon name="camera" size={12} />
        </span>
      </button>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/avif"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (f) upload.mutate(f);
        }}
      />
      {u.avatar_url && (
        <button type="button" onClick={() => remove.mutate()} disabled={busy} className="text-[11px] text-muted transition hover:text-danger">
          Remove
        </button>
      )}
      {error && <p className="max-w-[9rem] text-center text-[11px] text-danger">{error.message}</p>}
    </div>
  );
}

function PlanCard({ u }) {
  const { data: storage } = useStorage();
  return (
    <div id="plan">
      <Card title="Plan">
        <p className="text-sm">
          You're on the <strong>{planName(u.plan)}</strong> plan
          {storage ? <> with {fmtBytes(storage.quota_bytes)} of storage</> : null}
          {u.plan === 'free' ? '. The AI assistant is included in Pro and Business.' : '. The AI assistant is included.'}
        </p>
        <div className="mt-4">
          <PlanCards current={u.plan} compact />
        </div>
      </Card>
    </div>
  );
}

function AppearanceCard() {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  return (
    <Card title="Appearance">
      <Segmented
        value={mode}
        onChange={(v) => setMode(/** @type {any} */ (v))}
        options={[
          { id: 'light', label: 'Light', icon: 'sun' },
          { id: 'dark', label: 'Dark', icon: 'moon' },
          { id: 'system', label: 'Match my computer' },
        ]}
      />
      <p className="mt-2 text-xs text-muted">The sun/moon button in the sidebar switches between light and dark quickly.</p>
    </Card>
  );
}

function SignInCard({ u }) {
  const { data: prov } = useQuery({ queryKey: ['authProviders'], queryFn: () => api.get('/auth/providers') });
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const change = useMutation({
    mutationFn: () => api.post('/auth/me/password', { current_password: cur || null, new_password: next }),
    onSuccess: () => {
      setOpen(false);
      setCur('');
      setNext('');
      qc.invalidateQueries({ queryKey: ['me'] });
    },
  });
  const linked = new Set(u.providers ?? []);
  return (
    <Card title="Sign-in methods" padded={false}>
      <ul className="divide-y divide-border text-sm">
        <li className="flex items-center justify-between px-4 py-3">
          <span>Email and password</span>
          <span className="flex items-center gap-2">
            <Badge tone={u.has_password ? 'ok' : 'neutral'}>{u.has_password ? 'on' : 'not set'}</Badge>
            <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
              {u.has_password ? 'Change password' : 'Set a password'}
            </Button>
          </span>
        </li>
        {[
          ['google', 'Google', <GoogleIcon key="g" />],
          ['github', 'GitHub', <GitHubIcon key="h" />],
        ].map(([id, label, icon]) => (
          <li key={/** @type {string} */ (id)} className="flex items-center justify-between px-4 py-3">
            <span className="flex items-center gap-2">
              {icon} {label}
            </span>
            {linked.has(/** @type {string} */ (id)) ? (
              <Badge tone="ok">linked</Badge>
            ) : prov?.providers?.includes(id) ? (
              <a className="text-xs font-medium text-accent hover:underline" href={`/api/v1/auth/oauth/${id}/start`}>
                Link {label}
              </a>
            ) : (
              <span className="text-xs text-muted">not available yet</span>
            )}
          </li>
        ))}
      </ul>
      <Modal open={open} onClose={() => setOpen(false)} title={u.has_password ? 'Change password' : 'Set a password'}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate();
          }}
        >
          {u.has_password && (
            <Field label="Current password">{(id) => <Input id={id} type="password" required value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />}</Field>
          )}
          <PasswordField label="New password" value={next} onChange={setNext} email={u.email} name={u.display_name} />
          <ErrorBox error={change.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={change.isPending}>
              Save password
            </Button>
          </div>
        </form>
      </Modal>
      {change.isSuccess && <p className="px-4 pb-3 text-xs text-ok">Password updated.</p>}
    </Card>
  );
}

function StorageCard() {
  const { data, isPending } = useStorage();
  const qc = useQueryClient();
  const free = useMutation({
    mutationFn: (/** @type {string} */ projectId) => api.post(`/projects/${projectId}/free-space`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['storage'] }),
  });
  if (isPending || !data) return <Spinner />;
  const pct = Math.min(100, data.percent);
  const tone = pct >= 90 ? 'bg-danger' : pct >= 75 ? 'bg-warn' : 'bg-accent';
  return (
    <div id="storage">
      <Card title="Storage">
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-semibold tabular-nums">{fmtBytes(data.used_bytes)}</span>
          <span className="text-sm text-muted">of {fmtBytes(data.quota_bytes)}</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-subtle">
          <div className={`h-full ${tone}`} style={{ width: `${Math.max(pct, 1)}%` }} />
        </div>
        <p className="mt-2 text-xs text-muted">
          Uploads, every cleaning version and exports count towards your limit. When it’s full you can still view everything, but new uploads, steps and exports are paused.
        </p>
        {free.data && (
          <p className="mt-2 text-xs text-ok">
            Freed {fmtBytes(free.data.freed_bytes)} ({free.data.deleted_versions} old versions removed).
          </p>
        )}
        <ErrorBox error={free.error} />
        {data.projects.length > 0 && (
          <ul className="mt-4 divide-y divide-border rounded-md border border-border text-sm">
            {data.projects.map((/** @type {any} */ p) => (
              <li key={p.id} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1 truncate">{p.name}</span>
                <span className="tabular-nums text-muted">{fmtBytes(p.bytes)}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={free.isPending && free.variables === p.id}
                  onClick={() => free.mutate(p.id)}
                  title="Delete versions no step needs any more (undone or replaced steps). Your current data is kept."
                >
                  Free up space
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function DangerCard({ u }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const clear = useAuthStore((s) => s.clear);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const del = useMutation({
    mutationFn: () => api.del('/auth/me', { confirm_email: email, password: password || null }),
    onSuccess: () => {
      clear();
      qc.clear();
      navigate('/login', { replace: true });
    },
  });
  return (
    <Card title="Delete account">
      <p className="text-sm text-muted">Permanently deletes your account, all projects, uploaded files, exports, recipes and chat history. This can’t be undone.</p>
      <Button variant="danger" className="mt-3" onClick={() => setOpen(true)}>
        Delete my account
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Delete your account?">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            del.mutate();
          }}
        >
          <p className="text-sm text-muted">
            Type <b className="text-fg">{u.email}</b> to confirm.
          </p>
          <Field label="Email">{(id) => <Input id={id} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />}</Field>
          {u.has_password && (
            <Field label="Password">{(id) => <Input id={id} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />}</Field>
          )}
          <ErrorBox error={del.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Keep my account
            </Button>
            <Button type="submit" variant="danger" disabled={email.trim().toLowerCase() !== u.email.toLowerCase()} loading={del.isPending}>
              Delete forever
            </Button>
          </div>
        </form>
      </Modal>
    </Card>
  );
}
