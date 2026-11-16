import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { refreshSession } from '../../api/client.js';
import { useAuthStore } from '../../store/auth.js';
import { Logo, LogoMark } from '../../components/Logo.jsx';
import { Icon } from '../../components/icons.jsx';
import { ThemeToggle } from '../../components/ThemeToggle.jsx';
import { PROJECT_SECTIONS } from '../../app/sections.js';
import { PlanCards } from '../plans/PlanCards.jsx';

const NAV = [
  ['#features', 'Features'],
  ['#how-it-works', 'How it works'],
  ['#assistant', 'Assistant'],
  ['#pricing', 'Pricing'],
  ['#about', 'About'],
];

const FEATURES = [
  ['history', 'Versioned datasets', 'Every step produces an immutable version. Undo, redo, reorder or reset, and switch back to any earlier version at any time.'],
  ['validate', 'No data leakage', 'Steps that learn statistics (imputation, scaling, encoding, selection) are fitted on the training rows only, by design.'],
  ['clean', 'Preview before you apply', 'Each cleaning step can be run on a sample first, so you see exactly what changes before it touches the full dataset.'],
  ['export', 'Reproducible exports', 'Download the prepared data together with a Python script or notebook that reproduces it exactly, learned values included.'],
  ['recipes', 'Recipes', 'Save a pipeline and apply the same steps to another project with one click.'],
  ['status', 'Background jobs', 'Ingest, pipeline runs, baseline models and exports run in workers, with progress streamed to the page.'],
];

const PIPELINE = [
  ['Cleaning', 'Row-wise, stateless', ['drop_columns', 'keep_columns', 'rename_columns', 'change_type', 'trim_text', 'replace_values', 'drop_duplicates', 'drop_missing_rows', 'filter_rows', 'formula', 'datetime_features']],
  ['Split', 'Train / validation / test', ['split']],
  ['Fitted on train only', 'Encoding, scaling, selection', ['impute', 'outliers', 'rare_group', 'one_hot', 'ordinal', 'label_encode', 'target_encode', 'frequency_encode', 'hash_encode', 'scale', 'numeric_transform', 'binning', 'text_features', 'feature_select', 'pca']],
  ['Resampling', 'Class balance', ['random_under', 'random_over', 'smote', 'adasyn', 'tomek']],
];

const EXPORTS = [
  ['Dataset', 'CSV, Parquet, Excel, NumPy'],
  ['Script', 'Standalone pandas / scikit-learn Python file'],
  ['Notebook', 'Jupyter notebook (.ipynb)'],
  ['Pipeline', 'JSON definition of every step'],
  ['Model starters', 'PyTorch and TensorFlow templates'],
  ['Report', 'HTML summary of the dataset and pipeline'],
];

const STACK = [
  ['Frontend', 'React, Vite, Tailwind CSS, TanStack Query, Plotly'],
  ['API', 'Python, FastAPI, SQLAlchemy, Alembic'],
  ['Workers', 'Celery on Redis'],
  ['Data engine', 'pandas, NumPy, PyArrow, DuckDB, scikit-learn, imbalanced-learn'],
  ['Storage', 'PostgreSQL and S3-compatible object storage'],
  ['Assistant', 'Google Gemini with function calling and a read-only SQL sandbox'],
  ['Deployment', 'Docker Compose locally; Terraform for AWS (ECS Fargate, RDS, S3, CloudFront)'],
];

