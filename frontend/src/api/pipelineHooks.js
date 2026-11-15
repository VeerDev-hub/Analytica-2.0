import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client.js';
import { isTerminal, keys, useJob } from './hooks.js';
import { useWorkspaceStore } from '../store/workspace.js';

export const useCatalog = () => useQuery({ queryKey: keys.catalog, queryFn: () => api.get('/steps/catalog'), staleTime: Infinity });

export const usePipeline = (/** @type {string} */ projectId, enabled = true) =>
  useQuery({
    queryKey: keys.pipeline(projectId),
    queryFn: () => api.get(`/projects/${projectId}/pipeline`),
    enabled: !!projectId && enabled,
  });

/** Everything that depends on the current version must refresh after a pipeline change. */
export function useRefreshAfterChange(/** @type {string} */ projectId) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.pipeline(projectId) });
    qc.invalidateQueries({ queryKey: keys.project(projectId) });
    qc.invalidateQueries({ queryKey: keys.readiness(projectId) });
    qc.invalidateQueries({ queryKey: ['storage'] });
  };
}

/**
 * Tracks the job started by the last pipeline action. When it finishes, refresh data.
 * @param {string} projectId
 */
export function useActiveJob(projectId) {
  const jobId = useWorkspaceStore((s) => s.jobs[projectId] ?? null);
  const setJob = useWorkspaceStore((s) => s.setJob);
  const refresh = useRefreshAfterChange(projectId);
  const job = useJob(jobId);
  const status = job.data?.status;
  useEffect(() => {
    if (isTerminal(status)) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);
  return { job: job.data, jobId, setJob: (/** @type {string | null} */ id) => setJob(projectId, id) };
}

function usePipelineMutation(/** @type {string} */ projectId, /** @type {(v: any) => Promise<any>} */ fn) {
  const setJob = useWorkspaceStore((s) => s.setJob);
  const refresh = useRefreshAfterChange(projectId);
  return useMutation({
    mutationFn: fn,
    onSuccess: (res) => {
      if (res?.job_id) setJob(projectId, res.job_id);
      refresh();
    },
  });
}

export const usePreviewStep = (/** @type {string} */ pipelineId) =>
  useMutation({ mutationFn: (/** @type {{step_type: string, params: object}} */ body) => api.post(`/pipeline/${pipelineId}/steps/preview`, body) });

export const useAddStep = (/** @type {string} */ projectId, /** @type {string} */ pipelineId) =>
  usePipelineMutation(projectId, (body) => api.post(`/pipeline/${pipelineId}/steps`, body));

export const usePatchStep = (/** @type {string} */ projectId) =>
  usePipelineMutation(projectId, ({ id, ...body }) => api.patch(`/steps/${id}`, body));

export const useDeleteStep = (/** @type {string} */ projectId) => usePipelineMutation(projectId, (id) => api.del(`/steps/${id}`));

export const useReorder = (/** @type {string} */ projectId, /** @type {string} */ pipelineId) =>
  usePipelineMutation(projectId, (stepIds) => api.post(`/pipeline/${pipelineId}/reorder`, { step_ids: stepIds }));

export const usePipelineAction = (/** @type {string} */ projectId, /** @type {string} */ pipelineId) =>
  usePipelineMutation(projectId, (/** @type {'undo'|'redo'|'reset'} */ action) => api.post(`/pipeline/${pipelineId}/${action}`));

export const useSetSplit = (/** @type {string} */ projectId, /** @type {string} */ pipelineId) =>
  usePipelineMutation(projectId, (config) => api.put(`/pipeline/${pipelineId}/split`, config));

export const useRecipes = () => useQuery({ queryKey: keys.recipes, queryFn: () => api.get('/recipes') });

export function useSaveRecipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (/** @type {object} */ body) => api.post('/recipes', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.recipes }),
  });
}

export const useApplyRecipe = (/** @type {string} */ projectId) =>
  usePipelineMutation(projectId, (recipeId) => api.post(`/projects/${projectId}/apply-recipe`, { recipe_id: recipeId }));

export const useColumnDetail = (/** @type {string | undefined} */ versionId, /** @type {string | null} */ name) =>
  useQuery({
    queryKey: keys.columnDetail(versionId ?? '', name ?? ''),
    queryFn: () => api.get(`/versions/${versionId}/columns/${encodeURIComponent(name ?? '')}/detail`),
    enabled: !!versionId && !!name,
    staleTime: Infinity,
  });

export const useChart = (/** @type {string} */ versionId) =>
  useMutation({ mutationFn: (/** @type {object} */ spec) => api.post(`/versions/${versionId}/chart`, spec) });
