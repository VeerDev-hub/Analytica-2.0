import { useState } from 'react';
import { NavLink, Outlet, useMatch, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client.js';
import { useProject } from '../api/hooks.js';
import { useAuthStore } from '../store/auth.js';
import { Logo } from '../components/Logo.jsx';
import { Icon } from '../components/icons.jsx';
import { ThemeToggle } from '../components/ThemeToggle.jsx';
import { JobToast } from '../components/JobToast.jsx';
import { PROJECT_SECTIONS } from './sections.js';

export const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: () => api.get('/meta'), staleTime: 30_000 });

/** Left sidebar + main area. Inside a project the sidebar lists that project's sections. */
export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: meta } = useMeta();
  const banner = meta?.announcement?.text;

  return (
    <div className="flex min-h-screen bg-bg text-fg">
      {/* desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-border bg-surface lg:block">
        <SidebarContent />
      </aside>
      {/* mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setMobileOpen(false)}>
          <div className="absolute inset-0 bg-black/40" />
          <aside
            className="absolute inset-y-0 left-0 w-64 border-r border-border bg-surface shadow-xl"
            onClick={(e) => {
              e.stopPropagation();
              if (/** @type {HTMLElement} */ (e.target).closest('a')) setMobileOpen(false);
            }}
          >
            <SidebarContent />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-surface/95 px-4 py-2.5 backdrop-blur lg:hidden">
          <button className="rounded p-1.5 hover:bg-subtle" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Icon name="menu" />
          </button>
          <Logo size={24} subtitle={false} />
        </header>
        {banner && (
          <div className={`border-b px-6 py-2 text-sm ${meta.announcement.tone === 'warn' ? 'border-warn/30 bg-warn/10 text-warn' : meta.announcement.tone === 'ok' ? 'border-ok/30 bg-ok/10 text-ok' : 'border-info/30 bg-info/10 text-info'}`} role="status">
            {banner}
          </div>
        )}
        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
      <JobToast />
    </div>
  );
}

function SidebarContent() {
  const projectMatch = useMatch('/projects/:projectId/*');
  const projectId = projectMatch?.params.projectId;
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const logout = async () => {
    await api.post('/auth/logout').catch(() => {});
    clear();
    qc.clear();
    navigate('/login');
  };

  return (
    <nav className="flex h-full flex-col" aria-label="Main">
      <div className="px-4 pb-3 pt-4">
        <NavLink to="/projects" aria-label="Analytica home">
          <Logo />
        </NavLink>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        {projectId ? (
          <ProjectNav projectId={projectId} />
        ) : (
          <ul className="space-y-0.5">
            <NavItem to="/projects" icon="projects" label="Projects" />
            <NavItem to="/recipes" icon="recipes" label="Recipes" />
          </ul>
        )}
      </div>
      <div className="border-t border-border p-2">
        {user?.role === 'admin' && (
          <ul className="space-y-0.5">
            <NavItem to="/admin" icon="admin" label="Admin" />
          </ul>
        )}
        <StorageMeter />
        <div className="flex items-center gap-2 rounded-md px-2 py-2">
          <NavLink to="/account" className="flex min-w-0 flex-1 items-center gap-2 rounded hover:text-accent" title="Account">
            <Avatar user={user} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{user?.display_name}</span>
              <span className="block truncate text-[11px] text-muted">{user?.email}</span>
            </span>
          </NavLink>
          <ThemeToggle />
          <button onClick={logout} className="rounded p-1 text-muted hover:bg-subtle hover:text-fg" title="Sign out" aria-label="Sign out">
            <Icon name="logout" size={16} />
          </button>
        </div>
      </div>
    </nav>
  );
}

function ProjectNav({ projectId }) {
  const { data: project } = useProject(projectId);
  const hasData = !!project?.dataset?.current_version_id;
  return (
    <div>
      <NavLink to="/projects" className="mb-2 flex items-center gap-1 rounded px-2 py-1 text-xs text-muted hover:text-fg">
        <Icon name="back" size={14} /> All projects
      </NavLink>
      <div className="mb-3 px-2">
        <div className="truncate text-sm font-semibold" title={project?.name}>
          {project?.name ?? '…'}
        </div>
        {project?.dataset?.current_version && (
          <div className="truncate text-[11px] text-muted">
            {project.dataset.original_filename} · v{project.dataset.current_version.version_no}
          </div>
        )}
      </div>
      <ul className="space-y-0.5">
        {PROJECT_SECTIONS.map((s) => (
          <NavItem key={s.id} to={`/projects/${projectId}/${s.id}`} icon={s.icon} label={s.label} hint={s.description} disabled={!hasData && s.id !== 'data'} />
        ))}
      </ul>
    </div>
  );
}

export const useStorage = () =>
  useQuery({ queryKey: ['storage'], queryFn: () => api.get('/auth/me/storage'), staleTime: 30_000 });

/** Used / allowed storage for this account, always visible in the sidebar. */
function StorageMeter() {
  const { data } = useStorage();
  if (!data) return null;
  const pct = Math.min(100, data.percent);
  const tone = pct >= 90 ? 'bg-danger' : pct >= 75 ? 'bg-warn' : 'bg-accent';
  return (
    <NavLink to="/account#storage" className="mt-1 block rounded-md px-2 py-2 hover:bg-subtle" title="Storage used by your uploads, versions and exports">
      <div className="flex justify-between text-[11px] text-muted">
        <span>Storage</span>
        <span className="tabular-nums">
          {fmtBytes(data.used_bytes)} / {fmtBytes(data.quota_bytes)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-subtle">
        <div className={`h-full ${tone}`} style={{ width: `${Math.max(pct, 1)}%` }} />
      </div>
    </NavLink>
  );
}

export function fmtBytes(/** @type {number} */ n) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(n >= 10 * 1024 ** 3 ? 0 : 1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(0)} MB`;
  return `${Math.max(0, Math.round(n / 1024))} KB`;
}

/** @param {{to: string, icon: any, label: string, hint?: string, disabled?: boolean}} props */
function NavItem({ to, icon, label, hint, disabled }) {
  if (disabled) {
    return (
      <li>
        <span className="flex cursor-not-allowed items-center gap-2.5 rounded-md px-2 py-2 text-sm text-muted/50" title="Upload a dataset first">
          <Icon name={icon} /> {label}
        </span>
      </li>
    );
  }
  return (
    <li>
      <NavLink
        to={to}
        title={hint}
        className={({ isActive }) =>
          `flex items-center gap-2.5 rounded-md px-2 py-2 text-sm transition ${isActive ? 'bg-accent/10 font-medium text-accent' : 'text-fg/80 hover:bg-subtle hover:text-fg'}`
        }
      >
        <Icon name={icon} /> {label}
      </NavLink>
    </li>
  );
}

/** @param {{user: any, size?: number}} props */
export function Avatar({ user, size = 30 }) {
  if (user?.avatar_url) return <img src={user.avatar_url} alt="" width={size} height={size} className="shrink-0 rounded-full" />;
  const initials = (user?.display_name ?? '?')
    .split(/\s+/)
    .map((/** @type {string} */ w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <span className="flex shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent" style={{ width: size, height: size }}>
      {initials}
    </span>
  );
}
