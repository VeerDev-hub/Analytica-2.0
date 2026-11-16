import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client.js';
import { BaselineCard, ExportsCard, ReadinessCard } from '../validate/ValidatePanel.jsx';
import { ChatBody } from '../chat/Chat.jsx';
import { SectionHeader, useProjectCtx } from './ProjectLayout.jsx';

export function ValidatePage() {
  const ctx = useProjectCtx();
  return (
    <div>
      <SectionHeader section="validate" ctx={ctx} showTarget />
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <ReadinessCard project={ctx.project} version={ctx.version} onFix={ctx.openStep} />
        <BaselineCard project={ctx.project} />
      </div>
    </div>
  );
}

export function ExportPage() {
  const ctx = useProjectCtx();
  return (
    <div>
      <SectionHeader section="export" ctx={ctx} />
      <ExportsCard project={ctx.project} />
    </div>
  );
}

export function AssistantPage() {
  const ctx = useProjectCtx();
  const status = useQuery({ queryKey: ['chatStatus'], queryFn: () => api.get('/chat/status'), staleTime: 60_000 });
  return (
    <div>
      <SectionHeader section="assistant" ctx={ctx} />
      <div className="flex h-[calc(100vh-190px)] min-h-[420px] flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-card">
        {status.data && !status.data.allowed ? (
          <div className="m-auto max-w-md p-6 text-center text-sm text-muted">
            <p className="font-medium text-fg">The assistant is part of the Pro and Business plans</p>
            <p className="mt-1">You're on the {status.data.plan_name} plan. Everything else in Analytica works without it: cleaning, features, validation and exports.</p>
            <div className="mt-4 flex justify-center gap-2">
              {status.data.upgrade_url && (
                <a href={status.data.upgrade_url} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-fg hover:brightness-110">
                  Upgrade
                </a>
              )}
              <Link to="/account#plan" className="inline-flex h-9 items-center rounded-md border border-border bg-surface px-4 text-sm font-medium hover:bg-subtle">
                Compare plans
              </Link>
            </div>
          </div>
        ) : status.data && !status.data.enabled ? (
          <div className="m-auto max-w-md p-6 text-center text-sm text-muted">
            <p className="font-medium text-fg">The assistant is turned off</p>
            <p className="mt-1">
              It needs <code className="font-mono">GEMINI_API_KEY</code> on the server, and an admin can switch it on or off in Admin → Settings.
            </p>
          </div>
        ) : (
          <ChatBody project={ctx.project} />
        )}
      </div>
    </div>
  );
}