export function HomePage() {
  const user = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);
  useEffect(() => {
    if (status === 'unknown') refreshSession();
  }, [status]);

  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6">
          <Link to="/" aria-label="Analytica Studio home">
            <Logo />
          </Link>
          <nav className="hidden items-center gap-1 md:flex" aria-label="Sections">
            {NAV.map(([href, label]) => (
              <a key={href} href={href} className="rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-subtle hover:text-fg">
                {label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {user ? (
              <Link to="/projects" className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-accent-fg hover:brightness-110">
                Open your projects <Icon name="arrowRight" size={16} />
              </Link>
            ) : (
              <>
                <Link to="/login" className="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-fg/80 hover:bg-subtle hover:text-fg">
                  Sign in
                </Link>
                <Link to="/register" className="inline-flex h-9 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-fg hover:brightness-110">
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="border-b border-border">
          <div className="mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:py-24">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">No-code data preparation for machine learning</p>
              <h1 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-[-0.02em] sm:text-5xl">Get tabular data ready for machine learning, without writing code.</h1>
              <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
                Upload a CSV, Excel or Parquet file. Explore it, clean it, engineer features, check it is ready to train on, and export the prepared data along with the code that
                reproduces it.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                {user ? (
                  <Link to="/projects" className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-sm font-medium text-accent-fg hover:brightness-110">
                    Open your projects <Icon name="arrowRight" size={16} />
                  </Link>
                ) : (
                  <>
                    <Link to="/register" className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-sm font-medium text-accent-fg hover:brightness-110">
                      Create a free account <Icon name="arrowRight" size={16} />
                    </Link>
                    <Link to="/login" className="inline-flex h-11 items-center rounded-md border border-border bg-surface px-5 text-sm font-medium hover:bg-subtle">
                      Sign in
                    </Link>
                  </>
                )}
              </div>
              <p className="mt-4 text-sm text-muted">Free plan with 3 GB of storage. Email, Google or GitHub sign-in. Your datasets stay private to your account.</p>
            </div>
            <WorkflowDiagram />
          </div>
        </section>

        {/* Features */}
        <section id="features" className="scroll-mt-16 border-b border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <SectionHeading eyebrow="Features" title="Built for the part of ML that takes the longest" description="Preparing data is most of the work. Analytica keeps every change recorded, reversible and safe to train on." />
            <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(([icon, title, body]) => (
                <li key={title} className="rounded-xl border border-border bg-surface p-5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                    <Icon name={/** @type {any} */ (icon)} />
                  </span>
                  <h3 className="mt-4 font-semibold">{title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-16 border-b border-border bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <SectionHeading eyebrow="How it works" title="One project, one dataset, seven pages" description="Every project follows the same workflow. Each step has its own page in the sidebar." />
            <ol className="mt-10 grid gap-x-8 gap-y-6 md:grid-cols-2">
              {PROJECT_SECTIONS.map((s, i) => (
                <li key={s.id} className="flex gap-4">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-bg font-mono text-sm font-medium text-accent">{i + 1}</span>
                  <div>
                    <h3 className="flex items-center gap-2 font-semibold">
                      <Icon name={/** @type {any} */ (s.icon)} size={16} className="text-muted" /> {s.label}
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted">{s.description}</p>
                  </div>
                </li>
              ))}
            </ol>

            <div className="mt-14 rounded-xl border border-border bg-bg p-6">
              <h3 className="font-semibold">Pipeline steps</h3>
              <p className="mt-1 text-sm text-muted">Steps run in phases. Anything after the split is fitted on the training partition only.</p>
              <div className="mt-5 divide-y divide-border">
                {PIPELINE.map(([phase, note, steps]) => (
                  <div key={phase} className="grid gap-2 py-4 sm:grid-cols-[200px_1fr]">
                    <div>
                      <div className="text-sm font-medium">{phase}</div>
                      <div className="text-xs text-muted">{note}</div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {steps.map((st) => (
                        <code key={st} className="rounded-md border border-border bg-surface px-2 py-0.5 font-mono text-xs">
                          {st}
                        </code>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Assistant */}
        <section id="assistant" className="scroll-mt-16 border-b border-border">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:items-center">
            <div>
              <SectionHeading eyebrow="Assistant" title="Ask questions in plain language" description="The assistant answers from read-only SQL queries over your current dataset version. Every number it gives comes from a query you can open and check." />
              <ul className="mt-6 space-y-3 text-sm text-muted">
                {[
                  'It only sees the schema, column profiles and a small sample, never the whole file.',
                  'Queries run in a sandbox with no write access.',
                  'It can propose a cleaning step, which you approve before it runs.',
                ].map((t) => (
                  <li key={t} className="flex gap-2.5">
                    <Icon name="check" size={16} className="mt-0.5 shrink-0 text-ok" /> {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-border bg-surface p-5 text-sm">
              <div className="text-xs font-medium uppercase tracking-wider text-muted">Example</div>
              <p className="mt-3 rounded-lg bg-subtle px-3 py-2">Which plan has the highest churn rate?</p>
              <p className="mt-3 leading-relaxed">
                The <strong>basic</strong> plan has the highest churn rate at <strong>41.5%</strong> (83 of 200 customers), compared with 28.0% for standard and 19.5% for premium.
              </p>
              <details className="mt-3 rounded-lg border border-border">
                <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted">Show query</summary>
                <pre className="overflow-x-auto border-t border-border px-3 py-2 font-mono text-xs leading-relaxed text-muted">{`SELECT plan,
       AVG(churned) AS churn_rate,
       COUNT(*)     AS customers
FROM dataset
GROUP BY plan
ORDER BY churn_rate DESC`}</pre>
              </details>
            </div>
          </div>
        </section>

        {/* Exports */}
        <section className="border-b border-border bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <SectionHeading eyebrow="Export" title="Leave with the data and the code" description="Generated scripts embed the values learned during fitting, so running one on the original file reproduces the exported data exactly, without refitting." />
            <dl className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {EXPORTS.map(([kind, formats]) => (
                <div key={kind} className="rounded-xl border border-border bg-bg p-4">
                  <dt className="font-medium">{kind}</dt>
                  <dd className="mt-1 text-sm text-muted">{formats}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="scroll-mt-16 border-b border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <SectionHeading eyebrow="Pricing" title="Start free, upgrade when you need more" description="Every plan includes the full preparation workflow. Paid plans add storage and the AI assistant." />
            <div className="mt-10">
              <PlanCards current={user?.plan} />
            </div>
            <p className="mt-4 text-xs text-muted">Prices in USD per month. Storage counts uploads, every cleaning version and exports; “Free up space” in Account removes versions you no longer need.</p>
          </div>
        </section>

        {/* About */}
        <section id="about" className="scroll-mt-16 border-b border-border">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1.2fr]">
            <div>
              <SectionHeading eyebrow="About" title="What Analytica Studio is" />
              <div className="mt-5 space-y-4 text-sm leading-relaxed text-muted">
                <p>
                  Analytica Studio is a web application for getting tabular data ready for machine learning. It is aimed at analysts, students and data scientists who want a
                  recorded, repeatable preparation process without writing pandas by hand.
                </p>
                <p>
                  Version 2.0 rewrites the original single-user Streamlit app as a multi-user platform: a FastAPI API, Celery workers, PostgreSQL, S3 object storage and a React
                  frontend, deployable with Docker Compose locally or on AWS with Terraform.
                </p>
                <p>Accounts have per-user storage quotas, can be deleted at any time, and an admin console shows usage, users and settings.</p>
              </div>
            </div>
            <div className="rounded-xl border border-border bg-surface">
              <div className="border-b border-border px-5 py-3 text-sm font-semibold">Technology</div>
              <dl className="divide-y divide-border text-sm">
                {STACK.map(([layer, tech]) => (
                  <div key={layer} className="grid gap-1 px-5 py-3 sm:grid-cols-[130px_1fr]">
                    <dt className="font-medium">{layer}</dt>
                    <dd className="text-muted">{tech}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section>
          <div className="mx-auto max-w-6xl px-4 py-16 text-center sm:px-6">
            <h2 className="text-2xl font-semibold tracking-tight">Start with one file</h2>
            <p className="mt-2 text-muted">Create a project, upload a dataset, and work through the pages in order.</p>
            <div className="mt-6 flex justify-center gap-3">
              {user ? (
                <Link to="/projects" className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-sm font-medium text-accent-fg hover:brightness-110">
                  Open your projects <Icon name="arrowRight" size={16} />
                </Link>
              ) : (
                <>
                  <Link to="/register" className="inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-medium text-accent-fg hover:brightness-110">
                    Create a free account
                  </Link>
                  <Link to="/login" className="inline-flex h-11 items-center rounded-md border border-border bg-surface px-5 text-sm font-medium hover:bg-subtle">
                    Sign in
                  </Link>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-6 text-sm text-muted sm:px-6">
          <div className="flex items-center gap-2">
            <LogoMark size={22} /> <span>Analytica Studio</span>
          </div>
          <nav className="flex flex-wrap gap-4" aria-label="Footer">
            {NAV.map(([href, label]) => (
              <a key={href} href={href} className="hover:text-fg">
                {label}
              </a>
            ))}
            <Link to="/login" className="hover:text-fg">
              Sign in
            </Link>
            <Link to="/register" className="hover:text-fg">
              Create account
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}

/** @param {{eyebrow: string, title: string, description?: string}} props */
function SectionHeading({ eyebrow, title, description }) {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
      {description && <p className="mt-3 leading-relaxed text-muted">{description}</p>}
    </div>
  );
}

/** Static picture of a project's workflow: the six ordered pages plus the assistant alongside. */
function WorkflowDiagram() {
  const steps = PROJECT_SECTIONS.filter((s) => s.id !== 'assistant');
  const assistant = PROJECT_SECTIONS.find((s) => s.id === 'assistant');
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium uppercase tracking-wider text-muted">A project, start to finish</span>
        <span className="font-mono text-muted">churn.csv · v4</span>
      </div>
      <ol className="mt-4 space-y-2">
        {steps.map((s, i) => (
          <li key={s.id} className="flex items-center gap-3 rounded-lg border border-border bg-bg px-3 py-2.5">
            <span className="font-mono text-xs text-muted">0{i + 1}</span>
            <Icon name={/** @type {any} */ (s.icon)} size={16} className="text-accent" />
            <span className="text-sm font-medium">{s.label}</span>
            <span className="ml-auto hidden text-xs text-muted sm:block">
              {['600 rows · 8 columns', '2 quality alerts', '3 steps recorded', 'split 70 / 15 / 15', '9 of 9 checks pass', 'script + parquet'][i]}
            </span>
          </li>
        ))}
      </ol>
      {assistant && (
        <div className="mt-3 flex items-center gap-3 rounded-lg border border-dashed border-border px-3 py-2.5">
          <Icon name="assistant" size={16} className="text-accent" />
          <span className="text-sm font-medium">{assistant.label}</span>
          <span className="ml-auto text-xs text-muted">available on every page</span>
        </div>
      )}
    </div>
  );
}
