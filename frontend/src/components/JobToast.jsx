import { useEffect } from 'react';
import { useMatch } from 'react-router-dom';
import { useActiveJob } from '../api/pipelineHooks.js';
import { isTerminal } from '../api/hooks.js';
import { ProgressBar } from './ui.jsx';

/** Bottom-right progress card for the current project's running pipeline job. */
export function JobToast() {
  const m = useMatch('/projects/:projectId/*');
  const projectId = m?.params.projectId ?? '';
  const { job, setJob } = useActiveJob(projectId);
  const done = isTerminal(job?.status);

  useEffect(() => {
    if (job?.status !== 'succeeded') return undefined;
    const t = setTimeout(() => setJob(null), 2500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  if (!projectId || !job) return null;
  return (
    <div className="fixed bottom-4 right-4 z-40 w-72 rounded-xl border border-border bg-surface shadow-pop p-3 shadow-lg" role="status">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="font-medium">{job.status === 'failed' ? 'Step failed' : done ? 'Done' : 'Working…'}</span>
        {done && (
          <button className="text-xs text-muted hover:text-fg" onClick={() => setJob(null)}>
            Dismiss
          </button>
        )}
      </div>
      {!done && <ProgressBar value={job.progress} />}
      <p className={`mt-1.5 text-xs ${job.status === 'failed' ? 'text-danger' : 'text-muted'}`}>{job.status === 'failed' ? job.error : job.message}</p>
    </div>
  );
}
