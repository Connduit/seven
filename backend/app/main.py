from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from . import db, agent
from .llm import LLMError

app = FastAPI(title="AI Influencers")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
db.init()

@app.exception_handler(LLMError)
async def llm_err(_, e): return JSONResponse({"detail": str(e)}, status_code=502)

@app.exception_handler(agent.PublishError)
async def pub_err(_, e): return JSONResponse({"detail": str(e)}, status_code=400)

class PersonaIn(BaseModel):
    name: str
    handle: str = ""
    core: str
    goal: str
    personality: str = "curious and friendly"
    life: str = ""
    autonomy: str = "approve"

class PersonaPatch(BaseModel):
    goal: str | None = None
    personality: str | None = None
    life: str | None = None
    autonomy: str | None = None
    paused: bool | None = None
    ig_user_id: str | None = None
    ig_token: str | None = None

class Approve(BaseModel):
    image_url: str = ""

def public(p):
    """Never send the Instagram token back to the browser."""
    if p:
        p["ig_connected"] = agent.ig_connected(p)
        p.pop("ig_token", None)
    return p

def get(pid): return public(db.q("SELECT * FROM personas WHERE id=?", (pid,), one=True))

@app.get("/api/personas")
def list_personas():
    return [public(p) for p in db.q("SELECT * FROM personas ORDER BY id")]

@app.post("/api/personas")
def create(p: PersonaIn):
    pid = db.run("INSERT INTO personas(name,handle,core,goal,personality,life,autonomy) VALUES(?,?,?,?,?,?,?)",
                 (p.name, p.handle, p.core, p.goal, p.personality, p.life, p.autonomy))
    return get(pid)

@app.patch("/api/personas/{pid}")
def patch(pid: int, p: PersonaPatch):
    for k, v in p.model_dump(exclude_none=True).items():
        db.run(f"UPDATE personas SET {k}=? WHERE id=?", (int(v) if k == "paused" else v, pid))
    return get(pid)

@app.delete("/api/personas/{pid}")
def delete(pid: int):
    for t in ("memories", "queue", "versions"):
        db.run(f"DELETE FROM {t} WHERE persona_id=?", (pid,))
    db.run("DELETE FROM personas WHERE id=?", (pid,))
    return {"ok": True}

@app.post("/api/personas/{pid}/tick")
def tick(pid: int): return agent.tick(pid)

@app.post("/api/personas/{pid}/reflect")
def reflect(pid: int): return agent.reflect(pid)

@app.get("/api/personas/{pid}/memories")
def memories(pid: int):
    return db.q("SELECT * FROM memories WHERE persona_id=? ORDER BY ts DESC LIMIT 50", (pid,))

@app.get("/api/queue")
def queue():
    return db.q("SELECT q.*, p.name FROM queue q JOIN personas p ON p.id=q.persona_id "
                "WHERE q.status='pending' ORDER BY q.ts DESC")

@app.post("/api/queue/{qid}/approve")
def approve(qid: int, body: Approve = Approve()):
    if not agent.decide(qid, True, body.image_url.strip()):
        raise HTTPException(404, "Pending item not found")
    return {"ok": True}

@app.post("/api/queue/{qid}/reject")
def reject(qid: int):
    if not agent.decide(qid, False):
        raise HTTPException(404, "Pending item not found")
    return {"ok": True}
