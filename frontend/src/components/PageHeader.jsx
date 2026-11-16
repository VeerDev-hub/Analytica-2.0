/**
 * Title + one-line description on every page, with optional actions on the right.
 * @param {{title: string, description?: string, eyebrow?: string, actions?: import('react').ReactNode}} props
 */
export function PageHeader({ title, description, eyebrow, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
