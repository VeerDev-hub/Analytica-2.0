import { useState } from 'react';
import { Navigate, Outlet, useNavigate, useOutletContext, useParams } from 'react-router-dom';
import { useOverview, usePatchProject, useProject } from '../../api/hooks.js';
import { usePipeline } from '../../api/pipelineHooks.js';
import { ErrorBox, Select, Spinner } from '../../components/ui.jsx';
import { Icon } from '../../components/icons.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';
import { useWorkspaceStore } from '../../store/workspace.js';
import { UploadPanel } from '../datasets/UploadPanel.jsx';
import { PipelinePanel } from '../prepare/PipelinePanel.jsx';
import { pageForStep, sectionById } from '../../app/sections.js';

/**
 * @typedef {{project: any, overview: any, version: any, openStep: (stepType: string, params: object) => void}} ProjectCtx
 * @returns {ProjectCtx}
 */
export const useProjectCtx = () => useOutletContext();

/** Loads the project once for all its sections; shows the upload screen until data exists. */
export function ProjectLayout() {
  const { projectId = '' } = useParams();
  const { data: project, isPending, error } = useProject(projectId);
  const versionId = project?.dataset?.current_version_id ?? undefined;
  const { data: overview } = useOverview(versionId);
  const openDraft = useWorkspaceStore((s) => s.openDraft);
  const navigate = useNavigate();

  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  if (!project) return null;

  if (!project.dataset?.current_version) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader eyebrow={project.name} title="Add your data" description="Upload one file to start. It is profiled automatically, and the original is never changed: every cleaning step creates a new version you can undo." />
        <UploadPanel projectId={project.id} />
      </div>
    );
  }

  /** @type {ProjectCtx} */
  const ctx = {
    project,
    overview,
    version: project.dataset.current_version,
    openStep: (stepType, params) => {
      openDraft({ step_type: stepType, params });
      navigate(`/projects/${project.id}/${pageForStep(stepType)}`);
    },
  };
  return <Outlet context={ctx} />;
}

export function ProjectIndex() {
  return <Navigate to="data" replace />;
}

/**
 * Standard header for a project section: title + description, target/task picker and the
 * history drawer button.
 * @param {{section: string, ctx: ProjectCtx, showTarget?: boolean, actions?: import('react').ReactNode}} props
 */
export function SectionHeader({ section, ctx, showTarget = false, actions }) {
  const s = sectionById[section];
  return (
    <PageHeader
      eyebrow={ctx.project.name}
      title={s.label}
      description={s.description}
      actions={
        <>
          {actions}
          {showTarget && <TargetPicker ctx={ctx} />}
          <HistoryButton project={ctx.project} />
        </>
      }
    />
  );
}

/** @param {{ctx: ProjectCtx}} props */
export function TargetPicker({ ctx }) {
  const patch = usePatchProject(ctx.project.id);
  const cols = (ctx.overview?.columns ?? []).filter((/** @type {any} */ c) => c.name !== '__split__');
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-sm" title="The column a model should predict, and the kind of problem">
      <span className="text-xs text-muted">Target</span>
      <Select aria-label="Target column" className="h-7 w-36 border-0 px-1 py-0" value={ctx.project.target_column ?? ''} onChange={(e) => patch.mutate({ target_column: e.target.value || null })}>
        <option value="">None</option>
        {cols.map((/** @type {any} */ c) => (
          <option key={c.id} value={c.name}>
            {c.name}
          </option>
        ))}
      </Select>
      <Select aria-label="Task type" className="h-7 w-36 border-0 px-1 py-0" value={ctx.project.task_type ?? ''} onChange={(e) => patch.mutate({ task_type: e.target.value || null })}>
        <option value="">Task…</option>
        <option value="classification">Classification</option>
        <option value="regression">Regression</option>
        <option value="forecast">Forecast</option>
        <option value="unsupervised">Unsupervised</option>
      </Select>
    </div>
  );
}

/** @param {{project: any}} props */
function HistoryButton({ project }) {
  const [open, setOpen] = useState(false);
  const { data: pl } = usePipeline(project.id);
  const n = pl?.steps.filter((/** @type {any} */ s) => s.status === 'applied').length ?? 0;
  return (
    <>
      <button onClick={() => setOpen(true)} className="flex h-9 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-sm hover:border-accent/60" title="Steps applied, undo/redo and recipes">
        <Icon name="history" size={16} /> History
        <span className="rounded bg-subtle px-1.5 text-xs tabular-nums text-muted">{n}</span>
      </button>
      {open && (
        <div className="fixed inset-0 z-50" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/30" />
          <aside className="absolute inset-y-0 right-0 flex w-full max-w-sm flex-col border-l border-border bg-bg shadow-2xl" onClick={(e) => e.stopPropagation()} aria-label="History">
            <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
              <div>
                <h2 className="font-semibold">History</h2>
                <p className="text-xs text-muted">Every change is a step. Undo, edit, disable or reorder them; later steps re-run.</p>
              </div>
              <button className="rounded p-1 text-muted hover:bg-subtle" onClick={() => setOpen(false)} aria-label="Close history">
                <Icon name="close" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              <PipelinePanel project={project} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
