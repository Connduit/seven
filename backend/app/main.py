import os
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timezone
from typing import Literal

import httpx
from .prompts import character_instructions
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, ForeignKey, String, Text, Date, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session, relationship


class Base(DeclarativeBase):
    pass


class Influencer(Base):
    __tablename__ = "influencers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    personality: Mapped[str] = mapped_column(Text)
    interests: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="paused")
    biography_record: Mapped["Biography"] = relationship("Biography", cascade="all, delete-orphan", uselist=False)

    @property
    def biography(self):
        return self.biography_record or {}


class Biography(Base):
    __tablename__ = "persona_biographies"
    influencer_id: Mapped[int] = mapped_column(ForeignKey("influencers.id"), primary_key=True)
    birthdate: Mapped[date | None] = mapped_column(Date, nullable=True)
    birthplace: Mapped[str] = mapped_column(default="")
    current_location: Mapped[str] = mapped_column(default="")
    pronouns: Mapped[str] = mapped_column(default="")
    occupation: Mapped[str] = mapped_column(default="")
    background: Mapped[str] = mapped_column(Text, default="")
    appearance: Mapped[str] = mapped_column(Text, default="")


class Entry(Base):
    __tablename__ = "entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    influencer_id: Mapped[int] = mapped_column(ForeignKey("influencers.id"), index=True)
    kind: Mapped[str]
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(default=lambda: datetime.now(timezone.utc).isoformat())


engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./studio.db"), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine)
Base.metadata.create_all(engine)
@asynccontextmanager
async def lifespan(app):
    from .token_refresh import refresh_worker
    task = asyncio.create_task(refresh_worker(SessionLocal))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AI Influencer Studio", version="0.1.0", lifespan=lifespan)


def db():
    with SessionLocal() as session:
        yield session


class BiographyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)
    birthdate: date | None = None
    birthplace: str = Field(default="", max_length=200)
    current_location: str = Field(default="", max_length=200)
    pronouns: str = Field(default="", max_length=100)
    occupation: str = Field(default="", max_length=200)
    background: str = Field(default="", max_length=10000)
    appearance: str = Field(default="", max_length=3000)

    @field_validator('birthdate')
    @classmethod
    def valid_birthdate(cls, value):
        if value and value > date.today():
            raise ValueError('Birthdate cannot be in the future')
        return value


class InfluencerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    personality: str = Field(min_length=1, max_length=10000)
    interests: str = Field(min_length=1, max_length=10000)
    goal: str = Field(min_length=1, max_length=10000)
    status: Literal["paused", "active", "archived"] = "paused"
    biography: BiographyInput = Field(default_factory=BiographyInput)


class InfluencerOutput(InfluencerInput):
    model_config = ConfigDict(from_attributes=True)
    id: int


class EntryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    influencer_id: int
    kind: str
    role: str
    content: str
    created_at: str


class Prompt(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=10000)


def find(session: Session, influencer_id: int):
    item = session.get(Influencer, influencer_id)
    if not item:
        raise HTTPException(404, "Influencer not found")
    return item


def history(session, influencer_id, kind):
    return list(session.scalars(select(Entry).where(Entry.influencer_id == influencer_id, Entry.kind == kind).order_by(Entry.id)))


async def generate(item, messages):
    identity = character_instructions(item)
    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            response = await client.post(
                os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + os.getenv("LLM_API_KEY", "local")},
                json={"model": os.getenv("LLM_MODEL", "local"), "messages": [{"role": "system", "content": identity}, *messages], "max_tokens": 600},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty completion")
            return content
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        raise HTTPException(503, "Inference unavailable. Start llama.cpp and check LLM_BASE_URL and LLM_MODEL.")


@app.get("/api/health")
def health():
    return {"status": "ok", "publishing_enabled": False}


@app.get("/api/influencers", response_model=list[InfluencerOutput])
def list_influencers(session: Session = Depends(db)):
    return list(session.scalars(select(Influencer).order_by(Influencer.id)))


