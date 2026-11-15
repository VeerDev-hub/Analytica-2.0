import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, refreshSession } from '../../api/client.js';
import { useAuthStore } from '../../store/auth.js';
import { Button, ErrorBox, Field, Input, Spinner } from '../../components/ui.jsx';
import { Logo, LogoMark } from '../../components/Logo.jsx';
import { GitHubIcon, GoogleIcon, Icon } from '../../components/icons.jsx';

const OAUTH_ERRORS = {
  OAUTH_FAILED: 'Sign-in was cancelled or could not be verified. Please try again.',
  SIGNUPS_CLOSED: 'New sign-ups are closed. Ask the administrator for an invite.',
  ACCOUNT_DISABLED: 'This account has been disabled by an administrator.',
  OAUTH_NOT_CONFIGURED: 'That sign-in method is not set up on this server yet.',
};

const FEATURES = [
  ['clean', 'Clean without code', 'Preview every fix on a sample, then apply. Undo anything.'],
  ['validate', 'No data leakage', 'Statistics are learned from training rows only, by design.'],
  ['assistant', 'Ask your data', 'Plain-language questions answered with queries you can check.'],
];

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
    <div className="grid min-h-screen bg-bg lg:grid-cols-2">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-[#1c1917] p-12 text-white lg:flex">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-orange-500/20 blur-3xl" aria-hidden />
        <div className="flex items-center gap-3">
          <LogoMark size={36} />
          <span className="text-lg font-semibold">Analytica Studio</span>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight">From messy spreadsheet to model-ready data.</h2>
          <p className="mt-3 text-white/70">Explore, clean and prepare datasets for machine learning, with every step recorded and reversible.</p>
          <ul className="mt-8 space-y-5">
            {FEATURES.map(([icon, t, d]) => (
              <li key={t} className="flex gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-orange-300">
                  <Icon name={/** @type {any} */ (icon)} />
                </span>
                <span>
                  <span className="block font-medium">{t}</span>
                  <span className="block text-sm text-white/60">{d}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-white/40">Your data stays private to your account.</p>
      </section>

      <section className="flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{isLogin ? 'Welcome back' : 'Create your account'}</h1>
          <p className="mt-1 text-sm text-muted">{isLogin ? 'Sign in to continue to your projects.' : 'Free to start. No credit card needed.'}</p>

          {oauthError && (
            <div className="mt-4">
              <ErrorBox error={{ message: OAUTH_ERRORS[/** @type {keyof OAUTH_ERRORS} */ (oauthError)] ?? 'Sign-in failed. Please try again.' }} />
            </div>
          )}

          <div className="mt-6 space-y-2.5">
            <OAuthButton provider="google" label="Continue with Google" icon={<GoogleIcon />} enabled={providers.includes('google')} loading={meta.isPending} />
            <OAuthButton provider="github" label="Continue with GitHub" icon={<GitHubIcon />} enabled={providers.includes('github')} loading={meta.isPending} />
          </div>
          <p className="mt-2 text-xs text-muted">
            We only read your name, email and profile picture. If an account with the same verified email exists, it’s linked automatically.
          </p>

          <div className="my-6 flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-border" /> or with email <span className="h-px flex-1 bg-border" />
          </div>

          <form onSubmit={submit} className="space-y-4">
            {!isLogin && <Field label="Name">{(id) => <Input id={id} value={form.display_name} onChange={set('display_name')} autoComplete="name" />}</Field>}
            <Field label="Email">{(id) => <Input id={id} type="email" required value={form.email} onChange={set('email')} autoComplete="email" />}</Field>
            <Field label="Password" hint={isLogin ? undefined : 'At least 8 characters'}>
              {(id) => (
                <Input id={id} type="password" required minLength={isLogin ? 1 : 8} value={form.password} onChange={set('password')} autoComplete={isLogin ? 'current-password' : 'new-password'} />
              )}
            </Field>
            <ErrorBox error={error} />
            <Button variant="primary" className="w-full" loading={busy} type="submit">
              {isLogin ? 'Sign in' : 'Create account'}
            </Button>
          </form>
          {!isLogin && meta.data && !meta.data.signups_open && <p className="mt-3 text-xs text-warn">New sign-ups are currently closed by the administrator.</p>}
          <p className="mt-6 text-center text-sm text-muted">
            {isLogin ? 'New to Analytica? ' : 'Already have an account? '}
            <Link className="font-medium text-accent hover:underline" to={isLogin ? '/register' : '/login'}>
              {isLogin ? 'Create an account' : 'Sign in'}
            </Link>
          </p>
        </div>
      </section>
    </div>
  );
}

/** @param {{provider: string, label: string, icon: import('react').ReactNode, enabled: boolean, loading: boolean}} props */
function OAuthButton({ provider, label, icon, enabled, loading }) {
  const cls = 'flex h-10 w-full items-center justify-center gap-2.5 rounded-md border border-border bg-surface text-sm font-medium transition';
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
    <a href={`/api/v1/auth/oauth/${provider}/start`} className={`${cls} hover:border-accent/60 hover:bg-subtle`}>
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
