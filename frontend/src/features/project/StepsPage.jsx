// Clean and Features pages: a step list on the left, the selected step's editor on the right.
import { useState } from 'react';
import { useCatalog, usePipeline } from '../../api/pipelineHooks.js';
import { Badge, Spinner } from '../../components/ui.jsx';
import { Icon } from '../../components/icons.jsx';
import { useWorkspaceStore } from '../../store/workspace.js';
import { StepEditor } from '../prepare/StepEditor.jsx';
import { defaultParams } from '../prepare/StepCatalog.jsx';
import { SplitCard } from '../features/FeatureStudio.jsx';
import { SectionHeader, useProjectCtx } from './ProjectLayout.jsx';

const GROUPS = {
  clean: [
    ['clean', 'Fix values'],
    ['rows', 'Rows'],
    ['columns', 'Columns'],
    ['feature', 'New columns'],
  ],
  features: [
    ['split', 'Split'],
    ['encode', 'Encode categories'],
    ['scale', 'Scale & transform'],
    ['resample', 'Balance classes'],
    ['select', 'Select & reduce'],
  ],
};

const INTRO = {
  clean: {
    title: 'Pick a cleaning step',
    points: [
      ['Preview first', 'Every step runs on a 1,000-row sample so you see before → after.'],
      ['Nothing is overwritten', 'Applying creates a new version. Undo any time from History.'],
      ['Replayable', 'Steps are recorded and can be saved as a recipe for new files.'],
    ],
  },
  features: {
    title: 'Prepare features for a model',
    points: [
      ['1. Split first', 'Mark rows as train / validation / test before anything learns from the data.'],
      ['2. Encode and scale', 'Turn categories into numbers and put numbers on similar scales.'],
      ['3. Balance if needed', 'Over/under-sample the training rows only, never the test rows.'],
    ],
  },
};

/** @param {{kind: 'clean' | 'features'}} props */
export function StepsPage({ kind }) {
  const ctx = useProjectCtx();
  const { data: catalog } = useCatalog();
  const { data: pl } = usePipeline(ctx.project.id);
  const draft = useWorkspaceStore((s) => s.draft);
  const openDraft = useWorkspaceStore((s) => s.openDraft);
  const closeDraft = useWorkspaceStore((s) => s.closeDraft);
  const [q, setQ] = useState('');
  const cats = GROUPS[kind].map(([c]) => c);
  const spec = draft && catalog?.find((/** @type {any} */ s) => s.step_type === draft.step_type);
  const draftHere = spec && cats.includes(spec.category);
  const showSplit = kind === 'features' && draft?.step_type === 'split' && !draft.editStepId;

  return (
    <div>
      <SectionHeader section={kind} ctx={ctx} showTarget={kind === 'features'} />
      <div className="flex flex-col gap-4 lg:flex-row">
        <aside className="lg:w-72 lg:shrink-0">
          <div className="rounded-xl border border-border bg-surface shadow-card">
            <div className="flex items-center gap-2 border-b border-border px-3 py-2">
              <Icon name="search" size={15} className="text-muted" />
              <input className="h-7 w-full bg-transparent text-sm outline-none" placeholder="Search steps" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search steps" />
            </div>
            {!catalog ? (
              <Spinner />
            ) : (
              <div className="max-h-[calc(100vh-250px)] overflow-y-auto p-1.5">
                {GROUPS[kind].map(([cat, label]) => {
                  const items = catalog.filter(
                    (/** @type {any} */ s) => s.category === cat && (s.label + s.explain).toLowerCase().includes(q.toLowerCase()),
                  );
                  if (!items.length) return null;
                  return (
                    <section key={cat} className="mb-1.5">
                      <h3 className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</h3>
                      {items.map((/** @type {any} */ s) => {
                        const active = draft?.step_type === s.step_type;
                        return (
                          <button
                            key={s.step_type}
                            onClick={() => openDraft({ step_type: s.step_type, params: defaultParams(s) })}
                            className={`block w-full rounded-md px-2 py-1.5 text-left transition ${active ? 'bg-accent/10' : 'hover:bg-subtle'}`}
                          >
                            <span className="flex items-center justify-between gap-2">
                              <span className={`text-sm ${active ? 'font-medium text-accent' : ''}`}>{s.label}</span>
                              {s.phase === 'post_split' && (
                                <Badge tone="info" title="Learns from training rows only">
                                  learns
                                </Badge>
                              )}
                            </span>
                            <span className="line-clamp-1 text-xs text-muted">{s.explain}</span>
                          </button>
                        );
                      })}
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        </aside>
        <section className="min-w-0 flex-1">
          {showSplit ? (
            <SplitCard project={ctx.project} overview={ctx.overview} onDone={closeDraft} />
          ) : draftHere && pl && ctx.overview ? (
            <StepEditor
              key={`${draft.step_type}:${draft.editStepId ?? ''}:${JSON.stringify(draft.params)}`}
              spec={spec}
              project={ctx.project}
              pipelineId={pl.id}
              columns={ctx.overview.columns}
              initial={draft.params}
              editStepId={draft.editStepId}
            />
          ) : (
            <Intro kind={kind} ctx={ctx} />
          )}
        </section>
      </div>
    </div>
  );
}

function Intro({ kind, ctx }) {
  const intro = INTRO[kind];
  const split = ctx.overview?.columns.some((/** @type {any} */ c) => c.name === '__split__');
  return (
    <div className="rounded-lg border border-dashed border-border p-8">
      <h2 className="text-lg font-semibold">{intro.title}</h2>
      <p className="mt-1 text-sm text-muted">Choose a step from the list. It opens here with its options and a preview.</p>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {intro.points.map(([t, d]) => (
          <div key={t} className="rounded-lg bg-surface p-4">
            <div className="text-sm font-medium">{t}</div>
            <p className="mt-1 text-xs text-muted">{d}</p>
          </div>
        ))}
      </div>
      {kind === 'features' && !split && (
        <p className="mt-6 rounded-md bg-accent/10 px-3 py-2 text-sm text-accent">
          This data isn’t split yet. Start with <b>Split → Train / validation / test split</b>.
        </p>
      )}
    </div>
  );
}
