import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client.js';
import { Icon } from '../../components/icons.jsx';

/** Public plan catalog + where the Upgrade button goes (set by an admin). */
export const usePlans = () => useQuery({ queryKey: ['plans'], queryFn: () => api.get('/plans'), staleTime: 5 * 60_000 });

export const planName = (/** @type {string | undefined} */ id) => (id ? id.charAt(0).toUpperCase() + id.slice(1) : 'Free');

/**
 * The three plans side by side. With `current` set (signed in) the matching card is marked and
 * the others offer an upgrade; without it (home page) every card leads to sign-up.
 * @param {{current?: string, compact?: boolean}} props
 */
export function PlanCards({ current, compact }) {
  const { data, isPending, error } = usePlans();
  if (error) return <p className="text-sm text-danger">Could not load plans.</p>;
  if (isPending || !data) return <div className="h-40 animate-pulse rounded-xl bg-subtle" />;
  const order = ['free', 'pro', 'business'];
  const rank = (/** @type {string} */ id) => order.indexOf(id);
  return (
    <div className={`grid gap-4 ${compact ? 'sm:grid-cols-3' : 'md:grid-cols-3'}`}>
      {data.plans.map((/** @type {any} */ p) => {
        const isCurrent = current === p.id;
        const highlight = p.id === 'pro';
        return (
          <div key={p.id} className={`flex flex-col rounded-xl border bg-surface ${compact ? 'p-4' : 'p-6'} ${highlight && !current ? 'border-accent' : 'border-border'} ${isCurrent ? 'ring-2 ring-accent/40' : ''}`}>
            <div className="flex items-center justify-between">
              <h3 className={`font-semibold ${compact ? 'text-base' : 'text-lg'}`}>{p.name}</h3>
              {isCurrent ? (
                <span className="rounded-md bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">Current plan</span>
              ) : highlight && !current ? (
                <span className="rounded-md bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">Most popular</span>
              ) : null}
            </div>
            <div className={`mt-2 flex items-baseline gap-1 ${compact ? '' : 'mt-3'}`}>
              <span className={`font-semibold tabular-nums ${compact ? 'text-2xl' : 'text-3xl'}`}>{p.price_month_usd === 0 ? 'Free' : `$${p.price_month_usd}`}</span>
              {p.price_month_usd > 0 && <span className="text-sm text-muted">/ month</span>}
            </div>
            {!compact && <p className="mt-2 text-sm text-muted">{p.tagline}</p>}
            <ul className={`space-y-1.5 text-sm ${compact ? 'mt-3' : 'mt-5'}`}>
              {p.features.map((/** @type {string} */ f) => (
                <li key={f} className="flex gap-2">
                  <Icon name="check" size={15} className="mt-0.5 shrink-0 text-ok" /> <span>{f}</span>
                </li>
              ))}
              {!p.assistant && (
                <li className="flex gap-2 text-muted">
                  <Icon name="close" size={15} className="mt-0.5 shrink-0" /> <span>AI assistant not included</span>
                </li>
              )}
            </ul>
            <div className={`${compact ? 'mt-4' : 'mt-6'} pt-2`}>
              <PlanAction plan={p} current={current} upgradeUrl={data.upgrade_url} rank={rank} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PlanAction({ plan, current, upgradeUrl, rank }) {
  const primary = 'inline-flex h-9 w-full items-center justify-center rounded-md bg-accent px-4 text-sm font-medium text-accent-fg hover:brightness-110';
  const secondary = 'inline-flex h-9 w-full items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium hover:bg-subtle';
  if (!current) {
    return (
      <Link to="/register" className={plan.id === 'pro' ? primary : secondary}>
        {plan.price_month_usd === 0 ? 'Start for free' : `Start with ${plan.name}`}
      </Link>
    );
  }
  if (current === plan.id) {
    return (
      <span className={`${secondary} cursor-default opacity-60`} aria-disabled>
        Your current plan
      </span>
    );
  }
  const isUpgrade = rank(plan.id) > rank(current);
  if (upgradeUrl) {
    return (
      <a href={upgradeUrl} target="_blank" rel="noreferrer" className={isUpgrade ? primary : secondary}>
        {isUpgrade ? `Upgrade to ${plan.name}` : `Switch to ${plan.name}`}
      </a>
    );
  }
  return <p className="text-center text-xs text-muted">Ask your administrator to change your plan.</p>;
}
