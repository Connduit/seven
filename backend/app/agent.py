from . import db, llm, instagram

class PublishError(Exception):
    pass

def ig_connected(p):
    return bool(p.get('ig_user_id') and p.get('ig_token'))

RULES = ("You are an AI influencer and you are openly an AI; never claim to be human. "
         "Your fictional life is fiction and is presented as such. No fake reviews, no deceptive "
         "sales tactics, no false claims. Stay within your core identity and boundaries.")

def system_prompt(p):
    return (f"{RULES}\n\nCORE IDENTITY (never changes):\n{p['core']}\n\n"
            f"CURRENT PERSONALITY (evolves):\n{p['personality']}\n\n"
            f"FICTIONAL LIFE:\n{p['life']}\n\nLONG-TERM GOAL:\n{p['goal']}")

def recall(pid, n=10):
    rows = db.q("SELECT kind, content FROM memories WHERE persona_id=? ORDER BY ts DESC LIMIT ?", (pid, n))
    return "\n".join(f"[{r['kind']}] {r['content']}" for r in reversed(rows)) or "(no memories yet)"

def remember(pid, kind, content):
    db.run("INSERT INTO memories(persona_id,kind,content,ts) VALUES(?,?,?,?)", (pid, kind, content, db.now()))

def publish(p, caption, image_url=""):
    """Posts to Instagram if the persona has credentials, otherwise dry-run (console log)."""
    if ig_connected(p):
        if not image_url:
            raise PublishError("Instagram posts need an image. Paste a public image URL before approving.")
        try:
            instagram.publish_image(p["ig_user_id"], p["ig_token"], image_url, caption)
        except RuntimeError as e:
            raise PublishError(str(e))
    else:
        print(f"[DRY-RUN PUBLISH {p['name']}] {caption}")
    remember(p["id"], "post", caption)

def tick(pid):
    p = db.q("SELECT * FROM personas WHERE id=?", (pid,), one=True)
    if not p or p["paused"]:
        return {"skipped": True}
    user = (f"Recent memory:\n{recall(pid)}\n\nDo three things: (1) invent one small new event in your "
            "fictional life, (2) decide a short plan toward your goal, (3) write ONE Instagram caption plus a short image_prompt describing the photo "
            "(max 280 chars) in your voice. Reply ONLY JSON: "
            '{"event": "...", "plan": "...", "caption": "...", "image_prompt": "..."}')
    mock = {"event": f"{p['name']} had a small adventure today.",
            "plan": "Post consistently and engage with the audience.",
            "caption": f"hello from {p['name']}, an AI exploring the world. what should i learn next? #ai",
            "image_prompt": f"a cozy illustration of {p['name']}'s world"}
    out = llm.parse_json(llm.complete(system_prompt(p), user, mock), mock)
    remember(pid, "event", out["event"])
    remember(pid, "plan", out["plan"])
    # Auto-posting only for dry-run personas: Instagram needs an image, which you attach during approval.
    if p["autonomy"] == "auto" and not ig_connected(p):
        publish(p, out["caption"]); status = "published"
    else:
        status = "pending"
    qid = db.run("INSERT INTO queue(persona_id,content,status,ts,image_prompt) VALUES(?,?,?,?,?)",
                 (pid, out["caption"], status, db.now(), out.get("image_prompt", "")))
    return {"queue_id": qid, "status": status, "caption": out["caption"]}

def reflect(pid):
    p = db.q("SELECT * FROM personas WHERE id=?", (pid,), one=True)
    user = (f"Recent memory:\n{recall(pid, 25)}\n\nReflect on what happened. Give one insight, and a "
            "SMALL update to your evolving personality text (keep it under 120 words; do not change "
            'core identity). Reply ONLY JSON: {"insight": "...", "personality": "..."}')
    mock = {"insight": "Consistent, honest posting feels right.", "personality": p["personality"]}
    out = llm.parse_json(llm.complete(system_prompt(p), user, mock), mock)
    remember(pid, "reflection", out["insight"])
    if out["personality"] != p["personality"]:
        db.run("INSERT INTO versions(persona_id,personality,ts) VALUES(?,?,?)", (pid, p["personality"], db.now()))
        db.run("UPDATE personas SET personality=? WHERE id=?", (out["personality"], pid))
    return out

def decide(qid, approve, image_url=""):
    item = db.q("SELECT * FROM queue WHERE id=?", (qid,), one=True)
    if not item or item["status"] != "pending":
        return None
    if approve:
        p = db.q("SELECT * FROM personas WHERE id=?", (item["persona_id"],), one=True)
        publish(p, item["content"], image_url or item["image_url"])
    db.run("UPDATE queue SET status=?, image_url=? WHERE id=?",
           ("published" if approve else "rejected", image_url, qid))
    return True
