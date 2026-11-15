/**
 * Title + one-line description on every page, with optional actions on the right.
 * @param {{title: string, description?: string, eyebrow?: string, actions?: import('react').ReactNode}} props
 */
export function PageHeader({ title, description, eyebrow, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-0.5 text-xs font-medium text-muted">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
