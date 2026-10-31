import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Sparkles, Plus, Users, MessageSquare, FileText, ArrowUpRight, Moon, Sun } from 'lucide-react';
import './style.css';

type Influencer = { id: number; name: string; personality: string; interests: string; goal: string; status: string };
type Entry = { id: number; kind: string; role: string; content: string; created_at: string };
const blank = { name: '', personality: '', interests: '', goal: '', status: 'paused' };
async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === 'string' ? error.detail : 'Request failed. Check your inputs and try again.'); }
  return response.json();
}
type Theme = 'light' | 'dark';
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem('studio-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* Storage is optional. */ }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
const startingTheme = initialTheme();
document.documentElement.dataset.theme = startingTheme;
function App() {
  const [theme, setTheme] = useState<Theme>(startingTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('studio-theme', theme); } catch { /* Keep working without storage. */ }
  }, [theme]);
  const [items, setItems] = useState<Influencer[]>([]), [selected, setSelected] = useState<number | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]), [tab, setTab] = useState('chat');
  const [form, setForm] = useState(blank), [editing, setEditing] = useState(false);
  const [prompt, setPrompt] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const item = items.find(i => i.id === selected);
  useEffect(() => { api<Influencer[]>('/influencers').then(setItems).catch(e => setError(e.message)); }, []);
  useEffect(() => {
    setEntries([]); setPrompt('');
    if (selected === null) return;
    let cancelled = false;
    api<Entry[]>(`/influencers/${selected}/entries`).then(data => { if (!cancelled) setEntries(data); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [selected]);
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { const result = await api<Influencer>(editing && item ? `/influencers/${item.id}` : '/influencers', editing && item ? 'PUT' : 'POST', form); setItems(old => [...old.filter(i => i.id !== result.id), result].sort((a,b) => a.id-b.id)); setSelected(result.id); setEditing(false); setForm(blank); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function send(e: React.FormEvent) {
    e.preventDefault(); if (!item) return; setBusy(true); setError('');
    try { await api(`/influencers/${item.id}/${tab === 'chat' ? 'chat' : 'drafts'}`, 'POST', { content: prompt }); setEntries(await api<Entry[]>(`/influencers/${item.id}/entries`)); setPrompt(''); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="layout"><aside><a className="brand" href="/"><Sparkles/> Studio<span>AI</span></a><div className="workspace">YOUR WORKSPACE</div><div className="nav"><Users size={18}/> Influencers <span>{items.length}</span></div><div className="sidebar-bottom"><div className="avatar">S</div><div>Creator workspace<small>Local development</small></div></div></aside>
    <main><header><span>Workspace <span className="muted">/ Influencers</span></span><div className="header-actions"><span className="pill">Phase 1 · Creator studio</span><button className="theme-toggle" type="button" aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}<span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span></button></div></header><section className="page"><div className="heading"><div><div className="eyebrow">YOUR CAST, YOUR CREATIVE WORLD</div><h1>Influencer studio<span>.</span></h1><p>Create distinct personalities. Give their stories a place to grow.</p></div><button disabled={busy} onClick={() => {setSelected(null);setEditing(false);setForm(blank);}}><Plus size={17}/> New influencer</button></div>
    <div className="stats"><div><span>YOUR CHARACTERS</span><strong>{items.length.toString().padStart(2,'0')}<Users/></strong></div><div><span>ACTIVE CHARACTERS</span><strong>{items.filter(i => i.status === 'active').length.toString().padStart(2,'0')}<Sparkles/></strong></div><div><span>PUBLISHING</span><strong className="smaller">Drafts only<ArrowUpRight/></strong></div></div>
    {error && <div role="alert" className="error">{error}</div>}
    <div className="section-title"><h2>Your influencers</h2><span>Fictional characters · AI generated</span></div>
    <div className="content"><div className="cast">{items.map((i,index) => <button disabled={busy} className={'character ' + (i.id === selected ? 'selected' : '')} key={i.id} onClick={() => {setSelected(i.id);setEditing(false);}}><div className={'portrait tone'+index%3}>{i.name.slice(0,1).toUpperCase()}<Sparkles size={18}/></div><div className="card-title"><h3>{i.name}</h3><span className={'status '+i.status}>{i.status}</span></div><p>{i.interests}</p><div className="goal">{i.goal}</div></button>)}{!items.length && <div className="empty"><Users size={30}/><h3>A new cast starts here</h3><p>Create your first fictional influencer to start a conversation and draft content.</p></div>}</div>
    <div className="panel">{!item || editing ? <><h2>{editing ? 'Edit character' : 'Meet your next character'}</h2><p className="muted">Define the identity. Explore the possibilities.</p><form onSubmit={save}>{(['name','personality','interests','goal'] as const).map(key => <label key={key}>{key === 'goal' ? 'Primary goal' : key}<textarea rows={key === 'name' ? 1 : 2} required maxLength={key === 'name' ? 100 : 10000} value={form[key]} onChange={e => setForm({...form,[key]:e.target.value})} placeholder={{name:'e.g. Maya Chen',personality:'Curious, witty, thoughtful…',interests:'Design, city life, sustainable fashion…',goal:'Build a community around creative living…'}[key]}/></label>)}<label>Status<select value={form.status} onChange={e=>setForm({...form,status:e.target.value})}><option value="paused">Paused</option><option value="active">Active</option><option value="archived">Archived</option></select></label><small>Status is organizational; autonomous actions are not enabled.</small><button disabled={busy} type="submit">{busy ? 'Saving…' : editing ? 'Save changes' : 'Create influencer'}<ArrowUpRight size={16}/></button></form></> : <><div className="panel-heading"><div><h2>{item.name}</h2><small>Fictional AI character</small></div><button disabled={busy} className="secondary" onClick={() => {setForm(item);setEditing(true);}}>Edit</button></div><p className="bio">{item.personality}</p><div className="tabs"><button disabled={busy} className={tab==='chat'?'chosen':''} onClick={()=>setTab('chat')}><MessageSquare size={16}/> Creator chat</button><button disabled={busy} className={tab==='draft'?'chosen':''} onClick={()=>setTab('draft')}><FileText size={16}/> Post drafts</button></div><div className="messages">{entries.filter(e=>e.kind===tab).map(e=><article className={e.role} key={e.id}><small>{e.kind==='draft'?'UNPUBLISHED DRAFT':e.role==='user'?'YOU':item.name.toUpperCase()}</small><p>{e.content}</p></article>)}{!entries.some(e=>e.kind===tab)&&<p className="muted">{tab==='chat'?'Get to know your character. Start a conversation.':'Give your character a brief to create an unpublished post.'}</p>}</div><form onSubmit={send}><label>{tab==='chat'?'Your message':'Creative brief'}<textarea required maxLength={10000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder={tab==='chat'?'What inspires you lately?':'Write a post introducing yourself…'}/></label><button disabled={busy}>{busy?'Generating…':tab==='chat'?'Send message':'Generate draft'}<Sparkles size={16}/></button></form></>}</div></div><footer><span className="dot"/> Creator-controlled workspace · All content stays in your studio</footer></section></main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