@app.post("/api/influencers", response_model=InfluencerOutput, status_code=201)
def create(payload: InfluencerInput, session: Session = Depends(db)):
    item = Influencer(**payload.model_dump(exclude={"biography"}))
    item.biography_record = Biography(**payload.biography.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@app.put("/api/influencers/{influencer_id}", response_model=InfluencerOutput)
def update(influencer_id: int, payload: InfluencerInput, session: Session = Depends(db)):
    item = find(session, influencer_id)
    for key, value in payload.model_dump(exclude={"biography"}).items():
        setattr(item, key, value)
    if 'biography' in payload.model_fields_set:
        if item.biography_record is None:
            item.biography_record = Biography(**payload.biography.model_dump())
        else:
            for key, value in payload.biography.model_dump().items():
                setattr(item.biography_record, key, value)
    session.commit()
    session.refresh(item)
    return item


@app.get("/api/influencers/{influencer_id}/entries", response_model=list[EntryOutput])
def entries(influencer_id: int, session: Session = Depends(db)):
    find(session, influencer_id)
    return list(session.scalars(select(Entry).where(Entry.influencer_id == influencer_id).order_by(Entry.id)))


@app.post("/api/influencers/{influencer_id}/chat", response_model=EntryOutput)
async def chat(influencer_id: int, payload: Prompt, session: Session = Depends(db)):
    item = find(session, influencer_id)
    messages = [{"role": e.role, "content": e.content} for e in history(session, influencer_id, "chat")[-20:]]
    content = await generate(item, [*messages, {"role": "user", "content": payload.content}])
    session.add(Entry(influencer_id=influencer_id, kind="chat", role="user", content=payload.content))
    result = Entry(influencer_id=influencer_id, kind="chat", role="assistant", content=content)
    session.add(result)
    session.commit()
    session.refresh(result)
    return result


@app.post("/api/influencers/{influencer_id}/drafts", response_model=EntryOutput, status_code=201)
async def draft(influencer_id: int, payload: Prompt, session: Session = Depends(db)):
    item = find(session, influencer_id)
    content = await generate(item, [{"role": "user", "content": "Write a social media post draft only. Brief: " + payload.content}])
    result = Entry(influencer_id=influencer_id, kind="draft", role="assistant", content=content)
    session.add(result)
    session.commit()
    session.refresh(result)
    return result


class SocialPage(Base):
    __tablename__ = "social_pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    influencer_id: Mapped[int] = mapped_column(ForeignKey("influencers.id"), index=True)
    platform: Mapped[str]
    url: Mapped[str]


SocialPage.__table__.create(engine, checkfirst=True)


class SocialPageInput(BaseModel):
    platform: Literal["Instagram", "TikTok", "YouTube", "X", "Bluesky", "Reddit", "Snapchat"]
    url: str = Field(min_length=1, max_length=2048)


class SocialPageOutput(SocialPageInput):
    model_config = ConfigDict(from_attributes=True)
    id: int


@app.get("/api/influencers/{influencer_id}/social-pages", response_model=list[SocialPageOutput])
def social_pages(influencer_id: int, session: Session = Depends(db)):
    find(session, influencer_id)
    return list(session.scalars(select(SocialPage).where(SocialPage.influencer_id == influencer_id).order_by(SocialPage.id)))


@app.post("/api/influencers/{influencer_id}/social-pages", response_model=SocialPageOutput, status_code=201)
def add_social_page(influencer_id: int, payload: SocialPageInput, session: Session = Depends(db)):
    from urllib.parse import urlsplit
    find(session, influencer_id)
    hosts = {"Instagram": ["instagram.com"], "TikTok": ["tiktok.com"], "YouTube": ["youtube.com"], "X": ["x.com", "twitter.com"], "Bluesky": ["bsky.app"], "Reddit": ["reddit.com"], "Snapchat": ["snapchat.com"]}
    try:
        parsed = urlsplit(payload.url)
        host = (parsed.hostname or "").removeprefix("www.")
        valid = parsed.scheme == "https" and host in hosts[payload.platform] and not parsed.username and not parsed.password and parsed.port in (None, 443) and parsed.path.strip('/')
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "Enter an HTTPS profile URL for the selected platform.")
    page = SocialPage(influencer_id=influencer_id, **payload.model_dump())
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


@app.delete("/api/influencers/{influencer_id}/social-pages/{page_id}", status_code=204)
def remove_social_page(influencer_id: int, page_id: int, session: Session = Depends(db)):
    page = session.get(SocialPage, page_id)
    if not page or page.influencer_id != influencer_id:
        raise HTTPException(404, "Social page not found")
    session.delete(page)
    session.commit()


class StatusInput(BaseModel):
    status: Literal["paused", "active", "archived"]


@app.patch("/api/influencers/{influencer_id}/status", response_model=InfluencerOutput)
def change_status(influencer_id: int, payload: StatusInput, session: Session = Depends(db)):
    item = find(session, influencer_id)
    item.status = payload.status
    session.commit()
    session.refresh(item)
    return item


@app.delete("/api/influencers/{influencer_id}", status_code=204)
def delete_influencer(influencer_id: int, session: Session = Depends(db), x_studio_key: str = Header(default='')):
    from sqlalchemy import delete
    item = find(session, influencer_id)
    if (session.scalar(select(InstagramConnection).where(InstagramConnection.influencer_id == influencer_id))
            or session.scalar(select(VaultAccount).where(VaultAccount.influencer_id == influencer_id))
            or session.scalar(select(LinkedAccount).where(LinkedAccount.influencer_id == influencer_id))):
        from .instagram import admin
        admin(x_studio_key)
    session.execute(delete(Entry).where(Entry.influencer_id == influencer_id))
    session.execute(delete(SocialPage).where(SocialPage.influencer_id == influencer_id))
    session.execute(delete(InstagramConnection).where(InstagramConnection.influencer_id == influencer_id))
    session.execute(delete(OAuthAttempt).where(OAuthAttempt.influencer_id == influencer_id))
    session.execute(delete(RefreshState).where(RefreshState.connection_id.in_(select(LinkedAccount.id).where(LinkedAccount.influencer_id == influencer_id))))
    session.execute(delete(LinkedAccount).where(LinkedAccount.influencer_id == influencer_id))
    session.execute(delete(LinkAttempt).where(LinkAttempt.influencer_id == influencer_id))
    for account in session.scalars(select(VaultAccount).where(VaultAccount.influencer_id == influencer_id)):
        account.influencer_id = None
    session.delete(item)
    session.commit()


from .instagram import router as instagram_router, InstagramConnection, OAuthAttempt
Base.metadata.create_all(engine)
app.include_router(instagram_router)


from .vault import router as vault_router, VaultAccount
Base.metadata.create_all(engine)
app.include_router(vault_router)


# Validation failures for credential routes must never echo submitted passwords.
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import request_validation_exception_handler


@app.exception_handler(RequestValidationError)
async def safe_validation_errors(request, exc):
    if request.url.path.startswith('/api/accounts/'):
        return JSONResponse(status_code=422, content={'detail': 'Invalid account details. Check required fields, field lengths, and the HTTPS website URL.'})
    return await request_validation_exception_handler(request, exc)


@app.middleware('http')
async def credential_response_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/accounts/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response


from .oauth import router as oauth_router, LinkedAccount, LinkAttempt
Base.metadata.create_all(engine)
app.include_router(oauth_router)


from .token_refresh import RefreshState
Base.metadata.create_all(engine)
