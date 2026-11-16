import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCreateProject, useDeleteProject, useProjects } from '../../api/hooks.js';
import { Button, ErrorBox, Field, Input, Modal, Spinner, Stat, fmt } from '../../components/ui.jsx';
import { useAuthStore } from '../../store/auth.js';
import { fmtBytes, useStorage } from '../../app/AppShell.jsx';
import { Icon } from '../../components/icons.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';

const HOW = [
  ['upload', 'Upload', 'CSV, Excel or Parquet. Types, gaps and problems are detected for you.'],
  ['clean', 'Clean & prepare', 'Fix data with recorded steps you can preview, undo and replay.'],
  ['validate', 'Validate', 'A readiness checklist and baseline models catch leakage and gaps.'],
  ['export', 'Export', 'Train/val/test files plus the Python code that reproduces them.'],
];

export function ProjectsPage() {
  const { data: projects, isPending, error } = useProjects();
  const [open, setOpen] = useState(false);
  const del = useDeleteProject();
  const user = useAuthStore((s) => s.user);
  const { data: storage } = useStorage();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const first = user?.display_name?.split(/\s+/)[0];
  const total = (/** @type {string} */ k) => (projects ?? []).reduce((a, /** @type {any} */ p) => a + (p[k] ?? 0), 0);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow={first ? `${greeting}, ${first}` : greeting}
        title="Your projects"
        description="Each project holds one dataset, the steps that clean it, and everything you export from it."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Icon name="plus" size={16} /> New project
          </Button>
        }
      />
      <ErrorBox error={error} />
      {isPending && <Spinner />}

      {projects?.length > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Projects" value={fmt.int(projects.length)} sub={`${projects.filter((/** @type {any} */ p) => p.dataset_name).length} with data`} />
          <Stat label="Rows under management" value={fmt.int(total('rows'))} sub={`${fmt.int(total('columns'))} columns in total`} />
          <Stat label="Recorded steps" value={fmt.int(total('steps'))} sub="Reversible and replayable" />
          <Stat label="Storage" value={storage ? fmtBytes(storage.used_bytes) : '—'} sub={storage ? `of ${fmtBytes(storage.quota_bytes)} · ${Math.round(storage.percent)}% used` : ' '} />
        </div>
      )}

      {projects?.length === 0 && (
        <div className="rounded-xl border border-border bg-surface p-8 shadow-card">
          <div>
          <h2 className="text-lg font-semibold">From raw file to model-ready data</h2>
          <p className="mt-1 text-sm text-muted">No code needed. Here’s how a project works:</p>
          <ol className="mt-6 grid gap-4 md:grid-cols-4">
            {HOW.map(([icon, t, d], i) => (
              <li key={t} className="rounded-lg border border-border bg-subtle/50 p-4">
                <div className="flex items-center gap-2 text-accent">
                  <Icon name={/** @type {any} */ (icon)} />
                  <span className="font-mono text-[11px] font-medium tracking-wider">STEP 0{i + 1}</span>
                </div>
                <div className="mt-2 font-medium">{t}</div>
                <p className="mt-1 text-xs text-muted">{d}</p>
              </li>
            ))}
          </ol>
          <Button variant="primary" className="mt-6" onClick={() => setOpen(true)}>
            Create your first project
          </Button>
          </div>
        </div>
      )}

      {projects?.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((/** @type {any} */ p) => (
            <li key={p.id} className="group relative">
              <Link
                to={`/projects/${p.id}`}
                className="flex h-full flex-col rounded-xl border border-border bg-surface p-5 shadow-card transition-colors hover:border-accent/50"
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                    <Icon name="data" />
                  </span>
                  <div className="min-w-0">
                    <h2 className="truncate font-semibold tracking-tight">{p.name}</h2>
                    <p className="truncate font-mono text-[11px] text-muted">{p.dataset_name ?? 'No data yet'}</p>
                  </div>
                </div>
                {p.description && <p className="mt-3 line-clamp-2 text-sm text-muted">{p.description}</p>}
                <div className="min-h-4 flex-1" />
                <dl className="grid grid-cols-3 gap-2 rounded-xl bg-subtle/60 p-3 pt-2.5 text-xs">
                  <div>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-muted">Rows</dt>
                    <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">{fmt.int(p.rows)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-muted">Columns</dt>
                    <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">{fmt.int(p.columns)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-muted">Steps</dt>
                    <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">{p.steps}</dd>
                  </div>
                </dl>
                <div className="mt-3 flex items-center justify-between text-xs text-muted">
                  <span className="flex min-w-0 items-center gap-1.5 truncate">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${p.target_column ? 'bg-ok' : 'bg-muted/40'}`} />
                    {p.target_column ? `Predicting ${p.target_column}` : 'No target yet'}
                  </span>
                  <span>{new Date(p.updated_at).toLocaleDateString()}</span>
                </div>
              </Link>
              <button
                className="absolute right-3 top-3 rounded-md p-1 text-muted opacity-0 transition hover:bg-danger/10 hover:text-danger focus:opacity-100 group-hover:opacity-100"
                onClick={() => window.confirm(`Delete "${p.name}"? Its data and exports are removed.`) && del.mutate(p.id)}
                aria-label={`Delete ${p.name}`}
                title="Delete project"
              >
                <Icon name="close" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <NewProjectModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

/** @param {{open: boolean, onClose: () => void}} props */
function NewProjectModal({ open, onClose }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const create = useCreateProject();
  const navigate = useNavigate();
  return (
    <Modal open={open} onClose={onClose} title="New project">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate({ name, description: description || undefined }, { onSuccess: (p) => navigate(`/projects/${p.id}`) });
        }}
      >
        <Field label="Name">{(id) => <Input id={id} required autoFocus placeholder="e.g. Customer churn" value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label="Description" hint="Optional: what you want to predict or learn">
          {(id) => <Input id={id} value={description} onChange={(e) => setDescription(e.target.value)} />}
        </Field>
        <ErrorBox error={create.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={create.isPending}>
            Create and upload data
          </Button>
        </div>
      </form>
    </Modal>
  );
}
