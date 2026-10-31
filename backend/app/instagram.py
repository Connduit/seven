"""Instagram professional-account OAuth. No publishing endpoints are exposed."""
import hashlib
import os
import secrets
import time
from typing import Literal
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import Base, db, find

router = APIRouter(prefix="/api")
REQUIRED = ['INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_REDIRECT_URI', 'TOKEN_ENCRYPTION_KEY', 'STUDIO_ADMIN_KEY']
SCOPES = 'instagram_business_basic,instagram_business_content_publish'
COOKIE = 'studio_instagram_state'
COOKIE_PATH = '/api/integrations/instagram'


class InstagramConnection(Base):
    __tablename__ = 'instagram_connections'
    id: Mapped[int] = mapped_column(primary_key=True)
    influencer_id: Mapped[int] = mapped_column(index=True)
    account_id: Mapped[str] = mapped_column(unique=True)
    username: Mapped[str]
    encrypted_token: Mapped[str]
    expires_at: Mapped[int]
    publishing_policy: Mapped[str] = mapped_column(default='disabled')
    daily_post_limit: Mapped[int] = mapped_column(default=1)


class OAuthAttempt(Base):
    __tablename__ = 'instagram_oauth_attempts'
    state_hash: Mapped[str] = mapped_column(primary_key=True)
    influencer_id: Mapped[int]
    expires_at: Mapped[int]


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def configuration():
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:
        raise HTTPException(503, 'Instagram setup requires: ' + ', '.join(missing))
    try:
        Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode())
        redirect = urlsplit(os.environ['INSTAGRAM_REDIRECT_URI'])
        # Meta requires the exact callback registered in its developer console.
        if redirect.scheme != 'https' or not redirect.netloc or redirect.username or redirect.fragment or redirect.query or redirect.path != COOKIE_PATH + '/callback':
            raise ValueError('Invalid redirect URI')
        frontend = urlsplit(os.getenv('STUDIO_FRONTEND_URL', 'http://localhost:5173'))
        if frontend.scheme not in ('http', 'https') or not frontend.netloc or frontend.username or frontend.query or frontend.fragment:
            raise ValueError('Invalid frontend URL')
        if len(os.environ['STUDIO_ADMIN_KEY']) < 32:
            raise ValueError('Admin key too short')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Invalid Instagram configuration. Check the encryption key, HTTPS callback URL, frontend URL, and admin key (32+ characters).')


def admin(x_studio_key: str = Header(default='')):
    expected = os.getenv('STUDIO_ADMIN_KEY', '')
    if expected and len(expected) < 32:
        raise HTTPException(503, 'Configure a studio administrator key of at least 32 characters.')
    if not expected or not secrets.compare_digest(x_studio_key, expected):
        raise HTTPException(401, 'Enter the studio administrator key to manage connected accounts.')


def public(connection):
    return {'id': connection.id, 'username': connection.username, 'account_id': connection.account_id,
            'expires_at': connection.expires_at, 'expired': connection.expires_at <= time.time(),
            'publishing_policy': connection.publishing_policy, 'daily_post_limit': connection.daily_post_limit,
            'publishing_available': False}


@router.get('/integrations/instagram/setup')
def setup():
    try:
        configuration()
        return {'configured': True, 'message': 'Instagram OAuth configured. Use a professional Instagram account.'}
    except HTTPException as exc:
        return {'configured': False, 'message': exc.detail}


@router.get('/influencers/{influencer_id}/instagram', dependencies=[Depends(admin)])
def connections(influencer_id: int, session: Session = Depends(db)):
    find(session, influencer_id)
    return [public(c) for c in session.scalars(select(InstagramConnection).where(InstagramConnection.influencer_id == influencer_id))]


@router.post('/influencers/{influencer_id}/instagram/connect', dependencies=[Depends(admin)])
def connect(influencer_id: int, response: Response, session: Session = Depends(db)):
    configuration()
    find(session, influencer_id)
    state = secrets.token_urlsafe(32)
    session.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at < int(time.time())))
    session.add(OAuthAttempt(state_hash=digest(state), influencer_id=influencer_id, expires_at=int(time.time()) + 600))
    session.commit()
    response.set_cookie(COOKIE, state, max_age=600, httponly=True, secure=True, samesite='lax', path=COOKIE_PATH)
    return {'authorization_url': 'https://www.instagram.com/oauth/authorize?' + urlencode({
        'client_id': os.environ['INSTAGRAM_APP_ID'], 'redirect_uri': os.environ['INSTAGRAM_REDIRECT_URI'],
        'response_type': 'code', 'scope': SCOPES, 'state': state, 'enable_fb_login': '0', 'force_authentication': '1'})}


