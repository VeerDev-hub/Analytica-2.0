import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, refreshSession } from '../../api/client.js';
import { useAuthStore } from '../../store/auth.js';
import { Button, ErrorBox, Field, Input, Spinner } from '../../components/ui.jsx';
import { Logo, LogoMark } from '../../components/Logo.jsx';
import { GitHubIcon, GoogleIcon } from '../../components/icons.jsx';
import { ThemeToggle } from '../../components/ThemeToggle.jsx';
import { PasswordField } from '../../components/PasswordField.jsx';

const OAUTH_ERRORS = {
  OAUTH_FAILED: 'Sign-in was cancelled or could not be verified. Please try again.',
  SIGNUPS_CLOSED: 'New sign-ups are closed. Ask the administrator for an invite.',
  ACCOUNT_DISABLED: 'This account has been disabled by an administrator.',
  OAUTH_NOT_CONFIGURED: 'That sign-in method is not set up on this server yet.',
};

/** @param {{mode: 'login' | 'register'}} props */
export function AuthPage({ mode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const [form, setForm] = useState({ email: '', password: '', display_name: '' });
  const [error, setError] = useState(/** @type {any} */ (null));
  const [busy, setBusy] = useState(false);
  const meta = useQuery({ queryKey: ['authProviders'], queryFn: () => api.get('/auth/providers') });
  const isLogin = mode === 'login';
  const oauthError = params.get('error');
  const providers = meta.data?.providers ?? [];

  // Clear a stale error when switching between sign-in and sign-up.
  const [shownMode, setShownMode] = useState(mode);
  if (shownMode !== mode) {
    setShownMode(mode);
    setError(null);
  }

  const submit = async (/** @type {import('react').FormEvent} */ e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = isLogin ? { email: form.email, password: form.password } : form;
      setSession(await api.post(`/auth/${mode}`, body));
      navigate(location.state?.from ?? '/projects', { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const set = (/** @type {string} */ k) => (/** @type {any} */ e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="flex items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/" aria-label="Analytica Studio home">
          <Logo />
        </Link>
        <ThemeToggle />
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-card sm:p-8">
          <h1 className="text-2xl font-semibold tracking-tight">{isLogin ? 'Sign in' : 'Create your account'}</h1>
          <p className="mt-1 text-sm text-muted">{isLogin ? 'Continue to your projects.' : 'Free to start. No credit card needed.'}</p>

          {oauthError && (
            <div className="mt-4">
              <ErrorBox error={{ message: OAUTH_ERRORS[/** @type {keyof OAUTH_ERRORS} */ (oauthError)] ?? 'Sign-in failed. Please try again.' }} />
            </div>
          )}

          <div className="mt-6 space-y-2.5">
            <OAuthButton provider="google" label="Continue with Google" icon={<GoogleIcon />} enabled={providers.includes('google')} loading={meta.isPending} />
            <OAuthButton provider="github" label="Continue with GitHub" icon={<GitHubIcon />} enabled={providers.includes('github')} loading={meta.isPending} />
          </div>

          <div className="my-6 flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-border" /> or with email <span className="h-px flex-1 bg-border" />
          </div>

          <form onSubmit={submit} className="space-y-4">
            {!isLogin && <Field label="Name">{(id) => <Input id={id} required value={form.display_name} onChange={set('display_name')} autoComplete="name" />}</Field>}
            <Field label="Email">{(id) => <Input id={id} type="email" required value={form.email} onChange={set('email')} autoComplete="email" />}</Field>
            {isLogin ? (
              <Field label="Password">{(id) => <Input id={id} type="password" required value={form.password} onChange={set('password')} autoComplete="current-password" />}</Field>
            ) : (
              <PasswordField value={form.password} onChange={(v) => setForm({ ...form, password: v })} email={form.email} name={form.display_name} />
            )}
            <ErrorBox error={error} />
            <Button variant="primary" className="h-10 w-full" loading={busy} type="submit">
              {isLogin ? 'Sign in' : 'Create account'}
            </Button>
          </form>

          {!isLogin && meta.data && !meta.data.signups_open && <p className="mt-3 text-xs text-warn">New sign-ups are currently closed by the administrator.</p>}

          {!isLogin && <p className="mt-3 text-xs text-muted">Temporary or disposable email addresses can't be used, and one mailbox can hold one account.</p>}

          <p className="mt-6 text-center text-sm text-muted">
            {isLogin ? 'New to Analytica? ' : 'Already have an account? '}
            <Link className="font-medium text-accent hover:underline" to={isLogin ? '/register' : '/login'}>
              {isLogin ? 'Create an account' : 'Sign in'}
            </Link>
          </p>
        </div>
      </main>

      <footer className="px-4 py-4 text-center text-xs text-muted">
        Google and GitHub share only your name, email and profile picture. Your datasets stay private to your account.
      </footer>
    </div>
  );
}

/** @param {{provider: string, label: string, icon: import('react').ReactNode, enabled: boolean, loading: boolean}} props */
function OAuthButton({ provider, label, icon, enabled, loading }) {
  const cls = 'flex h-10 w-full items-center justify-center gap-2.5 rounded-md border border-border bg-surface text-sm font-medium transition-colors';
  if (!enabled) {
    return (
      <button type="button" disabled className={`${cls} cursor-not-allowed opacity-50`} title={loading ? '' : 'Not set up on this server yet (Admin → Settings explains how)'}>
        {icon} {label}
        {!loading && <span className="text-[10px] font-normal text-muted">· not set up</span>}
      </button>
    );
  }
  // Full-page navigation: the API redirects to the provider and back.
  return (
    <a href={`/api/v1/auth/oauth/${provider}/start`} className={`${cls} hover:bg-subtle`}>
      {icon} {label}
    </a>
  );
}

/** Landing page after Google/GitHub: the API set the refresh cookie; exchange it. */
export function OAuthCallback() {
  const navigate = useNavigate();
  useEffect(() => {
    refreshSession().then((ok) => navigate(ok ? '/projects' : '/login?error=OAUTH_FAILED', { replace: true }));
  }, [navigate]);
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 text-muted">
      <LogoMark size={40} />
      <Spinner />
      <p className="text-sm">Signing you in…</p>
    </div>
  );
}
