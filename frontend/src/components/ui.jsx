// Small shared UI kit. Colors come only from design tokens (styles/index.css).
import { useEffect, useId } from 'react';

const cx = (/** @type {any[]} */ ...c) => c.filter(Boolean).join(' ');
/** Full width unless the caller sets its own width. */
const widthOr = (/** @type {string | undefined} */ c) => (/(^|\s)(w-|min-w-|flex-1)/.test(c ?? '') ? '' : 'w-full');

const BUTTON = {
  primary: 'bg-accent text-accent-fg hover:brightness-110 disabled:opacity-50',
  secondary: 'border border-border bg-surface hover:bg-subtle disabled:opacity-50',
  ghost: 'hover:bg-subtle disabled:opacity-50',
  danger: 'bg-danger text-accent-fg hover:brightness-110 disabled:opacity-50',
};

/** @param {{variant?: keyof BUTTON, size?: 'sm'|'md', loading?: boolean} & import('react').ButtonHTMLAttributes<HTMLButtonElement>} props */
export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }) {
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition',
        size === 'sm' ? 'h-8 px-3 text-sm' : 'h-9 px-4 text-sm',
        BUTTON[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner size={14} />}
      {children}
    </button>
  );
}

/** @param {{size?: number}} props */
export function Spinner({ size = 18 }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-current border-r-transparent"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

/** @param {{title?: import('react').ReactNode, actions?: import('react').ReactNode, className?: string, children: import('react').ReactNode, padded?: boolean}} props */
export function Card({ title, actions, className, children, padded = true }) {
  return (
    <section className={cx('rounded-lg border border-border bg-surface', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={padded ? 'p-4' : ''}>{children}</div>
    </section>
  );
}

/** @param {{label: string, hint?: string, error?: string, children: (id: string) => import('react').ReactNode}} props */
export function Field({ label, hint, error, children }) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children(id)}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export const inputClass =
  'h-9 rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30';

/** @param {import('react').InputHTMLAttributes<HTMLInputElement>} props */
export function Input({ className, ...rest }) {
  return <input className={cx(inputClass, widthOr(className), className)} {...rest} />;
}

/** @param {import('react').SelectHTMLAttributes<HTMLSelectElement>} props */
export function Select({ className, children, ...rest }) {
  return (
    <select className={cx(inputClass, 'pr-8', widthOr(className), className)} {...rest}>
      {children}
    </select>
  );
}

const BADGE = {
  neutral: 'bg-subtle text-muted',
  accent: 'bg-accent/15 text-accent',
  ok: 'bg-ok/15 text-ok',
  warn: 'bg-warn/15 text-warn',
  danger: 'bg-danger/15 text-danger',
  info: 'bg-info/15 text-info',
};

/** @param {{tone?: keyof BADGE, children: import('react').ReactNode, title?: string}} props */
export function Badge({ tone = 'neutral', children, title }) {
  return (
    <span title={title} className={cx('inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium', BADGE[tone])}>
      {children}
    </span>
  );
}

export const SEVERITY_TONE = /** @type {const} */ ({ high: 'danger', medium: 'warn', low: 'info' });

export const TYPE_TONE = /** @type {Record<string, keyof BADGE>} */ ({
  numeric: 'info',
  nominal: 'accent',
  ordinal: 'accent',
  boolean: 'ok',
  datetime: 'warn',
  text: 'neutral',
  id: 'neutral',
  constant: 'danger',
  empty: 'danger',
});

/** @param {{error: any}} props */
export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {error.message ?? String(error)}
      {Array.isArray(error.details) && error.details.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs">
          {error.details.slice(0, 5).map((/** @type {any} */ d, /** @type {number} */ i) => (
            <li key={i}>{d.message ?? d.msg ?? JSON.stringify(d)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** @param {{icon?: string, title: string, children?: import('react').ReactNode}} props */
export function EmptyState({ icon = '◇', title, children }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border px-6 py-12 text-center">
      <div className="text-2xl text-muted" aria-hidden>
        {icon}
      </div>
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

/** @param {{value: number}} props */
export function ProgressBar({ value }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-subtle" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-accent transition-all" style={{ width: `${Math.max(2, value)}%` }} />
    </div>
  );
}

/** @param {{open: boolean, onClose: () => void, title: string, children: import('react').ReactNode, wide?: boolean}} props */
export function Modal({ open, onClose, title, children, wide }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (/** @type {KeyboardEvent} */ e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-[10vh]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx('w-full rounded-lg border border-border bg-surface shadow-xl', wide ? 'max-w-3xl' : 'max-w-md')}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="font-semibold">{title}</h2>
          <button className="rounded px-2 text-muted hover:bg-subtle" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

/** @param {{tabs: {id: string, label: string, badge?: import('react').ReactNode}[], value: string, onChange: (id: string) => void}} props */
export function Tabs({ tabs, value, onChange }) {
  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            '-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition',
            value === t.id ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg',
          )}
        >
          {t.label}
          {t.badge}
        </button>
      ))}
    </nav>
  );
}

/** @param {{label: string, value: import('react').ReactNode, sub?: import('react').ReactNode}} props */
export function Stat({ label, value, sub }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export const fmt = {
  int: (/** @type {number | null | undefined} */ n) => (n == null ? '—' : Number(n).toLocaleString()),
  num: (/** @type {number | null | undefined} */ n, d = 3) =>
    n == null ? '—' : Math.abs(n) >= 1e6 || (Math.abs(n) < 1e-3 && n !== 0) ? Number(n).toExponential(2) : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }),
  pct: (/** @type {number | null | undefined} */ n, d = 1) => (n == null ? '—' : `${Number(n).toFixed(d)}%`),
  bytes: (/** @type {number | null | undefined} */ n) => {
    if (n == null) return '—';
    const u = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let v = n;
    while (v >= 1024 && i < u.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
  },
};