async def exchange(code):
    """Short-lived code -> long-lived token -> verified account identity."""
    async with httpx.AsyncClient(timeout=30) as client:
        short = await client.post('https://api.instagram.com/oauth/access_token', data={
            'client_id': os.environ['INSTAGRAM_APP_ID'], 'client_secret': os.environ['INSTAGRAM_APP_SECRET'],
            'grant_type': 'authorization_code', 'redirect_uri': os.environ['INSTAGRAM_REDIRECT_URI'], 'code': code})
        short.raise_for_status()
        token = short.json()['access_token']
        long = await client.get('https://graph.instagram.com/access_token', params={
            'grant_type': 'ig_exchange_token', 'client_secret': os.environ['INSTAGRAM_APP_SECRET'], 'access_token': token})
        long.raise_for_status()
        data = long.json()
        token = data['access_token']
        lifetime = int(data['expires_in'])
        if not token or lifetime <= 0:
            raise ValueError('Invalid token response')
        identity = await client.get('https://graph.instagram.com/me', params={'fields': 'user_id,username'}, headers={'Authorization': f'Bearer {token}'})
        identity.raise_for_status()
        account = identity.json()
        return str(account['user_id']), account['username'], token, int(time.time()) + lifetime


@router.get('/integrations/instagram/callback')
async def callback(request: Request, session: Session = Depends(db)):
    configuration()
    state = request.query_params.get('state', '')
    cookie = request.cookies.get(COOKIE, '')
    if not state or not cookie or not secrets.compare_digest(state, cookie):
        raise HTTPException(400, 'Invalid authorization state. Start a new connection from the studio.')
    attempt = session.get(OAuthAttempt, digest(state))
    if not attempt or attempt.expires_at <= time.time():
        raise HTTPException(400, 'Authorization expired or was already used. Start again.')
    influencer_id = attempt.influencer_id
    # Consume before external calls: a callback cannot be replayed, even concurrently.
    consumed = session.execute(delete(OAuthAttempt).where(OAuthAttempt.state_hash == digest(state)))
    session.commit()
    if consumed.rowcount != 1:
        raise HTTPException(400, 'Authorization was already used.')
    find(session, influencer_id)
    outcome = 'cancelled'
    if not request.query_params.get('error') and request.query_params.get('code'):
        try:
            account_id, username, token, expires = await exchange(request.query_params['code'])
            existing = session.scalar(select(InstagramConnection).where(InstagramConnection.account_id == account_id))
            if existing and existing.influencer_id != influencer_id:
                outcome = 'account_already_linked'
            else:
                encrypted = Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode()).encrypt(token.encode()).decode()
                if existing:
                    existing.encrypted_token, existing.expires_at, existing.username = encrypted, expires, username
                    existing.publishing_policy = 'disabled'
                else:
                    session.add(InstagramConnection(influencer_id=influencer_id, account_id=account_id, username=username,
                                                    encrypted_token=encrypted, expires_at=expires))
                session.commit()
                outcome = 'connected'
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IntegrityError):
            session.rollback()
            outcome = 'failed'
    result = RedirectResponse(os.getenv('STUDIO_FRONTEND_URL', 'http://localhost:5173').rstrip('/') + '/?' + urlencode({'instagram': outcome}), status_code=303)
    result.delete_cookie(COOKIE, path=COOKIE_PATH, secure=True, httponly=True, samesite='lax')
    result.headers['Cache-Control'] = 'no-store'
    result.headers['Referrer-Policy'] = 'no-referrer'
    return result


class Policy(BaseModel):
    # Autonomous mode is deliberately unavailable until the publishing engine exists.
    publishing_policy: Literal['disabled', 'approval_required']
    daily_post_limit: int = Field(ge=1, le=25)


def owned(session, influencer_id, connection_id):
    connection = session.get(InstagramConnection, connection_id)
    if not connection or connection.influencer_id != influencer_id:
        raise HTTPException(404, 'Connected account not found')
    return connection


@router.patch('/influencers/{influencer_id}/instagram/{connection_id}', dependencies=[Depends(admin)])
def policy(influencer_id: int, connection_id: int, payload: Policy, session: Session = Depends(db)):
    connection = owned(session, influencer_id, connection_id)
    connection.publishing_policy = payload.publishing_policy
    connection.daily_post_limit = payload.daily_post_limit
    session.commit()
    return public(connection)


@router.delete('/influencers/{influencer_id}/instagram/{connection_id}', status_code=204, dependencies=[Depends(admin)])
def disconnect(influencer_id: int, connection_id: int, session: Session = Depends(db)):
    # Remove local credentials. Provider permission revocation is available in Instagram settings.
    session.delete(owned(session, influencer_id, connection_id))
    session.commit()
