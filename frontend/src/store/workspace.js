import { create } from 'zustand';

/**
 * Per-project UI state shared by the workspace tabs and the pipeline panel.
 * - jobs: the job started by the latest pipeline action, by project id
 * - draft: a step the user is configuring (opened from the catalog, an alert or chat)
 */
export const useWorkspaceStore = create((set) => ({
  /** @type {Record<string, string | null>} */ jobs: {},
  /** @type {{step_type: string, params: object, editStepId?: string} | null} */ draft: null,
  chatOpen: false,
  setJob: (/** @type {string} */ projectId, /** @type {string | null} */ jobId) =>
    set((s) => ({ jobs: { ...s.jobs, [projectId]: jobId } })),
  openDraft: (/** @type {{step_type: string, params: object, editStepId?: string}} */ draft) => set({ draft }),
  closeDraft: () => set({ draft: null }),
  setChatOpen: (/** @type {boolean} */ open) => set({ chatOpen: open }),
}));
