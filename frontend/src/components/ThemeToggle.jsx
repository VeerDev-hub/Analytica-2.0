import { useEffectiveTheme, useThemeStore } from '../store/theme.js';
import { Icon } from './icons.jsx';

/** One click flips between light and dark. "Follow my computer" lives in Account. */
export function ThemeToggle() {
  const theme = useEffectiveTheme();
  const setMode = useThemeStore((s) => s.setMode);
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      onClick={() => setMode(next)}
      className="rounded-md p-1.5 text-muted transition hover:bg-subtle hover:text-fg"
      title={`Switch to ${next} mode`}
      aria-label={`Switch to ${next} mode`}
    >
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={16} />
    </button>
  );
}
