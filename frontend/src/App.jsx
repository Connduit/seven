import { useEffect, useState, useCallback } from "react";

const api = async (path, method = "GET", body) => {
  const r = await fetch(`/api${path}`, {
    method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.detail || `${method} ${path} failed (${r.status})`); }
  return r.json();
};

const blank = { name: "", handle: "", core: "", goal: "", personality: "curious and friendly", life: "" };

export default function App() {
  const [personas, setPersonas] = useState([]);
  const [sel, setSel] = useState(null);
  const [memories, setMemories] = useState([]);
  const [queue, setQueue] = useState([]);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [imgUrls, setImgUrls] = useState({});
  const [ig, setIg] = useState({ ig_user_id: "", ig_token: "" });

  const load = useCallback(async () => {
    try {
      const ps = await api("/personas");
      setPersonas(ps);
      setQueue(await api("/queue"));
      if (sel) setMemories(await api(`/personas/${sel}/memories`));
      setErr("");
    } catch (e) { setErr(`${e.message}. Is the backend running on port 8100?`); }
  }, [sel]);

  useEffect(() => { load(); }, [load]);
  const persona = personas.find((p) => p.id === sel);

  const act = async (fn) => { setBusy(true); try { await fn(); await load(); } catch (e) { setErr(e.message); } setBusy(false); };
  const create = (e) => { e.preventDefault(); act(async () => { const p = await api("/personas", "POST", form); setForm(blank); setSel(p.id); }); };
  const patch = (field, value) => act(() => api(`/personas/${sel}`, "PATCH", { [field]: value }));

  return (
    <div className="app">
      <aside>
        <h1>Influencers</h1>
        {personas.length === 0 && <div className="empty">No personas yet. Create one below.</div>}
        {personas.map((p) => (
          <button key={p.id} className={`persona ${p.id === sel ? "on" : ""}`} onClick={() => setSel(p.id)}>
            {p.name}<small>{p.handle} {p.paused ? "(paused)" : ""}</small>
          </button>
        ))}
        <h2>New persona</h2>
        <form onSubmit={create}>
          <input placeholder="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Handle (@nova)" value={form.handle} onChange={(e) => setForm({ ...form, handle: e.target.value })} />
          <textarea placeholder="Core identity: values, backstory, voice, boundaries" required value={form.core} onChange={(e) => setForm({ ...form, core: e.target.value })} />
          <textarea placeholder="Goal (e.g. reach 100k followers, then monetize via newsletter)" required value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} />
          <textarea placeholder="Fictional life: where they live, what they do" value={form.life} onChange={(e) => setForm({ ...form, life: e.target.value })} />
          <button className="btn" disabled={busy}>Create persona</button>
        </form>
      </aside>
      <main>
        {err && <div className="card" role="alert">{err}</div>}
        <h2>Approval queue ({queue.length})</h2>
        {queue.length === 0 && <div className="empty">Nothing waiting. Run a step on a persona to generate a draft.</div>}
        {queue.map((i) => (
          <div className="card" key={i.id}>
            <div className="dim">{i.name} drafted:</div>
            <p>{i.content}</p>
            {i.image_prompt && <div className="dim">Image idea: {i.image_prompt}</div>}
            <input placeholder="Public image URL (required for Instagram)" value={imgUrls[i.id] || ""} onChange={(e) => setImgUrls({ ...imgUrls, [i.id]: e.target.value })} />
            <button className="btn ok" onClick={() => act(() => api(`/queue/${i.id}/approve`, "POST", { image_url: imgUrls[i.id] || "" }))}>Approve and post</button>
            <button className="btn alt" onClick={() => act(() => api(`/queue/${i.id}/reject`, "POST"))}>Reject</button>
          </div>
        ))}
        {persona ? (
          <>
            <h1 style={{ marginTop: 32 }}>{persona.name}</h1>
            <div className="row">
              <button className="btn" disabled={busy} onClick={() => act(() => api(`/personas/${sel}/tick`, "POST"))}>Run step</button>
              <button className="btn alt" disabled={busy} onClick={() => act(() => api(`/personas/${sel}/reflect`, "POST"))}>Reflect</button>
              <button className="btn alt" onClick={() => patch("paused", !persona.paused)}>{persona.paused ? "Resume" : "Pause"}</button>
              <select style={{ width: "auto", margin: 0 }} value={persona.autonomy} onChange={(e) => patch("autonomy", e.target.value)}>
                <option value="approve">Approve each post</option>
                <option value="auto">Post automatically</option>
              </select>
              <button className="btn alt" onClick={() => confirm(`Delete ${persona.name}?`) && act(async () => { await api(`/personas/${sel}`, "DELETE"); setSel(null); })}>Delete</button>
            </div>
            <h2>Core identity (fixed)</h2><div className="card">{persona.core}</div>
            <h2>Goal</h2><textarea key={`g${persona.goal}`} defaultValue={persona.goal} onBlur={(e) => e.target.value !== persona.goal && patch("goal", e.target.value)} />
            <h2>Evolving personality</h2><textarea key={`p${persona.personality}`} defaultValue={persona.personality} onBlur={(e) => e.target.value !== persona.personality && patch("personality", e.target.value)} />
            <h2>Instagram: {persona.ig_connected ? "connected" : "not connected (posts are dry runs)"}</h2>
            <input placeholder="Instagram account ID" value={ig.ig_user_id} onChange={(e) => setIg({ ...ig, ig_user_id: e.target.value })} />
            <input type="password" placeholder="Access token (stored locally, never shown again)" value={ig.ig_token} onChange={(e) => setIg({ ...ig, ig_token: e.target.value })} />
            <button className="btn alt" disabled={!ig.ig_user_id || !ig.ig_token} onClick={() => act(async () => { await api(`/personas/${sel}`, "PATCH", ig); setIg({ ig_user_id: "", ig_token: "" }); })}>Save Instagram login</button>
            <h2>Memory</h2>
            {memories.length === 0 && <div className="empty">No memories yet. Run a step to start the story.</div>}
            {memories.map((m) => (
              <div className="card" key={m.id}><span className="kind">{m.kind}</span>{m.content}</div>
            ))}
          </>
        ) : <div className="empty" style={{ marginTop: 32 }}>Select or create a persona to manage it.</div>}
      </main>
    </div>
  );
}
