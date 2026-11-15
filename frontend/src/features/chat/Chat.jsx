import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFetch } from '../../api/client.js';
import { keys } from '../../api/hooks.js';
import { useWorkspaceStore } from '../../store/workspace.js';
import { Badge, Button, Spinner, inputClass } from '../../components/ui.jsx';
import { Plot } from '../../components/Plot.jsx';

/** Chat about the current dataset version (design 4.5). Answers stream in; each query the
 * assistant ran is shown with its rows; proposed steps need an explicit Approve. */

/** @param {{project: any}} props */
export function ChatBody({ project }) {
  const qc = useQueryClient();
  const sessions = useQuery({ queryKey: keys.chatSessions(project.id), queryFn: () => api.get(`/projects/${project.id}/chat/sessions`) });
  const [sessionId, setSessionId] = useState(/** @type {string | null} */ (null));
  const activeId = sessionId ?? sessions.data?.[0]?.id ?? null;
  const create = useMutation({
    mutationFn: () => api.post(`/projects/${project.id}/chat/sessions`),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: keys.chatSessions(project.id) });
      setSessionId(s.id);
    },
  });

  if (sessions.isPending) return <Spinner />;
  return (
    <>
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <select
          className={`${inputClass} h-8 w-full`}
          value={activeId ?? ''}
          onChange={(e) => setSessionId(e.target.value)}
          aria-label="Conversation"
          disabled={!sessions.data?.length}
        >
          {!sessions.data?.length && <option value="">No conversations yet</option>}
          {sessions.data?.map((/** @type {any} */ s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={() => create.mutate()} loading={create.isPending}>
          New
        </Button>
      </div>
      {activeId ? <Conversation key={activeId} sessionId={activeId} project={project} /> : <Starter onStart={() => create.mutate()} />}
    </>
  );
}

/** @param {{onStart: () => void}} props */
function Starter({ onStart }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center text-sm text-muted">
      <p>Ask questions about your data in plain language. Every number comes from a query you can inspect.</p>
      <Button variant="primary" onClick={onStart}>
        Start a conversation
      </Button>
    </div>
  );
}

const EXAMPLES = ['Which columns have the most missing values?', 'How does the target differ across categories?', 'What should I clean before training a model?'];

/** @param {{sessionId: string, project: any}} props */
function Conversation({ sessionId, project }) {
  const qc = useQueryClient();
  const history = useQuery({ queryKey: keys.chatMessages(sessionId), queryFn: () => api.get(`/chat/sessions/${sessionId}/messages`) });
  const [draft, setDraft] = useState('');
  const [live, setLive] = useState(/** @type {any | null} */ (null));
  const scroller = useRef(/** @type {HTMLDivElement | null} */ (null));

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [history.data, live]);

  const send = async (/** @type {string} */ text) => {
    const content = text.trim();
    if (!content || live) return;
    setDraft('');
    const state = { question: content, text: '', tools: /** @type {any[]} */ ([]), citations: /** @type {any[]} */ ([]), error: null };
    setLive({ ...state });
    try {
      const res = await apiFetch(`/chat/sessions/${sessionId}/messages`, { method: 'POST', json: { content }, raw: true });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error?.message ?? `Request failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          const ev = JSON.parse(part.slice(6));
          if (ev.type === 'text') state.text += ev.delta;
          else if (ev.type === 'tool') state.tools.push({ name: ev.name, input: ev.input });
          else if (ev.type === 'tool_done' && ev.citation) state.citations.push(ev.citation);
          else if (ev.type === 'error') state.error = ev.message;
          setLive({ ...state, tools: [...state.tools], citations: [...state.citations] });
        }
      }
    } catch (e) {
      state.error = /** @type {Error} */ (e).message;
      setLive({ ...state });
      return;
    }
    await qc.invalidateQueries({ queryKey: keys.chatMessages(sessionId) });
    qc.invalidateQueries({ queryKey: keys.chatSessions(project.id) });
    setLive(null);
  };

  const msgs = history.data ?? [];
  return (
    <>
      <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {msgs.length === 0 && !live && (
          <div className="space-y-2">
            <p className="text-sm text-muted">Try:</p>
            {EXAMPLES.map((q) => (
              <button key={q} onClick={() => send(q)} className="block w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:border-accent">
                {q}
              </button>
            ))}
          </div>
        )}
        {msgs.map((/** @type {any} */ m) => (m.role === 'user' ? <UserBubble key={m.id} text={m.content} /> : <AssistantMessage key={m.id} message={m} project={project} sessionId={sessionId} />))}
        {live && (
          <>
            <UserBubble text={live.question} />
            <AssistantMessage message={{ content: live.text, citations: live.citations, tool_calls: live.tools }} streaming project={project} sessionId={sessionId} />
            {live.error && <p className="text-sm text-danger">{live.error}</p>}
          </>
        )}
      </div>
      <form
        className="flex gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <textarea
          className={`${inputClass} h-auto min-h-10 w-full resize-none py-2`}
          rows={2}
          placeholder="Ask about this dataset…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
          aria-label="Message"
        />
        <Button variant="primary" type="submit" disabled={!draft.trim() || !!live} className="self-end">
          Send
        </Button>
      </form>
    </>
  );
}

/** @param {{text: string}} props */
function UserBubble({ text }) {
  return <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-accent/15 px-3 py-2 text-sm">{text}</div>;
}

/** @param {{message: any, streaming?: boolean, project: any, sessionId: string}} props */
function AssistantMessage({ message, streaming, project, sessionId }) {
  const citations = message.citations ?? [];
  return (
    <div className="space-y-2 text-sm">
      <div className="whitespace-pre-wrap leading-relaxed">
        {message.content}
        {streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-muted align-middle" aria-hidden />}
      </div>
      {streaming && message.tool_calls?.length > citations.length && (
        <p className="flex items-center gap-2 text-xs text-muted">
          <Spinner size={12} /> Running {message.tool_calls[message.tool_calls.length - 1].name.replace('_', ' ')}…
        </p>
      )}
      {citations.map((/** @type {any} */ c, /** @type {number} */ i) => (
        <Citation key={i} c={c} />
      ))}
      {message.proposed_step && <ProposedStep message={message} project={project} sessionId={sessionId} />}
    </div>
  );
}

/** @param {{c: any}} props */
function Citation({ c }) {
  const [open, setOpen] = useState(false);
  if (c.type === 'chart') return <div className="rounded-md border border-border p-2"><Plot figure={c.figure} height={280} /></div>;
  const label = c.type === 'query' ? `Query: ${c.purpose || 'result'} (${c.row_count}${c.truncated ? '+' : ''} rows)` : `Dictionary search: “${c.query}”`;
  return (
    <div className="rounded-md border border-border">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs text-muted hover:text-fg" aria-expanded={open}>
        <Badge tone={c.type === 'query' ? 'info' : 'neutral'}>{c.type === 'query' ? 'SQL' : 'docs'}</Badge>
        <span className="truncate">{label}</span>
        <span className="ml-auto">{open ? '▾' : '▸'}</span>
      </button>
      {open && c.type === 'query' && (
        <div className="space-y-2 border-t border-border p-2">
          <pre className="overflow-x-auto rounded bg-subtle p-2 font-mono text-xs">{c.sql}</pre>
          <div className="max-h-56 overflow-auto">
            <table className="grid-table w-max min-w-full border-separate border-spacing-0 text-xs">
              <thead className="sticky top-0 bg-subtle">
                <tr>
                  {c.columns.map((/** @type {string} */ h) => (
                    <th key={h} className="px-2 py-1 text-left font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {c.rows.map((/** @type {any[]} */ r, /** @type {number} */ i) => (
                  <tr key={i}>
                    {r.map((v, j) => (
                      <td key={j} className="px-2 py-0.5 tabular-nums">
                        {v == null ? '∅' : String(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {open && c.type === 'dictionary' && (
        <ul className="space-y-1 border-t border-border p-2 text-xs">
          {c.hits.map((/** @type {any} */ h, /** @type {number} */ i) => (
            <li key={i}>{h.content}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** @param {{message: any, project: any, sessionId: string}} props */
function ProposedStep({ message, project, sessionId }) {
  const qc = useQueryClient();
  const setJob = useWorkspaceStore((s) => s.setJob);
  const p = message.proposed_step;
  const approve = useMutation({
    mutationFn: () => api.post(`/chat/messages/${message.id}/approve`),
    onSuccess: (r) => {
      setJob(project.id, r.job_id);
      qc.invalidateQueries({ queryKey: keys.chatMessages(sessionId) });
      qc.invalidateQueries({ queryKey: keys.pipeline(project.id) });
    },
  });
  return (
    <div className="rounded-md border border-accent/50 bg-accent/5 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-accent">Suggested step</div>
      <div className="mt-1 font-medium">{p.label}</div>
      {p.reason && <p className="mt-0.5 text-xs text-muted">{p.reason}</p>}
      {p.warnings?.map((/** @type {any} */ w, /** @type {number} */ i) => (
        <p key={i} className="mt-1 text-xs text-warn">
          ⚠ {w.message}
        </p>
      ))}
      <div className="mt-2 flex items-center gap-2">
        {p.status === 'applied' ? (
          <Badge tone="ok">Applied</Badge>
        ) : message.id ? (
          <Button size="sm" variant="primary" loading={approve.isPending} onClick={() => approve.mutate()}>
            Approve and apply
          </Button>
        ) : null}
        {approve.error && <span className="text-xs text-danger">{/** @type {any} */ (approve.error).message}</span>}
      </div>
    </div>
  );
}
