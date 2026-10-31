import { useEffect, useState } from 'react';

type SocialPage = { id: number; platform: string; url: string };
type Props = {
  item: { id: number; name: string; personality: string; interests: string; goal: string; status: string };
  entries: { kind: string; role: string; created_at: string }[];
  loading: boolean;
};
export default function Profile({ item, entries, loading }: Props) {
  const [pages, setPages] = useState<SocialPage[]>([]);
  const [platform, setPlatform] = useState('Instagram'), [url, setUrl] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [pagesLoading, setPagesLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/influencers/${item.id}/social-pages`).then(async r => {
      if (!r.ok) throw new Error('Could not load social pages.');
      return r.json();
    }).then(data => { if (!cancelled) setPages(data); }).catch(e => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setPagesLoading(false); });
    return () => { cancelled = true; };
  }, [item.id]);
  async function add(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(`/api/influencers/${item.id}/social-pages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform, url }) });
      if (!response.ok) { const data = await response.json(); throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the profile URL.'); }
      const page = await response.json(); setPages(old => [...old, page]); setUrl('');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function remove(id: number) {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/influencers/${item.id}/social-pages/${id}`, { method: 'DELETE' });
      if (!response.ok) throw new Error('Could not remove this page.');
      setPages(old => old.filter(p => p.id !== id));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const chats = entries.filter(e => e.kind === 'chat' && e.role === 'user').length;
  const drafts = entries.filter(e => e.kind === 'draft').length;
  const latest = entries.at(-1);
  return <div className="profile-overview"><dl className="profile-details"><dt>Status</dt><dd><span className={'status '+item.status}>{item.status}</span></dd><dt>Personality</dt><dd>{item.personality}</dd><dt>Interests</dt><dd>{item.interests}</dd><dt>Primary goal</dt><dd>{item.goal}</dd></dl><h3>Studio activity</h3><div className="profile-stats"><div><strong>{loading ? '…' : chats}</strong><small>Messages sent</small></div><div><strong>{loading ? '…' : drafts}</strong><small>Post drafts</small></div><div><strong>{pagesLoading ? '…' : pages.length}</strong><small>Social pages</small></div></div><small>Last activity: {loading ? 'Loading…' : latest ? new Date(latest.created_at).toLocaleString() : 'No activity yet'}</small><h3>Social media pages</h3><p className="muted">Save links to this character’s public profiles. Links do not authorize posting or connect analytics.</p>{error && <p role="alert" className="error">{error}</p>}{pagesLoading ? <p className="muted">Loading social pages…</p> : !pages.length ? <p className="muted">No social pages added yet.</p> : <ul className="social-pages">{pages.map(page => <li key={page.id}><a href={page.url} target="_blank" rel="noopener noreferrer">{page.platform}<small>{page.url}</small></a><button className="secondary" disabled={busy} aria-label={`Remove ${page.platform} page`} onClick={() => remove(page.id)}>Remove</button></li>)}</ul>}<form onSubmit={add}><label>Platform<select value={platform} onChange={e => setPlatform(e.target.value)}>{['Instagram','TikTok','YouTube','X','Bluesky','Reddit'].map(p => <option key={p}>{p}</option>)}</select></label><label>Public profile URL<input type="url" required maxLength={2048} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.instagram.com/yourcharacter/"/></label><button disabled={busy || pagesLoading}>{busy ? 'Saving…' : 'Add social page'}</button></form><h3>Audience analytics</h3><p className="muted">Followers, engagement, reach, and revenue are unavailable until platform integrations are implemented.</p></div>;
}
