import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { keys, useJob, useUploadDataset } from '../../api/hooks.js';
import { Button, Card, ErrorBox, Input, ProgressBar } from '../../components/ui.jsx';

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xls,.parquet';

/** @param {{projectId: string, lastError?: string | null}} props */
export function UploadPanel({ projectId, lastError }) {
  const [file, setFile] = useState(/** @type {File | null} */ (null));
  const [drag, setDrag] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [options, setOptions] = useState({ delimiter: '', encoding: '', sheet_name: '', header_row: '' });
  const [jobId, setJobId] = useState(/** @type {string | null} */ (null));
  const upload = useUploadDataset(projectId);
  const job = useJob(jobId);
  const qc = useQueryClient();

  const status = job.data?.status;
  useEffect(() => {
    // The project now has a dataset; refetching swaps this panel for the workspace.
    if (status === 'succeeded') {
      qc.invalidateQueries({ queryKey: keys.project(projectId) });
      qc.invalidateQueries({ queryKey: ['storage'] });
    }
  }, [status, qc, projectId]);

  const start = () => {
    if (!file) return;
    const opts = Object.fromEntries(Object.entries(options).filter(([, v]) => v !== ''));
    if (opts.header_row) opts.header_row = Number(opts.header_row);
    upload.mutate({ file, options: opts }, { onSuccess: (r) => setJobId(r.job_id) });
  };

  const running = upload.isPending || (jobId && !['succeeded', 'failed', 'cancelled'].includes(status));

  return (
    <Card title="Upload a dataset" className="mx-auto max-w-2xl">
      <div className="space-y-4">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
          }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition ${
            drag ? 'border-accent bg-accent/5' : 'border-border hover:border-accent/60'
          }`}
        >
          <input type="file" accept={ACCEPT} className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <span className="text-2xl" aria-hidden>
            ⇪
          </span>
          {file ? (
            <span className="font-medium">
              {file.name} <span className="text-muted">({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
            </span>
          ) : (
            <>
              <span className="font-medium">Drop a file here or click to choose</span>
              <span className="text-sm text-muted">CSV, TSV, Excel (.xlsx/.xls) or Parquet, up to 200 MB</span>
            </>
          )}
        </label>

        <button className="text-sm text-muted hover:text-fg" onClick={() => setShowOptions(!showOptions)}>
          {showOptions ? '▾' : '▸'} Load options (auto-detected if empty)
        </button>
        {showOptions && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['delimiter', 'Delimiter (e.g. ; or \\t)'],
              ['encoding', 'Encoding (e.g. latin-1)'],
              ['sheet_name', 'Excel sheet name'],
              ['header_row', 'Header row (0 = first)'],
            ].map(([k, label]) => (
              <Input
                key={k}
                placeholder={label}
                aria-label={label}
                value={/** @type {any} */ (options)[k]}
                onChange={(e) => setOptions({ ...options, [k]: k === 'delimiter' ? e.target.value.replace('\\t', '\t') : e.target.value })}
              />
            ))}
          </div>
        )}

        {jobId && job.data && (
          <div className="space-y-1.5">
            <ProgressBar value={job.data.progress} />
            <p className="text-sm text-muted">{job.data.message}</p>
          </div>
        )}
        <ErrorBox error={upload.error ?? (status === 'failed' ? { message: job.data.error } : lastError ? { message: lastError } : null)} />

        <div className="flex justify-end">
          <Button variant="primary" disabled={!file} loading={!!running} onClick={start}>
            Upload and profile
          </Button>
        </div>
      </div>
    </Card>
  );
}
