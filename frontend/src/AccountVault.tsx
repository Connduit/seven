import { useEffect, useRef, useState } from 'react';
import { setAdminKey } from './admin';
import { accountRequest } from './accountRequest';
import OAuthAccounts from './OAuthAccounts';

type Account = { id: number; label: string; service: string; website: string; influencer_id: number | null };
type Connected = { id: number; username: string; influencer_id: number; expired: boolean; publishing_policy: string; daily_post_limit: number };
type Influencer = { id: number; name: string };
const empty = { label: '', service: 'Gmail', website: '', username: '', password: '', influencer_id: '' };

export default function AccountVault({ influencers }: { influencers: Influencer[] }) {
  const generation = useRef(0);
  const [unlocked, setUnlocked] = useState(false), [key, setKey] = useState('');
  const [accounts, setAccounts] = useState<Account[]>([]), [connected, setConnected] = useState<Connected[]>([]);
  const [form, setForm] = useState(empty), [editing, setEditing] = useState<number | null>(null);
  const [revealed, setRevealed] = useState<{ id: number; username: string; password: string } | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  async function request<T>(url: string, method = 'GET', body?: unknown): Promise<T> {
    const current = generation.current;
    const result = await accountRequest<T>(url, method, body);
    if (current !== generation.current) throw new Error('Vault locked. Unlock again to continue.');
    return result;
  }
  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function lock() {
    generation.current += 1;
    setAdminKey(''); setKey(''); setUnlocked(false); setRevealed(null); setForm(empty); setEditing(null); setAccounts([]); setConnected([]);
  }
  useEffect(() => {
    if (!unlocked) return;
    let timer = window.setTimeout(lock, 5 * 60 * 1000);
    const reset = () => { window.clearTimeout(timer); timer = window.setTimeout(lock, 5 * 60 * 1000); };
    document.addEventListener('pointerdown', reset);
    document.addEventListener('keydown', reset);
    return () => { window.clearTimeout(timer); document.removeEventListener('pointerdown', reset); document.removeEventListener('keydown', reset); };
  }, [unlocked]);
  useEffect(() => () => { generation.current += 1; setAdminKey(''); }, []);
  useEffect(() => {
    if (!revealed) return;
    const timer = window.setTimeout(() => setRevealed(null), 30000);
    return () => window.clearTimeout(timer);
  }, [revealed]);
  function owner(id: number | null) { return influencers.find(i => i.id === id)?.name || 'Workspace account'; }
  async function unlock(e: React.FormEvent) {
    e.preventDefault();
    await run(async () => {
      setAdminKey(key);
      try {
        const [saved, linked] = await Promise.all([request<Account[]>('/api/accounts/vault'), request<Connected[]>('/api/accounts/instagram')]);
        setAccounts(saved); setConnected(linked); setUnlocked(true); setKey('');
      } catch (e) { setAdminKey(''); throw e; }
    });
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    await run(async () => {
      const result = await request<Account>(editing === null ? '/api/accounts/vault' : `/api/accounts/vault/${editing}`, editing === null ? 'POST' : 'PUT', { ...form, influencer_id: form.influencer_id ? Number(form.influencer_id) : null });
      setAccounts(old => [...old.filter(a => a.id !== result.id), result].sort((a,b) => a.id-b.id));
      setForm(empty); setEditing(null); setRevealed(null);
    });
  }
  return <section className="page vault-page">
    <div className="heading"><div><div className="eyebrow">YOUR WORKSPACE ACCOUNTS</div><h1>Accounts & vault<span>.</span></h1><p>Manage social connections and saved account credentials in one place.</p></div>{unlocked && <button className="secondary" disabled={busy} onClick={lock}>Lock vault</button>}</div>
    {new URLSearchParams(window.location.search).has('oauth') && <p role="status" className="integration-note">{new URLSearchParams(window.location.search).get('result') === 'connected' ? 'Account connected. Unlock the vault to view it.' : 'Account authorization did not finish. It may have been cancelled, expired, or the account may already belong to another influencer. Unlock and try again.'}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!unlocked ? <div className="panel vault-unlock"><h2>Unlock your account vault</h2><p className="muted">Use your studio administrator key. Passwords stay encrypted in the database; credentials are never included in AI prompts.</p><form onSubmit={unlock}><label>Studio administrator key<input type="password" required autoComplete="off" value={key} onChange={e => setKey(e.target.value)}/></label><button aria-busy={busy} disabled={busy}>{busy ? 'Unlocking…' : 'Unlock vault'}</button></form><small>Requires STUDIO_ADMIN_KEY and TOKEN_ENCRYPTION_KEY on the backend. See the README for setup. Locks after 5 minutes of inactivity. Switching browser tabs keeps the vault unlocked.</small></div> : <>
      <OAuthAccounts influencers={influencers}/>
      <div className="section-title"><h2>Authorized Instagram accounts</h2><span>Official OAuth connections</span></div>
      {!connected.length ? <p className="integration-note">No authorized accounts yet. Open an influencer’s Overview to connect Instagram. Google, TikTok, and Snapchat connections are managed above.</p> : <div className="vault-grid">{connected.map(account => <article className="panel" key={account.id}><h3>Instagram · @{account.username}</h3><small>{owner(account.influencer_id)} · {account.expired ? 'Authorization expired' : 'Authorized'}</small><p className="muted">Publishing is not implemented yet.</p><label>Publishing policy<select disabled={busy} value={account.publishing_policy} onChange={e => { const policy = e.target.value; run(async () => { await request(`/api/influencers/${account.influencer_id}/instagram/${account.id}`, 'PATCH', { publishing_policy: policy, daily_post_limit: account.daily_post_limit }); setConnected(old => old.map(a => a.id === account.id ? { ...a, publishing_policy: policy } : a)); }); }}><option value="disabled">Disabled</option><option value="approval_required">Require approval (future publishing)</option></select></label><button className="secondary" disabled={busy} onClick={() => { if (window.confirm(`Disconnect @${account.username}? Remove this studio’s saved token?`)) run(async () => { await request(`/api/influencers/${account.influencer_id}/instagram/${account.id}`, 'DELETE'); setConnected(old => old.filter(a => a.id !== account.id)); }); }}>Disconnect</button></article>)}</div>}
      <div className="section-title"><h2>Saved account credentials</h2><span>{accounts.length} saved · Not API connections</span></div>
      <p className="integration-note">For Gmail, social networks, or other services. Saving login details does not connect the service, create an account, or authorize the AI to sign in. Use official OAuth connections for automation.</p>
      <div className="content"><div className="vault-grid">{accounts.map(account => <article className="panel vault-card" key={account.id}><h3>{account.label}</h3><small>{account.service} · {owner(account.influencer_id)}</small>{account.website && <a href={account.website} target="_blank" rel="noopener noreferrer">Open website ↗</a>}{revealed?.id === account.id ? <div className="revealed-credential"><small>Hidden automatically after 30 seconds</small><label>Username<input aria-label={`${account.label} username`} readOnly value={revealed.username}/></label><label>Password<input aria-label={`${account.label} password`} readOnly value={revealed.password}/></label></div> : <p className="muted">Username and password hidden</p>}<div className="tile-actions"><button className="secondary" disabled={busy} onClick={() => {
        if (revealed?.id === account.id) { setRevealed(null); return; }
        run(async () => { const data = await request<{ username: string; password: string }>(`/api/accounts/vault/${account.id}/reveal`, 'POST'); setRevealed({ id: account.id, ...data }); });
      }}>{revealed?.id === account.id ? 'Hide' : 'Reveal'}</button><button className="secondary" disabled={busy} onClick={() => run(async () => { const data = await request<Account & { username: string }>(`/api/accounts/vault/${account.id}/edit`); setEditing(account.id); setForm({ label: data.label, service: data.service, website: data.website, username: data.username, password: '', influencer_id: data.influencer_id === null ? '' : String(data.influencer_id) }); setRevealed(null); })}>Edit</button><button className="delete-action" disabled={busy} onClick={() => { if (window.confirm(`Delete saved credentials for ${account.label}? This cannot be undone and does not delete the account at the provider.`)) run(async () => { await request(`/api/accounts/vault/${account.id}`, 'DELETE'); setAccounts(old => old.filter(a => a.id !== account.id)); setRevealed(null); if (editing === account.id) { setEditing(null); setForm(empty); } }); }}>Delete</button></div></article>)}{!accounts.length && <div className="empty"><h3>No saved credentials yet</h3><p>Add an account using the form.</p></div>}</div>
      <div className="panel"><h2>{editing === null ? 'Save account credentials' : 'Edit saved account'}</h2><form onSubmit={save} autoComplete="off"><label>Account label<input required maxLength={100} value={form.label} onChange={e => setForm({...form, label:e.target.value})} placeholder="Maya’s Gmail"/></label><label>Service<input list="vault-services" required maxLength={100} value={form.service} onChange={e => setForm({...form, service:e.target.value})}/><datalist id="vault-services">{['Gmail','Instagram','Facebook','TikTok','YouTube','X','Bluesky','Reddit','Snapchat'].map(s => <option value={s} key={s}/>)}</datalist></label><label>Website (optional)<input type="url" maxLength={2048} value={form.website} onChange={e => setForm({...form, website:e.target.value})} placeholder="https://accounts.google.com"/></label><label>Assign to influencer<select value={form.influencer_id} onChange={e => setForm({...form, influencer_id:e.target.value})}><option value="">Workspace account</option>{influencers.map(i => <option value={i.id} key={i.id}>{i.name}</option>)}</select></label><label>Username or email<input required maxLength={1000} autoComplete="off" value={form.username} onChange={e => setForm({...form, username:e.target.value})}/></label><label>{editing === null ? 'Password' : 'New password (leave blank to keep existing)'}<input type="password" required={editing === null} maxLength={10000} autoComplete="new-password" value={form.password} onChange={e => setForm({...form, password:e.target.value})}/></label><button disabled={busy}>{busy ? 'Saving…' : 'Save encrypted credentials'}</button>{editing !== null && <button type="button" className="secondary" disabled={busy} onClick={() => { setEditing(null); setForm(empty); }}>Cancel editing</button>}</form></div></div>
    </>}
  </section>;
}
