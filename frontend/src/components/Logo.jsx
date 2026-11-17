// Analytica brand logo. The artwork lives in public/1.svg (for light mode) and public/2.svg
// (for dark mode); those files are ~2.7 MB each with opaque backgrounds, so the images here are
// transparent, cropped PNG cuts of them: the "A" mark and the "Analytica Studio" wordmark.
// public/favicon.svg carries the same mark for both colour schemes.
import { useEffectiveTheme } from '../store/theme.js';
import markLight from '../assets/brand/mark-light.png';
import markDark from '../assets/brand/mark-dark.png';
import wordmarkLight from '../assets/brand/wordmark-light.png';
import wordmarkDark from '../assets/brand/wordmark-dark.png';

/** The "A" mark on its own. @param {{size?: number, className?: string}} props */
export function LogoMark({ size = 32, className }) {
  const dark = useEffectiveTheme() === 'dark';
  return (
    <img
      src={dark ? markDark : markLight}
      width={size}
      height={size}
      className={className}
      alt="Analytica"
      draggable={false}
      style={{ width: size, height: size }}
    />
  );
}

/**
 * Mark + wordmark side by side, for headers.
 * `subtitle` is kept for older call sites; the wordmark artwork always includes "Studio".
 * @param {{size?: number, subtitle?: boolean}} props
 */
// eslint-disable-next-line no-unused-vars
export function Logo({ size = 28, subtitle = true }) {
  const dark = useEffectiveTheme() === 'dark';
  const h = Math.round(size * 1.1);
  return (
    <span className="inline-flex items-center gap-2">
      <LogoMark size={size} />
      <img
        src={dark ? wordmarkDark : wordmarkLight}
        alt="Analytica Studio"
        draggable={false}
        style={{ height: h, width: 'auto' }}
      />
    </span>
  );
}
