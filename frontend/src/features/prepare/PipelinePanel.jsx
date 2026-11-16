import { useState } from 'react';
import {
  useActiveJob,
  useApplyRecipe,
  useDeleteStep,
  usePatchStep,
  usePipeline,
  usePipelineAction,
  useRecipes,
  useReorder,
  useSaveRecipe,
} from '../../api/pipelineHooks.js';
import { isTerminal } from '../../api/hooks.js';
import { Badge, Button, ErrorBox, Input, Modal, Select, fmt } from '../../components/ui.jsx';
import { useWorkspaceStore } from '../../store/workspace.js';

const STATUS_TONE = /** @type {const} */ ({ applied: 'ok', undone: 'neutral', failed: 'danger', pending: 'warn', running: 'warn' });

/** The recorded, replayable recipe (design rule 2), always visible beside the workspace. */
export function PipelinePanel({ project }) {
  const { data: pl, error } = usePipeline(project.id);
  const { job } = useActiveJob(project.id);
  const action = usePipelineAction(project.id, pl?.id);
  const patch = usePatchStep(project.id);
  const del = useDeleteStep(project.id);
  const reorder = useReorder(project.id, pl?.id);
  const openDraft = useWorkspaceStore((s) => s.openDraft);
  const [recipeOpen, setRecipeOpen] = useState(false);

  if (error) return <ErrorBox error={error} />;
  if (!pl) return null;
  const running = pl.busy || (job && !isTerminal(job.status));
  const applied = pl.steps.filter((/** @type {any} */ s) => s.status === 'applied');
  const mutError = action.error ?? patch.error ?? del.error ?? reorder.error;

  const move = (/** @type {number} */ i, /** @type {number} */ dir) => {
    const ids = applied.map((/** @type {any} */ s) => s.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    reorder.mutate(ids);
  };

  return (
    <div className="flex w-full flex-col gap-3" aria-label="Pipeline">
      <div className="rounded-xl border border-border bg-surface shadow-card">
        <header className="flex items-center justify-between border-b border-border px-3 py-2">
          <h2 className="text-sm font-semibold">Steps applied</h2>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" disabled={!pl.can_undo || running} onClick={() => action.mutate('undo')} title="Undo last step">
              ↶
            </Button>
            <Button size="sm" variant="ghost" disabled={!pl.can_redo || running} onClick={() => action.mutate('redo')} title="Redo">
              ↷
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={!pl.can_undo || running}
              onClick={() => window.confirm('Go back to the original upload? Steps stay in history until you add a new one.') && action.mutate('reset')}
              title="Reset to original"
            >
              ⟲
            </Button>
          </div>
        </header>

        {job?.status === 'failed' && <p className="border-b border-border px-3 py-2 text-xs text-danger">{job.error}</p>}
        {mutError && (
          <div className="p-2">
            <ErrorBox error={mutError} />
          </div>
        )}

        <ol className="divide-y divide-border">
          <li className="flex items-center gap-2 px-3 py-2 text-xs text-muted">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-subtle">0</span>
            Original upload
          </li>
          {pl.steps.map((/** @type {any} */ s) => {
            const idx = applied.findIndex((/** @type {any} */ a) => a.id === s.id);
            return (
              <li key={s.id} className={`group px-3 py-2 ${s.status === 'undone' ? 'opacity-50' : ''} ${!s.is_enabled ? 'opacity-60' : ''}`}>
                <div className="flex items-start gap-2">
                  <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] ${s.step_type === 'split' ? 'bg-accent text-accent-fg' : 'bg-subtle'}`}>
                    {s.position}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className={`truncate text-sm ${!s.is_enabled ? 'line-through' : ''}`} title={s.describe}>
                        {s.describe || s.label}
                      </span>
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                      <Badge tone={STATUS_TONE[/** @type {'applied'} */ (s.status)]}>{s.status}</Badge>
                      {s.phase === 'post_split' && <Badge tone="info">train-fitted</Badge>}
                      {s.rows_after != null && s.rows_after !== s.rows_before && (
                        <span>
                          rows {fmt.int(s.rows_before)}→{fmt.int(s.rows_after)}
                        </span>
                      )}
                      {s.cols_after != null && s.cols_after !== s.cols_before && (
                        <span>
                          cols {s.cols_before}→{s.cols_after}
                        </span>
                      )}
                    </div>
                    {s.error_message && <p className="mt-1 text-xs text-danger">{s.error_message}</p>}
                    {s.warnings
                      ?.filter((/** @type {any} */ w) => w.level === 'warning')
                      .map((/** @type {any} */ w, /** @type {number} */ i) => (
                        <p key={i} className="mt-1 text-[11px] text-warn">
                          ⚠ {w.message}
                        </p>
                      ))}
                  </div>
                </div>
                {['applied', 'failed'].includes(s.status) && !running && (
                  <div className="mt-1 flex gap-1 pl-7 text-[11px] opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">
                    <button className="rounded px-1.5 hover:bg-subtle" onClick={() => openDraft({ step_type: s.step_type, params: s.params, editStepId: s.id })}>
                      Edit
                    </button>
                    {s.status === 'applied' && (
                      <button className="rounded px-1.5 hover:bg-subtle" onClick={() => patch.mutate({ id: s.id, is_enabled: !s.is_enabled })}>
                        {s.is_enabled ? 'Disable' : 'Enable'}
                      </button>
                    )}
                    {idx > 0 && (
                      <button className="rounded px-1.5 hover:bg-subtle" onClick={() => move(idx, -1)} aria-label="Move up">
                        ↑
                      </button>
                    )}
                    {idx >= 0 && idx < applied.length - 1 && (
                      <button className="rounded px-1.5 hover:bg-subtle" onClick={() => move(idx, 1)} aria-label="Move down">
                        ↓
                      </button>
                    )}
                    <button className="ml-auto rounded px-1.5 text-danger hover:bg-subtle" onClick={() => window.confirm('Delete this step? Later steps are re-run.') && del.mutate(s.id)}>
                      Delete
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        {pl.steps.length === 0 && <p className="px-3 pb-3 text-xs text-muted">No steps yet. Pick one from Prepare, or click “Fix” on an alert.</p>}
        {pl.issues.length > 0 && (
          <ul className="space-y-1 border-t border-border px-3 py-2">
            {pl.issues.map((/** @type {any} */ i, /** @type {number} */ k) => (
              <li key={k} className={`text-xs ${i.level === 'error' ? 'text-danger' : 'text-warn'}`}>
                ⚠ {i.message}
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-2 border-t border-border p-2">
          <Button size="sm" className="flex-1" onClick={() => setRecipeOpen(true)}>
            Recipes
          </Button>
        </div>
      </div>
      <RecipesModal open={recipeOpen} onClose={() => setRecipeOpen(false)} project={project} canSave={applied.length > 0} />
    </div>
  );
}

/** @param {{open: boolean, onClose: () => void, project: any, canSave: boolean}} props */
function RecipesModal({ open, onClose, project, canSave }) {
  const { data: recipes } = useRecipes();
  const save = useSaveRecipe();
  const applyR = useApplyRecipe(project.id);
  const [name, setName] = useState('');
  const [pick, setPick] = useState('');
  return (
    <Modal open={open} onClose={onClose} title="Recipes">
      <div className="space-y-5">
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Save this pipeline as a recipe</h3>
          <p className="text-xs text-muted">Replay the same steps on another file later.</p>
          <div className="flex gap-2">
            <Input placeholder="Recipe name" value={name} onChange={(e) => setName(e.target.value)} aria-label="Recipe name" />
            <Button disabled={!name || !canSave} loading={save.isPending} onClick={() => save.mutate({ project_id: project.id, name }, { onSuccess: () => setName('') })}>
              Save
            </Button>
          </div>
          {save.isSuccess && <p className="text-xs text-ok">Saved.</p>}
          <ErrorBox error={save.error} />
        </section>
        <section className="space-y-2 border-t border-border pt-4">
          <h3 className="text-sm font-medium">Apply a saved recipe here</h3>
          <div className="flex gap-2">
            <Select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Recipe">
              <option value="">Choose…</option>
              {recipes?.map((/** @type {any} */ r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.steps.length} steps)
                </option>
              ))}
            </Select>
            <Button variant="primary" disabled={!pick} loading={applyR.isPending} onClick={() => applyR.mutate(pick, { onSuccess: onClose })}>
              Apply
            </Button>
          </div>
          <ErrorBox error={applyR.error} />
        </section>
      </div>
    </Modal>
  );
}
