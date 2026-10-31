import { useEffect, useRef, useState } from 'react';
import { adminHeaders } from './admin';

type Setup = { provider: string; name: string; description: string; configured: boolean; message: string };
type Connection = { id: number; provider: string; influencer_id: number; display_name: string; expired: boolean; expires_at: number };
export default function OAuthAccounts({ influencers }: { influencers: { id: number; name: string }[] }) {
  const [providers, setProviders] = useState<Setup[]>([]), [accounts, setAccounts] = useState<Connection[]>([]);
  const [owner, setOwner] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const active = useRef(false);
  async function request<T>(url: string, method = 'GET'): Promise<T> {
    const response = await fetch(url, { method, cache: 'no-store', headers: adminHeaders() });
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === 'string' ? data.detail : 'Connection request failed.'); }
    const data = response.status === 204 ? undefined as T : await response.json();
    if (!active.current) throw new Error('Account settings closed.');
    return data;
  }
  useEffect(() => {
    active.current = true;
    Promise.all([request<Setup[]>('/api/integrations/oauth/setup'), request<Connection[]>('/api/accounts/connections')]).then(([setup, linked]) => { if (active.current) { setProviders(setup); setAccounts(linked); } }).catch(e => { if (active.current) setError(e.message); }).finally(() => { if (active.current) setLoading(false); });
    return () => { active.current = false; };
  }, []);
  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (e) { if (active.current) setError((e as Error).message); } finally { if (active.current) setBusy(false); }
  }
  return <section className="oauth-accounts"><div className="section-title"><h2>Google, TikTok & Snapchat</h2><span>Official account authorization</span></div><p className="integration-note">Link account identities without sharing passwords. This does not enable Gmail access, posting, messaging, or autonomous actions.</p>{error && <p className="error" role="alert">{error}</p>}{loading && <p className="muted">Loading providers…</p>}<label>Influencer to connect<select value={owner} onChange={e => setOwner(e.target.value)} disabled={busy}><option value="">Choose an influencer</option>{influencers.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select></label>{!influencers.length && <p className="muted">Create an influencer first to assign an account.</p>}<div className="vault-grid">{providers.map(provider => <article key={provider.provider} className="panel"><h3>{provider.name}</h3><p className="muted">{provider.description}</p>{!provider.configured && <small>{provider.message}. Follow the provider setup guide in the README.</small>}<button disabled={busy || !owner || !provider.configured} onClick={() => run(async () => { const data = await request<{ authorization_url: string }>(`/api/influencers/${owner}/connections/${provider.provider}/connect`, 'POST'); window.location.assign(data.authorization_url); })}>Connect {provider.name}</button></article>)}</div>{accounts.length > 0 && <><h3>Linked accounts</h3><div className="vault-grid">{accounts.map(account => <article className="panel" key={account.id}><h3>{providers.find(p => p.provider === account.provider)?.name || account.provider} · {account.display_name}</h3><small>{influencers.find(i => i.id === account.influencer_id)?.name || 'Influencer unavailable'}</small><p className="muted">{account.expired ? 'Authorization expired. Reconnect to continue.' : `Authorization expires ${new Date(account.expires_at * 1000).toLocaleString()}`}</p><button disabled={busy} className="secondary" onClick={() => { if (window.confirm(`Disconnect ${account.display_name}? This removes locally stored tokens. You can revoke provider access in that service’s account settings.`)) run(async () => { await request(`/api/accounts/connections/${account.id}`, 'DELETE'); setAccounts(old => old.filter(a => a.id !== account.id)); }); }}>Disconnect</button></article>)}</div></>}<small>Developer app credentials and provider approval may be required. Disconnect clears local tokens; revoke the app’s access in provider settings to remove the authorization completely.</small></section>;
}
