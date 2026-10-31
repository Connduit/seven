import { useEffect, useRef, useState } from 'react';
import { accountRequest } from './accountRequest';

type Setup = { provider: string; name: string; description: string; configured: boolean; message: string };
type Connection = { id: number; provider: string; influencer_id: number; display_name: string; expired: boolean; expires_at: number };
export default function OAuthAccounts({ influencers }: { influencers: { id: number; name: string }[] }) {
  const [providers, setProviders] = useState<Setup[]>([]), [accounts, setAccounts] = useState<Connection[]>([]);
  const [owner, setOwner] = useState(() => influencers.length === 1 ? String(influencers[0].id) : ''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const active = useRef(false);
  async function request<T>(url: string, method = 'GET'): Promise<T> {
    const data = await accountRequest<T>(url, method);
    if (!active.current) throw new Error('Account settings closed.');
    return data;
  }
  useEffect(() => {
    if (!influencers.some(i => String(i.id) === owner)) setOwner(influencers.length === 1 ? String(influencers[0].id) : '');
  }, [influencers, owner]);
  async function load() {
    setLoading(true); setError('');
    const [setup, linked] = await Promise.allSettled([request<Setup[]>('/api/integrations/oauth/setup'), request<Connection[]>('/api/accounts/connections')]);
    if (!active.current) return;
    if (setup.status === 'fulfilled') setProviders(setup.value);
    if (linked.status === 'fulfilled') setAccounts(linked.value);
    const failed = [setup, linked].filter(result => result.status === 'rejected');
    if (failed.length) setError(failed.map(result => result.status === 'rejected' ? String(result.reason.message) : '').join(' '));
    setLoading(false);
  }
  useEffect(() => {
    active.current = true;
    load();
    return () => { active.current = false; };
  }, []);
  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (e) { if (active.current) setError((e as Error).message); } finally { if (active.current) setBusy(false); }
  }
  return <section className="oauth-accounts"><div className="section-title"><h2>Google, TikTok & Snapchat</h2><button className="secondary" disabled={loading || busy} onClick={load}>Refresh status</button></div><p className="integration-note">Link account identities without sharing passwords. This does not enable Gmail access, posting, messaging, or autonomous actions.</p>{error && <div className="error" role="alert">{error}<button className="secondary" disabled={loading || busy} onClick={load}>Refresh connection status</button></div>}{loading && <p className="muted">Loading providers…</p>}<label htmlFor="oauth-influencer">Influencer to connect</label><select id="oauth-influencer" value={owner} onChange={e => setOwner(e.target.value)} disabled={busy || loading}><option value="">Choose an influencer</option>{influencers.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select>{!influencers.length && <p className="muted">Create an influencer first to assign an account.</p>}<div className="vault-grid">{providers.map(provider => <article key={provider.provider} className="panel"><h3>{provider.name}</h3><p className="muted">{provider.description}</p>{!provider.configured && <small>{provider.message}. Update backend/.env, restart FastAPI with --env-file .env, then refresh status. The README has the provider setup steps.</small>}<small className="connection-status" role="status">{!provider.configured ? 'Setup required — see the configuration message above.' : !owner ? 'Choose an influencer above to enable this connection.' : `Ready to connect for ${influencers.find(i => String(i.id) === owner)?.name}.`}</small><button aria-busy={busy} disabled={busy || loading || !owner || !provider.configured} onClick={() => run(async () => { const data = await request<{ authorization_url: string }>(`/api/influencers/${owner}/connections/${provider.provider}/connect`, 'POST'); window.location.assign(data.authorization_url); })}>{busy ? 'Working…' : `Connect ${provider.name}`}</button></article>)}</div>{accounts.length > 0 && <><h3>Linked accounts</h3><div className="vault-grid">{accounts.map(account => <article className="panel" key={account.id}><h3>{providers.find(p => p.provider === account.provider)?.name || account.provider} · {account.display_name}</h3><small>{influencers.find(i => i.id === account.influencer_id)?.name || 'Influencer unavailable'}</small><p className="muted">{account.expired ? 'Authorization expired. Reconnect to continue.' : `Authorization expires ${new Date(account.expires_at * 1000).toLocaleString()}`}</p><button disabled={busy} className="secondary" onClick={() => { if (window.confirm(`Disconnect ${account.display_name}? This removes locally stored tokens. You can revoke provider access in that service’s account settings.`)) run(async () => { await request(`/api/accounts/connections/${account.id}`, 'DELETE'); setAccounts(old => old.filter(a => a.id !== account.id)); }); }}>Disconnect</button></article>)}</div></>}<small>Developer app credentials and provider approval may be required. Disconnect clears local tokens; revoke the app’s access in provider settings to remove the authorization completely.</small></section>;
}
