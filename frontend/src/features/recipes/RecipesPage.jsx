import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client.js';
import { keys } from '../../api/hooks.js';
import { useRecipes } from '../../api/pipelineHooks.js';
import { Badge, EmptyState, ErrorBox, Spinner } from '../../components/ui.jsx';
import { Icon } from '../../components/icons.jsx';
import { PageHeader } from '../../components/PageHeader.jsx';

export function RecipesPage() {
  const { data, isPending, error } = useRecipes();
  const qc = useQueryClient();
  const del = useMutation({ mutationFn: (/** @type {string} */ id) => api.del(`/recipes/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: keys.recipes }) });
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Recipes"
        description="A recipe is a saved list of steps. Save one from a project’s History, then apply it to a new file with one click (History → Recipes)."
      />
      <ErrorBox error={error ?? del.error} />
      {isPending && <Spinner />}
      {data?.length === 0 && (
        <EmptyState title="No recipes yet">
          Open a project, apply some steps, then use <b>History → Recipes → Save</b>. The same cleaning can then be replayed on next month’s file.
        </EmptyState>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {data?.map((/** @type {any} */ r) => (
          <div key={r.id} className="rounded-xl border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-semibold">{r.name}</h2>
                <p className="text-xs text-muted">
                  {r.steps.length} steps · saved {new Date(r.created_at).toLocaleDateString()}
                </p>
              </div>
              <button className="rounded p-1 text-muted hover:bg-subtle hover:text-danger" title="Delete recipe" aria-label={`Delete ${r.name}`} onClick={() => window.confirm(`Delete recipe "${r.name}"?`) && del.mutate(r.id)}>
                <Icon name="close" size={16} />
              </button>
            </div>
            <ol className="mt-3 space-y-1">
              {r.steps.map((/** @type {any} */ s, /** @type {number} */ i) => (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-subtle text-[11px]">{i + 1}</span>
                  <span className="truncate">{s.step_type.replaceAll('_', ' ')}</span>
                  {s.phase === 'post_split' && <Badge tone="info">learns</Badge>}
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}
