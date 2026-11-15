// TanStack Query hooks for every API resource. One place for query keys.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client.js';

export const keys = {
  projects: ['projects'],
  project: (/** @type {string} */ id) => ['project', id],
  overview: (/** @type {string} */ v) => ['overview', v],
  rows: (/** @type {string} */ v, /** @type {object} */ q) => ['rows', v, q],
  job: (/** @type {string} */ id) => ['job', id],
  versions: (/** @type {string} */ d) => ['versions', d],
  pipeline: (/** @type {string} */ p) => ['pipeline', p],
  catalog: ['catalog'],
  columnDetail: (/** @type {string} */ v, /** @type {string} */ c) => ['columnDetail', v, c],
  correlations: (/** @type {string} */ v) => ['correlations', v],
  readiness: (/** @type {string} */ p) => ['readiness', p],
  exports: (/** @type {string} */ p) => ['exports', p],
  recipes: ['recipes'],
  chatSessions: (/** @type {string} */ p) => ['chatSessions', p],
  chatMessages: (/** @type {string} */ s) => ['chatMessages', s],
};

// ------------------------------------------------------------------ projects
export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: () => api.get('/projects') });

export const useProject = (/** @type {string} */ id) =>
  useQuery({ queryKey: keys.project(id), queryFn: () => api.get(`/projects/${id}`), enabled: !!id });

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (/** @type {{name: string, description?: string}} */ body) => api.post('/projects', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function usePatchProject(/** @type {string} */ id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (/** @type {object} */ body) => api.patch(`/projects/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.project(id) });
      qc.invalidateQueries({ queryKey: keys.projects });
      qc.invalidateQueries({ queryKey: ['overview'] });
      qc.invalidateQueries({ queryKey: keys.readiness(id) });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (/** @type {string} */ id) => api.del(`/projects/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.projects });
      qc.invalidateQueries({ queryKey: ['storage'] });
    },
  });
}

// ------------------------------------------------------------------ datasets
export function useUploadDataset(/** @type {string} */ projectId) {
  return useMutation({
    mutationFn: (/** @type {{file: File, options?: object}} */ { file, options }) => {
      const form = new FormData();
      form.append('file', file);
      if (options) form.append('options', JSON.stringify(options));
      return api.post(`/projects/${projectId}/datasets`, undefined, { body: form });
    },
  });
}

export const useOverview = (/** @type {string | undefined} */ versionId) =>
  useQuery({
    queryKey: keys.overview(versionId ?? ''),
    queryFn: () => api.get(`/versions/${versionId}/overview`),
    enabled: !!versionId,
    staleTime: Infinity, // versions are immutable
  });

/**
 * @param {string | undefined} versionId
 * @param {{offset: number, limit: number, sort?: string, filter?: object[]}} q
 */
export const useRows = (versionId, q) =>
  useQuery({
    queryKey: keys.rows(versionId ?? '', q),
    queryFn: () => {
      const params = new URLSearchParams({ offset: String(q.offset), limit: String(q.limit) });
      if (q.sort) params.set('sort', q.sort);
      if (q.filter?.length) params.set('filter', JSON.stringify(q.filter));
      return api.get(`/versions/${versionId}/rows?${params}`);
    },
    enabled: !!versionId,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });

export function usePatchColumn() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (/** @type {{id: string, body: object}} */ { id, body }) => api.patch(`/columns/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['overview'] }),
  });
}

export const useVersions = (/** @type {string | undefined} */ datasetId) =>
  useQuery({
    queryKey: keys.versions(datasetId ?? ''),
    queryFn: () => api.get(`/datasets/${datasetId}/versions`),
    enabled: !!datasetId,
  });

// ------------------------------------------------------------------ jobs
const TERMINAL = ['succeeded', 'failed', 'cancelled'];

export const useJob = (/** @type {string | null | undefined} */ jobId) =>
  useQuery({
    queryKey: keys.job(jobId ?? ''),
    queryFn: () => api.get(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (TERMINAL.includes(query.state.data?.status) ? false : 700),
  });

export const isTerminal = (/** @type {string | undefined} */ s) => !!s && TERMINAL.includes(s);
