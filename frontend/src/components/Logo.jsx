// Analytica mark: an "A" whose crossbar is a three-node pipeline (data flowing through
// steps). The same drawing is used for the favicon (public/favicon.svg).
import { useId } from 'react';

/** @param {{size?: number, className?: string}} props */
export function LogoMark({ size = 32, className }) {
  // Unique gradient id per instance: a shared id breaks when the first copy is hidden.
  const gid = `an-bg-${useId().replace(/:/g, '')}`;
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} role="img" aria-label="Analytica">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fb923c" />
          <stop offset="1" stopColor="#ea580c" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gid})`} />
      <path d="M8.5 24.5 L16 7.5 L23.5 24.5" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11.6 18.5 H20.4" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" opacity="0.9" />
      <circle cx="11.6" cy="18.5" r="2.1" fill="#fff" />
      <circle cx="16" cy="18.5" r="2.1" fill="#fff" />
      <circle cx="20.4" cy="18.5" r="2.1" fill="#fff" />
      <circle cx="16" cy="18.5" r="0.9" fill="#ea580c" />
    </svg>
  );
}

/** Mark + wordmark. @param {{size?: number, subtitle?: boolean}} props */
export function Logo({ size = 28, subtitle = true }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="flex flex-col leading-none">
        <span className="text-[15px] font-semibold tracking-tight text-fg">Analytica</span>
        {subtitle && <span className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-muted">Studio</span>}
      </span>
    </span>
  );
}
