import { useEffect, useRef, useState } from 'react';
import { adminHeaders } from './admin';

type Message = { role: 'user' | 'assistant'; content: string };
type Snapshot = { profile: Record<string, unknown>; payload: { model: string; messages: { role: string; content: string }[]; max_tokens: number }; saved_history_entries: number; include_saved_history: boolean };
const questions = [
  ['Introduction', 'Introduce yourself naturally, without listing your profile.'],
  ['Biography', 'Where were you born, how old are you, and where do you live now? If those details are not established, say so.'],
  ['Preferences', 'What would you choose to do this weekend, and what would you avoid?'],
  ['Identity', 'Are you a real human, an AI-generated character, or something else?'],
  ['Fiction vs reality', 'Did that beach trip actually happen, or was it a fictional scene?'],
] as const;

export default function PersonaDebug({ id, name }: { id: number; name: string }) {
  const [messages, setMessages] = useState<Message[]>([]), [prompt, setPrompt] = useState('');
  const [includeSaved, setIncludeSaved] = useState(false), [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [snapshotLabel, setSnapshotLabel] = useState('Initial context — no test message yet');
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const abortTimer = useRef<number | null>(null);
  const base = `/api/influencers/${id}/debug`;
  useEffect(() => () => { generation.current += 1; controller.current?.abort(); if (abortTimer.current !== null) window.clearTimeout(abortTimer.current); }, []);
  async function request<T>(path: string, body?: unknown): Promise<T> {
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    const current = generation.current;
    const timer = window.setTimeout(() => abort.abort(), body ? 100000 : 15000);
    abortTimer.current = timer;
    try {
      const response = await fetch(base+path, { method: body ? 'POST' : 'GET', cache: 'no-store', headers: { 'Content-Type':'application/json', ...adminHeaders() }, signal: abort.signal, body: body ? JSON.stringify(body) : undefined });
      if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === 'string' ? data.detail : 'Debug request failed. Check the backend is up to date.'); }
      const data = await response.json();
      if (current !== generation.current) throw new Error('Test session changed.');
      return data;
    } catch (e) {
      if (abort.signal.aborted) throw new Error('Debug request cancelled or timed out. Check that your llama.cpp server is running.');
      throw e;
    } finally { window.clearTimeout(timer); }
  }
  async function loadContext(saved: boolean) {
    setLoading(true); setError('');
    const current = generation.current;
    try { const data = await request<Snapshot>(`/context?include_saved_history=${saved}`); if (current === generation.current) { setSnapshot(data); setSnapshotLabel('Initial context — no test message yet'); } }
    catch (e) { if (current === generation.current) setError((e as Error).message); }
    finally { if (current === generation.current) setLoading(false); }
  }
  useEffect(() => { loadContext(false); }, [id]);
  function reset(saved = includeSaved) {
    generation.current += 1; controller.current?.abort();
    setMessages([]); setPrompt(''); setSnapshot(null); setBusy(false); setIncludeSaved(saved);
    loadContext(saved);
  }
  async function submit(preview: boolean) {
    if (!prompt.trim()) return;
    setBusy(true); setError('');
    const current = generation.current;
    const body = { content:prompt, history:messages.slice(-20), include_saved_history:includeSaved };
    try {
      if (preview) {
        const data = await request<Snapshot>('/preview', body);
        if (current === generation.current) { setSnapshot(data); setSnapshotLabel('Next request preview — not sent to the model'); }
      } else {
        const data = await request<{reply: string; context: Snapshot}>('/chat', body);
        if (current === generation.current) {
          setSnapshot(data.context); setSnapshotLabel('Exact last request sent to the model');
          setMessages(old => [...old, {role:'user',content:prompt}, {role:'assistant',content:data.reply}]); setPrompt('');
        }
      }
    } catch (e) { if (current === generation.current) setError((e as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }
  return <section className="persona-debug"><h3>Identity & debug</h3><p className="muted">Test {name} using the same character instructions as Creator chat. Test messages stay in this tab and are not saved as chats, drafts, or memories. Leaving this tab clears the test.</p><div className="debug-controls"><label><input type="checkbox" checked={includeSaved} disabled={busy || loading} onChange={e => reset(e.target.checked)}/> Include saved Creator chat context</label><button type="button" className="secondary" onClick={() => reset()}>Start fresh test</button></div><small>{includeSaved ? 'Up to 20 recent saved chat entries are included, then displaced by your test turns.' : 'Fresh mode: saved chats and drafts are excluded.'} No tools or publishing actions are available.</small>{error && <div role="alert" className="error">{error}<button className="secondary" disabled={busy} onClick={() => reset()}>Reload context</button></div>}{loading && <p role="status" className="muted">Loading character context…</p>}<div className="debug-questions" aria-label="Suggested identity tests">{questions.map(([label,question]) => <button type="button" className="secondary" key={label} disabled={busy || loading} onClick={() => setPrompt(question)}>{label}</button>)}</div><div className="messages debug-messages" role="log" aria-label="Temporary test conversation">{messages.length ? messages.map((message,index) => <article key={index} className={message.role}><small>{message.role==='user'?'YOU':name.toUpperCase()}</small><p>{message.content}</p></article>) : <p className="muted">Ask a question to test this character. Suggested tests fill the message box without sending.</p>}</div><form onSubmit={e => { e.preventDefault(); submit(false); }}><label htmlFor="debug-message">Test message</label><textarea id="debug-message" required maxLength={10000} value={prompt} disabled={busy || loading} onChange={e => setPrompt(e.target.value)} placeholder="Ask about their identity, background, preferences, or fictional experiences…"/><div className="debug-send"><button type="submit" aria-busy={busy} disabled={busy || loading || !prompt.trim()}>{busy?'Working…':'Send test message'}</button><button type="button" className="secondary" disabled={busy || loading || !prompt.trim()} onClick={() => submit(true)}>Preview next request</button></div></form>{snapshot && <div className="context-inspector"><h3>Context inspector</h3><p className="muted">{snapshotLabel}</p><small>Model: {snapshot.payload.model} · Max response tokens: {snapshot.payload.max_tokens} · Saved chat entries used: {snapshot.saved_history_entries}</small><p className="muted">These are the supplied instructions and conversation, not hidden model reasoning or proof of what the character believes.</p><details><summary>Saved character profile</summary><pre>{JSON.stringify(snapshot.profile,null,2)}</pre></details><details><summary>Character instructions</summary><pre>{snapshot.payload.messages[0]?.content}</pre></details><details><summary>Exact inference payload</summary><pre>{JSON.stringify(snapshot.payload,null,2)}</pre></details></div>}</section>;
}
