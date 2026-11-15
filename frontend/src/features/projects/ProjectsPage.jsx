import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCreateProject, useDeleteProject, useProjects } from '../../api/hooks.js';
import { Button, ErrorBox, Field, Input, Modal, Spinner, fmt } from '../../components/ui.jsx';
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

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Projects"
        description="Each project holds one dataset, the steps that clean it, and everything you export from it."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Icon name="plus" size={16} /> New project
          </Button>
        }
      />
      <ErrorBox error={error} />
      {isPending && <Spinner />}

      {projects?.length === 0 && (
        <div className="rounded-xl border border-border bg-surface p-8">
          <h2 className="text-lg font-semibold">From raw file to model-ready data</h2>
          <p className="mt-1 text-sm text-muted">No code needed. Here’s how a project works:</p>
          <ol className="mt-6 grid gap-4 md:grid-cols-4">
            {HOW.map(([icon, t, d], i) => (
              <li key={t} className="rounded-lg bg-subtle/60 p-4">
                <div className="flex items-center gap-2 text-accent">
                  <Icon name={/** @type {any} */ (icon)} />
                  <span className="text-xs font-semibold">STEP {i + 1}</span>
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
      )}

      {projects?.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((/** @type {any} */ p) => (
            <li key={p.id} className="group relative">
              <Link to={`/projects/${p.id}`} className="flex h-full flex-col rounded-xl border border-border bg-surface p-4 transition hover:border-accent/60 hover:shadow-sm">
                <div className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                    <Icon name="data" />
                  </span>
                  <div className="min-w-0">
                    <h2 className="truncate font-semibold">{p.name}</h2>
                    <p className="truncate text-xs text-muted">{p.dataset_name ?? 'No data yet'}</p>
                  </div>
                </div>
                {p.description && <p className="mt-3 line-clamp-2 text-sm text-muted">{p.description}</p>}
                <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-border pt-3 text-center text-xs">
                  <div>
                    <dt className="text-muted">Rows</dt>
                    <dd className="font-medium tabular-nums">{fmt.int(p.rows)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Columns</dt>
                    <dd className="font-medium tabular-nums">{fmt.int(p.columns)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Steps</dt>
                    <dd className="font-medium tabular-nums">{p.steps}</dd>
                  </div>
                </dl>
                <div className="mt-3 flex items-center justify-between text-xs text-muted">
                  <span className="truncate">{p.target_column ? `Predicting ${p.target_column}` : 'No target yet'}</span>
                  <span>{new Date(p.updated_at).toLocaleDateString()}</span>
                </div>
              </Link>
              <button
                className="absolute right-3 top-3 rounded p-1 text-muted opacity-0 hover:bg-subtle hover:text-danger focus:opacity-100 group-hover:opacity-100"
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
